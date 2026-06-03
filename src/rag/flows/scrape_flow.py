"""Prefect flow that runs the daily CafeF scraper.

The flow is intentionally thin – the heavy lifting lives in
:class:`DailyCafefScraper`. Prefect handles retries, logging, and the
schedule.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger, task

from src.rag.databases import MongoRepository
from src.rag.ingestion import DailyCafefScraper


@task(retries=2, retry_delay_seconds=30)
def scrape_task(keywords: Optional[List[str]]) -> Dict[str, Any]:
    """Run a single scrape pass and return a JSON-friendly report.

    Parameters
    ----------
    keywords : Optional[List[str]]
        Optional list of keywords passed to :class:`DailyCafefScraper`.

    Returns
    -------
    dict
        Serialisable scrape report.
    """
    logger = get_run_logger()
    with MongoRepository() as repo:
        scraper = DailyCafefScraper(repo=repo)
        report = scraper.run(keywords=keywords)
        logger.info("Scrape report: %s", report.as_dict())
    return report.as_dict()


@flow(name="vifinner-scrape", log_prints=True)
def scrape_flow(keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Daily CafeF scrape flow.

    Parameters
    ----------
    keywords : Optional[List[str]]
        Keywords to scrape; ``None`` uses the configured default list.

    Returns
    -------
    dict
        Serialised scrape report.
    """
    return scrape_task(keywords=keywords)
