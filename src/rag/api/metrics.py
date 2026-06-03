"""Prometheus metrics middleware for the FastAPI RAG API.

Exposes a ``/metrics`` endpoint that Prometheus scrapes directly, providing
real-time RAG serving metrics for Grafana Dashboard #4:

* End-to-end query latency (broken down into retrieval + LLM generation)
* Cache hit rate
* Request counts by endpoint and status
* User feedback aggregation
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

from src.rag.utils import get_logger

logger = get_logger(__name__)

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


if _HAS_PROMETHEUS:
    # --- Request-level metrics ---
    REQUEST_COUNT = Counter(
        "rag_api_requests_total",
        "Total HTTP requests to the RAG API",
        ["method", "endpoint", "status_code"],
    )
    REQUEST_LATENCY = Histogram(
        "rag_api_request_latency_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    )

    # --- RAG-specific metrics (Dashboard 4) ---
    CHAT_QUERY_LATENCY = Histogram(
        "rag_chat_query_latency_seconds",
        "End-to-end /chat query latency in seconds",
        ["model"],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0),
    )
    RETRIEVAL_LATENCY = Histogram(
        "rag_retrieval_latency_seconds",
        "Vector DB retrieval latency in seconds",
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
    )
    LLM_GENERATION_LATENCY = Histogram(
        "rag_llm_generation_latency_seconds",
        "LLM generation time in seconds",
        ["model"],
        buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0),
    )
    CACHE_HIT_TOTAL = Counter(
        "rag_cache_hit_total",
        "Total cache hits for RAG queries",
    )
    CACHE_MISS_TOTAL = Counter(
        "rag_cache_miss_total",
        "Total cache misses for RAG queries",
    )
    CACHE_HIT_RATE = Gauge(
        "rag_cache_hit_rate",
        "Current cache hit rate (rolling percentage)",
    )
    USER_FEEDBACK_POSITIVE = Counter(
        "rag_user_feedback_positive_total",
        "Total positive user feedback (thumbs up)",
    )
    USER_FEEDBACK_NEGATIVE = Counter(
        "rag_user_feedback_negative_total",
        "Total negative user feedback (thumbs down)",
    )
    ACTIVE_QUERIES = Gauge(
        "rag_active_queries",
        "Number of currently processing /chat queries",
    )


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware that records request count and latency per endpoint."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> StarletteResponse:
        if not _HAS_PROMETHEUS:
            return await call_next(request)

        # Skip metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = request.url.path

        start_time = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start_time

        status_code = str(response.status_code)
        REQUEST_COUNT.labels(method=method, endpoint=path, status_code=status_code).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=path).observe(duration)

        return response


def record_chat_metrics(
    *,
    model: str,
    total_latency_s: float,
    retrieval_latency_s: float = 0.0,
    llm_latency_s: float = 0.0,
    cache_hit: bool = False,
) -> None:
    """Record metrics for a single /chat query.

    Called from the AsyncRAGService after each query completes.

    Parameters
    ----------
    model : str
        LLM model used for generation.
    total_latency_s : float
        End-to-end query latency in seconds.
    retrieval_latency_s : float
        Time spent querying the vector DB.
    llm_latency_s : float
        Time spent on LLM generation.
    cache_hit : bool
        Whether the query was served from cache.
    """
    if not _HAS_PROMETHEUS:
        return

    CHAT_QUERY_LATENCY.labels(model=model).observe(total_latency_s)

    if retrieval_latency_s > 0:
        RETRIEVAL_LATENCY.observe(retrieval_latency_s)

    if llm_latency_s > 0:
        LLM_GENERATION_LATENCY.labels(model=model).observe(llm_latency_s)

    if cache_hit:
        CACHE_HIT_TOTAL.inc()
    else:
        CACHE_MISS_TOTAL.inc()


def record_user_feedback(positive: bool) -> None:
    """Record user feedback (thumbs up/down).

    Parameters
    ----------
    positive : bool
        True for positive feedback, False for negative.
    """
    if not _HAS_PROMETHEUS:
        return

    if positive:
        USER_FEEDBACK_POSITIVE.inc()
    else:
        USER_FEEDBACK_NEGATIVE.inc()


def setup_metrics(app: FastAPI) -> None:
    """Attach Prometheus middleware and /metrics endpoint to the FastAPI app.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    """
    if not _HAS_PROMETHEUS:
        logger.warning(
            "prometheus_client not installed; /metrics endpoint will not be available."
        )
        return

    app.add_middleware(PrometheusMiddleware)

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        """Expose Prometheus metrics for scraping."""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("Prometheus metrics enabled at /metrics endpoint.")
