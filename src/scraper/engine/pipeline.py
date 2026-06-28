"""
End-to-end scrape orchestration.

Flow per run:

1. Open PostgreSQL (metadata) and ADLS (content) connections.
2. Register a ``crawl_job`` row.
3. Load ``(stock, keyword)`` pairs from the input provider (PostgreSQL).
4. For every selected source x keyword, run the generic crawler.
5. Record a ``crawl_log`` row per keyword and finalize the ``crawl_job``.

Handles Ctrl+C gracefully — the crawl job is always finalized.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from src.scraper.storage.adls_writer import ADLSContentWriter
from src.scraper.config import ScraperSettings
from src.scraper.engine.crawler import crawl_keyword
from src.scraper.http_client import HttpClient
from src.scraper.storage.inputs import PostgresKeywordProvider
from src.scraper.storage.repository import MetadataRepository
from src.scraper.engine.registry import get_parser, resolve_sources
from src.utils.logger import clear_log_context, get_logger

logger = get_logger(__name__)


@dataclass
class RunSummary:
    """Aggregate counters for one full pipeline run."""

    sources: List[str] = field(default_factory=list)
    keywords_processed: int = 0
    articles_found: int = 0
    articles_persisted: int = 0
    articles_skipped: int = 0
    pages_crawled: int = 0
    errors: int = 0
    failed: List[str] = field(default_factory=list)

    def render(self) -> str:
        return (
            "Run summary\n"
            f"  sources             : {self.sources}\n"
            f"  keywords processed  : {self.keywords_processed}\n"
            f"  articles found      : {self.articles_found}\n"
            f"  articles persisted  : {self.articles_persisted}\n"
            f"  articles skipped    : {self.articles_skipped}\n"
            f"  pages crawled       : {self.pages_crawled}\n"
            f"  errors              : {self.errors}"
            + ("" if not self.failed else f"\n  failed -> {self.failed}")
        )


def run_pipeline(
    settings: ScraperSettings,
    *,
    tickers: Optional[Sequence[str]] = None,
    source_filter: Optional[str] = None,
    triggered_by: str = "manual",
) -> RunSummary:
    """Execute the full scrape across selected sources and tickers."""
    source_names = resolve_sources(source_filter)
    summary = RunSummary(sources=source_names)

    with MetadataRepository(settings) as repo, \
            HttpClient(settings) as client, \
            ADLSContentWriter(settings) as adls:

        provider = PostgresKeywordProvider(repo.session_factory)
        records = provider.iter_keywords(tickers)
        logger.info(
            "Loaded %s keyword(s) for %s source(s).", len(records), len(source_names)
        )

        job_note = (
            f"triggered_by={triggered_by}; "
            f"sources={source_names}; "
            f"tickers={list(tickers) if tickers else 'all'}"
        )
        job_id = repo.create_crawl_job(
            crawler_version=settings.crawler_version, note=job_note
        )
        logger.info("Crawl job %s started.", job_id)

        final_status = "SUCCESS"
        try:
            for source_name in source_names:
                parser = get_parser(source_name)
                source_id = repo.ensure_source(
                    parser.name,
                    base_url=parser.base_url,
                    language=parser.default_language,
                )
                logger.info("=== Source: %s ===", source_name)

                # One shared id-set per ticker: keywords of the same ticker must
                # never re-scrape the same article.
                seen_ids_by_ticker: dict[str, set[str]] = {}

                for record in records:
                    seen_ids = seen_ids_by_ticker.setdefault(record.ticker, set())
                    started = time.monotonic()
                    try:
                        result = crawl_keyword(
                            parser=parser,
                            record=record,
                            settings=settings,
                            client=client,
                            repository=repo,
                            adls=adls,
                            source_id=source_id,
                            crawl_job_id=job_id,
                            seen_ids=seen_ids,
                        )
                        summary.keywords_processed += 1
                        summary.articles_found += result.found
                        summary.articles_persisted += result.persisted
                        summary.articles_skipped += result.skipped
                        summary.pages_crawled += result.pages
                        repo.write_crawl_log(
                            job_id=job_id,
                            source_id=source_id,
                            keyword_id=record.keyword_id,
                            status="SUCCESS",
                            duration_ms=int((time.monotonic() - started) * 1000),
                            article_found=result.found,
                        )
                    except Exception as exc:
                        logger.exception(
                            "[%s:%s] keyword '%s' failed: %s",
                            source_name,
                            record.ticker,
                            record.keyword,
                            exc,
                        )
                        summary.errors += 1
                        summary.failed.append(f"{source_name}:{record.ticker}:{record.keyword}")
                        repo.write_crawl_log(
                            job_id=job_id,
                            source_id=source_id,
                            keyword_id=record.keyword_id,
                            status="FAILED",
                            duration_ms=int((time.monotonic() - started) * 1000),
                            article_found=0,
                            error_message=str(exc),
                        )
        except KeyboardInterrupt:
            logger.warning("Pipeline interrupted by user (Ctrl+C).")
            final_status = "FAILED"
        except Exception as exc:
            logger.exception("Pipeline-level failure: %s", exc)
            final_status = "FAILED"
            summary.errors += 1
        finally:
            repo.finish_crawl_job(job_id, status=final_status, note=job_note)

    clear_log_context()
    logger.success(summary.render())
    return summary
