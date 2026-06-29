"""
Persistence layer for the scraper.

Groups the two storage backends and their helpers:

* PostgreSQL metadata - :mod:`models`, :mod:`repository`, :mod:`inputs`.
* ADLS/MinIO content   - :mod:`adls_writer`.
"""
from src.scraper.storage.adls_writer import ADLSContentWriter, ContentDocument, MinIOContentWriter, create_content_writer
from src.scraper.storage.inputs import KeywordProvider, PostgresKeywordProvider
from src.scraper.storage.repository import MetadataRepository

__all__ = [
    "ADLSContentWriter",
    "ContentDocument",
    "MinIOContentWriter",
    "create_content_writer",
    "KeywordProvider",
    "PostgresKeywordProvider",
    "MetadataRepository",
]
