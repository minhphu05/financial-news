"""Bounded crawler metrics from read-only PostgreSQL operational snapshots."""

from collections import defaultdict

from prometheus_client.core import GaugeMetricFamily

SOURCES = {"cafef", "vnexpress", "tuoitre", "thanhnien", "baomoi"}
KINDS = (
    "discovered",
    "fetched",
    "changed",
    "unchanged",
    "failed",
    "parser_failures",
    "http_429",
    "http_403",
    "retry_count",
    "request_count",
    "new_articles",
    "updated_articles",
    "parse_successes",
    "http_failures",
    "blocked_or_rate_limited",
    "discovery_empty",
)


def labels(source):
    parts = source.split(":")
    key = parts[-1]
    return [
        key if key in SOURCES else "other",
        "fixture" if source.startswith("fixture") and len(parts) > 1 else "live",
    ]


def collect(snapshot):
    runs = GaugeMetricFamily(
        "financial_news_crawler_runs_total",
        "Persisted crawl runs",
        labels=["source", "data_kind", "status"],
    )
    counts = GaugeMetricFamily(
        "financial_news_crawler_articles_total",
        "Persisted article/request outcomes",
        labels=["source", "data_kind", "outcome"],
    )
    duration = GaugeMetricFamily(
        "financial_news_crawler_last_duration_seconds",
        "Last source-batch duration",
        labels=["source", "data_kind"],
    )
    freshness = GaugeMetricFamily(
        "financial_news_crawler_last_success_timestamp_seconds",
        "Last successful source batch",
        labels=["source", "data_kind"],
    )
    frontier = GaugeMetricFamily(
        "financial_news_crawler_frontier_urls",
        "Persistent frontier cardinality",
        labels=["source", "data_kind", "status"],
    )
    pending = GaugeMetricFamily(
        "financial_news_crawler_pending_batches",
        "Unpublished durable batches",
        labels=["source", "data_kind"],
    )
    totals = defaultdict(float)
    run_totals = defaultdict(int)
    frontier_totals = defaultdict(int)
    pending_totals = defaultdict(int)
    successful = {}
    for row in snapshot.get("crawl_runs", []):
        ls = labels(row["source"])
        run_totals[tuple(ls) + (row["status"],)] += row["count"]
        for kind in KINDS:
            totals[tuple(ls) + (kind,)] += float(row.get(kind) or 0)
    for ls, value in run_totals.items():
        runs.add_metric(list(ls), value)
    for ls, value in totals.items():
        counts.add_metric(list(ls), value)
    latest = {}
    for row in snapshot.get("crawl_latest", []):
        ls = labels(row["source"])
        key = tuple(ls)
        if key not in latest or row["started_at"] > latest[key]["started_at"]:
            latest[key] = row
    for ls, row in latest.items():
        measured = row["metrics"].get("duration_seconds")
        if measured is not None:
            duration.add_metric(list(ls), float(measured))
    for row in snapshot.get("crawl_sources", []):
        if row["last_success_at"]:
            ls = tuple(labels(row["source"]))
            successful[ls] = max(
                successful.get(ls, 0), row["last_success_at"].timestamp()
            )
    for ls, value in successful.items():
        freshness.add_metric(list(ls), value)
    for row in snapshot.get("crawl_frontier", []):
        frontier_totals[tuple(labels(row["source"])) + (row["status"],)] += row["count"]
    for ls, value in frontier_totals.items():
        frontier.add_metric(list(ls), value)
    for row in snapshot.get("crawl_pending", []):
        pending_totals[tuple(labels(row["source"]))] += row["count"]
    for ls, value in pending_totals.items():
        pending.add_metric(list(ls), value)
    yield from (runs, counts, duration, freshness, frontier, pending)
    # Additive Phase09 families; old snapshots remain valid without these keys.
    for name, help_text, rows_key, value_key in (
        (
            "last_completed_timestamp_seconds",
            "Last completed crawl, including a policy skip",
            "crawl_heartbeat",
            "finished_at",
        ),
        (
            "last_landing_timestamp_seconds",
            "Last observed durable HTML Landing write, not publication time",
            "crawl_landing",
            "landed_at",
        ),
        (
            "oldest_pending_timestamp_seconds",
            "Oldest unpublished batch creation time",
            "crawl_pending",
            "oldest_created_at",
        ),
        (
            "http_duration_seconds_total",
            "Persisted HTTP chain elapsed seconds; initial wait excluded, redirect pacing included",
            "crawl_http_duration",
            "duration_seconds",
        ),
    ):
        family = GaugeMetricFamily(
            "financial_news_crawler_" + name, help_text, labels=["source", "data_kind"]
        )
        values = {}
        for row in snapshot.get(rows_key, []):
            value = row.get(value_key)
            if value is not None:
                value = (
                    value.timestamp() if hasattr(value, "timestamp") else float(value)
                )
                key = tuple(labels(row["source"]))
                if name.endswith("_total"):
                    values[key] = values.get(key, 0) + value
                elif name.startswith("oldest_"):
                    values[key] = min(values.get(key, value), value)
                else:
                    values[key] = max(values.get(key, 0), value)
        for ls, value in values.items():
            family.add_metric(list(ls), value)
        yield family
    live = GaugeMetricFamily(
        "financial_news_crawler_live_enabled",
        "Runtime source live policy; does not change Airflow cron",
        labels=["source"],
    )
    heartbeat_limit = GaugeMetricFamily(
        "financial_news_crawler_heartbeat_max_age_seconds",
        "Configurable local operational threshold, not an SLA",
        labels=["source"],
    )
    for row in snapshot.get("crawl_policy", []):
        source = labels(row["source"])[0]
        live.add_metric([source], int(row["live_enabled"]))
        heartbeat_limit.add_metric([source], float(row["heartbeat_max_age_seconds"]))
    yield live
    yield heartbeat_limit
    layer = GaugeMetricFamily(
        "financial_news_crawler_layer_last_success_timestamp_seconds",
        "Successful downstream stage linked to a crawler outbox batch",
        labels=["source", "data_kind", "layer"],
    )
    latency = GaugeMetricFamily(
        "financial_news_crawler_landing_to_layer_seconds",
        "Latest measured first-Landing-to-stage interval",
        labels=["source", "data_kind", "layer"],
    )
    allowed = {
        "silver_merge": "silver",
        "gold_rag_merge": "gold_rag",
        "gold_analytics_refresh": "gold_analytics",
        "qdrant_upsert": "qdrant",
        "duckdb_publish": "duckdb",
    }
    merged = {}
    for row in snapshot.get("crawl_layers", []):
        if row["stage"] not in allowed:
            continue
        ls = tuple(labels(row["source"])) + (allowed[row["stage"]],)
        if ls not in merged or row["finished_at"] > merged[ls]["finished_at"]:
            merged[ls] = row
    for ls, row in merged.items():
        layer.add_metric(list(ls), row["finished_at"].timestamp())
        if row.get("latency_seconds") is not None and row["latency_seconds"] >= 0:
            latency.add_metric(list(ls), float(row["latency_seconds"]))
    yield layer
    yield latency
    state = GaugeMetricFamily(
        "financial_news_crawler_outbox_batches",
        "Outbox rows by bounded lifecycle state",
        labels=["source", "data_kind", "status"],
    )
    exhausted = GaugeMetricFamily(
        "financial_news_crawler_outbox_exhausted_batches",
        "Unpublished batches needing operator review after retry budget",
        labels=["source", "data_kind"],
    )
    states = defaultdict(int)
    for row in snapshot.get("crawl_batches", []):
        states[tuple(labels(row["source"])) + (row["status"],)] += row["count"]
    for ls, value in states.items():
        state.add_metric(list(ls), value)
    totals = defaultdict(int)
    for row in snapshot.get("crawl_exhausted", []):
        totals[tuple(labels(row["source"]))] += row["count"]
    for ls, value in totals.items():
        exhausted.add_metric(list(ls), value)
    yield state
    yield exhausted
    blocked = GaugeMetricFamily(
        "financial_news_crawler_source_blocked",
        "Persisted source block latch, cleared only after policy review",
        labels=["source", "data_kind"],
    )
    cooldown = GaugeMetricFamily(
        "financial_news_crawler_cooldown_until_timestamp_seconds",
        "Server-directed source cooldown deadline; zero means no cooldown",
        labels=["source", "data_kind"],
    )
    latched = defaultdict(int)
    deadlines = defaultdict(float)
    for row in snapshot.get("crawl_latches", []):
        ls = tuple(labels(row["source"]))
        latched[ls] = max(latched[ls], int(row.get("blocked_at") is not None))
        if row.get("cooldown_until"):
            deadlines[ls] = max(deadlines[ls], row["cooldown_until"].timestamp())
    for ls, value in latched.items():
        blocked.add_metric(list(ls), value)
        cooldown.add_metric(list(ls), deadlines[ls])
    yield blocked
    yield cooldown


