"""Idempotent Gold chunk vector projection into the existing local Qdrant."""

from datetime import datetime, timezone
import json
import time
import uuid

from src.news_pipeline.embedding import EmbeddingProvider, FastEmbedProvider
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.storage import ObjectStore, S3ObjectStore


def point_id(chunk_id: str, model_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{model_id}\n{chunk_id}"))


def payload_from_chunk(chunk: dict, model_id: str) -> dict:
    published = chunk.get("published_at")
    if isinstance(published, datetime):
        published = published.replace(tzinfo=timezone.utc).isoformat() if published.tzinfo is None else published.astimezone(timezone.utc).isoformat()
    return {
        "chunk_id": chunk["chunk_id"],
        "article_id": chunk["article_id"],
        "chunk_index": chunk["chunk_index"],
        "text": chunk["text"],
        "title": chunk["title"],
        "source": chunk["source"],
        "source_url": chunk["source_url"],
        "published_at": published,
        "stock_symbols": chunk.get("stock_symbols") or [],
        "entities": chunk.get("entities"),
        "processing_version": chunk["processing_version"],
        "source_ingestion_id": chunk["source_ingestion_id"],
        "embedding_model": model_id,
    }


class QdrantChunkIndex:
    def __init__(self, url: str, collection: str, dimension: int):
        from qdrant_client import QdrantClient

        self.client = QdrantClient(url=url, timeout=60)
        self.collection = collection
        self.dimension = dimension

    def ensure_collection(self) -> None:
        from qdrant_client import models

        existing = {item.name for item in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=self.dimension, distance=models.Distance.COSINE),
            )
        else:
            config = self.client.get_collection(self.collection).config.params.vectors
            actual = config.size if hasattr(config, "size") else None
            if actual != self.dimension:
                raise ValueError(f"Qdrant collection dimension {actual} differs from configured {self.dimension}")

    def upsert(self, chunks: list[dict], vectors: list[list[float]], model_id: str) -> list[str]:
        from qdrant_client import models

        if len(chunks) != len(vectors):
            raise ValueError("Embedding count does not match input chunks")
        points = []
        ids = []
        for chunk, vector in zip(chunks, vectors):
            if len(vector) != self.dimension:
                raise ValueError("Embedding vector dimension mismatch")
            identifier = point_id(chunk["chunk_id"], model_id)
            ids.append(identifier)
            points.append(models.PointStruct(id=identifier, vector=vector, payload=payload_from_chunk(chunk, model_id)))
        if points:
            self.client.upsert(collection_name=self.collection, points=points, wait=True)
        return ids

    def reconcile(self, expected_ids: set[str]) -> int:
        from qdrant_client import models

        stale = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection, offset=offset, limit=256, with_payload=False, with_vectors=False,
            )
            stale.extend(point.id for point in points if str(point.id) not in expected_ids)
            if offset is None:
                break
        for start in range(0, len(stale), 256):
            self.client.delete(
                collection_name=self.collection,
                points_selector=models.PointIdsList(points=stale[start:start + 256]),
                wait=True,
            )
        return len(stale)

    def search(self, vector: list[float], top_k: int) -> list[dict]:
        response = self.client.query_points(
            collection_name=self.collection, query=vector, limit=top_k, with_payload=True,
        )
        return [{"score": point.score, **(point.payload or {})} for point in response.points]

    def count(self) -> int:
        return self.client.count(collection_name=self.collection, exact=True).count

    def close(self) -> None:
        self.client.close()


def index_chunks(settings: GoldSettings, provider: EmbeddingProvider, store: ObjectStore) -> dict:
    from src.news_pipeline.gold_rag import CHUNK_FIELDS
    from src.news_pipeline.silver import create_spark

    started = time.monotonic()
    spark = create_spark(settings.news)
    index = QdrantChunkIndex(settings.qdrant_url, settings.qdrant_collection, provider.dimension)
    try:
        chunks = spark.read.format("delta").load(settings.chunks_uri)
        if chunks.columns != [field.name for field in CHUNK_FIELDS]:
            raise ValueError("Gold chunk Delta schema does not match the expected contract")
        selected = chunks.orderBy("article_id", "chunk_index")
        if settings.index_limit:
            selected = selected.limit(settings.index_limit)
        input_count = selected.count()
        index.ensure_collection()
        expected_ids: set[str] = set()
        batch: list[dict] = []
        embedded_count = indexed_count = failed_count = 0

        def flush() -> None:
            nonlocal embedded_count, indexed_count, failed_count, batch
            if not batch:
                return
            try:
                vectors = provider.embed_documents([row["text"] for row in batch])
                if len(vectors) != len(batch):
                    raise RuntimeError("Embedding provider returned the wrong number of vectors")
                embedded_count += len(vectors)
                ids = index.upsert(batch, vectors, provider.model_id)
                indexed_count += len(ids)
                expected_ids.update(ids)
            except Exception:
                failed_count += len(batch)
                raise
            finally:
                batch = []

        for row in selected.toLocalIterator():
            batch.append(row.asDict(recursive=True))
            if len(batch) >= settings.index_batch_size:
                flush()
        flush()
        stale_deleted = index.reconcile(expected_ids)
        if index.count() != indexed_count:
            raise AssertionError("Qdrant point count does not match indexed chunks")
        metrics = {
            "input_chunk_count": input_count,
            "embedded_chunk_count": embedded_count,
            "indexed_chunk_count": indexed_count,
            "failed_chunk_count": failed_count,
            "stale_points_deleted": stale_deleted,
            "collection_point_count": index.count(),
            "processing_duration_seconds": round(time.monotonic() - started, 3),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "collection": settings.qdrant_collection,
            "embedding_model": provider.model_id,
            "embedding_dimension": provider.dimension,
            "index_limit": settings.index_limit,
        }
        store.put_bytes(f"{settings.rag_prefix}/qdrant_metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2).encode())
        return metrics
    finally:
        index.close()
        spark.stop()


def main() -> None:
    settings = GoldSettings.from_env()
    provider = FastEmbedProvider(settings)
    print(json.dumps(index_chunks(settings, provider, S3ObjectStore(settings.news)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
