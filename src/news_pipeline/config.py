"""Configuration boundary for object storage and processing."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    endpoint: str = "http://minio:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "financial-news"
    source_file: str = "/app/data/raw/cafef_news_raw_final.json"
    source: str = "cafef.vn"
    processing_version: str = "cafef-v1.1"
    spark_master: str = "local[2]"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            endpoint=os.getenv("NEWS_STORAGE_ENDPOINT", cls.endpoint),
            access_key=os.getenv("NEWS_STORAGE_ACCESS_KEY", cls.access_key),
            secret_key=os.getenv("NEWS_STORAGE_SECRET_KEY", cls.secret_key),
            bucket=os.getenv("NEWS_STORAGE_BUCKET", cls.bucket),
            source_file=os.getenv("NEWS_SOURCE_FILE", cls.source_file),
            source=os.getenv("NEWS_SOURCE", cls.source),
            processing_version=os.getenv("NEWS_PROCESSING_VERSION", cls.processing_version),
            spark_master=os.getenv("NEWS_SPARK_MASTER", cls.spark_master),
        )

    def s3a(self, key: str) -> str:
        return f"s3a://{self.bucket}/{key.lstrip('/')}"
