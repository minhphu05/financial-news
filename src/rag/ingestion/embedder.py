"""Voyage AI embedding client with built-in rate limiting.

Wraps the ``voyageai`` SDK to produce embedding vectors for ingestion
(``input_type="document"``) and query time (``input_type="query"``).

The wrapper batches requests automatically (honouring Voyage AI's per-call
limits), validates output dimensionality, and applies exponential-backoff
retries so it can run unattended inside a Prefect flow.

Rate Limiting
-------------
Voyage AI's free tier enforces **3 RPM** (requests per minute) and
**10,000 TPM** (tokens per minute) across all models. The embedder
throttles outgoing requests to stay under both limits:

* A sliding-window limiter ensures at most 3 requests per 60-second window.
* Batch sizes are capped based on estimated token counts so that no single
  request exceeds the TPM budget.

Model notes
-----------
``voyage-4-lite`` is a lightweight, high-throughput model that supports
output dimensions of 512 (default) or 1024 (extended). We default to 1024
for better retrieval quality; configure via ``VOYAGE_EMBEDDING_DIM=512``
if cost or memory is a concern.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, List, Optional, Sequence

import voyageai

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit constants (Voyage AI free tier)
# ---------------------------------------------------------------------------
_MAX_RPM = 3            # Maximum requests per minute
_RPM_WINDOW = 60.0      # Sliding window in seconds
_MAX_TPM = 10_000       # Maximum tokens per minute
# Rough estimate: Vietnamese text averages ~1.3 tokens per character.
_CHARS_PER_TOKEN = 0.77  # conservative (1 / 1.3)


class VoyageAIEmbedder:
    """Embedding generator backed by Voyage AI with rate limiting.

    The embedder enforces the free-tier limits (3 RPM / 10K TPM) via a
    sliding-window request tracker. Batches are dynamically sized based on
    estimated token counts to avoid exceeding the TPM quota.

    Parameters
    ----------
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.
    client : Optional[voyageai.Client]
        Pre-built Voyage AI client. Mostly useful for testing.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[voyageai.Client] = None,
    ) -> None:
        self._settings = settings or get_settings()
        cfg = self._settings.voyage
        api_key = cfg.api_key.get_secret_value()
        if not api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY is empty. "
                "Set it in the environment or in `.env`."
            )
        self._client = client or voyageai.Client(api_key=api_key)
        self._model = cfg.embedding_model
        self._dim = cfg.embedding_dim
        self._batch_size = cfg.batch_size
        self._max_retries = cfg.max_retries

        # Sliding window of request timestamps for RPM limiting.
        self._request_timestamps: Deque[float] = deque()

    # -- public API ---------------------------------------------------------
    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed a list of documents (article chunks).

        Uses ``input_type="document"`` which is optimised for indexing
        and biased toward recall. Automatically rate-limits to 3 RPM.

        Parameters
        ----------
        texts : Sequence[str]
            Chunk texts to embed.

        Returns
        -------
        list[list[float]]
            One embedding vector per input text, in the same order.
        """
        return self._embed(list(texts), input_type="document")

    def embed_query(self, text: str) -> List[float]:
        """Embed a single user query.

        Uses ``input_type="query"`` which is optimised for precision
        (finding the most relevant passage for a short question).

        Parameters
        ----------
        text : str
            User question (Vietnamese or English).

        Returns
        -------
        list[float]
            Embedding vector of length ``settings.voyage.embedding_dim``.
        """
        vectors = self._embed([text], input_type="query")
        return vectors[0]

    # -- rate limiting ------------------------------------------------------
    def _estimate_tokens(self, texts: List[str]) -> int:
        """Estimate token count for a batch of texts.

        Vietnamese text has roughly 1.3 tokens per character on average.
        We use a conservative multiplier to stay safely within limits.

        Parameters
        ----------
        texts : list[str]
            Texts whose token usage to estimate.

        Returns
        -------
        int
            Estimated token count.
        """
        total_chars = sum(len(t) for t in texts)
        return int(total_chars / _CHARS_PER_TOKEN)

    def _wait_for_rate_limit(self) -> None:
        """Block until a request slot is available within the RPM window.

        Enforces two constraints:
        1. Sliding window: at most ``_MAX_RPM`` requests per 60s window.
        2. Minimum interval: at least ``_RPM_WINDOW / _MAX_RPM`` seconds
           between consecutive requests (ensures even spacing).
        """
        min_interval = _RPM_WINDOW / _MAX_RPM  # 20s for 3 RPM
        now = time.monotonic()

        # Purge timestamps outside the window.
        while self._request_timestamps and (now - self._request_timestamps[0]) >= _RPM_WINDOW:
            self._request_timestamps.popleft()

        wait_seconds = 0.0

        # Constraint 1: sliding window capacity.
        if len(self._request_timestamps) >= _MAX_RPM:
            oldest = self._request_timestamps[0]
            wait_seconds = max(wait_seconds, _RPM_WINDOW - (now - oldest) + 1.0)

        # Constraint 2: minimum interval since last request.
        if self._request_timestamps:
            last = self._request_timestamps[-1]
            elapsed = now - last
            if elapsed < min_interval:
                wait_seconds = max(wait_seconds, min_interval - elapsed + 0.5)

        if wait_seconds > 0:
            logger.info(
                "Rate limit: waiting %.1fs before next Voyage AI request "
                "(%d/%d slots used in window).",
                wait_seconds,
                len(self._request_timestamps),
                _MAX_RPM,
            )
            time.sleep(wait_seconds)
            # Purge again after sleeping.
            now = time.monotonic()
            while self._request_timestamps and (now - self._request_timestamps[0]) >= _RPM_WINDOW:
                self._request_timestamps.popleft()

    def _record_request(self) -> None:
        """Record a request timestamp in the sliding window."""
        self._request_timestamps.append(time.monotonic())

    def _make_token_safe_batches(self, texts: List[str]) -> List[List[str]]:
        """Split texts into batches that fit within both batch_size and TPM limits.

        Each batch is capped at:
        - ``self._batch_size`` texts (SDK limit).
        - Estimated tokens ≤ ``_MAX_TPM // _MAX_RPM`` (per-request token budget
          so that 3 requests/min stays under 10K TPM).

        Parameters
        ----------
        texts : list[str]
            All texts to embed.

        Returns
        -------
        list[list[str]]
            Batches ready to send, each within safe limits.
        """
        # Per-request token budget: spread TPM evenly across allowed RPM.
        per_request_token_budget = _MAX_TPM // _MAX_RPM  # ~3333 tokens

        batches: List[List[str]] = []
        current_batch: List[str] = []
        current_tokens = 0

        for text in texts:
            text_tokens = int(len(text) / _CHARS_PER_TOKEN)

            # If a single text exceeds the budget, it gets its own batch.
            if text_tokens > per_request_token_budget:
                if current_batch:
                    batches.append(current_batch)
                    current_batch, current_tokens = [], 0
                batches.append([text])
                continue

            # Check if adding this text would exceed limits.
            if (
                len(current_batch) >= self._batch_size
                or current_tokens + text_tokens > per_request_token_budget
            ):
                if current_batch:
                    batches.append(current_batch)
                current_batch = [text]
                current_tokens = text_tokens
            else:
                current_batch.append(text)
                current_tokens += text_tokens

        if current_batch:
            batches.append(current_batch)

        return batches

    # -- internals ----------------------------------------------------------
    def _embed(
        self,
        texts: List[str],
        input_type: str,
    ) -> List[List[float]]:
        """Issue batched embedding calls with rate limiting and retries.

        Parameters
        ----------
        texts : list[str]
            Texts to embed.
        input_type : str
            ``"document"`` for indexing, ``"query"`` for retrieval queries.

        Returns
        -------
        list[list[float]]
            Flat list of embedding vectors in input order.

        Raises
        ------
        RuntimeError
            If all retry attempts are exhausted for any batch.
        """
        if not texts:
            return []

        batches = self._make_token_safe_batches(texts)
        vectors: List[List[float]] = []

        for batch_idx, batch in enumerate(batches):
            est_tokens = self._estimate_tokens(batch)
            logger.debug(
                "Embedding batch %d/%d (%d texts, ~%d tokens).",
                batch_idx + 1,
                len(batches),
                len(batch),
                est_tokens,
            )

            for attempt in range(1, self._max_retries + 1):
                # Wait for a rate-limit slot before sending.
                self._wait_for_rate_limit()

                try:
                    self._record_request()
                    response = self._client.embed(
                        texts=batch,
                        model=self._model,
                        input_type=input_type,
                        output_dimension=self._dim,
                    )
                    for emb in response.embeddings:
                        values = list(emb)
                        if len(values) != self._dim:
                            raise RuntimeError(
                                f"Voyage AI returned dimension {len(values)}, "
                                f"expected {self._dim}. "
                                f"Check VOYAGE_EMBEDDING_DIM in .env."
                            )
                        vectors.append(values)
                    break  # success — move to next batch
                except Exception as exc:  # noqa: BLE001
                    err_msg = str(exc).lower()
                    is_rate_limit = (
                        "rate limit" in err_msg
                        or "429" in err_msg
                        or "reduced rate limits" in err_msg
                    )
                    if is_rate_limit:
                        # Server-side rate limit: wait a full window.
                        wait = _RPM_WINDOW + 1.0
                    else:
                        wait = min(60, 2 ** attempt)
                    logger.warning(
                        "Voyage AI embedding batch %d/%d failed "
                        "(attempt %d/%d, rate_limited=%s): %s. Retrying in %ds.",
                        batch_idx + 1,
                        len(batches),
                        attempt,
                        self._max_retries,
                        is_rate_limit,
                        exc,
                        int(wait),
                    )
                    time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Failed to embed batch {batch_idx + 1}/{len(batches)} "
                    f"after {self._max_retries} attempts."
                )

        return vectors

