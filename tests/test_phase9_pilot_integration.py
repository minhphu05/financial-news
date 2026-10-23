"""Real PostgreSQL + synthetic redirected responses; never public HTTP."""

import os
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.crawling.http_client import Response
from src.crawling.jobs import crawl
from src.crawling.sources import SOURCES
from src.crawling.state import Repository
from tests.test_crawling_state import FixtureClient, MemoryStore


@unittest.skipUnless(os.getenv("PHASE9_DB_TESTS") == "1", "requires local PostgreSQL")
class RedirectRecoveryTests(unittest.TestCase):
    def test_unsupported_redirect_is_terminal_for_url_and_does_not_stall_frontier(self):
        class Redirected(FixtureClient):
            def fetch(self, url):
                if url == self.source.listing:
                    return super().fetch(url)
                return Response(
                    "https://" + self.source.host + "/",
                    b"<html>Home</html>",
                    200,
                    {"content-type": "text/html"},
                )

        namespace = "fixture-pilot-" + uuid4().hex
        state_source = namespace + ":cafef"
        with (
            Repository() as repo,
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "CRAWLER_FIXTURE_STATE_NAMESPACE": namespace,
                    "CRAWLER_WORK_DIR": directory,
                },
            ),
        ):
            try:
                result = crawl(
                    "cafef",
                    trigger="FIXTURE",
                    limit=1,
                    client=Redirected(SOURCES["cafef"]),
                    repository=repo,
                    store=MemoryStore(),
                )
                self.assertEqual(result["status"], "PARTIAL")
                self.assertEqual(result["http_failures"], 1)
                self.assertFalse(result["batch_ids"])
                row = repo.query(
                    "SELECT status,last_error FROM crawler_operations.frontier WHERE source=%s",
                    (state_source,),
                )[0]
                self.assertEqual(row["status"], "PERMANENT_FAILURE")
                self.assertEqual(row["last_error"], "unsupported_article_redirect")
                self.assertEqual(repo.eligible(state_source, 1, 7), [])
                repo.discover(
                    state_source, ["https://cafef.vn/another-valid-999999.chn"]
                )
                self.assertEqual(len(repo.eligible(state_source, 1, 7)), 1)
            finally:
                repo.query(
                    "DELETE FROM crawler_operations.crawl_attempts WHERE crawl_run_id IN (SELECT crawl_run_id FROM crawler_operations.crawl_runs WHERE source=%s)",
                    (state_source,),
                )
                for table in ("batches", "crawl_runs", "frontier", "source_state"):
                    repo.query(
                        f"DELETE FROM crawler_operations.{table} WHERE source=%s",
                        (state_source,),
                    )


if __name__ == "__main__":
    unittest.main()
