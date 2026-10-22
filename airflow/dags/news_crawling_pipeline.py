"""Bounded source batches; all HTTP, frontier and pipeline logic is standalone."""

import os

import pendulum
from airflow.models.param import Param
from airflow.utils.task_group import TaskGroup
from news_pipeline_common import python_module_task, spark_task

from airflow import DAG

# Scheduling is opt-in. Defaults are a safe manual fixture demo.
schedule = os.getenv("AIRFLOW_NEWS_CRAWLER_SCHEDULE") or None
scheduled_live = (
    os.getenv("AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE", "false").lower() == "true"
)
if schedule and not scheduled_live:
    raise RuntimeError(
        "Crawler schedule requires explicit AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE=true"
    )
batch_limit = int(os.getenv("AIRFLOW_NEWS_CRAWLER_LIMIT", "1"))
if not 1 <= batch_limit <= 20:
    raise ValueError("AIRFLOW_NEWS_CRAWLER_LIMIT must be between 1 and 20")
with DAG(
    dag_id="news_crawling_pipeline",
    description="Phase08 manual multisource crawl -> existing hardened pipeline",
    schedule=schedule,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    params={
        "sources": Param(
            ["cafef", "vnexpress", "tuoitre", "thanhnien", "baomoi"],
            type="array",
            items={
                "type": "string",
                "enum": ["cafef", "vnexpress", "tuoitre", "thanhnien", "baomoi"],
            },
        ),
        # Manual triggers stay fixture-safe even when automatic live scheduling is on.
        "fixture_mode": Param(True, type="boolean"),
        "allow_live": Param(False, type="boolean"),
        "limit": Param(batch_limit, type="integer", minimum=1, maximum=20),
    },
    default_args={"owner": "financial-news", "depends_on_past": False},
    tags=["financial-news", "local", "crawler", "phase08"],
) as dag:
    for source in ("cafef", "vnexpress", "tuoitre", "thanhnien", "baomoi"):
        with TaskGroup(group_id=source):
            env = {
                "CRAWLER_SOURCE_KEY": source,
                "CRAWLER_SELECTED_SOURCES": "{{ params.sources | tojson }}",
                "CRAWLER_FIXTURE_MODE": "{{ params.fixture_mode | lower }}",
                "CRAWLER_ALLOW_LIVE": "{{ params.allow_live | lower }}",
                "CRAWLER_BATCH_LIMIT": "{{ params.limit }}",
                "CRAWLER_AIRFLOW_RUN_TYPE": "{{ dag_run.run_type }}",
                "CRAWLER_AIRFLOW_RUN_ID": "{{ run_id }}",
                "CRAWLER_AIRFLOW_DAG_ID": "{{ dag.dag_id }}",
                "CRAWLER_SCHEDULED_LIVE_ALLOWED": str(scheduled_live).lower(),
            }
            fetch = python_module_task(
                task_id="crawl",
                module="src.crawling.airflow_jobs",
                env={**env, "CRAWLER_STAGE": "crawl"},
                retries=0,
            )
            process = spark_task(
                task_id="publish",
                script="/app/src/crawling/airflow_jobs.py",
                env={**env, "CRAWLER_STAGE": "publish"},
                retries=1,
            )
            # Drain already accepted data even if the current fetch task failed.
            process.trigger_rule = "all_done"
            fetch >> process
