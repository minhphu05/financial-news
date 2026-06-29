"""Prefect flow that runs the canonical financial-news scraper pipeline.

This flow delegates to :func:`src.scraper.engine.pipeline.run_pipeline`, which is
the authoritative scrape implementation that writes:

1. metadata to PostgreSQL, and
2. article JSON content to the configured content backend (ADLS by default).

Using this path keeps Prefect-triggered runs consistent with the CLI entry
point (``python -m src.scraper.run``).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger, task

from src.rag.ingestion.pipeline_logger import PipelineRunLogger
from src.scraper.config import get_settings as get_scraper_settings
from src.scraper.engine.pipeline import run_pipeline as run_scraper_pipeline


@task(retries=2, retry_delay_seconds=30)
def scrape_task(
    tickers: Optional[List[str]] = None,
    run_id: Optional[str] = None,
    source_filter: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    content_storage_backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a single scrape pass and return a JSON-friendly report.

    Emits a structured ``scrape`` event via :class:`PipelineRunLogger` so
    Fluent Bit can forward it to Loki for the Grafana scrape dashboard.

    Parameters
    ----------
    tickers : Optional[List[str]]
        Optional ticker whitelist. ``None`` means all active ticker keywords.
    run_id : Optional[str]
        Shared run identifier for correlating events across stages.
        Defaults to a new UUID if not supplied.

    Returns
    -------
    dict
        Serialisable scrape report with ``run_id`` injected.
    """
    logger = get_run_logger()
    effective_run_id = run_id or str(uuid.uuid4())
    effective_tickers = tickers if tickers is not None else keywords
    run_log = PipelineRunLogger(run_id=effective_run_id)
    settings = get_scraper_settings().with_content_storage_backend(content_storage_backend)

    summary = run_scraper_pipeline(
        settings,
        tickers=effective_tickers,
        source_filter=source_filter,
        triggered_by="prefect",
    )

    logger.info("Scrape summary: %s", summary.render())

    logged_tickers = effective_tickers or ["(all)"]
    for ticker in logged_tickers:
        run_log.scrape(
            articles_found=summary.articles_found,
            articles_persisted=summary.articles_persisted,
            duration_s=0.0,
            source="cafef",
            keyword=ticker,
        )

    return {
        "run_id": effective_run_id,
        "articles_found": summary.articles_found,
        "articles_persisted": summary.articles_persisted,
        "articles_skipped": summary.articles_skipped,
        "pages_crawled": summary.pages_crawled,
        "keywords_processed": summary.keywords_processed,
        "persisted_ids": summary.persisted_article_ids,
        "errors_count": summary.errors,
        "failed": summary.failed,
        "content_storage_backend": settings.content_storage_backend,
    }

@flow(name="financial-news-scrape", log_prints=True)
def scrape_flow(
    tickers: Optional[List[str]] = None,
    source_filter: Optional[str] = None,
    content_storage_backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Daily CafeF scrape flow.

    Parameters
    ----------
    tickers : Optional[List[str]]
        Optional ticker whitelist; ``None`` scrapes all active ticker keywords.

    Returns
    -------
    dict
        Serialised scrape report (includes ``run_id`` for downstream flows).
    """
    run_id = str(uuid.uuid4())
    return scrape_task(
        tickers=tickers,
        source_filter=source_filter,
        run_id=run_id,
        content_storage_backend=content_storage_backend,
    )
