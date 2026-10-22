#!/usr/bin/env python3
"""Two real scheduled cycles with all live policies denied, then restore manual mode."""

from datetime import datetime, timezone
import json
import os
import subprocess
import time

from phase9 import (
    COMPOSE,
    EVIDENCE,
    ROOT,
    command,
    container_json,
    scheduler_snapshot,
    write,
)


def checked(args, *, env=None):
    result = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(
            "Scheduler drill command failed with exit " + str(result.returncode)
        )
    return result.stdout


def main():
    original = container_json(["config-check"], scheduler=True)
    if original["schedule_config"] or any(
        row["live_enabled"] for row in original["sources"].values()
    ):
        raise ValueError(
            "Safety-only scheduler drill requires manual baseline and every live source policy disabled"
        )
    start = datetime.now(timezone.utc)
    initial = scheduler_snapshot(start)
    if initial["active_scheduled_runs"]:
        raise ValueError("Let scheduled source runs settle before this safety drill")
    env = {
        **os.environ,
        "AIRFLOW_NEWS_CRAWLER_SCHEDULE": "*/2 * * * *",
        "AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE": "true",
        "AIRFLOW_NEWS_CRAWLER_LIMIT": "1",
    }
    result = {
        "scope": "SCHEDULE_SAFETY_ONLY_NO_LIVE_TRAFFIC",
        "started_at": start.isoformat(),
        "status": "RUNNING",
        "temporary_schedule": "*/2 * * * *",
        "live_sources_enabled": False,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    write(EVIDENCE / "scheduler-smoke.json", result)
    try:
        checked(
            COMPOSE
            + [
                "exec",
                "-T",
                "airflow-scheduler",
                "airflow",
                "dags",
                "pause",
                "news_crawling_pipeline",
            ]
        )
        checked(
            COMPOSE + ["up", "-d", "--force-recreate", "airflow-scheduler"], env=env
        )
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            try:
                checked(
                    COMPOSE
                    + [
                        "exec",
                        "-T",
                        "airflow-scheduler",
                        "airflow",
                        "dags",
                        "unpause",
                        "news_crawling_pipeline",
                    ]
                )
                snapshot = scheduler_snapshot(start)
                completed = [
                    r for r in snapshot["scheduled_runs"] if r["state"] == "success"
                ]
                print(
                    json.dumps(
                        {
                            "observed_at": datetime.now(timezone.utc).isoformat(),
                            "successful_scheduled_runs": len(completed),
                        }
                    ),
                    flush=True,
                )
                if len(completed) >= 2:
                    # Stop creation before collecting slower evidence or recreating
                    # the container. A queued/running extra cycle must settle too.
                    checked(
                        COMPOSE
                        + [
                            "exec",
                            "-T",
                            "airflow-scheduler",
                            "airflow",
                            "dags",
                            "pause",
                            "news_crawling_pipeline",
                        ]
                    )
                    snapshot = scheduler_snapshot(start)
                    if snapshot["active_scheduled_runs"]:
                        # Paused DAGs can leave remaining tasks unscheduled. Allow
                        # this fully denied cycle to finish before pausing again.
                        checked(
                            COMPOSE
                            + [
                                "exec",
                                "-T",
                                "airflow-scheduler",
                                "airflow",
                                "dags",
                                "unpause",
                                "news_crawling_pipeline",
                            ]
                        )
                        time.sleep(10)
                        continue
                    assert all(
                        row["state"] == "success" for row in snapshot["scheduled_runs"]
                    ), snapshot
                    completed = snapshot["scheduled_runs"]
                    break
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
            time.sleep(10)
        else:
            raise TimeoutError(
                "Scheduler-managed cycles did not settle within ten minutes"
            )
        ids = [r["run_id"] for r in completed]
        script = """import json,sys
from src.crawling.state import Repository
with Repository() as repo:
 rows=repo.query("SELECT source,status,metrics->>'skip_reason' AS reason,count(*) AS calls,sum(COALESCE((metrics->>'request_count')::integer,0)) AS requests FROM crawler_operations.crawl_runs WHERE metrics->>'airflow_run_id'=ANY(%s) GROUP BY source,status,metrics->>'skip_reason'",(json.loads(sys.argv[1]),))
print(json.dumps(rows))
"""
        output = checked(
            COMPOSE
            + [
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "news-pipeline",
                "python3",
                "-c",
                script,
                json.dumps(ids),
            ]
        )
        rows = json.loads(output)
        assert len(rows) == 5 and all(
            r["status"] == "SKIPPED"
            and r["reason"] in ("source_live_disabled", "source_disabled")
            and r["requests"] == 0
            and r["calls"] >= 2
            for r in rows
        ), rows
        assert not snapshot["overlapping_runs"], snapshot
        result.update(
            status="PASS",
            scheduler=snapshot,
            source_outcomes=rows,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        result.update(
            status="FAIL",
            error_type=type(exc).__name__,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        raise
    finally:
        # Pause first, including error paths, then recreate using unchanged .env/host baseline.
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
        checked(COMPOSE + ["up", "-d", "--force-recreate", "airflow-scheduler"])
        restored = container_json(["config-check"], scheduler=True)
        result["restored_schedule"] = restored["schedule_config"]
        result["restored_live_switch"] = restored["scheduled_live_switch"]
        if (
            restored["schedule_config"] != original["schedule_config"]
            or restored["scheduled_live_switch"] != original["scheduled_live_switch"]
        ):
            result["status"] = "FAIL"
            write(EVIDENCE / "scheduler-smoke.json", result)
            raise RuntimeError("Scheduler environment was not restored")
        if not initial["is_paused"]:
            checked(
                COMPOSE
                + [
                    "exec",
                    "-T",
                    "airflow-scheduler",
                    "airflow",
                    "dags",
                    "unpause",
                    "news_crawling_pipeline",
                ]
            )
        final = scheduler_snapshot(start)
        result["final_scheduler"] = final
        if final["active_scheduled_runs"] or any(
            row["state"] != "success" for row in final["scheduled_runs"]
        ):
            result["status"] = "FAIL"
            write(EVIDENCE / "scheduler-smoke.json", result)
            raise RuntimeError(
                "Scheduler rollback left unfinished or failed safety cycles"
            )
        write(EVIDENCE / "scheduler-smoke.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
