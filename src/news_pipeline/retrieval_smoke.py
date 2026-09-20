"""Run documented Gold retrieval queries against the real local embedding index."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from src.news_pipeline.embedding import FastEmbedProvider
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.qdrant_index import QdrantChunkIndex


def evaluate(settings: GoldSettings, fixture_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    provider = FastEmbedProvider(settings)
    index = QdrantChunkIndex(settings.qdrant_url, settings.qdrant_collection, provider.dimension)
    try:
        indexed_count = index.count()
        if indexed_count != fixture["index_limit"]:
            raise ValueError(
                f"Smoke fixture expects {fixture['index_limit']} indexed chunks; collection has {indexed_count}. "
                "Run make qdrant-index INDEX_LIMIT=96 first."
            )
        results = []
        for item in fixture["queries"]:
            hits = index.search(provider.embed_query(item["query"]), fixture["top_k"])
            retrieved = [
                {
                    "rank": rank,
                    "score": round(hit["score"], 6),
                    "chunk_id": hit["chunk_id"],
                    "article_id": hit["article_id"],
                    "title": hit["title"],
                    "source_url": hit["source_url"],
                }
                for rank, hit in enumerate(hits, start=1)
            ]
            results.append({
                **item,
                "expected_in_top_k": any(hit["article_id"] == item["expected_article_id"] for hit in retrieved),
                "retrieved_top_k": retrieved,
            })
        return {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "collection": settings.qdrant_collection,
            "embedding_model": provider.model_id,
            "indexed_chunk_count": indexed_count,
            "fixture_index_limit": fixture["index_limit"],
            "top_k": fixture["top_k"],
            "passed_queries": sum(item["expected_in_top_k"] for item in results),
            "total_queries": len(results),
            "results": results,
        }
    finally:
        index.close()


def main() -> None:
    settings = GoldSettings.from_env()
    fixture = Path(os.getenv("NEWS_SMOKE_FIXTURE", "/app/tests/fixtures/gold_retrieval_queries.json"))
    output = Path(os.getenv("NEWS_SMOKE_OUTPUT", "/app/local/gold-retrieval-smoke-results.json"))
    result = evaluate(settings, fixture)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
