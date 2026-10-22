"""Closed-window operational evidence, derived from existing crawler/run ledgers."""

from datetime import datetime, timezone
import math

SOURCE_KEYS = ("cafef", "vnexpress", "tuoitre", "thanhnien", "baomoi")
LAYERS = {
    "silver_merge": "silver",
    "gold_rag_merge": "gold_rag",
    "gold_analytics_refresh": "gold_analytics",
    "qdrant_upsert": "qdrant",
    "duckdb_publish": "duckdb",
}


def timestamp(value):
    if value is None:
        return None
    result = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if result.tzinfo is None:
        raise ValueError("timestamps_require_explicit_timezone")
    return result.astimezone(timezone.utc)


def percentile(values, quantile):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    return round(
        values[lower] + (values[upper] - values[lower]) * (position - lower), 3
    )


def latency_summary(values):
    return {
        "sample_count": len(values),
        "p50_seconds": percentile(values, 0.5),
        "p95_seconds": percentile(values, 0.95) if len(values) >= 20 else None,
        "p95_gap": None if len(values) >= 20 else "N/A: fewer than 20 measured samples",
    }


def aggregate(start, end, runs, batches, stages, *, observed_at=None):
    """Pure aggregation, testable without a database or an embedding provider."""
    start, end = timestamp(start), timestamp(end)
    observed = timestamp(observed_at or datetime.now(timezone.utc))
    if not start < end <= observed:
        raise ValueError("report_requires_a_closed_positive_time_window")
    sources = {}
    for key in SOURCE_KEYS:
        sources[key] = {
            "scheduled_runs": 0,
            "started_runs": 0,
            "completed_runs": 0,
            "failed_runs": 0,
            "partial_runs": 0,
            "skipped_runs": 0,
            "running_at_window_end": 0,
            "discovered_urls": 0,
            "fetched": 0,
            "new_articles": 0,
            "updated_articles": 0,
            "unchanged_articles": 0,
            "http_failures": 0,
            "blocked_or_rate_limited": 0,
            "parser_failures": 0,
            "empty_discoveries": 0,
            "pending_batches_end": 0,
            "oldest_pending_age_seconds": None,
            "latest_successful_crawl": None,
            "latest_landing": None,
            **{"latest_" + name: None for name in LAYERS.values()},
            "reconciliation": {"PASS": 0, "FAIL": 0},
            "data_gaps": [],
        }
    scheduled = {key: set() for key in SOURCE_KEYS}
    latencies = {key: {"silver": [], "gold_rag": []} for key in SOURCE_KEYS}

    def key_for(source):
        key = source.split(":")[-1]
        return key if key in sources else None

    def latest(row, field, value):
        value = timestamp(value)
        if (
            value is not None
            and value < end
            and (row[field] is None or value > row[field])
        ):
            row[field] = value

    for run in runs:
        key = key_for(run["source"])
        if key is None or timestamp(run["started_at"]) >= end:
            continue
        row = sources[key]
        finished = timestamp(run.get("finished_at"))
        measured = finished is not None and finished < end
        metrics = run.get("metrics") or {}
        if measured:
            latest(row, "latest_landing", metrics.get("last_landing_at"))
            if run["status"] == "SUCCESS":
                latest(row, "latest_successful_crawl", finished)
        if timestamp(run["started_at"]) < start:
            continue
        row["started_runs"] += 1
        if (
            run.get("trigger_type") == "SCHEDULED"
            or metrics.get("airflow_run_type") == "scheduled"
        ):
            scheduled[key].add(metrics.get("airflow_run_id") or run["crawl_run_id"])
        if not measured:
            row["running_at_window_end"] += 1
            continue
        row["completed_runs"] += 1
        row["failed_runs"] += run["status"] in ("FAILED", "BLOCKED")
        row["partial_runs"] += run["status"] == "PARTIAL"
        row["skipped_runs"] += run["status"] == "SKIPPED"
        for metric, field in (
            ("discovered", "discovered_urls"),
            ("fetched", "fetched"),
            ("new_articles", "new_articles"),
            ("updated_articles", "updated_articles"),
            ("unchanged", "unchanged_articles"),
            ("http_failures", "http_failures"),
            ("blocked_or_rate_limited", "blocked_or_rate_limited"),
            ("parser_failures", "parser_failures"),
            ("discovery_empty", "empty_discoveries"),
        ):
            row[field] += int(metrics.get(metric) or 0)
        if "new_articles" not in metrics and metrics.get("changed"):
            row["data_gaps"].append(
                "Historical changed count cannot be split into new/updated"
            )
        if metrics.get("fetched") and "last_landing_at" not in metrics:
            row["data_gaps"].append(
                "Historical crawl lacks a durable Landing completion timestamp"
            )
    batch_map = {}
    for batch in batches:
        key = key_for(batch["source"])
        if key is None or timestamp(batch["created_at"]) >= end:
            continue
        batch_map[batch["batch_id"]] = batch
        published = timestamp(batch.get("published_at"))
        if published is None or published >= end:
            row = sources[key]
            row["pending_batches_end"] += 1
            age = (end - timestamp(batch["created_at"])).total_seconds()
            row["oldest_pending_age_seconds"] = max(
                row["oldest_pending_age_seconds"] or 0, age
            )
    # Successful completion once per batch/stage, even when an attempt was retried.
    successful = {}
    for stage in stages:
        if stage.get("finished_at") and timestamp(stage["finished_at"]) < end:
            key = (stage["batch_id"], stage["stage_name"].split(":")[-1])
            if stage["status"] == "SUCCESS":
                prior = successful.get(key)
                if prior is None or timestamp(stage["finished_at"]) > timestamp(
                    prior["finished_at"]
                ):
                    successful[key] = stage
            elif (
                key[1] == "reconciliation" and timestamp(stage["finished_at"]) >= start
            ):
                batch = batch_map.get(stage["batch_id"])
                if batch and key_for(batch["source"]):
                    sources[key_for(batch["source"])]["reconciliation"]["FAIL"] += 1
    for (batch_id, stage_name), stage in successful.items():
        batch = batch_map.get(batch_id)
        if not batch:
            continue
        key = key_for(batch["source"])
        finished = timestamp(stage["finished_at"])
        if stage_name in LAYERS:
            layer = LAYERS[stage_name]
            latest(sources[key], "latest_" + layer, finished)
            landing = timestamp(batch.get("first_landing_at"))
            if layer in latencies[key] and start <= finished < end:
                if landing is not None and landing <= finished:
                    latencies[key][layer].append((finished - landing).total_seconds())
                else:
                    sources[key]["data_gaps"].append(
                        "N/A latency: batch has no valid first durable Landing timestamp"
                    )
        elif stage_name == "reconciliation" and finished >= start:
            sources[key]["reconciliation"]["PASS"] += 1
    for key, row in sources.items():
        row["scheduled_runs"] = len(scheduled[key])
        row["landing_to_silver"] = latency_summary(latencies[key]["silver"])
        row["landing_to_gold_rag"] = latency_summary(latencies[key]["gold_rag"])
        row["data_gaps"] = sorted(set(row["data_gaps"]))
    return {
        "interval_start": start,
        "interval_end": end,
        "timezone": "UTC",
        "display_timezone": "Asia/Ho_Chi_Minh",
        "observed_at": observed,
        "sources": sources,
        "semantics": {
            "runs": "Cohort started in [start,end); only completions before end contribute outcome counts",
            "scheduled_runs": "Distinct source scheduled-run IDs, not raw task retry attempts",
            "latency": "First durable HTML Landing write to successful downstream stage completion; samples completed in window",
            "pending": "Reconstructed at end from created_at/published_at; retry status history is not reconstructed",
            "new_updated": "Crawler observation classifications, not Silver insert/update totals",
        },
        "alert_summary": None,
        "data_gaps": [
            "Alert and resource history require the optional Prometheus/host evidence sampler"
        ],
    }


