"""Pure transformation and adapter-contract tests for Phase 02."""

from datetime import datetime, timezone
import uuid
import unittest

from src.news_pipeline.chunking import ArticleChunker
from src.news_pipeline.embedding import EmbeddingProvider
from src.news_pipeline.enrichment import NoOpEnricher
from src.news_pipeline.qdrant_index import payload_from_chunk, point_id
from tests.gold_fakes import DeterministicTestEmbeddingProvider


def sample_article(content: str) -> dict:
    return {
        "article_id": "article-1",
        "content_hash": "content-hash-1",
        "content": content,
        "title": "Lãi suất ACB",
        "source": "cafef.vn",
        "source_url": "https://cafef.vn/acb.chn",
        "published_at": datetime(2026, 2, 2, 1, 0, tzinfo=timezone.utc),
        "stock_symbols": ["ACB"],
        "processing_version": "cafef-v1.1",
        "source_ingestion_id": "batch-1",
    }


class GoldUnitTest(unittest.TestCase):
    def test_short_article_and_metadata(self):
        article = NoOpEnricher().enrich(sample_article("ACB tăng lãi suất."))
        chunks = ArticleChunker(80, 12).chunks_for_article(article)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], article["content"])
        self.assertEqual(chunks[0]["article_id"], article["article_id"])
        self.assertEqual(chunks[0]["source_url"], article["source_url"])
        self.assertEqual(chunks[0]["stock_symbols"], ["ACB"])
        self.assertIsNone(chunks[0]["entities"])
        self.assertEqual(chunks[0]["enrichment_status"], "unavailable")

    def test_deterministic_ids_and_content_version(self):
        article = NoOpEnricher().enrich(sample_article("Tin chứng khoán. " * 30))
        chunker = ArticleChunker(80, 12)
        first = chunker.chunks_for_article(article)
        second = chunker.chunks_for_article(article)
        self.assertEqual(first, second)
        self.assertEqual([item["chunk_index"] for item in first], list(range(len(first))))
        self.assertEqual(len({item["chunk_id"] for item in first}), len(first))
        changed = {**article, "content_hash": "new-hash"}
        self.assertNotEqual(first[0]["chunk_id"], chunker.chunks_for_article(changed)[0]["chunk_id"])
        self.assertNotEqual(first[0]["chunk_id"], ArticleChunker(100, 12).chunks_for_article(article)[0]["chunk_id"])

    def test_boundaries_overlap_and_long_article(self):
        text = " ".join(f"word{i}" for i in range(90))
        chunks = ArticleChunker(70, 15).split(text)
        self.assertGreater(len(chunks), 5)
        self.assertTrue(all(chunk and len(chunk) <= 70 for chunk in chunks))
        self.assertTrue(all(set(left.split()) & set(right.split()) for left, right in zip(chunks, chunks[1:])))
        self.assertEqual(ArticleChunker(70, 15).split(""), [])

    def test_embedding_port_and_payload(self):
        provider: EmbeddingProvider = DeterministicTestEmbeddingProvider()
        vectors = provider.embed_documents(["lãi suất ACB", "lãi suất ACB"])
        self.assertEqual(vectors[0], vectors[1])
        self.assertEqual(len(provider.embed_query("lãi suất ACB")), provider.dimension)
        chunk = ArticleChunker(80, 12).chunks_for_article(NoOpEnricher().enrich(sample_article("Lãi suất ACB.")))[0]
        payload = payload_from_chunk(chunk, provider.model_id)
        self.assertEqual(payload["article_id"], "article-1")
        self.assertEqual(payload["stock_symbols"], ["ACB"])
        self.assertIn("2026-02-02", payload["published_at"])
        self.assertEqual(point_id(chunk["chunk_id"], provider.model_id), point_id(chunk["chunk_id"], provider.model_id))
        uuid.UUID(point_id(chunk["chunk_id"], provider.model_id))


if __name__ == "__main__":
    unittest.main()
