"""Translate source-batch DAG parameters into the standalone crawler jobs."""

import json
import os
import sys

from src.crawling.jobs import crawl, publish
from src.crawling.sources import SOURCES


def main():
    source = os.environ["CRAWLER_SOURCE_KEY"]
    stage = os.environ["CRAWLER_STAGE"]
    selected = json.loads(os.getenv("CRAWLER_SELECTED_SOURCES", "[]"))
    if source not in selected:
        sys.exit(99)
    fixture = os.getenv("CRAWLER_FIXTURE_MODE", "true").lower() == "true"
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
            )
        else:
            if os.getenv("CRAWLER_ALLOW_LIVE", "false").lower() != "true":
                raise ValueError("Live DAG requires allow_live=true")
            result = crawl(source, limit=int(os.getenv("CRAWLER_BATCH_LIMIT", "1")))
        print(json.dumps(result, default=str))
        if result["status"] in ("FAILED", "BLOCKED"):
            sys.exit(2)
    elif stage == "publish":
        print(json.dumps(publish(source, fixture=fixture), default=str))
    else:
        raise ValueError("Unknown crawler stage")


if __name__ == "__main__":
    main()
