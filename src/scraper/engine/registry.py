"""
Source parser registry.

Maps a source name to its :class:`~src.scraper.base_parser.BaseParser`
implementation. Only fully-implemented sources are registered; the remaining
financial-news sites (vnexpress, baomoi, thanhnien, tuoitre) plug in here once
their parser modules are written under their own package.
"""
from __future__ import annotations

from typing import Dict, List, Type

from src.scraper.engine.base_parser import BaseParser
from src.scraper.cafef import CafefParser

# name -> parser class
_REGISTRY: Dict[str, Type[BaseParser]] = {
    CafefParser.name: CafefParser,
}


def available_sources() -> List[str]:
    """Return the names of every registered (implemented) source."""
    return sorted(_REGISTRY)


def get_parser(name: str) -> BaseParser:
    """Instantiate the parser registered under ``name``.

    Raises:
        KeyError: if ``name`` is not a registered source.
    """
    key = name.lower().strip()
    if key not in _REGISTRY:
        raise KeyError(
            f"Unknown source '{name}'. Available: {available_sources()}"
        )
    return _REGISTRY[key]()


def resolve_sources(requested: str | None) -> List[str]:
    """Resolve a ``--source`` argument into concrete source names.

    ``None`` or ``'all'`` expands to every registered source.
    """
    if requested is None or requested.lower() == "all":
        return available_sources()
    names = [s.strip().lower() for s in requested.split(",") if s.strip()]
    unknown = [n for n in names if n not in _REGISTRY]
    if unknown:
        raise KeyError(f"Unknown source(s): {unknown}. Available: {available_sources()}")
    return names


__all__ = ["available_sources", "get_parser", "resolve_sources"]
