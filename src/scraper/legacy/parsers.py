"""
HTML parsing helpers for the CafeF source.

Each function is intentionally small, pure, and unit-testable: it accepts
an HTML string (or already-parsed :class:`BeautifulSoup` object) and returns
plain Python data structures - never touching the network or the database.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ListingEntry:
    """One article reference discovered on a search-results page."""

    news_id: str
    url: str
    title: Optional[str]
    summary: Optional[str]


@dataclass(frozen=True)
class ArticleDetail:
    """Fields harvested by visiting an individual article URL."""

    title: Optional[str]
    content: Optional[str]
    author: Optional[str]
    created_at: Optional[datetime]


# ---------------------------------------------------------------------------
# news_id extraction
# ---------------------------------------------------------------------------
# CafeF article URLs end with ``-<digits>.chn``; the trailing digits are the
# news id we persist as the cross-store primary key.
_NEWS_ID_PATTERN = re.compile(r"-(\d+)\.chn(?:[?#].*)?$")


def extract_news_id(url_or_href: str) -> Optional[str]:
    """
    Extract the trailing numeric news id from a CafeF article URL.

    Examples
    --------
    >>> extract_news_id("/chu-tich-fpt-...-188260528163812616.chn")
    '188260528163812616'
    >>> extract_news_id("https://cafef.vn/foo-1234567890.chn?x=y")
    '1234567890'
    >>> extract_news_id("https://cafef.vn/no-id-here/") is None
    True
    """
    if not url_or_href:
        return None
    match = _NEWS_ID_PATTERN.search(url_or_href)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Listing page
# ---------------------------------------------------------------------------
# When the search returns zero results CafeF renders a notice inside this span.
_EMPTY_RESULT_SELECTOR = "div.search-content-wrap > span"

# Each result row.
_ITEM_SELECTOR = (
    "div.list-main > div.search-content-wrap > "
    "div.timeline.list-bytags > div.item"
)


def is_listing_exhausted(html: str) -> bool:
    """
    Return ``True`` if the search-results page has no items left.

    CafeF surfaces a notice in a ``<span>`` once you scroll past the last
    page. We treat that as the natural stop condition.
    """
    soup = BeautifulSoup(html, "html.parser")
    return soup.select_one(_EMPTY_RESULT_SELECTOR) is not None


def parse_listing_page(html: str, base_url: str) -> List[ListingEntry]:
    """
    Extract every article reference from one search-results page.

    Args:
        html: Raw HTML of the listing page.
        base_url: Site base URL used to resolve relative ``href`` values.

    Returns:
        A list of :class:`ListingEntry`. Items lacking either a URL or a
        recoverable ``news_id`` are dropped (with a warning log).
    """
    soup = BeautifulSoup(html, "html.parser")
    entries: List[ListingEntry] = []

    for item in soup.select(_ITEM_SELECTOR):
        anchor = item.select_one("h3.titlehidden > a")
        if anchor is None:
            continue

        href = anchor.get("href")
        if not href:
            continue

        absolute_url = urljoin(base_url, href)
        news_id = extract_news_id(absolute_url)
        if news_id is None:
            logger.warning(f"Could not extract news_id from URL: {absolute_url}")
            continue

        title_attr = anchor.get("title")
        title_text = anchor.get_text(strip=True) if not title_attr else title_attr

        summary_node = item.select_one("div.item-content > p.sapo")
        summary = summary_node.get_text(strip=True) if summary_node else None

        entries.append(
            ListingEntry(
                news_id=news_id,
                url=absolute_url,
                title=title_text or None,
                summary=summary,
            )
        )

    return entries


# ---------------------------------------------------------------------------
# Detail page
# ---------------------------------------------------------------------------
# Common selectors observed on CafeF article pages.
_TITLE_SELECTOR = "h1.title"
_MAGAZINE_CONTAINER_SELECTOR = "div.detail__magazine"
_STANDARD_DATE_SELECTOR = "p.dateandcat > span.pdate"
_MAGAZINE_DATE_SELECTOR = "a.link-source-name > span.time-source-detail"
_STANDARD_BODY_PARAGRAPHS = (
    "div.contentdetail > div.detail-cmain.ss > "
    "div.detail-content.afcbc-body p"
)
_STANDARD_BODY_FALLBACK = (
    "table[style='border-collapse: collapse;'] > tbody > tr > td > span"
)
_AUTHOR_SELECTORS = (
    "p.author",
    "div.author",
    "span.author",
    "p.pauthor",
    "div.detail-author",
    "p.detail-author",
)


# Accepts: "28-05-2026 - 14:30", "28/05/2026 14:30", "28-05-2026 14:30:00", etc.
_DATETIME_PATTERNS = (
    "%d-%m-%Y - %H:%M",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y - %H:%M",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
)


def _parse_vietnamese_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Best-effort parser for the publication timestamp string."""
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw).strip()
    for pattern in _DATETIME_PATTERNS:
        try:
            return datetime.strptime(cleaned, pattern)
        except ValueError:
            continue
    # Last resort: pull out a date + time substring via regex.
    match = re.search(
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})[^\d]+(\d{1,2}):(\d{2})(?::(\d{2}))?",
        cleaned,
    )
    if match:
        day, month, year, hour, minute, second = match.groups(default="0")
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
        except ValueError:
            return None
    logger.debug(f"Could not parse publication datetime: {raw!r}")
    return None


def _extract_author(soup: BeautifulSoup) -> Optional[str]:
    """Try several known selectors for the article byline."""
    for selector in _AUTHOR_SELECTORS:
        node = soup.select_one(selector)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    # Fallback: meta[name=author]
    meta = soup.find("meta", attrs={"name": "author"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    return None


def parse_detail_page(html: str) -> ArticleDetail:
    """
    Extract fields from an individual article page.

    Handles both the regular article layout and the ``detail__magazine``
    long-form layout used for feature pieces.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_node = soup.select_one(_TITLE_SELECTOR)
    title = title_node.get_text(strip=True) if title_node else None

    # Magazine vs. standard
    magazine_container = soup.select_one(_MAGAZINE_CONTAINER_SELECTOR)
    if magazine_container is not None:
        paragraphs = magazine_container.select("p")
        content = "\n".join(p.get_text(strip=True) for p in paragraphs) or None
        date_node = soup.select_one(_MAGAZINE_DATE_SELECTOR)
        raw_date = date_node.get_text(strip=True) if date_node else None
    else:
        paragraphs = soup.select(_STANDARD_BODY_PARAGRAPHS)
        if not paragraphs:
            paragraphs = soup.select(_STANDARD_BODY_FALLBACK)
        content = (
            "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            or None
        )
        date_node = soup.select_one(_STANDARD_DATE_SELECTOR)
        raw_date = date_node.get_text(strip=True) if date_node else None

    return ArticleDetail(
        title=title,
        content=content,
        author=_extract_author(soup),
        created_at=_parse_vietnamese_datetime(raw_date),
    )
