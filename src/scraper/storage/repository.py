"""
PostgreSQL repository for scraper metadata (normalized schema).

Owns the SQLAlchemy engine/session and exposes intention-revealing methods for
every write the pipeline performs: registering a crawl job, upserting article
metadata, bridging articles to stocks, and recording per-keyword crawl logs.

Article *content* is not stored here — only its ADLS ``json_path``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.scraper.config import ScraperSettings
from src.scraper.storage.models import (
    ArticleMetadata,
    ArticleStock,
    CrawlJob,
    CrawlLog,
    Source,
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

    # -- Sources ---------------------------------------------------------
    def ensure_source(
        self,
        name: str,
        *,
        base_url: Optional[str] = None,
        country: str = "VN",
        language: str = "vi",
    ) -> str:
        """Idempotently upsert a source row; return its id."""
        stmt = (
            pg_insert(Source)
            .values(name=name, base_url=base_url, country=country, language=language)
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
    def create_crawl_job(self, *, crawler_version: str, note: Optional[str] = None) -> str:
        job = CrawlJob(
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

    def finish_crawl_job(self, job_id: str, *, status: str, note: Optional[str] = None) -> None:
        with self.session_factory() as session:
            job = session.get(CrawlJob, uuid.UUID(job_id))
            if job is None:
                logger.warning("CrawlJob %s not found; cannot finish.", job_id)
                return
            job.finished_at = datetime.now(timezone.utc)
            job.status = status
            if note is not None:
                job.note = note
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
            "tag": record.tag,
            "type": record.type_,
            "author": record.author,
            "language": record.language,
            "published_at": record.published_at,
            "scraped_at": now,
            "json_path": record.json_path,
            "has_content": record.has_content,
            "content_checksum": record.content_checksum,
            "status": record.status,
            "updated_at": now,
        }
        stmt = pg_insert(ArticleMetadata).values(**values)
        update_cols = {
            "crawl_job_id": stmt.excluded.crawl_job_id,
            "title": stmt.excluded.title,
            "summary": stmt.excluded.summary,
            "tag": stmt.excluded.tag,
            "type": stmt.excluded.type,
            "author": stmt.excluded.author,
            "language": stmt.excluded.language,
            "published_at": stmt.excluded.published_at,
            "json_path": stmt.excluded.json_path,
            "has_content": stmt.excluded.has_content,
            "content_checksum": stmt.excluded.content_checksum,
            "content_version": ArticleMetadata.content_version + 1,
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
        source_id: str,
        keyword_id: Optional[str],
        status: str,
        duration_ms: int,
        article_found: int,
        error_message: Optional[str] = None,
    ) -> None:
        row = CrawlLog(
            job_id=uuid.UUID(job_id),
            source_id=uuid.UUID(source_id),
            keyword_id=uuid.UUID(keyword_id) if keyword_id else None,
            status=status,
            duration_ms=duration_ms,
            article_found=article_found,
            error_message=error_message,
        )
        with self.session_factory() as session:
            session.add(row)
            session.commit()
