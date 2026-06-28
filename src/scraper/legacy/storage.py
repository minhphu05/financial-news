"""
Persistence layer for the scraper.

The split is intentional and reflects the project spec:

* **PostgreSQL** holds *metadata* (one row per article).
* **MongoDB**   holds the *content* (full body keyed by ``news_id``).

Additionally, PostgreSQL houses **scrape tracking** tables:

* ``scrape_runs``     - audit log for every pipeline execution.
* ``scrape_progress`` - cursor state for incremental crawling.

Both stores are reachable via a single :class:`StorageManager` that exposes
an idempotent :meth:`save_article` operation - safe to call repeatedly for
the same article (UPSERT semantics on both stores).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from sqlalchemy import create_engine, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.scraper.legacy.config import ScraperSettings
from src.scraper.legacy.models import Base, NewsArticle, ScrapeProgress, ScrapeRun
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Aggregate value object
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScrapedArticle:
    """
    Fully assembled article ready for persistence.

    Combines fields harvested from the listing page (summary, keyword,
    ticker context) with fields harvested from the detail page (title,
    author, content, publication date).
    """

    # Identity & metadata
    news_id: str
    url: str
    title: str
    summary: Optional[str]
    author: Optional[str]
    created_at: Optional[datetime]
    scraped_at: datetime
    # Provenance
    source: str
    ticker_symbol: Optional[str]
    company_name: Optional[str]
    keyword: Optional[str]
    # Content (MongoDB)
    content: Optional[str]


# ---------------------------------------------------------------------------
# Storage manager
# ---------------------------------------------------------------------------
class StorageManager:
    """
    Single entry point for writing scraped articles.

    Lazily initializes both the SQLAlchemy engine and the MongoDB client.
    Use as a context manager to guarantee connections are released:

    >>> with StorageManager(settings) as storage:
    ...     storage.save_article(article)
    """

    def __init__(self, settings: ScraperSettings) -> None:
        self._settings = settings
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker[Session]] = None
        self._mongo_client: Optional[MongoClient] = None
        self._mongo_collection: Optional[Collection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open connections to PostgreSQL and MongoDB and ensure schema."""
        self._engine = create_engine(
            self._settings.postgres_dsn,
            pool_pre_ping=True,
            future=True,
        )
        # Create tables if they do not yet exist. Idempotent.
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

        self._mongo_client = MongoClient(self._settings.mongo_uri)
        db = self._mongo_client[self._settings.mongo_db]
        self._mongo_collection = db[self._settings.mongo_collection]
        # Make sure the natural key is unique (``_id`` already is, but we also
        # index ``news_id`` explicitly in case the document is stored with a
        # different primary key in the future).
        self._mongo_collection.create_index("news_id", unique=True)

        logger.success(
            f"Connected to PostgreSQL ({self._settings.pg_host}:{self._settings.pg_port}) "
            f"and MongoDB ({self._settings.mongo_db}.{self._settings.mongo_collection})."
        )

    def close(self) -> None:
        """Release database resources."""
        if self._mongo_client is not None:
            self._mongo_client.close()
            self._mongo_client = None
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> "StorageManager":
        self.connect()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def article_exists(self, news_id: str) -> bool:
        """
        Return ``True`` if a metadata row for ``news_id`` already exists.

        Used by the page scraper to skip re-fetching articles that have
        previously been ingested.
        """
        assert self._session_factory is not None, "StorageManager not connected"
        with self._session_factory() as session:
            return (
                session.query(NewsArticle.news_id)
                .filter(NewsArticle.news_id == news_id)
                .first()
                is not None
            )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def save_article(self, article: ScrapedArticle) -> None:
        """
        Persist one article atomically across both stores.

        The MongoDB write happens first so a successful metadata row always
        implies the body is reachable. Both writes are UPSERTs and therefore
        safe to retry.
        """
        self._upsert_content(article)
        self._upsert_metadata(article)
        logger.debug(f"Persisted article {article.news_id}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _upsert_content(self, article: ScrapedArticle) -> None:
        """Insert/replace the article body document in MongoDB."""
        assert self._mongo_collection is not None, "StorageManager not connected"
        document = {
            "_id": article.news_id,
            "news_id": article.news_id,
            "link": article.url,
            "url": article.url,
            "context": article.content,
            "content": article.content,
            "title": article.title,
            "summary": article.summary,
            "post_date": article.created_at,
            "ticker_symbol": article.ticker_symbol,
            "ticket_symbol": article.ticker_symbol,
            "ticker_name": article.company_name,
            "ticket_name": article.company_name,
            "keyword": article.keyword,
            "source": article.source,
            "scraped_at": article.scraped_at,
        }
        self._mongo_collection.replace_one(
            {"_id": article.news_id}, document, upsert=True
        )

    def _upsert_metadata(self, article: ScrapedArticle) -> None:
        """Insert/update the metadata row in PostgreSQL."""
        assert self._engine is not None, "StorageManager not connected"
        assert self._session_factory is not None

        row = {
            "news_id": article.news_id,
            "url": article.url,
            "title": article.title,
            "summary": article.summary,
            "author": article.author,
            "created_at": article.created_at,
            "scraped_at": article.scraped_at,
            "source": article.source,
            "ticker_symbol": article.ticker_symbol,
            "company_name": article.company_name,
            "keyword": article.keyword,
            "content_ref": article.news_id,
        }

        stmt = pg_insert(NewsArticle).values(**row)
        # On conflict: refresh everything except the immutable primary key.
        update_cols = {col: stmt.excluded[col] for col in row if col != "news_id"}
        stmt = stmt.on_conflict_do_update(
            index_elements=[NewsArticle.news_id], set_=update_cols
        )

        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()

    # ------------------------------------------------------------------
    # Scrape Tracking: ScrapeRun
    # ------------------------------------------------------------------
    def cleanup_stale_runs(self) -> int:
        """
        Mark any orphaned 'running' records as 'aborted' with correct timing.

        Called at the start of every new pipeline execution to finalize
        records left behind by previous runs that crashed or were killed
        without calling ``finish_scrape_run``.

        Returns:
            Number of stale runs cleaned up.
        """
        assert self._session_factory is not None, "StorageManager not connected"
        now = datetime.now(timezone.utc)
        cleaned = 0
        with self._session_factory() as session:
            stale_runs = (
                session.query(ScrapeRun)
                .filter(ScrapeRun.status == "running")
                .all()
            )
            for run in stale_runs:
                run.finished_at = now
                run.duration_seconds = (now - run.started_at).total_seconds()
                run.status = "aborted"
                run.error_message = "No graceful shutdown detected; marked aborted on next startup."
                cleaned += 1
            if cleaned:
                session.commit()
                logger.warning(
                    f"Cleaned up {cleaned} stale 'running' scrape run(s) from previous execution."
                )
        return cleaned

    def create_scrape_run(
        self,
        source: str,
        triggered_by: str = "manual",
        tickers_filter: Optional[str] = None,
    ) -> int:
        """
        Create a new scrape_run record and return its run_id.

        Automatically cleans up any orphaned 'running' records left from
        previous executions that did not shut down gracefully.

        Args:
            source: Source site identifier (e.g. 'cafef').
            triggered_by: How the run was initiated ('manual', 'cron', 'prefect').
            tickers_filter: Comma-separated ticker list or None for all.

        Returns:
            The auto-generated ``run_id``.
        """
        assert self._session_factory is not None, "StorageManager not connected"
        self.cleanup_stale_runs()
        run = ScrapeRun(
            started_at=datetime.now(timezone.utc),
            source=source,
            triggered_by=triggered_by,
            tickers_filter=tickers_filter,
            status="running",
        )
        with self._session_factory() as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.run_id

    def finish_scrape_run(
        self,
        run_id: int,
        *,
        articles_found: int = 0,
        articles_new: int = 0,
        articles_skipped: int = 0,
        pages_crawled: int = 0,
        errors_count: int = 0,
        duration_seconds: Optional[float] = None,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        """
        Mark a scrape run as finished and record aggregate counters.

        Args:
            run_id: The run to update.
            articles_found: Total articles discovered on listing pages.
            articles_new: Articles actually persisted.
            articles_skipped: Articles skipped (already exist).
            pages_crawled: Total listing pages fetched.
            errors_count: Non-fatal errors encountered.
            duration_seconds: Wall-clock duration from monotonic timer. If
                None, computed from ``finished_at - started_at``.
            status: Final status ('completed', 'failed', 'aborted').
            error_message: Error description if status == 'failed'.
        """
        assert self._session_factory is not None, "StorageManager not connected"
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            run = session.get(ScrapeRun, run_id)
            if run is None:
                logger.warning(f"ScrapeRun {run_id} not found; cannot finish.")
                return
            run.finished_at = now
            if duration_seconds is not None:
                run.duration_seconds = round(duration_seconds, 3)
            elif run.started_at:
                run.duration_seconds = (now - run.started_at).total_seconds()
            run.articles_found = articles_found
            run.articles_new = articles_new
            run.articles_skipped = articles_skipped
            run.pages_crawled = pages_crawled
            run.errors_count = errors_count
            run.status = status
            run.error_message = error_message
            session.commit()

    # ------------------------------------------------------------------
    # Scrape Tracking: ScrapeProgress (Incremental Cursors)
    # ------------------------------------------------------------------
    def get_progress(self, source: str, keyword: str) -> Optional[ScrapeProgress]:
        """
        Retrieve the scrape cursor for a (source, keyword) pair.

        Returns:
            The :class:`ScrapeProgress` row, or ``None`` if this is the
            first time this keyword is being crawled.
        """
        assert self._session_factory is not None, "StorageManager not connected"
        with self._session_factory() as session:
            return (
                session.query(ScrapeProgress)
                .filter(
                    ScrapeProgress.source == source,
                    ScrapeProgress.keyword == keyword,
                )
                .first()
            )

    def update_progress(
        self,
        source: str,
        keyword: str,
        *,
        ticker_symbol: Optional[str] = None,
        last_page_scraped: int = 0,
        last_scraped_news_id: Optional[str] = None,
        articles_added: int = 0,
        is_exhausted: bool = False,
    ) -> None:
        """
        Upsert the scrape progress cursor for a (source, keyword) pair.

        Called after each keyword crawl completes to record where to resume.

        Args:
            source: Source site identifier.
            keyword: The search keyword.
            ticker_symbol: Associated ticker (for reference).
            last_page_scraped: Deepest page successfully scanned.
            last_scraped_news_id: Newest news_id seen this run.
            articles_added: New articles persisted this run (accumulated).
            is_exhausted: Whether the site says no more results exist.
        """
        assert self._session_factory is not None, "StorageManager not connected"
        now = datetime.now(timezone.utc)

        row = {
            "source": source,
            "keyword": keyword,
            "ticker_symbol": ticker_symbol,
            "last_page_scraped": last_page_scraped,
            "last_scraped_at": now,
            "last_scraped_news_id": last_scraped_news_id,
            "total_articles_scraped": articles_added,
            "is_exhausted": is_exhausted,
        }

        stmt = pg_insert(ScrapeProgress).values(**row)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_scrape_progress_source_keyword",
            set_={
                "ticker_symbol": stmt.excluded.ticker_symbol,
                "last_page_scraped": stmt.excluded.last_page_scraped,
                "last_scraped_at": stmt.excluded.last_scraped_at,
                "last_scraped_news_id": stmt.excluded.last_scraped_news_id,
                "total_articles_scraped": (
                    ScrapeProgress.total_articles_scraped + stmt.excluded.total_articles_scraped
                ),
                "is_exhausted": stmt.excluded.is_exhausted,
            },
        )

        with self._session_factory() as session:
            session.execute(stmt)
            session.commit()
