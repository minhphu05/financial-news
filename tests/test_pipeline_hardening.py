"""Fast contract and control tests for Phase 05 hardening behavior."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.news_pipeline.bronze import ingest
from src.news_pipeline.config import Settings
from src.news_pipeline.duckdb_serving import publish as publish_duckdb
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.pipeline_runner import (
    _run_stage,
    date_range,
    make_run_id,
    validate_resume_identity,
)
from src.news_pipeline.qdrant_index import point_id
from src.news_pipeline.reconciliation import evaluate_counts
from src.news_pipeline.source_schema import SourceSchemaDriftError, validate_source_file


class MemoryStore:
    def __init__(self):
        self.objects = {}

    def ensure_bucket(self):
        pass

    def exists(self, key):
        return key in self.objects

    def upload_file(self, path, key):
        self.objects[key] = Path(path).read_bytes()

    def put_bytes(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_bytes(self, key):
        return self.objects[key]

    def list_keys(self, prefix):
        return sorted(key for key in self.objects if key.startswith(prefix))


class FakeStageRepository:
    def __init__(self):
        self.success = {}
        self.started = []
        self.finished = []

    def successful_stage(self, run_id, stage_name):
        return self.success.get((run_id, stage_name))

    def start_stage(self, run_id, stage_name, input_lineage=None):
        self.started.append((run_id, stage_name, input_lineage))
        return len(self.started)

    def finish_stage(self, stage_run_id, status, **fields):
        self.finished.append((stage_run_id, status, fields))


class PipelineHardeningTest(unittest.TestCase):
    def sample_row(self):
        return {
            "_id": "row-1",
            "context": "Nội dung tài chính",
            "index": 1,
            "keyword": "ngân hàng",
            "link": "https://cafef.vn/a.chn",
            "metadata": {"Date": "01-01-2026", "Time": "10:00"},
            "page": 1,
            "post date": "01-01-2026 - 10:00 AM",
            "summary": "Tóm tắt",
            "ticket name": "Ngân hàng A",
            "ticket symbol": "AAA",
            "title": "Tiêu đề",
        }

    def test_partition_range_and_run_identity_are_explicit(self):
        self.assertEqual(
            date_range(date(2026, 1, 1), date(2026, 1, 3)),
            [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
        )
        with self.assertRaisesRegex(ValueError, "earlier"):
            date_range(date(2026, 1, 2), date(2026, 1, 1))
        first = make_run_id("BACKFILL", date(2026, 1, 1), date(2026, 1, 3))
        second = make_run_id("BACKFILL", date(2026, 1, 1), date(2026, 1, 3))
        self.assertIn("backfill", first)
        self.assertNotEqual(first, second)

    def test_resume_rejects_changed_source_or_data_shaping_configuration(self):
        configuration = {
            "processing_version": "v1",
            "chunker_version": "sentence-v1-900-120",
            "embedding_provider": "fastembed",
            "embedding_model": "model-v1",
            "embedding_dimension": 384,
        }
        run = {
            "source": "cafef.vn",
            "parameters": {
                "configuration_id": "config-v1",
                "configuration": configuration,
            },
        }
        validate_resume_identity(
            run,
            source="cafef.vn",
            configuration_id="config-v1",
            configuration=configuration,
        )
        with self.assertRaisesRegex(ValueError, "current source"):
            validate_resume_identity(
                run,
                source="other.local",
                configuration_id="config-v1",
                configuration=configuration,
            )
        with self.assertRaisesRegex(ValueError, "changed processing"):
            validate_resume_identity(
                run,
                source="cafef.vn",
                configuration_id="config-v2",
                configuration={**configuration, "embedding_model": "model-v2"},
            )

    def test_bronze_bytes_and_partition_reference_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            source.write_text(json.dumps([self.sample_row()], ensure_ascii=False), encoding="utf-8")
            settings = Settings(
                source_file=str(source), source="cafef.vn", processing_date="2026-01-01"
            )
            store = MemoryStore()
            first = ingest(settings, store)
            object_count = len(store.objects)
            second = ingest(settings, store)
            self.assertEqual(first, second)
            self.assertEqual(len(store.objects), object_count)
            self.assertEqual(store.objects[first["raw_key"]], source.read_bytes())
            self.assertIn("processing_date=2026-01-01", first["partition_reference_key"])
            replay = ingest(replace(settings, processing_date="2026-01-02"), store)
            self.assertEqual(replay["ingestion_id"], first["ingestion_id"])
            self.assertEqual(len([key for key in store.objects if key.endswith("/raw.json")]), 1)
            self.assertIn("processing_date=2026-01-02", replay["partition_reference_key"])

    def test_schema_drift_fails_before_contract_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            source.write_text(json.dumps([self.sample_row()], ensure_ascii=False), encoding="utf-8")
            report = validate_source_file(source)
            self.assertTrue(report["compatible"])
            row = self.sample_row()
            row["new_unapproved_field"] = "drift"
            source.write_text(json.dumps([row], ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(SourceSchemaDriftError) as raised:
                validate_source_file(source)
            self.assertIn("unexpected fields", str(raised.exception))

    def test_stage_retry_reuses_success_and_records_failure(self):
        repository = FakeStageRepository()
        result = _run_stage(repository, "run-1", "silver", lambda: {"output_count": 2})
        self.assertEqual(result["output_count"], 2)
        self.assertEqual(repository.finished[-1][1], "SUCCESS")
        repository.success[("run-1", "silver")] = {"metrics": {"output_count": 2}}
        reused = _run_stage(repository, "run-1", "silver", lambda: self.fail("must not rerun"))
        self.assertEqual(reused, {"output_count": 2})
        with self.assertRaisesRegex(RuntimeError, "qdrant unavailable"):
            _run_stage(
                repository, "run-1", "qdrant",
                lambda: (_ for _ in ()).throw(RuntimeError("qdrant unavailable")),
            )
        self.assertEqual(repository.finished[-1][1], "FAILED")

    def test_current_paths_and_point_ids_are_stable_and_version_aware(self):
        base = GoldSettings(
            news=Settings(source="cafef.vn", processing_version="v1"),
            source_ingestion_id="abc", silver_articles_uri="old-a", silver_mentions_uri="old-m",
            rag_prefix="old-r", analytics_prefix="old-an", chunk_size=900, chunk_overlap=120,
            embedding_provider="fastembed", embedding_model="model", embedding_dimension=384,
            model_cache_dir="/tmp", qdrant_url="http://qdrant:6333", qdrant_collection="c",
            index_limit=0, index_batch_size=32, duckdb_path="/tmp/a.duckdb",
        )
        current = base.for_current_tables()
        self.assertIn("silver/current/cafef.vn/v1", current.silver_articles_uri)
        self.assertIn(base.chunker_version, current.rag_prefix)
        first = point_id("chunk-a", "model-v1")
        self.assertEqual(first, point_id("chunk-a", "model-v1"))
        self.assertNotEqual(first, point_id("chunk-a", "model-v2"))

    def test_reconciliation_reports_an_intentional_missing_output(self):
        healthy = {
            "silver_articles": 2, "silver_duplicate_ids": 0,
            "gold_documents": 2, "gold_duplicate_ids": 0,
            "gold_chunks": 3, "chunk_duplicate_ids": 0,
            "missing_gold_documents": 0, "orphan_gold_documents": 0,
            "orphan_chunks": 0, "qdrant_points": 3,
            "qdrant_missing_points": 0, "qdrant_stale_points": 0,
            "duckdb_articles": 2, "analytics_manifest_articles": 2,
        }
        self.assertEqual(evaluate_counts(healthy)["status"], "PASS")
        missing = {**healthy, "qdrant_points": 2, "qdrant_missing_points": 1}
        report = evaluate_counts(missing)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["checks"]["qdrant_matches_gold_chunks"])

    def test_duckdb_publish_failure_preserves_gold_and_current_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "analytics.duckdb"
            target.write_bytes(b"previous-serving-state")
            settings = GoldSettings(
                news=Settings(source="cafef.vn", processing_version="v1"),
                source_ingestion_id="ingestion-1",
                silver_articles_uri="unused-a",
                silver_mentions_uri="unused-m",
                rag_prefix="unused-r",
                analytics_prefix="gold/current/analytics/cafef.vn/v1",
                chunk_size=900,
                chunk_overlap=120,
                embedding_provider="fastembed",
                embedding_model="model",
                embedding_dimension=384,
                model_cache_dir=directory,
                qdrant_url="http://qdrant:6333",
                qdrant_collection="collection",
                index_limit=0,
                index_batch_size=32,
                duckdb_path=str(target),
            )
            store = MemoryStore()
            manifest_key = f"{settings.analytics_prefix}/manifest.json"
            manifest = {
                "source_ingestion_id": settings.source_ingestion_id,
                "input_article_count": 1,
                "datasets": {
                    name: {"row_count": 1, "object_keys": [f"missing/{name}.parquet"]}
                    for name in ("news_daily", "news_by_source", "news_publication_status")
                },
            }
            store.put_bytes(manifest_key, json.dumps(manifest).encode())

            with self.assertRaises(KeyError):
                publish_duckdb(settings, store)

            self.assertEqual(target.read_bytes(), b"previous-serving-state")
            self.assertEqual(json.loads(store.get_bytes(manifest_key)), manifest)
            self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_operations_tables_are_not_added_to_debezium_publication(self):
        migration = Path("operations/migrations/0001_pipeline_operations.up.sql").read_text()
        connector = Path("src/metadata_control/connector.py").read_text()
        metadata_config = Path("src/metadata_control/config.py").read_text()
        self.assertIn("pipeline_operations.pipeline_runs", migration)
        self.assertNotIn("pipeline_operations", connector)
        self.assertNotIn("pipeline_operations", metadata_config)
        self.assertIn('f"{self.schema}.news_sources"', metadata_config)
        self.assertIn('f"{self.schema}.pipeline_configs"', metadata_config)


if __name__ == "__main__":
    unittest.main(verbosity=2)
