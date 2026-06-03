"""Run the medallion pipeline (bronze → silver → gold) once.

Useful for historical backfills and local debugging::

    python scripts/run_medallion_once.py --max-articles 50
"""

from __future__ import annotations

import argparse
import json

from src.preprocessing.medallion import MedallionPipeline
from src.rag.databases import MongoRepository, PgVectorRepository
from src.rag.ingestion import GeminiEmbedder


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the medallion pipeline once.")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Maximum number of bronze articles to ingest in this run.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = _parse_args()
    with MongoRepository() as mongo, PgVectorRepository() as pg:
        pipeline = MedallionPipeline(
            mongo=mongo, pgvector=pg, embedder=GeminiEmbedder()
        )
        report = pipeline.run(max_articles=args.max_articles)
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
