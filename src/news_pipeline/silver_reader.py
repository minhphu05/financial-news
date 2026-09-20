"""Reusable Delta access layer for downstream Silver consumers."""

from pyspark.sql import DataFrame, SparkSession

from .gold_config import GoldSettings
from .silver import ARTICLE_FIELDS


class SilverArticleRepository:
    def __init__(self, spark: SparkSession, settings: GoldSettings):
        self.spark = spark
        self.settings = settings

    def articles(self) -> DataFrame:
        frame = self.spark.read.format("delta").load(self.settings.silver_articles_uri)
        expected = [field.name for field in ARTICLE_FIELDS]
        if frame.columns != expected:
            raise ValueError(f"Silver article contract mismatch: expected {expected}, got {frame.columns}")
        return frame

    def mentions(self) -> DataFrame:
        frame = self.spark.read.format("delta").load(self.settings.silver_mentions_uri)
        expected = {"article_id", "ticker_symbol", "keyword", "source_ingestion_id"}
        if not expected.issubset(frame.columns):
            raise ValueError(f"Silver mentions contract mismatch: missing {sorted(expected - set(frame.columns))}")
        return frame
