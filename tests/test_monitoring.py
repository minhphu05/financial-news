"""Unit tests for the Phase 07 low-cardinality pipeline exporter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from prometheus_client import generate_latest

from src.monitoring.exporter import (
    bounded_pipeline,
    bounded_source,
    build_registry,
    canonical_stage,
    stage_record_counts,
)


class FakeReader:
    def read(self):
        now = datetime.now(timezone.utc)
        return {
            "runs": [{
                "pipeline_name": "financial_news_incremental:config-hash",
                "source": "phase07-monitoring.local",
                "trigger_type": "REPROCESS",
                "status": "SUCCESS",
                "started_at": now - timedelta(seconds=4),
                "finished_at": now,
                "created_at": now - timedelta(seconds=4),
            }],
            "stages": [{
                "pipeline_name": "financial_news_incremental:config-hash",
                "source": "phase07-monitoring.local",
                "stage_name": "2026-09-07:silver_merge",
                "status": "SUCCESS",
                "attempt": 1,
                "metrics": {
                    "stage_duration_seconds": 1.5,
                    "input_count": 4,
                    "output_count": 2,
                    "invalid_count": 1,
                    "duplicate_count": 1,
                },
                "started_at": now - timedelta(seconds=2),
                "finished_at": now,
            }, {
                "pipeline_name": "financial_news_incremental:config-hash",
                "source": "phase07-monitoring.local",
                "stage_name": "2026-09-07:silver_merge",
                "status": "FAILED",
                "attempt": 2,
                "metrics": {"stage_duration_seconds": 0.5},
                "started_at": now + timedelta(seconds=1),
                "finished_at": now + timedelta(seconds=2),
            }],
            "slot": {"active": True, "has_confirmed_lsn": True, "lag_bytes": 0},
        }


class MonitoringExporterTest(unittest.TestCase):
    def test_stage_and_label_values_are_bounded(self):
        self.assertEqual(canonical_stage("2026-09-07:silver_merge"), "silver_merge")
        self.assertEqual(canonical_stage("arbitrary-stage-id"), "other")
        self.assertEqual(bounded_pipeline("financial_news_incremental:abc"), "financial_news_incremental")
        self.assertEqual(bounded_pipeline("dynamic-pipeline-123"), "other")
        self.assertEqual(bounded_source("unbounded.example/123"), "other")

    def test_record_counts_preserve_quality_effects(self):
        counts = stage_record_counts("silver_merge", {
            "input_count": 10, "output_count": 7, "invalid_count": 1,
            "duplicate_count": 2,
        })
        self.assertEqual(counts, {
            "input": 10.0, "output": 7.0, "invalid": 1.0, "duplicate": 2.0,
        })

    @patch("src.monitoring.exporter.service_snapshot")
    def test_exported_metrics_avoid_unbounded_identifiers(self, services):
        services.return_value = {
            "airflow": {"scheduler": 1.0, "metadatabase": 1.0},
            "debezium_connector": 1.0,
            "debezium_task": 1.0,
            "kafka": 1.0,
            "topics": [],
        }
        text = generate_latest(build_registry(FakeReader())).decode()
        self.assertIn("financial_news_pipeline_runs_total", text)
        self.assertIn('stage="silver_merge"', text)
        self.assertIn(
            'financial_news_pipeline_stage_last_success_timestamp_seconds{pipeline="financial_news_incremental",source="phase07-monitoring.local",stage="silver_merge"}',
            text,
        )
        self.assertIn(
            'financial_news_data_freshness_seconds{layer="silver",pipeline="financial_news_incremental",source="phase07-monitoring.local"}',
            text,
        )
        for forbidden in ("run_id=", "article_id=", "chunk_id=", "source_url=", "error="):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
