"""
Plain value objects shared between parsers, the crawler, and storage.

These dataclasses are deliberately free of any framework or I/O concern so
parsers stay pure and unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ListingEntry:
    """One article reference discovered on a search-results page."""

    url: str
    title: Optional[str] = None
    summary: Optional[str] = None
    external_id: Optional[str] = None
    """Source-native id (e.g. CafeF news_id). Drives in-run dedup."""
    image_url: Optional[str] = None
    """Cover/thumbnail image shown on the listing card."""


@dataclass(frozen=True)
class ContentBlock:
    """One ordered piece of article body: a text paragraph or an image."""

    type: str  # "text" | "image"
    text: Optional[str] = None
    image_url: Optional[str] = None
    caption: Optional[str] = None


@dataclass(frozen=True)
class ArticleDetail:
    """Fields harvested by visiting an individual article URL."""

    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    tag: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    blocks: tuple["ContentBlock", ...] = ()
    """Ordered text + image blocks preserving the article's reading order."""



@dataclass(frozen=True)
class KeywordRecord:
    """A (stock, keyword) pair to crawl, resolved from the input provider."""

    stock_id: str
    ticker: str
    company_name: str
    keyword: str
    keyword_id: Optional[str] = None
    priority: int = 1


@dataclass(frozen=True)
class ArticleRecord:
    """Metadata payload handed to the repository for one article upsert."""

    source_id: str
    crawl_job_id: str
    url: str
    url_hash: str
    title: str
    summary: Optional[str]
    tag: Optional[str]
    type_: Optional[str]
    author: Optional[str]
    language: Optional[str]
    published_at: Optional[datetime]
    json_path: Optional[str]
    content_checksum: Optional[str]
    has_content: bool
    status: str



@dataclass
class KeywordResult:
    """Outcome of crawling a single keyword on a single source."""

    found: int = 0
    persisted: int = 0
    skipped: int = 0
    pages: int = 0
    early_stopped: bool = False
    is_exhausted: bool = False
    error: Optional[str] = None
    persisted_article_ids: list[str] = field(default_factory=list)
