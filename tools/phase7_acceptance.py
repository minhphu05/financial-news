#!/usr/bin/env python3
"""Execute isolated Phase 07 normal, failure, recovery, quality, and CDC demos."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen

import monitoring


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
SPARK = [
    "/opt/spark/bin/spark-submit",
    "--packages",
    "io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4",
    "--conf",
    "spark.jars.ivy=/opt/news-ivy",
    "/app/src/news_pipeline/pipeline_runner.py",
]
PIPELINE_ENV = {
    "NEWS_SOURCE": "phase07-monitoring.local",
    "NEWS_INDEX_BATCH_SIZE": "8",
}


def configure_isolation(suffix: str) -> None:
    """Assign durable/derived namespaces used only by one acceptance execution."""
    PIPELINE_ENV.update({
        "NEWS_PROCESSING_VERSION": f"phase07-monitoring-{suffix}",
        "NEWS_QDRANT_COLLECTION": f"phase07_monitoring_{suffix}",
        "NEWS_DUCKDB_PATH": f"/app/local/phase07-monitoring-{suffix}.duckdb",
    })


def run(command: list[str], *, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if check and result.returncode:
        tail = "\n".join(result.stdout.splitlines()[-40:])
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\n{tail}")
    return result


def pipeline_command(run_id: str, date: str, fixture: str, *, resume: bool = False) -> list[str]:
    command = ["docker", "compose", "run", "--rm", "--no-deps", "--user", "0"]
    for name, value in PIPELINE_ENV.items():
        command.extend(["-e", f"{name}={value}"])
    command.extend(["-e", f"NEWS_PROCESSING_DATE={date}", "news-pipeline", *SPARK])
    if resume:
        command.extend(["resume", "--run-id", run_id])
    else:
        command.extend([
            "reprocess", "--date", date, "--source-file", fixture,
            "--force-reprocess", "--run-id", run_id,
        ])
    return command


def run_pipeline(run_id: str, date: str, fixture: str, *, expect_failure: bool = False, resume: bool = False) -> dict:
    print(f"phase07 pipeline: {run_id}", flush=True)
    started = time.monotonic()
    result = run(
        pipeline_command(run_id, date, fixture, resume=resume),
        check=not expect_failure,
    )
    log_path = ARTIFACTS / f"{run_id}{'-resume' if resume else ''}.log"
    log_path.write_text(result.stdout, encoding="utf-8")
    if expect_failure and result.returncode == 0:
        raise RuntimeError("The isolated Qdrant failure run unexpectedly succeeded")
    return {
        "run_id": run_id,
        "return_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "log": str(log_path.relative_to(ROOT)),
    }


def wait_prom(expression: str, predicate, label: str, timeout: float = 120.0) -> float:
    def check():
        value = monitoring.prom_value(expression)
        return value is not None and predicate(value)
    monitoring.wait_until(check, timeout=timeout, label=label)
    value = monitoring.prom_value(expression)
    if value is None:
        raise RuntimeError(f"Prometheus series disappeared after reaching {label}")
    return float(value)


def connector_action(action: str) -> None:
    url = f"http://localhost:8083/connectors/metadata-control-plane/{action}"
    with urlopen(Request(url, method="PUT"), timeout=10) as response:
        if response.status not in (200, 202, 204):
            raise RuntimeError(f"Kafka Connect {action} returned {response.status}")


def run_baseline_samples(suffix: str) -> list[dict]:
    results = []
    for sample in range(1, 3):
        results.append(run_pipeline(
            f"phase07-normal-{suffix}-{sample}",
            "2026-09-07",
            "/app/tests/fixtures/monitoring/normal.json",
        ))
    monitoring.wait_until(
        lambda: monitoring.prom_value(
            'financial_news_pipeline_runs_total{source="phase07-monitoring.local",status="SUCCESS"}', 0
        ) >= 2,
        timeout=90,
        label="normal runs in Prometheus",
    )
    return results


def baseline_only() -> dict:
    ARTIFACTS.mkdir(exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    configure_isolation(suffix)
    samples = run_baseline_samples(suffix)
    baseline = monitoring.baseline(ARTIFACTS / "phase7-monitoring-baseline.json")
    return {"status": baseline["status"], "samples": samples, "baseline": baseline}


def full_acceptance() -> dict:
    ARTIFACTS.mkdir(exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    configure_isolation(suffix)
    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": "isolated Phase 07 source, object prefixes, Qdrant collection, and DuckDB file",
        "normal_runs": [],
        "data_quality": {},
        "qdrant_failure_recovery": {},
        "cdc_failure_recovery": {},
    }
    qdrant_was_stopped = False
    connector_was_paused = False
    try:
        report["preflight"] = monitoring.smoke()
        report["normal_runs"] = run_baseline_samples(suffix)

        quality_run = run_pipeline(
            f"phase07-quality-{suffix}",
            "2026-09-08",
            "/app/tests/fixtures/monitoring/data-quality.json",
        )
        invalid = wait_prom(
            'financial_news_data_quality_invalid_records{source="phase07-monitoring.local"}',
            lambda value: value >= 1,
            "isolated invalid-record metric",
        )
        quality_alert = wait_prom(
            'count(ALERTS{alertname="DataQualityGateFailed",alertstate="firing",source="phase07-monitoring.local"})',
            lambda value: value >= 1,
            "data-quality alert",
        )
        report["data_quality"] = {
            **quality_run,
            "invalid_records": invalid,
            "quality_alert_firing": quality_alert >= 1,
            "pipeline_policy": "valid rows continue; invalid row is isolated in Silver rejects",
        }

        failed_before = monitoring.prom_value(
            'financial_news_pipeline_stage_runs_total{source="phase07-monitoring.local",stage="qdrant_upsert",status="FAILED"}',
            0,
        ) or 0
        run(["docker", "compose", "stop", "qdrant"])
        qdrant_was_stopped = True
        wait_prom('up{job="qdrant"}', lambda value: value == 0, "Qdrant scrape failure", 90)
        wait_prom(
            'count(ALERTS{alertname="QdrantDown",alertstate="firing"})',
            lambda value: value >= 1,
            "QdrantDown alert",
            90,
        )
        failure_id = f"phase07-qdrant-{suffix}"
        failed_run = run_pipeline(
            failure_id,
            "2026-09-09",
            "/app/tests/fixtures/monitoring/qdrant-recovery.json",
            expect_failure=True,
        )
        failed_after = wait_prom(
            'financial_news_pipeline_stage_runs_total{source="phase07-monitoring.local",stage="qdrant_upsert",status="FAILED"}',
            lambda value: value > failed_before,
            "failed Qdrant stage metric",
            90,
        )
        pipeline_failure_alert = wait_prom(
            'count(ALERTS{alertname=~"PipelineRunFailed|QdrantIndexFailure",alertstate="firing",source="phase07-monitoring.local"})',
            lambda value: value >= 1,
            "pipeline failure alert",
            90,
        )
        run(["docker", "compose", "up", "-d", "--wait", "qdrant"])
        qdrant_was_stopped = False
        wait_prom('up{job="qdrant"}', lambda value: value == 1, "Qdrant scrape recovery", 90)
        recovered_run = run_pipeline(
            failure_id,
            "2026-09-09",
            "/app/tests/fixtures/monitoring/qdrant-recovery.json",
            resume=True,
        )
        monitoring.wait_until(
            lambda: not monitoring.prom_query('ALERTS{alertname="QdrantDown",alertstate="firing"}'),
            timeout=90,
            label="QdrantDown alert resolution",
        )
        report["qdrant_failure_recovery"] = {
            "failed_run": failed_run,
            "failed_stage_total_before": failed_before,
            "failed_stage_total_after": failed_after,
            "pipeline_failure_alert_firing": pipeline_failure_alert >= 1,
            "service_alert_resolved": True,
            "recovered_run": recovered_run,
        }

        connector_action("pause")
        connector_was_paused = True
        wait_prom(
            "financial_news_debezium_connector_up",
            lambda value: value == 0,
            "paused Debezium metric",
            90,
        )
        cdc_alert = wait_prom(
            'count(ALERTS{alertname="DebeziumConnectorDown",alertstate="firing"})',
            lambda value: value >= 1,
            "Debezium connector alert",
            90,
        )
        kafka_up = monitoring.prom_value("financial_news_kafka_broker_up")
        postgres_up = monitoring.prom_value("pg_up")
        connector_action("resume")
        connector_was_paused = False
        wait_prom(
            "financial_news_debezium_connector_up",
            lambda value: value == 1,
            "resumed Debezium metric",
            120,
        )
        monitoring.wait_until(
            lambda: not monitoring.prom_query('ALERTS{alertname="DebeziumConnectorDown",alertstate="firing"}'),
            timeout=90,
            label="Debezium alert resolution",
        )
        report["cdc_failure_recovery"] = {
            "connector_unhealthy_observed": True,
            "alert_firing": cdc_alert >= 1,
            "kafka_remained_up": kafka_up == 1,
            "postgresql_remained_up": postgres_up == 1,
            "connector_recovered": True,
            "alert_resolved": True,
        }

        report["baseline"] = monitoring.baseline(
            ARTIFACTS / "phase7-monitoring-baseline.json"
        )
        report["final_checks"] = monitoring.acceptance(
            ARTIFACTS / "phase7-monitoring-checks.json"
        )
        required = [
            report["preflight"]["status"] == "PASS",
            report["data_quality"].get("invalid_records", 0) >= 1,
            report["qdrant_failure_recovery"].get("service_alert_resolved") is True,
            report["cdc_failure_recovery"].get("connector_recovered") is True,
            report["baseline"]["status"] == "PASS",
            report["final_checks"]["status"] == "PASS",
        ]
        report["status"] = "PASS" if all(required) else "FAIL"
    finally:
        if qdrant_was_stopped:
            run(["docker", "compose", "up", "-d", "--wait", "qdrant"], check=False)
        if connector_was_paused:
            try:
                connector_action("resume")
            except Exception:
                pass
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        output = ARTIFACTS / "phase7-acceptance.json"
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PHASE 07 ACCEPTANCE: {report.get('status', 'FAIL')}")
    if report.get("status") != "PASS":
        raise SystemExit(2)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("acceptance", "baseline"), default="acceptance")
    args = parser.parse_args()
    result = baseline_only() if args.mode == "baseline" else full_acceptance()
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
