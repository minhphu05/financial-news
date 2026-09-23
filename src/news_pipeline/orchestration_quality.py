"""Lightweight, reusable quality gates for local orchestration.

This module validates published artifacts and serving projections. It deliberately
contains no Bronze/Silver/Gold transformation logic and can be run without Airflow.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from src.news_pipeline.bronze import file_sha256
from src.news_pipeline.config import Settings
from src.news_pipeline.duckdb_serving import query as query_duckdb
from src.news_pipeline.gold_config import ANALYTICS_DATASETS, GoldSettings
from src.news_pipeline.qdrant_index import QdrantChunkIndex
from src.news_pipeline.storage import ObjectStore, S3ObjectStore


def _load_json(store: ObjectStore, key: str) -> dict:
    if not store.exists(key):
        raise FileNotFoundError(f"Required object is missing: {key}")
    value = json.loads(store.get_bytes(key))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object at {key}")
    return value


def _require_delta_log(store: ObjectStore, prefix: str) -> None:
    if not store.list_keys(f"{prefix.rstrip('/')}/_delta_log/"):
        raise FileNotFoundError(f"Delta log is missing below {prefix}")


def _source_identity(settings: Settings) -> tuple[str, Path]:
    path = Path(settings.source_file)
    if not path.is_file():
        raise FileNotFoundError(f"Source snapshot is missing: {path}")
    return file_sha256(path), path


def validate_source(settings: Settings) -> dict:
    ingestion_id, path = _source_identity(settings)
    with path.open("r", encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list) or not records:
        raise ValueError("Source snapshot must be a nonempty JSON array")
    result = {
        "gate": "source",
        "source": settings.source,
        "source_file": str(path),
        "source_ingestion_id": ingestion_id,
        "record_count": len(records),
        "byte_size": path.stat().st_size,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def validate_bronze(settings: Settings, store: ObjectStore) -> dict:
    ingestion_id, path = _source_identity(settings)
    prefix = f"bronze/{settings.source}/{ingestion_id}"
    manifest = _load_json(store, f"{prefix}/manifest.json")
    raw_key = manifest.get("raw_key")
    if manifest.get("source_file_sha256") != ingestion_id or not raw_key or not store.exists(raw_key):
        raise ValueError("Bronze manifest does not identify the expected immutable source object")
    raw = store.get_bytes(raw_key)
    if hashlib.sha256(raw).hexdigest() != ingestion_id:
        raise ValueError("Bronze object checksum differs from the source ingestion ID")
    if manifest.get("record_count", 0) <= 0 or manifest.get("byte_size") != path.stat().st_size:
        raise ValueError("Bronze manifest has impossible counts or byte size")
    result = {
        "gate": "bronze",
        "source_ingestion_id": ingestion_id,
        "record_count": manifest["record_count"],
        "raw_key": raw_key,
        "manifest_key": f"{prefix}/manifest.json",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def validate_silver(settings: Settings, store: ObjectStore) -> dict:
    ingestion_id, _ = _source_identity(settings)
    prefix = f"silver/{settings.source}/{ingestion_id}/{settings.processing_version}"
    metrics_key = f"{prefix}/metrics.json"
    metrics = _load_json(store, metrics_key)
    required = {"input_count", "output_count", "invalid_count", "duplicate_count", "article_mentions_count"}
    missing = required - metrics.keys()
    if missing:
        raise ValueError(f"Silver metrics are missing fields: {sorted(missing)}")
    if metrics["input_count"] <= 0 or metrics["output_count"] <= 0:
        raise ValueError("Silver cannot publish an empty input or output")
    if metrics["input_count"] != metrics["output_count"] + metrics["invalid_count"] + metrics["duplicate_count"]:
        raise ValueError("Silver metrics do not reconcile input, output, rejects, and duplicates")
    if metrics["article_mentions_count"] < metrics["output_count"]:
        raise ValueError("Silver association count is unexpectedly below article count")
    for table in ("articles", "article_mentions", "rejects"):
        _require_delta_log(store, f"{prefix}/{table}")
    result = {
        "gate": "silver",
        "source_ingestion_id": ingestion_id,
        "metrics_key": metrics_key,
        "input_count": metrics["input_count"],
        "output_count": metrics["output_count"],
        "invalid_count": metrics["invalid_count"],
        "duplicate_count": metrics["duplicate_count"],
        "article_mentions_count": metrics["article_mentions_count"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def validate_rag(settings: GoldSettings, store: ObjectStore, require_index: bool = True) -> dict:
    metrics_key = f"{settings.rag_prefix}/metrics.json"
    metrics = _load_json(store, metrics_key)
    article_count = metrics.get("silver_articles_read", 0)
    document_count = metrics.get("gold_documents_produced", 0)
    chunk_count = metrics.get("gold_chunks_produced", 0)
    if article_count <= 0 or document_count != article_count or chunk_count < document_count:
        raise ValueError("Gold RAG metrics have impossible article/document/chunk counts")
    if metrics.get("empty_rejected_chunk_count") != 0:
        raise ValueError("Gold RAG contains articles that unexpectedly produced no chunks")
    for table in ("documents", "chunks"):
        _require_delta_log(store, f"{settings.rag_prefix}/{table}")

    result = {
        "gate": "rag",
        "metrics_key": metrics_key,
        "article_count": article_count,
        "document_count": document_count,
        "chunk_count": chunk_count,
    }
    if require_index:
        qdrant_key = f"{settings.rag_prefix}/qdrant_metrics.json"
        index_metrics = _load_json(store, qdrant_key)
        input_count = index_metrics.get("input_chunk_count", 0)
        indexed_count = index_metrics.get("indexed_chunk_count", 0)
        if input_count <= 0 or indexed_count != input_count:
            raise ValueError("Qdrant indexing did not index every selected input chunk")
        if index_metrics.get("embedded_chunk_count") != input_count or index_metrics.get("failed_chunk_count") != 0:
            raise ValueError("Qdrant embedding/index metrics report failures or incomplete work")
        index = QdrantChunkIndex(settings.qdrant_url, settings.qdrant_collection, settings.embedding_dimension)
        try:
            actual_count = index.count()
        finally:
            index.close()
        if actual_count != indexed_count:
            raise ValueError(f"Qdrant contains {actual_count} points but metrics report {indexed_count}")
        result.update({
            "qdrant_metrics_key": qdrant_key,
            "indexed_count": indexed_count,
            "collection": settings.qdrant_collection,
        })
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def validate_analytics(settings: GoldSettings, store: ObjectStore) -> dict:
    manifest_key = f"{settings.analytics_prefix}/manifest.json"
    metrics_key = f"{settings.analytics_prefix}/metrics.json"
    duckdb_metrics_key = f"{settings.analytics_prefix}/duckdb_metrics.json"
    manifest = _load_json(store, manifest_key)
    metrics = _load_json(store, metrics_key)
    duckdb_metrics = _load_json(store, duckdb_metrics_key)
    input_count = manifest.get("input_article_count", 0)
    if input_count <= 0 or metrics.get("input_article_count") != input_count:
        raise ValueError("Gold Analytics input counts are missing or inconsistent")
    row_counts = metrics.get("output_aggregation_rows", {})
    for dataset in ANALYTICS_DATASETS:
        info = manifest.get("datasets", {}).get(dataset, {})
        if info.get("row_count", 0) <= 0 or row_counts.get(dataset) != info.get("row_count"):
            raise ValueError(f"Gold Analytics row counts are invalid for {dataset}")
        keys = info.get("object_keys") or []
        if not keys or any(not store.exists(key) for key in keys):
            raise FileNotFoundError(f"Gold Analytics Parquet objects are missing for {dataset}")
        if duckdb_metrics.get("duckdb_rows", {}).get(dataset) != info["row_count"]:
            raise ValueError(f"DuckDB metrics do not match Gold Analytics for {dataset}")
    if duckdb_metrics.get("input_article_count") != input_count:
        raise ValueError("DuckDB input article count differs from Gold Analytics")
    database = Path(settings.duckdb_path)
    if not database.is_file():
        raise FileNotFoundError(f"DuckDB serving file is missing: {database}")
    source_total = query_duckdb(settings, "SELECT SUM(article_count) FROM vw_news_by_source")[0][0]
    status_total = query_duckdb(settings, "SELECT SUM(article_count) FROM vw_news_publication_status")[0][0]
    if source_total != input_count or status_total != input_count:
        raise ValueError("DuckDB serving totals do not reconcile to Gold Analytics")
    result = {
        "gate": "analytics",
        "manifest_key": manifest_key,
        "metrics_key": metrics_key,
        "duckdb_metrics_key": duckdb_metrics_key,
        "input_article_count": input_count,
        "output_rows": row_counts,
        "duckdb_path": str(database),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def publish_status(stage: str, settings: GoldSettings, store: ObjectStore) -> dict:
    if stage == "silver":
        quality = validate_silver(settings.news, store)
    elif stage == "gold":
        quality = {
            "rag": validate_rag(settings, store, require_index=True),
            "analytics": validate_analytics(settings, store),
        }
    else:
        raise ValueError(f"Unsupported orchestration stage: {stage}")
    dag_id = os.getenv("NEWS_AIRFLOW_DAG_ID", "standalone")
    run_id = os.getenv("NEWS_AIRFLOW_DAG_RUN_ID", "standalone")
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("_") or "standalone"
    status = {
        "orchestrator": "airflow" if dag_id != "standalone" else "standalone",
        "stage": stage,
        "dag_id": dag_id,
        "dag_run_id": run_id,
        "logical_date": os.getenv("NEWS_AIRFLOW_LOGICAL_DATE"),
        "upstream_run_id": os.getenv("NEWS_AIRFLOW_UPSTREAM_RUN_ID") or None,
        "source": settings.news.source,
        "source_ingestion_id": settings.source_ingestion_id,
        "quality": quality,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    key = f"orchestration/airflow/{stage}/{safe_run_id}.json"
    store.put_bytes(key, json.dumps(status, ensure_ascii=False, indent=2).encode())
    status["status_key"] = key
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return status


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    settings = GoldSettings.from_env()
    store = S3ObjectStore(settings.news)
    commands = {
        "source": lambda: validate_source(settings.news),
        "bronze": lambda: validate_bronze(settings.news, store),
        "silver": lambda: validate_silver(settings.news, store),
        "rag": lambda: validate_rag(settings, store, require_index=True),
        "analytics": lambda: validate_analytics(settings, store),
        "publish-silver": lambda: publish_status("silver", settings, store),
        "publish-gold": lambda: publish_status("gold", settings, store),
    }
    if command not in commands:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} {'|'.join(commands)}")
    commands[command]()


if __name__ == "__main__":
    main()
