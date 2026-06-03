"""Clean pipeline: scrape → detect new → chunk → embed → vector DB.

This package provides the core pipeline stages as standalone, testable
functions. The data flow is explicit — news_ids from the scrape step are
passed directly to the ingestion step, avoiding implicit MongoDB
set-difference queries.

Usage
-----
::

    from src.pipeline.core import run_ingestion

    report = run_ingestion(mongo, qdrant, embedder, news_ids, settings)
"""

from src.pipeline.core import run_ingestion

__all__ = ["run_ingestion"]
