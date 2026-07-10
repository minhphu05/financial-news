"""
End-to-end scrape orchestration.

Flow per run:

1. Open PostgreSQL (metadata) and ADLS (content) connections.
2. Register a ``scraping.crawl_jobs`` row.
3. Load ``(stock, keyword)`` pairs from the input provider (PostgreSQL).
4. For every selected source x keyword, run the generic crawler.
5. Record a ``scraping.crawl_logs`` row per keyword and finalize the crawl job.

Handles Ctrl+C gracefully — the crawl job is always finalized.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from src.scraper.storage.adls_writer import create_content_writer
from src.scraper.config import ScraperSettings
from src.scraper.engine.crawler import crawl_keyword
from src.scraper.http_client import HttpClient
from src.scraper.metrics import push_scraper_metrics
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
    persisted_article_ids: List[str] = field(default_factory=list)
    pages_crawled: int = 0
    errors: int = 0
    keywords_skipped_checkpoint: int = 0
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
            f"  checkpoint skipped  : {self.keywords_skipped_checkpoint}\n"
            f"  errors              : {self.errors}"
            + ("" if not self.failed else f"\n  failed -> {self.failed}")
        )


def run_pipeline(
    settings: ScraperSettings,
    *,
    tickers: Optional[Sequence[str]] = None,
    source_filter: Optional[str] = None,
    triggered_by: str = "manual",
    max_keywords_per_ticker: Optional[int] = None,
    resume_from_checkpoint: bool = True,
    checkpoint_key: Optional[str] = None,
) -> RunSummary:
    """Execute the full scrape across selected sources and tickers."""
    source_names = resolve_sources(source_filter)
    summary = RunSummary(sources=source_names)
    effective_checkpoint_key = checkpoint_key or _default_checkpoint_key(
        source_names=source_names,
        tickers=tickers,
        max_keywords_per_ticker=max_keywords_per_ticker,
        max_pages=settings.max_pages,
    )

    with MetadataRepository(settings) as repo, \
            HttpClient(settings) as client, \
            create_content_writer(settings) as adls:

        provider = PostgresKeywordProvider(repo.session_factory)
        records = provider.iter_keywords(tickers)
        if max_keywords_per_ticker is not None:
            records = _limit_keywords_per_ticker(records, max_keywords_per_ticker)
        logger.info(
            "Loaded %s keyword(s) for %s source(s).", len(records), len(source_names)
        )

        parsers_by_source = {}
        source_ids_by_source = {}
        for source_name in source_names:
            parser = get_parser(source_name)
            parsers_by_source[source_name] = parser
            source_ids_by_source[source_name] = repo.ensure_source(
                parser.name,
                base_url=parser.base_url,
                language=parser.default_language,
            )

        job_source_id = (
            source_ids_by_source[source_names[0]] if len(source_names) == 1 else None
        )

        job_note = (
            f"triggered_by={triggered_by}; "
            f"sources={source_names}; "
            f"tickers={list(tickers) if tickers else 'all'}; "
            f"max_keywords_per_ticker={max_keywords_per_ticker or 'all'}; "
            f"resume_from_checkpoint={resume_from_checkpoint}; "
            f"checkpoint_key={effective_checkpoint_key}"
        )
        job_id = repo.create_crawl_job(
            crawler_version=settings.crawler_version,
            note=job_note,
            job_name="financial-news scrape",
            job_type="NEWS",
            source_id=job_source_id,
        )
        logger.info("Crawl job %s started.", job_id)

        final_status = "SUCCESS"
        try:
            for source_name in source_names:
                parser = parsers_by_source[source_name]
                source_id = source_ids_by_source[source_name]
                source_summary = RunSummary(sources=[source_name])
                source_started = time.monotonic()
                source_error_breakdown: dict[str, int] = {}
                logger.info("=== Source: %s ===", source_name)
                _push_source_metrics(
                    source_name=source_name,
                    source_summary=source_summary,
                    source_started=source_started,
                    total_keywords=len(records),
                    run_active=1,
                )

                # One shared id-set per ticker: keywords of the same ticker must
                # never re-scrape the same article.
                seen_ids_by_ticker: dict[str, set[str]] = {}

                for record in records:
                    seen_ids = seen_ids_by_ticker.setdefault(record.ticker, set())
                    checkpoint = None
                    start_page = settings.start_page
                    if resume_from_checkpoint:
                        checkpoint = repo.get_scrape_checkpoint(
                            source_name=source_name,
                            ticker=record.ticker,
                            keyword=record.keyword,
                            run_key=effective_checkpoint_key,
                        )
                        if checkpoint and checkpoint.get("status") == "COMPLETED":
                            summary.keywords_processed += 1
                            summary.keywords_skipped_checkpoint += 1
                            source_summary.keywords_processed += 1
                            source_summary.keywords_skipped_checkpoint += 1
                            logger.info(
                                "Checkpoint skip: source=%s ticker=%s keyword=%s run_key=%s",
                                source_name,
                                record.ticker,
                                record.keyword,
                                effective_checkpoint_key,
                                extra={
                                    "event": "checkpoint_skip",
                                    "checkpoint_key": effective_checkpoint_key,
                                    "source_name": source_name,
                                    "ticker_symbol": record.ticker,
                                    "keyword": record.keyword,
                                },
                            )
                            _push_source_metrics(
                                source_name=source_name,
                                source_summary=source_summary,
                                source_started=source_started,
                                total_keywords=len(records),
                                run_active=1,
                                current_ticker=record.ticker,
                                current_keyword=record.keyword,
                                last_keyword_status="checkpoint_skip",
                                error_breakdown=source_error_breakdown,
                            )
                            continue
                        if checkpoint:
                            last_page_completed = int(checkpoint.get("last_page_completed") or 0)
                            if last_page_completed >= settings.start_page:
                                start_page = min(settings.max_pages, last_page_completed + 1)
                                logger.info(
                                    "Checkpoint resume: source=%s ticker=%s keyword=%s page=%s run_key=%s previous_status=%s",
                                    source_name,
                                    record.ticker,
                                    record.keyword,
                                    start_page,
                                    effective_checkpoint_key,
                                    checkpoint.get("status"),
                                )

                    if resume_from_checkpoint:
                        repo.start_scrape_checkpoint(
                            source_name=source_name,
                            ticker=record.ticker,
                            keyword=record.keyword,
                            keyword_id=record.keyword_id,
                            run_key=effective_checkpoint_key,
                        )

                    target_url = parser.build_search_url(record.keyword, start_page)
                    started = time.monotonic()
                    try:
                        last_page_completed = max(0, start_page - 1)

                        def update_checkpoint(page: int, partial_result) -> None:
                            nonlocal last_page_completed
                            last_page_completed = page
                            if resume_from_checkpoint:
                                repo.update_scrape_checkpoint_progress(
                                    source_name=source_name,
                                    ticker=record.ticker,
                                    keyword=record.keyword,
                                    run_key=effective_checkpoint_key,
                                    last_page_completed=page,
                                    pages_crawled=partial_result.pages,
                                    articles_found=partial_result.found,
                                    articles_persisted=partial_result.persisted,
                                    articles_skipped=partial_result.skipped,
                                )

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
                            start_page=start_page,
                            on_page_complete=update_checkpoint,
                        )
                        summary.keywords_processed += 1
                        summary.articles_found += result.found
                        summary.articles_persisted += result.persisted
                        summary.articles_skipped += result.skipped
                        summary.persisted_article_ids.extend(result.persisted_article_ids)
                        summary.pages_crawled += result.pages
                        source_summary.keywords_processed += 1
                        source_summary.articles_found += result.found
                        source_summary.articles_persisted += result.persisted
                        source_summary.articles_skipped += result.skipped
                        source_summary.persisted_article_ids.extend(result.persisted_article_ids)
                        source_summary.pages_crawled += result.pages
                        if result.error is not None:
                            summary.errors += 1
                            source_summary.errors += 1
                            source_error_breakdown[result.error] = source_error_breakdown.get(result.error, 0) + 1
                            summary.failed.append(f"{source_name}:{record.ticker}:{record.keyword}:{result.error}")
                            if resume_from_checkpoint:
                                repo.fail_scrape_checkpoint(
                                    source_name=source_name,
                                    ticker=record.ticker,
                                    keyword=record.keyword,
                                    run_key=effective_checkpoint_key,
                                    error_category=result.error,
                                    error_message=result.error,
                                    errors_count=source_summary.errors,
                                    last_page_completed=last_page_completed,
                                    pages_crawled=result.pages,
                                    articles_found=result.found,
                                    articles_persisted=result.persisted,
                                    articles_skipped=result.skipped,
                                )
                        elif resume_from_checkpoint:
                            repo.complete_scrape_checkpoint(
                                source_name=source_name,
                                ticker=record.ticker,
                                keyword=record.keyword,
                                run_key=effective_checkpoint_key,
                                last_page_completed=last_page_completed,
                                pages_crawled=result.pages,
                                articles_found=result.found,
                                articles_persisted=result.persisted,
                                articles_skipped=result.skipped,
                            )
                        repo.write_crawl_log(
                            job_id=job_id,
                            target_url=target_url,
                            response_time_ms=int((time.monotonic() - started) * 1000),
                            is_success=result.error is None,
                            error_category=result.error,
                            error_message=result.error,
                        )
                        keyword_duration = time.monotonic() - started
                        logger.info(
                            "Keyword completed: source=%s ticker=%s keyword=%s found=%s persisted=%s skipped=%s pages=%s status=%s",
                            source_name,
                            record.ticker,
                            record.keyword,
                            result.found,
                            result.persisted,
                            result.skipped,
                            result.pages,
                            "error" if result.error else "success",
                            extra={
                                "event": "keyword_completed",
                                "crawl_job_id": str(job_id),
                                "articles_found": result.found,
                                "articles_persisted": result.persisted,
                                "articles_skipped": result.skipped,
                                "pages_crawled": result.pages,
                                "duration_s": round(keyword_duration, 3),
                                "status": "error" if result.error else "success",
                                "error_category": result.error,
                            },
                        )
                        _push_source_metrics(
                            source_name=source_name,
                            source_summary=source_summary,
                            source_started=source_started,
                            total_keywords=len(records),
                            run_active=1,
                            current_ticker=record.ticker,
                            current_keyword=record.keyword,
                            last_keyword_status="error" if result.error else "success",
                            last_keyword_duration_seconds=keyword_duration,
                            last_keyword_articles_found=result.found,
                            last_keyword_articles_persisted=result.persisted,
                            last_keyword_articles_skipped=result.skipped,
                            last_keyword_pages_crawled=result.pages,
                            error_breakdown=source_error_breakdown,
                        )
                    except Exception as exc:
                        logger.exception(
                            "[%s:%s] keyword '%s' failed: %s",
                            source_name,
                            record.ticker,
                            record.keyword,
                            exc,
                        )
                        summary.keywords_processed += 1
                        summary.errors += 1
                        summary.failed.append(f"{source_name}:{record.ticker}:{record.keyword}")
                        source_summary.keywords_processed += 1
                        source_summary.errors += 1
                        source_error_breakdown["PARSE_ERROR"] = source_error_breakdown.get("PARSE_ERROR", 0) + 1
                        repo.write_crawl_log(
                            job_id=job_id,
                            target_url=target_url,
                            response_time_ms=int((time.monotonic() - started) * 1000),
                            is_success=False,
                            error_category="PARSE_ERROR",
                            error_message=str(exc),
                        )
                        if resume_from_checkpoint:
                            repo.fail_scrape_checkpoint(
                                source_name=source_name,
                                ticker=record.ticker,
                                keyword=record.keyword,
                                run_key=effective_checkpoint_key,
                                error_category="PARSE_ERROR",
                                error_message=str(exc),
                                errors_count=source_summary.errors,
                            )
                        keyword_duration = time.monotonic() - started
                        logger.info(
                            "Keyword completed: source=%s ticker=%s keyword=%s found=0 persisted=0 skipped=0 pages=0 status=error",
                            source_name,
                            record.ticker,
                            record.keyword,
                            extra={
                                "event": "keyword_completed",
                                "crawl_job_id": str(job_id),
                                "articles_found": 0,
                                "articles_persisted": 0,
                                "articles_skipped": 0,
                                "pages_crawled": 0,
                                "duration_s": round(keyword_duration, 3),
                                "status": "error",
                                "error_category": "PARSE_ERROR",
                            },
                        )
                        _push_source_metrics(
                            source_name=source_name,
                            source_summary=source_summary,
                            source_started=source_started,
                            total_keywords=len(records),
                            run_active=1,
                            current_ticker=record.ticker,
                            current_keyword=record.keyword,
                            last_keyword_status="error",
                            last_keyword_duration_seconds=keyword_duration,
                            last_keyword_articles_found=0,
                            last_keyword_articles_persisted=0,
                            last_keyword_articles_skipped=0,
                            last_keyword_pages_crawled=0,
                            error_breakdown=source_error_breakdown,
                        )
                _push_source_metrics(
                    source_name=source_name,
                    source_summary=source_summary,
                    source_started=source_started,
                    total_keywords=len(records),
                    run_active=0,
                    error_breakdown=source_error_breakdown,
                )
        except KeyboardInterrupt:
            logger.warning("Pipeline interrupted by user (Ctrl+C).")
            final_status = "FAILED"
        except Exception as exc:
            logger.exception("Pipeline-level failure: %s", exc)
            final_status = "FAILED"
            summary.errors += 1
        finally:
            if summary.errors and final_status == "SUCCESS":
                final_status = "FAILED"
            repo.finish_crawl_job(
                job_id,
                status=final_status,
                note=job_note,
                total_requests=summary.keywords_processed,
                success_requests=max(0, summary.keywords_processed - summary.errors),
                failed_requests=summary.errors,
                items_extracted=summary.articles_persisted,
            )

    clear_log_context()
    logger.success(summary.render())
    return summary


def _default_checkpoint_key(
    *,
    source_names: Sequence[str],
    tickers: Optional[Sequence[str]],
    max_keywords_per_ticker: Optional[int],
    max_pages: int,
) -> str:
    """Build a deterministic daily resume scope for manual and scheduled retries."""
    today = datetime.now(timezone.utc).date().isoformat()
    source_part = ",".join(sorted(source_names))
    ticker_part = "all" if not tickers else ",".join(sorted(t.upper() for t in tickers))
    keyword_part = str(max_keywords_per_ticker) if max_keywords_per_ticker else "all"
    return f"{today}|sources={source_part}|tickers={ticker_part}|max_keywords={keyword_part}|max_pages={max_pages}"


def _push_source_metrics(
    *,
    source_name: str,
    source_summary: RunSummary,
    source_started: float,
    total_keywords: int,
    run_active: int,
    current_ticker: Optional[str] = None,
    current_keyword: Optional[str] = None,
    last_keyword_status: Optional[str] = None,
    last_keyword_duration_seconds: Optional[float] = None,
    last_keyword_articles_found: Optional[int] = None,
    last_keyword_articles_persisted: Optional[int] = None,
    last_keyword_articles_skipped: Optional[int] = None,
    last_keyword_pages_crawled: Optional[int] = None,
    error_breakdown: Optional[dict[str, int]] = None,
) -> None:
    """Push source-level progress so Grafana updates during long scrape runs."""
    push_scraper_metrics(
        articles_found=source_summary.articles_found,
        articles_new=source_summary.articles_persisted,
        articles_skipped=source_summary.articles_skipped,
        pages_crawled=source_summary.pages_crawled,
        errors_count=source_summary.errors,
        duration_seconds=time.monotonic() - source_started,
        source=source_name,
        error_breakdown=error_breakdown,
        run_active=run_active,
        keywords_total=total_keywords,
        keywords_processed=source_summary.keywords_processed,
        current_ticker=current_ticker,
        current_keyword=current_keyword,
        last_keyword_status=last_keyword_status,
        last_keyword_duration_seconds=last_keyword_duration_seconds,
        last_keyword_articles_found=last_keyword_articles_found,
        last_keyword_articles_persisted=last_keyword_articles_persisted,
        last_keyword_articles_skipped=last_keyword_articles_skipped,
        last_keyword_pages_crawled=last_keyword_pages_crawled,
    )


def _limit_keywords_per_ticker(records, max_keywords_per_ticker: int):
    """Keep only the first N active keywords for each ticker, preserving order."""
    if max_keywords_per_ticker < 1:
        raise ValueError("max_keywords_per_ticker must be greater than zero.")

    counts: dict[str, int] = {}
    limited = []
    for record in records:
        ticker = record.ticker.upper()
        count = counts.get(ticker, 0)
        if count >= max_keywords_per_ticker:
            continue
        limited.append(record)
        counts[ticker] = count + 1
    return limited
