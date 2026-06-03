"""Lightweight logger factory used across the RAG package.

The factory configures the root logger only once with a structured,
timestamped formatter and returns named child loggers afterwards so each
module gets a sensible ``logger.name``.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

_CONFIGURED: bool = False
_DEFAULT_FORMAT: str = (
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)


def _configure_root(level: str) -> None:
    """Configure the root logger exactly once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    root.handlers = [handler]

    _CONFIGURED = True


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a configured logger for ``name``.

    Parameters
    ----------
    name : str
        Logger name. Typically ``__name__`` of the calling module.
    level : Optional[str]
        Optional override for this logger's level. If ``None``, the level
        configured on the root logger is inherited.

    Returns
    -------
    logging.Logger
        Configured logger.
    """
    from src.rag.config import get_settings

    settings = get_settings()
    _configure_root(settings.log_level)

    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger
