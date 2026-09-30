"""Translate Airflow parameters into the standalone hardened-pipeline API."""

from datetime import date
import json
import os
from pathlib import Path

from src.news_pipeline.config import Settings
from src.news_pipeline.pipeline_runner import date_range, execute


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing Airflow pipeline parameter: {name}")
    return value


def main() -> None:
    mode = os.getenv("NEWS_RUN_MODE", "incremental").lower()
    run_id = os.getenv("NEWS_PIPELINE_RUN_ID") or None
    default_source = Settings.from_env().source_file
    if mode == "incremental":
        day = date.fromisoformat(_required("NEWS_PROCESSING_DATE"))
        result = execute(
            trigger_type="NORMAL",
            partitions=[(day, os.getenv("NEWS_RUN_SOURCE_FILE") or default_source)],
            force_reprocess=False,
            run_id=run_id,
        )
    elif mode == "backfill":
        start = date.fromisoformat(_required("NEWS_BACKFILL_FROM"))
        end = date.fromisoformat(_required("NEWS_BACKFILL_TO"))
        directory = Path(_required("NEWS_PARTITION_DIR"))
        pattern = os.getenv("NEWS_PARTITION_FILE_PATTERN", "{date}.json")
        result = execute(
            trigger_type="BACKFILL",
            partitions=[
                (day, str(directory / pattern.format(date=day.isoformat())))
                for day in date_range(start, end)
            ],
            force_reprocess=False,
            run_id=run_id,
        )
    elif mode == "reprocess":
        if os.getenv("NEWS_FORCE_REPROCESS", "false").lower() != "true":
            raise ValueError("Airflow reprocess requires force_reprocess=true")
        day = date.fromisoformat(_required("NEWS_PROCESSING_DATE"))
        result = execute(
            trigger_type="REPROCESS",
            partitions=[(day, os.getenv("NEWS_RUN_SOURCE_FILE") or default_source)],
            force_reprocess=True,
            run_id=run_id,
        )
    elif mode == "resume":
        if not run_id:
            raise ValueError("Airflow resume requires pipeline_run_id")
        result = execute(
            trigger_type="MANUAL",
            partitions=[(date.today(), default_source)],
            force_reprocess=False,
            run_id=run_id,
            resume=True,
        )
    else:
        raise ValueError(f"Unsupported NEWS_RUN_MODE: {mode}")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
