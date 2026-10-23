"""Read operational evidence and explicitly administer local source policy."""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .policy import DEFAULTS
from .reporting import read_report, timestamp
from .sources import SOURCES
from .state import Repository


def storage_snapshot(repo, max_pages=5):
    """Periodic admin measurement, never an expensive per-request/per-scrape scan."""
    from src.news_pipeline.config import Settings
    from src.news_pipeline.storage import create_object_store

    if not 1 <= max_pages <= 100:
        raise ValueError("storage_page_budget_must_be_1_to_100")
    store = create_object_store(Settings.from_env())
    result = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "sources": {},
        "max_pages_per_prefix": max_pages,
    }
    for key, source in SOURCES.items():
        objects = byte_count = 0
        complete = True
        version = repo.config(key, allow_disabled=True)["processing_version"]
        prefixes = [
            f"landing/live/{key}/",
            f"bronze/{source.host}/",
            f"silver/current/{source.host}/{version}/",
            f"gold/current/rag/{source.host}/{version}/",
            f"gold/current/analytics/{source.host}/{version}/",
        ]
        for prefix in prefixes:
            token = None
            for _ in range(max_pages):
                response = store.client.list_objects_v2(
                    Bucket=store.bucket,
                    Prefix=prefix,
                    **({"ContinuationToken": token} if token else {}),
                )
                items = response.get("Contents", [])
                objects += len(items)
                byte_count += sum(item["Size"] for item in items)
                token = response.get("NextContinuationToken")
                if not token:
                    break
            if token:
                complete = False
        result["sources"][key] = {
            "objects_observed": objects,
            "bytes_observed": byte_count,
            "complete_for_selected_prefixes": complete,
            "prefixes": prefixes,
        }
    result["postgres_relations"] = repo.query(
        "SELECT relname,pg_total_relation_size(oid) AS bytes FROM pg_class WHERE relnamespace='crawler_operations'::regnamespace AND relkind='r' ORDER BY relname"
    )
    result["scope"] = (
        "Selected live Landing/Bronze/current prefixes; historical Bronze for the same host is included. Partial scans are lower bounds, not exact totals."
    )
    return result


def config_check(repo):
    schedule = os.getenv("AIRFLOW_NEWS_CRAWLER_SCHEDULE") or None
    scheduled_live = (
        os.getenv("AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE", "false").lower() == "true"
    )
    limit = int(os.getenv("AIRFLOW_NEWS_CRAWLER_LIMIT", "1"))
    if schedule and not scheduled_live:
        raise ValueError("schedule_requires_explicit_live_switch")
    if not 1 <= limit <= 20:
        raise ValueError("scheduled_limit_must_be_between_1_and_20")
    policies = {}
    for key in SOURCES:
        policy = repo.config(key, allow_disabled=True)
        policies[key] = {
            name: policy[name]
            for name in (
                "enabled",
                "max_articles",
                "max_attempts",
                "request_interval_seconds",
                "recheck_hours",
                "recent_days",
                *DEFAULTS,
            )
        }
        policies[key]["live_until"] = policy.get("live_until")
        policies[key]["policy_review_recorded"] = bool(
            policy.get("policy_reviewed_at") and policy.get("policy_review_reference")
        )
    return {
        "status": "PASS",
        "schedule_config": schedule,
        "scheduled_live_switch": scheduled_live,
        "scheduled_batch_limit": limit,
        "sources": policies,
        "note": "Environment for this process; confirm parsed/running scheduler config separately. PostgreSQL policy does not change DAG cron.",
    }


def set_live_policy(
    repo, source, enabled, *, reviewed=False, reference=None, live_until=None
):
    if enabled and (not reviewed or not reference or not reference.strip()):
        raise ValueError("enabling_live_requires_explicit_policy_review_and_reference")
    if live_until is not None:
        live_until = timestamp(live_until).isoformat()
        if timestamp(live_until) <= datetime.now(timezone.utc):
            raise ValueError("live_until_must_be_in_the_future")
    # Validate the old configuration before changing only operational JSON keys.
    repo.config(source, allow_disabled=True)
    patch = {"live_enabled": enabled}
    if enabled:
        patch.update(
            policy_reviewed_at=datetime.now(timezone.utc).isoformat(),
            policy_review_reference=reference,
            live_until=live_until,
        )
    repo.query(
        "UPDATE control_metadata.news_sources SET config=jsonb_set(config,'{crawler}',(config->'crawler') || %s::jsonb) WHERE source_id=%s",
        (json.dumps(patch), "crawler:" + source),
    )
    return {"source": source, "live_enabled": enabled, "status": "UPDATED"}


def clear_block(repo, source):
    # Operator review never shortens a server-directed Retry-After cooldown.
    repo.query(
        "UPDATE crawler_operations.source_state SET blocked_at=NULL,blocked_reason=NULL WHERE source=%s",
        (source,),
    )
    return {
        "source": source,
        "status": "BLOCK_CLEARED",
        "note": "Live policy and Retry-After cooldown are unchanged",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("config-check")
    storage = commands.add_parser("storage")
    storage.add_argument("--max-pages", type=int, default=5)
    report = commands.add_parser("daily-report")
    report.add_argument("--start", type=timestamp)
    report.add_argument("--end", type=timestamp)
    report.add_argument("--fixture", action="store_true")
    report.add_argument("--output", type=Path)
    policy = commands.add_parser("policy")
    policy.add_argument("--source", choices=SOURCES, required=True)
    policy.add_argument("--live-enabled", choices=("true", "false"), required=True)
    policy.add_argument("--policy-reviewed", action="store_true")
    policy.add_argument("--policy-reference")
    policy.add_argument("--live-until", type=timestamp)
    unblock = commands.add_parser("clear-block")
    unblock.add_argument("--source", choices=SOURCES, required=True)
    unblock.add_argument("--policy-reviewed", action="store_true", required=True)
    args = parser.parse_args()
    with Repository() as repo:
        if args.command == "config-check":
            result = config_check(repo)
        elif args.command == "storage":
            result = storage_snapshot(repo, args.max_pages)
        elif args.command == "policy":
            result = set_live_policy(
                repo,
                args.source,
                args.live_enabled == "true",
                reviewed=args.policy_reviewed,
                reference=args.policy_reference,
                live_until=args.live_until,
            )
        elif args.command == "clear-block":
            result = clear_block(repo, args.source)
        else:
            end = args.end or datetime.now(timezone.utc)
            start = args.start or end - timedelta(days=1)
            # Read-only transaction and query deadline; never copy URLs/bodies/errors.
            with repo.connection.transaction():
                repo.query("SET TRANSACTION READ ONLY")
                repo.query("SET LOCAL statement_timeout='10s'")
                result = read_report(repo, start, end, fixture=args.fixture)
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
