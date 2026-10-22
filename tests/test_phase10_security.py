"""Security boundaries: index bytes, redaction, fail-closed and safe sentinel."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import security_scan


def sentinel():
    # This deliberately invalid marker is detected only by our synthetic rule.
    return "FINNEWS_" + "SYNTHETIC_SECRET_" + "0123456789ABCDEF01234567"


class SecurityBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="financial-news-guard-test-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(
            ["git", "init", "-q", str(self.root)], check=True, capture_output=True
        )
        self.binary = security_scan.resolve_binary()

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True
        )

    def test_harmless_placeholder_passes(self):
        (self.root / "example.env").write_text("SERVICE_TOKEN=change-me-for-local\n")
        result = security_scan.scan("working-tree", self.root, self.binary)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["exit_code"], 0)

    def test_synthetic_worktree_leak_rejected_without_value(self):
        (self.root / "leak.txt").write_text(sentinel())
        result = security_scan.scan("working-tree", self.root, self.binary)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(
            result["findings"][0]["rule"], "financial-news-synthetic-secret"
        )
        self.assertNotIn(sentinel(), json.dumps(result))

    def test_staged_secret_cannot_be_hidden_by_clean_worktree(self):
        file = self.root / "example.txt"
        file.write_text(sentinel())
        self.git("add", "example.txt")
        file.write_text("harmless unstaged replacement\n")
        self.assertEqual(
            security_scan.scan("working-tree", self.root, self.binary)["status"], "PASS"
        )
        result = security_scan.scan("staged", self.root, self.binary)
        self.assertEqual(result["status"], "FAIL")
        self.assertNotIn(sentinel(), json.dumps(result))

    def test_upstream_rules_are_enabled_with_an_invalid_private_key_fixture(self):
        # Malformed public fixture, no cryptographic key material. Tests upstream rules,
        # independently of our custom sentinel rule, without using provider credentials.
        marker = (
            "-----"
            + "BEGIN PRIVATE KEY"
            + "-----\n"
            + "THIS_IS_NOT_A_KEY\n" * 8
            + "-----"
            + "END PRIVATE KEY"
            + "-----\n"
        )
        (self.root / "invalid-fixture.txt").write_text(marker)
        result = security_scan.scan("working-tree", self.root, self.binary)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("private-key", {r["rule"] for r in result["findings"]})
        self.assertNotIn(marker, json.dumps(result))

    def test_symlink_is_not_followed_or_misreported_clean(self):
        (self.root / "outside").symlink_to("/etc/hosts")
        result = security_scan.scan("working-tree", self.root, self.binary)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("symlink_not_followed", result["coverage_gaps"])

    def test_ignored_env_is_separate_from_committable_surface(self):
        (self.root / ".gitignore").write_text(".env\n")
        (self.root / ".env").write_text(sentinel())
        self.assertEqual(
            security_scan.scan("working-tree", self.root, self.binary)["status"], "PASS"
        )
        result = security_scan.scan("ignored-config", self.root, self.binary)
        self.assertEqual(result["status"], "FAIL")
        self.assertNotIn(sentinel(), json.dumps(result))

    def test_scanning_does_not_change_source_permissions(self):
        file = self.root / "example.txt"
        file.write_text("safe\n")
        file.chmod(0o640)
        security_scan.scan("working-tree", self.root, self.binary)
        self.assertEqual(file.stat().st_mode & 0o777, 0o640)

    def test_missing_scanner_blocks_instead_of_pass(self):
        result = security_scan.scan(
            "working-tree", self.root, "/nonexistent/security-tool"
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["exit_code"], 2)

    def test_wrong_version_is_blocked(self):
        fake = subprocess.CompletedProcess([], 0, "0.0.0\n", "")
        with patch.object(security_scan.subprocess, "run", return_value=fake):
            result = security_scan.scan("history", self.root, self.binary)
        self.assertEqual(result["status"], "BLOCKED")

    def test_report_whitelist_drops_raw_context_and_secret_hash(self):
        row = {
            "RuleID": "synthetic",
            "File": "sample.txt",
            "StartLine": 1,
            "Commit": "a" * 40,
            "Secret": sentinel(),
            "Match": sentinel(),
            "Fingerprint": "never publish",
            "Message": sentinel(),
        }
        result = security_scan.safe_findings([row], self.root)
        self.assertNotIn(sentinel(), json.dumps(result))
        self.assertNotIn("Fingerprint", json.dumps(result))
        self.assertEqual(result[0]["commit"], "a" * 40)

    def test_cli_stdout_never_contains_sentinel(self):
        (self.root / "leak.txt").write_text(sentinel())
        with patch(
            "sys.argv",
            [
                "security_scan",
                "working-tree",
                "--root",
                str(self.root),
                "--gitleaks",
                self.binary,
            ],
        ):
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = security_scan.main()
        self.assertEqual(code, 1)
        self.assertNotIn(sentinel(), captured.getvalue())


if __name__ == "__main__":
    unittest.main()
