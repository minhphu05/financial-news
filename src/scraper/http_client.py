"""
HTTP client with retry, exponential backoff, and polite jittered delays.

This wraps :mod:`requests` so every call inside the scraper benefits from
the same timeout / retry / pacing policy without copy-pasting boilerplate.
"""
from __future__ import annotations

import random
import time
from typing import Optional

import requests

from src.scraper.config import ScraperSettings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HttpClient:
    """
    Thin wrapper around a persistent ``requests.Session``.

    Responsibilities:

    * Apply a consistent ``User-Agent`` header for every request.
    * Retry transient failures with exponential backoff.
    * Apply a small randomized delay between successful requests to avoid
      hammering the source.
    """

    def __init__(self, settings: ScraperSettings) -> None:
        self._settings = settings
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept-Language": "vi,en;q=0.9",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(self, url: str) -> Optional[requests.Response]:
        """
        Fetch ``url`` with retries.

        Args:
            url: Absolute URL to GET.

        Returns:
            The successful :class:`requests.Response`, or ``None`` if every
            retry attempt failed.
        """
        last_exc: Optional[BaseException] = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                response = self._session.get(
                    url, timeout=self._settings.request_timeout
                )
                response.raise_for_status()
                self._sleep_polite()
                return response
            except requests.RequestException as exc:
                last_exc = exc
                backoff = self._settings.retry_delay * attempt
                logger.warning(
                    f"GET {url} failed (attempt {attempt}/{self._settings.max_retries}): "
                    f"{exc.__class__.__name__}: {exc} - retrying in {backoff:.1f}s"
                )
                time.sleep(backoff)

        logger.error(f"GET {url} gave up after {self._settings.max_retries} retries: {last_exc!r}")
        return None

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._session.close()

    # ------------------------------------------------------------------
    # Context manager sugar
    # ------------------------------------------------------------------
    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _sleep_polite(self) -> None:
        """Sleep a small random interval between successful requests."""
        lo = self._settings.request_delay_min
        hi = self._settings.request_delay_max
        if hi <= 0:
            return
        time.sleep(random.uniform(lo, max(lo, hi)))
