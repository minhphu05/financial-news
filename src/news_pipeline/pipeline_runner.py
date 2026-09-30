"""Incremental, backfill, reprocess, and recovery runner for the local news pipeline."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
import uuid
from typing import Any, Callable

from src.news_pipeline.bronze import ingest as ingest_bronze
from src.news_pipeline.config import Settings
from src.news_pipeline.duckdb_serving import publish as publish_duckdb
from src.news_pipeline.embedding import FastEmbedProvider
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.qdrant_index import QdrantChunkIndex, index_affected
from src.news_pipeline.source_schema import validate_source_file
from src.news_pipeline.storage import S3ObjectStore
from src.news_pipeline.structured_log import event
from src.pipeline_operations.config import OperationsSettings
from src.pipeline_operations.repository import OperationsRepository


PIPELINE_NAME = "financial_news_incremental"
Stage = Callable[[], dict[str, Any]]


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from exc


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("--to-date must not be earlier than --from-date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def make_run_id(trigger_type: str, start: date, end: date) -> str:
    return (
        f"news-{trigger_type.lower()}-{start.isoformat()}-{end.isoformat()}-"
        f"{uuid.uuid4().hex[:10]}"
    )


def validate_resume_identity(
    run: dict[str, Any],
    *,
    source: str,
    configuration_id: str,
    configuration: dict[str, Any],
) -> None:
    """Reject a resume under data-shaping settings different from the original run."""
    if run["source"] != source:
        raise ValueError(
            f"Cannot resume source {run['source']!r} with current source {source!r}"
        )
    parameters = dict(run.get("parameters") or {})
    if (
        parameters.get("configuration_id") != configuration_id
        or parameters.get("configuration") != configuration
    ):
        raise ValueError(
            "Cannot resume with changed processing, chunking, or embedding configuration"
        )


def _run_stage(
    repository: OperationsRepository,
    run_id: str,
    stage_name: str,
    operation: Stage,
    *,
    input_lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = repository.successful_stage(run_id, stage_name)
    if previous is not None:
        event("pipeline_stage_reused", run_id=run_id, stage=stage_name)
        return dict(previous.get("metrics") or {})
    stage_run_id = repository.start_stage(run_id, stage_name, input_lineage)
    started = time.monotonic()
    event("pipeline_stage_started", run_id=run_id, stage=stage_name)
    try:
        metrics = operation()
        metrics = {**metrics, "stage_duration_seconds": round(time.monotonic() - started, 3)}
        repository.finish_stage(
            stage_run_id,
            "SUCCESS",
            metrics=metrics,
            output_lineage={
                key: value for key, value in metrics.items()
                if key.endswith("_key") or key.endswith("_uri") or key.endswith("_prefix")
            },
        )
        event("pipeline_stage_succeeded", run_id=run_id, stage=stage_name, metrics=metrics)
        return metrics
    except Exception as exc:
        repository.finish_stage(
            stage_run_id,
            "FAILED",
            metrics={"stage_duration_seconds": round(time.monotonic() - started, 3)},
            error_message=str(exc),
        )
        event(
            "pipeline_stage_failed", level="ERROR", run_id=run_id,
            stage=stage_name, error=str(exc),
        )
        raise


def _read_affected(store: S3ObjectStore, key: str) -> list[str]:
    payload = json.loads(store.get_bytes(key))
    values = payload.get("article_ids")
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"Invalid affected article manifest: {key}")
    return values


def _qdrant_noop(settings: GoldSettings) -> dict:
    current = settings.for_current_tables()
    index = QdrantChunkIndex(
        current.qdrant_url, current.qdrant_collection, current.embedding_dimension
    )
    try:
        index.ensure_collection()
        return {
            "affected_article_count": 0,
            "input_chunk_count": 0,
            "embedded_chunk_count": 0,
            "indexed_chunk_count": 0,
            "failed_chunk_count": 0,
            "stale_points_deleted": 0,
            "collection_point_count": index.count(),
            "collection": current.qdrant_collection,
            "embedding_model": f"fastembed-0.8.0:{current.embedding_model}",
            "embedding_dimension": current.embedding_dimension,
            "mode": "incremental_noop",
        }
    finally:
        index.close()


def run_partition(
    *,
    repository: OperationsRepository,
    run_id: str,
    processing_date: date,
    source_file: str,
    base_settings: Settings,
    spark,
    pipeline_name: str,
) -> dict[str, Any]:
    from src.news_pipeline.analytics import build as build_analytics
    from src.news_pipeline.gold_rag import build_incremental as build_gold_incremental
    from src.news_pipeline.reconciliation import reconcile
    from src.news_pipeline.silver import build_incremental as build_silver_incremental

    partition = processing_date.isoformat()
    news = replace(
        base_settings,
        source_file=source_file,
        processing_date=partition,
        run_id=run_id,
    )
    store = S3ObjectStore(news)
    prefix = f"{partition}:"
    repository.acquire_partition(pipeline_name, news.source, processing_date, run_id)
    event(
        "pipeline_partition_started", run_id=run_id, source=news.source,
        processing_date=partition, source_file=source_file,
    )
    try:
        _run_stage(
            repository, run_id, prefix + "schema_validation",
            lambda: validate_source_file(source_file),
            input_lineage={"source_file": source_file},
        )
        bronze = _run_stage(
            repository, run_id, prefix + "bronze_ingest",
            lambda: ingest_bronze(news, store),
            input_lineage={"source_file": source_file},
        )
        silver = _run_stage(
            repository, run_id, prefix + "silver_merge",
            lambda: build_silver_incremental(news, store, spark),
            input_lineage={
                "bronze_manifest_key": (
                    f"bronze/{news.source}/{bronze['ingestion_id']}/manifest.json"
                )
            },
        )
        silver_affected_ids = _read_affected(store, silver["affected_article_ids_key"])
        gold_base = replace(
            GoldSettings.from_env(),
            news=news,
            source_ingestion_id=bronze["ingestion_id"],
        )
        current_gold = gold_base.for_current_tables()
        gold_log_prefix = (
            f"{current_gold.rag_prefix}/documents/_delta_log/"
        )
        if store.list_keys(gold_log_prefix):
            gold_affected_ids = silver_affected_ids
            gold_refresh_reason = "silver_change"
        else:
            gold_affected_ids = [
                row.article_id for row in
                spark.read.format("delta").load(current_gold.silver_articles_uri)
                    .select("article_id").orderBy("article_id").toLocalIterator()
            ]
            gold_refresh_reason = "gold_configuration_bootstrap"
        gold_affected_key = (
            f"gold/operations/{run_id}/processing_date={partition}/affected_articles.json"
        )
        store.put_bytes(
            gold_affected_key,
            json.dumps({"article_ids": gold_affected_ids}, indent=2, sort_keys=True).encode(),
        )

        def merge_gold() -> dict:
            metrics = build_gold_incremental(gold_base, spark, store, gold_affected_ids)
            return {
                **metrics,
                "affected_article_ids_key": gold_affected_key,
                "refresh_reason": gold_refresh_reason,
            }

        gold = _run_stage(
            repository, run_id, prefix + "gold_rag_merge",
            merge_gold,
            input_lineage={
                "current_silver_prefix": silver["current_silver_prefix"],
                "affected_article_ids_key": silver["affected_article_ids_key"],
            },
        )
        gold_affected_ids = _read_affected(store, gold["affected_article_ids_key"])
        analytics = _run_stage(
            repository, run_id, prefix + "gold_analytics_refresh",
            lambda: build_analytics(current_gold, spark, store),
            input_lineage={"current_silver_prefix": silver["current_silver_prefix"]},
        )
        duckdb = _run_stage(
            repository, run_id, prefix + "duckdb_publish",
            lambda: publish_duckdb(current_gold, store),
            input_lineage={"manifest_key": analytics["manifest_key"]},
        )
        expected_model_id = f"fastembed-0.8.0:{current_gold.embedding_model}"
        qdrant_metrics_key = f"{current_gold.rag_prefix}/qdrant_metrics.json"
        qdrant_affected_ids = gold_affected_ids
        if store.exists(qdrant_metrics_key):
            previous_qdrant = json.loads(store.get_bytes(qdrant_metrics_key))
            if previous_qdrant.get("embedding_model") != expected_model_id:
                qdrant_affected_ids = [
                    row.article_id for row in
                    spark.read.format("delta").load(current_gold.chunks_uri)
                        .select("article_id").distinct().orderBy("article_id").toLocalIterator()
                ]
        else:
            qdrant_affected_ids = [
                row.article_id for row in
                spark.read.format("delta").load(current_gold.chunks_uri)
                    .select("article_id").distinct().orderBy("article_id").toLocalIterator()
            ]
        qdrant = _run_stage(
            repository, run_id, prefix + "qdrant_upsert",
            lambda: (
                index_affected(
                    gold_base, FastEmbedProvider(gold_base), store, qdrant_affected_ids, spark=spark
                )
                if qdrant_affected_ids else _qdrant_noop(gold_base)
            ),
            input_lineage={
                "chunks_uri": gold["chunks_uri"],
                "affected_article_ids_key": silver["affected_article_ids_key"],
            },
        )
        reconciliation = _run_stage(
            repository, run_id, prefix + "reconciliation",
            lambda: reconcile(gold_base, spark, store, run_id=f"{run_id}-{partition}"),
            input_lineage={
                "chunks_uri": gold["chunks_uri"],
                "analytics_manifest_key": analytics["manifest_key"],
                "duckdb_path": duckdb["duckdb_path"],
                "qdrant_collection": qdrant["collection"],
            },
        )
        result = {
            "processing_date": partition,
            "source_file": source_file,
            "ingestion_id": bronze["ingestion_id"],
            "silver_affected_article_count": len(silver_affected_ids),
            "gold_affected_article_count": len(gold_affected_ids),
            "qdrant_affected_article_count": len(qdrant_affected_ids),
            "silver": silver,
            "gold": gold,
            "analytics": analytics,
            "duckdb": duckdb,
            "qdrant": qdrant,
            "reconciliation": reconciliation,
        }
        event("pipeline_partition_succeeded", run_id=run_id, **result)
        return result
    finally:
        repository.release_partition(pipeline_name, news.source, processing_date, run_id)


def execute(
    *,
    trigger_type: str,
    partitions: list[tuple[date, str]],
    force_reprocess: bool,
    run_id: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    if not partitions:
        raise ValueError("At least one partition is required")
    base = Settings.from_env()
    identity_gold = replace(GoldSettings.from_env(), news=base)
    identity_payload = json.dumps({
        "processing_version": base.processing_version,
        "chunker_version": identity_gold.chunker_version,
        "embedding_provider": identity_gold.embedding_provider,
        "embedding_model": identity_gold.embedding_model,
        "embedding_dimension": identity_gold.embedding_dimension,
    }, sort_keys=True)
    configuration_id = hashlib.sha256(identity_payload.encode()).hexdigest()[:12]
    pipeline_name = f"{PIPELINE_NAME}:{configuration_id}"
    start = min(item[0] for item in partitions)
    end = max(item[0] for item in partitions)
    run_id = run_id or make_run_id(trigger_type, start, end)
    operations = OperationsSettings.from_env()
    parameters = {
        "partitions": [
            {"processing_date": day.isoformat(), "source_file": path}
            for day, path in partitions
        ],
        "processing_version": base.processing_version,
        "configuration_id": configuration_id,
        "configuration": json.loads(identity_payload),
    }
    with OperationsRepository(operations) as repository:
        if not resume:
            try:
                repository.get_run(run_id)
                resume = True
            except KeyError:
                pass
        if resume:
            run = repository.get_run(run_id)
            validate_resume_identity(
                run,
                source=base.source,
                configuration_id=configuration_id,
                configuration=json.loads(identity_payload),
            )
            run = repository.resume_run(run_id)
            trigger_type = run["trigger_type"]
            force_reprocess = bool(run["force_reprocess"])
            pipeline_name = run["pipeline_name"]
            parameters = dict(run["parameters"])
            partitions = [
                (date.fromisoformat(item["processing_date"]), item["source_file"])
                for item in parameters["partitions"]
            ]
            start = run["partition_start"]
            end = run["partition_end"]
        else:
            repository.begin_run(
                run_id=run_id,
                pipeline_name=pipeline_name,
                source=base.source,
                trigger_type=trigger_type,
                partition_start=start,
                partition_end=end,
                force_reprocess=force_reprocess,
                parameters=parameters,
                airflow_dag_id=os.getenv("NEWS_AIRFLOW_DAG_ID") or None,
                airflow_run_id=os.getenv("NEWS_AIRFLOW_DAG_RUN_ID") or None,
            )
            if trigger_type == "NORMAL" and not force_reprocess:
                checkpoint = repository.checkpoint(pipeline_name, base.source)
                if checkpoint and checkpoint["last_successful_partition"] >= end:
                    repository.finish_run(run_id, "SKIPPED")
                    result = {
                        "run_id": run_id,
                        "status": "SKIPPED",
                        "reason": "partition is at or before the committed checkpoint",
                        "checkpoint": checkpoint,
                    }
                    event("pipeline_run_skipped", **result)
                    return result

        event(
            "pipeline_run_started", run_id=run_id, trigger_type=trigger_type,
            source=base.source, partition_start=start, partition_end=end,
            force_reprocess=force_reprocess,
        )
        from src.news_pipeline.silver import create_spark

        spark = create_spark(base)
        results: list[dict[str, Any]] = []
        try:
            for processing_date, source_file in partitions:
                if not Path(source_file).is_file():
                    raise FileNotFoundError(
                        f"No source fixture for partition {processing_date}: {source_file}"
                    )
                results.append(run_partition(
                    repository=repository,
                    run_id=run_id,
                    processing_date=processing_date,
                    source_file=source_file,
                    base_settings=base,
                    spark=spark,
                    pipeline_name=pipeline_name,
                ))
            if trigger_type in {"NORMAL", "MANUAL"}:
                repository.advance_checkpoint(pipeline_name, base.source, end, run_id)
            repository.finish_run(run_id, "SUCCESS")
            result = {
                "run_id": run_id,
                "status": "SUCCESS",
                "trigger_type": trigger_type,
                "partition_start": start.isoformat(),
                "partition_end": end.isoformat(),
                "partitions": results,
            }
            event("pipeline_run_succeeded", **result)
            return result
        except Exception as exc:
            repository.finish_run(run_id, "FAILED", str(exc))
            event("pipeline_run_failed", level="ERROR", run_id=run_id, error=str(exc))
            raise
        finally:
            spark.stop()


def _backfill_partitions(args) -> list[tuple[date, str]]:
    directory = Path(args.partition_dir)
    return [
        (day, str(directory / args.file_pattern.format(date=day.isoformat())))
        for day in date_range(args.from_date, args.to_date)
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    incremental = commands.add_parser("incremental")
    incremental.add_argument("--date", required=True, type=parse_date)
    incremental.add_argument("--source-file")
    incremental.add_argument("--run-id")

    backfill = commands.add_parser("backfill")
    backfill.add_argument("--from-date", required=True, type=parse_date)
    backfill.add_argument("--to-date", required=True, type=parse_date)
    backfill.add_argument("--partition-dir", required=True)
    backfill.add_argument("--file-pattern", default="{date}.json")
    backfill.add_argument("--run-id")

    reprocess = commands.add_parser("reprocess")
    reprocess.add_argument("--date", required=True, type=parse_date)
    reprocess.add_argument("--source-file")
    reprocess.add_argument("--force-reprocess", action="store_true", required=True)
    reprocess.add_argument("--run-id")

    resume = commands.add_parser("resume")
    resume.add_argument("--run-id", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    default_source = Settings.from_env().source_file
    if args.command == "incremental":
        result = execute(
            trigger_type="NORMAL",
            partitions=[(args.date, args.source_file or default_source)],
            force_reprocess=False,
            run_id=args.run_id,
        )
    elif args.command == "backfill":
        result = execute(
            trigger_type="BACKFILL",
            partitions=_backfill_partitions(args),
            force_reprocess=False,
            run_id=args.run_id,
        )
    elif args.command == "reprocess":
        result = execute(
            trigger_type="REPROCESS",
            partitions=[(args.date, args.source_file or default_source)],
            force_reprocess=True,
            run_id=args.run_id,
        )
    else:
        result = execute(
            trigger_type="MANUAL", partitions=[(date.today(), default_source)],
            force_reprocess=False, run_id=args.run_id, resume=True,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
