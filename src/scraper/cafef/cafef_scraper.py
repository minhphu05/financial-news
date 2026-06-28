"""
CafeF (https://cafef.vn) scraper.

Ports the original CafeF DOM logic into the reusable :class:`BaseParser`
interface. Pure parsing only; no network or database access.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.scraper.engine.base_parser import BaseParser
from src.scraper.engine.types import ArticleDetail, ContentBlock, ListingEntry
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CafefParser(BaseParser):
    """Parser for CafeF search results and article pages."""

    name = "cafef"
    base_url = os.getenv("CAFEF_BASE_URL", "https://cafef.vn")
    default_language = "vi"

    _HTML_PARSER = "html.parser"

    _SEARCH_URL_TEMPLATE = os.getenv(
        "CAFEF_SEARCH_URL_TEMPLATE",
        "https://cafef.vn/tim-kiem/trang-{page}.chn?keywords={keyword}",
    )

    # Article URLs end with ``-<digits>.chn``; the digits are the native id.
    _NEWS_ID_PATTERN = re.compile(r"-(\d+)\.chn(?:[?#].*)?$")

    # Listing selectors.
    _EMPTY_RESULT_SELECTOR = "div.search-content-wrap > span"
    _ITEM_SELECTOR = (
        "div.list-main > div.search-content-wrap > "
        "div.timeline.list-bytags > div.item"
    )
    _LISTING_IMAGE_SELECTOR = "div.item-content a.avatar img, div.item-content img"

    # Detail selectors.
    _TITLE_SELECTOR = "h1.title"
    _MAGAZINE_CONTAINER_SELECTOR = "div.detail__magazine"
    _STANDARD_DATE_SELECTOR = "p.dateandcat > span.pdate"
    _MAGAZINE_DATE_SELECTOR = "a.link-source-name > span.time-source-detail"
    _STANDARD_BODY_SELECTOR = (
        "div.contentdetail > div.detail-cmain.ss > div.detail-content.afcbc-body"
    )
    _STANDARD_BODY_FALLBACK = (
        "table[style='border-collapse: collapse;'] > tbody > tr > td > span"
    )
    _CATEGORY_SELECTOR = "p.dateandcat > a.category-page__name, p.dateandcat a"
    _AUTHOR_SELECTORS = (
        "p.author",
        "div.author",
        "span.author",
        "p.pauthor",
        "div.detail-author",
        "p.detail-author",
    )

    # Body child elements to ignore (related-news widgets, responsive wrappers).
    _NOISE_CLASS_TOKENS = frozenset(
        {"tindnd", "h-show-pc", "h-show-mobile", "VCObjectBoxRelatedNewsItem"}
    )

    _DATETIME_PATTERNS = (
        "%d-%m-%Y - %H:%M",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y - %H:%M",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
    )

    # -- URL building ----------------------------------------------------
    def build_search_url(self, keyword: str, page: int) -> str:
        return self._SEARCH_URL_TEMPLATE.format(page=page, keyword=keyword)

    # -- Listing page ----------------------------------------------------
    def is_listing_exhausted(self, html: str) -> bool:
        soup = BeautifulSoup(html, self._HTML_PARSER)
        return soup.select_one(self._EMPTY_RESULT_SELECTOR) is not None

    def parse_listing(self, html: str) -> List[ListingEntry]:
        soup = BeautifulSoup(html, self._HTML_PARSER)
        entries: List[ListingEntry] = []

        for item in soup.select(self._ITEM_SELECTOR):
            anchor = item.select_one("h3.titlehidden > a")
            if anchor is None:
                continue
            href = anchor.get("href")
            if not href:
                continue

            absolute_url = urljoin(self.base_url, href)
            title_attr = anchor.get("title")
            title_text = title_attr or anchor.get_text(strip=True)

            summary_node = item.select_one("div.item-content > p.sapo")
            summary = summary_node.get_text(strip=True) if summary_node else None

            entries.append(
                ListingEntry(
                    url=absolute_url,
                    title=title_text or None,
                    summary=summary,
                    external_id=self._extract_news_id(absolute_url),
                    image_url=self._extract_listing_image(item),
                )
            )

        return entries

    # -- Detail page -----------------------------------------------------
    def parse_detail(self, html: str) -> ArticleDetail:
        soup = BeautifulSoup(html, self._HTML_PARSER)

        title_node = soup.select_one(self._TITLE_SELECTOR)
        title = title_node.get_text(strip=True) if title_node else None

        magazine = soup.select_one(self._MAGAZINE_CONTAINER_SELECTOR)
        if magazine is not None:
            blocks = self._extract_blocks(magazine)
            date_node = soup.select_one(self._MAGAZINE_DATE_SELECTOR)
        else:
            body = soup.select_one(self._STANDARD_BODY_SELECTOR)
            blocks = self._extract_blocks(body) if body is not None else ()
            if not blocks:
                blocks = self._fallback_blocks(soup)
            date_node = soup.select_one(self._STANDARD_DATE_SELECTOR)

        raw_date = date_node.get_text(strip=True) if date_node else None

        content = (
            "\n".join(b.text for b in blocks if b.type == "text" and b.text) or None
        )

        category_node = soup.select_one(self._CATEGORY_SELECTOR)
        category = category_node.get_text(strip=True) if category_node else None

        return ArticleDetail(
            title=title,
            content=content,
            summary=None,
            author=self._extract_author(soup),
            published_at=self._parse_datetime(raw_date),
            tag=None,
            type=category,
            language=self.default_language,
            blocks=blocks,
        )

    # -- Internals -------------------------------------------------------
    @classmethod
    def _extract_news_id(cls, url: str) -> Optional[str]:
        if not url:
            return None
        match = cls._NEWS_ID_PATTERN.search(url)
        return match.group(1) if match else None

    def _extract_listing_image(self, item: Tag) -> Optional[str]:
        node = item.select_one(self._LISTING_IMAGE_SELECTOR)
        return self._image_src(node) if node is not None else None

    @staticmethod
    def _image_src(img: Optional[Tag]) -> Optional[str]:
        """Return the best available image URL, honoring lazy-load attributes."""
        if img is None:
            return None
        for attr in ("data-original", "data-src", "src"):
            value = img.get(attr)
            if value and not value.startswith("data:"):
                return value.strip()
        return None

    def _extract_blocks(self, body: Tag) -> tuple[ContentBlock, ...]:
        """Walk the body in document order, emitting text + image blocks."""
        blocks: List[ContentBlock] = []
        for child in body.find_all(recursive=False):
            if not isinstance(child, Tag) or self._is_noise(child):
                continue

            if child.name == "figure" or child.select_one("img") is not None:
                block = self._figure_block(child)
                if block is not None:
                    blocks.append(block)
                continue

            text = child.get_text(" ", strip=True)
            if text:
                blocks.append(ContentBlock(type="text", text=text))
        return tuple(blocks)

    def _figure_block(self, node: Tag) -> Optional[ContentBlock]:
        img = node.select_one("img")
        src = self._image_src(img)
        if not src:
            return None
        caption_node = node.select_one("figcaption")
        caption = caption_node.get_text(" ", strip=True) if caption_node else None
        return ContentBlock(type="image", image_url=src, caption=caption or None)

    def _fallback_blocks(self, soup: BeautifulSoup) -> tuple[ContentBlock, ...]:
        """Legacy table-based articles: text-only paragraphs."""
        nodes = soup.select(self._STANDARD_BODY_FALLBACK)
        blocks = [
            ContentBlock(type="text", text=node.get_text(" ", strip=True))
            for node in nodes
            if node.get_text(strip=True)
        ]
        return tuple(blocks)

    @classmethod
    def _is_noise(cls, node: Tag) -> bool:
        classes = node.get("class") or []
        return any(token in cls._NOISE_CLASS_TOKENS for token in classes)

    @classmethod
    def _parse_datetime(cls, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        cleaned = re.sub(r"\s+", " ", raw).strip()
        for pattern in cls._DATETIME_PATTERNS:
            try:
                return datetime.strptime(cleaned, pattern)
            except ValueError:
                continue
        match = re.search(
            r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})[^\d]+(\d{1,2}):(\d{2})(?::(\d{2}))?",
            cleaned,
        )
        if match:
            day, month, year, hour, minute, second = match.groups(default="0")
            try:
                return datetime(
                    int(year), int(month), int(day), int(hour), int(minute), int(second)
                )
            except ValueError:
                return None
        logger.debug("Could not parse publication datetime: %r", raw)
        return None

    @classmethod
    def _extract_author(cls, soup: BeautifulSoup) -> Optional[str]:
        for selector in cls._AUTHOR_SELECTORS:
            node = soup.select_one(selector)
            if node and node.get_text(strip=True):
                return node.get_text(strip=True)
        meta = soup.find("meta", attrs={"name": "author"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None