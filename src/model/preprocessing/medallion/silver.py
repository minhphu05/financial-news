"""Silver layer: Polars-native cleaning, dedup and normalisation.

The silver stage takes the bronze DataFrame (see :mod:`bronze`) and
returns a clean, indexable dataset:

* Whitespace collapsed, Unicode NFC-normalised.
* Glued digit/letter pairs separated.
* CafeF boilerplate suffixes removed.
* Empty bodies dropped.
* Articles deduplicated by URL **and** by content hash (helpful when
  CafeF republishes the same article under a different URL).

Polars expressions are used wherever possible so the work is vectorised
and trivially parallel. Slow per-row work (NFC normalisation, the small
regex set) lives behind a single ``map_elements`` call to keep the rest
of the pipeline branch-free.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import polars as pl

from src.rag.config import Settings, get_settings
from src.rag.databases import MongoRepository
from src.rag.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Regex compiled once at import time
# ---------------------------------------------------------------------------
_BOILERPLATE_PATTERNS: List[re.Pattern] = [
    re.compile(r"theo\s+(cafef|cafe\s*f|nhịp sống.*)", re.IGNORECASE),
    re.compile(r"nguồn\s*:\s*cafe\s*f.*", re.IGNORECASE),
    re.compile(r"theo\s+nhịp sống.*", re.IGNORECASE),
    re.compile(r"đọc thêm.*", re.IGNORECASE),
]
_MULTI_WS = re.compile(r"[ \t\u00a0]+")
_MULTI_NL = re.compile(r"\n{3,}")
_STUCK_DL = re.compile(r"(?<=[a-zA-Zà-ỹÀ-Ỹ])(\d)")
_STUCK_LD = re.compile(r"(?<=\d)([a-zA-Zà-ỹÀ-Ỹ])")


def _normalise_text(text: Optional[str]) -> Optional[str]:
    """Apply the full cleaning pipeline to one body.

    Returns ``None`` for empty inputs so that downstream Polars filters
    drop the row entirely.
    """
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    if not text.strip():
        return None

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _STUCK_DL.sub(r" \1", text)
    text = _STUCK_LD.sub(r" \1", text)
    text = _MULTI_WS.sub(" ", text)
    text = _MULTI_NL.sub("\n\n", text)

    for pat in _BOILERPLATE_PATTERNS:
        text = pat.sub("", text)

    cleaned = text.strip()
    return cleaned or None


def _content_hash(text: Optional[str]) -> Optional[str]:
    """SHA-1 of a stripped, lowercased body — used for content-level dedup."""
    if not text:
        return None
    digest = hashlib.sha1(text.strip().lower().encode("utf-8"))
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class SilverReport:
    """Stats produced by a Silver run."""

    input_rows: int = 0
    cleaned_rows: int = 0
    dedup_dropped: int = 0
    written: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        """Stamp ``finished_at``."""
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly summary."""
        return {
            "input_rows": self.input_rows,
            "cleaned_rows": self.cleaned_rows,
            "dedup_dropped": self.dedup_dropped,
            "written": self.written,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------
class SilverStage:
    """Polars-native cleaning / deduplication for the silver layer.

    Parameters
    ----------
    mongo : MongoRepository
        Mongo repository used to upsert silver rows.
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

    # -- transform ---------------------------------------------------------
    def transform(self, bronze: pl.DataFrame) -> pl.DataFrame:
        """Apply cleaning + deduplication.

        Parameters
        ----------
        bronze : polars.DataFrame
            Output of :class:`BronzeStage.read`.

        Returns
        -------
        polars.DataFrame
            Silver dataset, sorted by ``cleaned_at`` descending. Empty if
            the bronze frame was empty.
        """
        if bronze.is_empty():
            return bronze

        df = bronze.lazy()

        # 1) Clean body + title using a vectorised map_elements call.
        df = df.with_columns(
            pl.col("context")
            .map_elements(_normalise_text, return_dtype=pl.Utf8)
            .alias("clean_text"),
            pl.col("title")
            .map_elements(_normalise_text, return_dtype=pl.Utf8)
            .alias("clean_title"),
        )

        # 2) Drop rows that ended up empty after cleaning.
        df = df.filter(pl.col("clean_text").is_not_null())

        # 3) Compute content_hash + char_count.
        df = df.with_columns(
            pl.col("clean_text")
            .map_elements(_content_hash, return_dtype=pl.Utf8)
            .alias("content_hash"),
            pl.col("clean_text").str.len_chars().alias("char_count"),
        )

        # 4) Normalise ticker case.
        df = df.with_columns(
            pl.col("ticker_symbol").str.to_uppercase().alias("ticker_symbol"),
        )

        # 5) Stamp cleaned_at.
        now = datetime.now(timezone.utc)
        df = df.with_columns(pl.lit(now).alias("cleaned_at"))

        # 6) Deduplicate: first by link, then by content_hash.
        df = df.unique(subset=["link"], keep="last", maintain_order=True)
        df = df.unique(subset=["content_hash"], keep="first", maintain_order=True)

        # 7) Final projection + ordering.
        df = df.select(
            [
                "link",
                pl.col("clean_title").alias("title"),
                "summary",
                "post_date",
                "ticker_symbol",
                "ticker_name",
                "keyword",
                "source",
                "clean_text",
                "char_count",
                "content_hash",
                "cleaned_at",
            ]
        )

        return df.collect()

    # -- persistence -------------------------------------------------------
    def write(self, silver: pl.DataFrame) -> int:
        """Upsert the silver DataFrame into ``cafef_clean``.

        Parameters
        ----------
        silver : polars.DataFrame
            Output of :meth:`transform`.

        Returns
        -------
        int
            Number of rows persisted.
        """
        if silver.is_empty():
            return 0

        for row in silver.iter_rows(named=True):
            self._mongo.upsert_clean(_to_mongo_doc(row))
        return silver.height

    # -- combined ----------------------------------------------------------
    def run(self, bronze: pl.DataFrame) -> tuple[pl.DataFrame, SilverReport]:
        """Run :meth:`transform` then :meth:`write` and return a report."""
        report = SilverReport(input_rows=bronze.height)
        silver = self.transform(bronze)
        report.dedup_dropped = max(0, report.input_rows - silver.height)
        report.cleaned_rows = silver.height
        report.written = self.write(silver)
        report.mark_done()
        logger.info("Silver run: %s", report.as_dict())
        return silver, report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_mongo_doc(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Polars row dict into the Mongo clean-doc shape.

    Polars dates come back as Python ``datetime`` instances which pymongo
    serialises natively. ``clean_text`` is required; everything else is
    optional / nullable in MongoDB.
    """
    return {
        "link": row["link"],
        "title": row.get("title"),
        "summary": row.get("summary"),
        "post_date": row.get("post_date"),
        "ticker_symbol": row.get("ticker_symbol"),
        "ticker_name": row.get("ticker_name"),
        "keyword": row.get("keyword"),
        "source": row.get("source") or "cafef.vn",
        "clean_text": row["clean_text"],
        "char_count": int(row.get("char_count") or 0),
        "content_hash": row.get("content_hash"),
    }
