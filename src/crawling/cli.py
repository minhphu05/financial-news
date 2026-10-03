"""Explicit, bounded local crawler commands; live requests never run in CI."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .jobs import crawl, publish
from .sources import SOURCES
from .state import Repository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    sub.add_parser("status")
    for name in ("crawl", "recrawl", "backfill", "live-smoke", "publish"):
        p = sub.add_parser(name)
        p.add_argument("--source", choices=[*SOURCES, "all"], required=True)
        if name != "publish":
            p.add_argument("--limit", type=int, default=1)
            p.add_argument("--url", action="append")
            p.add_argument(
                "--allow-live",
                action="store_true",
                help="Required to make public HTTP requests",
            )
            if name == "backfill":
                p.add_argument("--url-file", required=True)
                p.add_argument("--from-date", type=date.fromisoformat, required=True)
                p.add_argument("--to-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    with Repository() as repo:
        if args.command == "seed":
            result = {"seeded": repo.seed()}
        elif args.command == "status":
            result = {
                "sources": repo.query(
                    "SELECT source,cooldown_until,last_success_at FROM crawler_operations.source_state ORDER BY source"
                ),
                "frontier": repo.query(
                    "SELECT source,status,count(*) FROM crawler_operations.frontier GROUP BY source,status ORDER BY source,status"
                ),
                "batches": repo.query(
                    "SELECT source,status,count(*) FROM crawler_operations.batches GROUP BY source,status ORDER BY source,status"
                ),
                "recent_runs": repo.query(
                    "SELECT * FROM crawler_operations.crawl_runs ORDER BY started_at DESC LIMIT 10"
                ),
            }
        else:
            if args.command != "publish" and not args.allow_live:
                parser.error(
                    "Public HTTP requires --allow-live; use make crawler-demo for offline fixtures"
                )
            if args.command == "recrawl" and not args.url:
                parser.error("recrawl requires an explicit --url")
            urls = args.url if args.command != "publish" else None
            if args.command == "backfill":
                urls = json.loads(Path(args.url_file).read_text())
                if (
                    not isinstance(urls, list)
                    or not all(isinstance(u, str) for u in urls)
                    or not 1 <= len(urls) <= 20
                ):
                    parser.error("url-file must be a JSON array of 1–20 explicit URLs")
                if args.to_date < args.from_date:
                    parser.error("Invalid backfill date range")
            results = []
            for source in SOURCES if args.source == "all" else [args.source]:
                try:
                    if args.command == "publish":
                        r = publish(source, repository=repo)
                    else:
                        r = crawl(
                            source,
                            repository=repo,
                            limit=args.limit,
                            urls=urls,
                            trigger="RECRAWL"
                            if args.command == "recrawl"
                            else "BACKFILL"
                            if args.command == "backfill"
                            else "NORMAL",
                            from_date=getattr(args, "from_date", None),
                            to_date=getattr(args, "to_date", None),
                        )
                    results.append(r)
                except Exception as e:  # noqa: BLE001 - one source must not cancel others
                    results.append(
                        {"source": source, "status": "FAILED", "error": str(e)[:500]}
                    )
            result = {"results": results}
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if any(
            r.get("status") in ("FAILED", "BLOCKED") for r in result.get("results", [])
        ):
            sys.exit(2)


if __name__ == "__main__":
    main()
