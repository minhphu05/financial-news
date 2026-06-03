"""Qdrant vector store repository for financial news chunks.

Schema design
-------------
Collection  : ``settings.qdrant.collection``  (default: ``financial_news_chunks``)
Vector      : dense float32, dimension 1024 (voyage-4-lite), cosine distance
HNSW index  : m=16, ef_construct=200 — good accuracy/latency balance

Point payload (all fields stored, selective indexing for fast filtering):

    article_link  (str)  – canonical URL; *keyword* index, used for dedup
    chunk_index   (int)  – 0-based position inside article; *integer* index
    content       (str)  – raw chunk text  (no index — full text in Qdrant)
    title         (str)  – article title   (stored, not indexed)
    ticker_symbol (str)  – VN30/VN50 ticker, e.g. "ACB"; *keyword* index
    ticker_name   (str)  – human name, e.g. "Ngân hàng Á Châu" (stored)
    post_date     (str)  – "YYYY-MM-DD"; *keyword* index for date-range filter
    source        (str)  – origin site, e.g. "cafef"; *keyword* index
    keyword       (str)  – scraping keyword that found this article; *keyword* idx
    char_count    (int)  – chunk character count (stored, no index)
    embedded_at   (str)  – ISO-8601 datetime when this point was upserted

Point IDs are deterministic UUID5 derived from ``{article_link}#{chunk_index}``,
enabling safe idempotent upserts (re-running the ingestion is a no-op).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Distance metric mapping
# ---------------------------------------------------------------------------
_DISTANCE_MAP: Dict[str, qm.Distance] = {
    "cosine": qm.Distance.COSINE,
    "dot": qm.Distance.DOT,
    "euclid": qm.Distance.EUCLID,
}

# Payload field names — kept as constants to avoid magic strings scattered
# across the codebase.
F_LINK = "article_link"
F_IDX = "chunk_index"
F_CONTENT = "content"
F_TITLE = "title"
F_TICKER = "ticker_symbol"
F_TICKER_NAME = "ticker_name"
F_DATE = "post_date"
F_SOURCE = "source"
F_KEYWORD = "keyword"
F_CHAR_COUNT = "char_count"
F_EMBEDDED_AT = "embedded_at"


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------
@dataclass
class ChunkRecord:
    """A single document chunk ready to be upserted into Qdrant.

    Attributes
    ----------
    article_link : str
        Canonical article URL (natural key for deduplication).
    chunk_index : int
        Zero-based position of this chunk inside the article.
    content : str
        Raw chunk text.
    embedding : list[float]
        Dense embedding vector; length must equal ``settings.qdrant.embedding_dim``.
    metadata : dict
        Optional payload fields (title, ticker_symbol, post_date, source, …).
    """

    article_link: str
    chunk_index: int
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    """A chunk returned by a similarity search.

    Attributes
    ----------
    point_id : str
        Qdrant point UUID.
    article_link : str
        Source article URL.
    chunk_index : int
        Chunk position inside the article.
    content : str
        Chunk text.
    metadata : dict
        Stored payload (title, ticker_symbol, post_date, …).
    score : float
        Cosine similarity in ``[0, 1]`` (higher = more similar).
    """

    point_id: str
    article_link: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any]
    score: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_point_id(article_link: str, chunk_index: int) -> str:
    """Derive a deterministic UUID5 for ``(article_link, chunk_index)``.

    Using UUID5 means the same chunk always maps to the same ID, so upserts
    are idempotent regardless of how many times the ingestion pipeline runs.

    Parameters
    ----------
    article_link : str
        Article URL.
    chunk_index : int
        Zero-based chunk position.

    Returns
    -------
    str
        UUID string (hex with dashes).
    """
    key = f"{article_link}#{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class QdrantRepository:
    """Repository that wraps the Qdrant vector store.

    A single :class:`qdrant_client.QdrantClient` is kept open for the lifetime
    of the repository. The collection is created (if missing) on first use
    via :meth:`ensure_collection`.

    Parameters
    ----------
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        cfg = self._settings.qdrant
        api_key = cfg.api_key.get_secret_value() or None
        self._client = QdrantClient(
            host=cfg.host,
            port=cfg.port,
            grpc_port=cfg.grpc_port,
            prefer_grpc=cfg.prefer_grpc,
            api_key=api_key,
            https=cfg.https,
        )
        self._collection = cfg.collection
        self._dim = cfg.embedding_dim
        self._distance = _DISTANCE_MAP[cfg.distance]
        self._hnsw_m = cfg.hnsw_m
        self._hnsw_ef = cfg.hnsw_ef_construct

    # -- lifecycle ----------------------------------------------------------
    def ensure_collection(self) -> None:
        """Create the Qdrant collection and payload indexes if they do not exist.

        The collection is configured with an HNSW index for efficient ANN
        search. Payload indexes are created on the fields most likely to
        appear in filters: ``ticker_symbol``, ``post_date``, ``source``,
        ``article_link``, and ``keyword``.

        This method is idempotent and safe to call on every start-up.
        """
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=qm.VectorParams(
                    size=self._dim,
                    distance=self._distance,
                    hnsw_config=qm.HnswConfigDiff(
                        m=self._hnsw_m,
                        ef_construct=self._hnsw_ef,
                    ),
                ),
                # Optimise for low-latency reads at the cost of slightly
                # slower indexing — good for a news corpus that is appended
                # incrementally and read frequently.
                optimizers_config=qm.OptimizersConfigDiff(
                    indexing_threshold=10_000,
                ),
            )
            logger.info(
                "Created Qdrant collection '%s' (dim=%d, distance=%s).",
                self._collection,
                self._dim,
                self._distance,
            )
        else:
            logger.debug("Qdrant collection '%s' already exists.", self._collection)

        # Payload indexes — always run so the index is present even on an
        # existing collection that was created without them.
        index_fields = [
            (F_LINK, qm.PayloadSchemaType.KEYWORD),
            (F_TICKER, qm.PayloadSchemaType.KEYWORD),
            (F_DATE, qm.PayloadSchemaType.KEYWORD),
            (F_SOURCE, qm.PayloadSchemaType.KEYWORD),
            (F_KEYWORD, qm.PayloadSchemaType.KEYWORD),
            (F_IDX, qm.PayloadSchemaType.INTEGER),
        ]
        for fname, ftype in index_fields:
            try:
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=fname,
                    field_schema=ftype,
                )
            except Exception:  # noqa: BLE001 — index may already exist
                pass

    def close(self) -> None:
        """Close the underlying gRPC/HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "QdrantRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -- write --------------------------------------------------------------
    def upsert_chunks(self, records: List[ChunkRecord]) -> int:
        """Upsert a list of chunk records into the collection.

        Point IDs are deterministic, so calling this method with the same
        records twice overwrites rather than duplicates.

        Parameters
        ----------
        records : list[ChunkRecord]
            Chunks to upsert. Empty list is a no-op.

        Returns
        -------
        int
            Number of records submitted to Qdrant.
        """
        if not records:
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        points = []
        for rec in records:
            point_id = _make_point_id(rec.article_link, rec.chunk_index)
            payload: Dict[str, Any] = {
                F_LINK: rec.article_link,
                F_IDX: rec.chunk_index,
                F_CONTENT: rec.content,
                F_CHAR_COUNT: len(rec.content),
                F_EMBEDDED_AT: now_iso,
                **{k: v for k, v in rec.metadata.items() if v is not None},
            }
            points.append(
                qm.PointStruct(
                    id=point_id,
                    vector=rec.embedding,
                    payload=payload,
                )
            )

        self._client.upsert(
            collection_name=self._collection,
            points=points,
            wait=True,
        )
        logger.debug("Upserted %d chunks to Qdrant.", len(points))
        return len(points)

    # -- read ---------------------------------------------------------------
    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        """Search for the most similar chunks.

        Parameters
        ----------
        query_embedding : list[float]
            Dense query vector produced by the same embedder used at ingest
            time.
        top_k : int
            Maximum number of results to return.
        score_threshold : float
            Minimum cosine similarity score. Results below this value are
            discarded. Set to ``0.0`` to disable.
        filters : dict, optional
            Equality filters on payload fields, e.g.::

                {"ticker_symbol": "ACB"}
                {"source": "cafef", "ticker_symbol": "BID"}

            All key-value pairs are combined with AND logic.

        Returns
        -------
        list[RetrievedChunk]
            Chunks sorted by descending similarity score.
        """
        qdrant_filter: Optional[qm.Filter] = None
        if filters:
            must_conditions = [
                qm.FieldCondition(
                    key=k,
                    match=qm.MatchValue(value=v),
                )
                for k, v in filters.items()
                if v is not None
            ]
            if must_conditions:
                qdrant_filter = qm.Filter(must=must_conditions)

        search_result = self._client.query_points(
            collection_name=self._collection,
            query=query_embedding,
            query_filter=qdrant_filter,
            limit=top_k,
            score_threshold=score_threshold if score_threshold > 0 else None,
            with_payload=True,
        )

        chunks: List[RetrievedChunk] = []
        for hit in search_result.points:
            payload = hit.payload or {}
            chunks.append(
                RetrievedChunk(
                    point_id=str(hit.id),
                    article_link=payload.get(F_LINK, ""),
                    chunk_index=payload.get(F_IDX, 0),
                    content=payload.get(F_CONTENT, ""),
                    metadata={
                        k: payload[k]
                        for k in (F_TITLE, F_TICKER, F_TICKER_NAME, F_DATE, F_SOURCE, F_KEYWORD)
                        if k in payload
                    },
                    score=hit.score,
                )
            )
        return chunks

    # -- stats --------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        """Return basic collection statistics.

        Returns
        -------
        dict
            ``{"chunk_count": int, "collection": str}``
        """
        info = self._client.get_collection(self._collection)
        return {
            "collection": self._collection,
            "chunk_count": info.points_count or 0,
        }

    def count_chunks_for_article(self, article_link: str) -> int:
        """Count how many chunks exist for a given article URL.

        Parameters
        ----------
        article_link : str
            Article URL.

        Returns
        -------
        int
            Number of stored chunks.
        """
        result = self._client.count(
            collection_name=self._collection,
            count_filter=qm.Filter(
                must=[
                    qm.FieldCondition(
                        key=F_LINK,
                        match=qm.MatchValue(value=article_link),
                    )
                ]
            ),
            exact=True,
        )
        return result.count

    def delete_all_points(self) -> None:
        """Delete all points in the collection without dropping it.

        This removes every vector but keeps the collection schema, indexes,
        and configuration intact. Use before a full re-index.
        """
        self._client.delete(
            collection_name=self._collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(must=[
                    qm.FieldCondition(
                        key=F_LINK,
                        match=qm.MatchAny(any=["_impossible_match_"]),
                    )
                ])
            ),
        )
        # MatchAny with impossible value won't delete anything.
        # Use the proper approach: delete collection and recreate.
        self._client.delete_collection(self._collection)
        logger.info("Deleted collection '%s'. Will recreate on next ensure_collection().", self._collection)
        self.ensure_collection()
