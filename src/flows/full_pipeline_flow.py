"""Composed Prefect flow: scrape → detect new → chunk → embed → Qdrant.

This is the primary orchestrator for the daily pipeline.  It:

1. Scrapes CafeF for every configured keyword/ticker.
2. Collects the ``news_id`` of every newly persisted article.
3. Passes those IDs directly to the ingestion pipeline (no implicit
   MongoDB set-difference queries — clean, explicit data flow).

The pipeline runs sequentially within a single flow run, generating a
shared ``run_id`` (UUID) for end-to-end observability in Grafana/Loki.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger, task

from src.flows.scrape_flow import scrape_task
from src.pipeline.core import run_ingestion
from src.rag.config import get_settings
from src.rag.databases import MongoRepository, QdrantRepository
from src.rag.ingestion import VoyageAIEmbedder


@task(retries=1, retry_delay_seconds=60)
def ingest_new_task(
    news_ids: List[str],
    run_id: str,
    max_articles: Optional[int] = None,
) -> Dict[str, Any]:
    """Chunk, embed, and store only the newly scraped articles.

    Parameters
    ----------
    news_ids : list[str]
        ``news_id`` values returned by the preceding scrape step.
    run_id : str
        Shared run identifier for correlating structured log events.
    max_articles : Optional[int]
        Safety cap (if >0, limits processing to the first N IDs).

    Returns
    -------
    dict
        Serialised :class:`~src.pipeline.core.IngestionReport`.
    """
    logger = get_run_logger()
    settings = get_settings()

    target_ids = news_ids
    if max_articles is not None and max_articles > 0:
        target_ids = news_ids[:max_articles]

    logger.info(
        "Ingesting %d / %d new article(s) (run_id=%s).",
        len(target_ids),
        len(news_ids),
        run_id,
    )

    if not target_ids:
        logger.info("No new articles to ingest.")
        return {
            "cleaned": 0,
            "embedded": 0,
            "chunks_written": 0,
            "failed_ids": [],
        }

    with MongoRepository(settings=settings) as mongo, \
         QdrantRepository(settings=settings) as qdrant:
        embedder = VoyageAIEmbedder(settings=settings)
        report = run_ingestion(
            mongo=mongo,
            qdrant=qdrant,
            embedder=embedder,
            news_ids=target_ids,
            settings=settings,
            run_id=run_id,
        )

    logger.info("Ingestion report: %s", report.as_dict())
    return report.as_dict()


@flow(name="financial-news-full-pipeline", log_prints=True)
def full_pipeline_flow(
    keywords: Optional[List[str]] = None,
    max_articles: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the full daily pipeline: scrape → clean → chunk → embed → Qdrant.

    Newly scraped articles are detected by their ``news_id`` and processed
    immediately — no backlogs, no re-processing of already-embedded articles.

    Parameters
    ----------
    keywords : Optional[List[str]]
        Keywords to scrape. ``None`` uses the configured default list.
    max_articles : Optional[int]
        Optional safety cap for the ingestion stage (number of articles).

    Returns
    -------
    dict
        ``{"run_id": ..., "scrape": <report>, "ingest": <report>}``.
    """
    logger = get_run_logger()
    run_id = str(uuid.uuid4())
    logger.info("Starting full pipeline (run_id=%s).", run_id)

    # Stage 1: Scrape financial news → PostgreSQL (metadata) + MongoDB (content).
    scrape_report = scrape_task(keywords=keywords, run_id=run_id)

    # Stage 2: Detect new articles and process them.
    persisted_ids: List[str] = scrape_report.get("persisted_ids", [])
    logger.info(
        "Scrape complete: %d new / %d total articles.",
        len(persisted_ids),
        scrape_report.get("articles_found", 0),
    )

    ingest_report = ingest_new_task(
        news_ids=persisted_ids,
        run_id=run_id,
        max_articles=max_articles,
    )

    logger.info(
        "Pipeline complete (run_id=%s): scraped=%d, ingested=%d.",
        run_id,
        len(persisted_ids),
        ingest_report.get("cleaned", 0),
    )

    return {"run_id": run_id, "scrape": scrape_report, "ingest": ingest_report}
