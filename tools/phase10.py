#!/usr/bin/env python3
"""Local Phase10 evidence and fail-closed release review; no cloud/issuer writes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import security_scan  # noqa: E402 -- support direct CLI execution from repository tools/

OUT = ROOT / "artifacts/phase10"


def now():
    return datetime.now(timezone.utc).isoformat()


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read(name):
    path = OUT / name
    return json.loads(path.read_text()) if path.exists() else {}


def preflight():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    result = {
        "captured_at": now(),
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "HEAD"),
        "changes_count": len(git("status", "--porcelain").splitlines()),
        "local_refs_count": len(
            git("for-each-ref", "--format=%(refname)").splitlines()
        ),
        "shallow": git("rev-parse", "--is-shallow-repository"),
        "baseline_record": "preflight.json"
        if (OUT / "preflight.json").exists()
        else None,
        "no_credentials_or_remote_urls_retained": True,
    }
    write("preflight-latest.json", result)
    return 0


def phase6_gate():
    completed = subprocess.run(
        ["make", "release-audit"], cwd=ROOT, capture_output=True, text=True, timeout=180
    )
    try:
        audit, _ = json.JSONDecoder().raw_decode(
            completed.stdout[completed.stdout.index("{") :]
        )
    except (ValueError, json.JSONDecodeError):
        write(
            "phase6-gate.json",
            {
                "checked_at": now(),
                "status": "BLOCKED",
                "command_exit_code": completed.returncode,
            },
        )
        return 2
    # Preserve and honor the existing Phase06 checker; its CLI exit 0 is not a PASS.
    status = (
        "PASS"
        if completed.returncode == 0 and audit.get("status") == "PASS"
        else "FAIL"
    )
    write(
        "phase6-gate.json",
        {
            "checked_at": now(),
            "command": ["make", "release-audit"],
            "command_exit_code": completed.returncode,
            "status": status,
            "phase10_gate_exit_code": 0 if status == "PASS" else 1,
            "findings": audit.get("findings", {}),
            "no_checker_or_history_policy_changed": True,
        },
    )
    return 0 if status == "PASS" else 1


def scans():
    results = {}
    for mode in security_scan.MODES:
        result = security_scan.scan(mode)
        write(f"scan-{mode}.json", result)
        results[mode] = {"status": result["status"], "count": len(result["findings"])}
        print(json.dumps({"scope": mode, **results[mode]}), flush=True)
    write("security-scans.json", {"checked_at": now(), "scopes": results})
    # Ignored local config is triaged independently; never waive history/current findings.
    return (
        0
        if all(
            results[m]["status"] == "PASS"
            for m in ("working-tree", "staged", "history")
        )
        else 1
    )


def image_config_scans():
    results = []
    for image in (
        "financial-news-news-pipeline",
        "financial-news-airflow:2.11.2",
        "financial-news-metadata-tools:phase04",
    ):
        with tempfile.TemporaryDirectory(
            prefix="financial-news-image-config-"
        ) as private:
            root = Path(private)
            subprocess.run(
                ["git", "init", "-q", str(root)], capture_output=True, check=True
            )
            inspect = subprocess.run(
                ["docker", "image", "inspect", image], capture_output=True, text=True
            )
            history = subprocess.run(
                [
                    "docker",
                    "image",
                    "history",
                    "--no-trunc",
                    "--format",
                    "{{.CreatedBy}}",
                    image,
                ],
                capture_output=True,
                text=True,
            )
            if inspect.returncode or history.returncode:
                results.append({"image": image, "status": "BLOCKED"})
                continue
            metadata = json.loads(inspect.stdout)[0]
            envfile = root / "image-env.txt"
            envfile.write_text("\n".join(metadata.get("Config", {}).get("Env", [])))
            envfile.chmod(0o600)
            historyfile = root / "image-build-history.txt"
            historyfile.write_text(history.stdout)
            historyfile.chmod(0o600)
            result = security_scan.scan("working-tree", root)
            result.update(
                image=image,
                image_id=metadata["Id"],
                scope="Image Config.Env plus CreatedBy build instructions; not final files or deleted-layer blobs",
            )
            results.append(result)
    write(
        "image-config-scans.json",
        {
            "checked_at": now(),
            "images": results,
            "deleted_layer_files": "NOT_SCANNED",
            "registry_artifacts": "NOT_SCANNED",
        },
    )
    return 0 if all(r["status"] == "PASS" for r in results) else 1


def recorded_command(label, args, timeout=1200):
    result = {"label": label, "command": args, "started_at": now()}
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    # Child output may include service configuration; retain only counts and exit status.
    with tempfile.TemporaryFile() as stream:
        try:
            completed = subprocess.run(
                args,
                cwd=ROOT,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            result["exit_code"] = completed.returncode
        except subprocess.TimeoutExpired:
            result["exit_code"] = 124
        stream.seek(0)
        text = stream.read().decode(errors="replace")
        result["unittest_counts"] = [
            int(n) for n in re.findall(r"Ran (\d+) tests? in", text)
        ]
        result["skipped_counts"] = [int(n) for n in re.findall(r"skipped=(\d+)", text)]
        result["raw_output_retained"] = False
    result["finished_at"] = now()
    result["status"] = "PASS" if result["exit_code"] == 0 else "FAIL"
    write(label + ".json", result)
    print(
        json.dumps({k: result[k] for k in ("label", "exit_code", "unittest_counts")}),
        flush=True,
    )
    return result


def regressions():
    compose = ["docker", "compose"]
    base = [*compose, "run", "--rm", "--no-deps", "-e", "PYTHONDONTWRITEBYTECODE=1"]
    commands = [
        (
            "security-unit",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_phase10_security",
                "tests.test_phase10_readiness",
                "-v",
            ],
        ),
        (
            "pipeline-unit-db",
            [
                *base,
                "-e",
                "CRAWLER_DB_TESTS=1",
                "-e",
                "PHASE9_DB_TESTS=1",
                "news-pipeline",
                "python3",
                "-m",
                "unittest",
                "tests.test_news_pipeline_unit",
                "tests.test_news_gold_unit",
                "tests.test_pipeline_hardening",
                "tests.test_local_release_unit",
                "tests.test_crawling_parsers",
                "tests.test_crawling_state",
                "tests.test_phase9_unit",
                "tests.test_phase9_integration",
                "tests.test_phase9_burnin",
                "-v",
            ],
        ),
        (
            "monitoring-unit",
            [
                *base,
                "metadata-tools",
                "python3",
                "-m",
                "unittest",
                "tests.test_monitoring",
                "tests.test_crawler_metrics",
                "tests.test_phase9_metrics",
                "tests.test_metadata_control",
                "-v",
            ],
        ),
        (
            "airflow-dag-unit",
            [
                *compose,
                "exec",
                "-T",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "airflow-scheduler",
                "python3",
                "-m",
                "unittest",
                "tests.test_airflow_dags",
                "-v",
            ],
        ),
        (
            "five-source-fixture",
            [
                *base,
                "--user",
                "0",
                "news-pipeline",
                "/opt/spark/bin/spark-submit",
                "--packages",
                "io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4",
                "--conf",
                "spark.jars.ivy=/opt/news-ivy",
                "/app/tests/test_crawling_e2e.py",
            ],
        ),
        ("monitoring-smoke", [sys.executable, "tools/monitoring.py", "smoke"]),
        (
            "crawler-observability",
            [
                *base,
                "metadata-tools",
                "python3",
                "-m",
                "unittest",
                "tests.test_crawling_observability",
                "-v",
            ],
        ),
    ]
    results = [recorded_command(label, command) for label, command in commands]
    result = {
        "checked_at": now(),
        "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
        "scope": "selected P05/P07/P08/P09 tests, real five-source fixture and observability; no replacement credentials or live burn-in",
        "commands": results,
        "not_run": [
            "issuer credential invalidation",
            "post-rotation runtime recovery",
            "live HTTP",
            "24h/72h burn-in",
            "full phase5/7/8/9 acceptance targets",
        ],
    }
    write("platform-regression.json", result)
    return 0 if result["status"] == "PASS" else 1


def decision(phase6, phase9, regression, security, guards=None):
    # Missing evidence is never truthy success. Owner/issuer proof is not inferred from a scan.
    checks = security.get("scopes", {})
    clean = all(
        checks.get(m, {}).get("status") == "PASS"
        for m in ("working-tree", "staged", "history")
    )
    guards = guards or {}
    regression_status = (
        "FAIL"
        if "FAIL" in (regression.get("status"), guards.get("status"))
        else (
            "PASS"
            if regression.get("status") == guards.get("status") == "PASS"
            else "BLOCKED"
        )
    )
    return {
        "P10-SEC-INCIDENT": "BLOCKED",
        "P10-HISTORY-GATE": phase6.get("status", "BLOCKED"),
        "P10-CODE-REGRESSION": regression_status,
        "P10-P09-DEPENDENCY": "VERIFIED"
        if (
            phase9.get("status") == "PASS"
            and phase9.get("overall") == "PASS"
            and phase9.get("burnin_24h") == "PASS"
            and phase9.get("burnin_72h") == "PASS"
        )
        else "PENDING",
        "P10-AZURE-DESIGN": "INCOMPLETE",
        "P10-OVERALL": "NO-GO",
        "current_local_scans_clean": clean,
        "owner_signoff": "NOT_PROVIDED",
        "credential_invalidation": "NOT_VERIFIED",
        "migration_authorized": False,
        "reason": "Issuer invalidation, approved history remediation, required P09 live evidence and authorized design/sign-off are not established; scans alone cannot authorize migration.",
    }


def readiness():
    p9 = ROOT / "artifacts/phase9/acceptance.json"
    phase9 = json.loads(p9.read_text()) if p9.exists() else {}
    result = decision(
        read("phase6-gate.json"),
        phase9,
        read("platform-regression.json"),
        read("security-scans.json"),
        read("security-unit.json"),
    )
    result.update(
        generated_at=now(),
        scope="reviewable local evidence only; human sign-off cannot be synthesized",
    )
    write("readiness.json", result)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "go-no-go-decision.md").write_text(
        "# Phase10 — NO-GO\n\nUTC: "
        + result["generated_at"]
        + "\n\n"
        + "\n".join(
            f"- {key}: **{value}**"
            for key, value in result.items()
            if key.startswith("P10-")
        )
        + "\n\nIssuer invalidation and owner sign-off: NOT VERIFIED / NOT PROVIDED.\n"
        + "No authorization to start Phase11, provision Azure, mutate remote history or rotate accounts.\n"
        + "Prepared by: local coding agent (evidence assembly only).\nApproved by: PENDING authorized repository/security/cloud owners.\n"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "security-scan",
            "image-config-scan",
            "phase6-gate",
            "regressions",
            "acceptance",
            "readiness-report",
        ),
    )
    args = parser.parse_args()
    if args.command == "preflight":
        return preflight()
    if args.command == "security-scan":
        return scans()
    if args.command == "image-config-scan":
        return image_config_scans()
    if args.command == "phase6-gate":
        return phase6_gate()
    if args.command == "regressions":
        return regressions()
    if args.command == "acceptance":
        checks = [
            recorded_command(
                "security-unit",
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "tests.test_phase10_security",
                    "tests.test_phase10_readiness",
                    "-v",
                ],
            )
        ]
        scans()
        phase6_gate()
        write(
            "security-acceptance.json",
            {
                "checked_at": now(),
                "local_checks": checks,
                "status": "FAIL"
                if any(c["status"] != "PASS" for c in checks)
                else "BLOCKED",
                "note": "Use readiness gates; local negative tests never waive issuer/history/P09 evidence",
            },
        )
    return readiness()


if __name__ == "__main__":
    raise SystemExit(main())
