"""Real MinIO/Delta/Qdrant/DuckDB/PostgreSQL Phase 05 integration scenarios."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid

from qdrant_client import models

from src.news_pipeline.analytics import build as build_analytics
from src.news_pipeline.bronze import ingest
from src.news_pipeline.config import Settings
from src.news_pipeline.duckdb_serving import publish
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.gold_rag import build_incremental as build_gold
from src.news_pipeline.qdrant_index import QdrantChunkIndex, index_affected, point_id
from src.news_pipeline.reconciliation import reconcile
from src.news_pipeline.silver import build_incremental as build_silver, create_spark
from src.news_pipeline.storage import S3ObjectStore
from src.pipeline_operations.config import OperationsSettings
from src.pipeline_operations.repository import OperationsRepository, PartitionLockedError


class DeterministicEmbedding:
    model_id = "fastembed-0.8.0:phase05-deterministic-model"
    dimension = 384

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [((digest[index % len(digest)] / 255.0) - 0.5) for index in range(self.dimension)]

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


def row(
    number: int,
    content: str,
    *,
    day: int = 1,
    ticker_symbol: str = "AAA",
    keyword: str = "finance",
) -> dict:
    return {
        "_id": f"row-{number}-{day}",
        "context": content,
        "index": number,
        "keyword": keyword,
        "link": f"https://phase05-it.local/article-{number}.chn",
        "metadata": {"Date": f"{day:02d}-09-2026", "Time": "10:00"},
        "page": 1,
        "post date": f"{day:02d}-09-2026 - 10:00 AM",
        "summary": f"Summary {number}",
        "ticket name": "Company",
        "ticket symbol": ticker_symbol,
        "title": f"Article {number}",
    }


def write_fixture(directory: Path, day: str, rows: list[dict]) -> Path:
    path = directory / f"{day}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path


def affected(store, metrics):
    return json.loads(store.get_bytes(metrics["affected_article_ids_key"]))["article_ids"]


def snapshot(spark, settings, index) -> dict:
    current = settings.for_current_tables()
    silver = spark.read.format("delta").load(current.silver_articles_uri)
    documents = spark.read.format("delta").load(
        current.news.s3a(f"{current.rag_prefix}/documents")
    )
    chunks = spark.read.format("delta").load(current.chunks_uri)
    return {
        "silver": sorted((r.article_id, r.content_hash) for r in silver.select("article_id", "content_hash").collect()),
        "documents": sorted((r.article_id, r.content_hash) for r in documents.select("article_id", "content_hash").collect()),
        "chunks": sorted(r.chunk_id for r in chunks.select("chunk_id").collect()),
        "qdrant_ids": sorted(index.point_ids()),
    }


def main() -> None:
    suffix = uuid.uuid4().hex[:10]
    fixture_dir = Path(f"/app/local/phase5-integration-{suffix}")
    fixture_dir.mkdir(parents=True)
    first_file = write_fixture(
        fixture_dir, "2026-09-01",
        [row(1, "Initial financial content A."), row(2, "Stable financial content B.")],
    )
    second_file = write_fixture(
        fixture_dir, "2026-09-02",
        [row(2, "Stable financial content B."), row(3, "New financial content C.", day=2)],
    )
    changed_file = write_fixture(
        fixture_dir, "2026-09-03",
        [row(1, "Publisher corrected financial content A.", day=3)],
    )
    mention_file = write_fixture(
        fixture_dir, "2026-09-04",
        [row(2, "Stable financial content B.", ticker_symbol="BBB", keyword="risk")],
    )

    news = Settings.from_env()
    news = replace(
        news,
        source="phase05-it.local",
        source_file=str(first_file),
        processing_version=f"phase05-it-{suffix}",
        processing_date="2026-09-01",
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
        embedding_provider="fastembed",
        embedding_model="phase05-deterministic-model",
        embedding_dimension=384,
        model_cache_dir="/opt/news-models",
        qdrant_url="http://qdrant:6333",
        qdrant_collection=f"phase05_it_{suffix}",
        index_limit=0,
        index_batch_size=8,
        duckdb_path=f"/app/local/phase05-it-{suffix}.duckdb",
    )
    store = S3ObjectStore(news)
    provider = DeterministicEmbedding()
    spark = create_spark(news)
    index = QdrantChunkIndex(gold.qdrant_url, gold.qdrant_collection, 384)
    started = time.monotonic()
    timings = []

    def process(source_file: Path, processing_date: str):
        nonlocal gold, store
        stage_started = time.monotonic()
        partition_news = replace(
            news,
            source_file=str(source_file),
            processing_date=processing_date,
            run_id=f"{suffix}-{processing_date}-{len(timings)}",
        )
        store = S3ObjectStore(partition_news)
        manifest = ingest(partition_news, store)
        silver_metrics = build_silver(partition_news, store, spark)
        ids = affected(store, silver_metrics)
        gold = replace(gold, news=partition_news, source_ingestion_id=manifest["ingestion_id"])
        gold_metrics = build_gold(gold, spark, store, ids)
        analytics_metrics = build_analytics(gold.for_current_tables(), spark, store)
        duckdb_metrics = publish(gold.for_current_tables(), store)
        qdrant_metrics = (
            index_affected(gold, provider, store, ids, spark=spark)
            if ids else {"affected_article_count": 0, "indexed_chunk_count": 0}
        )
        timings.append({
            "processing_date": processing_date,
            "duration_seconds": round(time.monotonic() - stage_started, 3),
            "silver": silver_metrics,
            "gold": gold_metrics,
            "analytics": analytics_metrics,
            "duckdb": duckdb_metrics,
            "qdrant": qdrant_metrics,
        })
        return manifest, silver_metrics, ids

    try:
        first_manifest, first_silver, first_ids = process(first_file, "2026-09-01")
        assert first_silver["inserted_article_count"] == 2
        assert len(first_ids) == 2
        index.ensure_collection()
        first_snapshot = snapshot(spark, gold, index)
        assert len(first_snapshot["silver"]) == 2
        assert len(first_snapshot["qdrant_ids"]) == len(first_snapshot["chunks"])

        # Same logical partition converges: no affected records, no duplicate vectors.
        second_manifest, repeated_silver, repeated_ids = process(first_file, "2026-09-01")
        repeated_snapshot = snapshot(spark, gold, index)
        assert first_manifest["ingestion_id"] == second_manifest["ingestion_id"]
        assert repeated_silver["inserted_article_count"] == 0
        assert repeated_silver["updated_article_count"] == 0
        assert repeated_silver["unchanged_article_count"] == 2
        assert repeated_ids == []
        assert repeated_snapshot == first_snapshot

        # New partition touches C only; A and B remain stable.
        _, new_silver, new_ids = process(second_file, "2026-09-02")
        new_snapshot = snapshot(spark, gold, index)
        assert new_silver["inserted_article_count"] == 1
        assert new_silver["updated_article_count"] == 0
        assert new_silver["unchanged_article_count"] == 1
        assert len(new_ids) == 1, {"metrics": new_silver, "ids": new_ids}
        assert len(new_snapshot["silver"]) == 3
        assert set(first_snapshot["silver"]).issubset(set(new_snapshot["silver"]))

        # Same article ID with changed content updates Silver and replaces only A chunks/vectors.
        before_change = new_snapshot
        _, changed_silver, changed_ids = process(changed_file, "2026-09-03")
        after_change = snapshot(spark, gold, index)
        assert changed_silver["inserted_article_count"] == 0
        assert changed_silver["updated_article_count"] == 1
        assert len(changed_ids) == 1
        unchanged_article_ids = {item[0] for item in before_change["silver"]} - set(changed_ids)
        before_stable = {item for item in before_change["silver"] if item[0] in unchanged_article_ids}
        after_stable = {item for item in after_change["silver"] if item[0] in unchanged_article_ids}
        assert before_stable == after_stable
        assert len(after_change["qdrant_ids"]) == len(after_change["chunks"])

        # Re-upserting an affected article keeps stable point IDs and count.
        index_affected(gold, provider, store, changed_ids, spark=spark)
        assert snapshot(spark, gold, index) == after_change

        # A new mention affects Gold/Qdrant metadata even when article content is unchanged.
        before_mention = after_change
        _, mention_silver, mention_ids = process(mention_file, "2026-09-04")
        after_mention = snapshot(spark, gold, index)
        assert mention_silver["inserted_article_count"] == 0
        assert mention_silver["updated_article_count"] == 0
        assert mention_silver["unchanged_article_count"] == 1
        assert len(mention_ids) == 1
        assert before_mention == after_mention
        current_documents = gold.for_current_tables().news.s3a(
            f"{gold.for_current_tables().rag_prefix}/documents"
        )
        symbols = (
            spark.read.format("delta").load(current_documents)
                .filter(f"article_id = '{mention_ids[0]}'")
                .select("stock_symbols").first().stock_symbols
        )
        assert symbols == ["AAA", "BBB"]

        analytics_metrics = build_analytics(gold.for_current_tables(), spark, store)
        publish(gold.for_current_tables(), store)
        healthy = reconcile(gold, spark, store, run_id=f"integration-{suffix}-healthy")
        assert healthy["status"] == "PASS"

        # An intentionally missing Qdrant point is detected, then targeted upsert repairs it.
        victim = after_change["qdrant_ids"][0]
        index.client.delete(
            collection_name=gold.qdrant_collection,
            points_selector=models.PointIdsList(points=[victim]),
            wait=True,
        )
        missing_detected = False
        try:
            reconcile(gold, spark, store, run_id=f"integration-{suffix}-missing")
        except RuntimeError as exc:
            missing_detected = "qdrant_matches_gold_chunks" in str(exc)
        assert missing_detected
        current = gold.for_current_tables()
        victim_chunk = spark.read.format("delta").load(current.chunks_uri).filter(
            f"chunk_id = '{next(row.chunk_id for row in spark.read.format('delta').load(current.chunks_uri).select('chunk_id').collect() if point_id(row.chunk_id, provider.model_id) == victim)}'"
        ).first()
        index_affected(gold, provider, store, [victim_chunk.article_id], spark=spark)
        repaired = reconcile(gold, spark, store, run_id=f"integration-{suffix}-repaired")
        assert repaired["status"] == "PASS"

        # PostgreSQL keeps backfill identity, lock ownership, failure, and checkpoint separately.
        operations = OperationsSettings.from_env()
        pipeline_name = f"phase05_integration:{suffix}"
        checkpoint_run = f"it-normal-{suffix}"
        with OperationsRepository(operations) as repository:
            repository.begin_run(
                run_id=checkpoint_run, pipeline_name=pipeline_name, source=news.source,
                trigger_type="NORMAL", partition_start=date(2026, 9, 2),
                partition_end=date(2026, 9, 2), force_reprocess=False, parameters={},
            )
            repository.finish_run(checkpoint_run, "SUCCESS")
            repository.advance_checkpoint(pipeline_name, news.source, date(2026, 9, 2), checkpoint_run)
            initial_checkpoint = repository.checkpoint(pipeline_name, news.source)
            backfill_run = f"it-backfill-{suffix}"
            repository.begin_run(
                run_id=backfill_run, pipeline_name=pipeline_name, source=news.source,
                trigger_type="BACKFILL", partition_start=date(2026, 9, 1),
                partition_end=date(2026, 9, 3), force_reprocess=False,
                parameters={"requested_range": ["2026-09-01", "2026-09-03"]},
            )
            repository.acquire_partition(pipeline_name, news.source, date(2026, 9, 1), backfill_run)
            other_run = f"it-concurrent-{suffix}"
            repository.begin_run(
                run_id=other_run, pipeline_name=pipeline_name, source=news.source,
                trigger_type="MANUAL", partition_start=date(2026, 9, 1),
                partition_end=date(2026, 9, 1), force_reprocess=False, parameters={},
            )
            with OperationsRepository(operations) as competitor:
                try:
                    competitor.acquire_partition(
                        pipeline_name, news.source, date(2026, 9, 1), other_run
                    )
                    raise AssertionError("overlapping partition lock was accepted")
                except PartitionLockedError:
                    pass
            repository.finish_run(other_run, "FAILED", "overlap rejected")
            repository.release_partition(pipeline_name, news.source, date(2026, 9, 1), backfill_run)
            repository.finish_run(backfill_run, "SUCCESS")
            assert repository.checkpoint(pipeline_name, news.source) == initial_checkpoint

            failed_run = f"it-failed-{suffix}"
            repository.begin_run(
                run_id=failed_run, pipeline_name=pipeline_name, source=news.source,
                trigger_type="NORMAL", partition_start=date(2026, 9, 4),
                partition_end=date(2026, 9, 4), force_reprocess=False, parameters={},
            )
            stage = repository.start_stage(failed_run, "qdrant_upsert")
            repository.finish_stage(stage, "FAILED", error_message="simulated unavailable")
            repository.finish_run(failed_run, "FAILED", "simulated unavailable")
            assert repository.checkpoint(pipeline_name, news.source) == initial_checkpoint

        result = {
            "status": "PASS",
            "scenario_id": suffix,
            "source": news.source,
            "processing_version": news.processing_version,
            "qdrant_collection": gold.qdrant_collection,
            "first_ingestion_id": first_manifest["ingestion_id"],
            "idempotent_reprocess_affected": len(repeated_ids),
            "incremental_new_affected": len(new_ids),
            "content_update_affected": len(changed_ids),
            "mention_update_affected": len(mention_ids),
            "final_counts": repaired["counts"],
            "intentional_missing_output_detected": missing_detected,
            "checkpoint_not_advanced_on_failure": True,
            "overlap_lock_rejected": True,
            "timings": timings,
            "total_duration_seconds": round(time.monotonic() - started, 3),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        Path("/app/local/phase5-integration-results.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps(result, indent=2, default=str))
    finally:
        index.close()
        spark.stop()


if __name__ == "__main__":
    main()
