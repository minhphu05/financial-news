"""
Generic per-keyword crawl loop.

Drives any :class:`~src.scraper.base_parser.BaseParser` across paginated search
results for a single keyword, persisting new articles to ADLS (content) and
PostgreSQL (metadata). Site-agnostic: all DOM knowledge lives in the parser.

Incremental early-stop: once ``consecutive_known_threshold`` already-seen
articles appear in a row, the crawl stops — daily runs finish fast.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Set
from urllib.parse import urlsplit

from tqdm import tqdm

from src.scraper.storage.adls_writer import ContentDocument
from src.scraper.engine.base_parser import BaseParser
from src.scraper.config import ScraperSettings
from src.scraper.http_client import HttpClient
from src.scraper.storage.repository import MetadataRepository
from src.scraper.engine.types import ArticleDetail, ArticleRecord, KeywordRecord, KeywordResult, ListingEntry
from src.utils.logger import get_logger, set_log_context

logger = get_logger(__name__)


@dataclass
class _CrawlContext:
    """Bundle of collaborators shared across one keyword crawl."""

    parser: BaseParser
    record: KeywordRecord
    settings: ScraperSettings
    client: HttpClient
    repository: MetadataRepository
    adls: object
    source_id: str
    crawl_job_id: str
    seen_ids: Set[str]


def crawl_keyword(
    *,
    parser: BaseParser,
    record: KeywordRecord,
    settings: ScraperSettings,
    client: HttpClient,
    repository: MetadataRepository,
    adls: object,
    source_id: str,
    crawl_job_id: str,
    seen_ids: Set[str],
) -> KeywordResult:
    """Crawl every listing page for one keyword on one source.

    ``seen_ids`` is shared across all keywords of the *same ticker* so the same
    article is never scraped twice when several keywords overlap.
    """
    ctx = _CrawlContext(
        parser=parser,
        record=record,
        settings=settings,
        client=client,
        repository=repository,
        adls=adls,
        source_id=source_id,
        crawl_job_id=crawl_job_id,
        seen_ids=seen_ids,
    )
    set_log_context(
        source_name=parser.name, ticker_symbol=record.ticker, keyword=record.keyword
    )

    result = KeywordResult()
    consecutive_known = 0

    pages = tqdm(
        range(settings.start_page, settings.max_pages + 1),
        desc=f"[{parser.name}:{record.ticker}] {record.keyword}",
        unit="page",
        leave=False,
    )

    for page in pages:
        entries = _fetch_listing(ctx, page, result)
        if entries is None:
            break  # unreachable or exhausted; result flags already set

        result.pages += 1
        result.found += len(entries)
        consecutive_known = _process_entries(ctx, entries, result, consecutive_known)
        if result.early_stopped:
            break

    logger.success(
        "Keyword '%s' [%s:%s] -> %s new, %s skipped, %s pages%s",
        record.keyword,
        parser.name,
        record.ticker,
        result.persisted,
        result.skipped,
        result.pages,
        " (early-stop)" if result.early_stopped else "",
    )
    return result


def _fetch_listing(
    ctx: _CrawlContext, page: int, result: KeywordResult
) -> list[ListingEntry] | None:
    """Return parsed listing entries, or ``None`` to stop the crawl."""
    browser_fetcher = getattr(ctx.parser, "fetch_listing_entries", None)
    if callable(browser_fetcher):
        if page != ctx.settings.start_page:
            result.is_exhausted = True
            return None
        entries = browser_fetcher(ctx.record.keyword, ctx.settings)
        if not entries:
            logger.info("No items for '%s'; stopping.", ctx.record.keyword)
            result.is_exhausted = True
            return None
        return entries

    response = ctx.client.get(ctx.parser.build_search_url(ctx.record.keyword, page))
    if response is None:
        logger.warning("Listing unreachable; stopping at page %s.", page)
        result.error = "LISTING_UNREACHABLE"
        return None
    if ctx.parser.is_listing_exhausted(response.text):
        logger.info("Keyword '%s' exhausted at page %s.", ctx.record.keyword, page)
        result.is_exhausted = True
        return None
    entries = ctx.parser.parse_listing(response.text)
    if not entries:
        logger.info("No items for '%s' at page %s; stopping.", ctx.record.keyword, page)
        result.is_exhausted = True
        return None
    return entries


def _process_entries(
    ctx: _CrawlContext,
    entries: list[ListingEntry],
    result: KeywordResult,
    consecutive_known: int,
) -> int:
    """Process one page of entries; returns the updated consecutive-known count."""
    threshold = ctx.settings.consecutive_known_threshold

    for entry in entries:
        url_hash = ctx.parser.url_hash(entry.url)
        dedup_id = entry.external_id or url_hash

        already_seen = dedup_id in ctx.seen_ids or ctx.repository.article_exists(url_hash)
        if already_seen:
            ctx.seen_ids.add(dedup_id)
            result.skipped += 1
            consecutive_known += 1
            if consecutive_known >= threshold:
                logger.info(
                    "Early stop for '%s': %s consecutive known articles.",
                    ctx.record.keyword,
                    consecutive_known,
                )
                result.early_stopped = True
                return consecutive_known
            continue

        consecutive_known = 0
        ctx.seen_ids.add(dedup_id)
        article_id = _scrape_and_persist(ctx, entry, url_hash)
        if article_id is not None:
            result.persisted += 1
            result.persisted_article_ids.append(article_id)

    return consecutive_known


def _scrape_and_persist(
    ctx: _CrawlContext, entry: ListingEntry, url_hash: str
) -> str | None:
    """Fetch the detail page, upload content to ADLS, and write metadata."""
    detail_html = _fetch_detail_html(ctx, entry.url)
    if detail_html is None:
        logger.error("Detail fetch failed: %s", entry.url)
        return None
    detail = ctx.parser.parse_detail(detail_html)

    title = detail.title or entry.title or "(untitled)"
    summary = entry.summary or detail.summary
    content = detail.content
    has_content = bool(content)
    language = detail.language or ctx.parser.default_language

    json_path = None
    if has_content:
        json_path = _upload_content(ctx, entry, detail, url_hash, title, summary, language)
        if json_path is None:
            return None

    record = ArticleRecord(
        source_id=ctx.source_id,
        crawl_job_id=ctx.crawl_job_id,
        url=entry.url,
        url_hash=url_hash,
        title=title,
        summary=summary,
        published_at=detail.published_at,
        json_path=json_path,
        status="CONTENT_DONE" if has_content else "METADATA_ONLY",
    )

    try:
        article_id = ctx.repository.upsert_article(record)
        ctx.repository.link_article_stock(
            article_id=article_id,
            stock_id=ctx.record.stock_id,
            matched_keyword=ctx.record.keyword,
            confidence=1.0,
        )
        return article_id
    except Exception as exc:
        logger.exception("Failed to persist metadata for %s: %s", entry.url, exc)
        return None


def _fetch_detail_html(ctx: _CrawlContext, url: str) -> str | None:
    rendered_fetcher = getattr(ctx.parser, "fetch_detail_html", None)
    if callable(rendered_fetcher):
        return rendered_fetcher(url, ctx.settings)

    response = ctx.client.get(url)
    return response.text if response is not None else None


def _upload_content(
    ctx: _CrawlContext,
    entry: ListingEntry,
    detail: ArticleDetail,
    url_hash: str,
    title: str,
    summary: str | None,
    language: str,
) -> str | None:
    """Upload the article JSON + its image binaries to ADLS.

    Layout per article::

        {folder}/{stem}.json          - content document (image URLs kept as-is)
        {folder}/images/{NN}_{name}   - downloaded image binaries, in order
    """
    document = ContentDocument(
        id=entry.external_id,
        url=entry.url,
        url_hash=url_hash,
        source=ctx.parser.name,
        ticker=ctx.record.ticker,
        title=title,
        summary=summary,
        cover_image=entry.image_url,
        author=detail.author,
        tag=detail.tag,
        type=detail.type,
        language=language,
        published_at=detail.published_at.isoformat() if detail.published_at else None,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        tickers=[ctx.record.ticker],
        matched_keyword=ctx.record.keyword,
        content=detail.content,
        blocks=[asdict(block) for block in detail.blocks],
    )
    try:
        paths = ctx.adls.build_paths(
            document.source,
            document.ticker,
            document.id,
            document.url_hash,
            detail.published_at,
        )
        json_path = ctx.adls.upload_document(paths, document)
    except Exception as exc:  # pragma: no cover - network/permission dependent
        logger.exception("ADLS upload failed for %s: %s", entry.url, exc)
        return None

    _store_images(ctx, paths, entry, detail)
    return json_path


def _store_images(
    ctx: _CrawlContext,
    paths,
    entry: ListingEntry,
    detail: ArticleDetail,
) -> None:
    """Download every image (cover + in-body) and upload it next to the JSON."""
    urls = _collect_image_urls(entry, detail)
    for index, image_url in enumerate(urls):
        image_data, content_type = _fetch_image_bytes(ctx, image_url, entry.url)
        if not image_data:
            logger.warning("Image fetch failed: %s", image_url)
            continue
        filename = _image_filename(index, image_url, content_type)
        try:
            ctx.adls.upload_image(paths, filename, image_data)
        except Exception as exc:  # pragma: no cover - network/permission dependent
            logger.warning("Image upload failed (%s): %s", image_url, exc)


def _fetch_image_bytes(ctx: _CrawlContext, url: str, referer: str | None = None) -> tuple[bytes | None, str | None]:
    binary_fetcher = getattr(ctx.parser, "fetch_binary", None)
    if callable(binary_fetcher):
        return binary_fetcher(url, ctx.settings, referer=referer)

    response = ctx.client.get(url)
    if response is None or not response.content:
        return None, None
    return response.content, response.headers.get("Content-Type")


def _collect_image_urls(entry: ListingEntry, detail: ArticleDetail) -> List[str]:
    """Cover image first, then in-body images, preserving order and de-duping."""
    ordered: List[str] = []
    seen: Set[str] = set()
    candidates = [entry.image_url] + [
        block.image_url for block in detail.blocks if block.type == "image"
    ]
    for url in candidates:
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


_EXT_PATTERN = re.compile(r"\.(jpe?g|png|gif|webp|bmp|svg)$", re.IGNORECASE)
_CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}


def _image_filename(index: int, url: str, content_type: str | None) -> str:
    """Build an ordered, filesystem-safe image filename: ``NN_name.ext``."""
    base = os.path.basename(urlsplit(url).path) or f"image_{index}"
    base = re.sub(r"[^0-9A-Za-z._-]+", "_", base).strip("_") or f"image_{index}"
    if not _EXT_PATTERN.search(base):
        ext = _CONTENT_TYPE_EXT.get((content_type or "").split(";")[0].strip().lower(), ".jpg")
        base = f"{base}{ext}"
    return f"{index:02d}_{base}"

