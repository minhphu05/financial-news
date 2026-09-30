"""PySpark Bronze-to-Silver transformations and Delta writes on S3A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession, Window, functions as F, types as T

from src.news_pipeline.bronze import file_sha256
from src.news_pipeline.config import Settings
from src.news_pipeline.normalize import normalize_observation
from src.news_pipeline.storage import ObjectStore, S3ObjectStore


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


@dataclass
class SilverFrames:
    ingestion_id: str
    input_count: int
    valid: DataFrame
    rejects: DataFrame
    articles: DataFrame
    mentions: DataFrame
    valid_count: int
    invalid_count: int
    output_count: int
    duplicate_count: int
    shared_hash_groups: int

    def release(self) -> None:
        self.valid.unpersist()
        self.rejects.unpersist()
        self.articles.unpersist()
        self.mentions.unpersist()


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


def _bronze_rows(settings: Settings, store: ObjectStore) -> tuple[str, list[dict]]:
    ingestion_id = file_sha256(Path(settings.source_file))
    manifest_key = f"bronze/{settings.source}/{ingestion_id}/manifest.json"
    manifest = json.loads(store.get_bytes(manifest_key))
    raw_bytes = store.get_bytes(manifest["raw_key"])
    if hashlib.sha256(raw_bytes).hexdigest() != manifest["source_file_sha256"]:
        raise RuntimeError("Bronze raw bytes differ from manifest checksum")
    rows = json.loads(raw_bytes)
    if not isinstance(rows, list) or len(rows) != manifest["record_count"]:
        raise ValueError("Bronze record count or array shape differs from manifest")
    return ingestion_id, rows


def transform(settings: Settings, store: ObjectStore, spark: SparkSession) -> SilverFrames:
    """Apply the canonical Silver normalization once for full and incremental jobs."""
    ingestion_id, rows = _bronze_rows(settings, store)
    input_count = len(rows)
    slices = max(1, min(8, input_count))
    normalized = (spark.sparkContext.parallelize(list(enumerate(rows)), slices)
        .map(lambda pair: normalize_observation(
            pair[1], pair[0], ingestion_id, settings.source, settings.processing_version
        )))
    valid = spark.createDataFrame(
        normalized.filter(lambda item: "valid" in item).map(lambda item: item["valid"]),
        OBSERVATION_SCHEMA,
    ).persist(StorageLevel.MEMORY_AND_DISK)
    rejects = spark.createDataFrame(
        normalized.filter(lambda item: "reject" in item).map(lambda item: item["reject"]),
        REJECT_SCHEMA,
    ).persist(StorageLevel.MEMORY_AND_DISK)
    invalid_count = rejects.count()
    valid_count = valid.count()
    if input_count != invalid_count + valid_count:
        raise AssertionError("Every source row must be valid or rejected")

    article_window = Window.partitionBy("source", "canonical_url").orderBy(
        F.length("content").desc(), F.col("source_row_position").asc()
    )
    articles = (valid.withColumn("_rank", F.row_number().over(article_window))
        .filter(F.col("_rank") == 1)
        .select(*[field.name for field in ARTICLE_FIELDS])
        .persist(StorageLevel.MEMORY_AND_DISK))
    output_count = articles.count()
    duplicate_count = valid_count - output_count
    shared_hash_groups = (articles.groupBy("content_hash")
        .agg(F.countDistinct("canonical_url").alias("url_count"))
        .filter(F.col("url_count") > 1).count())

    mention_window = Window.partitionBy("article_id", "ticker_symbol", "keyword").orderBy(
        F.col("source_row_position").asc()
    )
    mentions = (valid.withColumn("_rank", F.row_number().over(mention_window))
        .filter(F.col("_rank") == 1)
        .select(*[field.name for field in MENTION_SCHEMA])
        .persist(StorageLevel.MEMORY_AND_DISK))
    mentions.count()
    return SilverFrames(
        ingestion_id=ingestion_id,
        input_count=input_count,
        valid=valid,
        rejects=rejects,
        articles=articles,
        mentions=mentions,
        valid_count=valid_count,
        invalid_count=invalid_count,
        output_count=output_count,
        duplicate_count=duplicate_count,
        shared_hash_groups=shared_hash_groups,
    )


def _write_partition(settings: Settings, frames: SilverFrames) -> str:
    prefix = f"silver/{settings.source}/{frames.ingestion_id}/{settings.processing_version}"
    (frames.articles.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
        .save(settings.s3a(f"{prefix}/articles")))
    (frames.mentions.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
        .save(settings.s3a(f"{prefix}/article_mentions")))
    (frames.rejects.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
        .save(settings.s3a(f"{prefix}/rejects")))
    return prefix


def _base_metrics(settings: Settings, frames: SilverFrames, prefix: str, started: float) -> dict:
    return {
        "source_ingestion_id": frames.ingestion_id,
        "processing_version": settings.processing_version,
        "processing_date": settings.processing_date,
        "input_count": frames.input_count,
        "output_count": frames.output_count,
        "invalid_count": frames.invalid_count,
        "duplicate_count": frames.duplicate_count,
        "shared_content_hash_group_count": frames.shared_hash_groups,
        "article_mentions_count": frames.mentions.count(),
        "processing_duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "silver_prefix": prefix,
    }


def build(settings: Settings, store: ObjectStore, spark: SparkSession) -> dict:
    """Build the original immutable per-ingestion Silver snapshot."""
    started = time.monotonic()
    frames = transform(settings, store, spark)
    try:
        prefix = _write_partition(settings, frames)
        metrics = _base_metrics(settings, frames, prefix, started)
        store.put_bytes(f"{prefix}/metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2).encode())
        return metrics
    finally:
        frames.release()


def _changed_condition(left: str, right: str) -> F.Column:
    stable_fields = [
        field.name for field in ARTICLE_FIELDS
        if field.name not in {"article_id", "source_ingestion_id"}
    ]
    equal = F.lit(True)
    for name in stable_fields:
        equal = equal & F.col(f"{left}.{name}").eqNullSafe(F.col(f"{right}.{name}"))
    return ~equal


def _merge_current(
    settings: Settings, frames: SilverFrames, spark: SparkSession
) -> tuple[dict, DataFrame]:
    from delta.tables import DeltaTable

    current_prefix = f"silver/current/{settings.source}/{settings.processing_version}"
    articles_uri = settings.s3a(f"{current_prefix}/articles")
    mentions_uri = settings.s3a(f"{current_prefix}/article_mentions")
    rejects_uri = settings.s3a(f"{current_prefix}/rejects")

    if DeltaTable.isDeltaTable(spark, articles_uri):
        existing = spark.read.format("delta").load(articles_uri).persist(StorageLevel.MEMORY_AND_DISK)
        inserted = frames.articles.alias("incoming").join(
            existing.alias("current"), "article_id", "left_anti"
        ).persist(StorageLevel.MEMORY_AND_DISK)
        updated = (frames.articles.alias("incoming")
            .join(existing.alias("current"), "article_id", "inner")
            .filter(_changed_condition("incoming", "current"))
            .select("incoming.*")
            .persist(StorageLevel.MEMORY_AND_DISK))
        insert_count = inserted.count()
        update_count = updated.count()
        # Materialize IDs before MERGE. Delta invalidates cached plans that read
        # the target table after a commit; retaining the anti-join DataFrame
        # would therefore make the affected set appear empty after the merge.
        article_affected_values = [
            row.article_id for row in
            inserted.unionByName(updated).select("article_id").distinct().orderBy("article_id").collect()
        ]
        unchanged_count = frames.output_count - len(article_affected_values)
        (DeltaTable.forPath(spark, articles_uri).alias("target")
            .merge(frames.articles.alias("source"), "target.article_id = source.article_id")
            .whenMatchedUpdate(condition=_changed_condition("source", "target"), set={
                field.name: f"source.{field.name}" for field in ARTICLE_FIELDS
            })
            .whenNotMatchedInsertAll()
            .execute())
        inserted.unpersist()
        updated.unpersist()
        existing.unpersist()
    else:
        (frames.articles.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
            .save(articles_uri))
        insert_count = frames.output_count
        update_count = 0
        unchanged_count = 0
        article_affected_values = [
            row.article_id for row in frames.articles.select("article_id").distinct().orderBy("article_id").collect()
        ]

    mention_affected_values: list[str] = []
    if DeltaTable.isDeltaTable(spark, mentions_uri):
        mention_match = (
            "target.article_id = source.article_id AND "
            "target.ticker_symbol <=> source.ticker_symbol AND target.keyword <=> source.keyword"
        )
        existing_mentions = spark.read.format("delta").load(mentions_uri)
        mention_affected_values = [
            row.article_id for row in
            frames.mentions.alias("source")
                .join(existing_mentions.alias("target"), F.expr(mention_match), "left_anti")
                .select("source.article_id").distinct().orderBy("article_id").collect()
        ]
        (DeltaTable.forPath(spark, mentions_uri).alias("target")
            .merge(frames.mentions.alias("source"), mention_match)
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute())
    else:
        (frames.mentions.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
            .save(mentions_uri))

    # A new ticker/keyword association changes Gold metadata even when the
    # normalized article body itself is unchanged. Mentions are cumulative
    # because the source has no removal/tombstone contract.
    affected_values = sorted(set(article_affected_values) | set(mention_affected_values))
    affected = spark.createDataFrame(
        [(value,) for value in affected_values], "article_id string"
    ).persist()
    affected_count = len(affected_values)

    if DeltaTable.isDeltaTable(spark, rejects_uri):
        (DeltaTable.forPath(spark, rejects_uri).alias("target")
            .merge(
                frames.rejects.alias("source"),
                "target.source_ingestion_id = source.source_ingestion_id AND "
                "target.source_row_position = source.source_row_position",
            )
            .whenNotMatchedInsertAll()
            .execute())
    else:
        (frames.rejects.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
            .save(rejects_uri))

    counts = {
        "inserted_article_count": insert_count,
        "updated_article_count": update_count,
        "unchanged_article_count": unchanged_count,
        "affected_article_count": affected_count,
        "current_article_count": spark.read.format("delta").load(articles_uri).count(),
        "current_mentions_count": spark.read.format("delta").load(mentions_uri).count(),
        "current_silver_prefix": current_prefix,
        "current_articles_uri": articles_uri,
        "current_mentions_uri": mentions_uri,
    }
    return counts, affected


def build_incremental(settings: Settings, store: ObjectStore, spark: SparkSession) -> dict:
    """Merge one explicit logical partition into the durable current Silver tables."""
    if not settings.processing_date:
        raise ValueError("Incremental Silver requires NEWS_PROCESSING_DATE")
    started = time.monotonic()
    frames = transform(settings, store, spark)
    affected: DataFrame | None = None
    try:
        prefix = _write_partition(settings, frames)
        merge_counts, affected = _merge_current(settings, frames, spark)
        affected_ids = [row.article_id for row in affected.orderBy("article_id").toLocalIterator()]
        operation_id = settings.run_id or frames.ingestion_id
        affected_key = (
            f"silver/operations/source={settings.source}/processing_version={settings.processing_version}/"
            f"processing_date={settings.processing_date}/run_id={operation_id}/affected_articles.json"
        )
        store.put_bytes(
            affected_key,
            json.dumps({"article_ids": affected_ids}, indent=2, sort_keys=True).encode(),
        )
        metrics = {
            **_base_metrics(settings, frames, prefix, started),
            **merge_counts,
            "affected_article_ids_key": affected_key,
        }
        store.put_bytes(f"{prefix}/incremental_metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2).encode())
        return metrics
    finally:
        if affected is not None:
            affected.unpersist()
        frames.release()


def main() -> None:
    settings = Settings.from_env()
    spark = create_spark(settings)
    try:
        operation = build_incremental if settings.processing_date else build
        print(json.dumps(operation(settings, S3ObjectStore(settings), spark), ensure_ascii=False, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
