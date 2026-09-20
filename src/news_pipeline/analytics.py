"""Silver Delta to published Gold analytical Parquet datasets."""

from datetime import datetime, timezone
import json
import time

from pyspark.sql import DataFrame, SparkSession, functions as F

from src.news_pipeline.gold_config import ANALYTICS_DATASETS, GoldSettings
from src.news_pipeline.silver import create_spark
from src.news_pipeline.silver_reader import SilverArticleRepository
from src.news_pipeline.storage import ObjectStore, S3ObjectStore


def analytical_frames(articles: DataFrame) -> dict[str, DataFrame]:
    prepared = (articles
        .withColumn("published_date", F.to_date(F.from_utc_timestamp("published_at", "Asia/Ho_Chi_Minh")))
        .withColumn("content_chars", F.length("content"))
        .withColumn("publication_status", F.when(F.col("published_date").isNull(), "unparsed").otherwise("parsed")))
    daily = (prepared.filter(F.col("published_date").isNotNull())
        .groupBy("source", "published_date")
        .agg(F.count("article_id").alias("article_count"), F.round(F.avg("content_chars"), 2).alias("avg_content_chars")))
    by_source = (prepared.groupBy("source")
        .agg(F.count("article_id").alias("article_count"),
             F.sum(F.when(F.col("publication_status") == "parsed", 1).otherwise(0)).alias("parsed_count"),
             F.sum(F.when(F.col("publication_status") == "unparsed", 1).otherwise(0)).alias("unparsed_count"),
             F.round(F.avg("content_chars"), 2).alias("avg_content_chars")))
    publication_status = (prepared.groupBy("source", "publication_status")
        .agg(F.count("article_id").alias("article_count")))
    return {"news_daily": daily, "news_by_source": by_source, "news_publication_status": publication_status}


def build(settings: GoldSettings, spark: SparkSession, store: ObjectStore) -> dict:
    started = time.monotonic()
    articles = SilverArticleRepository(spark, settings).articles()
    input_count = articles.count()
    frames = analytical_frames(articles)
    row_counts = {}
    for name, frame in frames.items():
        row_counts[name] = frame.count()
        frame.write.mode("overwrite").parquet(settings.analytics_uri(name))

    by_source_total = frames["news_by_source"].agg(F.sum("article_count")).first()[0]
    status_total = frames["news_publication_status"].agg(F.sum("article_count")).first()[0]
    if by_source_total != input_count or status_total != input_count:
        raise AssertionError("Analytical group counts do not reconcile with Silver")

    datasets = {}
    for name in ANALYTICS_DATASETS:
        keys = [key for key in store.list_keys(f"{settings.analytics_prefix}/{name}/") if key.endswith(".parquet")]
        if not keys:
            raise RuntimeError(f"No Parquet objects written for {name}")
        datasets[name] = {"row_count": row_counts[name], "object_keys": keys}
    manifest = {
        "source_ingestion_id": settings.source_ingestion_id,
        "silver_processing_version": settings.news.processing_version,
        "input_article_count": input_count,
        "datasets": datasets,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    store.put_bytes(f"{settings.analytics_prefix}/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode())
    metrics = {
        "input_article_count": input_count,
        "output_aggregation_rows": row_counts,
        "processing_duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "manifest_key": f"{settings.analytics_prefix}/manifest.json",
    }
    store.put_bytes(f"{settings.analytics_prefix}/metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2).encode())
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
