"""Orchestrate the existing RAG/Qdrant and Analytics/DuckDB entrypoints."""

from datetime import timedelta
import os

import pendulum
from airflow import DAG
from airflow.models.param import Param

from news_pipeline_common import python_module_task, spark_task


with DAG(
    dag_id="news_gold_pipeline",
    description="Delta Silver to durable Gold and local serving projections",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=4,
    params={
        "index_limit": Param(
            int(os.getenv("AIRFLOW_NEWS_INDEX_LIMIT", "96")),
            type="integer",
            minimum=0,
            description="Maximum deterministic Gold chunks to index; 0 indexes all chunks.",
        )
    },
    default_args={"owner": "financial-news", "depends_on_past": False},
    tags=["financial-news", "local", "gold"],
) as dag:
    validate_silver = python_module_task(
        task_id="validate_silver",
        module="src.news_pipeline.orchestration_quality",
        args=["silver"],
    )

    build_gold_rag_chunks = spark_task(
        task_id="build_gold_rag_chunks",
        script="/app/src/news_pipeline/gold_rag.py",
    )
    embed_and_index_qdrant = spark_task(
        task_id="embed_and_index_qdrant",
        script="/app/src/news_pipeline/qdrant_index.py",
        env={"NEWS_INDEX_LIMIT": "{{ params.index_limit }}"},
    )
    rag_quality_check = python_module_task(
        task_id="rag_quality_check",
        module="src.news_pipeline.orchestration_quality",
        args=["rag"],
    )

    build_gold_analytics = spark_task(
        task_id="build_gold_analytics",
        script="/app/src/news_pipeline/analytics.py",
    )
    publish_duckdb = python_module_task(
        task_id="publish_duckdb",
        module="src.news_pipeline.duckdb_serving",
        args=["build"],
        retries=1,
        retry_delay=timedelta(seconds=30),
    )
    analytics_quality_check = python_module_task(
        task_id="analytics_quality_check",
        module="src.news_pipeline.orchestration_quality",
        args=["analytics"],
    )

    publish_gold_success = python_module_task(
        task_id="publish_gold_success",
        module="src.news_pipeline.orchestration_quality",
        args=["publish-gold"],
    )

    validate_silver >> build_gold_rag_chunks >> embed_and_index_qdrant >> rag_quality_check
    validate_silver >> build_gold_analytics >> publish_duckdb >> analytics_quality_check
    [rag_quality_check, analytics_quality_check] >> publish_gold_success
