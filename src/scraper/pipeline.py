"""
End-to-end orchestration for the scraper.

Responsibilities:

* Locate and load the *single* ``.xlsx`` file in ``RAW_INPUT_DIR``.
* Parse the ``Keywords`` column for every row.
* For each ``(ticker, keyword)`` pair, delegate to
  :func:`src.scraper.page_scraper.scrape_keyword`.
* Track the run in ``scrape_runs`` table with aggregate stats.
* Push metrics to Prometheus Pushgateway for Grafana monitoring.
* Aggregate run-level statistics for the log file summary.

Handles ``KeyboardInterrupt`` (Ctrl+C) gracefully — the scrape run is
always finalized in PostgreSQL regardless of how the pipeline stops.
"""
from __future__ import annotations

import ast
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from src.scraper.config import ScraperSettings
from src.scraper.http_client import HttpClient
from src.scraper.metrics import push_scraper_metrics
from src.scraper.page_scraper import KeywordContext, scrape_keyword
from src.scraper.storage import StorageManager
from src.utils.logger import get_logger, set_log_context, clear_log_context

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Run-level aggregates
# ---------------------------------------------------------------------------
@dataclass
class RunSummary:
    """Counters captured during one full scraper run."""

    tickers_processed: int = 0
    keywords_processed: int = 0
    articles_found: int = 0
    articles_persisted: int = 0
    articles_skipped: int = 0
    pages_crawled: int = 0
    errors_count: int = 0
    failed_keywords: List[str] = field(default_factory=list)
    persisted_ids: List[str] = field(default_factory=list)
    """news_id of every article newly persisted during this run."""

    def render(self) -> str:
        """Return a human-readable multi-line summary."""
        return (
            "Run summary\n"
            f"  tickers processed   : {self.tickers_processed}\n"
            f"  keywords processed  : {self.keywords_processed}\n"
            f"  articles found      : {self.articles_found}\n"
            f"  articles persisted  : {self.articles_persisted}\n"
            f"  articles skipped    : {self.articles_skipped}\n"
            f"  pages crawled       : {self.pages_crawled}\n"
            f"  errors              : {self.errors_count}\n"
            f"  failed keywords     : {len(self.failed_keywords)}"
            + ("" if not self.failed_keywords else f" -> {self.failed_keywords}")
        )


# ---------------------------------------------------------------------------
# Excel loading
# ---------------------------------------------------------------------------
_KEYWORDS_COLUMN = "Keywords"
_TICKER_COLUMN = "ticket_symbol"
_COMPANY_COLUMN = "company_name_vi"


def find_input_excel(raw_dir: Path) -> Path:
    """
    Locate the single ``.xlsx`` file inside ``raw_dir``.

    The project guarantees exactly one Excel file lives there. We
    explicitly fail loud if that invariant is broken so the user notices
    immediately rather than scraping against the wrong file.
    """
    if not raw_dir.exists():
        raise FileNotFoundError(f"RAW_INPUT_DIR does not exist: {raw_dir}")
    candidates = sorted(raw_dir.glob("*.xlsx"))
    if len(candidates) == 0:
        raise FileNotFoundError(f"No .xlsx file found in {raw_dir}")
    if len(candidates) > 1:
        raise RuntimeError(
            f"Expected exactly one .xlsx in {raw_dir}, found {len(candidates)}: "
            f"{[p.name for p in candidates]}"
        )
    return candidates[0]


def _coerce_keywords(raw: object) -> List[str]:
    """
    Normalize the value stored in the ``Keywords`` column into a list.

    The column may contain either a real Python list (already) or its
    string repr (``'["A", "B"]'``). Anything else returns an empty list.
    """
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except (ValueError, SyntaxError):
            pass
    return []


