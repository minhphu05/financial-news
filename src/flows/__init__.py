# src/flows/__init__.py
"""
Active Prefect flows for the local Financial News scraper.

Inactive RAG/ingestion/evaluation flows kept for later reuse live in
:mod:`src.flows.future_use`.
"""

from importlib import import_module


_FLOW_EXPORTS = {
    "market_data_flow": "src.flows.standard_scraper_flow",
    "scrape_flow": "src.flows.scrape_flow",
    "standard_scraper_flow": "src.flows.standard_scraper_flow",
}


def __getattr__(name: str):
    if name not in _FLOW_EXPORTS:
        raise AttributeError(name)
    module = import_module(_FLOW_EXPORTS[name])
    value = getattr(module, name)
    globals()[name] = value
    return value

__all__ = [
    "market_data_flow",
    "scrape_flow",
    "standard_scraper_flow",
]
