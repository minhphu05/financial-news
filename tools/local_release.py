#!/usr/bin/env python3
"""Host-side bootstrap, audit, reset, and report helpers for local-rc1."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RELEASE_SERVICES = (
    "minio", "qdrant", "postgresql", "kafka", "debezium",
    "airflow-postgres", "airflow-init", "airflow-scheduler", "airflow-webserver",
)
RELEASE_VOLUMES = (
    "news_minio_data", "qdrant_data", "metadata_postgres_data", "kafka_data",
    "airflow_postgres_data", "airflow_duckdb", "airflow_logs",
)


def run(*command: str, capture: bool = False, check: bool = True) -> str:
    completed = subprocess.run(
        command, cwd=ROOT, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return completed.stdout if capture else ""


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected NAME=value")
        name, value = line.split("=", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise ValueError(f"{path}:{number}: invalid environment variable name")
        values[name] = value.strip().strip("'\"")
    return values


@contextmanager
def configured(values: dict[str, str]) -> Iterator[None]:
    old = os.environ.copy()
    try:
        for name in list(os.environ):
            if name.startswith(("NEWS_", "OBJECT_STORAGE_", "AZURE_STORAGE_")) or name == "ENVIRONMENT":
                os.environ.pop(name, None)
        os.environ.update(values)
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


def validate_profile(path: Path) -> dict:
    sys.path.insert(0, str(ROOT))
    from src.news_pipeline.config import Settings
    from src.news_pipeline.gold_config import GoldSettings

    values = read_env(path)
    with configured(values):
        news = Settings.from_env()
        gold = GoldSettings.from_env()
    return {
        "status": "PASS",
        "profile": str(path.relative_to(ROOT)),
        "environment": news.environment,
        "storage_provider": news.storage_provider,
        "storage_scheme": news.storage_scheme,
        "bronze_uri": news.object_uri("bronze"),
        "silver_uri": news.object_uri("silver"),
        "gold_rag_uri": news.object_uri(gold.rag_prefix),
        "gold_analytics_uri": news.object_uri(gold.analytics_prefix),
        "qdrant_url": gold.qdrant_url,
        "duckdb_path": gold.duckdb_path,
    }


def prerequisites() -> dict:
    missing = [name for name in ("docker", "make", "git") if shutil.which(name) is None]
    if missing:
        raise RuntimeError("missing required commands: " + ", ".join(missing))
    run("docker", "compose", "version", capture=True)
    run("docker", "info", capture=True)
    run("docker", "compose", "config", "--quiet", capture=True)
    result = {
        "status": "PASS",
        "docker": run("docker", "--version", capture=True).strip(),
        "compose": run("docker", "compose", "version", capture=True).strip(),
        "make": run("make", "--version", capture=True).splitlines()[0],
    }
    print(json.dumps(result, indent=2))
    return result


def validate_runtime() -> dict:
    values = read_env(ROOT / ".env") if (ROOT / ".env").is_file() else {}
    values.update({key: value for key, value in os.environ.items() if value})
    missing = [name for name in ("METADATA_CDC_PASSWORD",) if not values.get(name, "").strip()]
    if missing:
        raise RuntimeError(
            "runtime configuration validation failed: " + ", ".join(missing)
            + " is required; copy .env.example to .env and replace change-me placeholders"
        )
    result = {"status": "PASS", "required_secret_names_present": ["METADATA_CDC_PASSWORD"]}
    print(json.dumps(result, indent=2))
    return result


def compose_rows() -> list[dict]:
    raw = run("docker", "compose", "ps", "--format", "json", capture=True)
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]


def bootstrap_status() -> dict:
    rows = {row.get("Service"): row for row in compose_rows()}
    required = [service for service in RELEASE_SERVICES if service != "airflow-init"]
    checks = {}
    for service in required:
        row = rows.get(service)
        state = (row or {}).get("State")
        health = (row or {}).get("Health") or "not-defined"
        checks[service] = {
            "state": state,
            "health": health,
            "ready": state == "running" and health in {"healthy", "not-defined", ""},
        }
    result = {
        "status": "PASS" if all(item["ready"] for item in checks.values()) else "FAIL",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services": checks,
    }
    write_json(ARTIFACTS / "local-bootstrap-status.json", result)
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)
    return result


def tracked_release_files() -> list[Path]:
    output = run(
        "git", "ls-files", "--cached", "--others", "--exclude-standard", capture=True
    )
    allowed = (
        "src/news_pipeline/", "src/pipeline_operations/", "src/metadata_control/",
        "airflow/", "docker/news-pipeline/", "docker/airflow/",
        "docker/metadata-tools/", "docker/postgresql/", "config/",
    )
    exact = {"docker-compose.yml", "Makefile", ".env.example", ".gitignore"}
    return [
        ROOT / value for value in output.splitlines()
        if value in exact or value.startswith(allowed)
    ]


def release_audit() -> dict:
    developer_path = re.compile(r"(?:/home/[^/\s]+|/Users/[^/\s]+|[A-Za-z]:\\\\Users\\\\[^\\\s]+)")
    static_ip = re.compile(r"\b(?:10|172|192)\.(?:\d{1,3}\.){2}\d{1,3}\b")
    secret_patterns = {
        "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "azure_account_key": re.compile(r"AccountKey=[A-Za-z0-9+/]{40,}={0,2}"),
    }
    findings = {
        "developer_paths": [],
        "static_container_ips": [],
        "current_secret_indicators": [],
        "historical_secret_key_names": [],
    }
    classification_counts = {
        "VALID LOCAL DEFAULT": 0,
        "CONFIGURATION BUG": 0,
        "TEST FIXTURE": 0,
        "DOCUMENTATION ONLY": 0,
        "UNUSED FOR NOW": 0,
    }
    for path in tracked_release_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = str(path.relative_to(ROOT))
        for line_number, line in enumerate(text.splitlines(), 1):
            if developer_path.search(line):
                findings["developer_paths"].append({"file": relative, "line": line_number})
            if static_ip.search(line):
                findings["static_container_ips"].append({"file": relative, "line": line_number})
            for name, pattern in secret_patterns.items():
                if pattern.search(line):
                    findings["current_secret_indicators"].append(
                        {"file": relative, "line": line_number, "kind": name}
                    )
            if "localhost" in line or "127.0.0.1" in line or "/app/" in line:
                classification_counts["VALID LOCAL DEFAULT"] += 1
    legacy_paths = run(
        "git", "grep", "-l", "-E", "/Users/[^/ ]+|/home/[^/ ]+", "--",
        "src/model", "*.ipynb", capture=True, check=False,
    )
    classification_counts["UNUSED FOR NOW"] = len(set(legacy_paths.splitlines()))
    # Inspect the formerly tracked .env from HEAD without logging values. Its
    # staged deletion fixes the next tree; rotation/history remediation remains
    # an explicit repository-owner action.
    previous_env = run("git", "show", "HEAD:.env", capture=True, check=False)
    for line in previous_env.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if not value or not any(token in name.upper() for token in ("KEY", "TOKEN", "SECRET")):
            continue
        lowered = value.lower()
        placeholder = (
            any(token in lowered for token in (
                "change", "replace", "example", "your_", "your-", "dummy", "test-only"
            ))
            or value.startswith("${")
        )
        credential_shape = value.startswith(
            ("sk-", "ghp_", "github_pat_", "xox", "AIza", "pa-")
        ) or len(value) >= 32
        if credential_shape and not placeholder:
            findings["historical_secret_key_names"].append(name)
    findings["historical_secret_key_names"] = sorted(
        set(findings["historical_secret_key_names"])
    )
    problem_count = sum(len(values) for values in findings.values())
    classification_counts["CONFIGURATION BUG"] = problem_count
    result = {
        "status": "PASS" if problem_count == 0 else "FAIL",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Phase 01-06 runtime/configuration files",
        "classifications": classification_counts,
        "findings": findings,
        "notes": [
            "localhost, 127.0.0.1, Docker DNS names, and /app paths are valid explicit local/container defaults.",
            "Legacy NER notebooks/scripts with developer paths are outside the released data-pipeline runtime.",
            "The next Git tree removes .env, but likely credentials remain in existing Git history.",
            "Credential values are never emitted by this audit.",
        ],
    }
    write_json(ARTIFACTS / "local-release-audit.json", result)
    print(json.dumps(result, indent=2))
    return result


def destructive_reset(confirm: str) -> None:
    if confirm != "DELETE_LOCAL_RELEASE_DATA":
        raise SystemExit(
            "Refusing destructive reset. Set CONFIRM=DELETE_LOCAL_RELEASE_DATA exactly."
        )
    run("docker", "compose", "rm", "--stop", "--force", *RELEASE_SERVICES, check=False)
    config = json.loads(run("docker", "compose", "config", "--format", "json", capture=True))
    volume_config = config.get("volumes", {})
    for logical in RELEASE_VOLUMES:
        name = volume_config.get(logical, {}).get("name")
        if name:
            run("docker", "volume", "rm", "--force", name, check=False)
    local = ROOT / "data" / "local"
    if local.exists():
        try:
            shutil.rmtree(local)
        except PermissionError:
            # Spark acceptance jobs intentionally run as container root so some
            # bind-mounted outputs are root-owned on Linux hosts.
            run(
                "docker", "compose", "run", "--rm", "--no-deps", "--user", "0",
                "news-pipeline", "sh", "-c", "rm -rf /app/local/* /app/local/.[!.]*",
            )
            shutil.rmtree(local)
    local.mkdir(parents=True, exist_ok=True)
    print("Removed only Phase 01-06 service containers, persistent data volumes, and derived local files.")


def read_json(name: str) -> dict:
    path = ARTIFACTS / name
    if not path.is_file():
        return {"status": "MISSING", "path": str(path.relative_to(ROOT))}
    return json.loads(path.read_text(encoding="utf-8"))


def memory_total_gib() -> float | None:
    try:
        line = next(line for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemTotal:"))
        return round(int(line.split()[1]) / 1024 / 1024, 2)
    except Exception:
        return None


def release_report() -> dict:
    evidence = {
        "configuration_audit": read_json("local-release-audit.json"),
        "bootstrap": read_json("local-bootstrap-status.json"),
        "ci": read_json("local-release-ci.json"),
        "e2e": read_json("local-release-e2e.json"),
        "phase5_recovery": read_json("phase5-recovery-results.json"),
        "cdc_lifecycle": read_json("metadata-cdc-smoke.json"),
        "cdc_connect_recovery": read_json("metadata-cdc-recovery.json"),
        "cdc_kafka_recovery": read_json("metadata-cdc-kafka-recovery.json"),
        "cdc_postgres_recovery": read_json("metadata-cdc-postgres-recovery.json"),
    }
    statuses = {name: value.get("status") for name, value in evidence.items()}
    passed = all(status in {"PASS", "success"} for status in statuses.values())
    versions = read_env(ROOT / "config" / "release-versions.env")
    fixture_files = sorted((ROOT / "tests" / "fixtures" / "local_release").glob("*.json"))
    result = {
        "status": "PASS" if passed else "FAIL",
        "release": versions["LOCAL_RELEASE_VERSION"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": run("git", "rev-parse", "HEAD", capture=True).strip(),
        "environment": "local Docker Compose",
        "service_versions": versions,
        "test_results": statuses,
        "record_counts": evidence["e2e"].get("counts", {}),
        "pipeline_duration_seconds": evidence["e2e"].get("duration_seconds"),
        "local_resource_baseline": {
            "host_logical_cpu_count": os.cpu_count(),
            "host_memory_gib": memory_total_gib(),
            "spark_master": "local[2]",
            "spark_driver_memory_observed_default": "approximately 1 GiB container/JVM default",
            "acceptance_fixture_files": len(fixture_files),
            "acceptance_fixture_bytes": sum(path.stat().st_size for path in fixture_files),
            "docker": run("docker", "--version", capture=True).strip(),
        },
        "known_warnings": [
            "Local timings are a reproducibility baseline, not a production capacity benchmark.",
            "The ADLS byte adapter, Hadoop ABFS connector, Azure identity, and deployment are Phase 07 work.",
            "The local Kafka broker, Airflow LocalExecutor, and local Spark master are single-node configurations.",
            "Historical .env credentials require revoke/rotation and an explicit Git history remediation decision.",
        ],
        "evidence": evidence,
    }
    write_json(ARTIFACTS / "local-release-report.json", result)
    print(json.dumps({key: result[key] for key in (
        "status", "release", "generated_at", "git_commit", "test_results",
        "record_counts", "pipeline_duration_seconds", "local_resource_baseline",
    )}, indent=2))
    if not passed:
        raise SystemExit(1)
    return result


def mark(name: str) -> None:
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise ValueError("invalid marker name")
    write_json(ARTIFACTS / f"local-release-{name}.json", {
        "status": "PASS", "completed_at": datetime.now(timezone.utc).isoformat()
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prerequisites")
    subparsers.add_parser("validate-runtime")
    profile = subparsers.add_parser("validate-profile")
    profile.add_argument("path", type=Path)
    subparsers.add_parser("audit")
    subparsers.add_parser("bootstrap-status")
    reset = subparsers.add_parser("destructive-reset")
    reset.add_argument("--confirm", default="")
    subparsers.add_parser("report")
    marker = subparsers.add_parser("mark")
    marker.add_argument("name")
    args = parser.parse_args()

    if args.command == "prerequisites":
        prerequisites()
    elif args.command == "validate-runtime":
        validate_runtime()
    elif args.command == "validate-profile":
        print(json.dumps(validate_profile((ROOT / args.path).resolve()), indent=2))
    elif args.command == "audit":
        release_audit()
    elif args.command == "bootstrap-status":
        bootstrap_status()
    elif args.command == "destructive-reset":
        destructive_reset(args.confirm)
    elif args.command == "report":
        release_report()
    elif args.command == "mark":
        mark(args.name)


if __name__ == "__main__":
    main()
