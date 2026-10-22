"""Translate source-batch DAG parameters into the standalone crawler jobs."""

import json
import os
import sys

from src.crawling.jobs import crawl, publish
from src.crawling.sources import SOURCES
from src.crawling.state import Repository, SourceBusy
from src.crawling.policy import gate
from src.news_pipeline.structured_log import event


def main():
    source = os.environ["CRAWLER_SOURCE_KEY"]
    stage = os.environ["CRAWLER_STAGE"]
    selected = json.loads(os.getenv("CRAWLER_SELECTED_SOURCES", "[]"))
    if source not in selected:
        sys.exit(99)
    fixture = os.getenv("CRAWLER_FIXTURE_MODE", "true").lower() == "true"
    scheduled = os.getenv("CRAWLER_AIRFLOW_RUN_TYPE") == "scheduled"
    allow_live = os.getenv("CRAWLER_ALLOW_LIVE", "false").lower() == "true"
    if scheduled:
        fixture = False
        allow_live = (
            os.getenv("CRAWLER_SCHEDULED_LIVE_ALLOWED", "false").lower() == "true"
        )
    if not fixture and not allow_live:
        raise ValueError("Live DAG requires explicit opt-in")
    if stage == "crawl":
        if fixture:
            # Fixture transport stays in tests. Runtime public HTTP never
            # generates fixture article content or embeddings.
            from tests.test_crawling_state import FixtureClient

            result = crawl(
                source,
                trigger="FIXTURE",
                limit=int(os.getenv("CRAWLER_BATCH_LIMIT", "1")),
                client=FixtureClient(SOURCES[source]),
                skip_busy=True,
            )
        else:
            try:
                result = crawl(
                    source,
                    limit=int(os.getenv("CRAWLER_BATCH_LIMIT", "1")),
                    allow_live=allow_live,
                    scheduled=scheduled,
                    skip_busy=True,
                )
            except SourceBusy:
                event(
                    "crawler_run_skipped",
                    source=source,
                    outcome="SKIPPED_BY_POLICY",
                    reason="source_lock_busy",
                )
                sys.exit(99)
        print(json.dumps(result, default=str))
        if result["status"] in ("FAILED", "BLOCKED"):
            sys.exit(2)
        if result["status"] == "SKIPPED":
            sys.exit(99)
    elif stage == "publish":
        with Repository() as repo:
            if gate(
                repo.config(source, allow_disabled=True),
                fixture=fixture,
                allow_live=allow_live,
            ):
                sys.exit(99)
        print(
            json.dumps(
                publish(
                    source, fixture=fixture, scheduled=scheduled, respect_retry=True
                ),
                default=str,
            )
        )
    else:
        raise ValueError("Unknown crawler stage")


if __name__ == "__main__":
    main()
