"""Redis connection helper used by the caching subsystem.

We keep the surface tiny on purpose: a single :func:`get_redis_client`
function that returns a configured :class:`redis.Redis` instance, plus a
:class:`NullRedis` fallback that silently no-ops when the cache is
disabled (``CACHE_ENABLED=false`` or the connection fails).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)


class NullRedis:
    """No-op :class:`redis.Redis` substitute.

    Implements just enough of the interface for :class:`SemanticCache` to
    keep working: every call returns a sensible "empty" value (``None``,
    ``0``, or an empty list/dict).
    """

    def get(self, _key: str) -> Optional[bytes]:
        """Return ``None`` to indicate a cache miss."""
        return None

    def set(self, *args: Any, **kwargs: Any) -> bool:
        """Drop the write silently."""
        return False

    def setex(self, *args: Any, **kwargs: Any) -> bool:
        """Drop the TTL write silently."""
        return False

    def delete(self, *_keys: str) -> int:
        """Pretend the delete succeeded."""
        return 0

    def scan_iter(self, *_args: Any, **_kwargs: Any):
        """Yield no keys."""
        return iter(())

    def zadd(self, *_args: Any, **_kwargs: Any) -> int:
        """No-op sorted set add."""
        return 0

    def zrange(self, *_args: Any, **_kwargs: Any):
        """Return an empty range."""
        return []

    def zrem(self, *_args: Any, **_kwargs: Any) -> int:
        """No-op sorted set removal."""
        return 0

    def zcard(self, _key: str) -> int:
        """Pretend the cache is empty."""
        return 0

    def ping(self) -> bool:
        """Mirror the redis-py contract."""
        return False

    def close(self) -> None:
        """No-op close."""
        return None


@lru_cache(maxsize=1)
def _get_redis_client_cached():
    """Cached inner factory — always uses :func:`get_settings`."""
    cfg = get_settings().cache
    if not cfg.enabled:
        logger.info("Redis cache disabled via settings (CACHE_ENABLED=false).")
        return NullRedis()

    try:
        import redis  # noqa: WPS433 - optional dependency

        client = redis.Redis.from_url(cfg.redis_url, decode_responses=False)
        client.ping()
        logger.info("Connected to Redis at %s", _safe_url(cfg.redis_url))
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unreachable (%s); using NullRedis fallback.", exc)
        return NullRedis()


def get_redis_client(settings: Optional[Settings] = None):
    """Return a process-wide Redis client (or :class:`NullRedis`).

    The factory is cached so every caller in the FastAPI process shares
    the same connection pool. When the cache is disabled or Redis is
    unreachable the function logs a warning and returns a
    :class:`NullRedis` so downstream code can run unchanged.
    """
    if settings is None:
        return _get_redis_client_cached()
    # Settings override provided (e.g. from tests): build without caching.
    cfg = settings.cache
    if not cfg.enabled:
        return NullRedis()
    try:
        import redis  # noqa: WPS433 - optional dependency

        client = redis.Redis.from_url(cfg.redis_url, decode_responses=False)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unreachable (%s); using NullRedis fallback.", exc)
        return NullRedis()


def _safe_url(url: str) -> str:
    """Strip credentials from a Redis URL before logging it."""
    if "@" in url:
        proto, rest = url.split("://", 1)
        _, host = rest.split("@", 1)
        return f"{proto}://***@{host}"
    return url
