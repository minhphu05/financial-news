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
from src.news_pipeline.structured_log import event

from .adapters import SourceAdapter
from .http_client import FetchError, HttpClient
from .landing import Landing, encoded
from .sources import SOURCES, ParseError
from .state import Repository, SourceBusy
from .policy import batch_limit, failure_category, gate, retry_delay


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
    allow_live=False,
    scheduled=False,
    skip_busy=False,
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
                allow_live=allow_live,
                scheduled=scheduled,
                skip_busy=skip_busy,
            )
    repo = repository
    config = repo.config(source_key, allow_disabled=True)
    limit = batch_limit(limit, config)
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
    context = {
        "airflow_run_type": os.getenv("CRAWLER_AIRFLOW_RUN_TYPE", "standalone"),
        "airflow_run_id": os.getenv("CRAWLER_AIRFLOW_RUN_ID"),
        "airflow_dag_id": os.getenv("CRAWLER_AIRFLOW_DAG_ID"),
    }
    if scheduled:
        trigger = "SCHEDULED"

    def skip(reason):
        repo.record_skip(state_source, run, trigger, reason, context)
        event(
            "crawler_run_skipped",
            source=source_key,
            run_id=run,
            outcome="SKIPPED_BY_POLICY",
            reason=reason,
        )
        return {
            "source": source_key,
            "crawl_run_id": run,
            "status": "SKIPPED",
            "skip_reason": reason,
        }

    reason = gate(config, fixture=data_kind == "FIXTURE", allow_live=allow_live)
    if reason:
        return skip(reason)
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
        "new_articles": 0,
        "updated_articles": 0,
        "parse_successes": 0,
        "http_failures": 0,
        "blocked_or_rate_limited": 0,
        **context,
    }
    store = store or create_object_store(Settings.from_env())
    landing = Landing(store)
    client = client or HttpClient(
        source,
        user_agent=config["user_agent"],
        interval=config["request_interval_seconds"],
        timeout=config["request_timeout_seconds"],
        retries=config["http_retries"],
        max_bytes=config["max_response_bytes"],
    )
    with repo.lock(state_source):
        try:
            repo.start(state_source, run, trigger)
        except SourceBusy as exc:
            if skip_busy:
                return skip(str(exc))
            raise
        event(
            "crawler_run_started",
            source=source_key,
            run_id=run,
            trigger_type=trigger,
            limit=limit,
        )
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
            metrics["discovery_empty"] = int(not candidates)
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
                    landed_at = datetime.now(timezone.utc).isoformat()
                    metrics.setdefault("first_landing_at", landed_at)
                    metrics["last_landing_at"] = landed_at
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
                    metrics["parse_successes"] += 1
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
                        metrics[
                            "new_articles"
                            if row["observation_hash"] is None
                            else "updated_articles"
                        ] += 1
                    elif not changed:
                        metrics["unchanged"] += 1
                    event(
                        "crawler_article_observed",
                        source=source_key,
                        run_id=run,
                        outcome="NEW_OR_UPDATED"
                        if changed and inside
                        else "UNCHANGED"
                        if not changed
                        else "SKIPPED_BY_POLICY",
                    )
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
                    category = failure_category(e)
                    event(
                        "crawler_article_failed",
                        source=source_key,
                        run_id=run,
                        outcome=category,
                        http_status=getattr(e, "status", None),
                    )
                    metrics["failed"] += 1
                    metrics["http_failures"] += int(isinstance(e, FetchError))
                    metrics["blocked_or_rate_limited"] += int(
                        category == "BLOCKED_OR_RATE_LIMITED"
                    )
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
            category = failure_category(e)
            metrics["http_failures"] += int(isinstance(e, FetchError))
            metrics["blocked_or_rate_limited"] += int(
                category == "BLOCKED_OR_RATE_LIMITED"
            )
            metrics["http_429"] += int(getattr(e, "status", None) == 429)
            metrics["http_403"] += int(getattr(e, "status", None) == 403)
            event(
                "crawler_run_failed",
                source=source_key,
                run_id=run,
                outcome=category,
                error_type=type(e).__name__,
                http_status=getattr(e, "status", None),
            )
            status = "BLOCKED" if getattr(e, "status", None) in (401, 403) else "FAILED"
            if status == "BLOCKED":
                repo.block(state_source, getattr(e, "reason", "blocked_source"))
            failure = str(e)[:500]
            if getattr(e, "retry_after", 0) or getattr(e, "retryable", False):
                repo.cooldown(state_source, max(getattr(e, "retry_after", 0), 60))
        metrics["request_count"] = getattr(client, "request_count", 0)
        metrics["retry_count"] = getattr(client, "retry_count", 0)
        metrics["http_duration_seconds"] = getattr(
            client, "request_duration_seconds", None
        )
        metrics["duration_seconds"] = round(time.monotonic() - started, 3)
        repo.finish(state_source, run, status, metrics, failure)
        event(
            "crawler_run_finished",
            source=source_key,
            run_id=run,
            status=status,
            metrics=metrics,
        )
    return {
        "source": source_key,
        "crawl_run_id": run,
        "status": status,
        "error": failure,
        **metrics,
    }


