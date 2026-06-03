"""HTTP helpers used by the scraper.

Keeps a polite user-agent and a retry-with-backoff utility so the rest of
the scraper code stays focused on parsing.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

from src.rag.utils import get_logger

logger = get_logger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ViFinNER-Bot/1.0; "
        "+https://github.com/vifinner)"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


def request_with_retry(
    url: str,
    max_retries: int = 3,
    delay: int = 2,
    timeout: int = 10,
) -> Optional[requests.Response]:
    """Issue an HTTP GET request with retry/backoff.

    Parameters
    ----------
    url : str
        Target URL.
    max_retries : int
        Maximum number of attempts.
    delay : int
        Base delay between retries (seconds). The actual delay grows linearly
        with the attempt count.
    timeout : int
        Per-request timeout in seconds.

    Returns
    -------
    Optional[requests.Response]
        The successful response, or ``None`` if every attempt failed.
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=_DEFAULT_HEADERS, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001 - we want to capture everything
            if attempt < max_retries:
                wait = delay * attempt
                logger.warning(
                    "GET %s failed (attempt %s/%s): %s. Retrying in %ss",
                    url, attempt, max_retries, exc, wait,
                )
                time.sleep(wait)
            else:
                logger.error("GET %s failed permanently after %s attempts: %s", url, max_retries, exc)
                return None
    return None
