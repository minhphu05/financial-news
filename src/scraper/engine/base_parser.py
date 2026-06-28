"""
Reusable base class for site-specific HTML parsers.

A parser is the *only* place that knows the DOM layout and URL conventions of
a given news site. Everything else in the scraper (HTTP, crawl loop, storage)
is site-agnostic and drives parsers through this interface.

To onboard a new source, subclass :class:`BaseParser`, implement the four
abstract methods, and register the class in :mod:`src.scraper.sources`.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import List
from urllib.parse import urlsplit, urlunsplit

from src.scraper.engine.types import ArticleDetail, ListingEntry


class BaseParser(ABC):
    """Contract every source parser must satisfy."""

    #: Short, unique source identifier (matches the ``source.name`` column).
    name: str = ""
    #: Site root, used to resolve relative links.
    base_url: str = ""
    #: ISO language code stored on metadata when the page omits one.
    default_language: str = "vi"

    # -- URL building ----------------------------------------------------
    @abstractmethod
    def build_search_url(self, keyword: str, page: int) -> str:
        """Return the search-results URL for ``keyword`` at ``page``."""

    # -- Listing page ----------------------------------------------------
    @abstractmethod
    def is_listing_exhausted(self, html: str) -> bool:
        """Return ``True`` when the listing has no more results."""

    @abstractmethod
    def parse_listing(self, html: str) -> List[ListingEntry]:
        """Extract every article reference from one listing page."""

    # -- Detail page -----------------------------------------------------
    @abstractmethod
    def parse_detail(self, html: str) -> ArticleDetail:
        """Extract the structured fields from one article page."""

    # -- Shared helpers --------------------------------------------------
    @staticmethod
    def canonicalize_url(url: str) -> str:
        """Normalize a URL for stable hashing (drop query/fragment, trailing /)."""
        parts = urlsplit(url)
        path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    @classmethod
    def url_hash(cls, url: str) -> str:
        """SHA-256 of the canonical URL — the cross-source dedup key."""
        return hashlib.sha256(cls.canonicalize_url(url).encode("utf-8")).hexdigest()
