"""Composed Prefect flow: scrape then ingest."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger

from src.rag.flows.ingest_flow import ingest_task
from src.rag.flows.scrape_flow import scrape_task


@flow(name="vifinner-full-pipeline", log_prints=True)
def full_pipeline_flow(
    keywords: Optional[List[str]] = None,
    max_articles: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the full daily pipeline: scrape → clean → chunk → embed.

    Parameters
    ----------
    keywords : Optional[List[str]]
        Keywords to scrape.
    max_articles : Optional[int]
        Optional cap to the ingestion stage.

    Returns
    -------
    dict
        ``{"scrape": <report>, "ingest": <report>}``.
    """
    logger = get_run_logger()
    logger.info("Starting full pipeline.")

    scrape_report = scrape_task(keywords=keywords)
    ingest_report = ingest_task(max_articles=max_articles)

    return {"scrape": scrape_report, "ingest": ingest_report}
