"""Full sample Silver -> Gold -> serving integration; uses free test vectors for Qdrant."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from pyspark.sql import functions as F

from src.news_pipeline.analytics import build as build_analytics
from src.news_pipeline.duckdb_serving import publish, query
from src.news_pipeline.gold_config import ANALYTICS_DATASETS, GoldSettings
from src.news_pipeline.gold_rag import build as build_rag
from src.news_pipeline.qdrant_index import QdrantChunkIndex
from src.news_pipeline.silver import create_spark
from src.news_pipeline.silver_reader import SilverArticleRepository
from src.news_pipeline.storage import S3ObjectStore
from tests.gold_fakes import DeterministicTestEmbeddingProvider


class GoldIntegrationTest(unittest.TestCase):
    def test_full_sample_and_serving(self):
        settings = GoldSettings.from_env()
        spark = create_spark(settings.news)
        store = S3ObjectStore(settings.news)
        try:
            silver = SilverArticleRepository(spark, settings).articles()
            silver_count = silver.count()
            self.assertGreater(silver_count, 0)

            rag_metrics = build_rag(settings, spark, store)
            documents_uri = settings.news.s3a(f"{settings.rag_prefix}/documents")
            documents = spark.read.format("delta").load(documents_uri)
            chunks = spark.read.format("delta").load(settings.chunks_uri)
            self.assertEqual(documents.count(), silver_count)
            self.assertEqual(chunks.count(), rag_metrics["gold_chunks_produced"])
            self.assertGreater(rag_metrics["gold_chunks_produced"], silver_count)
            self.assertEqual(rag_metrics["empty_rejected_chunk_count"], 0)
            self.assertEqual(chunks.filter(F.length(F.trim("text")) == 0).count(), 0)
            self.assertEqual(chunks.select("chunk_id").distinct().count(), chunks.count())
            self.assertEqual(chunks.select("article_id").distinct().count(), silver_count)
            self.assertTrue(store.list_keys(f"{settings.rag_prefix}/chunks/_delta_log/"))
            self.assertTrue(store.list_keys(f"{settings.rag_prefix}/documents/_delta_log/"))

            provider = DeterministicTestEmbeddingProvider()
            index = QdrantChunkIndex(
                settings.qdrant_url, f"news_gold_test_{uuid.uuid4().hex}", provider.dimension
            )
            try:
                sample = [row.asDict(recursive=True) for row in chunks.orderBy("article_id", "chunk_index").limit(8).collect()]
                vectors = provider.embed_documents([row["text"] for row in sample])
                index.ensure_collection()
                first_ids = index.upsert(sample, vectors, provider.model_id)
                second_ids = index.upsert(sample, vectors, provider.model_id)
                self.assertEqual(first_ids, second_ids)
                self.assertEqual(index.count(), len(sample))
                self.assertEqual(index.reconcile(set(first_ids)), 0)
                hits = index.search(provider.embed_query(sample[0]["text"]), 5)
                self.assertIn(sample[0]["chunk_id"], [hit["chunk_id"] for hit in hits])
                self.assertEqual(hits[0]["source_url"], sample[0]["source_url"])
            finally:
                if index.collection in {item.name for item in index.client.get_collections().collections}:
                    index.client.delete_collection(index.collection)
                index.close()

            analytics_metrics = build_analytics(settings, spark, store)
            self.assertEqual(analytics_metrics["input_article_count"], silver_count)
            manifest = json.loads(store.get_bytes(f"{settings.analytics_prefix}/manifest.json"))
            self.assertEqual(set(manifest["datasets"]), set(ANALYTICS_DATASETS))
            for name in ANALYTICS_DATASETS:
                self.assertEqual(
                    spark.read.parquet(settings.analytics_uri(name)).count(),
                    analytics_metrics["output_aggregation_rows"][name],
                )
            with tempfile.TemporaryDirectory(prefix="news-gold-test-") as directory:
                test_settings = replace(settings, duckdb_path=str(Path(directory) / "analytics.duckdb"))
                serving_metrics = publish(test_settings, store, record_metrics=False)
                self.assertEqual(serving_metrics["input_article_count"], silver_count)
                source_total = query(test_settings, "SELECT SUM(article_count) FROM vw_news_by_source")[0][0]
                status_total = query(test_settings, "SELECT SUM(article_count) FROM vw_news_publication_status")[0][0]
                self.assertEqual(source_total, silver_count)
                self.assertEqual(status_total, silver_count)
        finally:
            spark.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
