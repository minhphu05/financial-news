"""Prefect flows that orchestrate the ViFinNER data pipeline.

Flows
-----
* :mod:`scrape_flow`           - daily CafeF scrape into MongoDB.
* :mod:`scrape_quality_flow`   - scrape with Pydantic quality gate.
* :mod:`ingest_flow`           - legacy cleaning + embedding pipeline.
* :mod:`medallion_flow`        - new bronze → silver → gold pipeline.
* :mod:`full_pipeline_flow`    - composed flow (scrape → ingest).
* :mod:`eval_flow`             - RAG evaluation harness.
"""

from src.rag.flows.eval_flow import rag_eval_flow
from src.rag.flows.full_pipeline_flow import full_pipeline_flow
from src.rag.flows.ingest_flow import ingest_flow
from src.rag.flows.medallion_flow import medallion_flow
from src.rag.flows.scrape_flow import scrape_flow
from src.rag.flows.scrape_quality_flow import scrape_quality_flow

__all__ = [
    "full_pipeline_flow",
    "ingest_flow",
    "medallion_flow",
    "rag_eval_flow",
    "scrape_flow",
    "scrape_quality_flow",
]
