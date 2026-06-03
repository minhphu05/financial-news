"""Medallion orchestrator: Bronze → Silver → Gold.

The orchestrator wires :class:`BronzeStage`, :class:`SilverStage` and
:class:`GoldStage` into a single, idempotent pipeline. It also pushes
per-layer telemetry to MLflow (best-effort — failures are logged but
don't break the run).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.preprocessing.medallion.bronze import BronzeReport, BronzeStage
from src.preprocessing.medallion.gold import GoldReport, GoldStage
from src.preprocessing.medallion.silver import SilverReport, SilverStage
from src.rag.config import Settings, get_settings
from src.rag.databases import MongoRepository, PgVectorRepository
from src.rag.ingestion import GeminiEmbedder
from src.rag.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class MedallionReport:
    """Combined report covering all three layers."""

    bronze: Optional[BronzeReport] = None
    silver: Optional[SilverReport] = None
    gold: Optional[GoldReport] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        """Stamp ``finished_at`` with UTC now."""
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable summary."""
        return {
            "bronze": self.bronze.as_dict() if self.bronze else None,
            "silver": self.silver.as_dict() if self.silver else None,
            "gold": self.gold.as_dict() if self.gold else None,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class MedallionPipeline:
    """High-level orchestrator for the medallion data flow.

    Parameters
    ----------
    mongo : MongoRepository
        Mongo repository used by Bronze + Silver.
    pgvector : PgVectorRepository
        Vector store used by Gold.
    embedder : GeminiEmbedder
        Embedder used by Gold.
    settings : Optional[Settings]
        Settings override.
    """

    def __init__(
        self,
        mongo: MongoRepository,
        pgvector: PgVectorRepository,
        embedder: GeminiEmbedder,
        settings: Optional[Settings] = None,
    ) -> None:
        self._mongo = mongo
        self._pg = pgvector
        self._embedder = embedder
        self._settings = settings or get_settings()
        self._bronze = BronzeStage(mongo=mongo, settings=self._settings)
        self._silver = SilverStage(mongo=mongo, settings=self._settings)
        self._gold = GoldStage(
            pg=pgvector, embedder=embedder, settings=self._settings
        )

    def run(self, max_articles: Optional[int] = None) -> MedallionReport:
        """Execute the medallion pipeline end-to-end.

        The orchestrator processes:

        1. Articles that have **not** been through the silver layer yet
           (no matching ``cafef_clean`` doc); these are cleaned + persisted
           in Mongo.
        2. Articles that have a silver doc but **no** ``embedded_at`` flag;
           these are chunked, embedded and pushed to PGVector.

        Parameters
        ----------
        max_articles : Optional[int]
            Soft cap on the number of bronze rows pulled in.

        Returns
        -------
        MedallionReport
            Aggregate of the per-layer reports.
        """
        import polars as pl

        report = MedallionReport()
        self._pg.ensure_schema()

        # --- Bronze read (skip rows already in silver) -----------------
        already_silver = [
            d["link"]
            for d in self._mongo._clean.find({}, {"link": 1, "_id": 0})
        ]
        bronze_df, bronze_report = self._bronze.read(link_skip=already_silver)
        if max_articles is not None and bronze_df.height > max_articles:
            bronze_df = bronze_df.head(max_articles)
            bronze_report.rows = bronze_df.height
        report.bronze = bronze_report

        # --- Silver transform + write to Mongo -------------------------
        _, silver_report = self._silver.run(bronze_df)
        report.silver = silver_report

        # --- Gold: read every pending silver doc and embed it ---------
        pending_docs = list(self._mongo.iter_clean_not_embedded())
        if max_articles is not None:
            pending_docs = pending_docs[:max_articles]

        pending_df = (
            pl.DataFrame([_silver_doc_to_row(doc) for doc in pending_docs])
            if pending_docs
            else pl.DataFrame()
        )

        chunks_df, gold_report = (
            (pl.DataFrame(), self._gold_empty_report())
            if pending_df.is_empty()
            else self._run_gold_with_chunk_counts(pending_df)
        )
        report.gold = gold_report

        # --- Mark each embedded article in Mongo ----------------------
        if not chunks_df.is_empty():
            counts = chunks_df.group_by("article_link").agg(pl.len().alias("n"))
            for row in counts.iter_rows(named=True):
                self._mongo.mark_embedded(row["article_link"], int(row["n"]))

        report.mark_done()
        logger.info("Medallion run finished: %s", report.as_dict())
        return report

    # -- helpers -----------------------------------------------------------
    def _run_gold_with_chunk_counts(self, pending_df):
        """Run the gold stage and return ``(chunks_df, report)``.

        Returning the chunks DataFrame lets the orchestrator group by
        ``article_link`` to mark Mongo with the precise number of chunks
        produced.
        """
        report = GoldReport(articles=pending_df.height)
        chunks_df = self._gold.expand_chunks(pending_df)
        report.chunks = chunks_df.height
        report.written = self._gold.load(chunks_df)
        report.mark_done()
        return chunks_df, report

    @staticmethod
    def _gold_empty_report() -> GoldReport:
        """Return a zero-filled :class:`GoldReport` for empty runs."""
        report = GoldReport()
        report.mark_done()
        return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _silver_doc_to_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Project a Mongo ``cafef_clean`` document into a silver row."""
    return {
        "link": doc.get("link"),
        "title": doc.get("title"),
        "summary": doc.get("summary"),
        "post_date": doc.get("post_date"),
        "ticker_symbol": doc.get("ticker_symbol"),
        "ticker_name": doc.get("ticker_name"),
        "keyword": doc.get("keyword"),
        "source": doc.get("source"),
        "clean_text": doc.get("clean_text"),
        "char_count": doc.get("char_count"),
        "content_hash": doc.get("content_hash"),
    }
