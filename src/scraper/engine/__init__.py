"""
Site-agnostic crawl engine.

Holds everything that does *not* depend on a specific website or storage
backend: the parser contract, value objects, the source registry, the
per-keyword crawl loop, and the run orchestrator.
"""
from src.scraper.engine.base_parser import BaseParser
from src.scraper.engine.pipeline import RunSummary, run_pipeline
from src.scraper.engine.registry import (
    available_sources,
    get_parser,
    resolve_sources,
)
from src.scraper.engine.types import (
    ArticleDetail,
    ArticleRecord,
    ContentBlock,
    KeywordRecord,
    KeywordResult,
    ListingEntry,
)

__all__ = [
    "BaseParser",
    "RunSummary",
    "run_pipeline",
    "available_sources",
    "get_parser",
    "resolve_sources",
    "ArticleDetail",
    "ArticleRecord",
    "ContentBlock",
    "KeywordRecord",
    "KeywordResult",
    "ListingEntry",
]
