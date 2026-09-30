"""Fast configuration and release-boundary tests."""

from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from src.news_pipeline.config import Settings
from src.news_pipeline.spark_storage import configure_storage
from src.news_pipeline.storage import create_object_store


class FakeBuilder:
    def __init__(self):
        self.values = {}

    def config(self, key, value):
        self.values[key] = value
        return self


class LocalReleaseUnitTest(unittest.TestCase):
    @staticmethod
    def _root() -> Path:
        return Path("/app") if Path("/app/Makefile").exists() else Path(__file__).resolve().parents[1]

    def test_local_uri_and_spark_adapter(self):
        settings = Settings()
        self.assertEqual(
            settings.object_uri("silver/articles"),
            "s3a://financial-news/silver/articles",
        )
        self.assertEqual(
            settings.object_key(settings.object_uri("gold/chunks")), "gold/chunks"
        )
        builder = configure_storage(FakeBuilder(), settings)
        self.assertEqual(builder.values["spark.hadoop.fs.s3a.endpoint"], settings.endpoint)

    def test_invalid_configuration_fails_early(self):
        with patch.dict(
            os.environ,
            {"OBJECT_STORAGE_PROVIDER": "s3", "NEWS_STORAGE_ENDPOINT": ""},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "NEWS_STORAGE_ENDPOINT is required"):
                Settings.from_env()

    def test_future_cloud_profile_resolves_abfss_but_adapter_is_deferred(self):
        settings = Settings(
            environment="cloud",
            storage_provider="adls",
            storage_scheme="abfss",
            azure_storage_account="thesisstore",
            azure_storage_container="financial-news",
        )
        settings.validate()
        self.assertEqual(
            settings.object_uri("silver/articles"),
            "abfss://financial-news@thesisstore.dfs.core.windows.net/silver/articles",
        )
        with self.assertRaisesRegex(ValueError, "Phase 07"):
            create_object_store(settings)

    def test_runtime_modules_do_not_call_legacy_s3a_helper(self):
        root = Path("/app/src/news_pipeline") if Path("/app").exists() else Path("src/news_pipeline")
        offenders = []
        for path in root.glob("*.py"):
            if path.name == "config.py":
                continue
            if ".s3a(" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_release_version_manifest_matches_runtime_declarations(self):
        root = self._root()
        versions = {}
        for line in (root / "config/release-versions.env").read_text().splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                versions[key] = value
        declarations = {
            "SPARK_VERSION": (root / "docker/news-pipeline/Dockerfile").read_text(),
            "DELTA_SPARK_VERSION": (root / "Makefile").read_text(),
            "HADOOP_AWS_VERSION": (root / "Makefile").read_text(),
            "AIRFLOW_VERSION": (root / "docker/airflow/Dockerfile").read_text(),
            "POSTGRES_VERSION": (root / "docker/postgresql/Dockerfile").read_text(),
            "KAFKA_VERSION": (root / "docker-compose.yml").read_text(),
            "DEBEZIUM_VERSION": (root / "docker-compose.yml").read_text(),
            "QDRANT_VERSION": (root / "docker-compose.yml").read_text(),
            "DUCKDB_VERSION": (root / "docker/news-pipeline/Dockerfile").read_text(),
            "FASTEMBED_VERSION": (root / "docker/news-pipeline/Dockerfile").read_text(),
        }
        missing = [key for key, text in declarations.items() if versions[key] not in text]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
