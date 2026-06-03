"""Prefect flow that runs the cleaning + embedding pipeline."""

from __future__ import annotations

from typing import Any, Dict, Optional

from prefect import flow, get_run_logger, task

from src.rag.databases import MongoRepository, PgVectorRepository
from src.rag.ingestion import GeminiEmbedder
from src.rag.ingestion.pipeline import IngestionPipeline


@task(retries=2, retry_delay_seconds=60)
def ingest_task(max_articles: Optional[int]) -> Dict[str, Any]:
    """Execute the ingestion pipeline once.

    Parameters
    ----------
    max_articles : Optional[int]
        Safety-rail used to cap a single run.

    Returns
    -------
    dict
        Serialisable ingestion report.
    """
    logger = get_run_logger()
    with MongoRepository() as mongo, PgVectorRepository() as pg:
        embedder = GeminiEmbedder()
        pipeline = IngestionPipeline(mongo=mongo, pgvector=pg, embedder=embedder)
        report = pipeline.run(max_articles=max_articles)
        logger.info("Ingestion report: %s", report.as_dict())
    return report.as_dict()


@flow(name="vifinner-ingest", log_prints=True)
def ingest_flow(max_articles: Optional[int] = None) -> Dict[str, Any]:
    """Run the cleaning + embedding pipeline.

    Parameters
    ----------
    max_articles : Optional[int]
        Optional cap to the number of articles processed.

    Returns
    -------
    dict
        Serialised ingestion report.
    """
    return ingest_task(max_articles=max_articles)
