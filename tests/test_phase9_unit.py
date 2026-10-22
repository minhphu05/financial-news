"""Phase09 policy and closed-window evidence tests; never issue public HTTP."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
import unittest

from src.crawling.jobs import crawl
from src.crawling.policy import (
    batch_limit,
    effective_policy,
    failure_category,
    gate,
    retry_delay,
)
from src.crawling.reporting import aggregate, latency_summary, timestamp
from src.crawling.sources import SOURCES, ParseError
from src.crawling.http_client import FetchError


def policy(**overrides):
    source = SOURCES["cafef"]
    return effective_policy(
        source,
        {
            "adapter": source.key,
            "raw_schema_version": source.raw_schema_version,
            "parser_version": source.parser_version,
            "max_articles": 3,
            "max_attempts": 3,
            "recent_days": 7,
            "recheck_hours": 6,
            "request_interval_seconds": 3,
            "discovery_urls": [source.listing],
            "user_agent": "FinancialNewsTest/1",
            "processing_version": "fixture-phase9-v1",
            **overrides,
        },
    )


class PolicyTests(unittest.TestCase):
    def test_airflow_adapter_distinguishes_scheduled_and_manual_fixture(self):
        import os
        from src.crawling.airflow_jobs import main

        env = {
            "CRAWLER_SOURCE_KEY": "cafef",
            "CRAWLER_STAGE": "crawl",
            "CRAWLER_SELECTED_SOURCES": '["cafef"]',
            "CRAWLER_FIXTURE_MODE": "true",
            "CRAWLER_ALLOW_LIVE": "false",
            "CRAWLER_SCHEDULED_LIVE_ALLOWED": "true",
        }
        for run_type in ("manual", "scheduled"):
            with (
                patch.dict(os.environ, {**env, "CRAWLER_AIRFLOW_RUN_TYPE": run_type}),
                patch(
                    "src.crawling.airflow_jobs.crawl",
                    return_value={"status": "SUCCESS"},
                ) as call,
            ):
                main()
                if run_type == "scheduled":
                    self.assertTrue(call.call_args.kwargs["scheduled"])
                    self.assertTrue(call.call_args.kwargs["allow_live"])
                    self.assertNotIn("client", call.call_args.kwargs)
                else:
                    self.assertTrue(call.call_args.kwargs["client"].is_fixture)

    def test_live_is_fail_closed_but_fixture_remains_available(self):
        p = policy()
        self.assertEqual(gate(p, allow_live=True), "source_live_disabled")
        self.assertIsNone(gate(p, fixture=True))
        self.assertEqual(gate(policy(live_enabled=True)), "live_opt_in_required")
        self.assertIsNone(gate(policy(live_enabled=True), allow_live=True))

    def test_disabled_source_skips_before_http_or_storage_initialization(self):
        repo = Mock()
        repo.config.return_value = {**policy(), "enabled": False}
        with (
            patch(
                "src.crawling.jobs.HttpClient",
                side_effect=AssertionError("HTTP construction forbidden"),
            ),
            patch(
                "src.crawling.jobs.create_object_store",
                side_effect=AssertionError("storage forbidden"),
            ),
        ):
            result = crawl("cafef", repository=repo, allow_live=True)
        self.assertEqual(result["status"], "SKIPPED")
        self.assertEqual(result["skip_reason"], "source_disabled")
        repo.record_skip.assert_called_once()

    def test_source_cap_cannot_be_raised_by_dag_limit(self):
        self.assertEqual(batch_limit(20, policy(max_articles=2)), 2)
        for invalid in (0, 21, True, 1.5):
            with self.assertRaises(ValueError):
                batch_limit(invalid, policy())

    def test_policy_rejects_wrong_types_unbounded_or_nonfinite_values(self):
        for change in (
            {"live_enabled": "false"},
            {"request_interval_seconds": float("nan")},
            {"request_timeout_seconds": 0},
            {"http_retries": 4},
            {"publish_max_batches": 21},
            {"max_articles": True},
            {"discovery_urls": ["https://example.com/news"]},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                policy(**change)

    def test_retry_delay_is_exponential_jittered_and_capped(self):
        p = policy()
        with patch("src.crawling.policy.random.uniform", return_value=3):
            self.assertEqual(retry_delay(1, p), 63)
            self.assertEqual(retry_delay(2, p), 123)
            self.assertEqual(retry_delay(30, p), 3600)

    def test_parser_fetch_and_block_categories_are_distinct(self):
        self.assertEqual(failure_category(ParseError("missing_body")), "PARSER_FAILURE")
        self.assertEqual(
            failure_category(FetchError("timeout", retryable=True)), "FETCH_FAILURE"
        )
        for code in (403, 429):
            self.assertEqual(
                failure_category(FetchError("blocked", code)), "BLOCKED_OR_RATE_LIMITED"
            )


class ReportTests(unittest.TestCase):
    def test_empty_alerts_are_not_claimed_as_complete_history_without_data(self):
        from tools.phase9 import daily

        with (
            patch("tools.phase9.container_json", return_value={"data_gaps": []}),
            patch("tools.phase9.prom", return_value=[]),
        ):
            report = daily(self.start, self.end)
        self.assertFalse(report["alert_history_coverage"]["complete"])
        self.assertTrue(any("missing Prometheus" in gap for gap in report["data_gaps"]))
        end = self.start + timedelta(seconds=60)
        with (
            patch("tools.phase9.container_json", return_value={"data_gaps": []}),
            patch(
                "tools.phase9.prom",
                side_effect=[
                    [],
                    [
                        {
                            "values": [
                                [self.start.timestamp(), "1"],
                                [end.timestamp(), "1"],
                            ]
                        }
                    ],
                ],
            ),
        ):
            report = daily(self.start, end)
        self.assertTrue(report["alert_history_coverage"]["complete"])
        self.assertEqual(report["alert_summary"], [])

    def setUp(self):
        self.start = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.end = self.start + timedelta(days=1)

    def test_closed_window_excludes_future_completion_and_reconstructs_backlog(self):
        runs = [
            {
                "source": "cafef",
                "crawl_run_id": "a",
                "trigger_type": "SCHEDULED",
                "status": "SUCCESS",
                "started_at": self.start,
                "finished_at": self.end + timedelta(seconds=1),
                "metrics": {"fetched": 2},
            }
        ]
        batches = [
            {
                "source": "cafef",
                "batch_id": "b",
                "created_at": self.start,
                "published_at": self.end + timedelta(seconds=1),
            }
        ]
        report = aggregate(
            self.start,
            self.end,
            runs,
            batches,
            [],
            observed_at=self.end + timedelta(days=1),
        )
        row = report["sources"]["cafef"]
        self.assertEqual(row["completed_runs"], 0)
        self.assertEqual(row["fetched"], 0)
        self.assertEqual(row["pending_batches_end"], 1)
        self.assertEqual(row["oldest_pending_age_seconds"], 86400)

    def test_latency_uses_durable_landing_and_deduplicates_stage_attempts(self):
        batches = [
            {
                "source": "cafef",
                "batch_id": "b",
                "created_at": self.start,
                "published_at": self.start + timedelta(minutes=5),
                "first_landing_at": self.start,
            }
        ]
        stages = [
            {
                "batch_id": "b",
                "stage_name": "2026-10-20:silver_merge",
                "status": "SUCCESS",
                "finished_at": self.start + timedelta(seconds=60),
            }
        ] * 2
        row = aggregate(
            self.start, self.end, [], batches, stages, observed_at=self.end
        )["sources"]["cafef"]
        self.assertEqual(row["landing_to_silver"]["sample_count"], 1)
        self.assertEqual(row["landing_to_silver"]["p50_seconds"], 60)
        self.assertIsNone(row["landing_to_silver"]["p95_seconds"])
        self.assertEqual(row["pending_batches_end"], 0)

    def test_missing_historical_timestamps_never_become_invented_latency(self):
        batch = {
            "source": "cafef",
            "batch_id": "b",
            "created_at": self.start,
            "published_at": None,
        }
        stage = {
            "batch_id": "b",
            "stage_name": "silver_merge",
            "status": "SUCCESS",
            "finished_at": self.start + timedelta(seconds=60),
        }
        row = aggregate(
            self.start, self.end, [], [batch], [stage], observed_at=self.end
        )["sources"]["cafef"]
        self.assertEqual(row["landing_to_silver"]["sample_count"], 0)
        self.assertTrue(row["data_gaps"])

    def test_timezones_required_future_windows_rejected(self):
        with self.assertRaises(ValueError):
            timestamp("2026-10-20T00:00:00")
        with self.assertRaises(ValueError):
            aggregate(self.start, self.end, [], [], [], observed_at=self.start)
        self.assertEqual(timestamp("2026-10-20T07:00:00+07:00"), self.start)

    def test_p95_requires_recorded_samples(self):
        self.assertIsNone(latency_summary([])["p50_seconds"])
        self.assertIsNone(latency_summary([1, 2])["p95_seconds"])
        self.assertEqual(latency_summary(list(range(20)))["p95_seconds"], 18.05)


if __name__ == "__main__":
    unittest.main()
