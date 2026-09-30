"""Explicit full rebuild of the current-state Qdrant projection."""

import json

from src.news_pipeline.embedding import FastEmbedProvider
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.qdrant_index import index_chunks
from src.news_pipeline.storage import S3ObjectStore


def main() -> None:
    base = GoldSettings.from_env()
    current = base.for_current_tables()
    provider = FastEmbedProvider(current)
    print(json.dumps(index_chunks(current, provider, S3ObjectStore(current.news)), indent=2))


if __name__ == "__main__":
    main()
