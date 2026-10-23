"""Synthetic pilot inputs verify safety gates, never establish real uptime."""

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from src.crawling.burnin import assess, assess_pilot, verified_24h_report
from src.crawling.policy import gate
from tests import test_phase9_burnin
from tools import phase9_pilot


class PilotTests(unittest.TestCase):
    def setUp(self):
        base = test_phase9_burnin.BurninGateTests()
        base.setUp()
        self.start = base.start
        self.session = {**base.session, "kind": "pilot", "hours": 4}
        self.samples = base.samples()[:49]

    def test_four_hours_can_only_pass_as_pilot(self):
        result = assess_pilot(
            self.session, self.samples, now=self.start + timedelta(hours=4)
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["burnin_24h"], "PENDING")
        self.assertEqual(result["burnin_72h"], "PENDING")
        with self.assertRaises(ValueError):
            assess(self.session, self.samples)

    def test_clock_time_without_coverage_is_not_enough(self):
        self.assertNotEqual(
            assess_pilot(
                self.session, self.samples[:2], now=self.start + timedelta(hours=4)
            )["status"],
            "PASS",
        )
        self.assertEqual(
            assess_pilot(
                self.session, self.samples[:2], now=self.start + timedelta(minutes=5)
            )["status"],
            "PENDING",
        )

    def test_reboot_and_hard_stop_fail_pilot(self):
        for change in ({"boot_id": "other"}, {"hard_stop_reasons": ["source blocked"]}):
            samples = [*self.samples[:-1], {**self.samples[-1], **change}]
            self.assertEqual(
                assess_pilot(
                    self.session, samples, now=self.start + timedelta(hours=4)
                )["status"],
                "FAIL",
            )

    def test_pilot_report_cannot_authorize_72_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.report.json"
            path.write_text(
                json.dumps({"status": "PASS", "required_hours": 4, "kind": "pilot"})
            )
            with self.assertRaises(ValueError):
                verified_24h_report(path)

    def test_expired_and_invalid_policy_deadlines_deny_live_but_not_fixture(self):
        for expiry, expected in (
            ("2000-01-01T00:00:00+00:00", "source_live_expired"),
            ("2099-01-01T00:00:00", "source_live_deadline_invalid"),
            ("bad", "source_live_deadline_invalid"),
        ):
            p = {"enabled": True, "live_enabled": True, "live_until": expiry}
            self.assertEqual(gate(p, allow_live=True), expected)
            self.assertIsNone(gate(p, fixture=True))
        self.assertIsNone(
            gate(
                {
                    "enabled": True,
                    "live_enabled": True,
                    "live_until": "2099-01-01T00:00:00+00:00",
                },
                allow_live=True,
            )
        )

    def test_stop_attempts_every_source_even_if_pause_and_first_source_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.json"
            path.write_text(json.dumps({"sources": ["cafef", "vnexpress"]}))
            with (
                patch.object(phase9_pilot, "command", side_effect=TimeoutError),
                patch.object(
                    phase9_pilot, "container_json", side_effect=[RuntimeError, {}]
                ) as policy,
            ):
                result = phase9_pilot.stop(path, "incident")
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(policy.call_count, 2)
            with (
                patch.object(phase9_pilot, "command") as command,
                patch.object(phase9_pilot, "container_json", return_value={}),
            ):
                command.return_value.returncode = 0
                result = phase9_pilot.stop(path, "deadline")
                self.assertEqual(result["reason"], "incident")

    def test_collector_error_runs_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.json"
            path.write_text(json.dumps(self.session))
            path.with_suffix(".samples.json").write_text("[]")
            with (
                patch.object(phase9_pilot, "sample", side_effect=RuntimeError),
                patch.object(phase9_pilot, "stop") as stop,
                patch.object(phase9_pilot, "report", return_value={"status": "FAIL"}),
            ):
                self.assertEqual(phase9_pilot.watch(path), 1)
                stop.assert_called_once()
                self.assertIn("RuntimeError", stop.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
