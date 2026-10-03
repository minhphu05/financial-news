import unittest
from datetime import datetime, timezone

from src.monitoring.crawler_metrics import collect, labels


class CrawlerMetricsTest(unittest.TestCase):
    def test_no_article_url_or_run_labels(self):
        snapshot = {
            "crawl_runs": [
                {
                    "source": "cafef",
                    "status": "SUCCESS",
                    "count": 2,
                    "fetched": 3,
                    "changed": 2,
                }
            ],
            "crawl_latest": [
                {
                    "source": "cafef",
                    "started_at": datetime.now(timezone.utc),
                    "metrics": {"duration_seconds": 5},
                }
            ],
            "crawl_sources": [
                {"source": "cafef", "last_success_at": datetime.now(timezone.utc)}
            ],
            "crawl_frontier": [{"source": "cafef", "status": "SUCCESS", "count": 3}],
            "crawl_pending": [{"source": "cafef", "count": 1}],
        }
        samples = [s for family in collect(snapshot) for s in family.samples]
        self.assertTrue(samples)
        for sample in samples:
            self.assertLessEqual(
                set(sample.labels), {"source", "data_kind", "status", "outcome"}
            )
        self.assertTrue(
            any(
                s.name == "financial_news_crawler_articles_total"
                and s.labels["outcome"] == "fetched"
                and s.value == 3
                for s in samples
            )
        )

    def test_fixture_and_unknown_sources_are_bounded(self):
        self.assertEqual(labels("fixture-unit:cafef"), ["cafef", "fixture"])
        self.assertEqual(labels("https://unknown/run/random"), ["other", "live"])

    def test_pre_crawler_snapshot_is_compatible(self):
        self.assertEqual(sum(len(f.samples) for f in collect({})), 0)


if __name__ == "__main__":
    unittest.main()
