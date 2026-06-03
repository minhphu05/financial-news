"""Structured JSON event logger for the ingestion pipeline.

Emits one JSON line per pipeline event (scrape, chunk, embed, upsert) to
a rotating log file under ``logs/pipeline/``.  Fluent Bit tails these files
and forwards them to Loki so Grafana can plot per-stage metrics.

Each event has a ``stage`` field that acts as the primary Loki label:
  - ``scrape``    — articles found / persisted by the scraper.
  - ``clean``     — article cleaning result.
  - ``chunk``     — number of chunks produced and time taken.
  - ``embed``     — embedding model, batch count, total time, token estimate.
  - ``upsert``    — Qdrant upsert result.
  - ``pipeline``  — end-of-run summary for the whole ingestion run.

Usage
-----
Instantiate once per pipeline run::

    from src.rag.ingestion.pipeline_logger import PipelineRunLogger

    run_log = PipelineRunLogger(run_id="my-run")
    run_log.scrape(articles_found=20, articles_persisted=18)
    run_log.chunk(link="https://...", num_chunks=8, duration_s=0.03)
    run_log.embed(model="voyage-4-lite", num_chunks=8, duration_s=62.1, est_tokens=3200)
    run_log.pipeline_summary(cleaned=18, embedded=18, chunks=144, failed=0, duration_s=630)
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


class PipelineRunLogger:
    """Write one JSON line per pipeline event to a file tailed by Fluent Bit.

    Parameters
    ----------
    run_id : str
        Unique identifier for this pipeline run (e.g. a UUID or ISO timestamp).
    log_dir : str
        Directory where log files are written.  Each stage gets its own file
        so Fluent Bit can tag them separately and Loki labels stay clean.
    """

    def __init__(
        self,
        run_id: str,
        log_dir: str = _DEFAULT_LOG_DIR,
    ) -> None:
        self._run_id = run_id
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # One file per stage so Fluent Bit can set separate tags / labels.
        self._files: Dict[str, Path] = {
            stage: self._log_dir / f"{stage}.json.log"
            for stage in ("scrape", "clean", "chunk", "embed", "upsert", "pipeline")
        }

    # ------------------------------------------------------------------
    # Public event methods
    # ------------------------------------------------------------------
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
            New articles actually written to MongoDB.
        duration_s : float
            Wall-clock time of the scrape stage.
        source : str
            News source name (e.g. ``"cafef"``).
        keyword : Optional[str]
            Keyword that triggered the scrape, if any.
        """
        self._write("scrape", {
            "articles_found": articles_found,
            "articles_persisted": articles_persisted,
            "duration_s": round(duration_s, 3),
            "source": source,
            "keyword": keyword,
        })

    def clean(
        self,
        *,
        link: str,
        success: bool,
        skipped_empty: bool = False,
        duration_s: float = 0.0,
    ) -> None:
        """Log the cleaning result for a single article.

        Parameters
        ----------
        link : str
            Article URL.
        success : bool
            Whether cleaning produced a non-empty document.
        skipped_empty : bool
            ``True`` when the article body was empty after cleaning.
        duration_s : float
            Time spent cleaning this article.
        """
        self._write("clean", {
            "link": link,
            "success": success,
            "skipped_empty": skipped_empty,
            "duration_s": round(duration_s, 4),
        })

    def chunk(
        self,
        *,
        link: str,
        num_chunks: int,
        total_chars: int,
        chunk_size: int,
        chunk_overlap: int,
        duration_s: float,
    ) -> None:
        """Log the chunking result for a single article.

        Parameters
        ----------
        link : str
            Article URL.
        num_chunks : int
            Number of chunks produced.
        total_chars : int
            Total character count of the source text.
        chunk_size : int
            Configured target chunk size.
        chunk_overlap : int
            Configured chunk overlap.
        duration_s : float
            Wall-clock time to chunk this article.
        """
        self._write("chunk", {
            "link": link,
            "num_chunks": num_chunks,
            "total_chars": total_chars,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "avg_chunk_chars": round(total_chars / num_chunks, 1) if num_chunks else 0,
            "duration_s": round(duration_s, 4),
        })

    def embed(
        self,
        *,
        link: str,
        model: str,
        num_chunks: int,
        num_batches: int,
        est_tokens: int,
        duration_s: float,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Log the embedding result for a single article.

        Parameters
        ----------
        link : str
            Article URL.
        model : str
            Voyage AI model name (e.g. ``"voyage-4-lite"``).
        num_chunks : int
            Number of chunk vectors produced.
        num_batches : int
            Number of HTTP requests sent to the embedding API.
        est_tokens : int
            Estimated token count for this article's chunks.
        duration_s : float
            Wall-clock time including rate-limit waits.
        success : bool
            ``False`` if any batch ultimately failed.
        error : Optional[str]
            Error message if ``success`` is ``False``.
        """
        self._write("embed", {
            "link": link,
            "model": model,
            "num_chunks": num_chunks,
            "num_batches": num_batches,
            "est_tokens": est_tokens,
            "duration_s": round(duration_s, 3),
            "success": success,
            "error": error,
        })

    def upsert(
        self,
        *,
        link: str,
        num_points: int,
        collection: str,
        duration_s: float,
        success: bool = True,
    ) -> None:
        """Log the Qdrant upsert result for a single article.

        Parameters
        ----------
        link : str
            Article URL.
        num_points : int
            Number of vector points upserted.
        collection : str
            Qdrant collection name.
        duration_s : float
            Wall-clock time for the upsert call.
        success : bool
            ``False`` if the upsert raised an exception.
        """
        self._write("upsert", {
            "link": link,
            "collection": collection,
            "num_points": num_points,
            "duration_s": round(duration_s, 4),
            "success": success,
        })

    def pipeline_summary(
        self,
        *,
        cleaned: int,
        embedded: int,
        chunks: int,
        failed: int,
        duration_s: float,
        pending_clean: int = 0,
        pending_embed: int = 0,
    ) -> None:
        """Log the end-of-run summary for the whole pipeline.

        Parameters
        ----------
        cleaned : int
            Articles cleaned this run.
        embedded : int
            Articles embedded this run.
        chunks : int
            Total chunks written to Qdrant.
        failed : int
            Articles that failed at any stage.
        duration_s : float
            Total wall-clock time for the run.
        pending_clean : int
            Backlog articles still waiting to be cleaned.
        pending_embed : int
            Backlog articles still waiting to be embedded.
        """
        self._write("pipeline", {
            "articles_cleaned": cleaned,
            "articles_embedded": embedded,
            "chunks_written": chunks,
            "articles_failed": failed,
            "pending_clean": pending_clean,
            "pending_embed": pending_embed,
            "duration_s": round(duration_s, 1),
            "throughput_articles_per_min": round(
                (cleaned + embedded) / max(duration_s / 60, 0.001), 2
            ),
        })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _write(self, stage: str, payload: Dict[str, Any]) -> None:
        """Append a JSON line to the stage-specific log file.

        Parameters
        ----------
        stage : str
            Pipeline stage name (used as the file key and Loki label).
        payload : dict
            Stage-specific fields to include alongside common metadata.
        """
        event: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": "INFO",
            "stage": stage,
            "run_id": self._run_id,
            **payload,
        }
        line = json.dumps(event, ensure_ascii=False, default=str)
        log_file = self._files[stage]
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
