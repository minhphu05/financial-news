#!/usr/bin/env python3
"""Local functional acceptance and real-time evidence collection; no crawl loop."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import uuid4

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.crawling.burnin import assess, verified_24h_report  # noqa: E402 - repository root added for script execution
from src.crawling.reporting import SOURCE_KEYS, timestamp  # noqa: E402

EVIDENCE = ROOT / "artifacts/phase9"
COMPOSE = ["docker", "compose"]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    temporary.replace(path)


def command(args, timeout=1800):
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def check(label, args):
    started = datetime.now(timezone.utc).isoformat()
    path = EVIDENCE / (label + ".log")
    try:
        with path.open("w") as log:
            result = subprocess.run(
                args,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=1800,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        code = result.returncode
    except subprocess.TimeoutExpired:
        code = 124
        with path.open("a") as log:
            log.write("Command exceeded bounded 1800-second timeout\n")
    item = {
        "check": label,
        "command": args,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "exit_code": code,
        "log": str((EVIDENCE / (label + ".log")).relative_to(ROOT)),
    }
    print(json.dumps(item), flush=True)
    return item


def container_json(arguments, *, scheduler=False):
    prefix = COMPOSE + (
        ["exec", "-T", "airflow-scheduler"]
        if scheduler
        else [
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "news-pipeline",
        ]
    )
    result = command(
        prefix + ["python3", "-m", "src.crawling.operations", *arguments], timeout=180
    )
    if result.returncode:
        raise RuntimeError(
            "operational command failed with exit " + str(result.returncode)
        )
    return json.loads(result.stdout)


def prom(query, *, at=None, start=None, end=None):
    base = os.getenv("PHASE9_PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
    if start:
        path = "/api/v1/query_range"
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": 60,
        }
    else:
        path = "/api/v1/query"
        params = {
            "query": query,
            "time": (at or datetime.now(timezone.utc)).timestamp(),
        }
    with urlopen(base + path + "?" + urlencode(params), timeout=20) as response:
        payload = json.load(response)
    if payload.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    return payload["data"]["result"]


def scheduler_snapshot(start):
    # Read through Airflow's own application/session; never use its DB for crawler state.
    script = """import json,sys,runpy
sys.path.insert(0,'/opt/airflow/dags')
from datetime import datetime
from airflow.models import DagRun,DagModel
from airflow.settings import Session
dag=runpy.run_path('/opt/airflow/dags/news_crawling_pipeline.py')['dag']
with Session() as db:
 rows=db.query(DagRun).filter(DagRun.dag_id==dag.dag_id,DagRun.run_type=='scheduled',DagRun.start_date>=datetime.fromisoformat(sys.argv[1])).order_by(DagRun.start_date).limit(1000).all()
 active=db.query(DagRun).filter(DagRun.dag_id==dag.dag_id,DagRun.run_type=='scheduled',DagRun.state.in_(['queued','running'])).limit(1000).all()
 model=db.query(DagModel).filter(DagModel.dag_id==dag.dag_id).one()
 value={'is_paused':model.is_paused,'parsed_schedule':dag.schedule_interval,'max_active_runs':dag.max_active_runs,'max_active_tasks':dag.max_active_tasks,'scheduled_runs':[{'run_id':r.run_id,'start_date':r.start_date,'end_date':r.end_date,'state':r.state} for r in rows],'truncated':len(rows)==1000}
 value['active_scheduled_runs']=[{'run_id':r.run_id,'state':r.state} for r in active]
