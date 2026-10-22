from datetime import datetime, timedelta, timezone
import unittest

from src.monitoring.crawler_metrics import collect


class ContinuousMetricsTest(unittest.TestCase):
    def test_block_latch_is_not_lost_when_recent_event_window_expires(self):
        now = datetime.now(timezone.utc)
        samples = [
            s
            for family in collect(
                {
                    "crawl_latches": [
                        {
                            "source": "cafef",
                            "blocked_at": now - timedelta(days=1),
                            "cooldown_until": now + timedelta(minutes=2),
                        }
                    ]
                }
            )
            for s in family.samples
        ]
        self.assertEqual(
            next(
                s.value
                for s in samples
                if s.name == "financial_news_crawler_source_blocked"
            ),
            1,
        )
        self.assertEqual(
            next(
                s.value
                for s in samples
                if s.name == "financial_news_crawler_cooldown_until_timestamp_seconds"
            ),
            now.timestamp() + 120,
        )

    def test_skip_without_duration_does_not_fabricate_zero(self):
        now = datetime.now(timezone.utc)
        samples = [
            s
            for family in collect(
                {
                    "crawl_latest": [
                        {
                            "source": "cafef",
                            "started_at": now,
                            "metrics": {"skip_reason": "source_live_disabled"},
                        }
                    ],
                    "crawl_heartbeat": [{"source": "cafef", "finished_at": now}],
                }
            )
            for s in family.samples
        ]
        self.assertFalse(
            any(
                s.name == "financial_news_crawler_last_duration_seconds"
                for s in samples
            )
        )
        self.assertTrue(
            any(
                s.name == "financial_news_crawler_last_completed_timestamp_seconds"
                for s in samples
            )
        )

    def test_heartbeat_landing_pending_and_serving_are_separate(self):
        now = datetime.now(timezone.utc)
        samples = [
            s
            for family in collect(
                {
                    "crawl_heartbeat": [{"source": "cafef", "finished_at": now}],
                    "crawl_landing": [
                        {"source": "cafef", "landed_at": now - timedelta(seconds=10)}
                    ],
                    "crawl_pending": [
                        {
                            "source": "cafef",
                            "count": 1,
                            "oldest_created_at": now - timedelta(seconds=30),
                        }
                    ],
                    "crawl_policy": [
                        {
                            "source": "cafef",
                            "live_enabled": False,
                            "heartbeat_max_age_seconds": 7200,
                        }
                    ],
                    "crawl_layers": [
                        {
                            "source": "cafef",
                            "stage": "silver_merge",
                            "finished_at": now,
                            "latency_seconds": 10,
                        }
                    ],
                    "crawl_batches": [
                        {"source": "cafef", "status": "FAILED", "count": 1}
                    ],
                    "crawl_exhausted": [{"source": "cafef", "count": 1}],
                }
            )
            for s in family.samples
        ]
        by_name = {s.name: s for s in samples}
        self.assertEqual(
            by_name["financial_news_crawler_last_completed_timestamp_seconds"].value,
            now.timestamp(),
        )
        self.assertEqual(
            by_name["financial_news_crawler_last_landing_timestamp_seconds"].value,
            now.timestamp() - 10,
        )
        self.assertEqual(
            by_name["financial_news_crawler_oldest_pending_timestamp_seconds"].value,
            now.timestamp() - 30,
        )
        self.assertEqual(by_name["financial_news_crawler_live_enabled"].value, 0)
        self.assertEqual(
            by_name["financial_news_crawler_landing_to_layer_seconds"].value, 10
        )
        for s in samples:
            self.assertLessEqual(
                set(s.labels), {"source", "data_kind", "status", "outcome", "layer"}
            )
            if "layer" in s.labels:
                self.assertIn(
                    s.labels["layer"],
                    {"silver", "gold_rag", "gold_analytics", "qdrant", "duckdb"},
                )

    def test_oldest_pending_survives_bounded_fixture_label_merging(self):
        now = datetime.now(timezone.utc)
        samples = [
            s
            for family in collect(
                {
                    "crawl_pending": [
                        {
                            "source": "fixture-a:cafef",
                            "count": 1,
                            "oldest_created_at": now,
                        },
                        {
                            "source": "fixture-b:cafef",
                            "count": 1,
                            "oldest_created_at": now - timedelta(minutes=3),
                        },
                    ]
                }
            )
            for s in family.samples
        ]
        pending = next(
            s for s in samples if s.name == "financial_news_crawler_pending_batches"
        )
        oldest = next(
            s
            for s in samples
            if s.name == "financial_news_crawler_oldest_pending_timestamp_seconds"
        )
        self.assertEqual(pending.value, 2)
        self.assertEqual(oldest.value, now.timestamp() - 180)


if __name__ == "__main__":
    unittest.main()
