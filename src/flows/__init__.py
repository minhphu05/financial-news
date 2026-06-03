"""Prefect flows that orchestrate the ViFinNER data pipeline.

Flows
-----
* :mod:`scrape_flow`        - daily CafeF scrape into MongoDB.
* :mod:`ingest_flow`        - cleaning + embedding pipeline.
* :mod:`full_pipeline_flow` - composed flow (scrape → chunk → embed).
* :mod:`eval_flow`          - RAG evaluation harness.
"""

from src.flows.eval_flow import rag_eval_flow
from src.flows.full_pipeline_flow import full_pipeline_flow
from src.flows.ingest_flow import ingest_flow
from src.flows.scrape_flow import scrape_flow

__all__ = [
    "full_pipeline_flow",
    "ingest_flow",
    "rag_eval_flow",
    "scrape_flow",
]
