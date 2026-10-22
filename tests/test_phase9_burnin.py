"""Synthetic time inputs test the gate algorithm; these are not burn-in evidence."""

from datetime import datetime, timedelta, timezone
import unittest

from src.crawling.burnin import assess, verified_24h_report


class BurninGateTests(unittest.TestCase):
    def test_functional_pass_cannot_open_72h_gate(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acceptance.json"
            path.write_text(json.dumps({"status": "PASS", "scope": "functional only"}))
            with self.assertRaisesRegex(ValueError, "real_24h"):
                verified_24h_report(path)

    def setUp(self):
        self.start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.session = {
            "started_at": self.start.isoformat(),
            "hours": 24,
            "sample_interval_seconds": 300,
            "boot_id": "test-boot",
            "monotonic_start": 10,
            "sources": ["cafef"],
            "live_opt_in": True,
            "backup_reference": "synthetic-unit-test-only",
        }
        self.report = {
            "data_kind": "live",
            "sources": {
                "cafef": {
                    "scheduled_runs": 48,
                    "latest_successful_crawl": (
                        self.start + timedelta(hours=23)
                    ).isoformat(),
                    "pending_batches_end": 0,
                    "failed_runs": 0,
                    "partial_runs": 0,
                    "reconciliation": {"FAIL": 0},
                }
            },
        }

    def samples(self):
        return [
            {
                "observed_at": (self.start + timedelta(seconds=i)).isoformat(),
                "monotonic_seconds": 10 + i,
                "boot_id": "test-boot",
                "hard_stop_reasons": [],
                "report": self.report,
                "scheduler": {"overlapping_runs": False, "scheduled_runs": [{}, {}]},
            }
            for i in range(0, 86401, 300)
        ]

    def test_short_run_never_counts_as_24_hours(self):
        self.assertEqual(
            assess(
                self.session, self.samples()[:2], now=self.start + timedelta(minutes=5)
            )["status"],
            "PENDING",
        )

    def test_elapsed_time_without_samples_is_insufficient(self):
        self.assertEqual(
            assess(self.session, [], now=self.start + timedelta(days=4))["status"],
            "PENDING",
        )

    def test_complete_synthetic_input_satisfies_algorithm_only(self):
        self.assertEqual(
            assess(self.session, self.samples(), now=self.start + timedelta(days=1))[
                "status"
            ],
            "PASS",
        )

    def test_sleep_gap_and_monotonic_shortfall_prevent_pass(self):
        samples = self.samples()
        del samples[10:20]
        self.assertNotEqual(
            assess(self.session, samples, now=self.start + timedelta(days=1))["status"],
            "PASS",
        )
        samples = self.samples()
        samples[-1]["monotonic_seconds"] = 20
        self.assertNotEqual(
            assess(self.session, samples, now=self.start + timedelta(days=1))["status"],
            "PASS",
        )

    def test_reboot_and_hard_stop_fail(self):
        for change in (
            {"boot_id": "other-boot"},
            {"hard_stop_reasons": ["source blocked"]},
        ):
            samples = self.samples()
            samples[-1].update(change)
            self.assertEqual(
                assess(self.session, samples, now=self.start + timedelta(days=1))[
                    "status"
                ],
                "FAIL",
            )

    def test_fixture_and_unresolved_backlog_cannot_pass_live_gate(self):
        samples = self.samples()
        self.report["data_kind"] = "fixture"
        self.assertNotEqual(
            assess(self.session, samples, now=self.start + timedelta(days=1))["status"],
            "PASS",
        )
        self.report["data_kind"] = "live"
        self.report["sources"]["cafef"]["pending_batches_end"] = 1
        self.assertNotEqual(
            assess(self.session, samples, now=self.start + timedelta(days=1))["status"],
            "PASS",
        )


if __name__ == "__main__":
    unittest.main()
