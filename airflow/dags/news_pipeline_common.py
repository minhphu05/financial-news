"""Thin Airflow operator factory for the existing standalone pipeline jobs."""

from __future__ import annotations

from datetime import timedelta
import os
from pathlib import Path
from typing import Sequence

from airflow.operators.bash import BashOperator


SPARK_PACKAGES = "io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4"
SPARK_SUBMIT = [
    "/opt/spark/bin/spark-submit",
    "--packages",
    SPARK_PACKAGES,
    "--conf",
    "spark.jars.ivy=/opt/news-ivy",
]


def required_runtime_config() -> dict[str, str]:
    """Return logical runtime configuration and fail clearly when it is absent."""
    names = ("NEWS_STORAGE_ENDPOINT", "NEWS_STORAGE_BUCKET", "NEWS_SOURCE_FILE", "NEWS_QDRANT_URL")
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required pipeline configuration: {', '.join(missing)}")
    source = Path(os.environ["NEWS_SOURCE_FILE"])
    if not source.is_absolute():
        raise RuntimeError("NEWS_SOURCE_FILE must be an absolute container path")
    return {name: os.environ[name] for name in names}


def context_environment() -> dict[str, str]:
    return {
        "NEWS_AIRFLOW_DAG_ID": "{{ dag.dag_id }}",
        "NEWS_AIRFLOW_DAG_RUN_ID": "{{ run_id }}",
        "NEWS_AIRFLOW_LOGICAL_DATE": "{{ logical_date }}",
        "NEWS_AIRFLOW_UPSTREAM_RUN_ID": "{{ dag_run.conf.get('upstream_run_id', '') if dag_run else '' }}",
    }


def pipeline_task(
    *,
    task_id: str,
    command: Sequence[str],
    retries: int,
    retry_delay: timedelta,
    execution_timeout: timedelta = timedelta(hours=2),
    env: dict[str, str] | None = None,
) -> BashOperator:
    required_runtime_config()
    rendered = " ".join(command)
    task_env = context_environment()
    if env:
        task_env.update(env)
    return BashOperator(
        task_id=task_id,
        bash_command=rendered,
        cwd="/app",
        env=task_env,
        append_env=True,
        do_xcom_push=False,
        retries=retries,
        retry_delay=retry_delay,
        execution_timeout=execution_timeout,
    )


def python_module_task(
    *, task_id: str, module: str, args: Sequence[str] = (), retries: int = 0,
    retry_delay: timedelta = timedelta(seconds=30), env: dict[str, str] | None = None,
) -> BashOperator:
    return pipeline_task(
        task_id=task_id,
        command=["python3", "-m", module, *args],
        retries=retries,
        retry_delay=retry_delay,
        env=env,
    )


def spark_task(
    *, task_id: str, script: str, retries: int = 1,
    retry_delay: timedelta = timedelta(minutes=1), env: dict[str, str] | None = None,
) -> BashOperator:
    return pipeline_task(
        task_id=task_id,
        command=[*SPARK_SUBMIT, script],
        retries=retries,
        retry_delay=retry_delay,
        env=env,
    )
