"""
VnExpress (https://vnexpress.net) scraper.

Search pages are rendered with Selenium. The source walks stable search URLs
(``page=1..N``) and stops when VnExpress returns its explicit no-result block.
Detail-page parsing remains pure HTML parsing so it stays unit-testable.
"""
from __future__ import annotations

import os
import re
import time
import json
import base64
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote_plus, urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.scraper.engine.base_parser import BaseParser
from src.scraper.engine.types import ArticleDetail, ContentBlock, ListingEntry
from src.utils.logger import get_logger

logger = get_logger(__name__)


class VnexpressParser(BaseParser):
    """Parser and Selenium listing fetcher for VnExpress search results."""

    name = "vnexpress"
    base_url = os.getenv("VNEXPRESS_BASE_URL", "https://vnexpress.net")
    default_language = "vi"

    _HTML_PARSER = "html.parser"
    _SEARCH_URL_TEMPLATE = os.getenv(
        "VNEXPRESS_SEARCH_URL_TEMPLATE",
        "https://timkiem.vnexpress.net/?q={keyword}&page={page}",
    )

    _NEWS_ID_PATTERN = re.compile(r"-(\d+)\.html(?:[?#].*)?$")
    _ITEM_SELECTOR = "article.item-news, div.item-news"
    _NO_RESULT_SELECTOR = "p.mb20.no-result, p.no-result"
    _TITLE_SELECTOR = "h1.title-detail, h1.title_news_detail, h1"
    _SUMMARY_SELECTOR = "p.description, h2.description, meta[name='description'], meta[property='og:description']"
    _BODY_SELECTOR = "article.fck_detail, div.fck_detail, div.sidebar-1 article"
    _DATE_SELECTORS = (
        "span.date",
        "div.header-content span.date",
        "meta[property='article:published_time']",
        "meta[name='pubdate']",
        "time[datetime]",
        "time",
    )
    _CATEGORY_SELECTOR = "ul.breadcrumb a, meta[property='article:section']"
    _AUTHOR_SELECTORS = ("p.author", "strong.author", "meta[name='author']")
    _NOISE_CLASS_TOKENS = frozenset(
        {
            "box_embed_video_parent",
            "related_news",
            "list-news",
            "social_share",
            "banner",
            "ads",
            "box_category",
        }
    )
    _DATETIME_PATTERNS = (
        "%d/%m/%Y, %H:%M GMT%z",
        "%d/%m/%Y, %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    )

    def build_search_url(self, keyword: str, page: int) -> str:
        return self._SEARCH_URL_TEMPLATE.format(
            keyword=quote_plus(keyword.strip()),
            page=page,
        )

    def fetch_listing_entries(self, keyword: str, settings) -> List[ListingEntry]:
        """Fetch every search-result page with Selenium until VnExpress is exhausted."""
        try:
            from selenium import webdriver
            from selenium.common.exceptions import TimeoutException
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Selenium is required for VnExpress search pages.") from exc

        timeout = max(settings.request_timeout, 10)
        options = self._chrome_options(settings.user_agent)
        max_items = int(os.getenv("VNEXPRESS_MAX_ITEMS", "0"))
        entries: List[ListingEntry] = []

        logger.info("Rendering VnExpress search for keyword '%s'.", keyword)
        with webdriver.Chrome(options=options) as driver:
            driver.set_page_load_timeout(timeout)
            for page_number in range(settings.start_page, settings.max_pages + 1):
                url = self.build_search_url(keyword, page_number)
                driver.get(url)
                try:
                    WebDriverWait(driver, timeout).until(
                        lambda page: page.find_elements(By.CSS_SELECTOR, self._ITEM_SELECTOR)
                        or page.find_elements(By.CSS_SELECTOR, self._NO_RESULT_SELECTOR)
                    )
                except TimeoutException:
                    logger.warning("VnExpress listing timed out: %s", url)

                html = driver.page_source
                if self.is_listing_exhausted(html):
                    logger.info("VnExpress keyword '%s' exhausted at page %s.", keyword, page_number)
                    break
                page_entries = self.parse_listing(html)
                if not page_entries:
                    logger.info("No VnExpress entries for '%s' at page %s; stopping.", keyword, page_number)
                    break
                entries.extend(page_entries)
                if max_items > 0 and len(self._unique_entries(entries)) >= max_items:
                    entries = self._unique_entries(entries)[:max_items]
                    break

        unique = self._unique_entries(entries)
        logger.info("VnExpress keyword '%s': parsed %s listing result(s).", keyword, len(unique))
        return unique

    def fetch_detail_html(self, url: str, settings) -> Optional[str]:
        """Fetch one article detail page through Selenium."""
        try:
            from selenium import webdriver
            from selenium.common.exceptions import TimeoutException
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Selenium is required for VnExpress detail pages.") from exc

        timeout = max(settings.request_timeout, 10)
        with webdriver.Chrome(options=self._chrome_options(settings.user_agent)) as driver:
            driver.set_page_load_timeout(timeout)
            driver.get(url)
            try:
                WebDriverWait(driver, timeout).until(
                    lambda page: page.find_elements(By.CSS_SELECTOR, self._TITLE_SELECTOR)
                    or page.find_elements(By.CSS_SELECTOR, self._BODY_SELECTOR)
                )
            except TimeoutException:
                logger.warning("VnExpress detail timed out: %s", url)
            return driver.page_source

    def fetch_binary(
        self,
        url: str,
        settings,
        referer: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """Fetch image bytes through Selenium/Chrome DevTools to honor browser proxy auth."""
        try:
            from selenium import webdriver
            from selenium.common.exceptions import WebDriverException
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Selenium is required for VnExpress image downloads.") from exc

        timeout = max(settings.request_timeout, 10)
        image_timeout = max(3, min(int(os.getenv("VNEXPRESS_IMAGE_TIMEOUT", "8")), timeout))
        options = self._chrome_options(settings.user_agent)
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        with webdriver.Chrome(options=options) as driver:
            driver.set_page_load_timeout(timeout)
            driver.set_script_timeout(image_timeout + 2)
            driver.execute_cdp_cmd("Network.enable", {})
            if referer:
                driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Referer": referer}})
                driver.get(referer)
                self._scroll_for_lazy_images(driver)
                data, mime_type = self._image_from_performance_log(driver, url, image_timeout)
                if data:
                    return data, mime_type
                try:
                    data, mime_type = self._image_from_browser_fetch(driver, url, image_timeout)
                    if data:
                        return data, mime_type
                except WebDriverException as exc:
                    logger.debug("VnExpress article-context image fallback failed for %s: %s", url, exc)
                if self._is_vnexpress_cdn_url(url):
                    return None, None
            driver.get(url)
            content_type = driver.execute_script("return document.contentType || ''")
            if content_type and not str(content_type).startswith("image/"):
                logger.debug("VnExpress CDN returned non-image content for %s: %s", url, content_type)
                return None, None
            data, mime_type = self._image_from_performance_log(driver, url, image_timeout)
            if data:
                return data, mime_type
            try:
                return self._image_from_browser_fetch(driver, url, image_timeout)
            except WebDriverException as exc:
                logger.debug("VnExpress browser image fallback failed for %s: %s", url, exc)
        return None, None

    def _image_from_performance_log(self, driver, target_url: str, timeout: int) -> tuple[bytes | None, str | None]:
        deadline = time.monotonic() + min(max(timeout, 5), 20)
        pending: dict[str, str] = {}

        while time.monotonic() < deadline:
            for entry in driver.get_log("performance"):
                message = json.loads(entry["message"])["message"]
                method = message.get("method")
                params = message.get("params", {})
                request_id = params.get("requestId")

                if method == "Network.responseReceived":
                    response = params.get("response", {})
                    mime_type = response.get("mimeType") or ""
                    response_url = response.get("url") or ""
                    status = int(response.get("status") or 0)
                    if (
                        request_id
                        and status < 400
                        and mime_type.startswith("image/")
                        and self._same_image_url(target_url, response_url)
                    ):
                        pending[request_id] = mime_type
                    continue

                if method != "Network.loadingFinished" or request_id not in pending:
                    continue
                try:
                    body = driver.execute_cdp_cmd(
                        "Network.getResponseBody",
                        {"requestId": request_id},
                    )
                except Exception as exc:  # pragma: no cover - timing/browser dependent
                    logger.debug("VnExpress CDP body unavailable for %s: %s", target_url, exc)
                    continue
                raw = body.get("body") or ""
                if not raw:
                    continue
                data = base64.b64decode(raw) if body.get("base64Encoded") else raw.encode()
                return data, pending[request_id]
            time.sleep(0.2)

        return None, None

    @staticmethod
    def _image_from_browser_fetch(driver, url: str, timeout: int) -> tuple[bytes | None, str | None]:
        script = """
            const done = arguments[arguments.length - 1];
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), arguments[1] * 1000);
            fetch(arguments[0], { cache: 'no-store', credentials: 'omit', signal: controller.signal })
                .then(async response => {
                    clearTimeout(timer);
                    if (!response.ok) {
                        done({ ok: false, status: response.status });
                        return;
                    }
                    const buffer = await response.arrayBuffer();
                    const bytes = new Uint8Array(buffer);
                    let binary = '';
                    const chunkSize = 0x8000;
                    for (let i = 0; i < bytes.length; i += chunkSize) {
                        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
                    }
                    done({
                        ok: true,
                        mimeType: response.headers.get('content-type') || '',
                        body: btoa(binary),
                    });
                })
                .catch(error => {
                    clearTimeout(timer);
                    done({ ok: false, error: String(error) });
                });
        """
        result = driver.execute_async_script(script, url, timeout) or {}
        if not result.get("ok") or not result.get("body"):
            return None, None
        return base64.b64decode(result["body"]), result.get("mimeType")

    @staticmethod
    def _scroll_for_lazy_images(driver) -> None:
        try:
            height = int(driver.execute_script("return document.body.scrollHeight || 0") or 0)
        except Exception:  # pragma: no cover - browser dependent
            return
        for offset in range(0, min(height, 8000), 700):
            driver.execute_script("window.scrollTo(0, arguments[0])", offset)
            time.sleep(0.15)
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(0.5)

    @staticmethod
    def _same_image_url(target_url: str, response_url: str) -> bool:
        target = urlsplit(target_url)
        response = urlsplit(response_url)
        return target.path.lower() == response.path.lower()

    @staticmethod
    def _is_vnexpress_cdn_url(url: str) -> bool:
        host = urlsplit(url).netloc.lower()
        return host.endswith("vnecdn.net")

    def is_listing_exhausted(self, html: str) -> bool:
        soup = BeautifulSoup(html, self._HTML_PARSER)
        no_result = soup.select_one(self._NO_RESULT_SELECTOR)
        if no_result and "Không tìm thấy kết quả" in no_result.get_text(" ", strip=True):
            return True
        return False

    def parse_listing(self, html: str) -> List[ListingEntry]:
        soup = BeautifulSoup(html, self._HTML_PARSER)
        entries: List[ListingEntry] = []

        for item in soup.select(self._ITEM_SELECTOR):
            anchor = item.select_one("h3.title-news a[href]") or item.select_one("a[href]")
            if anchor is None:
                continue
            href = anchor.get("href")
            if not href:
                continue

            url = urljoin(self.base_url, href)
            title = anchor.get("title") or anchor.get_text(" ", strip=True)
            summary_node = item.select_one("p.description a, p.description")
            summary = summary_node.get_text(" ", strip=True) if summary_node else None

            entries.append(
                ListingEntry(
                    url=url,
                    title=title or None,
                    summary=summary,
                    external_id=item.get("data-id") or self._extract_news_id(url),
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
            type=self._extract_category(soup),
            language=self.default_language,
            blocks=blocks,
        )

    @classmethod
    def _extract_news_id(cls, url: str) -> Optional[str]:
        match = cls._NEWS_ID_PATTERN.search(url or "")
        return match.group(1) if match else None

    def _extract_listing_image(self, item: Tag) -> Optional[str]:
        source = item.select_one("picture source[srcset], picture source[data-srcset]")
        src = self._srcset_url(source.get("srcset") or source.get("data-srcset")) if source else None
        if src:
            return src
        img = item.select_one("img")
        return self._image_src(img)

    def _extract_blocks(self, body: Tag) -> tuple[ContentBlock, ...]:
        blocks: List[ContentBlock] = []
        seen_text: set[str] = set()

        for node in body.find_all(["p", "figure", "table"], recursive=True):
            if not isinstance(node, Tag) or self._is_noise(node):
                continue
            if node.name in {"figure", "table"} or node.select_one("img") is not None:
                block = self._figure_block(node)
                if block is not None:
                    blocks.append(block)
                continue
            text = node.get_text(" ", strip=True)
            if text and text not in seen_text:
                seen_text.add(text)
                blocks.append(ContentBlock(type="text", text=text))
        return tuple(blocks)

    def _figure_block(self, node: Tag) -> Optional[ContentBlock]:
        img = node.select_one("img")
        src = self._image_src(img)
        if not src:
            return None
        caption_node = node.select_one("figcaption, .fig-picture, .Image, .caption")
        caption = caption_node.get_text(" ", strip=True) if caption_node else None
        return ContentBlock(type="image", image_url=urljoin(self.base_url, src), caption=caption or None)

    @classmethod
    def _is_noise(cls, node: Tag) -> bool:
        classes = node.get("class") or []
        return any(token in cls._NOISE_CLASS_TOKENS for token in classes)

    @staticmethod
    def _image_src(img: Optional[Tag]) -> Optional[str]:
        if img is None:
            return None
        for attr in ("data-src", "data-original", "src"):
            value = img.get(attr)
            if value and not value.startswith("data:"):
                return value.strip()
        srcset = img.get("srcset") or img.get("data-srcset")
        return VnexpressParser._srcset_url(srcset)

    @staticmethod
    def _srcset_url(srcset: Optional[str]) -> Optional[str]:
        if not srcset:
            return None
        first = srcset.split(",", 1)[0].strip()
        return first.split()[0] if first else None

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

    def _extract_category(self, soup: BeautifulSoup) -> Optional[str]:
        meta = soup.select_one("meta[property='article:section']")
        if meta and meta.get("content"):
            return meta["content"].strip()
        nodes = [node.get_text(" ", strip=True) for node in soup.select(self._CATEGORY_SELECTOR)]
        nodes = [node for node in nodes if node]
        return nodes[-1] if nodes else None

    @staticmethod
    def _extract_tags(soup: BeautifulSoup) -> Optional[str]:
        tags = [node.get_text(" ", strip=True) for node in soup.select(".tags a, .tag_item, a[href*='/tag/']")]
        tags = [tag for tag in tags if tag]
        return ", ".join(dict.fromkeys(tags)) or None

    @classmethod
    def _parse_datetime(cls, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        cleaned = re.sub(r"\s+", " ", raw).strip()
        cleaned = cleaned.replace("+07:00", "+0700")
        cleaned = cleaned.replace("GMT+7", "GMT+0700")
        cleaned = re.sub(r"^Thứ [^,]+,\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("(", "").replace(")", "")
        for pattern in cls._DATETIME_PATTERNS:
            try:
                return datetime.strptime(cleaned, pattern)
            except ValueError:
                continue
        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4}),?\s*(\d{1,2}):(\d{2})", cleaned)
        if match:
            day, month, year, hour, minute = match.groups()
            try:
                return datetime(int(year), int(month), int(day), int(hour), int(minute))
            except ValueError:
                return None
        logger.debug("Could not parse VnExpress publication datetime: %r", raw)
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
    def _chrome_options(user_agent: str):
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={user_agent}")
        proxy = VnexpressParser._proxy_server_from_env()
        if proxy:
            options.add_argument(f"--proxy-server={proxy}")
        return options

    @staticmethod
    def _proxy_server_from_env() -> Optional[str]:
        for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            value = os.getenv(key)
            if value:
                return value.strip()
        return None