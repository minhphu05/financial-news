"""Standalone crawl/adapter/Bronze jobs; downstream processing reuses Phase05."""

import hashlib
import os
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.news_pipeline.bronze import ingest
from src.news_pipeline.config import Settings
from src.news_pipeline.normalize import normalize_observation
from src.news_pipeline.source_schema import validate_source_file
from src.news_pipeline.storage import create_object_store

from .adapters import SourceAdapter
from .http_client import FetchError, HttpClient
from .landing import Landing, encoded
from .sources import SOURCES, ParseError
from .state import Repository


def crawl(
    source_key,
    *,
    limit=None,
    urls=None,
    trigger="NORMAL",
    from_date=None,
    to_date=None,
    client=None,
    repository=None,
    store=None,
):
    source = SOURCES[source_key]
    if repository is None:
        with Repository() as repo:
            return crawl(
                source_key,
                limit=limit,
                urls=urls,
                trigger=trigger,
                from_date=from_date,
                to_date=to_date,
                client=client,
                repository=repo,
                store=store,
            )
    repo = repository
    config = repo.config(source_key)
    limit = config["max_articles"] if limit is None else limit
    if not 1 <= limit <= 20:
        raise ValueError("limit_must_be_between_1_and_20")
    if trigger == "BACKFILL" and (
        not urls or from_date is None or to_date is None or to_date < from_date
    ):
        raise ValueError("backfill_requires_explicit_urls_and_valid_date_window")
    if urls and len(urls) > 20:
        raise ValueError("explicit_url_scope_exceeds_20")
    data_kind = (
        "FIXTURE"
        if trigger == "FIXTURE" or getattr(client, "is_fixture", False)
        else "LIVE"
    )
    state_source = (
        (os.getenv("CRAWLER_FIXTURE_STATE_NAMESPACE", "fixture") + ":" + source_key)
        if data_kind == "FIXTURE"
        else source_key
    )
    if data_kind == "FIXTURE":
        config = {
            **config,
            "processing_version": os.getenv(
                "CRAWLER_FIXTURE_VERSION", "fixture-crawl-v1"
            ),
        }
    day = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    run = "crawl-" + source_key + "-" + uuid.uuid4().hex
    started = time.monotonic()
    metrics = {
        "discovered": 0,
        "fetched": 0,
        "changed": 0,
        "unchanged": 0,
        "failed": 0,
        "parser_failures": 0,
        "http_429": 0,
        "http_403": 0,
        "retry_count": 0,
        "batch_ids": [],
    }
    store = store or create_object_store(Settings.from_env())
    landing = Landing(store)
    client = client or HttpClient(
        source,
        user_agent=config["user_agent"],
        interval=config["request_interval_seconds"],
    )
    with repo.lock(state_source):
        repo.start(state_source, run, trigger)
        rows = []
        observations = []
        successes = []
        status = "SUCCESS"
        failure = None
        try:
            if urls:
                candidates = list(
                    dict.fromkeys(source.url(u, article=True) for u in urls)
                )
            else:
                candidates = []
                for listing in config["discovery_urls"]:
                    candidates.extend(source.discover(client.fetch(listing).body))
                candidates = list(dict.fromkeys(candidates))[:500]
            repo.discover(state_source, candidates)
            metrics["discovered"] = len(candidates)
            eligible = (
                repo.selected(state_source, candidates)[:limit]
                if trigger == "RECRAWL"
                else repo.eligible(state_source, limit, config["recent_days"])
            )
            # Backfill is an explicit bounded URL manifest, never the normal
            # global frontier and never guessed pagination/API endpoints.
            if trigger == "BACKFILL":
                eligible = [
                    r
                    for r in repo.selected(state_source, candidates)
                    if r["status"] in ("NEW", "RETRY")
                    and r["next_eligible_at"] <= datetime.now(timezone.utc)
                ][:limit]
            for row in eligible:
                try:
                    response = client.fetch(row["canonical_url"])
                    metrics["fetched"] += 1
                    envelope = {
                        "source": source_key,
                        "data_kind": data_kind,
                        "url": source.url(response.url, article=True),
                        "requested_url": row["canonical_url"],
                        "crawl_run_id": run,
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "http_status": response.status,
                        "http_headers": response.headers,
                        "parser_version": source.parser_version,
                        "raw_schema_version": source.raw_schema_version,
                        "payload": None,
                    }
                    # Keep HTTP evidence even when parsing fails.
                    key, raw_envelope = landing.observation(
                        {**envelope, "parse_status": "UNPARSED"}, response.body
                    )
                    payload = source.parse(response.body)
                    envelope = {
                        **raw_envelope,
                        "payload": payload,
                        "parse_status": "SUCCESS",
                    }
                    parsed_key = key.removesuffix(".json") + ".parsed.json"
                    from .landing import immutable_put

                    immutable_put(store, parsed_key, encoded(envelope))
                    adapted = SourceAdapter(source).adapt(envelope)
                    result = normalize_observation(
                        adapted, 0, "crawler", source.host, config["processing_version"]
                    )
                    if "valid" not in result:
                        raise ParseError(result["reject"]["reason"])
                    valid = result["valid"]
                    content_hash = valid["content_hash"]
                    signature = hashlib.sha256(
                        encoded(
                            {
                                k: valid[k]
                                for k in (
                                    "content_hash",
                                    "title",
                                    "description",
                                    "published_at_raw",
                                )
                            }
                        )
                    ).hexdigest()
                    changed = row["observation_hash"] != signature
                    inside = True
                    if trigger == "BACKFILL":
                        pub = valid["published_at"]
                        inside = pub is not None and from_date <= pub.date() <= to_date
                        if not inside:
                            metrics["outside_date_window"] = (
                                metrics.get("outside_date_window", 0) + 1
                            )
                    if changed and inside:
                        rows.append(adapted)
                        observations.append(parsed_key)
                        metrics["changed"] += 1
                    elif not changed:
                        metrics["unchanged"] += 1
                    successes.append(
                        (
                            row,
                            envelope,
                            (content_hash, signature)
                            if inside
                            else (row["content_hash"], row["observation_hash"]),
                            parsed_key,
                        )
                    )
                except (FetchError, ParseError) as e:
                    metrics["failed"] += 1
                    metrics["parser_failures"] += int(isinstance(e, ParseError))
                    metrics["http_429"] += int(getattr(e, "status", None) == 429)
                    metrics["http_403"] += int(getattr(e, "status", None) == 403)
                    state = repo.failure(
                        state_source, row, run, e, config["max_attempts"]
                    )
                    status = "PARTIAL"
                    if state == "BLOCKED":
                        status = "BLOCKED"
                        failure = str(e)
                        break
                    if getattr(e, "retry_after", 0):
                        break
            manifest_key = None
            if rows:
                manifest_key, manifest = landing.batch(
                    source_key,
                    rows,
                    observations,
                    run,
                    day,
                    config["processing_version"],
                    SourceAdapter.version,
                    data_kind=data_kind,
                )
                manifest, path = landing.restore(
                    manifest_key, os.getenv("CRAWLER_WORK_DIR", "/app/local/crawler")
                )
                validate_source_file(path)
                bronze = ingest(
                    replace(
                        Settings.from_env(),
                        source=source.host,
                        source_file=path,
                        processing_version=config["processing_version"],
                        processing_date=manifest["processing_date"],
                    ),
                    store,
                )
                metrics["bronze_ingestion_id"] = bronze["ingestion_id"]
                metrics["batch_ids"] = [manifest["batch_id"]]
            # Advance hashes only after immutable batch and Bronze commit. The
            # pending outbox is atomic with frontier success, so downstream
            # failure never loses articles or requires website refetching.
            with repo.connection.transaction():
                if manifest_key:
                    repo.batch(
                        manifest["batch_id"],
                        run,
                        state_source,
                        manifest["processing_date"],
                        manifest_key,
                    )
                for row, envelope, hashes, key in successes:
                    repo.success(
                        state_source,
                        row,
                        run,
                        envelope,
                        hashes,
                        key,
                        config["recheck_hours"],
                    )
        except Exception as e:  # noqa: BLE001 - persist batch failure and isolate sources
            status = "BLOCKED" if getattr(e, "status", None) in (401, 403) else "FAILED"
            failure = str(e)[:500]
            if getattr(e, "retry_after", 0) or getattr(e, "retryable", False):
                repo.cooldown(state_source, max(getattr(e, "retry_after", 0), 60))
        metrics["request_count"] = getattr(client, "request_count", 0)
        metrics["retry_count"] = getattr(client, "retry_count", 0)
        metrics["duration_seconds"] = round(time.monotonic() - started, 3)
        repo.finish(state_source, run, status, metrics, failure)
    return {
        "source": source_key,
        "crawl_run_id": run,
        "status": status,
        "error": failure,
        **metrics,
    }


