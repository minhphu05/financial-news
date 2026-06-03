"""Data quality validation for the scraping layer.

* :class:`ScrapedArticleV1` — strict Pydantic schema that every raw
  article must satisfy before being persisted to the bronze layer.
* :class:`QualityReport` — aggregated stats produced by a validation pass.
* :func:`validate_articles` — pure-function entrypoint used by Prefect.
"""

from src.rag.quality.validators import (
    QualityReport,
    QualityRejection,
    ScrapedArticleV1,
    validate_articles,
)

__all__ = [
    "ScrapedArticleV1",
    "QualityReport",
    "QualityRejection",
    "validate_articles",
]
