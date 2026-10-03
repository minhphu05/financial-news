"""Capture local Phase08 evidence, without fetching websites or logging credentials."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.crawling.state import Repository


def main():
    with Repository() as repo:
        sources = repo.query(
            "SELECT source,status,count(*) AS runs FROM crawler_operations.crawl_runs GROUP BY source,status ORDER BY source,status"
        )
        publication = repo.query(
            "SELECT schemaname,tablename FROM pg_publication_tables WHERE pubname=%s ORDER BY schemaname,tablename",
            (os.getenv("METADATA_CDC_PUBLICATION", "metadata_cdc_publication"),),
        )
        batches = repo.query(
            "SELECT source,status,count(*) AS batches FROM crawler_operations.batches GROUP BY source,status ORDER BY source,status"
        )
        reconciliation = repo.query("""SELECT r.source,r.run_id,s.metrics FROM pipeline_operations.pipeline_runs r
          JOIN pipeline_operations.pipeline_stage_runs s USING(run_id)
          WHERE r.run_id LIKE 'pipeline-crawl-%%' AND s.stage_name LIKE '%%:reconciliation' AND s.status='SUCCESS'
          ORDER BY s.finished_at DESC LIMIT 30""")
    checks = {
        "five_fixture_sources_verified": all(
            any(
                s["source"] == "fixture-acceptance:" + k and s["status"] == "SUCCESS"
                for s in sources
            )
            for k in ("cafef", "vnexpress", "tuoitre", "thanhnien", "baomoi")
        ),
        "reconciliation_reports_pass": bool(reconciliation)
        and all(r["metrics"]["status"] == "PASS" for r in reconciliation),
        "no_crawler_or_article_tables_in_cdc": {
            (t["schemaname"], t["tablename"]) for t in publication
        }
        == {
            ("control_metadata", "news_sources"),
            ("control_metadata", "pipeline_configs"),
        },
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "sources": sources,
        "batches": batches,
        "cdc_publication_tables": publication,
        "reconciliation": reconciliation,
    }
    # A successful report is evidence only; Make's prerequisite tests and real
    # scheduler/monitoring smoke are also required for the release verdict.
    report["status"] = "PASS" if all(checks.values()) else "FAIL"
    Path("/app/local/phase8-acceptance.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n"
    )
    print(json.dumps({"status": report["status"], "checks": checks}))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
