"""Silver Delta to durable Gold RAG documents and chunks."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import time

from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession, functions as F, types as T

from src.news_pipeline.chunking import ArticleChunker
from src.news_pipeline.enrichment import ArticleEnricher, NoOpEnricher
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.silver import ARTICLE_FIELDS, create_spark
from src.news_pipeline.silver_reader import SilverArticleRepository
from src.news_pipeline.storage import ObjectStore, create_object_store


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


def _materialize(
    settings: GoldSettings,
    spark: SparkSession,
    enricher: ArticleEnricher,
    affected_article_ids: list[str] | None = None,
) -> tuple[DataFrame, DataFrame, int]:
    repo = SilverArticleRepository(spark, settings)
    articles = repo.articles()
    mentions = repo.mentions()
    if affected_article_ids is not None:
        ids = spark.createDataFrame([(value,) for value in affected_article_ids], "article_id string")
        articles = articles.join(ids, "article_id", "inner")
        mentions = mentions.join(ids, "article_id", "inner")
    symbols = (mentions.filter(F.col("ticker_symbol").isNotNull() & (F.trim("ticker_symbol") != ""))
        .groupBy("article_id")
        .agg(F.sort_array(F.collect_set("ticker_symbol")).alias("stock_symbols")))
    joined = (articles.join(symbols, "article_id", "left")
        .withColumn("stock_symbols", F.coalesce(
            F.col("stock_symbols"), F.array().cast(T.ArrayType(T.StringType()))
        )))
    documents = spark.createDataFrame(
        joined.rdd.map(lambda row: _enrich_row(row.asDict(recursive=True), enricher)),
        T.StructType(DOCUMENT_FIELDS),
    ).persist(StorageLevel.MEMORY_AND_DISK)
    document_count = documents.count()
    if document_count != articles.count():
        raise AssertionError("Gold document count differs from selected Silver articles")

    chunker = ArticleChunker(settings.chunk_size, settings.chunk_overlap)
    chunked = (documents.rdd.map(
        lambda row: chunker.chunks_for_article(row.asDict(recursive=True))
    ).persist(StorageLevel.MEMORY_AND_DISK))
    zero_chunk_articles = chunked.filter(lambda chunks: len(chunks) == 0).count()
    chunks = spark.createDataFrame(
        chunked.flatMap(lambda rows: rows), T.StructType(CHUNK_FIELDS)
    ).persist(StorageLevel.MEMORY_AND_DISK)
    chunk_count = chunks.count()
    if chunk_count < document_count - zero_chunk_articles:
        raise AssertionError("Chunk count does not cover every nonempty article")
    chunked.unpersist()
    return documents, chunks, zero_chunk_articles


def build(
    settings: GoldSettings,
    spark: SparkSession,
    store: ObjectStore,
    enricher: ArticleEnricher | None = None,
) -> dict:
    """Build the original immutable per-ingestion Gold snapshot."""
    started = time.monotonic()
    documents, chunks, zero_chunk_articles = _materialize(
        settings, spark, enricher or NoOpEnricher()
    )
    try:
        article_count = documents.count()
        if documents.filter(
            F.col("source_ingestion_id") != settings.source_ingestion_id
        ).limit(1).count():
            raise ValueError("Silver rows do not match configured ingestion ID")
        chunk_count = chunks.count()
        (documents.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
            .save(settings.news.object_uri(f"{settings.rag_prefix}/documents")))
        (chunks.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
            .save(settings.chunks_uri))
        metrics = _metrics(
            settings, article_count, chunk_count, zero_chunk_articles, started,
            affected_count=article_count,
        )
        store.put_bytes(
            f"{settings.rag_prefix}/metrics.json",
            json.dumps(metrics, ensure_ascii=False, indent=2).encode(),
        )
        return metrics
    finally:
        chunks.unpersist()
        documents.unpersist()


def _metrics(
    settings: GoldSettings,
    article_count: int,
    chunk_count: int,
    zero_chunk_articles: int,
    started: float,
    *,
    affected_count: int,
    total_documents: int | None = None,
    total_chunks: int | None = None,
    replaced_chunks: int = 0,
) -> dict:
    documents_total = article_count if total_documents is None else total_documents
    chunks_total = chunk_count if total_chunks is None else total_chunks
    return {
        "source_ingestion_id": settings.source_ingestion_id,
        "silver_processing_version": settings.news.processing_version,
        "gold_processing_version": settings.gold_processing_version,
        "affected_article_count": affected_count,
        "silver_articles_read": documents_total,
        "gold_documents_produced": documents_total,
        "gold_chunks_produced": chunks_total,
        "run_documents_produced": article_count,
        "run_chunks_produced": chunk_count,
        "replaced_chunk_count": replaced_chunks,
        "average_chunks_per_article": round(chunks_total / documents_total, 4) if documents_total else 0,
        "empty_rejected_chunk_count": zero_chunk_articles,
        "processing_duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "documents_uri": settings.news.object_uri(f"{settings.rag_prefix}/documents"),
        "chunks_uri": settings.chunks_uri,
    }


def _quoted(values: list[str]) -> str:
    return ",".join("'" + value.replace("'", "''") + "'" for value in values)


def build_incremental(
    settings: GoldSettings,
    spark: SparkSession,
    store: ObjectStore,
    affected_article_ids: list[str],
    enricher: ArticleEnricher | None = None,
) -> dict:
    """Regenerate and merge Gold rows only for changed Silver articles."""
    from delta.tables import DeltaTable

    started = time.monotonic()
    settings = settings.for_current_tables()
    documents_uri = settings.news.object_uri(f"{settings.rag_prefix}/documents")
    documents, chunks, zero_chunk_articles = _materialize(
        settings, spark, enricher or NoOpEnricher(), affected_article_ids
    )
    try:
        run_documents = documents.count()
        run_chunks = chunks.count()
        if run_documents != len(set(affected_article_ids)):
            raise AssertionError("Affected Silver IDs and regenerated Gold documents differ")

        if DeltaTable.isDeltaTable(spark, documents_uri):
            (DeltaTable.forPath(spark, documents_uri).alias("target")
                .merge(documents.alias("source"), "target.article_id = source.article_id")
                .whenMatchedUpdateAll()
                .whenNotMatchedInsertAll()
                .execute())
        elif run_documents:
            (documents.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
                .save(documents_uri))
        else:
            raise RuntimeError("Current Gold documents do not exist and no affected articles were supplied")

        replaced_chunks = 0
        if DeltaTable.isDeltaTable(spark, settings.chunks_uri):
            if affected_article_ids:
                ids_sql = _quoted(sorted(set(affected_article_ids)))
                replaced_chunks = (spark.read.format("delta").load(settings.chunks_uri)
                    .filter(F.expr(f"article_id IN ({ids_sql})")).count())
                (DeltaTable.forPath(spark, settings.chunks_uri).alias("target")
                    .merge(chunks.alias("source"), "target.chunk_id = source.chunk_id")
                    .whenMatchedUpdateAll()
                    .whenNotMatchedInsertAll()
                    .whenNotMatchedBySourceDelete(
                        condition=f"target.article_id IN ({ids_sql})"
                    )
                    .execute())
        elif run_chunks:
            (chunks.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
                .save(settings.chunks_uri))
        else:
            raise RuntimeError("Current Gold chunks do not exist and no affected chunks were supplied")

        total_documents = spark.read.format("delta").load(documents_uri).count()
        total_chunks = spark.read.format("delta").load(settings.chunks_uri).count()
        metrics = _metrics(
            settings,
            run_documents,
            run_chunks,
            zero_chunk_articles,
            started,
            affected_count=len(set(affected_article_ids)),
            total_documents=total_documents,
            total_chunks=total_chunks,
            replaced_chunks=replaced_chunks,
        )
        store.put_bytes(
            f"{settings.rag_prefix}/metrics.json",
            json.dumps(metrics, ensure_ascii=False, indent=2).encode(),
        )
        return metrics
    finally:
        chunks.unpersist()
        documents.unpersist()


def main() -> None:
    settings = GoldSettings.from_env()
    spark = create_spark(settings.news)
    try:
        print(json.dumps(build(settings, spark, create_object_store(settings.news)), ensure_ascii=False, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
