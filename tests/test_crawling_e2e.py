"""Offline websites -> real MinIO/Postgres/Spark/Delta/Qdrant/DuckDB acceptance.

Uses actual existing FastEmbed downstream jobs. Synthetic text never shares live
frontier, processing version, Qdrant collection or DuckDB serving file.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.crawling.jobs import crawl, publish
from src.crawling.sources import SOURCES
from src.crawling.state import Repository
from tests.test_crawling_state import FixtureClient


def main():
    started = time.monotonic()
    suffix = uuid.uuid4().hex[:8]
    output = {"data_kind": "FIXTURE", "scenario": suffix, "sources": {}, "checks": {}}
    os.environ["CRAWLER_FIXTURE_VERSION"] = "fixture-crawl-v1"
    os.environ["CRAWLER_FIXTURE_STATE_NAMESPACE"] = "fixture-acceptance"
    with Repository() as repo:
        repo.seed()
        # Re-enable only this fixture suite's rows, for deterministic repeatability.
        repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now(),status='NEW',observation_hash=NULL WHERE source LIKE 'fixture-acceptance:%%'"
        )
        repo.query(
            "UPDATE crawler_operations.source_state SET cooldown_until=NULL WHERE source LIKE 'fixture-acceptance:%%'"
        )
        for key, source in SOURCES.items():
            run = crawl(
                key,
                trigger="FIXTURE",
                limit=1,
                repository=repo,
                client=FixtureClient(source),
            )
            assert run["status"] == "SUCCESS" and run["changed"] == 1, run
            publish_result = publish(key, repository=repo, fixture=True)
            output["sources"][key] = {"crawl": run, "publish": publish_result}
            no_request = crawl(
                key,
                trigger="FIXTURE",
                limit=1,
                repository=repo,
                client=FixtureClient(source),
            )
            assert no_request["fetched"] == 0
        output["checks"]["all_five_fixture_sources"] = True
        output["checks"]["repeat_discovery_fetches_no_known_ineligible_articles"] = True
        # Replay/unchanged: observations retained but no new downstream outbox.
        repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source='fixture-acceptance:cafef'"
        )
        unchanged = crawl(
            "cafef",
            trigger="FIXTURE",
            limit=1,
            repository=repo,
            client=FixtureClient(SOURCES["cafef"]),
        )
        assert unchanged["changed"] == 0 and unchanged["unchanged"] == 1
        output["checks"]["unchanged_recheck_no_batch"] = True
        # Changed content travels through the Phase05 delta merges and removes
        # old Qdrant points through existing affected-article indexing.
        repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source='fixture-acceptance:cafef'"
        )
        corrected = crawl(
            "cafef",
            trigger="FIXTURE",
            limit=1,
            repository=repo,
            client=FixtureClient(SOURCES["cafef"], changed=True),
        )
        assert corrected["changed"] == 1
        changed_publish = publish("cafef", repository=repo, fixture=True)
        batch_id = corrected["batch_ids"][0]
        stages = repo.query(
            "SELECT stage_name,metrics FROM pipeline_operations.pipeline_stage_runs WHERE run_id=%s AND status='SUCCESS'",
            ("pipeline-" + batch_id,),
        )
        silver = next(
            s["metrics"] for s in stages if s["stage_name"].endswith(":silver_merge")
        )
        reconciliation = next(
            s["metrics"] for s in stages if s["stage_name"].endswith(":reconciliation")
        )
        assert silver["affected_article_count"] == 1
        assert reconciliation["status"] == "PASS", reconciliation
        output["checks"]["changed_content_updates_existing_silver_gold_serving"] = True
        output["changed_publish"] = changed_publish
        # Operational publisher failure leaves durable outbox. Same batch can
        # resume from committed stages without fetching the site.
        repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source='fixture-acceptance:vnexpress'"
        )
        crawl(
            "vnexpress",
            trigger="FIXTURE",
            limit=1,
            repository=repo,
            client=FixtureClient(SOURCES["vnexpress"], changed=True),
        )
        with patch(
            "src.news_pipeline.pipeline_runner.execute",
            side_effect=RuntimeError("injected_publisher_failure"),
        ):
            try:
                publish("vnexpress", repository=repo, fixture=True)
            except RuntimeError:
                pass
            else:
                raise AssertionError("failure injection did not fail")
        assert repo.pending("fixture-acceptance:vnexpress")
        recovered = publish("vnexpress", repository=repo, fixture=True)
        assert not repo.pending("fixture-acceptance:vnexpress")
        output["checks"]["durable_outbox_publisher_retry_no_refetch"] = True
        output["recovery"] = recovered
        # Restore base fixture content so the manual DAG demo remains aligned.
        for key in ("cafef", "vnexpress"):
            repo.query(
                "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source=%s",
                ("fixture-acceptance:" + key,),
            )
            crawl(
                key,
                trigger="FIXTURE",
                limit=1,
                repository=repo,
                client=FixtureClient(SOURCES[key]),
            )
            publish(key, repository=repo, fixture=True)
    output.update(
        {
            "status": "PASS",
            "duration_seconds": round(time.monotonic() - started, 3),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    path = Path("/app/local/phase8-e2e.json")
    path.write_text(json.dumps(output, indent=2, default=str))
    print(
        json.dumps(
            {
                "status": output["status"],
                "checks": output["checks"],
                "duration_seconds": output["duration_seconds"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