def read_report(repo, start, end, *, fixture=False):
    end = timestamp(end)
    # Limit scope explicitly; neither article bodies nor URLs/errors enter the report.
    clause = "source LIKE 'fixture%%'" if fixture else "source = ANY(%s)"
    args = () if fixture else (list(SOURCE_KEYS),)
    runs = repo.query(
        "SELECT crawl_run_id,source,trigger_type,status,started_at,finished_at,metrics "
        f"FROM crawler_operations.crawl_runs WHERE {clause} AND started_at < %s",
        (*args, end),
    )
    batches = repo.query(
        "SELECT b.batch_id,b.source,b.created_at,b.published_at,"
        "c.metrics->>'first_landing_at' AS first_landing_at "
        "FROM crawler_operations.batches b JOIN crawler_operations.crawl_runs c USING(crawl_run_id) "
        f"WHERE b.{clause} AND b.created_at < %s",
        (*args, end),
    )
    stages = repo.query(
        "SELECT b.batch_id,s.stage_name,s.status,s.finished_at FROM crawler_operations.batches b "
        "JOIN pipeline_operations.pipeline_stage_runs s "
        "ON s.run_id=COALESCE(b.pipeline_run_id,'pipeline-'||b.batch_id) "
        f"WHERE b.{clause} AND s.finished_at < %s",
        (*args, end),
    )
    return {
        **aggregate(start, end, runs, batches, stages),
        "data_kind": "fixture" if fixture else "live",
    }
