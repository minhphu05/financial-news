"""Prometheus exporter backed by Phase 05 operational metadata.

The exporter is deliberately read-only.  Batch jobs keep writing their normal
run and stage records to PostgreSQL; this long-running process converts that
bounded operational state into low-cardinality Prometheus series.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily


KNOWN_STAGES = {
    "schema_validation",
    "bronze_ingest",
    "silver_merge",
    "gold_rag_merge",
    "gold_analytics_refresh",
    "duckdb_publish",
    "qdrant_upsert",
    "reconciliation",
}
LAYER_STAGE = {
    "bronze": "bronze_ingest",
    "silver": "silver_merge",
    "gold_rag": "gold_rag_merge",
    "gold_analytics": "gold_analytics_refresh",
    "duckdb": "duckdb_publish",
    "qdrant": "qdrant_upsert",
}
RECORD_FIELDS = {
    "record_count": "input",
    "input_count": "input",
    "output_count": "output",
    "invalid_count": "invalid",
    "duplicate_count": "duplicate",
    "current_article_count": "silver_articles",
    "silver_articles_read": "input_articles",
    "gold_documents_produced": "documents",
    "gold_chunks_produced": "chunks",
    "input_chunk_count": "input_chunks",
    "indexed_chunk_count": "indexed_chunks",
    "failed_chunk_count": "failed_chunks",
    "collection_point_count": "qdrant_points",
    "input_article_count": "input_articles",
}


def _csv_env(name: str, default: str) -> set[str]:
    return {item.strip() for item in os.getenv(name, default).split(",") if item.strip()}


ALLOWED_PIPELINES = _csv_env(
    "MONITORING_PIPELINE_ALLOWLIST",
    "financial_news_incremental,phase05_integration,local_release_e2e",
)
ALLOWED_SOURCES = _csv_env(
    "MONITORING_SOURCE_ALLOWLIST",
    "cafef.vn,local-release.test,phase05-it.local,phase05-recovery.local,phase07-monitoring.local",
)


def canonical_stage(value: str) -> str:
    stage = re.sub(r"^\d{4}-\d{2}-\d{2}:", "", value or "")
    return stage if stage in KNOWN_STAGES else "other"


def bounded_pipeline(value: str) -> str:
    pipeline = (value or "").split(":", 1)[0]
    return pipeline if pipeline in ALLOWED_PIPELINES else "other"


def bounded_source(value: str) -> str:
    return value if value in ALLOWED_SOURCES else "other"


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def stage_record_counts(stage: str, metrics: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for field, kind in RECORD_FIELDS.items():
        value = numeric(metrics.get(field))
        if value is not None:
            result[kind] = value
    nested = metrics.get("output_aggregation_rows") or metrics.get("duckdb_rows")
    if isinstance(nested, dict):
        values = [numeric(value) for value in nested.values()]
        result["aggregation_rows"] = sum(value for value in values if value is not None)
    if stage == "reconciliation" and isinstance(metrics.get("counts"), dict):
        for field in (
            "silver_articles", "gold_documents", "gold_chunks", "qdrant_points",
            "duckdb_articles", "missing_gold_documents", "orphan_gold_documents",
            "qdrant_missing_points", "qdrant_stale_points",
        ):
            value = numeric(metrics["counts"].get(field))
            if value is not None:
                result[field] = value
    return result


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


class SnapshotReader:
    def __init__(self) -> None:
        self.connection_kwargs = {
            "host": os.getenv("METADATA_POSTGRES_HOST", "postgresql"),
            "port": int(os.getenv("METADATA_POSTGRES_INTERNAL_PORT", "5432")),
            "dbname": os.getenv("METADATA_POSTGRES_DB", "financial_metadata"),
            "user": os.getenv("MONITORING_POSTGRES_USER", "monitoring_exporter"),
            "password": os.getenv("MONITORING_POSTGRES_PASSWORD", "monitoring_password"),
            "connect_timeout": 5,
            "options": "-c default_transaction_read_only=on -c statement_timeout=5000",
        }

    def read(self) -> dict[str, Any]:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(**self.connection_kwargs, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pipeline_name, source, trigger_type, status,
                           started_at, finished_at, created_at
                    FROM pipeline_operations.pipeline_runs
                    """
                )
                runs = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT r.pipeline_name, r.source, s.stage_name, s.status,
                           s.attempt, s.metrics, s.started_at, s.finished_at
                    FROM pipeline_operations.pipeline_stage_runs s
                    JOIN pipeline_operations.pipeline_runs r USING (run_id)
                    """
                )
                stages = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT active, confirmed_flush_lsn IS NOT NULL AS has_confirmed_lsn,
                           COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn), 0)
                               AS lag_bytes
                    FROM pg_replication_slots
                    WHERE slot_name = %s
                    """,
                    (os.getenv("METADATA_CDC_SLOT", "metadata_cdc_slot"),),
                )
                slot = cursor.fetchone()
        return {"runs": runs, "stages": stages, "slot": None if slot is None else dict(slot)}


