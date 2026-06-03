"""
Scraper package for the Financial News RAG stack.

Public entry point: :mod:`src.scraper.run`.

The package is split into focused modules:

* :mod:`config`        - Centralized environment-driven configuration.
* :mod:`http_client`   - Polite HTTP client with retry & jittered delays.
* :mod:`parsers`       - HTML parsing helpers (listing page, detail page, news_id).
* :mod:`storage`       - PostgreSQL + MongoDB persistence layer.
* :mod:`models`        - SQLAlchemy ORM definitions for article metadata.
* :mod:`page_scraper`  - Iterates listing pages for a given keyword.
* :mod:`detail_scraper`- Fetches a single article detail page.
* :mod:`pipeline`      - Orchestrates the full crawl across all keywords.
* :mod:`run`           - CLI entry point (``python -m src.scraper.run``).
"""

__all__: list[str] = []
