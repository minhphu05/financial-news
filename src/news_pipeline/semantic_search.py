"""CLI retrieval of Gold chunks from Qdrant without LLM generation."""

import json
import os
import sys

from src.news_pipeline.embedding import EmbeddingProvider, FastEmbedProvider
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.qdrant_index import QdrantChunkIndex


def search(query: str, settings: GoldSettings, provider: EmbeddingProvider, top_k: int = 5) -> list[dict]:
    if not query.strip():
        raise ValueError("Query must not be empty")
    index = QdrantChunkIndex(settings.qdrant_url, settings.qdrant_collection, provider.dimension)
    try:
        return index.search(provider.embed_query(query), top_k)
    finally:
        index.close()


def main() -> None:
    query = sys.argv[1] if len(sys.argv) >= 2 else os.getenv("NEWS_SEARCH_QUERY", "")
    if not query:
        raise SystemExit("Usage: semantic_search.py QUERY [TOP_K]")
    settings = GoldSettings.from_env()
    provider = FastEmbedProvider(settings)
    result = search(query, settings, provider, int(sys.argv[2]) if len(sys.argv) > 2 else 5)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