def _json_get(url: str, timeout: float = 4.0) -> Any:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def service_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {
        "airflow": {},
        "debezium_connector": 0.0,
        "debezium_task": 0.0,
        "kafka": 0.0,
        "topics": [],
    }
    try:
        health = _json_get(
            os.getenv("AIRFLOW_HEALTH_URL", "http://airflow-webserver:8080/health")
        )
        for component in ("metadatabase", "scheduler", "dag_processor", "triggerer"):
            state = (health.get(component) or {}).get("status")
            if state is not None:
                result["airflow"][component] = 1.0 if state == "healthy" else 0.0
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        result["airflow"] = {"metadatabase": 0.0, "scheduler": 0.0}

    connect_url = os.getenv("DEBEZIUM_CONNECT_URL", "http://debezium:8083").rstrip("/")
    connector = os.getenv("DEBEZIUM_CONNECTOR_NAME", "metadata-control-plane")
    try:
        status = _json_get(f"{connect_url}/connectors/{connector}/status")
        result["debezium_connector"] = 1.0 if status.get("connector", {}).get("state") == "RUNNING" else 0.0
        tasks = status.get("tasks") or []
        result["debezium_task"] = 1.0 if tasks and all(item.get("state") == "RUNNING" for item in tasks) else 0.0
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        pass

    try:
        from confluent_kafka import Consumer, TopicPartition

        topics = tuple(
            f"{os.getenv('METADATA_CDC_TOPIC_PREFIX', 'platform')}.{table}"
            for table in (
                "control_metadata.news_sources",
                "control_metadata.pipeline_configs",
            )
        )
        consumer = Consumer({
            "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            "group.id": "phase07-metrics-exporter",
            "enable.auto.commit": False,
            "session.timeout.ms": 6000,
        })
        try:
            metadata = consumer.list_topics(timeout=4)
            result["kafka"] = 1.0
            for topic in topics:
                topic_metadata = metadata.topics.get(topic)
                if topic_metadata is None or topic_metadata.error is not None:
                    continue
                for partition in sorted(topic_metadata.partitions):
                    tp = TopicPartition(topic, partition)
                    low, high = consumer.get_watermark_offsets(tp, timeout=3)
                    latest_timestamp = 0.0
                    if high > low:
                        consumer.assign([TopicPartition(topic, partition, high - 1)])
                        message = consumer.poll(2)
                        if message is not None and message.error() is None:
                            _, timestamp_ms = message.timestamp()
                            latest_timestamp = max(0.0, timestamp_ms / 1000.0)
                    result["topics"].append({
                        "topic": topic,
                        "partition": str(partition),
                        "latest_offset": float(high),
                        "latest_timestamp": latest_timestamp,
                    })
        finally:
            consumer.close()
    except Exception:
        # Scrapes must stay available while Kafka is being failure-tested.
        pass
    return result


