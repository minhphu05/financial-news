"""Prefect flow: medallion bronze → silver → gold ingestion.

This flow replaces the legacy :mod:`ingest_flow` for new deployments.
Each stage is wrapped in an MLflow run so the operator can compare
ingestion runs over time (rows processed, dedup ratio, chunk count,
end-to-end duration).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from prefect import flow, get_run_logger, task

from src.preprocessing.medallion import MedallionPipeline
from src.rag.config import get_settings
from src.rag.databases import MongoRepository, QdrantRepository
from src.rag.ingestion import VoyageAIEmbedder
from src.rag.mlops import MLflowTracker


@task(retries=2, retry_delay_seconds=60)
def medallion_task(max_articles: Optional[int]) -> Dict[str, Any]:
    """Run the medallion pipeline once.

    Parameters
    ----------
    max_articles : Optional[int]
        Soft cap on the number of bronze rows processed.

    Returns
    -------
    dict
        Serialised :class:`MedallionReport`.
    """
    logger = get_run_logger()
    settings = get_settings()
    tracker = MLflowTracker(experiment=settings.mlflow.experiment_medallion)

    with MongoRepository() as mongo, QdrantRepository() as qdrant:
        embedder = VoyageAIEmbedder()
        pipeline = MedallionPipeline(
            mongo=mongo,
            qdrant=qdrant,
            embedder=embedder,
            settings=settings,
        )

        with tracker.start_run(run_name="medallion") as run:
            run.log_params({"max_articles": max_articles})
            report = pipeline.run(max_articles=max_articles)
            metrics = {
                "bronze_rows": report.bronze.rows if report.bronze else 0,
                "silver_cleaned": report.silver.cleaned_rows if report.silver else 0,
                "silver_dedup_dropped": report.silver.dedup_dropped if report.silver else 0,
                "gold_articles": report.gold.articles if report.gold else 0,
                "gold_chunks": report.gold.chunks if report.gold else 0,
                "gold_written": report.gold.written if report.gold else 0,
            }
            run.log_metrics(metrics)
            run.log_dict(report.as_dict(), name="medallion_report.json")

    logger.info("Medallion stats: %s", report.as_dict())
    return report.as_dict()


@flow(name="vifinner-medallion", log_prints=True)
def medallion_flow(max_articles: Optional[int] = None) -> Dict[str, Any]:
    """Run bronze → silver → gold ingestion.

    Parameters
    ----------
    max_articles : Optional[int]
        Optional cap to process only N bronze rows in one run.

    Returns
    -------
    dict
        Aggregated medallion report.
    """
    return medallion_task(max_articles=max_articles)
