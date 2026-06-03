"""Register Prefect deployments for the Financial News pipeline.

Run from inside the orchestrator container::

    python -m src.flows.deploy

Prefect is used solely as a time-based trigger. The registered deployments:

* ``financial-news-full-pipeline/daily``  - daily at 06:00 ICT (scrape → preprocess → embed).
* ``financial-news-full-pipeline/manual`` - on-demand manual trigger via Prefect UI.
"""

from __future__ import annotations

from prefect import serve
from prefect.client.schemas.schedules import CronSchedule

from src.flows.full_pipeline_flow import full_pipeline_flow
from src.rag.utils import get_logger

logger = get_logger(__name__)

ICT_TIMEZONE = "Asia/Ho_Chi_Minh"
WORK_POOL_NAME = "financial-news-pool"


def deploy() -> None:
    """Register Prefect deployments for the Financial News pipeline.

    Prefect acts only as a scheduler/trigger. Two deployments are registered:

    * **daily** — Runs at 06:00 ICT every day. Executes the full pipeline:
      scrape → preprocess → chunk → embed → Qdrant.
    * **manual** — No schedule; triggered manually from the Prefect UI
      or API when an immediate pipeline run is needed.
    """
    daily_deployment = full_pipeline_flow.to_deployment(
        name="daily",
        schedule=CronSchedule(cron="0 6 * * *", timezone=ICT_TIMEZONE),
        tags=["financial-news", "daily", "scheduled"],
    )
    manual_deployment = full_pipeline_flow.to_deployment(
        name="manual",
        tags=["financial-news", "manual"],
    )

    logger.info("Registering Prefect deployments: daily (06:00 ICT) + manual trigger.")
    serve(daily_deployment, manual_deployment, work_pool_name=WORK_POOL_NAME)


if __name__ == "__main__":
    deploy()

