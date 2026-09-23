"""Focused tests for reusable orchestration quality gates."""

import json
from pathlib import Path
import tempfile
import unittest

from src.news_pipeline.config import Settings
from src.news_pipeline.orchestration_quality import validate_bronze, validate_silver


class MemoryStore:
    def __init__(self):
        self.values: dict[str, bytes] = {}

    def ensure_bucket(self):
        pass

    def exists(self, key):
        return key in self.values

    def upload_file(self, path, key):
        self.values[key] = Path(path).read_bytes()

    def put_bytes(self, key, body, content_type="application/json"):
        self.values[key] = body

    def get_bytes(self, key):
        return self.values[key]

    def list_keys(self, prefix):
        return [key for key in self.values if key.startswith(prefix)]


class OrchestrationQualityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name) / "sample.json"
        self.source.write_text('[{"context":"valid"}]', encoding="utf-8")
        self.settings = Settings(source_file=str(self.source), source="cafef.vn", processing_version="test-v1")
        self.store = MemoryStore()
        import hashlib

        self.ingestion_id = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def test_bronze_gate_checks_manifest_and_checksum(self):
        prefix = f"bronze/cafef.vn/{self.ingestion_id}"
        raw_key = f"{prefix}/raw.json"
        self.store.values[raw_key] = self.source.read_bytes()
        self.store.values[f"{prefix}/manifest.json"] = json.dumps({
            "source_file_sha256": self.ingestion_id,
            "record_count": 1,
            "byte_size": self.source.stat().st_size,
            "raw_key": raw_key,
        }).encode()
        result = validate_bronze(self.settings, self.store)
        self.assertEqual(result["record_count"], 1)
        self.store.values[raw_key] = b"corrupt"
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_bronze(self.settings, self.store)

    def test_silver_gate_reconciles_counts_and_delta_logs(self):
        prefix = f"silver/cafef.vn/{self.ingestion_id}/test-v1"
        metrics = {
            "input_count": 5,
            "output_count": 3,
            "invalid_count": 1,
            "duplicate_count": 1,
            "article_mentions_count": 4,
        }
        self.store.values[f"{prefix}/metrics.json"] = json.dumps(metrics).encode()
        for table in ("articles", "article_mentions", "rejects"):
            self.store.values[f"{prefix}/{table}/_delta_log/000.json"] = b"{}"
        result = validate_silver(self.settings, self.store)
        self.assertEqual(result["output_count"], 3)
        metrics["duplicate_count"] = 2
        self.store.values[f"{prefix}/metrics.json"] = json.dumps(metrics).encode()
        with self.assertRaisesRegex(ValueError, "reconcile"):
            validate_silver(self.settings, self.store)


if __name__ == "__main__":
    unittest.main(verbosity=2)
