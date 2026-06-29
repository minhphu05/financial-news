"""Prefect flows for the standard scraper schedule.

Standard flow:

1. Scrape Vietstock HOSE/HNX metrics plus VN30/HNX30 memberships.
2. Generate and persist 5 LLM keywords only for tickers missing active keywords.
3. Scrape implemented financial-news sources; article JSON content is written to the configured content backend.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger, task

from src.flows.scrape_flow import scrape_task
from src.scraper.keyword_generation.gemini_keyword_generator import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT,
    DEFAULT_RPM,
    DEFAULT_TPM,
    generate_keywords,
    load_index_tickers_from_postgres,
    persist_keyword_items,
    filter_tickers_missing_keywords,
    write_output,
)
from src.scraper.vietstock.vietstock_scraper import (
    STANDARD_FLOW_EXCHANGES,
    persist_to_postgres,
    scrape_exchanges,
)


@task(retries=2, retry_delay_seconds=60)
def market_data_task(
    session_note: Optional[str] = None,
    is_eod: bool = False,
    render: str = "auto",
    browser_engine: str = "auto",
    timeout: int = 30,
) -> Dict[str, Any]:
    """Scrape and persist HOSE/HNX metrics plus VN30/HNX30 memberships."""
    logger = get_run_logger()
    frames = scrape_exchanges(
        STANDARD_FLOW_EXCHANGES,
        timeout=timeout,
        render=render,
        browser_engine=browser_engine,
        progress=False,
    )
    persist_to_postgres(
        frames,
        session_note=session_note,
        is_eod=is_eod,
        triggered_by="prefect",
    )
    rows_by_exchange = {exchange: len(frame) for exchange, frame in frames.items()}
    logger.info("Vietstock persisted rows: %s", rows_by_exchange)
    return {
        "exchanges": list(frames),
        "rows_by_exchange": rows_by_exchange,
        "rows_total": sum(rows_by_exchange.values()),
    }


@task(retries=1, retry_delay_seconds=120)
def missing_keyword_task(
    output: str = str(DEFAULT_OUTPUT),
    model: str = DEFAULT_MODEL,
    rpm: int = DEFAULT_RPM,
    tpm: int = DEFAULT_TPM,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    """Generate and persist keywords for VN30/HNX30 tickers that need them."""
    logger = get_run_logger()
    tickers = filter_tickers_missing_keywords(load_index_tickers_from_postgres())
    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parents[2] / output_path

    if not tickers:
        write_output([], output_path, model=model)
        logger.info("No missing keyword tickers. Wrote empty audit file: %s", output_path)
        return {"tickers_generated": 0, "keywords_persisted": 0, "output": str(output_path)}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is empty. Set it before running keyword generation.")

    items = generate_keywords(
        tickers,
        api_key=api_key,
        model=model,
        rpm=rpm,
        tpm=tpm,
        batch_size=batch_size,
    )
    write_output(items, output_path, model=model)
    keywords_persisted = persist_keyword_items(items)
    logger.info("Persisted %d generated keyword(s) for %d ticker(s).", keywords_persisted, len(items))
    return {
        "tickers_generated": len(items),
        "keywords_persisted": keywords_persisted,
        "output": str(output_path),
    }


@flow(name="financial-news-market-data", log_prints=True)
def market_data_flow(
    session_note: Optional[str] = None,
    is_eod: bool = False,
    render: str = "auto",
    browser_engine: str = "auto",
) -> Dict[str, Any]:
    return market_data_task(
        session_note=session_note,
        is_eod=is_eod,
        render=render,
        browser_engine=browser_engine,
    )


@flow(name="financial-news-standard-scraper", log_prints=True)
def standard_scraper_flow(
    tickers: Optional[List[str]] = None,
    source_filter: Optional[str] = None,
    skip_market_data: bool = False,
    skip_keyword_generation: bool = False,
    content_storage_backend: Optional[str] = None,
) -> Dict[str, Any]:
    logger = get_run_logger()
    run_id = str(uuid.uuid4())
    logger.info("Starting standard scraper flow (run_id=%s).", run_id)

    market_report: Dict[str, Any] = {"skipped": True}
    if not skip_market_data:
        market_report = market_data_task(session_note="AFTERNOON", is_eod=False)

    keyword_report: Dict[str, Any] = {"skipped": True}
    if not skip_keyword_generation:
        keyword_report = missing_keyword_task()

    news_report = scrape_task(
        tickers=tickers,
        source_filter=source_filter,
        run_id=run_id,
        content_storage_backend=content_storage_backend,
    )
    return {
        "run_id": run_id,
        "market_data": market_report,
        "keyword_generation": keyword_report,
        "news": news_report,
    }