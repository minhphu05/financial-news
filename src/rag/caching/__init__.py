"""Redis-backed caching for the RAG serving layer.

Modules
-------
* :mod:`redis_client`     - thin :class:`redis.Redis` wrapper that handles
  connection lifecycle and namespacing.
* :mod:`semantic_cache`   - :class:`SemanticCache` for chatbot answers,
  with a cosine-similarity lookup so paraphrases hit the cache.
* :mod:`async_inference`  - :class:`AsyncRAGService` that orchestrates
  Gemini calls in async + thread-pool form and consults the cache.
"""

from src.rag.caching.async_inference import AsyncRAGService
from src.rag.caching.redis_client import get_redis_client
from src.rag.caching.semantic_cache import (
    CachedAnswer,
    SemanticCache,
    SemanticHit,
)

__all__ = [
    "AsyncRAGService",
    "CachedAnswer",
    "SemanticCache",
    "SemanticHit",
    "get_redis_client",
]
