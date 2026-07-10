"""Prometheus metrics for the scraper pipeline.

Pushes run-level metrics to the Pushgateway after each scrape completes,
so Grafana can display scrape duration, article counts, error rates,
data volume, and per-source breakdowns.

The module gracefully handles the absence of ``prometheus_client`` by logging
a warning and skipping the push — this keeps the scraper usable in minimal
environments without the monitoring stack.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse
import time
from typing import Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


def push_scraper_metrics(
    *,
    articles_found: int,
    articles_new: int,
    articles_skipped: int,
    pages_crawled: int,
    errors_count: int,
    duration_seconds: float,
    source: str = "cafef",
    data_volume_bytes: int = 0,
    error_breakdown: Optional[Dict[str, int]] = None,
    run_active: int = 0,
    keywords_total: Optional[int] = None,
    keywords_processed: Optional[int] = None,
    current_ticker: Optional[str] = None,
    current_keyword: Optional[str] = None,
    last_keyword_status: Optional[str] = None,
    last_keyword_duration_seconds: Optional[float] = None,
    last_keyword_articles_found: Optional[int] = None,
    last_keyword_articles_persisted: Optional[int] = None,
    last_keyword_articles_skipped: Optional[int] = None,
    last_keyword_pages_crawled: Optional[int] = None,
    pushgateway_url: Optional[str] = None,
) -> None:
    """Push scraper run metrics to Prometheus Pushgateway.

    Parameters
    ----------
    articles_found : int
        Total articles discovered on listing pages.
    articles_new : int
        Articles actually persisted (new).
    articles_skipped : int
        Articles skipped (already existed).
    pages_crawled : int
        Number of listing pages fetched.
    errors_count : int
        Non-fatal errors during the run.
    duration_seconds : float
        Total scrape run duration in seconds.
    source : str
        Data source identifier (e.g. ``'cafef'``).
    data_volume_bytes : int
        Raw data volume ingested in bytes.
    error_breakdown : Optional[Dict[str, int]]
        Error counts by type (e.g. ``{"http_429": 2, "timeout": 1}``).
    pushgateway_url : Optional[str]
        Override the Pushgateway address. Defaults to the
        ``PUSHGATEWAY_URL`` env var or ``pushgateway:9091``.
    """
    if not _HAS_PROMETHEUS:
        logger.warning(
            "prometheus_client not installed; scraper metrics not pushed."
        )
        return

    gateway = pushgateway_url or os.environ.get("PUSHGATEWAY_URL", "pushgateway:9091")

    # Allow local CLI runs to work without extra env vars: if Docker service
    # DNS is not resolvable from host, retry against localhost:<same-port>.
    candidates = [gateway]
    parsed = urlparse(f"http://{gateway}" if "://" not in gateway else gateway)
    if parsed.hostname in {"pushgateway", "financial-pushgateway"}:
        localhost_gateway = f"localhost:{parsed.port or 9091}"
        if localhost_gateway not in candidates:
            candidates.append(localhost_gateway)

    registry = CollectorRegistry()
    labels = ["source"]

    g_found = Gauge(
        "scraper_articles_found_total",
        "Total articles found on listing pages",
        labels,
        registry=registry,
    )
    g_new = Gauge(
        "scraper_articles_persisted_total",
        "Articles persisted (new) in the last run",
        labels,
        registry=registry,
    )
    g_skipped = Gauge(
        "scraper_articles_skipped_total",
        "Articles skipped (duplicates) in the last run",
        labels,
        registry=registry,
    )
    g_pages = Gauge(
        "scraper_pages_crawled_total",
        "Listing pages crawled in the last run",
        labels,
        registry=registry,
    )
    g_errors = Gauge(
        "scraper_errors_total",
        "Non-fatal errors during the last run",
        labels,
        registry=registry,
    )
    g_duration = Gauge(
        "scraper_run_duration_seconds",
        "Duration of the last scrape run in seconds",
        labels,
        registry=registry,
    )
    g_volume = Gauge(
        "scraper_data_volume_bytes",
        "Raw data volume ingested in bytes during the last run",
        labels,
        registry=registry,
    )
    g_job_success = Gauge(
        "scraper_job_success",
        "1 if last scrape job succeeded, 0 if failed",
        labels,
        registry=registry,
    )
    g_last_run_ts = Gauge(
        "scraper_last_run_timestamp_seconds",
        "Unix timestamp of the last scrape run completion",
        labels,
        registry=registry,
    )
    g_run_active = Gauge(
        "scraper_run_active",
        "1 while a scrape run is active, 0 after completion",
        labels,
        registry=registry,
    )

    if keywords_total is not None:
        g_keywords_total = Gauge(
            "scraper_keywords_total",
            "Total keywords planned for the active scrape run",
            labels,
            registry=registry,
        )
        g_keywords_total.labels(source=source).set(keywords_total)

    if keywords_processed is not None:
        g_keywords_processed = Gauge(
            "scraper_keywords_processed_total",
            "Keywords processed so far in the active scrape run",
            labels,
            registry=registry,
        )
        g_keywords_remaining = Gauge(
            "scraper_keywords_remaining",
            "Keywords remaining in the active scrape run",
            labels,
            registry=registry,
        )
        g_keywords_processed.labels(source=source).set(keywords_processed)
        if keywords_total is not None:
            g_keywords_remaining.labels(source=source).set(
                max(0, keywords_total - keywords_processed)
            )

    if current_ticker and current_keyword:
        g_current_keyword = Gauge(
            "scraper_current_keyword_info",
            "Current or most recently processed keyword labeled by ticker and keyword",
            ["source", "ticker", "keyword"],
            registry=registry,
        )
        g_current_keyword.labels(
            source=source,
            ticker=current_ticker,
            keyword=current_keyword,
        ).set(1)

    if last_keyword_status is not None:
        keyword_labels = ["source", "ticker", "keyword", "status"]
        ticker = current_ticker or "unknown"
        keyword = current_keyword or "unknown"
        status = last_keyword_status or "unknown"
        g_last_keyword_ts = Gauge(
            "scraper_keyword_last_processed_timestamp_seconds",
            "Unix timestamp when the last keyword finished processing",
            keyword_labels,
            registry=registry,
        )
        g_last_keyword_ts.labels(
            source=source,
            ticker=ticker,
            keyword=keyword,
            status=status,
        ).set(time.time())
        if last_keyword_duration_seconds is not None:
            g_last_keyword_duration = Gauge(
                "scraper_keyword_duration_seconds",
                "Duration of the most recently processed keyword",
                keyword_labels,
                registry=registry,
            )
            g_last_keyword_duration.labels(
                source=source,
                ticker=ticker,
                keyword=keyword,
                status=status,
            ).set(last_keyword_duration_seconds)
        keyword_value_specs = [
            (
                "scraper_keyword_articles_found_total",
                "Articles found for the most recently processed keyword",
                last_keyword_articles_found,
            ),
            (
                "scraper_keyword_articles_persisted_total",
                "Articles persisted for the most recently processed keyword",
                last_keyword_articles_persisted,
            ),
            (
                "scraper_keyword_articles_skipped_total",
                "Articles skipped for the most recently processed keyword",
                last_keyword_articles_skipped,
            ),
            (
                "scraper_keyword_pages_crawled_total",
                "Pages crawled for the most recently processed keyword",
                last_keyword_pages_crawled,
            ),
        ]
        for metric_name, description, value in keyword_value_specs:
            if value is None:
                continue
            gauge = Gauge(metric_name, description, keyword_labels, registry=registry)
            gauge.labels(
                source=source,
                ticker=ticker,
                keyword=keyword,
                status=status,
            ).set(value)

    # Set main metrics
    g_found.labels(source=source).set(articles_found)
    g_new.labels(source=source).set(articles_new)
    g_skipped.labels(source=source).set(articles_skipped)
    g_pages.labels(source=source).set(pages_crawled)
    g_errors.labels(source=source).set(errors_count)
    g_duration.labels(source=source).set(duration_seconds)
    g_volume.labels(source=source).set(data_volume_bytes)
    g_job_success.labels(source=source).set(1 if errors_count == 0 else 0)
    g_last_run_ts.labels(source=source).set(time.time())
    g_run_active.labels(source=source).set(run_active)

    # Error breakdown by type (http_429, timeout, duplicate, parse_error, etc.)
    if error_breakdown:
        g_err_type = Gauge(
            "scraper_errors_by_type",
            "Errors broken down by type",
            ["source", "error_type"],
            registry=registry,
        )
        for err_type, count in error_breakdown.items():
            g_err_type.labels(source=source, error_type=err_type).set(count)

    for target in candidates:
        try:
            push_to_gateway(target, job="scraper", registry=registry)
            logger.info(
                "Scraper metrics pushed to Pushgateway (%s): "
                "found=%d, new=%d, skipped=%d, pages=%d, errors=%d, "
                "duration=%.1fs, volume=%d bytes",
                target,
                articles_found,
                articles_new,
                articles_skipped,
                pages_crawled,
                errors_count,
                duration_seconds,
                data_volume_bytes,
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to push scraper metrics to %s: %s", target, exc)
