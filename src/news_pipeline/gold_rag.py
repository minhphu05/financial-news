"""Silver Delta to durable Gold RAG documents and chunks."""

from datetime import datetime, timezone
import json
import time

from pyspark import StorageLevel
from pyspark.sql import SparkSession, functions as F, types as T

from src.news_pipeline.chunking import ArticleChunker
from src.news_pipeline.enrichment import ArticleEnricher, NoOpEnricher
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.silver import ARTICLE_FIELDS, create_spark
from src.news_pipeline.silver_reader import SilverArticleRepository
from src.news_pipeline.storage import ObjectStore, S3ObjectStore


ENTITY_TYPE = T.ArrayType(T.MapType(T.StringType(), T.StringType()))
DOCUMENT_FIELDS = ARTICLE_FIELDS + [
    T.StructField("stock_symbols", T.ArrayType(T.StringType()), False),
    T.StructField("entities", ENTITY_TYPE),
    T.StructField("enrichment_status", T.StringType(), False),
    T.StructField("enricher_version", T.StringType()),
]
CHUNK_FIELDS = [
    T.StructField("chunk_id", T.StringType(), False),
    T.StructField("article_id", T.StringType(), False),
    T.StructField("chunk_index", T.IntegerType(), False),
    T.StructField("text", T.StringType(), False),
    T.StructField("title", T.StringType(), False),
    T.StructField("source", T.StringType(), False),
    T.StructField("source_url", T.StringType(), False),
    T.StructField("published_at", T.TimestampType()),
    T.StructField("stock_symbols", T.ArrayType(T.StringType()), False),
    T.StructField("entities", ENTITY_TYPE),
    T.StructField("processing_version", T.StringType(), False),
    T.StructField("content_hash", T.StringType(), False),
    T.StructField("source_ingestion_id", T.StringType(), False),
    T.StructField("chunker_version", T.StringType(), False),
    T.StructField("enrichment_status", T.StringType(), False),
    T.StructField("enricher_version", T.StringType()),
]


def _enrich_row(row: dict, enricher: ArticleEnricher) -> dict:
    return enricher.enrich(row)


def build(settings: GoldSettings, spark: SparkSession, store: ObjectStore, enricher: ArticleEnricher | None = None) -> dict:
    started = time.monotonic()
    repo = SilverArticleRepository(spark, settings)
    articles = repo.articles()
    mentions = repo.mentions()
    symbols = (mentions.filter(F.col("ticker_symbol").isNotNull() & (F.trim("ticker_symbol") != ""))
        .groupBy("article_id")
        .agg(F.sort_array(F.collect_set("ticker_symbol")).alias("stock_symbols")))
    joined = (articles.join(symbols, "article_id", "left")
        .withColumn("stock_symbols", F.coalesce(F.col("stock_symbols"), F.array().cast(T.ArrayType(T.StringType())))))
    enricher = enricher or NoOpEnricher()
    documents = spark.createDataFrame(
        joined.rdd.map(lambda row: _enrich_row(row.asDict(recursive=True), enricher)),
        T.StructType(DOCUMENT_FIELDS),
    ).persist(StorageLevel.MEMORY_AND_DISK)
    article_count = documents.count()
    if article_count != articles.count():
        raise AssertionError("Gold document count differs from Silver article count")
    if documents.filter(F.col("source_ingestion_id") != settings.source_ingestion_id).limit(1).count():
        raise ValueError("Silver rows do not match configured ingestion ID")

    chunker = ArticleChunker(settings.chunk_size, settings.chunk_overlap)
    chunked = (documents.rdd.map(lambda row: chunker.chunks_for_article(row.asDict(recursive=True)))
        .persist(StorageLevel.MEMORY_AND_DISK))
    zero_chunk_articles = chunked.filter(lambda chunks: len(chunks) == 0).count()
    chunks = spark.createDataFrame(chunked.flatMap(lambda rows: rows), T.StructType(CHUNK_FIELDS))
    chunk_count = chunks.count()
    if chunk_count < article_count - zero_chunk_articles:
        raise AssertionError("Chunk count does not cover every nonempty article")

    (documents.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
        .save(settings.news.s3a(f"{settings.rag_prefix}/documents")))
    (chunks.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
        .save(settings.chunks_uri))
    metrics = {
        "source_ingestion_id": settings.source_ingestion_id,
        "silver_processing_version": settings.news.processing_version,
        "gold_processing_version": settings.gold_processing_version,
        "silver_articles_read": article_count,
        "gold_documents_produced": article_count,
        "gold_chunks_produced": chunk_count,
        "average_chunks_per_article": round(chunk_count / article_count, 4) if article_count else 0,
        "empty_rejected_chunk_count": zero_chunk_articles,
        "processing_duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "documents_uri": settings.news.s3a(f"{settings.rag_prefix}/documents"),
        "chunks_uri": settings.chunks_uri,
    }
    store.put_bytes(f"{settings.rag_prefix}/metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2).encode())
    chunked.unpersist()
    documents.unpersist()
    return metrics


def main() -> None:
    settings = GoldSettings.from_env()
    spark = create_spark(settings.news)
    try:
        print(json.dumps(build(settings, spark, S3ObjectStore(settings.news)), ensure_ascii=False, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
