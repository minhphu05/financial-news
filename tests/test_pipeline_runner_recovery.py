"""End-to-end CLI smoke for backfill, reprocess, Qdrant failure, and resume."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.storage import S3ObjectStore
from src.pipeline_operations.config import OperationsSettings
from src.pipeline_operations.repository import OperationsRepository


SPARK_COMMAND = [
    "/opt/spark/bin/spark-submit",
    "--packages", "io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4",
    "--conf", "spark.jars.ivy=/opt/news-ivy",
    "/app/src/news_pipeline/pipeline_runner.py",
]


def row(number: int, content: str, day: int) -> dict:
    return {
        "_id": f"recovery-{number}-{day}", "context": content, "index": number,
        "keyword": "finance", "link": f"https://phase05-recovery.local/article-{number}.chn",
        "metadata": {"Date": f"{day:02d}-08-2026", "Time": "09:00"},
        "page": 1, "post date": f"{day:02d}-08-2026 - 09:00 AM",
        "summary": f"Summary {number}", "ticket name": "Company",
        "ticket symbol": "AAA", "title": f"Article {number}",
    }


def invoke(args: list[str], env: dict[str, str], log: Path, expect_success: bool = True) -> int:
    with log.open("w", encoding="utf-8") as output:
        completed = subprocess.run(
            [*SPARK_COMMAND, *args], env=env, stdout=output,
            stderr=subprocess.STDOUT, text=True,
        )
    if expect_success and completed.returncode != 0:
        raise AssertionError(f"command failed ({completed.returncode}); inspect {log}")
    if not expect_success and completed.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded; inspect {log}")
    return completed.returncode


def main() -> None:
    suffix = uuid.uuid4().hex[:10]
    workspace = Path(f"/app/local/phase5-recovery-{suffix}")
    workspace.mkdir(parents=True)
    fixtures = workspace / "partitions"
    fixtures.mkdir()
    payloads = {
        "2026-08-01": [row(1, "Backfill article A.", 1), row(2, "Backfill article B.", 1)],
        "2026-08-02": [row(3, "Backfill article C.", 2)],
        "2026-08-03": [row(4, "Backfill article D.", 3)],
        "2026-08-04": [row(5, "Recovery article E.", 4)],
    }
    for partition, rows in payloads.items():
        (fixtures / f"{partition}.json").write_text(
            json.dumps(rows, ensure_ascii=False), encoding="utf-8"
        )
    drift = row(6, "Unsafe drift.", 5)
    drift["unapproved"] = "field"
    drift_file = fixtures / "2026-08-05.json"
    drift_file.write_text(json.dumps([drift]), encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "NEWS_SOURCE": "phase05-recovery.local",
        "NEWS_PROCESSING_VERSION": f"phase05-recovery-{suffix}",
        "NEWS_QDRANT_COLLECTION": f"phase05_recovery_{suffix}",
        "NEWS_DUCKDB_PATH": f"/app/local/phase05-recovery-{suffix}.duckdb",
        "NEWS_INDEX_LIMIT": "0",
        "NEWS_SOURCE_FILE": str(fixtures / "2026-08-01.json"),
    })
    started = time.monotonic()
    run_ids = {
        "backfill": f"recovery-backfill-{suffix}",
        "backfill_repeat": f"recovery-backfill-repeat-{suffix}",
        "reprocess": f"recovery-reprocess-{suffix}",
        "qdrant_failure": f"recovery-qdrant-failure-{suffix}",
        "schema_drift": f"recovery-schema-drift-{suffix}",
    }

    invoke([
        "backfill", "--from-date", "2026-08-01", "--to-date", "2026-08-03",
        "--partition-dir", str(fixtures), "--run-id", run_ids["backfill"],
    ], env, workspace / "backfill.log")
    invoke([
        "backfill", "--from-date", "2026-08-01", "--to-date", "2026-08-03",
        "--partition-dir", str(fixtures), "--run-id", run_ids["backfill_repeat"],
    ], env, workspace / "backfill-repeat.log")
    invoke([
        "reprocess", "--date", "2026-08-01", "--source-file",
        str(fixtures / "2026-08-01.json"), "--force-reprocess",
        "--run-id", run_ids["reprocess"],
    ], env, workspace / "reprocess.log")

    operations = OperationsSettings.from_env()
    gold = GoldSettings.from_env()
    store = S3ObjectStore(gold.news)
    with OperationsRepository(operations) as repository:
        backfill = repository.get_run(run_ids["backfill"])
        repeat = repository.get_run(run_ids["backfill_repeat"])
        reprocess = repository.get_run(run_ids["reprocess"])
        repeat_stages = repository.run_stages(run_ids["backfill_repeat"])
        assert backfill["status"] == "SUCCESS" and backfill["trigger_type"] == "BACKFILL"
        assert repeat["status"] == "SUCCESS" and repeat["trigger_type"] == "BACKFILL"
        assert reprocess["status"] == "SUCCESS" and reprocess["trigger_type"] == "REPROCESS"
        repeat_silver = [
            stage for stage in repeat_stages if stage["stage_name"].endswith(":silver_merge")
        ]
        assert len(repeat_silver) == 3
        assert all(stage["metrics"]["affected_article_count"] == 0 for stage in repeat_silver)
        assert repository.checkpoint(backfill["pipeline_name"], backfill["source"]) is None

    # Make Qdrant unreachable. Gold/analytics/DuckDB must commit, while checkpoint stays absent.
    failed_env = {**env, "NEWS_QDRANT_URL": "http://qdrant:1"}
    invoke([
        "incremental", "--date", "2026-08-04", "--source-file",
        str(fixtures / "2026-08-04.json"), "--run-id", run_ids["qdrant_failure"],
    ], failed_env, workspace / "qdrant-failure.log", expect_success=False)

    current = GoldSettings.from_env().for_current_tables()
    # Reconstruct settings from the environment used by the child.
    old_env = os.environ.copy()
    os.environ.update(env)
    try:
        current = GoldSettings.from_env().for_current_tables()
        gold_metrics = json.loads(store.get_bytes(f"{current.rag_prefix}/metrics.json"))
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    with OperationsRepository(operations) as repository:
        failed = repository.get_run(run_ids["qdrant_failure"])
        failed_stages = repository.run_stages(run_ids["qdrant_failure"])
        checkpoint_before_retry = repository.checkpoint(failed["pipeline_name"], failed["source"])
        assert failed["status"] == "FAILED"
        assert checkpoint_before_retry is None
        assert gold_metrics["gold_documents_produced"] == 5
        successful_before = {
            stage["stage_name"] for stage in failed_stages if stage["status"] == "SUCCESS"
        }
        assert any(name.endswith(":gold_rag_merge") for name in successful_before)
        assert any(name.endswith(":duckdb_publish") for name in successful_before)
        assert any(
            stage["stage_name"].endswith(":qdrant_upsert") and stage["status"] == "FAILED"
            for stage in failed_stages
        )

    invoke([
        "resume", "--run-id", run_ids["qdrant_failure"],
    ], env, workspace / "qdrant-resume.log")
    with OperationsRepository(operations) as repository:
        recovered = repository.get_run(run_ids["qdrant_failure"])
        recovered_stages = repository.run_stages(run_ids["qdrant_failure"])
        checkpoint_after_retry = repository.checkpoint(
            recovered["pipeline_name"], recovered["source"]
        )
        attempts = Counter(stage["stage_name"] for stage in recovered_stages)
        assert recovered["status"] == "SUCCESS"
        assert checkpoint_after_retry["last_successful_partition"] == date(2026, 8, 4)
        assert attempts[f"2026-08-04:qdrant_upsert"] == 2
        for stage_name in successful_before:
            assert attempts[stage_name] == 1

    # Unsafe source drift fails at schema_validation and never mutates the approved contract.
    contract = Path("/app/docs/data-contracts.md")
    contract_hash = hashlib.sha256(contract.read_bytes()).hexdigest() if contract.exists() else None
    invoke([
        "reprocess", "--date", "2026-08-05", "--source-file", str(drift_file),
        "--force-reprocess", "--run-id", run_ids["schema_drift"],
    ], env, workspace / "schema-drift.log", expect_success=False)
    if contract_hash:
        assert hashlib.sha256(contract.read_bytes()).hexdigest() == contract_hash
    with OperationsRepository(operations) as repository:
        drift_run = repository.get_run(run_ids["schema_drift"])
        drift_stages = repository.run_stages(run_ids["schema_drift"])
        assert drift_run["status"] == "FAILED"
        assert len(drift_stages) == 1
        assert drift_stages[0]["stage_name"].endswith(":schema_validation")

    result = {
        "status": "PASS",
        "scenario_id": suffix,
        "run_ids": run_ids,
        "backfill_range": ["2026-08-01", "2026-08-03"],
        "repeat_backfill_silver_affected": [stage["metrics"]["affected_article_count"] for stage in repeat_silver],
        "reprocess_force_required": True,
        "qdrant_failure_recorded": True,
        "gold_documents_durable_during_qdrant_failure": gold_metrics["gold_documents_produced"],
        "checkpoint_before_retry": checkpoint_before_retry,
        "checkpoint_after_retry": checkpoint_after_retry,
        "qdrant_attempts": attempts[f"2026-08-04:qdrant_upsert"],
        "upstream_successful_stage_attempts": {
            name: attempts[name] for name in sorted(successful_before)
        },
        "schema_drift_failed_before_bronze": len(drift_stages) == 1,
        "duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    Path("/app/local/phase5-recovery-results.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
