"""Concise health/status command for the local hardened data platform."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.request

from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.qdrant_index import QdrantChunkIndex
from src.news_pipeline.storage import S3ObjectStore
from src.pipeline_operations.config import OperationsSettings


def _http_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def check(name, operation) -> dict:
    try:
        details = operation()
        return {"name": name, "status": "PASS", "details": details}
    except Exception as exc:
        return {"name": name, "status": "FAIL", "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    settings = GoldSettings.from_env().for_current_tables()
    store = S3ObjectStore(settings.news)
    operations = OperationsSettings.from_env()

    def minio():
        store.ensure_bucket()
        return {"bucket": settings.news.bucket}

    def delta():
        prefix = settings.silver_articles_uri.split(f"/{settings.news.bucket}/", 1)[-1]
        logs = [key for key in store.list_keys(f"{prefix}/_delta_log/") if key.endswith(".json")]
        if not logs:
            raise RuntimeError("current Silver Delta log is missing")
        return {"silver_articles_uri": settings.silver_articles_uri, "delta_commits": len(logs)}

    def qdrant():
        index = QdrantChunkIndex(
            settings.qdrant_url, settings.qdrant_collection, settings.embedding_dimension
        )
        try:
            index.ensure_collection()
            return {"collection": settings.qdrant_collection, "points": index.count()}
        finally:
            index.close()

    def duckdb_check():
        import duckdb
        if not Path(settings.duckdb_path).is_file():
            raise FileNotFoundError(settings.duckdb_path)
        with duckdb.connect(settings.duckdb_path, read_only=True) as connection:
            articles = connection.execute(
                "SELECT COALESCE(SUM(article_count), 0) FROM news_by_source"
            ).fetchone()[0]
        return {"path": settings.duckdb_path, "articles": int(articles)}

    def postgres():
        import psycopg
        with psycopg.connect(**operations.connection_kwargs) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('pipeline_operations.pipeline_runs'), "
                "to_regclass('control_metadata.news_sources')"
            )
            run_table, metadata_table = cursor.fetchone()
        if run_table is None or metadata_table is None:
            raise RuntimeError("required PostgreSQL schemas are not migrated")
        return {"operations_table": str(run_table), "control_table": str(metadata_table)}

    def kafka():
        from confluent_kafka.admin import AdminClient
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        metadata = AdminClient({"bootstrap.servers": bootstrap}).list_topics(timeout=10)
        return {"bootstrap_servers": bootstrap, "topic_count": len(metadata.topics)}

    def debezium():
        base = os.getenv("DEBEZIUM_CONNECT_URL", "http://debezium:8083").rstrip("/")
        connector = os.getenv("DEBEZIUM_CONNECTOR_NAME", "metadata-control-plane")
        payload = _http_json(f"{base}/connectors/{connector}/status")
        connector_status = payload.get("connector", {}).get("state")
        task_states = [task.get("state") for task in payload.get("tasks", [])]
        if connector_status != "RUNNING" or not task_states or any(state != "RUNNING" for state in task_states):
            raise RuntimeError(f"connector={connector_status}, tasks={task_states}")
        return {"connector": connector, "connector_status": connector_status, "tasks": task_states}

    def airflow():
        url = os.getenv("AIRFLOW_API_BASE_URL", "http://airflow-webserver:8080").rstrip("/")
        payload = _http_json(f"{url}/health")
        scheduler = payload.get("scheduler", {}).get("status")
        metadatabase = payload.get("metadatabase", {}).get("status")
        if scheduler != "healthy" or metadatabase != "healthy":
            raise RuntimeError(f"scheduler={scheduler}, metadatabase={metadatabase}")
        return {"scheduler": scheduler, "metadatabase": metadatabase}

    checks = [
        check("minio", minio),
        check("silver_delta", delta),
        check("qdrant", qdrant),
        check("duckdb", duckdb_check),
        check("postgresql", postgres),
        check("kafka", kafka),
        check("debezium", debezium),
        check("airflow", airflow),
    ]
    result = {"status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL", "checks": checks}
    if args.compact:
        print(" ".join(f"{item['name']}={item['status']}" for item in checks))
    else:
        print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
