#!/usr/bin/env python3
"""Controlled fixture drill: failed publish, scheduler restart, durable resume."""

from datetime import datetime, timezone
import json
import time

from phase9 import COMPOSE, EVIDENCE, ROOT, check, command, container_json, write


def main():
    config = container_json(["config-check"], scheduler=True)
    if config["schedule_config"]:
        raise ValueError(
            "Pause continuous scheduling and restore manual configuration before this fixture restart drill"
        )
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    spark = [
        "/opt/spark/bin/spark-submit",
        "--packages",
        "io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4",
        "--conf",
        "spark.jars.ivy=/opt/news-ivy",
        "/app/tests/test_phase9_recovery_e2e.py",
    ]
    base = COMPOSE + ["run", "--rm", "--user", "0", "--no-deps", "news-pipeline"]
    checks = []
    for label, args in [
        (
            "recovery-prepare",
            base + ["python3", "/app/tests/test_phase9_recovery_e2e.py", "prepare"],
        ),
        ("recovery-inject", base + spark + ["fail"]),
        ("recovery-scheduler-restart", COMPOSE + ["restart", "airflow-scheduler"]),
    ]:
        checks.append(check(label, args))
        if checks[-1]["exit_code"]:
            raise RuntimeError(label + " failed; durable fixture state preserved")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready = command(
            COMPOSE
            + [
                "exec",
                "-T",
                "airflow-scheduler",
                "airflow",
                "jobs",
                "check",
                "--job-type",
                "SchedulerJob",
                "--local",
            ],
            timeout=30,
        )
        if ready.returncode == 0:
            break
        time.sleep(3)
    else:
        raise TimeoutError("Scheduler did not recover health")
    checks.append(check("recovery-resume", base + spark + ["recover"]))
    if checks[-1]["exit_code"]:
        raise RuntimeError("Recovery assertions failed; inspect checkpoint log")
    state = json.loads((ROOT / "data/local/phase9-recovery.json").read_text())
    write(
        EVIDENCE / "restart-recovery.json",
        {
            "status": state["status"],
            "scope": "Offline fixture + real local serving, no public requests",
            "checks": checks,
            "evidence": state,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "no_refetch": state["no_refetch"],
                "upstream_success_reused": state["upstream_success_reused"],
                "reconciliation": state["reconciliation"]["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
