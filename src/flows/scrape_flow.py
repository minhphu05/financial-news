"""Prefect flow that runs the canonical financial-news scraper pipeline.

This flow delegates to :func:`src.scraper.pipeline.run_pipeline`, which is
the authoritative scrape implementation that writes:

1. metadata to PostgreSQL, and
2. article content to MongoDB.

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
    keywords: Optional[List[str]],
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a single scrape pass and return a JSON-friendly report.

    Emits a structured ``scrape`` event via :class:`PipelineRunLogger` so
    Fluent Bit can forward it to Loki for the Grafana scrape dashboard.

    Parameters
    ----------
    keywords : Optional[List[str]]
        Optional list of keywords passed to :class:`DailyCafefScraper`.
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
    run_log = PipelineRunLogger(run_id=effective_run_id)
    settings = get_scraper_settings()

    # ``keywords`` is kept for backward compatibility with the previous flow
    # signature, but operationally we treat it as an optional ticker whitelist.
    summary = run_scraper_pipeline(
        settings,
        only_tickers=keywords,
        triggered_by="prefect",
    )

    logger.info("Scrape summary: %s", summary.render())

    effective_keywords = keywords or ["(all)"]
    for kw in effective_keywords:
        run_log.scrape(
            articles_found=summary.articles_found,
            articles_persisted=summary.articles_persisted,
            duration_s=0.0,
            source="cafef",
            keyword=kw,
        )

    return {
        "run_id": effective_run_id,
        "articles_found": summary.articles_found,
        "articles_persisted": summary.articles_persisted,
        "articles_skipped": summary.articles_skipped,
        "pages_crawled": summary.pages_crawled,
        "errors_count": summary.errors_count,
        "tickers_processed": summary.tickers_processed,
        "keywords_processed": summary.keywords_processed,
        "failed_keywords": summary.failed_keywords,
        "persisted_ids": summary.persisted_ids,
    }

@flow(name="financial-news-scrape", log_prints=True)
def scrape_flow(keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Daily CafeF scrape flow.

    Parameters
    ----------
    keywords : Optional[List[str]]
        Keywords to scrape; ``None`` uses the configured default list.

    Returns
    -------
    dict
        Serialised scrape report (includes ``run_id`` for downstream flows).
    """
    run_id = str(uuid.uuid4())
    return scrape_task(keywords=keywords, run_id=run_id)
