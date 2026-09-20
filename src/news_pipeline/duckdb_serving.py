"""Build a local DuckDB file from committed Gold analytics Parquet exports."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

from src.news_pipeline.gold_config import ANALYTICS_DATASETS, GoldSettings
from src.news_pipeline.storage import ObjectStore, S3ObjectStore


def publish(settings: GoldSettings, store: ObjectStore, record_metrics: bool = True) -> dict:
    import duckdb

    started = time.monotonic()
    manifest = json.loads(store.get_bytes(f"{settings.analytics_prefix}/manifest.json"))
    if manifest["source_ingestion_id"] != settings.source_ingestion_id:
        raise ValueError("Gold analytics manifest ingestion ID mismatch")
    target = Path(settings.duckdb_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_db = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    row_counts = {}
    try:
        with tempfile.TemporaryDirectory(prefix="gold-analytics-") as stage:
            connection = duckdb.connect(str(temporary_db))
            try:
                for dataset in ANALYTICS_DATASETS:
                    info = manifest["datasets"][dataset]
                    directory = Path(stage) / dataset
                    directory.mkdir()
                    for index, key in enumerate(info["object_keys"]):
                        (directory / f"part-{index}.parquet").write_bytes(store.get_bytes(key))
                    connection.execute(f"CREATE TABLE {dataset} AS SELECT * FROM read_parquet('{directory}/*.parquet')")
                    count = connection.execute(f"SELECT COUNT(*) FROM {dataset}").fetchone()[0]
                    if count != info["row_count"]:
                        raise AssertionError(f"DuckDB row count mismatch for {dataset}: {count} != {info['row_count']}")
                    row_counts[dataset] = count
                    connection.execute(f"CREATE VIEW vw_{dataset} AS SELECT * FROM {dataset}")
                article_count = connection.execute("SELECT SUM(article_count) FROM news_by_source").fetchone()[0]
                if article_count != manifest["input_article_count"]:
                    raise AssertionError("DuckDB article total differs from Gold manifest")
            finally:
                connection.close()
        os.replace(temporary_db, target)
    finally:
        if temporary_db.exists():
            temporary_db.unlink()
    metrics = {
        "input_article_count": manifest["input_article_count"],
        "duckdb_rows": row_counts,
        "processing_duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duckdb_path": str(target),
    }
    if record_metrics:
        store.put_bytes(f"{settings.analytics_prefix}/duckdb_metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2).encode())
    return metrics


def query(settings: GoldSettings, sql: str) -> list[tuple]:
    import duckdb

    if not sql.lstrip().lower().startswith("select "):
        raise ValueError("analytics-query accepts SELECT statements only")
    with duckdb.connect(settings.duckdb_path, read_only=True) as connection:
        return connection.execute(sql).fetchall()


def main() -> None:
    settings = GoldSettings.from_env()
    if len(sys.argv) == 1 or sys.argv[1] == "build":
        print(json.dumps(publish(settings, S3ObjectStore(settings.news)), ensure_ascii=False, indent=2))
    elif sys.argv[1] == "query":
        sql = sys.argv[2] if len(sys.argv) > 2 else os.getenv("NEWS_ANALYTICS_SQL") or "SELECT * FROM vw_news_by_source ORDER BY article_count DESC"
        for row in query(settings, sql):
            print(row)
    else:
        raise SystemExit("Usage: duckdb_serving.py build|query [SELECT ...]")


if __name__ == "__main__":
    main()
