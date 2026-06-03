"""Async RAG service that fronts the chatbot with a semantic cache.

The Voyage AI SDK + Qdrant client are both blocking — to expose them through
an async-friendly surface (``await service.ask(...)``) we:

1. Embed the query (cache-aware).
2. Look up the semantic cache; if it hits, return immediately.
3. Otherwise run the regular RAG path inside :func:`asyncio.to_thread`
   so the event loop is never blocked.
4. Write the new answer back to the cache.

This wrapper composes the existing :class:`FinanceRAGChatbot` so we
don't duplicate prompt / retrieval logic.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.rag.agent import FinanceRAGChatbot
from src.rag.caching.semantic_cache import CachedAnswer, SemanticCache
from src.rag.config import Settings, get_settings
from src.rag.ingestion import VoyageAIEmbedder
from src.rag.utils import get_logger

logger = get_logger(__name__)


@dataclass
class AsyncChatResult:
    """Async-friendly chatbot response payload.

    Attributes
    ----------
    answer : str
        Generated answer.
    citations : list[dict]
        Citations as returned by the chatbot (or replayed from cache).
    cache_hit : bool
        ``True`` if the answer came from the semantic cache.
    cache_score : Optional[float]
        Similarity score when ``cache_hit`` is true.
    latency_ms : float
        End-to-end latency in milliseconds (includes cache lookup).
    """

    answer: str
    citations: List[Dict[str, Any]]
    cache_hit: bool
    cache_score: Optional[float]
    latency_ms: float


class AsyncRAGService:
    """Async wrapper around the synchronous chatbot.

    Parameters
    ----------
    chatbot : FinanceRAGChatbot
        Existing chatbot instance (handles retrieval + OpenRouter chat).
    embedder : VoyageAIEmbedder
        Used to embed user queries for the semantic cache.
    cache : Optional[SemanticCache]
        Override the default cache (defaults to a fresh
        :class:`SemanticCache` built from settings).
    settings : Optional[Settings]
        Settings override.
    """

    def __init__(
        self,
        chatbot: FinanceRAGChatbot,
        embedder: VoyageAIEmbedder,
        cache: Optional[SemanticCache] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self._chatbot = chatbot
        self._embedder = embedder
        self._settings = settings or get_settings()
        self._cache = cache or SemanticCache(self._settings)

    async def ask(
        self,
        question: str,
        model: Optional[str] = None,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
        bypass_cache: bool = False,
    ) -> AsyncChatResult:
        """Answer ``question`` with cache awareness.

        Parameters
        ----------
        question : str
            User question.
        model : Optional[str]
            OpenRouter model ID. ``None`` uses the settings default.
        top_k, score_threshold, filters :
            Forwarded to :meth:`FinanceRAGChatbot.ask`.
        bypass_cache : bool
            When ``True``, skip the cache lookup entirely (useful for the
            evaluation runner).

        Returns
        -------
        AsyncChatResult
            Combined response + cache telemetry.
        """
        started = time.monotonic()
        embedding = await self._embed_query(question)

        # 1) Cache lookup ------------------------------------------------
        if not bypass_cache:
            hit = await asyncio.to_thread(self._cache.lookup, embedding)
            if hit is not None:
                latency = (time.monotonic() - started) * 1000
                return AsyncChatResult(
                    answer=hit.entry.answer,
                    citations=hit.entry.citations,
                    cache_hit=True,
                    cache_score=hit.score,
                    latency_ms=latency,
                )

        # 2) Fall back to the synchronous chatbot in a worker thread ----
        response = await asyncio.to_thread(
            self._chatbot.ask,
            question=question,
            model=model,
            top_k=top_k,
            score_threshold=score_threshold,
            filters=filters,
        )

        # 3) Persist the answer in the cache -----------------------------
        try:
            entry = CachedAnswer(
                question=question,
                embedding=embedding,
                answer=response.answer,
                citations=list(response.citations),
            )
            await asyncio.to_thread(self._cache.put, entry)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache write failed (%s); continuing.", exc)

        latency = (time.monotonic() - started) * 1000
        return AsyncChatResult(
            answer=response.answer,
            citations=list(response.citations),
            cache_hit=False,
            cache_score=None,
            latency_ms=latency,
        )

    # -- internals --------------------------------------------------------
    async def _embed_query(self, question: str) -> List[float]:
        """Embed the query, consulting the embedding sub-cache first."""
        cached = await asyncio.to_thread(self._cache.get_embedding, question)
        if cached is not None:
            return cached
        embedding = await asyncio.to_thread(self._embedder.embed_query, question)
        await asyncio.to_thread(self._cache.set_embedding, question, embedding)
        return embedding
