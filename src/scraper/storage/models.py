"""
SQLAlchemy ORM models mirroring the normalized scraper schema.

The canonical DDL lives in
``docker/postgresql/init-scripts/003-create-scraper-schema.sql``; these models
are the application-side mapping. ``Base.metadata.create_all`` is *not* relied
upon for production (the SQL script is authoritative), but is handy for tests.

Article *content* is stored as JSON in ADLS — only metadata lives in PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
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
    __tablename__ = "stocks"
    __table_args__ = {"schema": "core"}

    stock_id: Mapped[uuid.UUID] = _uuid_pk()
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(16))
    sector: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IndexMembership(Base):
    __tablename__ = "index_memberships"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.stocks.stock_id", ondelete="CASCADE"), nullable=False
    )
    index_name: Mapped[str] = mapped_column(String(32), nullable=False)
    joined_at: Mapped[date] = mapped_column(Date, nullable=False)
    left_at: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StockMetric(Base):
    __tablename__ = "stock_metrics"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.stocks.stock_id", ondelete="CASCADE"), nullable=False
    )
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    snapshot_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_eod: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    session_note: Mapped[str | None] = mapped_column(String(32))

    reference_price: Mapped[float | None] = mapped_column(Numeric(18, 4))
    ceiling_price: Mapped[float | None] = mapped_column(Numeric(18, 4))
    floor_price: Mapped[float | None] = mapped_column(Numeric(18, 4))

    bid_price_3: Mapped[float | None] = mapped_column(Numeric(18, 4))
    bid_volume_3: Mapped[int | None] = mapped_column(BigInteger)
    bid_price_2: Mapped[float | None] = mapped_column(Numeric(18, 4))
    bid_volume_2: Mapped[int | None] = mapped_column(BigInteger)
    bid_price_1: Mapped[float | None] = mapped_column(Numeric(18, 4))
    bid_volume_1: Mapped[int | None] = mapped_column(BigInteger)

    matched_price: Mapped[float | None] = mapped_column(Numeric(18, 4))
    matched_volume: Mapped[int | None] = mapped_column(BigInteger)
    change: Mapped[float | None] = mapped_column(Numeric(18, 4))
    change_percent: Mapped[float | None] = mapped_column(Numeric(12, 6))

    ask_price_1: Mapped[float | None] = mapped_column(Numeric(18, 4))
    ask_volume_1: Mapped[int | None] = mapped_column(BigInteger)
    ask_price_2: Mapped[float | None] = mapped_column(Numeric(18, 4))
    ask_volume_2: Mapped[int | None] = mapped_column(BigInteger)
    ask_price_3: Mapped[float | None] = mapped_column(Numeric(18, 4))
    ask_volume_3: Mapped[int | None] = mapped_column(BigInteger)

    total_volume: Mapped[int | None] = mapped_column(BigInteger)
    total_value: Mapped[float | None] = mapped_column(Numeric(24, 4))
    high_price: Mapped[float | None] = mapped_column(Numeric(18, 4))
    low_price: Mapped[float | None] = mapped_column(Numeric(18, 4))
    average_price: Mapped[float | None] = mapped_column(Numeric(18, 4))

    foreign_buy_volume: Mapped[int | None] = mapped_column(BigInteger)
    foreign_sell_volume: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (
        UniqueConstraint("stock_id", "keyword", name="uq_scraping_keywords_stock_keyword"),
        {"schema": "scraping"},
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.stocks.stock_id", ondelete="CASCADE"), nullable=False
    )
    keyword: Mapped[str] = mapped_column(String(512), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = {"schema": "scraping"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    base_url: Mapped[str | None] = mapped_column(String(512))
    language: Mapped[str | None] = mapped_column(String(16), default="vi")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Proxy(Base):
    __tablename__ = "proxies"
    __table_args__ = {"schema": "scraping"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = {"schema": "scraping"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_name: Mapped[str | None] = mapped_column(String(256))
    job_type: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scraping.sources.id")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(16))
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    crawler_version: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ArticleMetadata(Base):
    __tablename__ = "article_metadata"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = _uuid_pk()

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scraping.sources.id"), nullable=False
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scraping.crawl_jobs.id"), nullable=False
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    json_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(16))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ArticleStock(Base):
    __tablename__ = "article_stock_mapping"
    __table_args__ = {"schema": "core"}

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.article_metadata.id", ondelete="CASCADE"),
        primary_key=True,
    )
    stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.stocks.stock_id", ondelete="CASCADE"),
        primary_key=True,
    )
    matched_keyword: Mapped[str | None] = mapped_column(String(512))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))


class CrawlLog(Base):
    __tablename__ = "crawl_logs"
    __table_args__ = {"schema": "scraping"}

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scraping.crawl_jobs.id", ondelete="CASCADE"), nullable=False
    )
    proxy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scraping.proxies.id")
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="GET")
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    is_success: Mapped[bool | None] = mapped_column(Boolean)
    error_category: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_response_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
