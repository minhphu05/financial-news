"""Persisted MinIO/outbox recovery across processes and a real scheduler restart.

Offline synthetic transport, real local FastEmbed/Delta/Qdrant/DuckDB. Only fixture
serving is touched; this test is invoked explicitly by the host drill tool.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from src.crawling.jobs import crawl, publish
from src.crawling.sources import SOURCES
from src.crawling.state import Repository
from tests.test_crawling_state import FixtureClient

STATE = Path("/app/local/phase9-recovery.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "fail", "recover"))
    args = parser.parse_args()
    if args.mode == "prepare":
        state = {
            "source": "vnexpress",
            "namespace": "fixture-phase9-restart-" + uuid4().hex[:8],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        state = json.loads(STATE.read_text())
    os.environ["CRAWLER_FIXTURE_STATE_NAMESPACE"] = state["namespace"]
    os.environ["CRAWLER_FIXTURE_VERSION"] = "fixture-crawl-v1"
    source = state["source"]
    state_source = state["namespace"] + ":" + source
    with Repository() as repo:
        if args.mode == "prepare":
            observed = crawl(
                source,
                trigger="FIXTURE",
                limit=1,
                repository=repo,
                client=FixtureClient(SOURCES[source], changed=True),
            )
            assert observed["status"] == "SUCCESS" and observed["changed"] == 1, (
                observed
            )
            state.update(
                batch_id=observed["batch_ids"][0], crawl_run_id=observed["crawl_run_id"]
            )
        elif args.mode == "fail":
            os.environ["NEWS_QDRANT_URL"] = "http://qdrant:1"
            try:
                publish(source, repository=repo, fixture=True)
            except Exception as exc:
                state["injected_error_type"] = type(exc).__name__
            else:
                raise AssertionError("Qdrant failure injection unexpectedly succeeded")
            pending = repo.pending(state_source)
            assert len(pending) == 1 and pending[0]["status"] == "FAILED", pending
            stages = repo.query(
                "SELECT stage_name,status,attempt FROM pipeline_operations.pipeline_stage_runs WHERE run_id=%s ORDER BY stage_run_id",
                ("pipeline-" + state["batch_id"],),
            )
            assert any(
                s["stage_name"].endswith(":qdrant_upsert") and s["status"] == "FAILED"
                for s in stages
            ), stages
            assert any(
                s["stage_name"].endswith(":gold_rag_merge") and s["status"] == "SUCCESS"
                for s in stages
            ), stages
            state.update(
                failed_at=datetime.now(timezone.utc).isoformat(),
                stages_before_restart=stages,
            )
        else:
            before = repo.query(
                "SELECT count(*) AS count FROM crawler_operations.crawl_runs WHERE source=%s",
                (state_source,),
            )[0]["count"]
            result = publish(source, repository=repo, fixture=True)
            assert result["published_batches"] == 1 and not repo.pending(
                state_source
            ), result
            after = repo.query(
                "SELECT count(*) AS count FROM crawler_operations.crawl_runs WHERE source=%s",
                (state_source,),
            )[0]["count"]
            assert before == after, (
                "Publisher refetched source instead of replaying durable input"
            )
            stages = repo.query(
                "SELECT stage_name,status,attempt,metrics FROM pipeline_operations.pipeline_stage_runs WHERE run_id=%s ORDER BY stage_run_id",
                ("pipeline-" + state["batch_id"],),
            )
            qdrant = [s for s in stages if s["stage_name"].endswith(":qdrant_upsert")]
            assert [s["status"] for s in qdrant] == ["FAILED", "SUCCESS"], qdrant
            assert all(
                s["attempt"] == 1
                for s in stages
                if s["stage_name"].endswith(
                    (":bronze_ingest", ":silver_merge", ":gold_rag_merge")
                )
            ), stages
            reconciliation = next(
                s["metrics"]
                for s in stages
                if s["stage_name"].endswith(":reconciliation")
                and s["status"] == "SUCCESS"
            )
            assert reconciliation["status"] == "PASS", reconciliation
            state.update(
                recovered_at=datetime.now(timezone.utc).isoformat(),
                no_refetch=True,
                upstream_success_reused=True,
                reconciliation=reconciliation,
                stages_after_restart=[
                    {k: s[k] for k in ("stage_name", "status", "attempt")}
                    for s in stages
                ],
            )
            # Leave the shared fixture serving projection on its base content.
            repo.query(
                "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source=%s",
                (state_source,),
            )
            restored = crawl(
                source,
                trigger="FIXTURE",
                limit=1,
                repository=repo,
                client=FixtureClient(SOURCES[source]),
            )
            assert restored["changed"] == 1, restored
            publish(source, repository=repo, fixture=True)
            state["status"] = "PASS"
    STATE.write_text(json.dumps(state, indent=2, default=str) + "\n")
    print("PHASE9_RECOVERY=" + json.dumps(state, default=str))


if __name__ == "__main__":
    main()
