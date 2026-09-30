"""Isolated Phase 06 local release, idempotency, and rebuild acceptance test."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from src.news_pipeline.analytics import build as build_analytics
from src.news_pipeline.bronze import ingest
from src.news_pipeline.config import Settings
from src.news_pipeline.duckdb_serving import publish, query as query_duckdb
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.gold_rag import build_incremental as build_gold
from src.news_pipeline.qdrant_index import QdrantChunkIndex, index_affected, index_chunks
from src.news_pipeline.reconciliation import reconcile
from src.news_pipeline.semantic_search import search
from src.news_pipeline.silver import build_incremental as build_silver, create_spark
from src.news_pipeline.storage import create_object_store
from tests.gold_fakes import DeterministicTestEmbeddingProvider


class ReleaseEmbedding(DeterministicTestEmbeddingProvider):
    model_id = "fastembed-0.8.0:local-release-token-hash-v1"


def main() -> None:
    started = time.monotonic()
    fixture_root = Path("/app/tests/fixtures/local_release")
    day1 = fixture_root / "2026-09-01.json"
    day2 = fixture_root / "2026-09-02.json"
    for path in (day1, day2):
        if not path.is_file():
            raise FileNotFoundError(path)

    news = replace(
        Settings.from_env(),
        environment="test",
        source="local-release.test",
        source_file=str(day1),
        processing_version="local-rc1-acceptance",
        processing_date="2026-09-01",
        run_id="local-rc1-initial",
    )
    gold = GoldSettings(
        news=news,
        source_ingestion_id="pending",
        silver_articles_uri="pending",
        silver_mentions_uri="pending",
        rag_prefix="pending",
        analytics_prefix="pending",
        chunk_size=120,
        chunk_overlap=20,
        embedding_provider="test",
        embedding_model="local-release-token-hash-v1",
        embedding_dimension=32,
        model_cache_dir="/opt/news-models",
        qdrant_url="http://qdrant:6333",
        qdrant_collection="local_release_acceptance_v1",
        index_limit=0,
        index_batch_size=8,
        duckdb_path="/app/local/local-release-acceptance.duckdb",
    )
    store = create_object_store(news)
    store.ensure_bucket()
    delete_prefix = getattr(store, "delete_prefix")
    for prefix in (
        "bronze/local-release.test/",
        "silver/local-release.test/",
        "silver/current/local-release.test/local-rc1-acceptance/",
        "silver/operations/source=local-release.test/processing_version=local-rc1-acceptance/",
        "gold/rag/local-release.test/",
        "gold/analytics/local-release.test/",
        "gold/current/rag/local-release.test/local-rc1-acceptance/",
        "gold/current/analytics/local-release.test/local-rc1-acceptance/",
        "operations/reconciliation/local-rc1-",
    ):
        delete_prefix(prefix)
    Path(gold.duckdb_path).unlink(missing_ok=True)
    index = QdrantChunkIndex(gold.qdrant_url, gold.qdrant_collection, gold.embedding_dimension)
    try:
        if gold.qdrant_collection in {c.name for c in index.client.get_collections().collections}:
            index.client.delete_collection(gold.qdrant_collection)
    finally:
        index.close()

    provider = ReleaseEmbedding(gold.embedding_dimension)
    spark = create_spark(news)
    runs: list[dict] = []

    def process(path: Path, day: str, run_id: str) -> tuple[dict, dict, list[str]]:
        nonlocal gold
        partition_news = replace(
            news, source_file=str(path), processing_date=day, run_id=run_id
        )
        partition_store = create_object_store(partition_news)
        bronze = ingest(partition_news, partition_store)
        silver = build_silver(partition_news, partition_store, spark)
        affected = json.loads(
            partition_store.get_bytes(silver["affected_article_ids_key"])
        )["article_ids"]
        gold = replace(gold, news=partition_news, source_ingestion_id=bronze["ingestion_id"])
        gold_metrics = build_gold(gold, spark, partition_store, affected)
        current = gold.for_current_tables()
        analytics = build_analytics(current, spark, partition_store)
        duckdb = publish(current, partition_store)
        qdrant = (
            index_affected(gold, provider, partition_store, affected, spark=spark)
            if affected else {"affected_article_count": 0, "indexed_chunk_count": 0}
        )
        runs.append({
            "date": day,
            "bronze": bronze,
            "silver": silver,
            "gold": gold_metrics,
            "analytics": analytics,
            "duckdb": duckdb,
            "qdrant": qdrant,
        })
        return bronze, silver, affected

    try:
        first_bronze, first_silver, first_affected = process(
            day1, "2026-09-01", "local-rc1-initial"
        )
        assert first_bronze["record_count"] == 4
        assert first_silver["output_count"] == 2
        assert first_silver["invalid_count"] == 1
        assert first_silver["duplicate_count"] == 1
        assert len(first_affected) == 2

        replay_bronze, replay_silver, replay_affected = process(
            day1, "2026-09-01", "local-rc1-replay"
        )
        assert replay_bronze["ingestion_id"] == first_bronze["ingestion_id"]
        assert replay_silver["affected_article_count"] == 0
        assert replay_affected == []

        _, incremental_silver, incremental_affected = process(
            day2, "2026-09-02", "local-rc1-incremental"
        )
        assert incremental_silver["inserted_article_count"] == 1
        assert incremental_silver["unchanged_article_count"] == 1
        assert len(incremental_affected) == 1

        current = gold.for_current_tables()
        initial_retrieval = search(
            "ngân hàng lợi nhuận", current, provider, top_k=3
        )
        assert initial_retrieval
        assert initial_retrieval[0]["title"] == "Ngân hàng ABC công bố lợi nhuận"
        analytical_total = query_duckdb(
            current, "SELECT SUM(article_count) FROM news_by_source"
        )[0][0]
        assert analytical_total == 3

        # Scenario C: remove isolated current Gold and rebuild it from current Silver.
        delete_prefix(current.rag_prefix + "/")
        article_ids = [
            row.article_id
            for row in spark.read.format("delta").load(current.silver_articles_uri)
                .select("article_id").orderBy("article_id").collect()
        ]
        gold_rebuild = build_gold(current, spark, store, article_ids)
        assert gold_rebuild["gold_documents_produced"] == 3
        delete_prefix(current.analytics_prefix + "/")
        analytics_rebuild = build_analytics(current, spark, store)
        assert analytics_rebuild["input_article_count"] == 3
    finally:
        spark.stop()

    # Scenario A: Qdrant is disposable and restores from durable Gold chunks.
    index = QdrantChunkIndex(gold.qdrant_url, gold.qdrant_collection, gold.embedding_dimension)
    try:
        index.client.delete_collection(gold.qdrant_collection)
    finally:
        index.close()
    qdrant_rebuild = index_chunks(current, provider, store)
    rebuilt_retrieval = search("ngân hàng lợi nhuận", current, provider, top_k=3)
    assert rebuilt_retrieval[0]["title"] == "Ngân hàng ABC công bố lợi nhuận"

    # Scenario B: DuckDB is disposable and restores directly from Gold Analytics.
    Path(current.duckdb_path).unlink(missing_ok=True)
    duckdb_rebuild = publish(current, store)
    rebuilt_total = query_duckdb(
        current, "SELECT SUM(article_count) FROM news_by_source"
    )[0][0]
    assert rebuilt_total == 3

    verification_spark = create_spark(news)
    try:
        reconciliation = reconcile(
            current, verification_spark, store, run_id="local-rc1-rebuild"
        )
    finally:
        verification_spark.stop()
    assert reconciliation["status"] == "PASS"

    result = {
        "status": "PASS",
        "release": "local-rc1",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "fixture_files": [str(day1), str(day2)],
        "capabilities": {
            "bronze_immutable": True,
            "silver_validation": True,
            "deduplication": True,
            "incremental": True,
            "idempotent_replay": replay_affected == [],
            "semantic_retrieval": True,
            "analytics_query": True,
            "gold_rebuilt_from_silver": True,
            "qdrant_rebuilt_from_gold": True,
            "duckdb_rebuilt_from_gold": True,
            "reconciliation": reconciliation["status"] == "PASS",
        },
        "counts": reconciliation["counts"],
        "qdrant_rebuild": qdrant_rebuild,
        "duckdb_rebuild": duckdb_rebuild,
        "gold_rebuild": gold_rebuild,
        "analytics_rebuild": analytics_rebuild,
        "retrieval_top_title": rebuilt_retrieval[0]["title"],
        "runs": runs,
    }
    output = Path("/app/local/local-release-e2e.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
