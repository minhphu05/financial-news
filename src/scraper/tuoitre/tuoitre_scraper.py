"""
Tuoi Tre (https://tuoitre.vn) scraper.

Search results are rendered and extended by scrolling, so this source exposes
``fetch_listing_entries`` for the generic crawler to call via Playwright.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.scraper.engine.base_parser import BaseParser
from src.scraper.engine.types import ArticleDetail, ContentBlock, ListingEntry
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TuoitreParser(BaseParser):
    """Parser and rendered-listing fetcher for Tuoi Tre search results."""

    name = "tuoitre"
    base_url = os.getenv("TUOITRE_BASE_URL", "https://tuoitre.vn")
    default_language = "vi"

    _HTML_PARSER = "html.parser"
    _SEARCH_URL_TEMPLATE = os.getenv(
        "TUOITRE_SEARCH_URL_TEMPLATE",
        "https://tuoitre.vn/tim-kiem.htm?keywords={keyword}",
    )

    _NEWS_ID_PATTERN = re.compile(r"-(\d+)\.htm(?:[?#].*)?$")
    _ITEM_SELECTOR = "article.box-category-item"
    _TOTAL_SELECTOR = "div.total-search span.bold"
    _TITLE_SELECTOR = "h1.detail-title, h1.article-title, h1"
    _SUMMARY_SELECTOR = (
        "h2.detail-sapo, div.detail-sapo, p.detail-sapo, "
        "meta[name='description'], meta[property='og:description']"
    )
    _BODY_SELECTOR = (
        "div.detail-content.afcbc-body, div.detail-content[data-role='content'], "
        "div.detail-content, div#main-detail-body, article.fck_detail"
    )
    _CATEGORY_SELECTOR = (
        "div.detail-cate a, div.breadcrumb a:last-child, "
        "meta[property='article:section']"
    )
    _AUTHOR_SELECTORS = (
        "div.detail-author",
        "p.detail-author",
        "div.author",
        "p.author",
        "meta[name='author']",
    )
    _DATE_SELECTORS = (
        "div.detail-time",
        "span.detail-time",
        "time[datetime]",
        "time",
        "meta[property='article:published_time']",
        "meta[name='pubdate']",
    )
    _TAG_SELECTOR = "div.tags a, div.detail-tags a, a[href*='/tag/']"
    _NOISE_CLASS_TOKENS = frozenset(
        {
            "ads",
            "advertisement",
            "banner",
            "box-related",
            "detail-related",
            "related-news",
            "social-share",
        }
    )
    _DATETIME_PATTERNS = (
        "%d/%m/%Y %H:%M GMT%z",
        "%d/%m/%Y %H:%M",
        "%H:%M %d/%m/%Y",
        "%H:%M, %d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    )

    def build_search_url(self, keyword: str, page: int) -> str:
        encoded_keyword = quote_plus(keyword.strip())
        return self._SEARCH_URL_TEMPLATE.format(keyword=encoded_keyword, page=page)

    def fetch_listing_entries(self, keyword: str, settings) -> List[ListingEntry]:
        """Render the search page, scroll until enough/stable results, and parse entries."""
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Playwright is required for Tuoi Tre search scrolling. "
                "Install it and run `playwright install chromium`."
            ) from exc

        url = self.build_search_url(keyword, 1)
        timeout_ms = max(settings.request_timeout, 10) * 1000
        pause_ms = int(os.getenv("TUOITRE_SCROLL_PAUSE_MS", "1200"))
        max_scrolls = int(os.getenv("TUOITRE_MAX_SCROLLS", "500"))
        stable_round_limit = int(os.getenv("TUOITRE_STABLE_SCROLL_ROUNDS", "8"))
        max_items = int(os.getenv("TUOITRE_MAX_ITEMS", "0"))

        logger.info("Rendering Tuoi Tre search: %s", url)
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
                    page.wait_for_selector(
                        f"{self._ITEM_SELECTOR}, {self._TOTAL_SELECTOR}",
                        timeout=timeout_ms,
                    )
                except PlaywrightTimeoutError:
                    logger.warning("Tuoi Tre listing did not expose expected nodes: %s", url)

                total = self.parse_total_results(page.content())
                previous_count = 0
                stable_rounds = 0

                for _ in range(max_scrolls):
                    entries = self._unique_entries(self.parse_listing(page.content()))
                    current_count = len(entries)
                    if (total and current_count >= total) or (max_items > 0 and current_count >= max_items):
                        break
                    if current_count == previous_count:
                        stable_rounds += 1
                    else:
                        stable_rounds = 0
                    if stable_rounds >= stable_round_limit:
                        break
                    previous_count = current_count
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(pause_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=timeout_ms)
                    except PlaywrightTimeoutError:
                        pass

                entries = self._unique_entries(self.parse_listing(page.content()))
                if max_items > 0:
                    entries = entries[:max_items]
                logger.info(
                    "Tuoi Tre keyword '%s': parsed %s/%s listing result(s).",
                    keyword,
                    len(entries),
                    total if total is not None else "unknown",
                )
                return entries
            finally:
                browser.close()

    def fetch_detail_html(self, url: str, settings) -> Optional[str]:
        """Fetch one detail page through Playwright for proxy/rendering consistency."""
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Playwright is required for Tuoi Tre detail pages.") from exc

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
                    page.wait_for_selector(
                        f"{self._TITLE_SELECTOR}, {self._BODY_SELECTOR}",
                        timeout=timeout_ms,
                    )
                except PlaywrightTimeoutError:
                    logger.warning("Tuoi Tre detail did not expose expected nodes: %s", url)
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
            raise RuntimeError("Playwright is required for Tuoi Tre image downloads.") from exc

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
                logger.warning("Tuoi Tre image timed out: %s", url)
                return None, None
            finally:
                browser.close()

    def is_listing_exhausted(self, html: str) -> bool:
        return self.parse_total_results(html) == 0 or not self.parse_listing(html)

    def parse_total_results(self, html: str) -> Optional[int]:
        soup = BeautifulSoup(html, self._HTML_PARSER)
        node = soup.select_one(self._TOTAL_SELECTOR)
        if node is None:
            return None
        raw = re.sub(r"[^0-9]", "", node.get_text(" ", strip=True))
        return int(raw) if raw else None

    def parse_listing(self, html: str) -> List[ListingEntry]:
        soup = BeautifulSoup(html, self._HTML_PARSER)
        entries: List[ListingEntry] = []

        for item in soup.select(self._ITEM_SELECTOR):
            anchor = item.select_one("a.box-category-link-title[href]") or item.select_one(
                "h3 a[href]"
            )
            if anchor is None:
                continue
            href = anchor.get("href")
            if not href:
                continue

            absolute_url = urljoin(self.base_url, href)
            title = anchor.get("title") or anchor.get_text(" ", strip=True)
            summary_node = item.select_one("p.box-category-sapo, a.box-category-sapo")
            summary = summary_node.get_text(" ", strip=True) if summary_node else None

            entries.append(
                ListingEntry(
                    url=absolute_url,
                    title=title or None,
                    summary=summary,
                    external_id=item.get("data-newsid") or self._extract_news_id(absolute_url),
                    image_url=self._extract_listing_image(item),
                )
            )

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
            published_at=self._parse_datetime(
                self._extract_first_text_or_content(soup, self._DATE_SELECTORS)
            ),
            tag=self._extract_tags(soup),
            type=self._node_text_or_content(soup.select_one(self._CATEGORY_SELECTOR)),
            language=self.default_language,
            blocks=blocks,
        )

    @classmethod
    def _extract_news_id(cls, url: str) -> Optional[str]:
        match = cls._NEWS_ID_PATTERN.search(url or "")
        return match.group(1) if match else None

    def _extract_listing_image(self, item: Tag) -> Optional[str]:
        img = item.select_one("img.box-category-avatar, a.img-resize img, img")
        return self._image_src(img) if img is not None else None

    def _extract_blocks(self, body: Tag) -> tuple[ContentBlock, ...]:
        blocks: List[ContentBlock] = []

        for child in body.find_all(recursive=False):
            if not isinstance(child, Tag) or self._is_noise(child):
                continue
            if child.name in {"figure", "picture", "table"} or child.select_one("img") is not None:
                block = self._figure_block(child)
                if block is not None:
                    blocks.append(block)
                continue
            if child.name in {"p", "h2", "h3", "blockquote", "ul", "ol"}:
                text = child.get_text(" ", strip=True)
                if text:
                    blocks.append(ContentBlock(type="text", text=text))
        return tuple(blocks)

    def _figure_block(self, node: Tag) -> Optional[ContentBlock]:
        img = node.select_one("img")
        src = self._image_src(img)
        if not src:
            return None
        caption_node = node.select_one("figcaption, .PhotoCMS_Caption, .caption")
        caption = caption_node.get_text(" ", strip=True) if caption_node else None
        return ContentBlock(
            type="image",
            image_url=urljoin(self.base_url, src),
            caption=caption or None,
        )

    @staticmethod
    def _image_src(img: Optional[Tag]) -> Optional[str]:
        if img is None:
            return None
        for attr in ("data-original", "data-src", "src", "data-srcset", "srcset"):
            value = img.get(attr)
            if value and not value.startswith("data:"):
                return value.split(",", 1)[0].split()[0].strip()
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
    def _extract_first_text_or_content(
        cls, soup: BeautifulSoup, selectors: tuple[str, ...]
    ) -> Optional[str]:
        for selector in selectors:
            value = cls._node_text_or_content(soup.select_one(selector))
            if value:
                return value
        return None

    def _extract_tags(self, soup: BeautifulSoup) -> Optional[str]:
        tags = [node.get_text(" ", strip=True) for node in soup.select(self._TAG_SELECTOR)]
        tags = [tag for tag in tags if tag and tag.lower() != "tags:"]
        return ", ".join(dict.fromkeys(tags)) or None

    @classmethod
    def _parse_datetime(cls, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        cleaned = re.sub(r"\s+", " ", raw).strip()
        cleaned = cleaned.replace("+07:00", "+0700")
        cleaned = cleaned.replace("GMT+7", "GMT+0700")
        cleaned = re.sub(r"^(Thứ \w+,\s*)", "", cleaned, flags=re.IGNORECASE)
        for pattern in cls._DATETIME_PATTERNS:
            try:
                return datetime.strptime(cleaned, pattern)
            except ValueError:
                continue
        match = re.search(
            r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})",
            cleaned,
        )
        if match:
            day, month, year, hour, minute = match.groups()
            try:
                return datetime(int(year), int(month), int(day), int(hour), int(minute))
            except ValueError:
                return None
        logger.debug("Could not parse Tuoi Tre publication datetime: %r", raw)
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