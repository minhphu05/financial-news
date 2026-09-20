"""Real PySpark Bronze-to-Silver transformation and Delta writes on S3A."""

from datetime import datetime, timezone
import hashlib
import json
import time

from pyspark.sql import SparkSession, Window, functions as F, types as T
from pyspark import StorageLevel

from src.news_pipeline.config import Settings
from src.news_pipeline.bronze import file_sha256
from src.news_pipeline.normalize import normalize_observation
from src.news_pipeline.storage import ObjectStore, S3ObjectStore
from pathlib import Path


ARTICLE_FIELDS = [
    T.StructField("article_id", T.StringType(), False),
    T.StructField("source", T.StringType(), False),
    T.StructField("source_url", T.StringType(), False),
    T.StructField("canonical_url", T.StringType(), False),
    T.StructField("title", T.StringType(), False),
    T.StructField("description", T.StringType()),
    T.StructField("content", T.StringType(), False),
    T.StructField("published_at", T.TimestampType()),
    T.StructField("published_at_raw", T.StringType()),
    T.StructField("content_hash", T.StringType(), False),
    T.StructField("processing_version", T.StringType(), False),
    T.StructField("source_ingestion_id", T.StringType(), False),
    T.StructField("author", T.StringType()),
    T.StructField("crawled_at", T.TimestampType()),
    T.StructField("category", T.StringType()),
    T.StructField("image_urls", T.ArrayType(T.StringType())),
]
OBSERVATION_SCHEMA = T.StructType(ARTICLE_FIELDS + [
    T.StructField("source_index", T.LongType()),
    T.StructField("source_row_position", T.LongType(), False),
    T.StructField("ticker_symbol", T.StringType()),
    T.StructField("ticker_name", T.StringType()),
    T.StructField("keyword", T.StringType()),
    T.StructField("source_page", T.LongType()),
])
REJECT_SCHEMA = T.StructType([
    T.StructField("source_ingestion_id", T.StringType(), False),
    T.StructField("source_row_position", T.LongType(), False),
    T.StructField("source_index", T.LongType()),
    T.StructField("reason", T.StringType(), False),
])
MENTION_SCHEMA = T.StructType([
    T.StructField("article_id", T.StringType(), False),
    T.StructField("ticker_symbol", T.StringType()),
    T.StructField("keyword", T.StringType()),
    T.StructField("ticker_name", T.StringType()),
    T.StructField("source_page", T.LongType()),
    T.StructField("source_index", T.LongType()),
    T.StructField("source_row_position", T.LongType(), False),
    T.StructField("source_ingestion_id", T.StringType(), False),
])


def create_spark(settings: Settings) -> SparkSession:
    endpoint = settings.endpoint.removesuffix("/")
    spark = (SparkSession.builder.appName("financial-news-bronze-silver")
        .master(settings.spark_master)
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.endpoint", endpoint)
        .config("spark.hadoop.fs.s3a.access.key", settings.access_key)
        .config("spark.hadoop.fs.s3a.secret.key", settings.secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", str(endpoint.startswith("https://")).lower())
        .config("spark.hadoop.fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
        .config("spark.delta.logStore.class", "io.delta.storage.S3SingleDriverLogStore")
        .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    return spark


def build(settings: Settings, store: ObjectStore, spark: SparkSession) -> dict:
    started = time.monotonic()
    ingestion_id = file_sha256(Path(settings.source_file))
    manifest_key = f"bronze/{settings.source}/{ingestion_id}/manifest.json"
    manifest = json.loads(store.get_bytes(manifest_key))
    raw_bytes = store.get_bytes(manifest["raw_key"])
    if hashlib.sha256(raw_bytes).hexdigest() != manifest["source_file_sha256"]:
        raise RuntimeError("Bronze raw bytes differ from manifest checksum")
    rows = json.loads(raw_bytes)
    if not isinstance(rows, list) or len(rows) != manifest["record_count"]:
        raise ValueError("Bronze record count or array shape differs from manifest")

    count = len(rows)
    normalized = (spark.sparkContext.parallelize(list(enumerate(rows)), 8)
        .map(lambda pair: normalize_observation(pair[1], pair[0], ingestion_id, settings.source, settings.processing_version))
        .persist(StorageLevel.MEMORY_AND_DISK))
    valid = spark.createDataFrame(normalized.filter(lambda item: "valid" in item).map(lambda item: item["valid"]), OBSERVATION_SCHEMA).persist()
    rejects = spark.createDataFrame(normalized.filter(lambda item: "reject" in item).map(lambda item: item["reject"]), REJECT_SCHEMA).persist()
    invalid_count = rejects.count()
    valid_count = valid.count()
    if count != invalid_count + valid_count:
        raise AssertionError("Every source row must be valid or rejected")

    article_window = Window.partitionBy("source", "canonical_url").orderBy(F.length("content").desc(), F.col("source_row_position").asc())
    articles = (valid.withColumn("_rank", F.row_number().over(article_window))
        .filter(F.col("_rank") == 1)
        .select(*[field.name for field in ARTICLE_FIELDS]))
    output_count = articles.count()
    duplicate_count = valid_count - output_count
    shared_hash_groups = (articles.groupBy("content_hash")
        .agg(F.countDistinct("canonical_url").alias("url_count"))
        .filter(F.col("url_count") > 1).count())

    mention_window = Window.partitionBy("article_id", "ticker_symbol", "keyword").orderBy(F.col("source_row_position").asc())
    mentions = (valid.withColumn("_rank", F.row_number().over(mention_window))
        .filter(F.col("_rank") == 1)
        .select(*[field.name for field in MENTION_SCHEMA]))

    prefix = f"silver/{settings.source}/{ingestion_id}/{settings.processing_version}"
    (articles.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(settings.s3a(f"{prefix}/articles")))
    (mentions.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(settings.s3a(f"{prefix}/article_mentions")))
    (rejects.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(settings.s3a(f"{prefix}/rejects")))
    metrics = {
        "source_ingestion_id": ingestion_id,
        "processing_version": settings.processing_version,
        "input_count": count,
        "output_count": output_count,
        "invalid_count": invalid_count,
        "duplicate_count": duplicate_count,
        "shared_content_hash_group_count": shared_hash_groups,
        "article_mentions_count": mentions.count(),
        "processing_duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "silver_prefix": prefix,
    }
    store.put_bytes(f"{prefix}/metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2).encode())
    valid.unpersist()
    rejects.unpersist()
    normalized.unpersist()
    return metrics


def main() -> None:
    settings = Settings.from_env()
    spark = create_spark(settings)
    try:
        print(json.dumps(build(settings, S3ObjectStore(settings), spark), ensure_ascii=False, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
