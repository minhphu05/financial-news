"""Schedule or manually invoke the standalone hardened news pipeline."""

from datetime import timedelta
import os

import pendulum
from airflow import DAG
from airflow.models.param import Param

from news_pipeline_common import spark_task


with DAG(
    dag_id="news_incremental_pipeline",
    description="Incremental/backfill/reprocess orchestration with durable run state",
    schedule=os.getenv("AIRFLOW_NEWS_INCREMENTAL_SCHEDULE") or None,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    params={
        "mode": Param("incremental", enum=["incremental", "backfill", "reprocess", "resume"]),
        "processing_date": Param("", type=["null", "string"]),
        "from_date": Param("", type=["null", "string"]),
        "to_date": Param("", type=["null", "string"]),
        "partition_dir": Param("/app/data/partitions", type="string"),
        "file_pattern": Param("{date}.json", type="string"),
        "source_file": Param("", type=["null", "string"]),
        "force_reprocess": Param(False, type="boolean"),
        "pipeline_run_id": Param("", type=["null", "string"]),
    },
    default_args={"owner": "financial-news", "depends_on_past": False},
    tags=["financial-news", "local", "incremental", "phase05"],
) as dag:
    run_incremental_pipeline = spark_task(
        task_id="run_incremental_pipeline",
        script="/app/src/news_pipeline/airflow_runner.py",
        retries=1,
        retry_delay=timedelta(minutes=1),
        env={
            "NEWS_RUN_MODE": "{{ params.mode }}",
            "NEWS_PROCESSING_DATE": "{{ params.processing_date or ds }}",
            "NEWS_BACKFILL_FROM": "{{ params.from_date }}",
            "NEWS_BACKFILL_TO": "{{ params.to_date }}",
            "NEWS_PARTITION_DIR": "{{ params.partition_dir }}",
            "NEWS_PARTITION_FILE_PATTERN": "{{ params.file_pattern }}",
            "NEWS_RUN_SOURCE_FILE": "{{ params.source_file }}",
            "NEWS_FORCE_REPROCESS": "{{ params.force_reprocess | lower }}",
            "NEWS_PIPELINE_RUN_ID": "{{ params.pipeline_run_id or ('airflow__' ~ run_id) }}",
        },
    )
