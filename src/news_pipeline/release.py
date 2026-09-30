"""Small local-release maintenance commands.

These commands initialize or remove serving state.  They never contain data
transformations and never delete Bronze, Silver, or Gold.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.qdrant_index import QdrantChunkIndex
from src.news_pipeline.storage import create_object_store


def bootstrap_storage() -> dict:
    settings = GoldSettings.from_env()
    store = create_object_store(settings.news)
    store.ensure_bucket()
    return {
        "status": "PASS",
        "environment": settings.news.environment,
        "storage_provider": settings.news.storage_provider,
        "bucket": settings.news.bucket,
        "bronze_uri": settings.news.object_uri("bronze"),
        "silver_uri": settings.news.object_uri("silver"),
        "gold_uri": settings.news.object_uri("gold"),
    }


def reset_derived() -> dict:
    settings = GoldSettings.from_env().for_current_tables()
    index = QdrantChunkIndex(
        settings.qdrant_url, settings.qdrant_collection, settings.embedding_dimension
    )
    qdrant_deleted = False
    try:
        names = {item.name for item in index.client.get_collections().collections}
        if settings.qdrant_collection in names:
            index.client.delete_collection(settings.qdrant_collection)
            qdrant_deleted = True
    finally:
        index.close()
    duckdb = Path(settings.duckdb_path)
    duckdb_deleted = duckdb.exists()
    duckdb.unlink(missing_ok=True)
    return {
        "status": "PASS",
        "qdrant_collection": settings.qdrant_collection,
        "qdrant_deleted": qdrant_deleted,
        "duckdb_path": str(duckdb),
        "duckdb_deleted": duckdb_deleted,
        "durable_layers_deleted": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bootstrap-storage", "reset-derived"))
    args = parser.parse_args()
    result = bootstrap_storage() if args.command == "bootstrap-storage" else reset_derived()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
