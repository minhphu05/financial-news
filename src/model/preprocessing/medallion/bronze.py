"""Bronze layer: extract raw scraped articles into Polars frames.

The Bronze layer is the **landing zone** for the scraper. Raw articles
live in MongoDB (``cafef_raw``); this module reads them out as a Polars
:class:`polars.DataFrame` so the silver stage can consume a typed,
vectorised dataset.

It is intentionally read-only: persistence is owned by the scraper and
the quality gate. The Bronze stage merely *exposes* the lake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import polars as pl

from src.rag.config import Settings, get_settings
from src.rag.databases import MongoRepository
from src.rag.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
BRONZE_COLUMNS: List[str] = [
    "link",
    "title",
    "context",
    "summary",
    "post_date",
    "is_magazine",
    "source",
    "scraped_keyword",
    "keyword",
    "page",
    "ticker_symbol",
    "ticker_name",
    "scraped_at",
]


@dataclass
class BronzeReport:
    """Stats produced by a Bronze read."""

    rows: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        """Stamp ``finished_at`` with current UTC time."""
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable summary."""
        return {
            "rows": self.rows,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------
class BronzeStage:
    """Extract raw articles from MongoDB into a Polars DataFrame.

    Parameters
    ----------
    mongo : MongoRepository
        Repository used for the read.
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.
    """

    def __init__(
        self,
        mongo: MongoRepository,
        settings: Optional[Settings] = None,
    ) -> None:
        self._mongo = mongo
        self._settings = settings or get_settings()

    def read(
        self,
        link_skip: Optional[List[str]] = None,
        batch_size: int = 500,
    ) -> tuple[pl.DataFrame, BronzeReport]:
        """Materialise the bronze dataset.

        Parameters
        ----------
        link_skip : Optional[list[str]]
            Article links to exclude (e.g. already processed in silver).
        batch_size : int
            Mongo cursor batch size.

        Returns
        -------
        (DataFrame, BronzeReport)
            The dataset and an aggregated report for telemetry.
        """
        report = BronzeReport()
        skip_set = set(link_skip or [])

        rows: List[Dict[str, Any]] = []
        query: Dict[str, Any] = {}
        if skip_set:
            query = {"link": {"$nin": list(skip_set)}}

        cursor = self._mongo._raw.find(query, batch_size=batch_size)
        for doc in cursor:
            rows.append({col: doc.get(col) for col in BRONZE_COLUMNS})

        report.rows = len(rows)
        df = (
            pl.DataFrame(rows, schema=_bronze_schema(), strict=False)
            if rows
            else pl.DataFrame(schema=_bronze_schema())
        )
        report.mark_done()
        logger.info("Bronze read: %s rows", report.rows)
        return df, report


def _bronze_schema() -> Dict[str, pl.DataType]:
    """Polars schema for the bronze DataFrame.

    We use ``Utf8`` for everything except the page index and the
    ``is_magazine`` flag. Free-form CafeF post dates stay as strings —
    parsing happens in the silver layer.
    """
    return {
        "link": pl.Utf8,
        "title": pl.Utf8,
        "context": pl.Utf8,
        "summary": pl.Utf8,
        "post_date": pl.Utf8,
        "is_magazine": pl.Boolean,
        "source": pl.Utf8,
        "scraped_keyword": pl.Utf8,
        "keyword": pl.Utf8,
        "page": pl.Int64,
        "ticker_symbol": pl.Utf8,
        "ticker_name": pl.Utf8,
        "scraped_at": pl.Datetime,
    }
