"""Run the LangChain ingestion pipeline once.

Reads cleaned articles from MongoDB (silver layer) and pushes embeddings
into the LangChain-managed PGVector collection (``vifinner_lc_chunks``
by default).

Usage::

    python scripts/run_langchain_ingest.py
    python scripts/run_langchain_ingest.py --max-articles 50
    python scripts/run_langchain_ingest.py --collection vifinner_lc_chunks
"""

from __future__ import annotations

import argparse
import json

from src.rag.databases import MongoRepository
from src.rag_langchain import LangChainIngestionPipeline, LangChainSettings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LangChain ingestion pipeline once.")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Cap the number of articles processed in this run.",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="PGVector collection name to write into (defaults to vifinner_lc_chunks).",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    settings = LangChainSettings.load(collection_name=args.collection)
    with MongoRepository(settings=settings.base) as mongo:
        pipeline = LangChainIngestionPipeline(mongo=mongo, settings=settings)
        report = pipeline.run(max_articles=args.max_articles)
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