def read(cursor):
    cursor.execute("SELECT to_regclass('crawler_operations.crawl_runs') AS table_name")
    if not cursor.fetchone()["table_name"]:
        return {}
    fields = ",".join(
        f"sum(COALESCE((metrics->>'{kind}')::numeric,0)) AS {kind}" for kind in KINDS
    )
    cursor.execute(
        "SELECT source,status,count(*) AS count,"
        + fields
        + " FROM crawler_operations.crawl_runs GROUP BY source,status"
    )
    runs = [dict(r) for r in cursor.fetchall()]
    cursor.execute(
        "SELECT DISTINCT ON(source) source,started_at,metrics FROM crawler_operations.crawl_runs ORDER BY source,started_at DESC"
    )
    latest = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT source,last_success_at FROM crawler_operations.source_state")
    sources = [dict(r) for r in cursor.fetchall()]
    cursor.execute(
        "SELECT source,status,count(*) AS count FROM crawler_operations.frontier GROUP BY source,status"
    )
    frontier = [dict(r) for r in cursor.fetchall()]
    cursor.execute(
        "SELECT s.source,count(b.batch_id) AS count,min(b.created_at) AS oldest_created_at "
        "FROM crawler_operations.source_state s LEFT JOIN crawler_operations.batches b "
        "ON b.source=s.source AND b.status<>'SUCCESS' GROUP BY s.source"
    )
    pending = [dict(r) for r in cursor.fetchall()]
    result = {
        "crawl_runs": runs,
        "crawl_latest": latest,
        "crawl_sources": sources,
        "crawl_frontier": frontier,
        "crawl_pending": pending,
    }
    for key, query in (
        (
            "crawl_heartbeat",
            "SELECT source,max(finished_at) AS finished_at FROM crawler_operations.crawl_runs GROUP BY source",
        ),
        (
            "crawl_landing",
            "SELECT source,max((metrics->>'last_landing_at')::timestamptz) AS landed_at FROM crawler_operations.crawl_runs GROUP BY source",
        ),
        (
            "crawl_http_duration",
            "SELECT source,sum((metrics->>'http_duration_seconds')::numeric) AS duration_seconds FROM crawler_operations.crawl_runs GROUP BY source",
        ),
        (
            "crawl_policy",
            "SELECT substring(source_id from 9) AS source,enabled AND COALESCE(config#>>'{crawler,live_enabled}','false')='true' AS live_enabled, COALESCE((config#>>'{crawler,heartbeat_max_age_seconds}')::numeric,7200) AS heartbeat_max_age_seconds FROM control_metadata.news_sources WHERE source_id LIKE 'crawler:%'",
        ),
        (
            "crawl_layers",
            "SELECT DISTINCT ON(b.source,regexp_replace(s.stage_name,'^.*:','')) b.source,regexp_replace(s.stage_name,'^.*:','') AS stage,s.finished_at,EXTRACT(EPOCH FROM s.finished_at-(c.metrics->>'first_landing_at')::timestamptz) AS latency_seconds FROM crawler_operations.batches b JOIN crawler_operations.crawl_runs c USING(crawl_run_id) JOIN pipeline_operations.pipeline_stage_runs s ON s.run_id=COALESCE(b.pipeline_run_id,'pipeline-'||b.batch_id) WHERE s.status='SUCCESS' AND s.finished_at IS NOT NULL ORDER BY b.source,regexp_replace(s.stage_name,'^.*:',''),s.finished_at DESC",
        ),
    ):
        cursor.execute(query)
        result[key] = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='crawler_operations' AND table_name='batches' AND column_name='attempts'"
    )
    if cursor.fetchone():
        cursor.execute(
            "SELECT source,blocked_at,cooldown_until FROM crawler_operations.source_state"
        )
        result["crawl_latches"] = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            "SELECT source,status,count(*) AS count FROM crawler_operations.batches GROUP BY source,status"
        )
        result["crawl_batches"] = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            "SELECT b.source,count(*) AS count FROM crawler_operations.batches b LEFT JOIN control_metadata.news_sources n ON n.source_id='crawler:'||regexp_replace(b.source,'^.*:','') WHERE b.status<>'SUCCESS' AND b.attempts>=COALESCE((n.config#>>'{crawler,publish_max_attempts}')::integer,5) GROUP BY b.source"
        )
        result["crawl_exhausted"] = [dict(row) for row in cursor.fetchall()]
    return result
