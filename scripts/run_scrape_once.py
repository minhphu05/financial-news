"""One-shot script that triggers a CafeF scrape outside Prefect.

Useful for local debugging and the first historical backfill::

    python scripts/run_scrape_once.py --keywords "VN-Index,BCM"
"""

from __future__ import annotations

import argparse
import json

from src.rag.databases import MongoRepository
from src.rag.ingestion import DailyCafefScraper


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a CafeF scrape once.")
    parser.add_argument(
        "--keywords",
        type=str,
        default=None,
        help="Comma-separated keywords. Defaults to SCRAPER_KEYWORDS env var.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = _parse_args()
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else None

    with MongoRepository() as repo:
        report = DailyCafefScraper(repo=repo).run(keywords=keywords)
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
