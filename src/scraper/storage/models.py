"""
SQLAlchemy ORM models mirroring the normalized scraper schema.

The canonical DDL lives in
``docker/postgresql/init-scripts/003-create-scraper-schema.sql``; these models
are the application-side mapping. ``Base.metadata.create_all`` is *not* relied
upon for production (the SQL script is authoritative), but is handy for tests.

Article *content* is stored as JSON in ADLS — only metadata lives here.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by all scraper ORM models."""


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Stock(Base):
    __tablename__ = "stock"

    stock_id: Mapped[uuid.UUID] = _uuid_pk()
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(16))
    sector: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Keyword(Base):
    __tablename__ = "keyword"
    __table_args__ = (UniqueConstraint("stock_id", "keyword", name="uq_keyword_stock"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock.stock_id", ondelete="CASCADE"), nullable=False
    )
    keyword: Mapped[str] = mapped_column(String(512), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Source(Base):
    __tablename__ = "source"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    base_url: Mapped[str | None] = mapped_column(String(512))
    country: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CrawlJob(Base):
    __tablename__ = "crawl_job"

    id: Mapped[uuid.UUID] = _uuid_pk()
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RUNNING")
    crawler_version: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)


class ArticleMetadata(Base):
    __tablename__ = "article_metadata"

    id: Mapped[uuid.UUID] = _uuid_pk()

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source.id"), nullable=False
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_job.id"), nullable=False
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    tag: Mapped[str | None] = mapped_column(String(128))
    type: Mapped[str | None] = mapped_column(String(128))

    author: Mapped[str | None] = mapped_column(String(256))
    language: Mapped[str | None] = mapped_column(String(16))

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    json_path: Mapped[str | None] = mapped_column(Text)
    has_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    content_checksum: Mapped[str | None] = mapped_column(String(64))
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="METADATA_ONLY")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ArticleStock(Base):
    __tablename__ = "article_stock"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("article_metadata.id", ondelete="CASCADE"),
        primary_key=True,
    )
    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock.stock_id", ondelete="CASCADE"),
        primary_key=True,
    )
    matched_keyword: Mapped[str | None] = mapped_column(String(512))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))


class CrawlLog(Base):
    __tablename__ = "crawl_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_job.id", ondelete="CASCADE")
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source.id")
    )
    keyword_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("keyword.id")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    article_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
