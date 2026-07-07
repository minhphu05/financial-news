"""
Bao Moi (https://baomoi.com) scraper.

Search results are paginated at ``/tim-kiem/{keyword}/trangN.epi`` and stop at
Bao Moi's explicit no-result message or the first page without main result cards.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.scraper.engine.base_parser import BaseParser
from src.scraper.engine.types import ArticleDetail, ContentBlock, ListingEntry
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BaomoiParser(BaseParser):
    """Parser and Playwright fetcher for Bao Moi search results."""

    name = "baomoi"
    base_url = os.getenv("BAOMOI_BASE_URL", "https://baomoi.com")
    default_language = "vi"

    _HTML_PARSER = "html.parser"
    _NEWS_ID_PATTERN = re.compile(r"-c(\d+)\.epi(?:[?#].*)?$")
    _NO_RESULT_TEXT = "Không tìm thấy kết quả phù hợp!"
    _ITEM_SELECTOR = "div.bm-card"
    _TITLE_SELECTOR = "h1, meta[property='og:title']"
    _SUMMARY_SELECTOR = "h3.sapo, .sapo, meta[name='description'], meta[property='og:description']"
    _BODY_SELECTOR = "div.content-body"
    _CATEGORY_SELECTOR = "meta[property='article:section'], nav a, .breadcrumb a"
    _AUTHOR_SELECTORS = "meta[name='author'], .article-source"
    _DATE_SELECTORS = (
        "meta[property='article:published_time']",
        "time[datetime]",
        "time",
    )
    _NOISE_CLASS_TOKENS = frozenset({"ads", "banner", "related", "recommend"})
    _DATETIME_PATTERNS = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
    )

    def build_search_url(self, keyword: str, page: int) -> str:
        slug = self._keyword_slug(keyword)
        if page <= 1:
            return f"{self.base_url}/tim-kiem/{slug}.epi"
        return f"{self.base_url}/tim-kiem/{slug}/trang{page}.epi"

    def fetch_listing_entries(self, keyword: str, settings) -> List[ListingEntry]:
        """Fetch paginated Bao Moi search pages until no-result/no-items."""
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Playwright is required for Bao Moi search pages.") from exc

        timeout_ms = max(settings.request_timeout, 10) * 1000
        max_items = int(os.getenv("BAOMOI_MAX_ITEMS", "0"))
        entries: List[ListingEntry] = []
        launch_options = {"headless": True}
        proxy_server = self._proxy_server_from_env()
        if proxy_server:
            launch_options["proxy"] = {"server": proxy_server}

        logger.info("Rendering Bao Moi search for keyword '%s'.", keyword)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch_options)
            try:
                page = browser.new_page(
                    user_agent=settings.user_agent,
                    viewport={"width": 1366, "height": 1800},
                    ignore_https_errors=True,
                )
                for page_number in range(settings.start_page, settings.max_pages + 1):
                    url = self.build_search_url(keyword, page_number)
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    try:
                        page.wait_for_selector(self._ITEM_SELECTOR, timeout=timeout_ms)
                    except PlaywrightTimeoutError:
                        logger.warning("Bao Moi listing did not expose expected nodes: %s", url)
                    page.wait_for_timeout(int(os.getenv("BAOMOI_PAGE_PAUSE_MS", "1000")))

                    html = page.content()
                    if self.is_listing_exhausted(html):
                        logger.info("Bao Moi keyword '%s' exhausted at page %s.", keyword, page_number)
                        break
                    page_entries = self.parse_listing(html)
                    if not page_entries:
                        logger.info("No Bao Moi entries for '%s' at page %s; stopping.", keyword, page_number)
                        break
                    entries.extend(page_entries)
                    entries = self._unique_entries(entries)
                    if max_items > 0 and len(entries) >= max_items:
                        entries = entries[:max_items]
                        break
            finally:
                browser.close()

        logger.info("Bao Moi keyword '%s': parsed %s listing result(s).", keyword, len(entries))
        return entries

    def fetch_detail_html(self, url: str, settings) -> Optional[str]:
        """Fetch one Bao Moi article detail page through Playwright."""
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Playwright is required for Bao Moi detail pages.") from exc

        timeout_ms = max(settings.request_timeout, 10) * 1000
        launch_options = {"headless": True}
        proxy_server = self._proxy_server_from_env()
        if proxy_server:
            launch_options["proxy"] = {"server": proxy_server}

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch_options)
            try:
                page = browser.new_page(
                    user_agent=settings.user_agent,
                    viewport={"width": 1366, "height": 1800},
                    ignore_https_errors=True,
                )
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_selector("h1, div.content-body", timeout=timeout_ms)
                except PlaywrightTimeoutError:
                    logger.warning("Bao Moi detail did not expose expected nodes: %s", url)
                return page.content()
            finally:
                browser.close()

    def fetch_binary(
        self,
        url: str,
        settings,
        referer: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """Fetch image bytes through Playwright Chromium to honor browser proxy auth."""
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Playwright is required for Bao Moi image downloads.") from exc

        timeout_ms = max(settings.request_timeout, 10) * 1000
        launch_options = {"headless": True}
        proxy_server = self._proxy_server_from_env()
        if proxy_server:
            launch_options["proxy"] = {"server": proxy_server}

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch_options)
            try:
                headers = {"Referer": referer} if referer else None
                page = browser.new_page(
                    user_agent=settings.user_agent,
                    viewport={"width": 1366, "height": 900},
                    ignore_https_errors=True,
                    extra_http_headers=headers,
                )
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if response is None or response.status >= 400:
                    return None, None
                content_type = response.headers.get("content-type")
                if content_type and not content_type.lower().startswith("image/"):
                    return None, None
                return response.body(), content_type
            except PlaywrightTimeoutError:
                logger.warning("Bao Moi image timed out: %s", url)
                return None, None
            finally:
                browser.close()

    def is_listing_exhausted(self, html: str) -> bool:
        return self._NO_RESULT_TEXT in BeautifulSoup(html, self._HTML_PARSER).get_text(" ", strip=True)

    def parse_listing(self, html: str) -> List[ListingEntry]:
        soup = BeautifulSoup(html, self._HTML_PARSER)
        entries: List[ListingEntry] = []
        for card in soup.select(self._ITEM_SELECTOR):
            if not self._is_main_result_card(card):
                continue
            anchor = card.select_one(".bm-card-header a[href$='.epi']") or card.select_one("a[title][href$='.epi']")
            if anchor is None:
                continue
            href = anchor.get("href") or ""
            if not href or self._is_publication_link(href):
                continue
            url = urljoin(self.base_url, href)
            summary_node = card.select_one(".bm-card-sapo, .bm-card-description, p")
            entries.append(
                ListingEntry(
                    url=url,
                    title=anchor.get("title") or anchor.get_text(" ", strip=True) or None,
                    summary=summary_node.get_text(" ", strip=True) if summary_node else None,
                    external_id=self._extract_news_id(url),
                    image_url=self._extract_listing_image(card),
                )
            )
            if len(entries) >= 20:
                break
        return entries

    def parse_detail(self, html: str) -> ArticleDetail:
        soup = BeautifulSoup(html, self._HTML_PARSER)
        body = soup.select_one(self._BODY_SELECTOR)
        blocks = self._extract_blocks(body) if body is not None else ()
        content = "\n".join(block.text for block in blocks if block.type == "text" and block.text) or None
        return ArticleDetail(
            title=self._node_text_or_content(soup.select_one(self._TITLE_SELECTOR)),
            content=content,
            summary=self._node_text_or_content(soup.select_one(self._SUMMARY_SELECTOR)),
            author=self._extract_first_text_or_content(soup, self._AUTHOR_SELECTORS),
            published_at=self._parse_datetime(self._extract_first_text_or_content(soup, self._DATE_SELECTORS)),
            tag=self._extract_tags(soup),
            type=self._extract_category(soup),
            language=self.default_language,
            blocks=blocks,
        )

    @staticmethod
    def _keyword_slug(keyword: str) -> str:
        slug = re.sub(r"\s+", "-", keyword.strip())
        slug = re.sub(r"-+", "-", slug).strip("-")
        return quote(slug or "-")

    @classmethod
    def _extract_news_id(cls, url: str) -> Optional[str]:
        match = cls._NEWS_ID_PATTERN.search(url or "")
        return match.group(1) if match else None

    @staticmethod
    def _is_publication_link(href: str) -> bool:
        return re.search(r"-p\d+\.epi(?:[?#].*)?$", href or "") is not None

    @staticmethod
    def _is_main_result_card(card: Tag) -> bool:
        image = card.select_one(".bm-card-image")
        classes = " ".join(image.get("class") or []) if image else ""
        return "w-[240px]" in classes

    def _extract_listing_image(self, card: Tag) -> Optional[str]:
        image = card.select_one(".bm-card-image img")
        return self._image_src(image)

    def _extract_blocks(self, body: Tag) -> tuple[ContentBlock, ...]:
        blocks: List[ContentBlock] = []
        skip_caption_nodes: set[int] = set()
        children = [child for child in body.find_all(recursive=False) if isinstance(child, Tag)]
        for index, child in enumerate(children):
            if id(child) in skip_caption_nodes or self._is_noise(child):
                continue
            if child.select_one("img") is not None:
                caption = self._next_caption(children, index)
                if caption is not None:
                    skip_caption_nodes.add(id(caption))
                block = self._image_block(child, caption)
                if block is not None:
                    blocks.append(block)
                continue
            if self._is_caption(child):
                continue
            if child.name in {"p", "h2", "h3", "blockquote", "ul", "ol"}:
                text = child.get_text(" ", strip=True)
                if text:
                    blocks.append(ContentBlock(type="text", text=text))
        return tuple(blocks)

    def _image_block(self, node: Tag, caption_node: Optional[Tag]) -> Optional[ContentBlock]:
        img = node.select_one("img")
        src = self._image_src(img)
        if not src:
            return None
        caption = caption_node.get_text(" ", strip=True) if caption_node else None
        return ContentBlock(type="image", image_url=urljoin(self.base_url, src), caption=caption or None)

    @staticmethod
    def _next_caption(children: list[Tag], index: int) -> Optional[Tag]:
        if index + 1 >= len(children):
            return None
        candidate = children[index + 1]
        return candidate if BaomoiParser._is_caption(candidate) else None

    @staticmethod
    def _is_caption(node: Tag) -> bool:
        classes = set(node.get("class") or [])
        return "media-caption" in classes or "caption" in classes

    @staticmethod
    def _image_src(img: Optional[Tag]) -> Optional[str]:
        if img is None:
            return None
        for attr in ("data-src", "data-original", "src", "srcset", "data-srcset"):
            value = img.get(attr)
            if value and not value.startswith("data:"):
                return value.split(",", 1)[0].split()[0].strip()
        source = img.find_previous("source")
        if source and source.get("srcset") and not source["srcset"].startswith("data:"):
            return source["srcset"].split(",", 1)[0].split()[0].strip()
        return None

    @classmethod
    def _is_noise(cls, node: Tag) -> bool:
        classes = node.get("class") or []
        return any(token in cls._NOISE_CLASS_TOKENS for token in classes)

    @staticmethod
    def _node_text_or_content(node: Optional[Tag]) -> Optional[str]:
        if node is None:
            return None
        content = node.get("content") or node.get("datetime")
        if content:
            return content.strip()
        text = node.get_text(" ", strip=True)
        return text or None

    @classmethod
    def _extract_first_text_or_content(cls, soup: BeautifulSoup, selectors: str | tuple[str, ...]) -> Optional[str]:
        selector_tuple = (selectors,) if isinstance(selectors, str) else selectors
        for selector in selector_tuple:
            value = cls._node_text_or_content(soup.select_one(selector))
            if value:
                return value
        return None

    @staticmethod
    def _extract_category(soup: BeautifulSoup) -> Optional[str]:
        meta = soup.select_one("meta[property='article:section']")
        if meta and meta.get("content"):
            return meta["content"].strip()
        nodes = [node.get_text(" ", strip=True) for node in soup.select(".breadcrumb a, nav a")]
        nodes = [node for node in nodes if node]
        return nodes[-1] if nodes else None

    @staticmethod
    def _extract_tags(soup: BeautifulSoup) -> Optional[str]:
        tags = [node.get_text(" ", strip=True) for node in soup.select("a.tag-link, a[href*='-tag']")]
        tags = [tag for tag in tags if tag]
        return ", ".join(dict.fromkeys(tags)) or None

    @classmethod
    def _parse_datetime(cls, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        cleaned = re.sub(r"\s+", " ", raw).strip()
        cleaned = cleaned.replace("Z", "+0000")
        cleaned = cleaned.replace("+07:00", "+0700")
        for pattern in cls._DATETIME_PATTERNS:
            try:
                return datetime.strptime(cleaned, pattern)
            except ValueError:
                continue
        logger.debug("Could not parse Bao Moi publication datetime: %r", raw)
        return None

    @staticmethod
    def _unique_entries(entries: List[ListingEntry]) -> List[ListingEntry]:
        unique: List[ListingEntry] = []
        seen: set[str] = set()
        for entry in entries:
            key = entry.external_id or entry.url
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        return unique

    @staticmethod
    def _proxy_server_from_env() -> Optional[str]:
        for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            value = os.getenv(key)
            if value:
                return value.strip()
        return None