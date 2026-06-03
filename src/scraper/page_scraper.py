"""
Listing-page scraper.

Walks paginated search results for a single keyword, yielding fully
assembled :class:`~src.scraper.storage.ScrapedArticle` objects ready for
persistence.

Supports **incremental scraping**: when consecutive already-seen articles
exceed ``settings.consecutive_known_threshold``, the crawl terminates early
to avoid re-processing old pages.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from tqdm import tqdm

from src.scraper.config import ScraperSettings
from src.scraper.detail_scraper import scrape_article_detail
from src.scraper.http_client import HttpClient
from src.scraper.parsers import is_listing_exhausted, parse_listing_page
from src.scraper.storage import ScrapedArticle, StorageManager
from src.utils.logger import get_logger, set_log_context

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Per-keyword crawl context
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KeywordContext:
    """Bundle of attributes that travel alongside a keyword crawl."""

    keyword: str
    ticker_symbol: Optional[str]
    company_name: Optional[str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def scrape_keyword(
    context: KeywordContext,
    settings: ScraperSettings,
    client: HttpClient,
    storage: StorageManager,
) -> dict:
    """
    Crawl every listing page for one keyword and persist found articles.

    The crawl terminates when:

    * The site marks the results as exhausted (no items / "not found" notice).
    * ``settings.max_pages`` has been visited.
    * A listing page cannot be fetched after all retries.
    * **Incremental early-stop**: ``consecutive_known_threshold`` articles in
      a row were already present in the DB. This signals that we've reached
      previously-scraped territory and further pages will be redundant.

    Args:
        context: Keyword + VN30 mapping carried for every article.
        settings: Resolved scraper settings.
        client: Shared HTTP client.
        storage: Shared storage manager.

    Returns:
        A dict summarising the crawl:
        ``{"persisted": int, "persisted_ids": list[str], "skipped": int, "found": int, "pages": int,
           "newest_news_id": str|None, "early_stopped": bool,
           "is_exhausted": bool}``
    """
    # Set structured log context for this keyword
    set_log_context(
        source_name=settings.source_name,
        ticker_symbol=context.ticker_symbol,
        keyword=context.keyword,
    )

    persisted = 0
    persisted_ids: list[str] = []
    skipped = 0
    found = 0
    pages_crawled = 0
    consecutive_known = 0
    newest_news_id: Optional[str] = None
    early_stopped = False
    is_exhausted = False

    page_iter = tqdm(
        range(settings.start_page, settings.max_pages + 1),
        desc=f"[{context.ticker_symbol}] {context.keyword}",
        unit="page",
        leave=False,
    )

    for page_index in page_iter:
        search_url = settings.search_url_template.format(
            page=page_index, keyword=context.keyword
        )
        response = client.get(search_url)
        if response is None:
            logger.warning(
                f"Listing page unreachable; aborting keyword "
                f"'{context.keyword}' at page {page_index}"
            )
            break

        if is_listing_exhausted(response.text):
            logger.info(f"Keyword '{context.keyword}' exhausted at page {page_index}.")
            is_exhausted = True
            break

        entries = parse_listing_page(response.text, settings.base_url)
        if not entries:
            logger.info(
                f"No items found for '{context.keyword}' on page {page_index}; stopping."
            )
            is_exhausted = True
            break

        pages_crawled += 1
        found += len(entries)

        for entry in entries:
            # Track the newest news_id (first article of page 1)
            if newest_news_id is None:
                newest_news_id = entry.news_id

            # Idempotency: skip articles already in the metadata table.
            if storage.article_exists(entry.news_id):
                logger.debug(f"Skip existing news_id={entry.news_id}")
                skipped += 1
                consecutive_known += 1

                # Early-stop: too many consecutive known articles
                if consecutive_known >= settings.consecutive_known_threshold:
                    logger.info(
                        f"Early stop for '{context.keyword}': "
                        f"{consecutive_known} consecutive known articles reached."
                    )
                    early_stopped = True
                    break
                continue

            # Reset counter when we find a genuinely new article
            consecutive_known = 0

            detail = scrape_article_detail(entry.url, client)
            if detail is None:
                continue

            article = ScrapedArticle(
                news_id=entry.news_id,
                url=entry.url,
                title=detail.title or entry.title or "(untitled)",
                summary=entry.summary,
                author=detail.author,
                created_at=detail.created_at,
                scraped_at=datetime.now(timezone.utc),
                source=settings.source_name,
                ticker_symbol=context.ticker_symbol,
                company_name=context.company_name,
                keyword=context.keyword,
                content=detail.content,
            )

            try:
                storage.save_article(article)
                persisted += 1
                persisted_ids.append(article.news_id)
            except Exception as exc:
                logger.exception(
                    f"Failed to persist {entry.news_id} ({entry.url}): {exc}"
                )

        # Break outer loop if early-stopped inside inner loop
        if early_stopped:
            break

    logger.success(
        f"Keyword '{context.keyword}' [{context.ticker_symbol}] -> "
        f"{persisted} new, {skipped} skipped, {pages_crawled} pages"
        f"{' (early-stop)' if early_stopped else ''}"
    )

    # Update incremental progress cursor
    storage.update_progress(
        source=settings.source_name,
        keyword=context.keyword,
        ticker_symbol=context.ticker_symbol,
        last_page_scraped=pages_crawled,
        last_scraped_news_id=newest_news_id,
        articles_added=persisted,
        is_exhausted=is_exhausted,
    )

    return {
        "persisted": persisted,
        "persisted_ids": persisted_ids,
        "skipped": skipped,
        "found": found,
        "pages": pages_crawled,
        "newest_news_id": newest_news_id,
        "early_stopped": early_stopped,
        "is_exhausted": is_exhausted,
    }


def iter_listing_entries(
    keyword: str,
    settings: ScraperSettings,
    client: HttpClient,
) -> Iterator:
    """
    Yield :class:`ListingEntry` objects across every search page for ``keyword``.

    Exposed primarily for inspection/debugging - the production code path
    goes through :func:`scrape_keyword`.
    """
    for page_index in range(settings.start_page, settings.max_pages + 1):
        url = settings.search_url_template.format(page=page_index, keyword=keyword)
        response = client.get(url)
        if response is None or is_listing_exhausted(response.text):
            return
        entries = parse_listing_page(response.text, settings.base_url)
        if not entries:
            return
        yield from entries
