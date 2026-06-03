"""PGVector repository for storing and searching document chunks.

The repository uses raw ``psycopg`` with the ``pgvector`` Python adapter to
keep dependencies light. A single table named ``settings.pgvector.table``
stores every chunk along with its embedding and rich metadata.

Schema
------
::

    CREATE TABLE document_chunks (
        id           BIGSERIAL PRIMARY KEY,
        article_link TEXT        NOT NULL,
        chunk_index  INTEGER     NOT NULL,
        content      TEXT        NOT NULL,
        metadata     JSONB       NOT NULL DEFAULT '{}',
        embedding    VECTOR(<dim>) NOT NULL,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (article_link, chunk_index)
    );
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------
@dataclass
class ChunkRecord:
    """A single chunk ready to be persisted in PGVector.

    Attributes
    ----------
    article_link : str
        URL of the source article (foreign key to the Mongo clean collection).
    chunk_index : int
        Zero-based position of the chunk inside the article.
    content : str
        Raw chunk text.
    embedding : Sequence[float]
        Embedding vector. Must have length equal to ``settings.pgvector.embedding_dim``.
    metadata : dict
        Free-form metadata (title, ticker, post_date, ...).
    """

    article_link: str
    chunk_index: int
    content: str
    embedding: Sequence[float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    """A chunk returned by similarity search.

    Attributes
    ----------
    id : int
        Primary key in the chunks table.
    article_link : str
        URL of the source article.
    chunk_index : int
        Index of the chunk in the article.
    content : str
        Chunk text.
    metadata : dict
        Persisted metadata.
    score : float
        Normalised similarity score in ``[0, 1]`` (higher = more similar).
    """

    id: int
    article_link: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any]
    score: float


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
_DISTANCE_OP = {"cosine": "<=>", "l2": "<->", "inner": "<#>"}


class PgVectorRepository:
    """Repository for the ``document_chunks`` table.

    The class is intentionally connection-aware (one persistent connection
    is kept open) to amortise the cost of registering the ``vector`` codec.

    Parameters
    ----------
    settings : Optional[Settings]
        Optional settings override (defaults to :func:`get_settings`).
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._dim = self._settings.pgvector.embedding_dim
        self._table = self._settings.pgvector.table
        self._distance_op = _DISTANCE_OP[self._settings.pgvector.distance]
        self._conn: psycopg.Connection = psycopg.connect(
            self._settings.pgvector.sync_dsn, autocommit=True
        )
        register_vector(self._conn)

    # -- schema -------------------------------------------------------------
    def ensure_schema(self) -> None:
        """Create the ``vector`` extension, table and indexes if absent."""
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id           BIGSERIAL PRIMARY KEY,
                    article_link TEXT        NOT NULL,
                    chunk_index  INTEGER     NOT NULL,
                    content      TEXT        NOT NULL,
                    metadata     JSONB       NOT NULL DEFAULT '{{}}'::jsonb,
                    embedding    VECTOR({self._dim}) NOT NULL,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (article_link, chunk_index)
                );
                """
            )
            opclass = {
                "cosine": "vector_cosine_ops",
                "l2": "vector_l2_ops",
                "inner": "vector_ip_ops",
            }[self._settings.pgvector.distance]
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {self._table}_embedding_idx
                ON {self._table}
                USING ivfflat (embedding {opclass})
                WITH (lists = 100);
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS {self._table}_link_idx "
                f"ON {self._table} (article_link);"
            )
        logger.info("Ensured PGVector schema (table=%s, dim=%s).", self._table, self._dim)

    # -- writes -------------------------------------------------------------
    def upsert_chunks(self, chunks: Sequence[ChunkRecord]) -> int:
        """Upsert a batch of chunks.

        The unique constraint on ``(article_link, chunk_index)`` is used to
        perform an idempotent ``INSERT ... ON CONFLICT DO UPDATE``.

        Parameters
        ----------
        chunks : Sequence[ChunkRecord]
            Chunks to write. All embeddings must have length ``embedding_dim``.

        Returns
        -------
        int
            Number of rows affected.
        """
        if not chunks:
            return 0

        for ch in chunks:
            if len(ch.embedding) != self._dim:
                raise ValueError(
                    f"Embedding for {ch.article_link}#{ch.chunk_index} has "
                    f"length {len(ch.embedding)}, expected {self._dim}."
                )

        sql = f"""
            INSERT INTO {self._table}
                (article_link, chunk_index, content, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (article_link, chunk_index) DO UPDATE
                SET content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding,
                    created_at = NOW();
        """
        rows = [
            (
                ch.article_link,
                ch.chunk_index,
                ch.content,
                json.dumps(ch.metadata, ensure_ascii=False),
                list(ch.embedding),
            )
            for ch in chunks
        ]
        with self._conn.cursor() as cur:
            cur.executemany(sql, rows)
            return cur.rowcount

    def delete_by_link(self, article_link: str) -> int:
        """Delete every chunk that belongs to ``article_link``.

        Useful when the cleaning step regenerates the chunks for an article.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE article_link = %s;",
                (article_link,),
            )
            return cur.rowcount

    # -- reads --------------------------------------------------------------
    def similarity_search(
        self,
        query_embedding: Sequence[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        """Run vector similarity search.

        Parameters
        ----------
        query_embedding : Sequence[float]
            Embedding of the query (same dim as stored vectors).
        top_k : int
            Maximum number of chunks to return.
        score_threshold : float
            Minimum normalised similarity score (``0.0`` disables filtering).
        filters : Optional[dict]
            Equality filters applied to the ``metadata`` JSONB column, e.g.
            ``{"ticker_symbol": "BCM"}``.

        Returns
        -------
        list[RetrievedChunk]
            Chunks ranked by descending similarity.
        """
        if len(query_embedding) != self._dim:
            raise ValueError(
                f"Query embedding has length {len(query_embedding)}, expected {self._dim}."
            )

        where_clauses: List[str] = []
        filter_params: List[Any] = []
        for key, value in (filters or {}).items():
            where_clauses.append("metadata ->> %s = %s")
            filter_params.extend([key, str(value)])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
            SELECT id, article_link, chunk_index, content, metadata,
                   1 - (embedding {self._distance_op} %s::vector) AS score
            FROM {self._table}
            {where_sql}
            ORDER BY embedding {self._distance_op} %s::vector
            LIMIT %s;
        """
        params: List[Any] = (
            [list(query_embedding)]
            + filter_params
            + [list(query_embedding), top_k]
        )

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        results: List[RetrievedChunk] = []
        for row in rows:
            score = float(row["score"])
            if score < score_threshold:
                continue
            results.append(
                RetrievedChunk(
                    id=row["id"],
                    article_link=row["article_link"],
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    metadata=row["metadata"] or {},
                    score=score,
                )
            )
        return results

    def stats(self) -> Dict[str, int]:
        """Return basic counts for monitoring."""
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self._table};")
            (count,) = cur.fetchone()
        return {"chunk_count": int(count)}

    # -- lifecycle ----------------------------------------------------------
    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> "PgVectorRepository":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
