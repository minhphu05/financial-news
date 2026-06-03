"""Centralised configuration for the Financial News RAG system.

All configuration is loaded from environment variables (or a ``.env`` file).
Each subsystem has its own typed settings group so that downstream modules
only have to depend on a small, well-defined slice of configuration.

Example
-------
>>> from src.rag.config import get_settings
>>> settings = get_settings()
>>> settings.mongo.uri
'mongodb://localhost:27017'
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import ClassVar, List, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Sub-settings
# ---------------------------------------------------------------------------
class MongoSettings(BaseSettings):
    """MongoDB connection settings.

    Attributes
    ----------
    uri : str
        Full MongoDB connection URI (e.g. ``mongodb://user:pass@host:27017``).
    database : str
        Database name that stores raw scraped articles.
    raw_collection : str
        Bronze layer collection: articles as scraped.
    clean_collection : str
        Silver layer collection: Polars-processed clean articles.
    rejected_collection : str
        Audit collection for documents that fail the quality gate.
    """

    model_config = SettingsConfigDict(env_prefix="MONGO_", extra="ignore")

    uri: str = Field(default="mongodb://localhost:27017")
    database: str = Field(default="financial_news")
    raw_collection: str = Field(
        default_factory=lambda: os.getenv("MONGO_CONTENT_COLLECTION", "cafef_raw")
    )
    clean_collection: str = Field(default="cafef_clean")
    rejected_collection: str = Field(default="cafef_rejected")


class QdrantSettings(BaseSettings):
    """Qdrant vector database connection settings.

    Attributes
    ----------
    host : str
        Qdrant server hostname.
    port : int
        Qdrant HTTP port (default 6333).
    grpc_port : int
        Qdrant gRPC port (default 6334).
    prefer_grpc : bool
        Use gRPC transport for higher throughput.
    api_key : SecretStr
        API key for authenticated Qdrant deployments.
    https : bool
        Enable TLS for cloud-hosted Qdrant.
    collection : str
        Name of the collection that stores article chunks.
    embedding_dim : int
        Dimensionality of stored vectors. Must match the embedding model.
    distance : Literal['cosine', 'dot', 'euclid']
        Distance metric used for the HNSW index.
    hnsw_m : int
        HNSW graph degree (higher = more accurate, more RAM).
    hnsw_ef_construct : int
        HNSW construction ef (higher = better index quality, slower build).
    """

    model_config = SettingsConfigDict(env_prefix="QDRANT_", extra="ignore")

    host: str = Field(default="localhost")
    port: int = Field(default=6333)
    grpc_port: int = Field(default=6334)
    prefer_grpc: bool = Field(default=False)
    api_key: SecretStr = Field(default=SecretStr(""))
    https: bool = Field(default=False)
    collection: str = Field(default="financial_news_chunks")
    embedding_dim: int = Field(default=1024)
    distance: Literal["cosine", "dot", "euclid"] = Field(default="cosine")
    hnsw_m: int = Field(default=16)
    hnsw_ef_construct: int = Field(default=200)

    @property
    def url(self) -> str:
        """Return the base HTTP URL for the Qdrant REST API."""
        scheme = "https" if self.https else "http"
        return f"{scheme}://{self.host}:{self.port}"


class VoyageAISettings(BaseSettings):
    """Voyage AI embedding API settings.

    Attributes
    ----------
    api_key : SecretStr
        Voyage AI API key.
    embedding_model : str
        Embedding model name (e.g. ``voyage-4-lite``).
    embedding_dim : int
        Output vector dimension. voyage-4-lite supports 512 or 1024.
    batch_size : int
        Number of texts sent per API call.
    max_retries : int
        Retry attempts for transient API failures.
    """

    model_config = SettingsConfigDict(env_prefix="VOYAGE_", extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""))
    embedding_model: str = Field(default="voyage-4-lite")
    embedding_dim: int = Field(default=1024)
    batch_size: int = Field(default=128)
    max_retries: int = Field(default=5)


class OpenRouterSettings(BaseSettings):
    """OpenRouter LLM API settings.

    Attributes
    ----------
    api_key : SecretStr
        OpenRouter API key.
    base_url : str
        Base URL of the OpenAI-compatible OpenRouter endpoint.
    default_model : str
        Model identifier used when the caller does not specify one.
    available_models : list[str]
        Allowlist of model IDs that users may choose from. Any model ID
        submitted by a client is validated against this list.
    temperature : float
        Default sampling temperature.
    max_tokens : int
        Default maximum tokens in a single completion.
    """

    model_config = SettingsConfigDict(env_prefix="OPENROUTER_", extra="ignore")

    api_key: SecretStr = Field(default=SecretStr(""))
    base_url: str = Field(default="https://openrouter.ai/api/v1")
    default_model: str = Field(default="liquid/lfm-2.5-1.2b-thinking:free")
    available_models: List[str] = Field(
        default_factory=lambda: [
            "liquid/lfm-2.5-1.2b-thinking:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "poolside/laguna-m.1:free",
            "openai/gpt-oss-120b:free",
            "google/gemma-4-31b-it:free",
        ]
    )
    temperature: float = Field(default=0.2)
    max_tokens: int = Field(default=2048)


class ScraperSettings(BaseSettings):
    """Daily CafeF scraper settings.

    Attributes
    ----------
    base_url : str
        Base URL of CafeF.
    keywords : list[str]
        Default keywords to query daily (overridable per flow run).
    max_pages : int
        Maximum number of pages per keyword to scan in a daily run.
    request_timeout : int
        Per-request timeout in seconds.
    max_retries : int
        Maximum retry count for transient HTTP failures.
    retry_delay : int
        Base delay (seconds) between retries.
    """

    model_config = SettingsConfigDict(env_prefix="SCRAPER_", extra="ignore")

    base_url: str = Field(default="https://cafef.vn")
    keywords: List[str] = Field(default_factory=lambda: ["VN-Index", "chứng khoán"])
    max_pages: int = Field(default=3)
    request_timeout: int = Field(default=10)
    max_retries: int = Field(default=3)
    retry_delay: int = Field(default=2)

    @field_validator("keywords", mode="before")
    @classmethod
    def _split_keywords(cls, value):
        """Allow keywords to be provided as a comma-separated string."""
        if isinstance(value, str):
            return [kw.strip() for kw in value.split(",") if kw.strip()]
        return value


class ChunkingSettings(BaseSettings):
    """Text chunking parameters.

    Attributes
    ----------
    chunk_size : int
        Target chunk size in characters.
    chunk_overlap : int
        Number of overlap characters between consecutive chunks.
    min_chunk_chars : int
        Chunks shorter than this threshold are dropped.
    """

    model_config = SettingsConfigDict(env_prefix="CHUNK_", extra="ignore")

    chunk_size: int = Field(default=900)
    chunk_overlap: int = Field(default=150)
    min_chunk_chars: int = Field(default=80)


class RetrievalSettings(BaseSettings):
    """Settings for the retrieval stage of the RAG pipeline.

    Attributes
    ----------
    top_k : int
        Number of chunks returned for each query.
    score_threshold : float
        Minimum similarity score (in ``[0, 1]``) required for a chunk to be
        included in the context window. Use ``0.0`` to disable filtering.
    """

    model_config = SettingsConfigDict(env_prefix="RETRIEVAL_", extra="ignore")

    top_k: int = Field(default=5)
    score_threshold: float = Field(default=0.2)


class CacheSettings(BaseSettings):
    """Redis + semantic-cache configuration.

    Attributes
    ----------
    enabled : bool
        Master switch. When ``False`` the cache layer is bypassed.
    redis_url : str
        Redis DSN (``redis://[:password@]host:port/db``).
    namespace : str
        Key prefix used by every cache entry (helpful when sharing a Redis
        instance between environments).
    embedding_ttl_seconds : int
        TTL applied to embedding cache entries.
    answer_ttl_seconds : int
        TTL applied to RAG answer cache entries.
    similarity_threshold : float
        Cosine similarity (``[0, 1]``) above which a cached answer is
        re-used. ``0.92`` is a safe default for Vietnamese queries.
    max_entries : int
        Soft cap on the answer cache size; LRU eviction kicks in beyond.
    """

    model_config = SettingsConfigDict(env_prefix="CACHE_", extra="ignore")

    enabled: bool = Field(default=True)
    redis_url: str = Field(default="redis://localhost:6379/0")
    namespace: str = Field(default="financial-news")
    embedding_ttl_seconds: int = Field(default=7 * 24 * 3600)
    answer_ttl_seconds: int = Field(default=24 * 3600)
    similarity_threshold: float = Field(default=0.92)
    max_entries: int = Field(default=5000)


class MLflowSettings(BaseSettings):
    """MLflow tracking configuration.

    Attributes
    ----------
    tracking_uri : str
        URI of the MLflow tracking server. ``file:./mlruns`` works locally
        with no extra dependencies; use ``http://mlflow:5000`` inside
        docker-compose.
    experiment_ner : str
        Experiment name used by the NER training tracker.
    experiment_rag : str
        Experiment name used by the RAG evaluation runner.
    experiment_medallion : str
        Experiment name used by the medallion pipeline.
    """

    model_config = SettingsConfigDict(env_prefix="MLFLOW_", extra="ignore")

    tracking_uri: str = Field(default="file:./mlruns")
    experiment_ner: str = Field(default="financial-news-ner")
    experiment_rag: str = Field(default="financial-news-rag-eval")
    experiment_medallion: str = Field(default="financial-news-medallion")


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """Root settings object.

    Aggregates every subsystem configuration into a single object that can be
    cached and reused across the application.

    Attributes
    ----------
    env : Literal['dev', 'prod', 'test']
        Application environment.
    log_level : str
        Default log level for the ``utils.logger`` factory.
    mongo, pgvector, gemini, scraper, chunking, retrieval :
        Nested subsystem settings (see corresponding classes).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["dev", "prod", "test"] = Field(default="dev")
    log_level: str = Field(default="INFO")

    mongo: MongoSettings = Field(default_factory=MongoSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    voyage: VoyageAISettings = Field(default_factory=VoyageAISettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    mlflow: MLflowSettings = Field(default_factory=MLflowSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Using :func:`functools.lru_cache` guarantees the same instance is shared
    across the application, which avoids re-parsing environment variables on
    every call and keeps secrets in memory only once.

    Returns
    -------
    Settings
        Fully initialised settings object.
    """
    return Settings()
