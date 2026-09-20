"""Embedding port and real local FastEmbed implementation."""

from typing import Protocol, Sequence

from .gold_config import GoldSettings


class EmbeddingProvider(Protocol):
    model_id: str
    dimension: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedProvider:
    """CPU ONNX multilingual model; downloads weights into a persistent local cache."""

    def __init__(self, settings: GoldSettings):
        if settings.embedding_provider != "fastembed":
            raise ValueError(f"Unsupported demo embedding provider: {settings.embedding_provider}")
        from fastembed import TextEmbedding

        self._model = TextEmbedding(
            model_name=settings.embedding_model,
            cache_dir=settings.model_cache_dir,
            threads=2,
        )
        self.model_id = f"fastembed-0.8.0:{settings.embedding_model}"
        self.dimension = self._model.embedding_size
        if self.dimension != settings.embedding_dimension:
            raise ValueError(f"Embedding dimension mismatch: model={self.dimension}, configured={settings.embedding_dimension}")

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return next(self._model.embed([text])).tolist()
