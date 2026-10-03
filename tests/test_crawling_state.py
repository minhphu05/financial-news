"""Landing replay, persistent frontier, retries and source failure isolation."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.crawling.http_client import FetchError, HttpClient, Response, RobotsPolicy
from src.crawling.jobs import crawl
from src.crawling.landing import Landing, immutable_put
from src.crawling.sources import SOURCES
from src.crawling.state import Repository, SourceBusy
from src.news_pipeline.source_schema import validate_source_file

FIXTURES = Path(__file__).parent / "fixtures/crawling"


class MemoryStore:
    def __init__(self):
        self.objects = {}

    def ensure_bucket(self):
        pass

    def exists(self, key):
        return key in self.objects

    def put_bytes(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_bytes(self, key):
        return self.objects[key]

    def upload_file(self, path, key):
        self.objects[key] = Path(path).read_bytes()

    def list_keys(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]


class FixtureClient:
    is_fixture = True
    request_count = 0
    retry_count = 0

    def __init__(self, source, *, changed=False, error=None):
        self.source = source
        self.changed = changed
        self.error = error

    def fetch(self, url):
        self.request_count += 1
        if url == self.source.listing:
            return Response(
                url,
                (FIXTURES / (self.source.key + "-listing.html")).read_bytes(),
                200,
                {"content-type": "text/html"},
            )
        if self.error:
            raise self.error
        body = (FIXTURES / (self.source.key + ".html")).read_bytes()
        if self.changed:
            body = body.replace(b"SYNTHETIC fixture", b"SYNTHETIC CORRECTED fixture")
        return Response(url, body, 200, {"content-type": "text/html"})


class StoragePolicyTests(unittest.TestCase):
    def test_landing_immutable_conflict(self):
        store = MemoryStore()
        immutable_put(store, "x", b"a")
        immutable_put(store, "x", b"a")
        with self.assertRaises(ValueError):
            immutable_put(store, "x", b"b")

    def test_batch_restore_checksum_and_schema(self):
        store = MemoryStore()
        landing = Landing(store)
        rows = [
            {
                "link": "https://cafef.vn/test-123456.chn",
                "title": "Title",
                "context": "Body",
                "summary": "",
                "post date": "",
            }
        ]
        key, m = landing.batch(
            "cafef",
            rows,
            ["observed"],
            "test-run",
            "2026-10-03",
            "test-v1",
            "adapter-v1",
        )
        with tempfile.TemporaryDirectory() as d:
            restored, path = landing.restore(key, d)
            self.assertEqual(restored, m)
            self.assertTrue(validate_source_file(path)["compatible"])
            store.objects[m["bronze_input_key"]] = b"corrupt"
            with self.assertRaises(ValueError):
                landing.restore(key, d)

    def test_raw_html_retained_and_fixture_scope(self):
        store = MemoryStore()
        landing = Landing(store)
        env = {
            "source": "cafef",
            "url": "https://cafef.vn/test-123456.chn",
            "crawl_run_id": "test",
            "data_kind": "FIXTURE",
        }
        key, m = landing.observation(env, b"<html>full evidence</html>")
        self.assertIn("landing/fixture/", key)
        self.assertEqual(
            store.get_bytes(m["raw_html_key"]), b"<html>full evidence</html>"
        )

    def test_retry_after_prevents_immediate_retry(self):
        client = HttpClient(SOURCES["cafef"], user_agent="Research/1")
        client.policy = RobotsPolicy("User-agent: *\nAllow: /", "Research/1")
        with patch.object(
            client, "_request", side_effect=FetchError("http_429", 429, 120, True)
        ) as request:
            with self.assertRaises(FetchError):
                client.fetch("https://cafef.vn/test-123456.chn")
            self.assertEqual(request.call_count, 1)

    def test_404_is_not_retried(self):
        client = HttpClient(SOURCES["cafef"], user_agent="Research/1")
        client.policy = RobotsPolicy("", "Research/1")
        with patch.object(
            client, "_request", side_effect=FetchError("http_404", 404)
        ) as request:
            with self.assertRaises(FetchError):
                client.fetch("https://cafef.vn/test-123456.chn")
            self.assertEqual(request.call_count, 1)

    def test_retryable_network_is_bounded(self):
        client = HttpClient(SOURCES["cafef"], user_agent="Research/1", retries=2)
        client.policy = RobotsPolicy("", "Research/1")
        with (
            patch.object(
                client,
                "_request",
                side_effect=FetchError("network_error", retryable=True),
            ) as request,
            patch("src.crawling.http_client.time.sleep"),
        ):
            with self.assertRaises(FetchError):
                client.fetch("https://cafef.vn/test-123456.chn")
            self.assertEqual(request.call_count, 3)


@unittest.skipUnless(
    os.getenv("CRAWLER_DB_TESTS") == "1", "explicit local PostgreSQL integration only"
)
class FrontierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Repository()
        cls.repo.seed()

    @classmethod
    def tearDownClass(cls):
        cls.repo.connection.close()

    def setUp(self):
        # This suite owns only fixture state. It never deletes live frontier.
        self.repo.query(
            "DELETE FROM crawler_operations.batches WHERE source LIKE 'fixture-unit:%%'"
        )
        self.repo.query(
            "DELETE FROM crawler_operations.crawl_attempts WHERE crawl_run_id IN (SELECT crawl_run_id FROM crawler_operations.crawl_runs WHERE source LIKE 'fixture-unit:%%')"
        )
        self.repo.query(
            "DELETE FROM crawler_operations.crawl_runs WHERE source LIKE 'fixture-unit:%%'"
        )
        self.repo.query(
            "DELETE FROM crawler_operations.frontier WHERE source LIKE 'fixture-unit:%%'"
        )
        self.repo.query(
            "DELETE FROM crawler_operations.source_state WHERE source LIKE 'fixture-unit:%%'"
        )
        self.store = MemoryStore()
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "CRAWLER_WORK_DIR": self.directory.name,
                "CRAWLER_FIXTURE_VERSION": "fixture-unit-v1",
                "CRAWLER_FIXTURE_STATE_NAMESPACE": "fixture-unit",
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def run_source(self, key="cafef", **kwargs):
        return crawl(
            key,
            trigger="FIXTURE",
            limit=1,
            repository=self.repo,
            store=self.store,
            client=FixtureClient(SOURCES[key], **kwargs),
        )

    def test_incremental_duplicate_discovery_and_persistent_restart(self):
        first = self.run_source()
        self.assertEqual(first["changed"], 1)
        with Repository() as fresh:
            self.assertEqual(len(fresh.eligible("fixture-unit:cafef", 20, 7)), 0)
        second = self.run_source()
        self.assertEqual(second["fetched"], 0)
        self.assertEqual(
            len(
                self.repo.selected(
                    "fixture-unit:cafef",
                    [json.loads((FIXTURES / "cafef.json").read_text())["url"]],
                )
            ),
            1,
        )
        self.assertEqual(len(self.repo.pending("fixture-unit:cafef")), 1)

    def test_recheck_unchanged_no_downstream_batch_then_changed(self):
        first = self.run_source()
        self.repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source='fixture-unit:cafef'"
        )
        unchanged = self.run_source()
        self.assertEqual(unchanged["unchanged"], 1)
        self.assertEqual(unchanged["changed"], 0)
        self.repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source='fixture-unit:cafef'"
        )
        changed = self.run_source(changed=True)
        self.assertEqual(changed["changed"], 1)
        self.assertNotEqual(first["batch_ids"], changed["batch_ids"])

    def test_content_reverts_create_new_event_batch(self):
        first = self.run_source()
        self.repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source='fixture-unit:cafef'"
        )
        self.run_source(changed=True)
        self.repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source='fixture-unit:cafef'"
        )
        reverted = self.run_source()
        self.assertEqual(reverted["changed"], 1)
        self.assertNotEqual(first["batch_ids"], reverted["batch_ids"])
        self.assertEqual(len(self.repo.pending("fixture-unit:cafef")), 3)

    def test_backfill_window_does_not_hide_future_normal_ingestion(self):
        from datetime import date

        result = crawl(
            "cafef",
            trigger="BACKFILL",
            urls=[json.loads((FIXTURES / "cafef.json").read_text())["url"]],
            from_date=date(2020, 1, 1),
            to_date=date(2020, 1, 2),
            repository=self.repo,
            store=self.store,
            client=FixtureClient(SOURCES["cafef"]),
        )
        self.assertEqual(result["changed"], 0)
        self.repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source='fixture-unit:cafef'"
        )
        self.assertEqual(self.run_source()["changed"], 1)

    def test_explicit_recrawl_fetches_even_before_next_recheck(self):
        self.run_source()
        result = crawl(
            "cafef",
            trigger="RECRAWL",
            urls=[json.loads((FIXTURES / "cafef.json").read_text())["url"]],
            repository=self.repo,
            store=self.store,
            client=FixtureClient(SOURCES["cafef"]),
        )
        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["unchanged"], 1)

    def test_backfill_window_admits_reviewed_publication(self):
        from datetime import date

        result = crawl(
            "cafef",
            trigger="BACKFILL",
            urls=[json.loads((FIXTURES / "cafef.json").read_text())["url"]],
            from_date=date(2026, 10, 1),
            to_date=date(2026, 10, 4),
            repository=self.repo,
            store=self.store,
            client=FixtureClient(SOURCES["cafef"]),
        )
        self.assertEqual(result["changed"], 1)
        self.assertEqual(len(self.repo.pending("fixture-unit:cafef")), 1)

    def test_source_failure_isolation(self):
        failed = self.run_source("cafef", error=FetchError("http_403", 403))
        good = self.run_source("vnexpress")
        self.assertEqual(failed["status"], "BLOCKED")
        self.assertEqual(good["status"], "SUCCESS")
        self.assertEqual(len(self.repo.pending("fixture-unit:vnexpress")), 1)
        self.assertEqual(len(self.repo.pending("fixture-unit:cafef")), 0)

    def test_retry_after_persists_cooldown(self):
        result = self.run_source(error=FetchError("http_429", 429, 120, True))
        self.assertEqual(result["http_429"], 1)
        with self.assertRaises(SourceBusy):
            self.run_source()

    def test_lock_excludes_parallel_worker(self):
        with self.repo.lock("fixture-unit:cafef"), Repository() as other:  # noqa: SIM117
            with self.assertRaises(SourceBusy):
                with other.lock("fixture-unit:cafef"):
                    pass

    def test_failed_landing_does_not_advance_hash(self):
        with patch.object(self.store, "put_bytes", side_effect=OSError("storage_down")):
            result = self.run_source()
        self.assertEqual(result["status"], "FAILED")
        rows = self.repo.query(
            "SELECT content_hash FROM crawler_operations.frontier WHERE source='fixture-unit:cafef'"
        )
        self.assertIsNone(rows[0]["content_hash"])

    def test_frontier_old_success_not_automatically_recrawled(self):
        self.run_source()
        self.repo.query(
            "UPDATE crawler_operations.frontier SET first_seen_at=now()-interval '30 days',next_eligible_at=now() WHERE source='fixture-unit:cafef'"
        )
        self.assertEqual(self.run_source()["fetched"], 0)


if __name__ == "__main__":
    unittest.main()
