#!/usr/bin/env python3
"""Health, smoke, acceptance, and baseline helpers for Phase 07."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
PIPELINE_EXPORTER_URL = os.getenv(
    "PIPELINE_EXPORTER_URL", "http://localhost:9108"
).rstrip("/")
GRAFANA_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin")
CRITICAL_JOBS = {
    "prometheus",
    "pipeline-exporter",
    "postgresql",
    "kafka",
    "airflow-statsd",
    "minio",
    "qdrant",
}
EXPECTED_DASHBOARDS = {
    "Financial News Platform — Overview",
    "Financial News Pipeline — Operations",
    "Financial News Pipeline — Data Quality",
    "Financial News Pipeline — Freshness",
    "Metadata Control Plane — CDC",
    "Local Infrastructure — Resources",
}
EXPECTED_ALERTS = {
    "ServiceDown",
    "PipelineRunFailed",
    "PipelineNoSuccessfulRunRecently",
    "SilverDataStale",
    "GoldDataStale",
    "QdrantIndexFailure",
    "DataQualityGateFailed",
    "ReconciliationFailed",
    "DebeziumConnectorDown",
    "KafkaConsumerLagHigh",
}


def request_json(url: str, *, auth: bool = False, timeout: float = 8.0) -> Any:
    headers = {"Accept": "application/json"}
    if auth:
        token = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        return json.loads(response.read())


def url_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        with urlopen(Request(url), timeout=timeout) as response:
            return response.status == 200
    except OSError:
        return False


def prom_query(expression: str) -> list[dict[str, Any]]:
    payload = request_json(f"{PROMETHEUS_URL}/api/v1/query?{urlencode({'query': expression})}")
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {expression}")
    return payload["data"]["result"]


def prom_value(expression: str, default: float | None = None) -> float | None:
    values = prom_query(expression)
    if not values:
        return default
    return float(values[0]["value"][1])


def target_states() -> dict[str, str]:
    payload = request_json(f"{PROMETHEUS_URL}/api/v1/targets")
    states: dict[str, str] = {}
    for target in payload["data"]["activeTargets"]:
        job = target.get("labels", {}).get("job")
        if job:
            current = states.get(job)
            health = target.get("health", "unknown")
            states[job] = health if current in (None, "up") else current
    return states


def wait_until(check, *, timeout: float = 120.0, interval: float = 3.0, label: str = "condition"):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except Exception as exc:  # dependency startup is intentionally retried
            last_error = exc
        time.sleep(interval)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"Timed out waiting for {label}{detail}")


def collect_health() -> dict[str, bool]:
    targets = target_states()
    return {
        "Prometheus": url_ok(f"{PROMETHEUS_URL}/-/healthy"),
        "Grafana": request_json(f"{GRAFANA_URL}/api/health", timeout=4).get("database") == "ok",
        "PipelineExport": targets.get("pipeline-exporter") == "up"
        and prom_value("financial_news_exporter_collection_success") == 1,
        "PostgreSQL": targets.get("postgresql") == "up" and prom_value("pg_up") == 1,
        "Kafka Metrics": targets.get("kafka") == "up"
        and (prom_value("kafka_brokers", 0) or 0) >= 1
        and prom_value("financial_news_kafka_broker_up") == 1,
        "Debezium": prom_value("financial_news_debezium_connector_up") == 1
        and prom_value("financial_news_debezium_task_up") == 1,
        "MinIO Metrics": targets.get("minio") == "up",
        "Qdrant Metrics": targets.get("qdrant") == "up" and bool(prom_query("app_info{name=\"qdrant\"}")),
    }


def health() -> dict[str, Any]:
    states = collect_health()
    for name, ok in states.items():
        print(f"{name:<16} {'OK' if ok else 'FAIL'}")
    return {"status": "PASS" if all(states.values()) else "FAIL", "services": states}


def dashboards() -> set[str]:
    result = request_json(f"{GRAFANA_URL}/api/search?tag=phase07")
    return {item["title"] for item in result if item.get("type") == "dash-db"}


def alerts() -> set[str]:
    payload = request_json(f"{PROMETHEUS_URL}/api/v1/rules?type=alert")
    return {
        rule["name"]
        for group in payload["data"]["groups"]
        for rule in group.get("rules", [])
    }


def smoke() -> dict[str, Any]:
    wait_until(
        lambda: CRITICAL_JOBS <= set(target_states()),
        timeout=120,
        label="Prometheus target discovery",
    )
    states = target_states()
    missing_jobs = sorted(CRITICAL_JOBS - set(states))
    unhealthy_jobs = sorted(job for job in CRITICAL_JOBS if states.get(job) != "up")
    present_metrics = {
        "pipeline_runs": bool(prom_query("financial_news_pipeline_runs_total")),
        "stage_duration": bool(prom_query("financial_news_pipeline_stage_duration_seconds")),
        "record_counts": bool(prom_query("financial_news_pipeline_records")),
        "freshness": bool(prom_query("financial_news_data_freshness_seconds")),
        "postgresql": prom_value("pg_up") == 1,
        "kafka": (prom_value("kafka_brokers", 0) or 0) >= 1,
        "airflow": bool(prom_query("statsd_exporter_build_info")),
        "debezium": bool(prom_query("financial_news_debezium_connector_up")),
        "minio": states.get("minio") == "up",
        "qdrant": bool(prom_query("app_info{name=\"qdrant\"}")),
        "duckdb": bool(prom_query("financial_news_duckdb_operational_up")),
    }
    found_dashboards = dashboards()
    found_alerts = alerts()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "missing_jobs": missing_jobs,
        "unhealthy_jobs": unhealthy_jobs,
        "metrics": present_metrics,
        "dashboards": sorted(found_dashboards),
        "missing_dashboards": sorted(EXPECTED_DASHBOARDS - found_dashboards),
        "alerts": sorted(found_alerts),
        "missing_alerts": sorted(EXPECTED_ALERTS - found_alerts),
    }
    report["status"] = "PASS" if (
        not missing_jobs
        and not unhealthy_jobs
        and all(present_metrics.values())
        and not report["missing_dashboards"]
        and not report["missing_alerts"]
    ) else "FAIL"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


def _psql_rows(query: str) -> list[list[str]]:
    command = [
        "docker", "compose", "exec", "-T", "postgresql", "sh", "-lc",
        "psql -v ON_ERROR_STOP=1 -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -At -F '|' -c \"$1\"",
        "monitoring-baseline", query,
    ]
    output = subprocess.run(command, check=True, text=True, capture_output=True).stdout
    return [line.split("|") for line in output.splitlines() if line.strip()]


def baseline(output: Path) -> dict[str, Any]:
    run_rows = _psql_rows(
        "SELECT extract(epoch FROM (finished_at-started_at))::numeric(12,3) "
        "FROM pipeline_operations.pipeline_runs "
        "WHERE source='phase07-monitoring.local' AND status='SUCCESS' "
        "AND run_id LIKE 'phase07-normal-%' ORDER BY created_at"
    )
    stage_rows = _psql_rows(
        "SELECT regexp_replace(s.stage_name, '^....-..-..:', ''), "
        "(s.metrics->>'stage_duration_seconds')::numeric(12,3) "
        "FROM pipeline_operations.pipeline_stage_runs s "
        "JOIN pipeline_operations.pipeline_runs r USING(run_id) "
        "WHERE r.source='phase07-monitoring.local' AND r.status='SUCCESS' "
        "AND r.run_id LIKE 'phase07-normal-%' AND s.status='SUCCESS' "
        "ORDER BY r.created_at, s.stage_run_id"
    )
    durations = [float(row[0]) for row in run_rows]
    by_stage: dict[str, list[float]] = {}
    for stage, value in stage_rows:
        by_stage.setdefault(stage, []).append(float(value))
    stage_summary = {
        stage: {
            "samples": len(values),
            "min_seconds": round(min(values), 3),
            "mean_seconds": round(statistics.fmean(values), 3),
            "max_seconds": round(max(values), 3),
        }
        for stage, values in sorted(by_stage.items())
    }
    counts = {}
    for kind in ("input", "output", "invalid", "duplicate", "documents", "chunks", "qdrant_points"):
        value = prom_value(
            f'max(financial_news_pipeline_records{{source="phase07-monitoring.local",kind="{kind}"}})',
            0,
        )
        counts[kind] = value
    phase6_path = Path("artifacts/local-release-e2e.json")
    phase6 = json.loads(phase6_path.read_text()) if phase6_path.is_file() else {}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "stable Phase 06 E2E dataset plus isolated Phase 07 operational runs; warm Docker and model caches",
        "phase06_acceptance_dataset": {
            "status": phase6.get("status"),
            "duration_seconds": phase6.get("duration_seconds"),
            "counts": phase6.get("counts"),
            "qdrant_rebuild_seconds": (phase6.get("qdrant_rebuild") or {}).get("processing_duration_seconds"),
            "gold_rebuild_seconds": (phase6.get("gold_rebuild") or {}).get("processing_duration_seconds"),
            "analytics_rebuild_seconds": (phase6.get("analytics_rebuild") or {}).get("processing_duration_seconds"),
            "duckdb_rebuild_seconds": (phase6.get("duckdb_rebuild") or {}).get("processing_duration_seconds"),
        },
        "run_duration": {
            "samples": len(durations),
            "min_seconds": round(min(durations), 3) if durations else None,
            "mean_seconds": round(statistics.fmean(durations), 3) if durations else None,
            "max_seconds": round(max(durations), 3) if durations else None,
        },
        "stage_duration": stage_summary,
        "record_counts": counts,
        "resource_observations": {
            "host_cpu_used_ratio": prom_value(
                '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[2m]))', 0
            ),
            "host_memory_used_bytes": prom_value(
                'node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes', 0
            ),
            "container_breakdown_available": False,
            "container_breakdown_note": "cAdvisor on this Docker/cgroup-v2 host exposes host cgroups without Compose container-name labels",
        },
        "statistical_claim": "descriptive local observations only",
    }
    report["status"] = "PASS" if (
        len(durations) >= 2
        and bool(stage_summary)
        and report["phase06_acceptance_dataset"]["status"] == "PASS"
    ) else "FAIL"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def acceptance(output: Path) -> dict[str, Any]:
    result = smoke()
    result["health"] = collect_health()
    result["cardinality_forbidden_labels"] = []
    metrics_text = urlopen(f"{PIPELINE_EXPORTER_URL}/metrics", timeout=10).read().decode()
    for forbidden in ("run_id=", "article_id=", "chunk_id=", "source_url=", "error="):
        if forbidden in metrics_text:
            result["cardinality_forbidden_labels"].append(forbidden[:-1])
    result["status"] = "PASS" if (
        result["status"] == "PASS"
        and all(result["health"].values())
        and not result["cardinality_forbidden_labels"]
    ) else "FAIL"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PHASE 07 MONITORING CHECK: {result['status']}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    sub.add_parser("smoke")
    baseline_parser = sub.add_parser("baseline")
    baseline_parser.add_argument("--output", type=Path, default=Path("artifacts/phase7-monitoring-baseline.json"))
    acceptance_parser = sub.add_parser("acceptance")
    acceptance_parser.add_argument("--output", type=Path, default=Path("artifacts/phase7-monitoring-checks.json"))
    args = parser.parse_args()
    if args.command == "health":
        result = health()
    elif args.command == "smoke":
        result = smoke()
    elif args.command == "baseline":
        result = baseline(args.output)
    else:
        result = acceptance(args.output)
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
