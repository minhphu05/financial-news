"""Real PostgreSQL operations + synthetic transport; no public website traffic."""

from datetime import datetime, timezone
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.crawling.jobs import crawl, publish
from src.crawling.http_client import FetchError, Response
from src.crawling.state import Repository
from src.crawling.sources import SOURCES
from tests.test_crawling_state import FixtureClient, MemoryStore


@unittest.skipUnless(
    os.getenv("PHASE9_DB_TESTS") == "1", "requires explicit local PostgreSQL"
)
class ContinuousTests(unittest.TestCase):
    def test_empty_discovery_is_visible_without_inventing_articles(self):
        class EmptyListing(FixtureClient):
            def fetch(self, url):
                return Response(
                    url,
                    b"<html><main>No article links</main></html>",
                    200,
                    {"content-type": "text/html"},
                )

        result = self.run_source(client=EmptyListing(SOURCES["cafef"]))
        self.assertEqual(result["discovery_empty"], 1)
        self.assertEqual(result["fetched"], 0)
        self.assertFalse(result["batch_ids"])

    def setUp(self):
        self.repo = Repository()
        self.repo.seed()
        self.original = self.repo.query(
            "SELECT source_id,enabled,config FROM control_metadata.news_sources WHERE source_type='crawler'"
        )
        for table in (
            "batches",
            "crawl_attempts",
            "crawl_runs",
            "frontier",
            "source_state",
        ):
            where = (
                "crawl_run_id IN (SELECT crawl_run_id FROM crawler_operations.crawl_runs WHERE source LIKE 'fixture-phase9:%%')"
                if table == "crawl_attempts"
                else "source LIKE 'fixture-phase9:%%'"
            )
            self.repo.query(f"DELETE FROM crawler_operations.{table} WHERE {where}")
        self.store = MemoryStore()
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "CRAWLER_FIXTURE_STATE_NAMESPACE": "fixture-phase9",
                "CRAWLER_WORK_DIR": self.temp.name,
                "CRAWLER_FIXTURE_VERSION": "fixture-phase9-v1",
            },
        )
        self.env.start()

    def tearDown(self):
        for row in self.original:
            self.repo.query(
                "UPDATE control_metadata.news_sources SET config=%s::jsonb,enabled=%s WHERE source_id=%s",
                (json.dumps(row["config"]), row["enabled"], row["source_id"]),
            )
        self.env.stop()
        self.temp.cleanup()
        self.repo.connection.close()

    def run_source(self, key="cafef", client=None, **kwargs):
        return crawl(
            key,
            trigger="FIXTURE",
            limit=1,
            client=client or FixtureClient(SOURCES[key]),
            repository=self.repo,
            store=self.store,
            **kwargs,
        )

    def due(self, key="cafef"):
        self.repo.query(
            "UPDATE crawler_operations.frontier SET next_eligible_at=now() WHERE source=%s",
            ("fixture-phase9:" + key,),
        )

    def test_disabled_source_is_persisted_skip_other_source_continues(self):
        self.repo.query(
            "UPDATE control_metadata.news_sources SET enabled=false WHERE source_id='crawler:cafef'"
        )
        client = FixtureClient(SOURCES["cafef"])
        result = self.run_source(client=client)
        self.assertEqual(result["status"], "SKIPPED")
        self.assertEqual(client.request_count, 0)
        self.assertEqual(self.run_source("vnexpress")["status"], "SUCCESS")
        self.assertEqual(
            self.repo.query(
                "SELECT status FROM crawler_operations.crawl_runs WHERE crawl_run_id=%s",
                (result["crawl_run_id"],),
            )[0]["status"],
            "SKIPPED",
        )

    def test_http_200_invalid_body_is_parser_failure_with_landing_evidence(self):
        class Invalid(FixtureClient):
            def fetch(self, url):
                if url == self.source.listing:
                    return super().fetch(url)
                return Response(
                    url,
                    b"<html><h1>Layout changed</h1></html>",
                    200,
                    {"content-type": "text/html"},
                )

        result = self.run_source(client=Invalid(SOURCES["cafef"]))
        self.assertEqual(result["parser_failures"], 1)
        self.assertEqual(result["parse_successes"], 0)
        self.assertEqual(result["http_failures"], 0)
        self.assertFalse(result["batch_ids"])
        self.assertTrue(any(key.endswith(".html") for key in self.store.objects))
        self.assertIn("last_landing_at", result)

    def test_block_is_latched_and_prevents_future_requests(self):
        self.assertEqual(
            self.run_source(
                client=FixtureClient(
                    SOURCES["cafef"], error=FetchError("http_403", 403)
                )
            )["status"],
            "BLOCKED",
        )
        client = FixtureClient(SOURCES["cafef"])
        self.assertEqual(
            self.run_source(client=client, skip_busy=True)["status"], "SKIPPED"
        )
        self.assertEqual(client.request_count, 0)
        self.assertEqual(self.run_source("vnexpress")["status"], "SUCCESS")

    def test_clear_block_preserves_server_retry_after(self):
        from src.crawling.operations import clear_block

        self.run_source(
            client=FixtureClient(
                SOURCES["cafef"], error=FetchError("http_403", 403, 120)
            )
        )
        clear_block(self.repo, "fixture-phase9:cafef")
        client = FixtureClient(SOURCES["cafef"])
        result = self.run_source(client=client, skip_busy=True)
        self.assertEqual(result["status"], "SKIPPED")
        self.assertEqual(result["skip_reason"], "source_retry_after_cooldown")
        self.assertEqual(client.request_count, 0)

    def test_outbox_backoff_budget_and_recovery_without_refetch(self):
        self.run_source()
        keys = set(self.store.objects)
        with patch(
            "src.news_pipeline.pipeline_runner.execute",
            side_effect=RuntimeError("injected_downstream_outage"),
        ):
            with self.assertRaises(RuntimeError):
                publish(
                    "cafef",
                    repository=self.repo,
                    store=self.store,
                    fixture=True,
                    scheduled=True,
                )
        batch = self.repo.pending("fixture-phase9:cafef")[0]
        self.assertEqual(batch["attempts"], 1)
        self.assertGreater(batch["next_eligible_at"], datetime.now(timezone.utc))
        with patch("src.news_pipeline.pipeline_runner.execute") as execute:
            result = publish(
                "cafef",
                repository=self.repo,
                store=self.store,
                fixture=True,
                scheduled=True,
            )
            self.assertEqual(result["published_batches"], 0)
            self.assertEqual(result["status"], "PENDING")
            self.assertEqual(result["pending_batches_remaining"], 1)
            execute.assert_not_called()
        self.repo.query(
            "UPDATE crawler_operations.batches SET next_eligible_at=now() WHERE batch_id=%s",
            (batch["batch_id"],),
        )
        with (
            patch(
                "src.news_pipeline.pipeline_runner.execute",
                return_value={"status": "SUCCESS"},
            ) as execute,
            patch.object(
                FixtureClient, "fetch", side_effect=AssertionError("refetch forbidden")
            ),
        ):
            result = publish(
                "cafef",
                repository=self.repo,
                store=self.store,
                fixture=True,
                scheduled=True,
            )
            self.assertEqual(result["published_batches"], 1)
            execute.assert_called_once()
        self.assertEqual(set(self.store.objects), keys)
        self.assertFalse(self.repo.pending("fixture-phase9:cafef"))

    def test_high_backlog_is_drained_in_bounded_passes(self):
        self.repo.query(
            "UPDATE control_metadata.news_sources SET config=jsonb_set(config,'{crawler,publish_max_batches}','1') WHERE source_id='crawler:cafef'"
        )
        self.run_source()
        self.due()
        self.run_source(client=FixtureClient(SOURCES["cafef"], changed=True))
        self.due()
        self.run_source()
        self.assertEqual(len(self.repo.pending("fixture-phase9:cafef")), 3)
        with patch(
            "src.news_pipeline.pipeline_runner.execute",
            return_value={"status": "SUCCESS"},
        ):
            for remaining in (2, 1, 0):
                self.assertEqual(
                    publish(
                        "cafef",
                        repository=self.repo,
                        store=self.store,
                        fixture=True,
                        scheduled=True,
                    )["published_batches"],
                    1,
                )
                self.assertEqual(
                    len(self.repo.pending("fixture-phase9:cafef")), remaining
                )

    def test_interrupted_publisher_reclaims_only_under_source_lock(self):
        self.run_source()
        batch = self.repo.pending("fixture-phase9:cafef")[0]
        self.repo.query(
            "UPDATE crawler_operations.batches SET status='RUNNING',attempts=1 WHERE batch_id=%s",
            (batch["batch_id"],),
        )
        with Repository() as competing:
            with competing.lock("fixture-phase9:cafef"):
                from src.crawling.state import SourceBusy

                with self.assertRaises(SourceBusy):
                    publish(
                        "cafef",
                        repository=self.repo,
                        store=self.store,
                        fixture=True,
                        scheduled=True,
                    )
        with patch(
            "src.news_pipeline.pipeline_runner.execute",
            return_value={"status": "SUCCESS"},
        ):
            self.assertEqual(
                publish(
                    "cafef",
                    repository=self.repo,
                    store=self.store,
                    fixture=True,
                    scheduled=True,
                )["published_batches"],
                1,
            )
        self.assertEqual(
            self.repo.query(
                "SELECT attempts FROM crawler_operations.batches WHERE batch_id=%s",
                (batch["batch_id"],),
            )[0]["attempts"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
