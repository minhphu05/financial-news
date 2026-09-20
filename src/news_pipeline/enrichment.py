"""Optional NLP boundary; no-op mode never fabricates model output."""

from typing import Protocol


class ArticleEnricher(Protocol):
    def enrich(self, article: dict) -> dict: ...


class NoOpEnricher:
    def enrich(self, article: dict) -> dict:
        return {
            **article,
            "entities": None,
            "enrichment_status": "unavailable",
            "enricher_version": None,
        }
