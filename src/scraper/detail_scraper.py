"""
Detail-page scraper.

Given an article URL, fetch the HTML and return a structured
:class:`~src.scraper.parsers.ArticleDetail` value.
"""
from __future__ import annotations

from typing import Optional

from src.scraper.http_client import HttpClient
from src.scraper.parsers import ArticleDetail, parse_detail_page
from src.utils.logger import get_logger

logger = get_logger(__name__)


def scrape_article_detail(url: str, client: HttpClient) -> Optional[ArticleDetail]:
    """
    Fetch and parse a single article detail page.

    Args:
        url: Absolute article URL.
        client: Shared :class:`HttpClient`.

    Returns:
        Parsed :class:`ArticleDetail`, or ``None`` if the page could not be
        retrieved after all retries.
    """
    response = client.get(url)
    if response is None:
        logger.error(f"Detail fetch failed: {url}")
        return None
    try:
        return parse_detail_page(response.text)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(f"Failed to parse detail page {url}: {exc}")
        return None
