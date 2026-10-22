"""A scanner or an exit-zero legacy CLI must not authorize cloud migration."""

import unittest

from tools.phase10 import decision
from tools.supply_chain_audit import independent_requirement_groups


class ReadinessBoundaryTest(unittest.TestCase):
    def test_missing_evidence_is_no_go(self):
        value = decision({}, {}, {}, {})
        self.assertEqual(value["P10-OVERALL"], "NO-GO")
        self.assertFalse(value["current_local_scans_clean"])
        self.assertFalse(value["migration_authorized"])

    def test_functional_phase9_pass_with_pending_time_is_not_verified(self):
        value = decision(
            {"status": "FAIL"},
            {
                "status": "PASS",
                "overall": "PENDING",
                "burnin_24h": "PENDING",
                "burnin_72h": "PENDING",
            },
            {"status": "PASS"},
            {},
            {"status": "PASS"},
        )
        self.assertEqual(value["P10-HISTORY-GATE"], "FAIL")
        self.assertEqual(value["P10-P09-DEPENDENCY"], "PENDING")
        self.assertEqual(value["P10-CODE-REGRESSION"], "PASS")

    def test_clean_scans_do_not_invent_issuer_invalidation_or_signoff(self):
        scopes = {
            mode: {"status": "PASS"} for mode in ("working-tree", "staged", "history")
        }
        value = decision(
            {"status": "PASS"},
            {
                "status": "PASS",
                "overall": "PASS",
                "burnin_24h": "PASS",
                "burnin_72h": "PASS",
            },
            {"status": "PASS"},
            {"scopes": scopes},
            {"status": "PASS"},
        )
        self.assertTrue(value["current_local_scans_clean"])
        self.assertEqual(value["P10-P09-DEPENDENCY"], "VERIFIED")
        self.assertEqual(value["P10-OVERALL"], "NO-GO")
        self.assertEqual(value["credential_invalidation"], "NOT_VERIFIED")
        self.assertEqual(value["owner_signoff"], "NOT_PROVIDED")

    def test_recent_guard_failure_is_not_hidden_by_previous_regression_pass(self):
        value = decision({}, {}, {"status": "PASS"}, {}, {"status": "FAIL"})
        self.assertEqual(value["P10-CODE-REGRESSION"], "FAIL")

    def test_shadowed_installed_versions_are_audited_without_solver_conflict(self):
        versions = [("package-a", "1.0"), ("package_a", "2.0"), ("other", "3.0")]
        groups = independent_requirement_groups(versions)
        self.assertEqual({row for group in groups for row in group}, set(versions))
        self.assertEqual(len(groups), 2)
        self.assertTrue(
            all(
                len({n.lower().replace("_", "-") for n, _ in group}) == len(group)
                for group in groups
            )
        )


if __name__ == "__main__":
    unittest.main()
