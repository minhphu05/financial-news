"""Gold layer: chunk + embed and load into PGVector.

The Gold stage consumes the Silver DataFrame and pushes one row per
chunk into PGVector. It deliberately uses Polars to **expand** chunks
(one input article → N output rows) before handing the list off to the
Gemini embedder so the heavy I/O (the embedding API) operates on a
single flat batch instead of many small per-article calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import polars as pl

from src.rag.config import Settings, get_settings
from src.rag.databases import PgVectorRepository
from src.rag.databases.pgvector_client import ChunkRecord
from src.rag.ingestion import GeminiEmbedder, TextChunker
from src.rag.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class GoldReport:
    """Stats produced by a Gold run."""

    articles: int = 0
    chunks: int = 0
    written: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        """Stamp ``finished_at`` with UTC now."""
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable summary."""
        return {
            "articles": self.articles,
            "chunks": self.chunks,
            "written": self.written,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------
class GoldStage:
    """Chunk + embed a silver DataFrame and bulk-upsert into PGVector.

    Parameters
    ----------
    pg : PgVectorRepository
        Vector store target.
    embedder : GeminiEmbedder
        Embedding generator.
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.
    chunker : Optional[TextChunker]
        Override the default chunker (handy for tests).
    """

    def __init__(
        self,
        pg: PgVectorRepository,
        embedder: GeminiEmbedder,
        settings: Optional[Settings] = None,
        chunker: Optional[TextChunker] = None,
    ) -> None:
        self._pg = pg
        self._embedder = embedder
        self._settings = settings or get_settings()
        self._chunker = chunker or TextChunker(self._settings)

    # -- transform ---------------------------------------------------------
    def expand_chunks(self, silver: pl.DataFrame) -> pl.DataFrame:
        """Expand each silver row into one row per chunk.

        Parameters
        ----------
        silver : polars.DataFrame
            Output of :class:`SilverStage.transform`.

        Returns
        -------
        polars.DataFrame
            DataFrame with columns
            ``[article_link, chunk_index, content, metadata]``.
        """
        if silver.is_empty():
            return pl.DataFrame(
                schema={
                    "article_link": pl.Utf8,
                    "chunk_index": pl.Int64,
                    "content": pl.Utf8,
                    "metadata": pl.Object,
                }
            )

        records: List[Dict[str, Any]] = []
        for row in silver.iter_rows(named=True):
            text = row.get("clean_text") or ""
            if not text:
                continue
            chunks = self._chunker.split(text)
            if not chunks:
                continue

            metadata_base = _metadata_from_row(row)
            for idx, chunk in enumerate(chunks):
                records.append(
                    {
                        "article_link": row["link"],
                        "chunk_index": idx,
                        "content": chunk,
                        "metadata": {**metadata_base, "chunk_index": idx},
                    }
                )

        return pl.DataFrame(records) if records else pl.DataFrame()

    # -- load --------------------------------------------------------------
    def load(self, chunks_df: pl.DataFrame) -> int:
        """Embed + upsert chunks into PGVector.

        Parameters
        ----------
        chunks_df : polars.DataFrame
            Output of :meth:`expand_chunks`.

        Returns
        -------
        int
            Number of rows written to PGVector.
        """
        if chunks_df.is_empty():
            return 0

        # Delete every existing chunk for the affected articles first so
        # we don't accumulate stale entries when chunking parameters change.
        affected_links: List[str] = chunks_df["article_link"].unique().to_list()
        for link in affected_links:
            self._pg.delete_by_link(link)

        # Embed in one batched call so we amortise the network overhead.
        contents = chunks_df["content"].to_list()
        embeddings = self._embedder.embed_documents(contents)
        if len(embeddings) != len(contents):
            raise RuntimeError(
                f"Embedder returned {len(embeddings)} vectors for "
                f"{len(contents)} chunks; aborting Gold load."
            )

        records = [
            ChunkRecord(
                article_link=row["article_link"],
                chunk_index=int(row["chunk_index"]),
                content=row["content"],
                embedding=emb,
                metadata=row["metadata"] or {},
            )
            for row, emb in zip(chunks_df.iter_rows(named=True), embeddings)
        ]
        return self._pg.upsert_chunks(records)

    # -- orchestration ----------------------------------------------------
    def run(self, silver: pl.DataFrame) -> tuple[pl.DataFrame, GoldReport]:
        """Run :meth:`expand_chunks` then :meth:`load` and return a report."""
        report = GoldReport(articles=silver.height)
        chunks_df = self.expand_chunks(silver)
        report.chunks = chunks_df.height
        report.written = self.load(chunks_df)
        report.mark_done()
        logger.info("Gold run: %s", report.as_dict())
        return chunks_df, report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _metadata_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Project a silver row into the JSONB ``metadata`` payload."""
    meta = {
        "title": row.get("title"),
        "post_date": row.get("post_date"),
        "ticker_symbol": row.get("ticker_symbol"),
        "ticker_name": row.get("ticker_name"),
        "keyword": row.get("keyword"),
        "source": row.get("source"),
        "content_hash": row.get("content_hash"),
    }
    return {k: v for k, v in meta.items() if v is not None}
