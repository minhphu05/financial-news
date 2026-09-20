"""Inspect committed Gold datasets and their metrics in MinIO."""

import json
import sys

from src.news_pipeline.gold_config import ANALYTICS_DATASETS, GoldSettings
from src.news_pipeline.storage import S3ObjectStore


def main() -> None:
    settings = GoldSettings.from_env()
    store = S3ObjectStore(settings.news)
    mode = sys.argv[1] if len(sys.argv) > 1 else "rag"
    if mode == "metrics":
        for key in (
            f"{settings.rag_prefix}/metrics.json",
            f"{settings.rag_prefix}/qdrant_metrics.json",
            f"{settings.analytics_prefix}/metrics.json",
            f"{settings.analytics_prefix}/duckdb_metrics.json",
        ):
            if store.exists(key):
                print(key)
                print(store.get_bytes(key).decode())
        return
    from src.news_pipeline.silver import create_spark

    spark = create_spark(settings.news)
    try:
        if mode == "rag":
            for name in ("documents", "chunks"):
                frame = spark.read.format("delta").load(settings.news.s3a(f"{settings.rag_prefix}/{name}"))
                print(f"{name}: {frame.count()} rows; columns={frame.columns}")
            chunks = spark.read.format("delta").load(settings.chunks_uri)
            for row in chunks.orderBy("article_id", "chunk_index").select("article_id", "chunk_id", "title", "text").limit(20).collect():
                print(json.dumps({"article_id": row.article_id, "chunk_id": row.chunk_id, "title": row.title, "text_preview": row.text[:150]}, ensure_ascii=False))
        elif mode == "analytics":
            for name in ANALYTICS_DATASETS:
                frame = spark.read.parquet(settings.analytics_uri(name))
                print(f"{name}: {frame.count()} rows; columns={frame.columns}")
                frame.show(5, truncate=70)
        else:
            raise SystemExit("Usage: inspect_gold.py rag|analytics|metrics")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
