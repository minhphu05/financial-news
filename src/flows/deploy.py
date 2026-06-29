"""Register Prefect deployments for the Financial News pipeline.

Run from inside the orchestrator container::

    python -m src.flows.deploy

Prefect is used solely as a time-based trigger. The registered deployments:

* ``financial-news-market-data/noon`` - daily at 12:00 ICT.
* ``financial-news-market-data/afternoon`` - daily at 15:00 ICT.
* ``financial-news-standard-scraper/daily`` - daily at 16:00 ICT.
* ``financial-news-standard-scraper/manual`` - on-demand manual trigger via Prefect UI.
"""

from __future__ import annotations

from prefect import serve
from prefect.client.schemas.schedules import CronSchedule

from src.flows.standard_scraper_flow import market_data_flow, standard_scraper_flow
from src.rag.utils import get_logger

logger = get_logger(__name__)

ICT_TIMEZONE = "Asia/Ho_Chi_Minh"


def deploy() -> None:
    """Register Prefect deployments for the Financial News pipeline.

    Prefect acts only as a scheduler/trigger. Two deployments are registered:

    * **daily** — Runs at 06:00 ICT every day. Executes the full pipeline:
      scrape → preprocess → chunk → embed → Qdrant.
    * **manual** — No schedule; triggered manually from the Prefect UI
      or API when an immediate pipeline run is needed.
    """
    noon_market_deployment = market_data_flow.to_deployment(
        name="noon",
        schedule=CronSchedule(cron="0 12 * * *", timezone=ICT_TIMEZONE),
        parameters={"session_note": "MORNING", "is_eod": False},
        tags=["financial-news", "market-data", "noon", "scheduled"],
    )
    afternoon_market_deployment = market_data_flow.to_deployment(
        name="afternoon",
        schedule=CronSchedule(cron="0 15 * * *", timezone=ICT_TIMEZONE),
        parameters={"session_note": "AFTERNOON", "is_eod": False},
        tags=["financial-news", "market-data", "afternoon", "scheduled"],
    )
    daily_news_deployment = standard_scraper_flow.to_deployment(
        name="daily",
        schedule=CronSchedule(cron="0 16 * * *", timezone=ICT_TIMEZONE),
        parameters={"skip_market_data": True},
        tags=["financial-news", "daily", "news", "scheduled"],
    )
    manual_deployment = standard_scraper_flow.to_deployment(
        name="manual",
        tags=["financial-news", "manual"],
    )

    logger.info("Registering Prefect deployments: market data 12:00/15:00 ICT + news 16:00 ICT + manual.")
    serve(
        noon_market_deployment,
        afternoon_market_deployment,
        daily_news_deployment,
        manual_deployment,
    )


if __name__ == "__main__":
    deploy()