print('PHASE9_JSON='+json.dumps(value,default=str))
"""
    result = command(
        COMPOSE
        + [
            "exec",
            "-T",
            "airflow-scheduler",
            "python3",
            "-c",
            script,
            start.isoformat(),
        ],
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError("Airflow schedule inspection failed")
    line = next(
        (
            line
            for line in result.stdout.splitlines()
            if line.startswith("PHASE9_JSON=")
        ),
        None,
    )
    if not line:
        raise RuntimeError("Missing Airflow inspection output")
    data = json.loads(line.partition("=")[2])
    prior_end = None
    overlap = False
    for index, row in enumerate(data["scheduled_runs"]):
        begun = timestamp(row["start_date"])
        if index and (prior_end is None or begun < prior_end):
            overlap = True
        prior_end = timestamp(row["end_date"])
    data["overlapping_runs"] = overlap
    return data


def daily(start, end, fixture=False):
    data = container_json(
        [
            "daily-report",
            "--start",
            start.isoformat(),
            "--end",
            end.isoformat(),
            *(["--fixture"] if fixture else []),
        ]
    )
    try:
        alerts = prom('ALERTS{alertstate="firing"}', start=start, end=end)
        data["alert_summary"] = [
            {
                "labels": {
                    k: v
                    for k, v in row["metric"].items()
                    if k in ("alertname", "source", "data_kind", "severity")
                },
                "firing_sample_count": sum(
                    float(v) > 0 for _, v in row.get("values", [])
                ),
            }
            for row in alerts
        ]
        data["data_gaps"] = [
            "Resource history requires the optional host/storage evidence sampler"
        ]
        availability = prom('up{job="prometheus"}', start=start, end=end)
        observed_steps = {
            point[0] for row in availability for point in row.get("values", [])
        }
        expected_steps = int((end - start).total_seconds() // 60) + 1
        data["alert_history_coverage"] = {
            "query_step_seconds": 60,
            "expected_query_steps": expected_steps,
            "steps_with_self_scrape_data": len(observed_steps),
            "complete": len(observed_steps) >= expected_steps,
            "semantics": "Prometheus query-step availability, not proof of uninterrupted raw scrapes or service uptime",
        }
        if len(observed_steps) < expected_steps:
            data["data_gaps"].append(
                "N/A complete alert history: missing Prometheus data; an empty alert list does not prove no alerts in the entire requested window"
            )
    except Exception as exc:
        data["data_gaps"].append("N/A alert history: " + type(exc).__name__)
    return data


def sample(session):
    now = datetime.now(timezone.utc)
    item = {
        "observed_at": now.isoformat(),
        "monotonic_seconds": time.monotonic(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "hard_stop_reasons": [],
    }
    try:
        item["report"] = daily(timestamp(session["started_at"]), now)
        item["scheduler"] = scheduler_snapshot(timestamp(session["started_at"]))
        item["storage"] = container_json(["storage"])
        item["service_up"] = prom(
            'up{job=~"pipeline-exporter|postgresql|kafka|airflow-statsd|minio|qdrant"}',
            at=now,
        )
        observed_jobs = {row["metric"]["job"] for row in item["service_up"]}
        if observed_jobs != {
            "pipeline-exporter",
            "postgresql",
            "kafka",
            "airflow-statsd",
            "minio",
            "qdrant",
        } or any(float(row["value"][1]) != 1 for row in item["service_up"]):
            item["hard_stop_reasons"].append("Required service targets missing or down")
        if item["scheduler"]["overlapping_runs"]:
            item["hard_stop_reasons"].append("Scheduled DAG overlap")
        disk = shutil.disk_usage(ROOT)
        item["host_disk"] = {"free_bytes": disk.free, "total_bytes": disk.total}
        if disk.free < 2 * 1024**3:
            item["hard_stop_reasons"].append(
                "Less than 2 GiB free on evidence filesystem"
            )
        item["host_available_memory"] = prom("node_memory_MemAvailable_bytes", at=now)
        item["host_cpu_utilization_ratio"] = prom(
            '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', at=now
        )
        if not item["host_cpu_utilization_ratio"]:
            item["host_cpu_gap"] = "N/A: no five-minute host CPU rate available"
        if not item["host_available_memory"]:
            item["hard_stop_reasons"].append("Host memory telemetry missing")
        elif (
            min(float(row["value"][1]) for row in item["host_available_memory"])
            < 128 * 1024**2
        ):
            item["hard_stop_reasons"].append(
                "Host available memory below local 128 MiB hard-stop floor"
            )
        for source in session["sources"]:
            row = item["report"]["sources"][source]
            if row["blocked_or_rate_limited"]:
                item["hard_stop_reasons"].append(
                    source
                    + ": block/rate-limit observed; source policy review required"
                )
            if row["reconciliation"]["FAIL"]:
                item["hard_stop_reasons"].append(source + ": reconciliation failed")
    except Exception as exc:
        item["collection_error"] = type(exc).__name__
    return item


def acceptance():
    # No news requests or 24h/72h sleeps. The final safety drill temporarily
    # schedules fully denied sources, then restores the original manual mode.
    checks = []
    commands = [
        (
            "config",
            COMPOSE
            + [
                "exec",
                "-T",
                "airflow-scheduler",
                "python3",
                "-m",
                "src.crawling.operations",
                "config-check",
            ],
        ),
        (
            "phase9-tests",
            COMPOSE
            + [
                "run",
                "--rm",
                "--no-deps",
                "-e",
                "PHASE9_DB_TESTS=1",
                "-e",
                "CRAWLER_DB_TESTS=1",
                "news-pipeline",
                "python3",
                "-m",
                "unittest",
                "tests.test_phase9_unit",
                "tests.test_phase9_integration",
                "tests.test_phase9_burnin",
                "tests.test_crawling_parsers",
                "tests.test_crawling_state",
                "-v",
            ],
        ),
        (
            "metrics-tests",
            COMPOSE
            + [
                "run",
                "--rm",
                "--no-deps",
                "metadata-tools",
                "python3",
                "-m",
                "unittest",
                "tests.test_monitoring",
                "tests.test_crawler_metrics",
                "tests.test_phase9_metrics",
                "-v",
            ],
        ),
        (
            "alert-tests",
            COMPOSE
            + [
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "promtool",
                "prometheus",
                "test",
                "rules",
                "/etc/prometheus/tests/phase9.yml",
            ],
        ),
        ("phase8-regression", ["make", "phase8-acceptance"]),
        ("phase5-regression", ["make", "test-hardening"]),
        ("phase7-regression", ["make", "phase7-acceptance"]),
        ("restart-recovery", ["python3", "tools/phase9_recovery.py"]),
        ("scheduler-smoke", ["python3", "tools/phase9_scheduler_smoke.py"]),
    ]
    for label, args in commands:
        checks.append(check(label, args))
        # Preserve the failing checkpoint; don't spend minutes on dependent checks.
        if checks[-1]["exit_code"]:
            break
    status = (
        "PASS"
        if len(checks) == len(commands) and all(c["exit_code"] == 0 for c in checks)
        else "FAIL"
    )
    data = {
        "status": status,
        "scope": "Functional fixture/local acceptance only; no live burn-in",
        "checks": checks,
        "burnin_24h": "PENDING",
        "burnin_72h": "PENDING",
        "overall": "PENDING" if status == "PASS" else "FAIL",
        "cloud_verdict": "NOT READY FOR CLOUD MIGRATION",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    write(EVIDENCE / "acceptance.json", data)
    (EVIDENCE / "acceptance-summary.md").write_text(
        "# Phase09 acceptance\n\nFunctional: **"
        + status
        + "**. Burn-in 24h: **PENDING**. Burn-in 72h: **PENDING**. Overall is not DONE.\n\n"
        + "\n".join(
            "- `"
            + c["check"]
            + "`: exit "
            + str(c["exit_code"])
            + "; `"
            + c["log"]
            + "`."
            for c in checks
        )
        + "\n"
    )
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("acceptance")
    sub.add_parser("config-check")
    report = sub.add_parser("daily-report")
    report.add_argument("--start", type=timestamp)
    report.add_argument("--end", type=timestamp)
    report.add_argument("--fixture", action="store_true")
    begin = sub.add_parser("burnin-start")
    begin.add_argument("--hours", type=int, choices=(24, 72), required=True)
    begin.add_argument(
        "--sources", nargs="+", choices=SOURCE_KEYS, default=list(SOURCE_KEYS)
    )
    begin.add_argument("--live-opt-in", action="store_true", required=True)
    begin.add_argument("--backup-reference", type=Path, required=True)
    begin.add_argument("--previous-24h-report", type=Path)
    begin.add_argument("--interval", type=int, default=300)
    watch = sub.add_parser("watch")
    watch.add_argument("--session", type=Path, required=True)
    end = sub.add_parser("burnin-report")
    end.add_argument("--session", type=Path)
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.command == "acceptance":
        data = acceptance()
        print(json.dumps(data, indent=2))
        return 0 if data["status"] == "PASS" else 1
    if args.command == "config-check":
        data = container_json(["config-check"], scheduler=True)
    elif args.command == "daily-report":
        end = args.end or datetime.now(timezone.utc)
        start = args.start or end - timedelta(days=1)
        data = daily(start, end, args.fixture)
        write(
            EVIDENCE
            / "daily-reports"
            / (end.strftime("%Y%m%dT%H%M%SZ") + "-" + data["data_kind"] + ".json"),
            data,
        )
    elif args.command == "burnin-start":
        if not args.backup_reference.is_file():
            raise ValueError(
                "Provide an existing backup/restore evidence or reviewed recovery-plan reference"
            )
        if not 60 <= args.interval <= 900:
            raise ValueError("Evidence sampling interval must be 60..900 seconds")
        accepted = json.loads((EVIDENCE / "acceptance.json").read_text())
        if accepted["status"] != "PASS":
            raise ValueError("Functional acceptance must pass first")
        if args.hours == 72:
            if not args.previous_24h_report:
                raise ValueError("72h requires a genuine PASS 24h go/no-go report")
            verified_24h_report(args.previous_24h_report)
        config = container_json(["config-check"], scheduler=True)
        if not config["schedule_config"] or not config["scheduled_live_switch"]:
            raise ValueError("Live scheduler is not explicitly configured")
        if any(
            not config["sources"][s]["enabled"]
            or not config["sources"][s]["live_enabled"]
            or not config["sources"][s]["policy_review_recorded"]
            for s in args.sources
        ):
            raise ValueError(
                "Selected source live policies must be explicitly enabled with recorded policy review"
            )
        now = datetime.now(timezone.utc)
        data = {
            "hours": args.hours,
            "sources": args.sources,
            "started_at": now.isoformat(),
            "sample_interval_seconds": args.interval,
            "monotonic_start": time.monotonic(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "live_opt_in": True,
            "backup_reference": str(args.backup_reference.resolve()),
            "functional_acceptance_completed_at": accepted["completed_at"],
        }
        path = EVIDENCE / (
            "burnin-" + now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6] + ".json"
        )
        first = sample(data)
        if (
            first.get("collection_error")
            or first["hard_stop_reasons"]
            or first.get("scheduler", {}).get("is_paused")
        ):
            raise ValueError(
                "Burn-in prerequisites failed; scheduler must be active and telemetry healthy"
            )
        write(path, data)
        write(path.with_suffix(".samples.json"), [first])
        print(
            json.dumps(
                {
                    "session": str(path.relative_to(ROOT)),
                    "status": "STARTED",
                    "note": "Run watch with this session; no 24h/72h result exists yet",
                }
            )
        )
        return 0
    elif args.command == "watch":
        data = json.loads(args.session.read_text())
        samples_path = args.session.with_suffix(".samples.json")
        samples = json.loads(samples_path.read_text())
        try:
            while True:
                item = sample(data)
                samples.append(item)
                write(samples_path, samples)
                if item["hard_stop_reasons"] or item.get("collection_error"):
                    for source in data["sources"]:
                        container_json(
                            ["policy", "--source", source, "--live-enabled", "false"]
                        )
                    data["stopped_reason"] = "Hard stop or missing evidence: " + str(
                        item.get("hard_stop_reasons") or item.get("collection_error")
                    )
                    write(args.session, data)
                    break
                if datetime.now(timezone.utc) >= timestamp(
                    data["started_at"]
                ) + timedelta(hours=data["hours"]):
                    break
                time.sleep(data["sample_interval_seconds"])
        finally:
            # A completed B2 window also pauses before its 72h go/no-go decision.
            command(
                COMPOSE
                + [
                    "exec",
                    "-T",
                    "airflow-scheduler",
                    "airflow",
                    "dags",
                    "pause",
                    "news_crawling_pipeline",
                ],
                timeout=60,
            )
        result = assess(data, samples)
        write(args.session.with_suffix(".report.json"), result)
        print(json.dumps(result, default=str))
        return 0 if result["status"] == "PASS" else 1
    else:
        if args.session:
            data = assess(
                json.loads(args.session.read_text()),
                json.loads(args.session.with_suffix(".samples.json").read_text()),
            )
            write(args.session.with_suffix(".report.json"), data)
        else:
            data = {
                "status": "PENDING",
                "reason": "No real 24h/72h collection session supplied; functional tests do not satisfy time-based gates",
            }
    print(json.dumps(data, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