def publish(
    source_key,
    *,
    repository=None,
    store=None,
    fixture=False,
    scheduled=False,
    max_batches=None,
    respect_retry=False,
):
    """Replay durable pending batches through the original hardened runner."""
    if repository is None:
        with Repository() as repo:
            return publish(
                source_key,
                repository=repo,
                store=store,
                fixture=fixture,
                scheduled=scheduled,
                max_batches=max_batches,
                respect_retry=respect_retry,
            )
    from src.news_pipeline.pipeline_runner import execute
    from src.pipeline_operations.config import OperationsSettings
    from src.pipeline_operations.repository import OperationsRepository

    repo = repository
    source = SOURCES[source_key]
    config = repo.config(source_key, allow_disabled=True)
    if max_batches is not None and (
        type(max_batches) is not int or not 1 <= max_batches <= 20
    ):
        raise ValueError("publish_max_batches_must_be_between_1_and_20")
    limit = min(
        max_batches or config["publish_max_batches"], config["publish_max_batches"]
    )
    state_source = (
        (os.getenv("CRAWLER_FIXTURE_STATE_NAMESPACE", "fixture") + ":" + source_key)
        if fixture
        else source_key
    )
    store = store or create_object_store(Settings.from_env())
    landing = Landing(store)
    results = []
    with repo.lock(state_source):
        repo.recover_publishing(state_source)
        for batch in repo.due_batches(
            state_source,
            limit,
            config["publish_max_attempts"],
            force=not (scheduled or respect_retry),
        ):
            run_id = "pipeline-" + batch["batch_id"]
            attempt = repo.claim_batch(batch["batch_id"])
            try:
                manifest, path = landing.restore(
                    batch["manifest_key"],
                    os.getenv("CRAWLER_WORK_DIR", "/app/local/crawler"),
                )
            except Exception:
                repo.query(
                    "UPDATE crawler_operations.batches SET status='FAILED',error_message='Durable input restore failed',next_eligible_at=now()+%s::interval WHERE batch_id=%s",
                    (f"{retry_delay(attempt, config)} seconds", batch["batch_id"]),
                )
                event(
                    "crawler_publish_failed",
                    source=source_key,
                    run_id=run_id,
                    outcome="DOWNSTREAM_FAILURE",
                    attempt=attempt,
                    stage="restore",
                )
                raise
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
                event(
                    "crawler_batch_published",
                    source=source_key,
                    run_id=run_id,
                    attempt=attempt,
                )
            except Exception as e:
                repo.query(
                    "UPDATE crawler_operations.batches SET status='FAILED',pipeline_run_id=%s,error_message=%s,next_eligible_at=now()+%s::interval WHERE batch_id=%s",
                    (
                        run_id,
                        str(e)[:500],
                        f"{retry_delay(attempt, config)} seconds",
                        batch["batch_id"],
                    ),
                )
                event(
                    "crawler_publish_failed",
                    source=source_key,
                    run_id=run_id,
                    outcome="DOWNSTREAM_FAILURE",
                    attempt=attempt,
                    error_type=type(e).__name__,
                )
                raise
            finally:
                for key, value in prior.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
    remaining = repo.query(
        "SELECT count(*) AS count FROM crawler_operations.batches WHERE source=%s AND status<>'SUCCESS'",
        (state_source,),
    )[0]["count"]
    return {
        "source": source_key,
        "status": "PENDING" if remaining else "SUCCESS",
        "published_batches": len(results),
        "pending_batches_remaining": remaining,
        "results": results,
    }
