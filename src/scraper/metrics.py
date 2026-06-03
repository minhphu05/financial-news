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