class FinancialNewsCollector:
    def __init__(self, reader: SnapshotReader | None = None) -> None:
        self.reader = reader or SnapshotReader()

    def collect(self):
        collection_ok = 1.0
        try:
            snapshot = self.reader.read()
        except Exception:
            collection_ok = 0.0
            snapshot = {"runs": [], "stages": [], "slot": None}

        success = GaugeMetricFamily(
            "financial_news_exporter_collection_success",
            "Whether the latest read-only PostgreSQL collection succeeded",
        )
        success.add_metric([], collection_ok)
        yield success

        run_totals: dict[tuple[str, str, str, str], int] = defaultdict(int)
        latest_runs: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in snapshot["runs"]:
            pipeline = bounded_pipeline(row["pipeline_name"])
            source = bounded_source(row["source"])
            status = row["status"]
            run_totals[(pipeline, source, row["trigger_type"], status)] += 1
            key = (pipeline, source, status)
            at = row["finished_at"] or row["started_at"] or row["created_at"]
            if key not in latest_runs or at > (
                latest_runs[key]["finished_at"]
                or latest_runs[key]["started_at"]
                or latest_runs[key]["created_at"]
            ):
                latest_runs[key] = row

        runs = GaugeMetricFamily(
            "financial_news_pipeline_runs_total", "Recorded pipeline runs",
            labels=["pipeline", "source", "trigger_type", "status"],
        )
        for labels, value in sorted(run_totals.items()):
            runs.add_metric(list(labels), value)
        yield runs

        run_timestamp = GaugeMetricFamily(
            "financial_news_pipeline_last_run_timestamp_seconds",
            "Completion or start timestamp of the latest run in each status",
            labels=["pipeline", "source", "status"],
        )
        run_duration = GaugeMetricFamily(
            "financial_news_pipeline_last_run_duration_seconds",
            "Processing duration of the latest completed run in each status",
            labels=["pipeline", "source", "status"],
        )
        for (pipeline, source, status), row in sorted(latest_runs.items()):
            at = row["finished_at"] or row["started_at"] or row["created_at"]
            run_timestamp.add_metric([pipeline, source, status], _timestamp(at))
            if row["started_at"] and row["finished_at"]:
                run_duration.add_metric(
                    [pipeline, source, status],
                    max(0.0, (row["finished_at"] - row["started_at"]).total_seconds()),
                )
        yield run_timestamp
        yield run_duration

        stage_totals: dict[tuple[str, str, str, str], int] = defaultdict(int)
        latest_stages: dict[tuple[str, str, str], dict[str, Any]] = {}
        latest_successful_stages: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in snapshot["stages"]:
            pipeline = bounded_pipeline(row["pipeline_name"])
            source = bounded_source(row["source"])
            stage = canonical_stage(row["stage_name"])
            stage_totals[(pipeline, source, stage, row["status"])] += 1
            key = (pipeline, source, stage)
            at = row["finished_at"] or row["started_at"]
            old = latest_stages.get(key)
            old_at = None if old is None else old["finished_at"] or old["started_at"]
            if old is None or (at is not None and (old_at is None or at > old_at)):
                latest_stages[key] = row
            if row["status"] == "SUCCESS":
                old_success = latest_successful_stages.get(key)
                old_success_at = (
                    None
                    if old_success is None
                    else old_success["finished_at"] or old_success["started_at"]
                )
                if old_success is None or (
                    at is not None
                    and (old_success_at is None or at > old_success_at)
                ):
                    latest_successful_stages[key] = row

        stage_runs = GaugeMetricFamily(
            "financial_news_pipeline_stage_runs_total", "Recorded stage attempts",
            labels=["pipeline", "source", "stage", "status"],
        )
        for labels, value in sorted(stage_totals.items()):
            stage_runs.add_metric(list(labels), value)
        yield stage_runs

        stage_duration = GaugeMetricFamily(
            "financial_news_pipeline_stage_duration_seconds",
            "Duration recorded by the latest stage attempt",
            labels=["pipeline", "source", "stage", "status"],
        )
        records = GaugeMetricFamily(
            "financial_news_pipeline_records",
            "Latest bounded input, output, quality, or serving record count",
            labels=["pipeline", "source", "stage", "kind"],
        )
        last_stage_success = GaugeMetricFamily(
            "financial_news_pipeline_stage_last_success_timestamp_seconds",
            "Latest successful completion timestamp for a pipeline stage",
            labels=["pipeline", "source", "stage"],
        )
        last_stage_attempt = GaugeMetricFamily(
            "financial_news_pipeline_stage_last_attempt_timestamp_seconds",
            "Completion or start timestamp of the latest stage attempt",
            labels=["pipeline", "source", "stage", "status"],
        )
        for (pipeline, source, stage), row in sorted(latest_stages.items()):
            metrics = row.get("metrics") or {}
            duration = numeric(metrics.get("stage_duration_seconds"))
            if duration is None and row["started_at"] and row["finished_at"]:
                duration = (row["finished_at"] - row["started_at"]).total_seconds()
            if duration is not None:
                stage_duration.add_metric([pipeline, source, stage, row["status"]], duration)
            for kind, value in sorted(stage_record_counts(stage, metrics).items()):
                records.add_metric([pipeline, source, stage, kind], value)
            at = row["finished_at"] or row["started_at"]
            if at:
                last_stage_attempt.add_metric(
                    [pipeline, source, stage, row["status"]], _timestamp(at)
                )
        for (pipeline, source, stage), row in sorted(latest_successful_stages.items()):
            if row["finished_at"]:
                last_stage_success.add_metric(
                    [pipeline, source, stage], _timestamp(row["finished_at"])
                )
        yield stage_duration
        yield records
        yield last_stage_success
        yield last_stage_attempt

        now = datetime.now(timezone.utc).timestamp()
        layer_updated = GaugeMetricFamily(
            "financial_news_data_last_success_timestamp_seconds",
            "Operational timestamp of the latest successful durable or serving layer update",
            labels=["pipeline", "source", "layer"],
        )
        freshness = GaugeMetricFamily(
            "financial_news_data_freshness_seconds",
            "Seconds since the latest successful stage for a durable or serving layer",
            labels=["pipeline", "source", "layer"],
        )
        for (pipeline, source, stage), row in sorted(latest_successful_stages.items()):
            layer = next((name for name, mapped in LAYER_STAGE.items() if mapped == stage), None)
            if layer and row["finished_at"]:
                completed = _timestamp(row["finished_at"])
                layer_updated.add_metric([pipeline, source, layer], completed)
                freshness.add_metric([pipeline, source, layer], max(0.0, now - completed))
        yield layer_updated
        yield freshness

        invalid = GaugeMetricFamily(
            "financial_news_data_quality_invalid_records",
            "Invalid records in the latest Silver attempt",
            labels=["pipeline", "source"],
        )
        duplicates = GaugeMetricFamily(
            "financial_news_data_quality_duplicate_records",
            "Duplicate records in the latest Silver attempt",
            labels=["pipeline", "source"],
        )
        duplicate_rate = GaugeMetricFamily(
            "financial_news_data_quality_duplicate_ratio",
            "Duplicate records divided by latest Silver input records",
            labels=["pipeline", "source"],
        )
        gate_pass = GaugeMetricFamily(
            "financial_news_data_quality_gate_pass",
            "Whether the latest schema validation and Silver attempts succeeded",
            labels=["pipeline", "source"],
        )
        reconciliation_pass = GaugeMetricFamily(
            "financial_news_reconciliation_pass",
            "Whether the latest reconciliation attempt passed",
            labels=["pipeline", "source"],
        )
        pipeline_sources = {(key[0], key[1]) for key in latest_stages}
        for pipeline, source in sorted(pipeline_sources):
            silver = latest_stages.get((pipeline, source, "silver_merge"))
            schema = latest_stages.get((pipeline, source, "schema_validation"))
            reconcile = latest_stages.get((pipeline, source, "reconciliation"))
            if schema is None and silver is None:
                continue
            silver_metrics = {} if silver is None else silver.get("metrics") or {}
            invalid_value = numeric(silver_metrics.get("invalid_count")) or 0.0
            duplicate_value = numeric(silver_metrics.get("duplicate_count")) or 0.0
            input_value = numeric(silver_metrics.get("input_count")) or 0.0
            invalid.add_metric([pipeline, source], invalid_value)
            duplicates.add_metric([pipeline, source], duplicate_value)
            duplicate_rate.add_metric(
                [pipeline, source], duplicate_value / input_value if input_value else 0.0
            )
            gate_pass.add_metric(
                [pipeline, source],
                1.0 if schema and silver and schema["status"] == silver["status"] == "SUCCESS" else 0.0,
            )
            reconcile_metrics = {} if reconcile is None else reconcile.get("metrics") or {}
            if reconcile is not None:
                reconciliation_pass.add_metric(
                    [pipeline, source],
                    1.0 if reconcile["status"] == "SUCCESS" and reconcile_metrics.get("status") == "PASS" else 0.0,
                )
        yield invalid
        yield duplicates
        yield duplicate_rate
        yield gate_pass
        yield reconciliation_pass

        duckdb = GaugeMetricFamily(
            "financial_news_duckdb_operational_up",
            "Whether the latest DuckDB publish stage succeeded",
            labels=["pipeline", "source"],
        )
        for (pipeline, source, stage), row in sorted(latest_stages.items()):
            if stage == "duckdb_publish":
                duckdb.add_metric([pipeline, source], 1.0 if row["status"] == "SUCCESS" else 0.0)
        yield duckdb

        slot_active = GaugeMetricFamily(
            "financial_news_cdc_replication_slot_active",
            "Whether the configured PostgreSQL logical replication slot is active",
        )
        slot_lag = GaugeMetricFamily(
            "financial_news_cdc_replication_slot_lag_bytes",
            "WAL bytes between current LSN and the slot confirmed flush LSN",
        )
        slot = snapshot.get("slot")
        slot_active.add_metric([], 1.0 if slot and slot["active"] else 0.0)
        slot_lag.add_metric([], float(slot["lag_bytes"]) if slot else 0.0)
        yield slot_active
        yield slot_lag

        services = service_snapshot()
        airflow = GaugeMetricFamily(
            "financial_news_airflow_component_up", "Airflow health API component state",
            labels=["component"],
        )
        for component, value in sorted(services["airflow"].items()):
            airflow.add_metric([component], value)
        yield airflow
        connector = GaugeMetricFamily(
            "financial_news_debezium_connector_up", "Debezium connector RUNNING state"
        )
        connector.add_metric([], services["debezium_connector"])
        yield connector
        task = GaugeMetricFamily(
            "financial_news_debezium_task_up", "Debezium connector task RUNNING state"
        )
        task.add_metric([], services["debezium_task"])
        yield task
        kafka = GaugeMetricFamily(
            "financial_news_kafka_broker_up", "Kafka metadata request succeeded"
        )
        kafka.add_metric([], services["kafka"])
        yield kafka
        topic_offset = GaugeMetricFamily(
            "financial_news_cdc_topic_latest_offset", "Current CDC topic high watermark",
            labels=["topic", "partition"],
        )
        topic_timestamp = GaugeMetricFamily(
            "financial_news_cdc_latest_event_timestamp_seconds",
            "Kafka timestamp of the latest event in a metadata CDC topic",
            labels=["topic"],
        )
        latest_by_topic: dict[str, float] = defaultdict(float)
        for item in services["topics"]:
            topic_offset.add_metric(
                [item["topic"], item["partition"]], item["latest_offset"]
            )
            latest_by_topic[item["topic"]] = max(
                latest_by_topic[item["topic"]], item["latest_timestamp"]
            )
        for topic, value in sorted(latest_by_topic.items()):
            topic_timestamp.add_metric([topic], value)
        yield topic_offset
        yield topic_timestamp


def build_registry(reader: SnapshotReader | None = None) -> CollectorRegistry:
    registry = CollectorRegistry(auto_describe=True)
    registry.register(FinancialNewsCollector(reader))
    return registry


def serve() -> None:
    registry = build_registry()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path == "/health":
                body = b'{"status":"ok","mode":"read-only"}\n'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            elif self.path == "/metrics":
                body = generate_latest(registry)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            else:
                body = b"not found\n"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    port = int(os.getenv("MONITORING_PIPELINE_EXPORTER_PORT", "9108"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(json.dumps({"event": "metrics_exporter_started", "port": port, "mode": "read-only"}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    serve()
