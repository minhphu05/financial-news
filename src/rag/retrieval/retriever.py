"""Semantic retriever for the RAG pipeline.

The retriever combines :class:`VoyageAIEmbedder` (query embeddings) and
:class:`QdrantRepository` (vector search) to fetch the top-K most
similar chunks for a user question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.rag.config import Settings, get_settings
from src.rag.databases import QdrantRepository
from src.rag.databases.qdrant_client import RetrievedChunk
from src.rag.ingestion.embedder import VoyageAIEmbedder
from src.rag.utils import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """The output of a retrieval call.

    Attributes
    ----------
    query : str
        The user question that was used.
    chunks : List[RetrievedChunk]
        Top-K chunks ranked by similarity.
    """

    query: str
    chunks: List[RetrievedChunk] = field(default_factory=list)

    def to_context(self, max_chars: int = 6000) -> str:
        """Concatenate chunks into a single context string.

        Parameters
        ----------
        max_chars : int
            Hard limit on the resulting string size to avoid blowing the
            LLM context window.

        Returns
        -------
        str
            ``"[1] <chunk1>\\n[2] <chunk2>..."`` formatted block.
        """
        out: List[str] = []
        total = 0
        for idx, chunk in enumerate(self.chunks, start=1):
            block = f"[{idx}] {chunk.content.strip()}"
            if total + len(block) > max_chars:
                break
            out.append(block)
            total += len(block)
        return "\n\n".join(out)


class Retriever:
    """High-level retrieval API used by the chatbot.

    Parameters
    ----------
    embedder : VoyageAIEmbedder
        Voyage AI embedding generator used to encode queries.
    qdrant : QdrantRepository
        Qdrant vector store to query.
    settings : Optional[Settings]
        Settings override.
    """

    def __init__(
        self,
        embedder: VoyageAIEmbedder,
        qdrant: QdrantRepository,
        settings: Optional[Settings] = None,
    ) -> None:
        self._embedder = embedder
        self._qdrant = qdrant
        self._settings = settings or get_settings()

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> RetrievalResult:
        """Embed ``query`` and return the most similar chunks.

        Parameters
        ----------
        query : str
            User question, in Vietnamese or English.
        top_k : Optional[int]
            Override for ``settings.retrieval.top_k``.
        score_threshold : Optional[float]
            Override for ``settings.retrieval.score_threshold``.
        filters : Optional[dict]
            Equality filters on stored metadata (e.g. ``{"ticker_symbol": "BCM"}``).

        Returns
        -------
        RetrievalResult
            Wrapped retrieval result.
        """
        if not query or not query.strip():
            return RetrievalResult(query=query, chunks=[])

        top_k = top_k or self._settings.retrieval.top_k
        score_threshold = (
            score_threshold
            if score_threshold is not None
            else self._settings.retrieval.score_threshold
        )

        embedding = self._embedder.embed_query(query)
        chunks: List[RetrievedChunk] = self._qdrant.similarity_search(
            query_embedding=embedding,
            top_k=top_k,
            score_threshold=score_threshold,
            filters=filters,
        )
        logger.info("Retrieved %d chunks for query='%s'", len(chunks), query[:60])
        return RetrievalResult(query=query, chunks=chunks)
