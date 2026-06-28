"""
CLI entry point for the multi-source scraper.

Usage
-----
Scrape every ticker on every implemented source::

    python -m src.scraper.run --ticket all

Scrape a single ticker::

    python -m src.scraper.run --ticket ACB

Restrict to specific sources (comma-separated) and cap pages::

    python -m src.scraper.run --ticket ACB --source cafef --max-pages 2

Each run writes a plain-text log and a JSON log (for FluentBit -> Loki) under
``LOGS_DIR``.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.scraper.config import ScraperSettings, get_settings
from src.scraper.engine.pipeline import run_pipeline
from src.scraper.engine.registry import available_sources
from src.utils.logger import get_logger


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.scraper.run",
        description="Scrape financial-news sites for VN30 tickers into ADLS + PostgreSQL.",
    )
    parser.add_argument(
        "--ticket",
        default="all",
        metavar="SYMBOL",
        help="Ticker to scrape ('all' for every ticker, or e.g. 'ACB'). "
        "Comma-separated lists are accepted (e.g. 'ACB,FPT').",
    )
    parser.add_argument(
        "--source",
        default="all",
        metavar="NAME",
        help=f"Source(s) to scrape ('all' or comma-separated). "
        f"Available: {available_sources()}.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override SCRAPER_MAX_PAGES for this run (per keyword).",
    )
    parser.add_argument(
        "--triggered-by",
        default="manual",
        choices=["manual", "cron", "prefect"],
        help="How this run was triggered (recorded on the crawl job).",
    )
    return parser


def _parse_tickets(raw: str) -> Optional[List[str]]:
    """Return a ticker whitelist, or ``None`` for 'all'."""
    if raw.strip().lower() == "all":
        return None
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def _build_log_stem(logs_dir: Path, tickers: Optional[List[str]]) -> str:
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    suffix = "_" + "-".join(tickers) if tickers else "_all"
    return str(logs_dir / f"scrape_{timestamp}{suffix}")


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.max_pages is not None:
        os.environ["SCRAPER_MAX_PAGES"] = str(args.max_pages)

    settings: ScraperSettings = get_settings()
    tickers = _parse_tickets(args.ticket)

    log_stem = _build_log_stem(settings.logs_dir, tickers)
    plain_log = f"{log_stem}.log"
    json_log = f"{log_stem}.json.log"
    logger = get_logger("src.scraper", log_file=plain_log, json_log_file=json_log)

    logger.info("Plain log        : %s", plain_log)
    logger.info("JSON log         : %s", json_log)
    logger.info("PostgreSQL       : %s:%s/%s", settings.pg_host, settings.pg_port, settings.pg_database)
    logger.info("ADLS filesystem  : %s", settings.adls_filesystem)
    logger.info("Sources          : %s", args.source)
    logger.info("Tickers          : %s", tickers or "all")
    logger.info("Max pages/keyword: %s", settings.max_pages)

    started_at = datetime.now()
    try:
        run_pipeline(
            settings,
            tickers=tickers,
            source_filter=args.source,
            triggered_by=args.triggered_by,
        )
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl-C). Partial progress is saved.")
        return 130
    except Exception as exc:
        logger.exception("Run aborted by unhandled exception: %s", exc)
        return 1
    finally:
        elapsed = (datetime.now() - started_at).total_seconds()
        logger.info("Total elapsed: %.1fs", elapsed)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
