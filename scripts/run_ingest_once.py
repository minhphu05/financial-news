"""One-shot ingestion script (cleaning + chunking + embedding + load).

Useful when you want to re-run the pipeline manually after a fix or a
historical backfill::

    python scripts/run_ingest_once.py --max-articles 50
"""

from __future__ import annotations

import argparse
import json

from src.rag.databases import MongoRepository, PgVectorRepository
from src.rag.ingestion import GeminiEmbedder, IngestionPipeline


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ingestion pipeline once.")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Maximum number of articles to process in each stage.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = _parse_args()

    with MongoRepository() as mongo, PgVectorRepository() as pg:
        embedder = GeminiEmbedder()
        pipeline = IngestionPipeline(mongo=mongo, pgvector=pg, embedder=embedder)
        report = pipeline.run(max_articles=args.max_articles)
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
