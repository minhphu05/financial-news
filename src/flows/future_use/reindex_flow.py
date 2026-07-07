"""Prefect flow that deletes all Qdrant vectors and re-chunks from scratch.

This flow is used when the chunking strategy changes or when a full
re-index is needed. It:

1. Deletes all points in the Qdrant collection (drop + recreate).
2. Resets the ``embedded_at`` field on all clean articles in MongoDB.
3. Runs the embedding stage to re-chunk and re-embed every clean article.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from prefect import flow, get_run_logger, task

from src.rag.databases import MongoRepository, QdrantRepository
from src.rag.ingestion import VoyageAIEmbedder
from src.rag.ingestion.pipeline import IngestionPipeline


@task(name="delete-qdrant-vectors", retries=1)
def delete_qdrant_vectors_task() -> int:
    """Delete all vectors in Qdrant and return the previous count."""
    logger = get_run_logger()
    with QdrantRepository() as qdrant:
        stats = qdrant.stats()
        prev_count = stats["chunk_count"]
        logger.info("Deleting %d existing chunks from Qdrant.", prev_count)
        qdrant.delete_all_points()
    return prev_count


@task(name="reset-embedded-flags", retries=1)
def reset_embedded_flags_task() -> int:
    """Remove embedded_at from all clean articles so they get re-embedded."""
    with MongoRepository() as mongo:
        return mongo.reset_all_embedded()


@task(name="reindex-embed", retries=2, retry_delay_seconds=60)
def reindex_embed_task(max_articles: Optional[int]) -> Dict[str, Any]:
    """Run the ingestion pipeline (embed stage only since all are reset)."""
    with MongoRepository() as mongo, QdrantRepository() as qdrant:
        embedder = VoyageAIEmbedder()
        pipeline = IngestionPipeline(mongo=mongo, qdrant=qdrant, embedder=embedder)
        report = pipeline.run(max_articles=max_articles)
    return report.as_dict()


@flow(name="vifinner-reindex", log_prints=True)
def reindex_flow(max_articles: Optional[int] = None) -> Dict[str, Any]:
    """Full re-index: delete vectors → reset flags → re-embed.

    Parameters
    ----------
    max_articles : Optional[int]
        Optional cap on re-embedding (useful for testing).

    Returns
    -------
    dict
        Summary with previous count, reset count, and ingestion report.
    """
    logger = get_run_logger()

    prev_count = delete_qdrant_vectors_task()
    reset_count = reset_embedded_flags_task()
    logger.info("Reset %d articles for re-embedding (was %d chunks).", reset_count, prev_count)

    report = reindex_embed_task(max_articles=max_articles)
    logger.info("Re-index complete: %s", report)

    return {
        "previous_chunk_count": prev_count,
        "articles_reset": reset_count,
        "ingestion": report,
    }
