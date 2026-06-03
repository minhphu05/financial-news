"""Prometheus metrics emitter for the ingestion pipeline.

Pushes batch job metrics to the Pushgateway after each ingestion run,
covering three stages:

1. **Preprocessing & Cleaning** — documents processed, dropped, latency.
2. **Chunking** — chunk size distribution, chunks per document, processing time.
3. **Embedding & Vectorization** — API latency, tokens embedded, DB writes,
   sync lag, failure rate.

These metrics power Grafana dashboards #2 (Preprocessing & Chunking) and
#3 (Embedding & Vectorization).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
from urllib.parse import urlparse
from typing import List, Optional

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)

_PUSHGATEWAY_URL_ENV = "PUSHGATEWAY_URL"
_DEFAULT_PUSHGATEWAY_URL = "pushgateway:9091"


@dataclass
class IngestionMetricDetails:
    """Optional extended metrics emitted by the ingestion pipeline.

    The core run counters stay in ``push_ingestion_metrics`` parameters,
    while this dataclass groups optional stage-level metrics to keep the
    function signature compact and maintainable.
    """

    dropped_articles: int = 0
    cleaning_duration_seconds: float = 0.0
    embedding_duration_seconds: float = 0.0
    chunk_sizes: List[int] = field(default_factory=list)
    chunks_per_doc_avg: float = 0.0
    tokens_embedded: int = 0
    embedding_api_latency_p95: float = 0.0
    embedding_api_latency_p99: float = 0.0
    embedding_failures: int = 0
    vector_db_write_rps: float = 0.0


def push_ingestion_metrics(
    cleaned_articles: int,
    embedded_articles: int,
    chunks_written: int,
    failed_count: int,
    duration_seconds: float,
    settings: Optional[Settings] = None,
    details: Optional[IngestionMetricDetails] = None,
) -> None:
    """Push ingestion pipeline metrics to Prometheus Pushgateway.

    Parameters
    ----------
    cleaned_articles : int
        Number of articles cleaned in this run.
    embedded_articles : int
        Number of articles embedded in this run.
    chunks_written : int
        Total chunks written to Qdrant.
    failed_count : int
        Number of articles that failed processing.
    duration_seconds : float
        Wall-clock duration of the pipeline run.
    settings : Optional[Settings]
        Settings override.
    details : Optional[IngestionMetricDetails]
        Optional stage-level metrics (chunk distribution, embedding latencies,
        queue/drop counters). Defaults to zeroed values when omitted.
    """
    try:
        from prometheus_client import CollectorRegistry, Gauge, Histogram, push_to_gateway

        registry = CollectorRegistry()

        details = details or IngestionMetricDetails()

        # --- Dashboard 2: Preprocessing & Chunking ---
        g_cleaned = Gauge(
            "ingestion_articles_cleaned_total",
            "Articles cleaned in this run",
            registry=registry,
        )
        g_dropped = Gauge(
            "ingestion_articles_dropped_total",
            "Articles dropped (too short, missing fields, noise)",
            registry=registry,
        )
        g_chunks = Gauge(
            "ingestion_chunks_written_total",
            "Chunks written to Qdrant in this run",
            registry=registry,
        )
        g_chunks_per_doc = Gauge(
            "ingestion_chunks_per_document_avg",
            "Average chunks generated per article",
            registry=registry,
        )
        g_cleaning_duration = Gauge(
            "ingestion_cleaning_duration_seconds",
            "Time spent on text cleaning/preprocessing",
            registry=registry,
        )
        g_processing_queue = Gauge(
            "ingestion_processing_queue_length",
            "Documents waiting to be processed",
            registry=registry,
        )

        # Chunk size distribution histogram
        g_chunk_size_min = Gauge(
            "ingestion_chunk_size_min_chars",
            "Minimum chunk size in characters",
            registry=registry,
        )
        g_chunk_size_max = Gauge(
            "ingestion_chunk_size_max_chars",
            "Maximum chunk size in characters",
            registry=registry,
        )
        g_chunk_size_avg = Gauge(
            "ingestion_chunk_size_avg_chars",
            "Average chunk size in characters",
            registry=registry,
        )
        g_chunk_size_p50 = Gauge(
            "ingestion_chunk_size_p50_chars",
            "Median (p50) chunk size in characters",
            registry=registry,
        )

        # --- Dashboard 3: Embedding & Vectorization ---
        g_embedded = Gauge(
            "ingestion_articles_embedded_total",
            "Articles embedded in this run",
            registry=registry,
        )
        g_tokens = Gauge(
            "ingestion_tokens_embedded_total",
            "Estimated total tokens sent to embedding API",
            registry=registry,
        )
        g_embed_duration = Gauge(
            "ingestion_embedding_duration_seconds",
            "Total time spent on embedding API calls",
            registry=registry,
        )
        g_embed_latency_p95 = Gauge(
            "ingestion_embedding_api_latency_p95_seconds",
            "95th percentile embedding API call latency",
            registry=registry,
        )
        g_embed_latency_p99 = Gauge(
            "ingestion_embedding_api_latency_p99_seconds",
            "99th percentile embedding API call latency",
            registry=registry,
        )
        g_embed_failures = Gauge(
            "ingestion_embedding_failures_total",
            "Number of embedding API failures",
            registry=registry,
        )
        g_vector_write_rps = Gauge(
            "ingestion_vector_db_write_rps",
            "Qdrant write operations per second",
            registry=registry,
        )
        g_sync_lag = Gauge(
            "ingestion_vector_db_sync_lag_seconds",
            "Lag from scrape completion to vectors available for search",
            registry=registry,
        )
        g_failed = Gauge(
            "ingestion_articles_failed_total",
            "Articles that failed processing",
            registry=registry,
        )
        g_duration = Gauge(
            "ingestion_run_duration_seconds",
            "Duration of the ingestion run in seconds",
            registry=registry,
        )
        g_last_run_ts = Gauge(
            "ingestion_last_run_timestamp_seconds",
            "Unix timestamp of the last ingestion run",
            registry=registry,
        )

        # Set values
        g_cleaned.set(cleaned_articles)
        g_dropped.set(details.dropped_articles)
        g_chunks.set(chunks_written)
        g_chunks_per_doc.set(details.chunks_per_doc_avg)
        g_cleaning_duration.set(details.cleaning_duration_seconds)
        g_embedded.set(embedded_articles)
        g_tokens.set(details.tokens_embedded)
        g_embed_duration.set(details.embedding_duration_seconds)
        g_embed_latency_p95.set(details.embedding_api_latency_p95)
        g_embed_latency_p99.set(details.embedding_api_latency_p99)
        g_embed_failures.set(details.embedding_failures)
        g_vector_write_rps.set(details.vector_db_write_rps)
        g_sync_lag.set(duration_seconds)  # Total pipeline duration as sync lag proxy
        g_failed.set(failed_count)
        g_duration.set(duration_seconds)
        g_last_run_ts.set(time.time())

        # Chunk size distribution
        if details.chunk_sizes:
            sorted_sizes = sorted(details.chunk_sizes)
            g_chunk_size_min.set(sorted_sizes[0])
            g_chunk_size_max.set(sorted_sizes[-1])
            g_chunk_size_avg.set(sum(sorted_sizes) / len(sorted_sizes))
            p50_idx = len(sorted_sizes) // 2
            g_chunk_size_p50.set(sorted_sizes[p50_idx])

        # Pending queue from MongoDB
        cfg = settings or get_settings()
        try:
            from src.rag.databases import MongoRepository

            with MongoRepository(settings=cfg) as mongo:
                g_processing_queue.set(
                    mongo.count_raw_not_cleaned() + mongo.count_clean_not_embedded()
                )
        except Exception:
            g_processing_queue.set(0)

        pushgateway_url = os.environ.get(_PUSHGATEWAY_URL_ENV, _DEFAULT_PUSHGATEWAY_URL)
        candidates = [pushgateway_url]
        parsed = urlparse(
            f"http://{pushgateway_url}" if "://" not in pushgateway_url else pushgateway_url
        )
        if parsed.hostname in {"pushgateway", "financial-pushgateway"}:
            localhost_gateway = f"localhost:{parsed.port or 9091}"
            if localhost_gateway not in candidates:
                candidates.append(localhost_gateway)

        pushed = False
        for target in candidates:
            try:
                push_to_gateway(target, job="ingestion", registry=registry)
                pushed = True
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to push ingestion metrics to %s: %s", target, exc)

        if pushed:
            logger.info(
                "Pushed ingestion metrics: cleaned=%d, dropped=%d, embedded=%d, "
                "chunks=%d, failed=%d, tokens=%d, duration=%.1fs",
                cleaned_articles,
                details.dropped_articles,
                embedded_articles,
                chunks_written,
                failed_count,
                details.tokens_embedded,
                duration_seconds,
            )
    except ImportError:
        logger.warning("prometheus_client not installed; skipping metrics push.")
    except Exception as exc:
        logger.warning("Failed to push ingestion metrics: %s", exc)