def load_keyword_table(xlsx_path: Path) -> pd.DataFrame:
    """
    Load and normalize the keyword table from an Excel file.

    Returns a DataFrame whose ``Keywords`` column is guaranteed to contain
    Python ``list[str]`` values.
    """
    df = pd.read_excel(xlsx_path, header=0)
    missing = {_KEYWORDS_COLUMN, _TICKER_COLUMN, _COMPANY_COLUMN} - set(df.columns)
    if missing:
        raise ValueError(
            f"{xlsx_path.name} is missing required columns: {sorted(missing)}"
        )
    df[_KEYWORDS_COLUMN] = df[_KEYWORDS_COLUMN].apply(_coerce_keywords)
    return df


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_pipeline(
    settings: ScraperSettings,
    *,
    only_tickers: Iterable[str] | None = None,
    triggered_by: str = "manual",
) -> RunSummary:
    """
    Execute the full scrape: Excel -> keywords -> articles -> stores.

    Creates a ``scrape_runs`` record on start and finalizes it on completion
    (or failure). Uses incremental early-stop per keyword so daily runs
    finish quickly when there are few new articles.

    Args:
        settings: Resolved scraper settings.
        only_tickers: Optional whitelist of ticker symbols to process.
            Useful for smoke-testing a single symbol without scraping the
            entire VN30 universe.
        triggered_by: How this run was initiated ('manual', 'cron', 'prefect').

    Returns:
        Aggregated :class:`RunSummary` for logging / monitoring.
    """
    xlsx_path = find_input_excel(settings.raw_input_dir)
    logger.info(f"Loading keyword table: {xlsx_path}")
    df = load_keyword_table(xlsx_path)

    tickers_filter: str | None = None
    if only_tickers is not None:
        whitelist = {t.upper() for t in only_tickers}
        df = df[df[_TICKER_COLUMN].str.upper().isin(whitelist)]
        tickers_filter = ",".join(sorted(whitelist))
        logger.info(f"Filtered to {len(df)} ticker(s): {sorted(whitelist)}")

    summary = RunSummary()
    run_id: int | None = None
    start_time = time.monotonic()

    with HttpClient(settings) as client, StorageManager(settings) as storage:
        # Register this run in the tracking table
        run_id = storage.create_scrape_run(
            source=settings.source_name,
            triggered_by=triggered_by,
            tickers_filter=tickers_filter,
        )
        set_log_context(run_id=run_id, source_name=settings.source_name)
        logger.info(f"Scrape run #{run_id} started.")

        final_status = "completed"
        error_msg: str | None = None

        try:
            for _, row in df.iterrows():
                ticker = str(row[_TICKER_COLUMN])
                company = str(row[_COMPANY_COLUMN])
                keywords: List[str] = row[_KEYWORDS_COLUMN]

                if not keywords:
                    logger.warning(f"No keywords for ticker {ticker}; skipping.")
                    continue

                summary.tickers_processed += 1
                logger.info(f"[{ticker}] {company} - {len(keywords)} keyword(s)")

                for keyword in keywords:
                    try:
                        result = scrape_keyword(
                            KeywordContext(
                                keyword=keyword,
                                ticker_symbol=ticker,
                                company_name=company,
                            ),
                            settings,
                            client,
                            storage,
                        )
                        summary.articles_persisted += result["persisted"]
                        summary.persisted_ids.extend(result.get("persisted_ids", []))
                        summary.articles_skipped += result["skipped"]
                        summary.articles_found += result["found"]
                        summary.pages_crawled += result["pages"]
                        summary.keywords_processed += 1
                    except Exception as exc:
                        logger.exception(
                            f"[{ticker}] keyword '{keyword}' failed: {exc}"
                        )
                        summary.failed_keywords.append(f"{ticker}:{keyword}")
                        summary.errors_count += 1

        except KeyboardInterrupt:
            logger.warning("Pipeline interrupted by user (Ctrl+C).")
            final_status = "aborted"
            error_msg = "Interrupted by user (KeyboardInterrupt)"
        except Exception as exc:
            logger.exception(f"Pipeline-level failure: {exc}")
            final_status = "failed"
            error_msg = str(exc)
            summary.errors_count += 1

        # Always finalize the run record, even on abort/crash
        duration = time.monotonic() - start_time
        storage.finish_scrape_run(
            run_id,
            articles_found=summary.articles_found,
            articles_new=summary.articles_persisted,
            articles_skipped=summary.articles_skipped,
            pages_crawled=summary.pages_crawled,
            errors_count=summary.errors_count,
            duration_seconds=duration,
            status=final_status,
            error_message=error_msg or (
                f"Failed keywords: {summary.failed_keywords}"
                if summary.failed_keywords
                else None
            ),
        )

        # Push metrics to Prometheus Pushgateway
        push_scraper_metrics(
            articles_found=summary.articles_found,
            articles_new=summary.articles_persisted,
            articles_skipped=summary.articles_skipped,
            pages_crawled=summary.pages_crawled,
            errors_count=summary.errors_count,
            duration_seconds=duration,
            source=settings.source_name,
        )

    clear_log_context()
    logger.success(summary.render())
    return summary
