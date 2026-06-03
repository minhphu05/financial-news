"""Ingestion pipeline: scrape → clean → chunk → embed → load into Qdrant."""

from src.rag.ingestion.cleaner import TextCleaner
from src.rag.ingestion.chunker import TextChunker
from src.rag.ingestion.embedder import VoyageAIEmbedder

__all__ = [
    "DailyCafefScraper",
    "TextCleaner",
    "TextChunker",
    "VoyageAIEmbedder",
]


def __getattr__(name: str):
    """Lazy import for modules with heavy dependencies (e.g. bs4)."""
    if name == "DailyCafefScraper":
        from src.rag.ingestion.daily_scraper import DailyCafefScraper
        return DailyCafefScraper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
