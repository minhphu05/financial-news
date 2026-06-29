"""Prefect flows that orchestrate the ViFinNER data pipeline.

Flows
-----
* :mod:`scrape_flow`        - daily CafeF scrape into MongoDB.
* :mod:`ingest_flow`        - cleaning + embedding pipeline.
* :mod:`full_pipeline_flow` - composed flow (scrape → chunk → embed).
* :mod:`eval_flow`          - RAG evaluation harness.
"""

from importlib import import_module


_FLOW_EXPORTS = {
    "full_pipeline_flow": "src.flows.full_pipeline_flow",
    "ingest_flow": "src.flows.ingest_flow",
    "rag_eval_flow": "src.flows.eval_flow",
    "scrape_flow": "src.flows.scrape_flow",
}


def __getattr__(name: str):
    if name not in _FLOW_EXPORTS:
        raise AttributeError(name)
    module = import_module(_FLOW_EXPORTS[name])
    value = getattr(module, name)
    globals()[name] = value
    return value

__all__ = [
    "full_pipeline_flow",
    "ingest_flow",
    "rag_eval_flow",
    "scrape_flow",
]
