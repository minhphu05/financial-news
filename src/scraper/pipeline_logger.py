"""Structured JSON event logger for the scraper pipeline.

Self-contained logger that emits one JSON line per scrape event to
``logs/pipeline/scrape.json.log``. Fluent Bit tails this file (tag
``pipeline.scrape``) and forwards it to Loki so Grafana can plot per-run
scrape metrics.

This module intentionally lives inside ``src.scraper`` so the scraper /
flows layer has **no dependency on the RAG package**. It mirrors the JSON
schema previously produced by ``src.rag.ingestion.pipeline_logger`` for the
``scrape`` stage, keeping the existing Fluent Bit -> Loki -> Grafana pipeline
working unchanged.

Usage
-----
Instantiate once per scrape run::

    from src.scraper.pipeline_logger import ScrapeRunLogger

    run_log = ScrapeRunLogger(run_id="my-run")
    run_log.scrape(articles_found=20, articles_persisted=18, source="cafef")
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Log directory is resolved from the environment so it works both on the
# host and inside Docker containers.
_DEFAULT_LOG_DIR = os.getenv("PIPELINE_LOG_DIR", "logs/pipeline")


class ScrapeRunLogger:
    """Write one JSON line per scrape event to a file tailed by Fluent Bit.

    Parameters
    ----------
    run_id : str
        Unique identifier for this scrape run (e.g. a UUID or ISO timestamp).
    log_dir : str
        Directory where log files are written.
    """

    def __init__(self, run_id: str, log_dir: str = _DEFAULT_LOG_DIR) -> None:
        self._run_id = run_id
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._scrape_file = self._log_dir / "scrape.json.log"

    def scrape(
        self,
        *,
        articles_found: int,
        articles_persisted: int,
        duration_s: float = 0.0,
        source: str = "cafef",
        keyword: Optional[str] = None,
    ) -> None:
        """Log a scrape-stage completion event.

        Parameters
        ----------
        articles_found : int
            Total article links discovered.
        articles_persisted : int
            New articles actually persisted.
        duration_s : float
            Wall-clock time of the scrape stage.
        source : str
            News source name (e.g. ``"cafef"``).
        keyword : Optional[str]
            Keyword that triggered the scrape, if any.
        """
        self._write(
            "scrape",
            {
                "articles_found": articles_found,
                "articles_persisted": articles_persisted,
                "duration_s": round(duration_s, 3),
                "source": source,
                "keyword": keyword,
            },
        )

    def _write(self, stage: str, payload: Dict[str, Any]) -> None:
        """Append a JSON line to the stage-specific log file."""
        event: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": "INFO",
            "stage": stage,
            "run_id": self._run_id,
            **payload,
        }
        line = json.dumps(event, ensure_ascii=False, default=str)
        with self._scrape_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
