"""Contract-focused tests that run without Spark or object storage."""

from pathlib import Path
import tempfile
import unittest

from src.news_pipeline.bronze import ingest
from src.news_pipeline.config import Settings
from src.news_pipeline.normalize import canonical_url, normalize_observation, normalize_text, published_at


class MemoryStore:
    def __init__(self):
        self.items = {}
        self.uploads = 0

    def ensure_bucket(self):
        pass

    def exists(self, key):
        return key in self.items

    def upload_file(self, path, key):
        self.items[key] = Path(path).read_bytes()
        self.uploads += 1

    def put_bytes(self, key, body, content_type="application/json"):
        self.items[key] = body

    def get_bytes(self, key):
        return self.items[key]


class PipelineUnitTest(unittest.TestCase):
    def test_bronze_preserves_bytes_and_replay(self):
        raw = b'[ { "_id": "old-export-id", "context": null }, 42 ]\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.json"
            path.write_bytes(raw)
            settings = Settings(source_file=str(path))
            store = MemoryStore()
            first = ingest(settings, store)
            second = ingest(settings, store)
            self.assertEqual(first, second)
            self.assertEqual(store.items[first["raw_key"]], raw)
            self.assertEqual(store.uploads, 1)
            self.assertEqual(first["record_count"], 2)

    def test_text_and_url_normalization(self):
        self.assertEqual(normalize_text("<p>A&amp;B</p><script>bad</script><p>Ca\u0301</p>"), "A&B Cá")
        self.assertEqual(normalize_text("Tin chính\nNguồn: CafeF\n", body=True), "Tin chính")
        self.assertEqual(canonical_url("HTTPS://CAFEF.VN/a/?x=1#frag", "cafef.vn"), "https://cafef.vn/a?x=1")
        with self.assertRaises(ValueError):
            canonical_url("https://example.com/a", "cafef.vn")

    def test_timestamp_policy(self):
        parsed = published_at("02-02-2026 - 07:32 AM")
        self.assertEqual(parsed.utcoffset().total_seconds(), 7 * 3600)
        self.assertIsNone(published_at("28-01-2026 - 16:44 PM"))

    def test_article_contract_and_rejects(self):
        row = {
            "link": "https://cafef.vn/a.chn", "title": "Tiêu đề", "summary": "Mô tả",
            "context": "Tin\nNguồn: CafeF", "post date": "28-01-2026 - 16:44 PM",
            "ticket symbol": "ACB", "ticket name": "Ngân hàng Á Châu", "keyword": "ACB",
            "page": 1, "index": 0, "_id": "export-id",
        }
        result = normalize_observation(row, 0, "batch", "cafef.vn", "cafef-v1")["valid"]
        self.assertEqual(result["content"], "Tin")
        self.assertIsNone(result["published_at"])
        self.assertEqual(result["published_at_raw"], row["post date"])
        self.assertIsNone(result["crawled_at"])
        self.assertNotIn("_id", result)
        reject = normalize_observation({**row, "context": None}, 4, "batch", "cafef.vn", "cafef-v1")["reject"]
        self.assertEqual(reject["source_row_position"], 4)
        self.assertEqual(reject["source_index"], 0)
        self.assertEqual(normalize_observation(3, 5, "batch", "cafef.vn", "cafef-v1")["reject"]["reason"], "not_an_object")


if __name__ == "__main__":
    unittest.main()
