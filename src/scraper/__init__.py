"""
Multi-source financial-news scraper.

Public entry point: :mod:`src.scraper.run` (``python -m src.scraper.run``).

Package layout
--------------
* :mod:`config`         - Environment-driven settings (Postgres, ADLS, crawl).
* :mod:`http_client`    - Polite HTTP client with retry & jittered delays.
* :mod:`metrics`        - Prometheus push-gateway metrics.
* :mod:`run`            - CLI entry point.
* :mod:`engine`         - Site-agnostic crawl engine:
    ``base_parser``, ``types``, ``registry``, ``crawler``, ``pipeline``.
* :mod:`storage`        - Persistence:
    ``models``, ``repository``, ``inputs`` (Postgres) + ``adls_writer`` (ADLS).
* ``cafef`` / ``baomoi`` / ``thanhnien`` / ``tuoitre`` / ``vnexpress``
                        - Per-site packages with ``{source}_scraper.py``.

The original CafeF-only implementation is archived under :mod:`src.scraper.legacy`.
"""

__all__ = [
    "ScraperSettings",
    "get_settings",
    "RunSummary",
    "available_sources",
    "run_pipeline",
]


def __getattr__(name: str):
    if name in {"ScraperSettings", "get_settings"}:
        from src.scraper.config import ScraperSettings, get_settings

        return {"ScraperSettings": ScraperSettings, "get_settings": get_settings}[name]
    if name in {"RunSummary", "available_sources", "run_pipeline"}:
        from src.scraper.engine import RunSummary, available_sources, run_pipeline

        return {
            "RunSummary": RunSummary,
            "available_sources": available_sources,
            "run_pipeline": run_pipeline,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
