"""Configuration for the local Silver to Gold serving jobs."""

from dataclasses import dataclass
import os
from pathlib import Path

from .bronze import file_sha256
from .config import Settings

ANALYTICS_DATASETS = ("news_daily", "news_by_source", "news_publication_status")


@dataclass(frozen=True)
class GoldSettings:
    news: Settings
    source_ingestion_id: str
    silver_articles_uri: str
    silver_mentions_uri: str
    rag_prefix: str
    analytics_prefix: str
    chunk_size: int
    chunk_overlap: int
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    model_cache_dir: str
    qdrant_url: str
    qdrant_collection: str
    index_limit: int
    index_batch_size: int
    duckdb_path: str

    @classmethod
    def from_env(cls) -> "GoldSettings":
        news = Settings.from_env()
        ingestion_id = os.getenv("NEWS_SOURCE_INGESTION_ID") or file_sha256(Path(news.source_file))
        silver_prefix = f"silver/{news.source}/{ingestion_id}/{news.processing_version}"
        size = int(os.getenv("NEWS_CHUNK_SIZE", "900"))
        overlap = int(os.getenv("NEWS_CHUNK_OVERLAP", "120"))
        if size < 50 or overlap < 0 or overlap >= size:
            raise ValueError("NEWS_CHUNK_SIZE must be >= 50 and 0 <= NEWS_CHUNK_OVERLAP < size")
        chunker_version = f"sentence-v1-{size}-{overlap}"
        rag_prefix = os.getenv("NEWS_GOLD_RAG_PREFIX") or f"gold/rag/{news.source}/{ingestion_id}/{news.processing_version}/{chunker_version}"
        analytics_prefix = os.getenv("NEWS_GOLD_ANALYTICS_PREFIX") or f"gold/analytics/{news.source}/{ingestion_id}/{news.processing_version}"
        dimension = int(os.getenv("NEWS_EMBEDDING_DIMENSION", "384"))
        index_limit = int(os.getenv("NEWS_INDEX_LIMIT", "0"))
        batch_size = int(os.getenv("NEWS_INDEX_BATCH_SIZE", "32"))
        if dimension <= 0 or index_limit < 0 or batch_size <= 0:
            raise ValueError("Embedding dimension and batch size must be positive; index limit must be nonnegative")
        return cls(
            news=news,
            source_ingestion_id=ingestion_id,
            silver_articles_uri=os.getenv("NEWS_SILVER_ARTICLES_URI") or news.s3a(f"{silver_prefix}/articles"),
            silver_mentions_uri=os.getenv("NEWS_SILVER_MENTIONS_URI") or news.s3a(f"{silver_prefix}/article_mentions"),
            rag_prefix=rag_prefix.strip("/"),
            analytics_prefix=analytics_prefix.strip("/"),
            chunk_size=size,
            chunk_overlap=overlap,
            embedding_provider=os.getenv("NEWS_EMBEDDING_PROVIDER", "fastembed"),
            embedding_model=os.getenv("NEWS_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
            embedding_dimension=dimension,
            model_cache_dir=os.getenv("NEWS_MODEL_CACHE_DIR", "/opt/news-models"),
            qdrant_url=os.getenv("NEWS_QDRANT_URL", "http://qdrant:6333"),
            qdrant_collection=os.getenv("NEWS_QDRANT_COLLECTION", "news_chunks_local_v1"),
            index_limit=index_limit,
            index_batch_size=batch_size,
            duckdb_path=os.getenv("NEWS_DUCKDB_PATH", "/app/local/analytics.duckdb"),
        )

    @property
    def chunker_version(self) -> str:
        return f"sentence-v1-{self.chunk_size}-{self.chunk_overlap}"

    @property
    def gold_processing_version(self) -> str:
        return f"{self.news.processing_version}+{self.chunker_version}"

    @property
    def chunks_uri(self) -> str:
        return self.news.s3a(f"{self.rag_prefix}/chunks")

    def analytics_uri(self, dataset: str) -> str:
        return self.news.s3a(f"{self.analytics_prefix}/{dataset}")
