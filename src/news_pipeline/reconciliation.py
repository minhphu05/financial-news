"""Cross-layer reconciliation for current Silver, Gold, Qdrant, and DuckDB state."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import time


from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.qdrant_index import QdrantChunkIndex, point_id
from src.news_pipeline.storage import ObjectStore


EMBEDDING_IMPLEMENTATION_VERSION = "fastembed-0.8.0"


def evaluate_counts(counts: dict[str, int]) -> dict:
    checks = {
        "silver_article_ids_unique": counts["silver_duplicate_ids"] == 0,
        "gold_document_ids_unique": counts["gold_duplicate_ids"] == 0,
        "gold_chunk_ids_unique": counts["chunk_duplicate_ids"] == 0,
        "silver_gold_documents_match": (
            counts["silver_articles"] == counts["gold_documents"]
            and counts["missing_gold_documents"] == 0
            and counts["orphan_gold_documents"] == 0
        ),
        "chunks_reference_documents": counts["orphan_chunks"] == 0,
        "qdrant_matches_gold_chunks": (
            counts["qdrant_points"] == counts["gold_chunks"]
            and counts["qdrant_missing_points"] == 0
            and counts["qdrant_stale_points"] == 0
        ),
        "duckdb_matches_analytics_manifest": (
            counts["duckdb_articles"] == counts["analytics_manifest_articles"]
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": counts,
    }


def reconcile(
    settings: GoldSettings,
    spark,
    store: ObjectStore,
    *,
    run_id: str,
) -> dict:
    started = time.monotonic()
    current = settings.for_current_tables()
    silver = spark.read.format("delta").load(current.silver_articles_uri).persist()
    documents_uri = current.news.object_uri(f"{current.rag_prefix}/documents")
    documents = spark.read.format("delta").load(documents_uri).persist()
    chunks = spark.read.format("delta").load(current.chunks_uri).persist()
    index = QdrantChunkIndex(
        current.qdrant_url, current.qdrant_collection, current.embedding_dimension
    )
    try:
        model_id = f"{EMBEDDING_IMPLEMENTATION_VERSION}:{current.embedding_model}"
        expected_qdrant_ids = {
            point_id(row.chunk_id, model_id)
            for row in chunks.select("chunk_id").toLocalIterator()
        }
        actual_qdrant_ids = index.point_ids()
        manifest = json.loads(
            store.get_bytes(f"{current.analytics_prefix}/manifest.json")
        )
        import duckdb
        with duckdb.connect(current.duckdb_path, read_only=True) as connection:
            duckdb_articles = connection.execute(
                "SELECT COALESCE(SUM(article_count), 0) FROM news_by_source"
            ).fetchone()[0]
        counts = {
            "silver_articles": silver.count(),
            "silver_duplicate_ids": silver.groupBy("article_id").count().filter("count > 1").count(),
            "gold_documents": documents.count(),
            "gold_duplicate_ids": documents.groupBy("article_id").count().filter("count > 1").count(),
            "gold_chunks": chunks.count(),
            "chunk_duplicate_ids": chunks.groupBy("chunk_id").count().filter("count > 1").count(),
            "missing_gold_documents": silver.select("article_id").join(
                documents.select("article_id"), "article_id", "left_anti"
            ).count(),
            "orphan_gold_documents": documents.select("article_id").join(
                silver.select("article_id"), "article_id", "left_anti"
            ).count(),
            "orphan_chunks": chunks.select("article_id").distinct().join(
                documents.select("article_id"), "article_id", "left_anti"
            ).count(),
            "qdrant_points": len(actual_qdrant_ids),
            "qdrant_missing_points": len(expected_qdrant_ids - actual_qdrant_ids),
            "qdrant_stale_points": len(actual_qdrant_ids - expected_qdrant_ids),
            "duckdb_articles": int(duckdb_articles),
            "analytics_manifest_articles": int(manifest["input_article_count"]),
        }
        result = {
            **evaluate_counts(counts),
            "run_id": run_id,
            "source": current.news.source,
            "processing_version": current.news.processing_version,
            "embedding_model_id": model_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.monotonic() - started, 3),
        }
        key = f"operations/reconciliation/{run_id}.json"
        store.put_bytes(key, json.dumps(result, indent=2, default=str).encode())
        result["report_key"] = key
        if result["status"] != "PASS":
            failed = [name for name, ok in result["checks"].items() if not ok]
            raise RuntimeError(f"Reconciliation failed: {', '.join(failed)}")
        return result
    finally:
        index.close()
        silver.unpersist()
        documents.unpersist()
        chunks.unpersist()


def main() -> None:
    import argparse
    from src.news_pipeline.silver import create_spark
    from src.news_pipeline.storage import create_object_store

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    settings = GoldSettings.from_env()
    spark = create_spark(settings.news)
    try:
        print(json.dumps(
            reconcile(settings, spark, create_object_store(settings.news), run_id=args.run_id),
            indent=2,
        ))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
