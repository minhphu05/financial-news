"""
CLI entry point for the scraper.

Usage
-----
Run the full pipeline (all tickers in the input Excel)::

    python -m src.scraper.run

Restrict to one or more ticker symbols (handy for smoke tests)::

    python -m src.scraper.run --ticker BCM
    python -m src.scraper.run --ticker ACB --ticker BID

Override the maximum pages per keyword (useful for short test runs)::

    python -m src.scraper.run --ticker BCM --max-pages 2

Every invocation writes a dedicated log file under ``LOGS_DIR``. Two formats
are produced:

* **Plain text** (human-readable): ``scrape_20260528T231245_BCM.log``
* **JSON structured** (FluentBit): ``scrape_20260528T231245_BCM.json.log``

The JSON variant is tailed by FluentBit and shipped to Loki for centralized
log querying via Grafana.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.scraper.legacy.config import ScraperSettings, get_settings
from src.scraper.legacy.pipeline import run_pipeline
from src.utils.logger import get_logger



# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the scraper CLI."""
    parser = argparse.ArgumentParser(
        prog="src.scraper.run",
        description="Scrape CafeF news for VN30 tickers into PostgreSQL + MongoDB.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        metavar="SYMBOL",
        help="Restrict the run to one or more ticker symbols (repeatable).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override CAFEF_MAX_PAGES for this run (per keyword).",
    )
    parser.add_argument(
        "--triggered-by",
        type=str,
        default="manual",
        choices=["manual", "cron", "prefect"],
        help="How this run was triggered (recorded in scrape_runs table).",
    )
    parser.add_argument(
        "--skip-auto-ingest",
        action="store_true",
        help=(
            "Skip automatic preprocessing/chunking/embedding after scraping. "
            "By default, ingestion runs automatically when new articles are found."
        ),
    )
    parser.add_argument(
        "--ingest-max-articles",
        type=int,
        default=None,
        help=(
            "Optional safety cap for the auto-ingestion stage "
            "(number of pending articles to process)."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Per-run log file
# ---------------------------------------------------------------------------
def _build_log_stem(logs_dir: Path, ticker_filter: Optional[List[str]]) -> str:
    """
    Compose the per-run log file stem (without extension).

    The filename always embeds the start timestamp; if a ticker filter is
    active the symbols are appended to make the file easy to locate.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    suffix = "_" + "-".join(sorted({t.upper() for t in ticker_filter})) if ticker_filter else ""
    return str(logs_dir / f"scrape_{timestamp}{suffix}")


def _run_auto_ingestion(
    logger,
    *,
    has_new_articles: bool,
    ingest_max_articles: Optional[int] = None,
) -> None:
    """Run preprocessing/chunking/embedding automatically after scraping.

    Parameters
    ----------
    has_new_articles : bool
        Whether the scrape stage persisted new content. If ``False``, ingestion
        is skipped to avoid unnecessary embedding API calls.
    ingest_max_articles : Optional[int]
        Optional upper bound for a single ingestion pass.

    Notes
    -----
    This function intentionally imports ingestion dependencies lazily so that
    users can still run scrape-only workflows in minimal environments.
    """
    if not has_new_articles:
        logger.info("No new scraped articles detected; auto-ingestion is skipped.")
        return

    logger.info(
        "New scraped data detected; starting automatic preprocessing/chunking/embedding."
    )

    from src.rag.config import get_settings as get_rag_settings
    from src.rag.databases import MongoRepository, QdrantRepository
    from src.rag.ingestion import VoyageAIEmbedder
    from src.rag.ingestion.pipeline import IngestionPipeline

    rag_settings = get_rag_settings()
    with MongoRepository(settings=rag_settings) as mongo, QdrantRepository(settings=rag_settings) as qdrant:
        embedder = VoyageAIEmbedder(settings=rag_settings)
        pipeline = IngestionPipeline(
            mongo=mongo,
            qdrant=qdrant,
            embedder=embedder,
            settings=rag_settings,
        )
        report = pipeline.run(max_articles=ingest_max_articles)
        logger.info("Auto-ingestion completed: %s", report.as_dict())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    args = _build_arg_parser().parse_args(argv)

    # Apply optional --max-pages override BEFORE settings get cached.
    if args.max_pages is not None:
        os.environ["CAFEF_MAX_PAGES"] = str(args.max_pages)

    settings: ScraperSettings = get_settings()
    log_stem = _build_log_stem(settings.logs_dir, args.ticker)

    # Two log outputs: plain text for humans, JSON for FluentBit
    plain_log = f"{log_stem}.log"
    json_log = f"{log_stem}.json.log"

    logger = get_logger(
        "src.scraper",
        log_file=plain_log,
        json_log_file=json_log,
    )

    logger.info(f"Logging this run to: {plain_log}")
    logger.info(f"JSON log (FluentBit): {json_log}")
    logger.info(f"Project root      : {Path(__file__).resolve().parents[2]}")
    logger.info(f"Input Excel dir   : {settings.raw_input_dir}")
    logger.info(f"PostgreSQL host   : {settings.pg_host}:{settings.pg_port}")
    logger.info(f"MongoDB target    : {settings.mongo_db}.{settings.mongo_collection}")
    logger.info(f"Max pages/keyword : {settings.max_pages}")
    logger.info(f"Early-stop thresh : {settings.consecutive_known_threshold} consecutive known")
    if args.ticker:
        logger.info(f"Ticker filter     : {sorted({t.upper() for t in args.ticker})}")

    started_at = datetime.now()
    try:
        scrape_summary = run_pipeline(
            settings,
            only_tickers=args.ticker,
            triggered_by=args.triggered_by,
        )

        if not args.skip_auto_ingest:
            _run_auto_ingestion(
                logger,
                has_new_articles=scrape_summary.articles_persisted > 0,
                ingest_max_articles=args.ingest_max_articles,
            )
        else:
            logger.info("Auto-ingestion disabled by --skip-auto-ingest.")
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl-C). Partial progress is saved.")
        return 130
    except Exception as exc:
        logger.exception(f"Run aborted by unhandled exception: {exc}")
        return 1
    finally:
        elapsed = (datetime.now() - started_at).total_seconds()
        logger.info(f"Total elapsed: {elapsed:.1f}s")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
