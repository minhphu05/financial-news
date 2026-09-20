"""End-to-end sample integration test: source file -> MinIO -> Spark -> Delta."""

import json
import unittest

from src.news_pipeline.bronze import ingest
from src.news_pipeline.config import Settings
from src.news_pipeline.silver import ARTICLE_FIELDS, build, create_spark
from src.news_pipeline.storage import S3ObjectStore


class SamplePipelineIntegrationTest(unittest.TestCase):
    def test_repository_sample(self):
        settings = Settings.from_env()
        store = S3ObjectStore(settings)
        manifest = ingest(settings, store)
        self.assertEqual(manifest["record_count"], 15457)
        spark = create_spark(settings)
        try:
            metrics = build(settings, store, spark)
            prefix = metrics["silver_prefix"]
            articles = spark.read.format("delta").load(settings.s3a(f"{prefix}/articles"))
            mentions = spark.read.format("delta").load(settings.s3a(f"{prefix}/article_mentions"))
            rejects = spark.read.format("delta").load(settings.s3a(f"{prefix}/rejects"))
            self.assertEqual(articles.columns, [field.name for field in ARTICLE_FIELDS])
            self.assertEqual(articles.count(), metrics["output_count"])
            self.assertEqual(mentions.count(), metrics["article_mentions_count"])
            self.assertEqual(rejects.count(), metrics["invalid_count"])
            self.assertEqual(metrics["input_count"], metrics["output_count"] + metrics["duplicate_count"] + metrics["invalid_count"])
            self.assertGreater(metrics["duplicate_count"], 0)
            self.assertGreaterEqual(metrics["invalid_count"], 25)
            self.assertEqual(json.loads(store.get_bytes(f"{prefix}/metrics.json"))["input_count"], 15457)
        finally:
            spark.stop()


if __name__ == "__main__":
    unittest.main()
