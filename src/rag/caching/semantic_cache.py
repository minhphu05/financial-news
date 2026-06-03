"""Semantic cache for chatbot answers.

The cache stores each ``(question, embedding, answer, citations)`` tuple
in Redis. At lookup time:

1. The user's query is embedded (cheap, also cached).
2. Every stored entry is loaded and compared via cosine similarity.
3. If the best match exceeds ``CACHE_SIMILARITY_THRESHOLD`` the cached
   answer is returned without calling the LLM.
4. Otherwise the caller falls back to the regular RAG path and writes
   the new answer back to the cache.

The implementation deliberately uses a brute-force scan — it is fast for
a few thousand entries and avoids a RediSearch dependency. For larger
deployments the lookup can be swapped for ``ft.search`` against a vector
index without changing the public API.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from src.rag.caching.redis_client import get_redis_client
from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public DTOs
# ---------------------------------------------------------------------------
@dataclass
class CachedAnswer:
    """Payload stored against each cached question."""

    question: str
    embedding: List[float]
    answer: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time())

    def to_json(self) -> str:
        """Serialise the entry to JSON for Redis storage."""
        return json.dumps(self.__dict__, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: bytes | str) -> "CachedAnswer":
        """Inverse of :meth:`to_json`."""
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        data = json.loads(text)
        return cls(
            question=data["question"],
            embedding=list(data["embedding"]),
            answer=data["answer"],
            citations=list(data.get("citations", [])),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class SemanticHit:
    """Result of a successful semantic lookup."""

    entry: CachedAnswer
    score: float
    key: str


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
class SemanticCache:
    """Redis-backed semantic cache for RAG answers.

    Parameters
    ----------
    settings : Optional[Settings]
        Settings override. The cache reads its parameters from
        ``settings.cache``.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._cfg = self._settings.cache
        self._redis = get_redis_client(self._settings)
        self._ns = self._cfg.namespace

    @property
    def enabled(self) -> bool:
        """``True`` if the cache is wired to a real Redis instance."""
        return self._cfg.enabled and self._redis.__class__.__name__ != "NullRedis"

    # -- embedding sub-cache ---------------------------------------------
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Return a cached embedding for ``text`` or ``None``."""
        if not self.enabled:
            return None
        raw = self._redis.get(self._embedding_key(text))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_embedding(self, text: str, embedding: Sequence[float]) -> None:
        """Persist an embedding for ``text`` (TTL: ``embedding_ttl_seconds``)."""
        if not self.enabled:
            return
        self._redis.setex(
            self._embedding_key(text),
            self._cfg.embedding_ttl_seconds,
            json.dumps(list(embedding)),
        )

    # -- answer cache -----------------------------------------------------
    def lookup(self, embedding: Sequence[float]) -> Optional[SemanticHit]:
        """Find the best cached answer for ``embedding``.

        Parameters
        ----------
        embedding : Sequence[float]
            Embedding of the user's query.

        Returns
        -------
        Optional[SemanticHit]
            The best hit if its score exceeds
            ``settings.cache.similarity_threshold``, otherwise ``None``.
        """
        if not self.enabled:
            return None

        best: Optional[SemanticHit] = None
        for key in self._iter_answer_keys():
            try:
                raw = self._redis.get(key)
            except Exception:
                continue
            if not raw:
                continue
            try:
                entry = CachedAnswer.from_json(raw)
            except (KeyError, json.JSONDecodeError):
                continue
            score = _cosine(embedding, entry.embedding)
            if best is None or score > best.score:
                best = SemanticHit(entry=entry, score=score, key=key.decode() if isinstance(key, bytes) else key)

        if best and best.score >= self._cfg.similarity_threshold:
            logger.info(
                "Semantic cache HIT (score=%.3f, q=%r)",
                best.score,
                best.entry.question[:60],
            )
            return best
        return None

    def put(self, entry: CachedAnswer) -> str:
        """Persist a new answer and return its Redis key.

        Soft-LRU eviction kicks in once the cache size exceeds
        ``max_entries`` (oldest entries by ``created_at`` go first).
        """
        if not self.enabled:
            return ""

        key = self._answer_key(entry.question)
        self._redis.setex(key, self._cfg.answer_ttl_seconds, entry.to_json())
        self._redis.zadd(self._index_key(), {key: entry.created_at})

        self._evict_if_needed()
        return key.decode() if isinstance(key, bytes) else key

    def clear(self) -> int:
        """Delete every entry under the configured namespace."""
        count = 0
        if not self.enabled:
            return count
        for key in self._iter_answer_keys():
            self._redis.delete(key)
            count += 1
        self._redis.delete(self._index_key())
        return count

    # -- internals --------------------------------------------------------
    def _evict_if_needed(self) -> None:
        """Drop the oldest entries when the namespace gets too large."""
        total = self._redis.zcard(self._index_key())
        excess = total - self._cfg.max_entries
        if excess <= 0:
            return
        oldest = self._redis.zrange(self._index_key(), 0, excess - 1)
        for key in oldest:
            self._redis.delete(key)
            self._redis.zrem(self._index_key(), key)

    def _iter_answer_keys(self):
        """Iterate over every answer key in the namespace."""
        pattern = f"{self._ns}:rag:ans:*"
        yield from self._redis.scan_iter(match=pattern)

    def _embedding_key(self, text: str) -> str:
        digest = hashlib.sha1(text.strip().encode("utf-8")).hexdigest()
        return f"{self._ns}:embed:{digest}"

    def _answer_key(self, text: str) -> str:
        digest = hashlib.sha1(text.strip().encode("utf-8")).hexdigest()
        return f"{self._ns}:rag:ans:{digest}"

    def _index_key(self) -> str:
        return f"{self._ns}:rag:index"


# ---------------------------------------------------------------------------
# Math
# ---------------------------------------------------------------------------
def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length float vectors.

    Returns ``-1.0`` for invalid inputs so the lookup safely skips them.
    """
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0:
        return -1.0
    return dot / denom
