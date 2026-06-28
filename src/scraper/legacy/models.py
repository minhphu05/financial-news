"""
SQLAlchemy ORM models for the scraper.

Tables
------
* ``news_articles``  - Article *metadata only*. The body lives in MongoDB.
* ``scrape_runs``    - One row per pipeline execution (daily cron, manual run…).
* ``scrape_progress``- Cursor state per (source, keyword) enabling incremental crawl.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models."""


class NewsArticle(Base):
    """
    Metadata row for a single financial news article.

    Field map (per project spec)
    ----------------------------
    * ``news_id``     - unique id extracted from the article URL.
    * ``url``         - canonical article URL.
    * ``title``       - article title.
    * ``summary``     - short teaser pulled from the listing page.
    * ``author``      - byline (best-effort; may be ``None``).
    * ``created_at``  - publication timestamp parsed from the detail page.
    * ``scraped_at``  - UTC timestamp recorded when the row was persisted.

    Additional bookkeeping fields support downstream analytics:

    * ``source``      - source site identifier (e.g. ``cafef``).
    * ``ticker_symbol`` / ``company_name`` - VN30 mapping for the keyword.
    * ``keyword``     - the search keyword that surfaced the article.
    * ``content_ref`` - identifier of the MongoDB document holding the body.
    """

    __tablename__ = "news_articles"

    # ---- Identity --------------------------------------------------------
    news_id = Column(String(64), primary_key=True, doc="Numeric id parsed from URL slug.")

    # ---- Required metadata ----------------------------------------------
    url = Column(String(1024), nullable=False, unique=True)
    title = Column(String(1024), nullable=False)
    summary = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True, doc="Publication time.")
    scraped_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        doc="When this row was written.",
    )

    # ---- Provenance / classification ------------------------------------
    source = Column(String(64), nullable=False)
    ticker_symbol = Column(String(16), nullable=True)
    company_name = Column(String(255), nullable=True)
    keyword = Column(String(255), nullable=True)

    # ---- Cross-store reference ------------------------------------------
    content_ref = Column(
        String(64),
        nullable=True,
        doc="MongoDB _id (== news_id) holding the article body.",
    )

    # ---- Helpful indexes ------------------------------------------------
    __table_args__ = (
        Index("ix_news_articles_created_at", "created_at"),
        Index("ix_news_articles_ticker", "ticker_symbol"),
        Index("ix_news_articles_keyword", "keyword"),
        Index("ix_news_articles_source", "source"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"NewsArticle(news_id={self.news_id!r}, ticker={self.ticker_symbol!r}, "
            f"title={self.title!r:.40})"
        )


# ===========================================================================
# Scrape Tracking Tables
# ===========================================================================
class ScrapeRun(Base):
    """
    One row per pipeline execution.

    Tracks when a scrape run started, when it finished, how many articles
    were found vs. how many were genuinely new, and the final status.
    Useful for daily cron audit and Grafana metrics.
    """

    __tablename__ = "scrape_runs"

    # ---- Identity --------------------------------------------------------
    run_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        doc="Auto-incrementing surrogate key.",
    )

    # ---- Timing ----------------------------------------------------------
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        doc="UTC timestamp when this run was initiated.",
    )
    finished_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="UTC timestamp when this run completed (null if still running).",
    )
    duration_seconds = Column(
        Float,
        nullable=True,
        doc="Wall-clock duration in seconds (computed on finish).",
    )

    # ---- Provenance ------------------------------------------------------
    source = Column(
        String(64),
        nullable=False,
        doc="Source identifier (e.g. 'cafef', 'vnexpress').",
    )
    triggered_by = Column(
        String(64),
        nullable=False,
        default="manual",
        doc="How the run was triggered: 'manual', 'cron', 'prefect', etc.",
    )
    tickers_filter = Column(
        Text,
        nullable=True,
        doc="Comma-separated ticker filter applied to this run (null = all).",
    )

    # ---- Counters --------------------------------------------------------
    articles_found = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Total articles discovered on listing pages.",
    )
    articles_new = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Articles actually persisted (not already in DB).",
    )
    articles_skipped = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Articles skipped because they already exist.",
    )
    pages_crawled = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Total listing pages fetched across all keywords.",
    )
    errors_count = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of non-fatal errors encountered.",
    )

    # ---- Status ----------------------------------------------------------
    status = Column(
        String(32),
        nullable=False,
        default="running",
        doc="Run status: 'running', 'completed', 'failed', 'aborted'.",
    )
    error_message = Column(
        Text,
        nullable=True,
        doc="Top-level error message if status == 'failed'.",
    )

    # ---- Indexes ---------------------------------------------------------
    __table_args__ = (
        Index("ix_scrape_runs_started_at", "started_at"),
        Index("ix_scrape_runs_source_status", "source", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ScrapeRun(run_id={self.run_id}, source={self.source!r}, "
            f"status={self.status!r}, new={self.articles_new})"
        )


class ScrapeProgress(Base):
    """
    Cursor/checkpoint per (source, keyword, ticker) tuple.

    Enables **incremental scraping**: the page scraper reads this table to
    know where it left off and to detect when it has reached articles that
    were already ingested.

    Detection logic:
    ----------------
    1. Before crawling, read ``last_scraped_news_id`` for this keyword.
    2. While crawling, if we encounter ``consecutive_known_threshold``
       articles already in the DB *in a row*, stop early.
    3. After a successful crawl, update the cursor with the newest id seen.
    """

    __tablename__ = "scrape_progress"

    # ---- Composite natural key -------------------------------------------
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        doc="Surrogate PK for ORM convenience.",
    )
    source = Column(String(64), nullable=False, doc="e.g. 'cafef'.")
    keyword = Column(String(255), nullable=False, doc="Search keyword used.")
    ticker_symbol = Column(
        String(16),
        nullable=True,
        doc="Associated ticker (null for generic keywords).",
    )

    # ---- Cursor state ----------------------------------------------------
    last_page_scraped = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Last listing-page index that was fully processed.",
    )
    last_scraped_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When this keyword was last crawled.",
    )
    last_scraped_news_id = Column(
        String(64),
        nullable=True,
        doc="Newest news_id seen in the previous successful crawl.",
    )
    total_articles_scraped = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Lifetime count of articles scraped for this keyword.",
    )

    # ---- Control flags ---------------------------------------------------
    is_exhausted = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="True if the site says no more results exist for this keyword.",
    )

    # ---- Unique constraint on logical key --------------------------------
    __table_args__ = (
        UniqueConstraint("source", "keyword", name="uq_scrape_progress_source_keyword"),
        Index("ix_scrape_progress_source", "source"),
        Index("ix_scrape_progress_ticker", "ticker_symbol"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ScrapeProgress(source={self.source!r}, keyword={self.keyword!r}, "
            f"last_page={self.last_page_scraped})"
        )
