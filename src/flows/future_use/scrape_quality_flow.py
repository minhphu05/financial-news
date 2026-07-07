"""Prefect flow: scrape → Pydantic quality gate → MongoDB bronze.

Compared to :mod:`scrape_flow`, this flow runs raw scraper output
through :func:`validate_articles` before persisting it. Rejected
documents land in ``cafef_rejected`` for later inspection so we get a
permanent audit trail of every quality failure.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger, task

from src.rag.databases import MongoRepository
from src.rag.ingestion import DailyCafefScraper
from src.rag.quality import QualityReport, validate_articles


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@task(retries=2, retry_delay_seconds=30)
def scrape_articles_task(keywords: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Run the daily scraper and return the freshly inserted articles."""
    logger = get_run_logger()
    raw: List[Dict[str, Any]] = []
    with MongoRepository() as repo:
        scraper = DailyCafefScraper(repo=repo)
        report = scraper.run(keywords=keywords)
        logger.info("Scrape stats: %s", report.as_dict())

        if report.articles_inserted:
            # Pull a window slightly larger than the insert count to be safe
            # against concurrent writes.
            raw = list(repo.iter_recent_raw(limit=min(report.articles_inserted * 2, 500)))
    return raw


@task
def quality_gate_task(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate scraped articles and persist rejections.

    Returns a JSON-serialisable summary suitable for logs and MLflow.
    """
    logger = get_run_logger()
    if not articles:
        return QualityReport().as_dict()

    report = validate_articles(articles)
    logger.info(
        "Quality gate: %d valid / %d rejected (pass_rate=%.2f)",
        len(report.valid),
        len(report.rejections),
        report.pass_rate,
    )

    if report.rejections:
        with MongoRepository() as repo:
            repo.save_rejections(
                {"link": r.link, "errors": r.errors, "payload": r.payload}
                for r in report.rejections
            )

    return report.as_dict()


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------
@flow(name="vifinner-scrape-quality", log_prints=True)
def scrape_quality_flow(keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Daily scrape with a Pydantic quality gate.

    Parameters
    ----------
    keywords : Optional[List[str]]
        Optional keyword override.

    Returns
    -------
    dict
        Quality report (rejection counts + samples) as JSON.
    """
    raw = scrape_articles_task(keywords=keywords)
    return quality_gate_task(articles=raw)