def publish(source_key, *, repository=None, store=None, fixture=False):
    """Replay durable pending batches through the original hardened runner."""
    if repository is None:
        with Repository() as repo:
            return publish(source_key, repository=repo, store=store, fixture=fixture)
    from src.news_pipeline.pipeline_runner import execute
    from src.pipeline_operations.config import OperationsSettings
    from src.pipeline_operations.repository import OperationsRepository

    repo = repository
    source = SOURCES[source_key]
    state_source = (
        (os.getenv("CRAWLER_FIXTURE_STATE_NAMESPACE", "fixture") + ":" + source_key)
        if fixture
        else source_key
    )
    store = store or create_object_store(Settings.from_env())
    landing = Landing(store)
    results = []
    with repo.lock(state_source):
        for batch in repo.pending(state_source):
            manifest, path = landing.restore(
                batch["manifest_key"],
                os.getenv("CRAWLER_WORK_DIR", "/app/local/crawler"),
            )
            run_id = "pipeline-" + batch["batch_id"]
            # Source-scoped serving follows the existing source-scoped Gold and
            # reconciliation contracts. Sharing one DuckDB file would overwrite
            # another source's view; sharing one index would miscount reconciliation.
            overrides = {
                "NEWS_SOURCE": source.host,
                "NEWS_SOURCE_FILE": path,
                "NEWS_PROCESSING_VERSION": manifest["processing_version"],
                "NEWS_QDRANT_COLLECTION": (
                    "fixture_crawler_" if fixture else "crawler_"
                )
                + source_key
                + "_v1",
                "NEWS_DUCKDB_PATH": str(
                    Path(os.getenv("CRAWLER_WORK_DIR", "/app/local/crawler"))
                    / (("fixture-" if fixture else "") + source_key + ".duckdb")
                ),
                "NEWS_INDEX_LIMIT": "0",
                **{
                    name: ""
                    for name in (
                        "NEWS_SOURCE_INGESTION_ID",
                        "NEWS_SILVER_ARTICLES_URI",
                        "NEWS_SILVER_MENTIONS_URI",
                        "NEWS_GOLD_RAG_PREFIX",
                        "NEWS_GOLD_ANALYTICS_PREFIX",
                    )
                },
            }
            prior = {k: os.environ.get(k) for k in overrides}
            os.environ.update(overrides)
            try:
                with OperationsRepository(OperationsSettings.from_env()) as operations:
                    try:
                        old = operations.get_run(run_id)
                    except KeyError:
                        old = None
                result = (
                    execute(
                        trigger_type="MANUAL",
                        partitions=[(batch["processing_date"], path)],
                        force_reprocess=False,
                        run_id=run_id,
                        resume=old is not None,
                    )
                    if not old or old["status"] != "SUCCESS"
                    else {"status": "SUCCESS", "run_id": run_id, "reused": True}
                )
                repo.query(
                    "UPDATE crawler_operations.batches SET status='SUCCESS',published_at=now(),pipeline_run_id=%s,error_message=NULL WHERE batch_id=%s",
                    (run_id, batch["batch_id"]),
                )
                results.append(result)
            except Exception as e:
                repo.query(
                    "UPDATE crawler_operations.batches SET status='FAILED',pipeline_run_id=%s,error_message=%s WHERE batch_id=%s",
                    (run_id, str(e)[:500], batch["batch_id"]),
                )
                raise
            finally:
                for key, value in prior.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
    return {"source": source_key, "published_batches": len(results), "results": results}
