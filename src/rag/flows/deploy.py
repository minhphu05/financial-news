"""Register Prefect deployments for the ViFinNER pipeline.

Run from inside the orchestrator container::

    python -m src.rag.flows.deploy

This registers three deployments against the configured ``PREFECT_API_URL``:

* ``vifinner-scrape/daily``        - daily at 06:00 ICT.
* ``vifinner-ingest/daily``        - daily at 06:30 ICT.
* ``vifinner-full-pipeline/on-demand`` - manual run for backfills.
"""

from __future__ import annotations

from prefect import serve

from src.rag.flows.eval_flow import rag_eval_flow
from src.rag.flows.full_pipeline_flow import full_pipeline_flow
from src.rag.flows.medallion_flow import medallion_flow
from src.rag.flows.scrape_quality_flow import scrape_quality_flow
from src.rag.utils import get_logger

logger = get_logger(__name__)

WORK_POOL_NAME = "vifinner-pool"
ICT_TIMEZONE = "Asia/Ho_Chi_Minh"


def deploy() -> None:
    """Register every Prefect deployment used by ViFinNER.

    Schedules
    ---------
    * **scrape-quality** — daily at 06:00 ICT (Pydantic-gated scrape).
    * **medallion**      — daily at 06:30 ICT (Bronze → Silver → Gold).
    * **rag-eval**       — weekly on Mondays at 07:00 ICT.
    * **full-pipeline**  — on-demand (manual runs / backfills).
    """
    logger.info("Registering ViFinNER Prefect deployments.")

    scrape_quality = scrape_quality_flow.to_deployment(
        name="daily",
        cron="0 6 * * *",
        timezone=ICT_TIMEZONE,
        tags=["vifinner", "scrape", "quality", "daily"],
    )
    medallion = medallion_flow.to_deployment(
        name="daily",
        cron="30 6 * * *",
        timezone=ICT_TIMEZONE,
        tags=["vifinner", "medallion", "daily"],
    )
    rag_eval = rag_eval_flow.to_deployment(
        name="weekly",
        cron="0 7 * * 1",
        timezone=ICT_TIMEZONE,
        tags=["vifinner", "eval", "weekly"],
    )
    on_demand = full_pipeline_flow.to_deployment(
        name="on-demand",
        tags=["vifinner", "manual"],
    )

    serve(scrape_quality, medallion, rag_eval, on_demand, work_pool_name=WORK_POOL_NAME)


if __name__ == "__main__":
    deploy()
