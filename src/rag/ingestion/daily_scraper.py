"""Daily incremental CafeF scraper.

The scraper walks CafeF's keyword search pages and stores every new article
into MongoDB. It stops scanning further pages as soon as it sees an article
URL that is already present in the database, which keeps the daily run
cheap and polite.

This is a re-implementation of the original ``src/cafef_scraper`` module
designed to plug into Prefect and the MongoDB repository layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from bs4 import BeautifulSoup

from src.rag.config import Settings, get_settings
from src.rag.databases import MongoRepository
from src.rag.ingestion.http_utils import request_with_retry
from src.rag.utils import get_logger

logger = get_logger(__name__)


@dataclass
class ScrapeReport:
    """Summary of a single scrape run, returned to the Prefect flow."""

    keywords: List[str]
    pages_scanned: int = 0
    articles_seen: int = 0
    articles_inserted: int = 0
    failed_urls: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        """Stamp the report with the finish timestamp."""
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> Dict[str, object]:
        """Return a JSON-serialisable representation."""
        return {
            "keywords": self.keywords,
            "pages_scanned": self.pages_scanned,
            "articles_seen": self.articles_seen,
            "articles_inserted": self.articles_inserted,
            "failed_urls": self.failed_urls,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class DailyCafefScraper:
    """Scrape CafeF news pages for a given set of keywords.

    Parameters
    ----------
    repo : MongoRepository
        Repository used to upsert raw articles.
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.

    Notes
    -----
    The scraper is deliberately conservative:

    * It walks at most ``settings.scraper.max_pages`` per keyword.
    * As soon as it sees an article whose link already exists in MongoDB, it
      assumes the page has been scraped in a previous run and stops scanning
      further pages for that keyword (early exit).
    """

    def __init__(
        self,
        repo: MongoRepository,
        settings: Optional[Settings] = None,
    ) -> None:
        self._repo = repo
        self._settings = settings or get_settings()

    # -- public API ---------------------------------------------------------
    def run(self, keywords: Optional[Iterable[str]] = None) -> ScrapeReport:
        """Run a daily scrape for every keyword.

        Parameters
        ----------
        keywords : Optional[Iterable[str]]
            Override the keyword list. Defaults to ``settings.scraper.keywords``.

        Returns
        -------
        ScrapeReport
            Run summary.
        """
        kws = list(keywords) if keywords is not None else list(self._settings.scraper.keywords)
        report = ScrapeReport(keywords=kws)

        for kw in kws:
            logger.info("Scraping keyword: %s", kw)
            self._scrape_keyword(kw, report)

        report.mark_done()
        logger.info("Scrape finished: %s", report.as_dict())
        return report

    # -- internals ----------------------------------------------------------
    def _scrape_keyword(self, keyword: str, report: ScrapeReport) -> None:
        """Scrape a single keyword and merge its stats into ``report``."""
        base_url = self._settings.scraper.base_url
        max_pages = self._settings.scraper.max_pages

        for page in range(1, max_pages + 1):
            search_url = f"{base_url}/tim-kiem/trang-{page}.chn?keywords={keyword}"
            response = request_with_retry(
                search_url,
                max_retries=self._settings.scraper.max_retries,
                delay=self._settings.scraper.retry_delay,
                timeout=self._settings.scraper.request_timeout,
            )
            if response is None:
                report.failed_urls.append(search_url)
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            if soup.select_one("div[class='search-content-wrap'] > span") is not None:
                logger.info("Keyword '%s' exhausted at page %s.", keyword, page)
                return

            articles = soup.select(
                "div[class='list-main'] > div[class='search-content-wrap'] "
                "> div[class='timeline list-bytags'] > div[class='item']"
            )

            new_in_page = 0
            for article_tag in articles:
                report.articles_seen += 1
                link_tag = article_tag.select_one("h3[class='titlehidden'] > a")
                summary_tag = article_tag.select_one("div[class='item-content'] > p[class='sapo']")
                if link_tag is None:
                    continue

                href = link_tag.get("href") or ""
                if href.startswith("/"):
                    href = base_url + href

                if self._repo.link_exists(href):
                    continue

                article = self._scrape_detail(href, keyword)
                if article is None:
                    report.failed_urls.append(href)
                    continue
                if summary_tag is not None:
                    article["summary"] = summary_tag.get_text(strip=True)
                article["keyword"] = keyword
                article["page"] = page

                inserted = self._repo.upsert_raw(article)
                if inserted:
                    report.articles_inserted += 1
                    new_in_page += 1

            report.pages_scanned += 1

            # Early exit: a page with zero new items means we've caught up.
            if new_in_page == 0:
                logger.info(
                    "No new articles on page %s for '%s'; stopping early.",
                    page, keyword,
                )
                return

    def _scrape_detail(self, link: str, keyword: str) -> Optional[Dict[str, object]]:
        """Fetch and parse an article detail page.

        Returns ``None`` if the page can't be loaded or has no body.
        """
        response = request_with_retry(
            link,
            max_retries=self._settings.scraper.max_retries,
            delay=self._settings.scraper.retry_delay,
            timeout=self._settings.scraper.request_timeout,
        )
        if response is None:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        is_magazine = soup.select_one("div[class='detail__magazine']") is not None

        title_tag = soup.select_one("h1[class='title']")
        title = title_tag.get_text(strip=True) if title_tag else None

        if not is_magazine:
            post_date_tag = soup.select_one(
                "p[class='dateandcat'] > span[class='pdate']"
            )
            post_date = post_date_tag.get_text(strip=True) if post_date_tag else None

            try:
                container = soup.select("div.w640.fr.clear")[0]
                paragraphs = container.select(
                    "div[class='contentdetail'] > div[class='detail-cmain ss'] "
                    "> div[class='detail-content afcbc-body'] p"
                )
                if not paragraphs:
                    paragraphs = container.select(
                        "table[style='border-collapse: collapse;'] > tbody > tr > td > span"
                    )
                context = "\n".join(p.get_text(strip=True) for p in paragraphs)
            except IndexError:
                context = ""
        else:
            container = soup.select_one("div[class='detail__magazine']")
            paragraphs = container.select("p") if container else []
            context = "\n".join(p.get_text(strip=True) for p in paragraphs)
            post_date_tag = soup.select_one(
                "a[class='link-source-name'] > span[class='time-source-detail']"
            )
            post_date = post_date_tag.get_text(strip=True) if post_date_tag else None

        if not context:
            logger.warning("Empty body for %s", link)
            return None

        return {
            "link": link,
            "title": title,
            "post_date": post_date,
            "context": context,
            "is_magazine": is_magazine,
            "source": "cafef.vn",
            "scraped_keyword": keyword,
        }
