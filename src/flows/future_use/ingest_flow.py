"""Prefect flow that runs the cleaning + embedding pipeline.

This flow accepts an explicit list of ``news_id`` values to process,
making the data flow from the scrape step fully transparent.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger, task

from src.pipeline.core import run_ingestion
from src.rag.config import get_settings
from src.rag.databases import MongoRepository, QdrantRepository
from src.rag.ingestion import VoyageAIEmbedder


@task(retries=2, retry_delay_seconds=60)
def ingest_task(
    news_ids: List[str],
    max_articles: Optional[int] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Chunk, embed, and store the specified articles.

    Parameters
    ----------
    news_ids : list[str]
        ``news_id`` values of articles to process (from the scrape step).
    max_articles : Optional[int]
        Safety-rail used to cap a single run (limits to first N IDs).
    run_id : Optional[str]
        Shared run identifier for correlating structured log events.

    Returns
    -------
    dict
        Serialised ``IngestionReport``.
    """
    logger = get_run_logger()
    effective_run_id = run_id or str(uuid.uuid4())
    settings = get_settings()

    target_ids = news_ids
    if max_articles is not None and max_articles > 0:
        target_ids = news_ids[:max_articles]

    if not target_ids:
        logger.info("No news_ids provided; skipping ingestion.")
        return {"cleaned": 0, "embedded": 0, "chunks_written": 0, "failed_ids": []}

    logger.info(
        "Ingesting %d article(s) (run_id=%s).",
        len(target_ids),
        effective_run_id,
    )

    with MongoRepository(settings=settings) as mongo, \
         QdrantRepository(settings=settings) as qdrant:
        embedder = VoyageAIEmbedder(settings=settings)
        report = run_ingestion(
            mongo=mongo,
            qdrant=qdrant,
            embedder=embedder,
            news_ids=target_ids,
            settings=settings,
            run_id=effective_run_id,
        )
        logger.info("Ingestion report: %s", report.as_dict())

    result = report.as_dict()
    result["run_id"] = effective_run_id
    return result


@flow(name="financial-news-ingest", log_prints=True)
def ingest_flow(
    news_ids: Optional[List[str]] = None,
    max_articles: Optional[int] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the cleaning + embedding pipeline for specific articles.

    Parameters
    ----------
    news_ids : Optional[list[str]]
        Article IDs to process. When ``None``, the flow falls back to
        the implicit backlog query (all unprocessed articles).
    max_articles : Optional[int]
        Optional cap to the number of articles processed.
    run_id : Optional[str]
        Optional run correlation ID (generated if absent).

    Returns
    -------
    dict
        Serialised ingestion report.
    """
    if news_ids:
        return ingest_task(news_ids=news_ids, max_articles=max_articles, run_id=run_id)

    # Fallback: process the implicit backlog (backward compatible).
    logger = get_run_logger()
    logger.info("No news_ids provided; falling back to backlog ingestion.")

    from src.rag.ingestion.pipeline import IngestionPipeline

    effective_run_id = run_id or str(uuid.uuid4())
    settings = get_settings()
    with MongoRepository(settings=settings) as mongo, \
         QdrantRepository(settings=settings) as qdrant:
        embedder = VoyageAIEmbedder(settings=settings)
        pipeline = IngestionPipeline(
            mongo=mongo,
            qdrant=qdrant,
            embedder=embedder,
            settings=settings,
            run_id=effective_run_id,
        )
        report = pipeline.run(max_articles=max_articles)
        logger.info("Backlog ingestion report: %s", report.as_dict())

    result = report.as_dict()
    result["run_id"] = effective_run_id
    return result
