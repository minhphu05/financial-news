"""
PostgreSQL repository for scraper metadata (normalized schema).

Owns the SQLAlchemy engine/session and exposes intention-revealing methods for
every write the pipeline performs: registering a crawl job, upserting article
metadata, bridging articles to stocks, and recording crawl logs.

Article *content* is not stored here — only its ADLS ``json_path``.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.scraper.config import ScraperSettings
from src.scraper.storage.models import (
    ArticleMetadata,
    ArticleStock,
    CrawlJob,
    CrawlLog,
    IndexMembership,
    Keyword,
    Source,
    Stock,
    StockMetric,
)
from src.scraper.engine.types import ArticleRecord
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MetadataRepository:
    """Single entry point for all metadata writes/queries in PostgreSQL."""

    def __init__(self, settings: ScraperSettings) -> None:
        self._settings = settings
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker[Session]] = None

    # -- Lifecycle -------------------------------------------------------
    def connect(self) -> None:
        self._engine = create_engine(
            self._settings.postgres_dsn, pool_pre_ping=True, future=True
        )
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        logger.success(
            "Connected to PostgreSQL %s:%s/%s",
            self._settings.pg_host,
            self._settings.pg_port,
            self._settings.pg_database,
        )

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None

    def __enter__(self) -> "MetadataRepository":
        self.connect()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    @property
    def session_factory(self) -> sessionmaker[Session]:
        assert self._session_factory is not None, "MetadataRepository not connected"
        return self._session_factory

    # -- Stocks ----------------------------------------------------------
    def ensure_stock(
        self,
        *,
        ticker: str,
        company_name: str,
        exchange: Optional[str] = None,
    ) -> str:
        """Idempotently upsert a stock row; return its id."""
        normalized_ticker = ticker.upper().strip()
        stmt = (
            pg_insert(Stock)
            .values(
                ticker=normalized_ticker,
                company_name=company_name or normalized_ticker,
                exchange=exchange.upper() if exchange else None,
                is_active=True,
            )
            .on_conflict_do_update(
                index_elements=[Stock.ticker],
                set_={
                    "company_name": company_name or normalized_ticker,
                    "exchange": exchange.upper() if exchange else None,
                    "is_active": True,
                },
            )
            .returning(Stock.stock_id)
        )
        with self.session_factory() as session:
            stock_id = session.execute(stmt).scalar_one()
            session.commit()
        return str(stock_id)

    def ensure_index_membership(
        self,
        *,
        stock_id: str,
        index_name: str,
        joined_at,
    ) -> str:
        """Ensure an active stock/index membership exists; return its id."""
        stmt = (
            pg_insert(IndexMembership)
            .values(
                stock_id=uuid.UUID(stock_id),
                index_name=index_name.upper().strip(),
                joined_at=joined_at,
                left_at=None,
                is_active=True,
            )
            .on_conflict_do_nothing()
            .returning(IndexMembership.id)
        )
        with self.session_factory() as session:
            membership_id = session.execute(stmt).scalar_one_or_none()
            if membership_id is None:
                membership_id = session.execute(
                    select(IndexMembership.id).where(
                        IndexMembership.stock_id == uuid.UUID(stock_id),
                        IndexMembership.index_name == index_name.upper().strip(),
                        IndexMembership.left_at.is_(None),
                    )
                ).scalar_one_or_none()
            session.commit()
        return str(membership_id) if membership_id else ""

    def upsert_stock_metric(self, values: dict) -> str:
        """Insert or update one stock metric snapshot keyed by stock/timestamp."""
        payload = dict(values)
        payload["stock_id"] = uuid.UUID(str(payload["stock_id"]))
        payload.setdefault("id", uuid.uuid4())
        stmt = pg_insert(StockMetric).values(**payload)
        update_cols = {
            column.name: getattr(stmt.excluded, column.name)
            for column in StockMetric.__table__.columns
            if column.name not in {"id", "stock_id", "snapshot_timestamp", "created_at"}
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[StockMetric.stock_id, StockMetric.snapshot_timestamp],
            set_=update_cols,
        ).returning(StockMetric.id)
        with self.session_factory() as session:
            metric_id = session.execute(stmt).scalar_one()
            session.commit()
        return str(metric_id)

    def active_keyword_tickers(self) -> set[str]:
        """Return tickers that already have at least one active keyword."""
        stmt = (
            select(Stock.ticker)
            .join(Keyword, Keyword.stock_id == Stock.stock_id)
            .where(Stock.is_active.is_(True), Keyword.is_active.is_(True))
            .distinct()
        )
        with self.session_factory() as session:
            return {row[0].upper() for row in session.execute(stmt).all()}

    def active_index_tickers(self, index_names: Sequence[str] = ("VN30", "HNX30")) -> list[dict[str, str | None]]:
        """Return active stocks that belong to the requested index baskets."""
        normalized = [name.upper().strip() for name in index_names if name.strip()]
        stmt = (
            select(Stock.ticker, Stock.company_name, Stock.exchange, IndexMembership.index_name)
            .join(IndexMembership, IndexMembership.stock_id == Stock.stock_id)
            .where(
                Stock.is_active.is_(True),
                IndexMembership.is_active.is_(True),
                IndexMembership.left_at.is_(None),
                IndexMembership.index_name.in_(normalized),
            )
            .order_by(IndexMembership.index_name, Stock.ticker)
        )
        with self.session_factory() as session:
            rows = session.execute(stmt).all()
        return [
            {
                "ticker": ticker,
                "company_name": company_name,
                "exchange": exchange,
                "index_name": index_name,
            }
            for ticker, company_name, exchange, index_name in rows
        ]

    def ensure_stock_keywords(
        self,
        *,
        ticker: str,
        company_name: str | None,
        keywords: Sequence[str],
        exchange: str | None = None,
        index_name: str | None = None,
        joined_at: date | None = None,
    ) -> int:
        """Ensure a stock and its active scraping keywords exist; return rows touched."""
        stock_id = self.ensure_stock(
            ticker=ticker,
            company_name=company_name or ticker,
            exchange=exchange,
        )
        if index_name:
            self.ensure_index_membership(
                stock_id=stock_id,
                index_name=index_name,
                joined_at=joined_at or datetime.now(timezone.utc).date(),
            )

        touched = 0
        with self.session_factory() as session:
            for priority, keyword in enumerate(keywords, start=1):
                cleaned = str(keyword).strip()
                if not cleaned:
                    continue
                stmt = (
                    pg_insert(Keyword)
                    .values(
                        stock_id=uuid.UUID(stock_id),
                        keyword=cleaned,
                        priority=priority,
                        is_active=True,
                    )
                    .on_conflict_do_update(
                        index_elements=[Keyword.stock_id, Keyword.keyword],
                        set_={"priority": priority, "is_active": True},
                    )
                )
                session.execute(stmt)
                touched += 1
            session.commit()
        return touched

    # -- Sources ---------------------------------------------------------
    def ensure_source(
        self,
        name: str,
        *,
        base_url: Optional[str] = None,
        language: str = "vi",
    ) -> str:
        """Idempotently upsert a source row; return its id."""
        stmt = (
            pg_insert(Source)
            .values(name=name, base_url=base_url, language=language)
            .on_conflict_do_nothing(index_elements=[Source.name])
        )
        with self.session_factory() as session:
            session.execute(stmt)
            session.commit()
            source_id = session.execute(
                select(Source.id).where(Source.name == name)
            ).scalar_one()
        return str(source_id)

    # -- Crawl job -------------------------------------------------------
    def create_crawl_job(
        self,
        *,
        crawler_version: str,
        note: Optional[str] = None,
        job_name: str = "financial-news scrape",
        job_type: str = "NEWS",
        source_id: Optional[str] = None,
    ) -> str:
        job = CrawlJob(
            job_name=job_name,
            job_type=job_type,
            source_id=uuid.UUID(source_id) if source_id else None,
            started_at=datetime.now(timezone.utc),
            status="RUNNING",
            crawler_version=crawler_version,
            note=note,
        )
        with self.session_factory() as session:
            session.add(job)
            session.commit()
            session.refresh(job)
            return str(job.id)

    def finish_crawl_job(
        self,
        job_id: str,
        *,
        status: str,
        note: Optional[str] = None,
        total_requests: Optional[int] = None,
        success_requests: Optional[int] = None,
        failed_requests: Optional[int] = None,
        items_extracted: Optional[int] = None,
    ) -> None:
        with self.session_factory() as session:
            job = session.get(CrawlJob, uuid.UUID(job_id))
            if job is None:
                logger.warning("CrawlJob %s not found; cannot finish.", job_id)
                return
            job.finished_at = datetime.now(timezone.utc)
            job.status = status
            if note is not None:
                job.note = note
            if total_requests is not None:
                job.total_requests = total_requests
            if success_requests is not None:
                job.success_requests = success_requests
            if failed_requests is not None:
                job.failed_requests = failed_requests
            if items_extracted is not None:
                job.items_extracted = items_extracted
            session.commit()

    # -- Articles --------------------------------------------------------
    def article_exists(self, url_hash: str) -> bool:
        with self.session_factory() as session:
            return (
                session.execute(
                    select(ArticleMetadata.id).where(
                        ArticleMetadata.url_hash == url_hash
                    )
                ).first()
                is not None
            )

    def upsert_article(self, record: ArticleRecord) -> str:
        """Insert or update one article metadata row keyed by ``url_hash``.

        Returns the article id (existing on conflict).
        """
        now = datetime.now(timezone.utc)
        values = {
            "id": uuid.uuid4(),
            "source_id": uuid.UUID(record.source_id),
            "crawl_job_id": uuid.UUID(record.crawl_job_id),
            "url": record.url,
            "url_hash": record.url_hash,
            "title": record.title,
            "summary": record.summary,
            "published_at": record.published_at,
            "scraped_at": now,
            "json_path": record.json_path or "",
            "status": record.status,
            "updated_at": now,
        }
        stmt = pg_insert(ArticleMetadata).values(**values)
        update_cols = {
            "crawl_job_id": stmt.excluded.crawl_job_id,
            "title": stmt.excluded.title,
            "summary": stmt.excluded.summary,
            "published_at": stmt.excluded.published_at,
            "json_path": stmt.excluded.json_path,
            "status": stmt.excluded.status,
            "updated_at": stmt.excluded.updated_at,
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[ArticleMetadata.url_hash], set_=update_cols
        ).returning(ArticleMetadata.id)

        with self.session_factory() as session:
            article_id = session.execute(stmt).scalar_one()
            session.commit()
        return str(article_id)

    def link_article_stock(
        self,
        *,
        article_id: str,
        stock_id: str,
        matched_keyword: Optional[str],
        confidence: Optional[float] = 1.0,
    ) -> None:
        stmt = (
            pg_insert(ArticleStock)
            .values(
                article_id=uuid.UUID(article_id),
                stock_id=uuid.UUID(stock_id),
                matched_keyword=matched_keyword,
                confidence=confidence,
            )
            .on_conflict_do_update(
                index_elements=[ArticleStock.article_id, ArticleStock.stock_id],
                set_={"matched_keyword": matched_keyword, "confidence": confidence},
            )
        )
        with self.session_factory() as session:
            session.execute(stmt)
            session.commit()

    # -- Crawl log -------------------------------------------------------
    def write_crawl_log(
        self,
        *,
        job_id: str,
        target_url: str,
        response_time_ms: int,
        is_success: bool,
        method: str = "GET",
        status_code: Optional[int] = None,
        error_category: Optional[str] = None,
        error_message: Optional[str] = None,
        raw_response_path: Optional[str] = None,
    ) -> None:
        row = CrawlLog(
            job_id=uuid.UUID(job_id),
            target_url=target_url,
            method=method,
            status_code=status_code,
            response_time_ms=response_time_ms,
            is_success=is_success,
            error_category=error_category,
            error_message=error_message,
            raw_response_path=raw_response_path,
        )
        with self.session_factory() as session:
            session.add(row)
            session.commit()
