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
        duration.add_metric(list(ls), float(row["metrics"].get("duration_seconds", 0)))
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
        "SELECT source,count(*) AS count FROM crawler_operations.batches WHERE status<>'SUCCESS' GROUP BY source"
    )
    pending = [dict(r) for r in cursor.fetchall()]
    return {
        "crawl_runs": runs,
        "crawl_latest": latest,
        "crawl_sources": sources,
        "crawl_frontier": frontier,
        "crawl_pending": pending,
    }
