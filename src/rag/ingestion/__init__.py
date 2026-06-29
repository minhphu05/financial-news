"""Ingestion pipeline: scrape → clean → chunk → embed → load into Qdrant."""

__all__ = [
    "DailyCafefScraper",
    "TextCleaner",
    "TextChunker",
    "VoyageAIEmbedder",
]


_INGESTION_EXPORTS = {
    "DailyCafefScraper": ("src.rag.ingestion.daily_scraper", "DailyCafefScraper"),
    "TextCleaner": ("src.rag.ingestion.cleaner", "TextCleaner"),
    "TextChunker": ("src.rag.ingestion.chunker", "TextChunker"),
    "VoyageAIEmbedder": ("src.rag.ingestion.embedder", "VoyageAIEmbedder"),
}


def __getattr__(name: str):
    """Lazy import for modules with heavy dependencies."""
    if name in _INGESTION_EXPORTS:
        module_name, attr_name = _INGESTION_EXPORTS[name]
        module = __import__(module_name, fromlist=[attr_name])
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
