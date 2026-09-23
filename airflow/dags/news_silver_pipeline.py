"""Orchestrate the existing Bronze and Silver entrypoints."""

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from news_pipeline_common import python_module_task, spark_task


with DAG(
    dag_id="news_silver_pipeline",
    description="CafeF sample snapshot to immutable Bronze and Delta Silver",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "financial-news", "depends_on_past": False},
    tags=["financial-news", "local", "silver"],
) as dag:
    start = EmptyOperator(task_id="start")
    validate_source_data = python_module_task(
        task_id="validate_source_data",
        module="src.news_pipeline.orchestration_quality",
        args=["source"],
    )
    bronze_ingest = python_module_task(
        task_id="bronze_ingest",
        module="src.news_pipeline.bronze",
        retries=2,
        retry_delay=timedelta(seconds=30),
    )
    bronze_quality_check = python_module_task(
        task_id="bronze_quality_check",
        module="src.news_pipeline.orchestration_quality",
        args=["bronze"],
    )
    spark_bronze_to_silver = spark_task(
        task_id="spark_bronze_to_silver",
        script="/app/src/news_pipeline/silver.py",
        retries=1,
        retry_delay=timedelta(minutes=1),
    )
    silver_quality_check = python_module_task(
        task_id="silver_quality_check",
        module="src.news_pipeline.orchestration_quality",
        args=["silver"],
    )
    publish_silver_success = python_module_task(
        task_id="publish_silver_success",
        module="src.news_pipeline.orchestration_quality",
        args=["publish-silver"],
    )
    trigger_gold = TriggerDagRunOperator(
        task_id="trigger_gold_pipeline",
        trigger_dag_id="news_gold_pipeline",
        trigger_run_id="gold_after__{{ run_id }}",
        logical_date="{{ logical_date }}",
        conf={
            "upstream_dag_id": "{{ dag.dag_id }}",
            "upstream_run_id": "{{ run_id }}",
            "upstream_logical_date": "{{ logical_date }}",
        },
        reset_dag_run=True,
        wait_for_completion=True,
        poke_interval=10,
        allowed_states=["success"],
        failed_states=["failed"],
        retries=0,
    )

    start >> validate_source_data >> bronze_ingest >> bronze_quality_check
    bronze_quality_check >> spark_bronze_to_silver >> silver_quality_check
    silver_quality_check >> publish_silver_success >> trigger_gold
