"""Configuration boundary for object storage and processing.

The transformation modules work with logical object keys and resolved URIs.  The
local release uses the S3 compatible adapter, while a future ADLS deployment can
provide ABFSS URIs and a different object-store adapter without changing those
transformations.
"""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    environment: str = "local"
    storage_provider: str = "s3"
    storage_scheme: str = "s3a"
    endpoint: str = "http://minio:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "financial-news"
    source_file: str = "/app/data/raw/cafef_news_raw_final.json"
    source: str = "cafef.vn"
    processing_version: str = "cafef-v1.1"
    spark_master: str = "local[2]"
    processing_date: str | None = None
    run_id: str | None = None
    azure_storage_account: str | None = None
    azure_storage_container: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            environment=os.getenv("ENVIRONMENT", cls.environment),
            storage_provider=os.getenv("OBJECT_STORAGE_PROVIDER", cls.storage_provider),
            storage_scheme=os.getenv("OBJECT_STORAGE_SCHEME", cls.storage_scheme),
            endpoint=os.getenv("NEWS_STORAGE_ENDPOINT", cls.endpoint),
            access_key=os.getenv("NEWS_STORAGE_ACCESS_KEY", cls.access_key),
            secret_key=os.getenv("NEWS_STORAGE_SECRET_KEY", cls.secret_key),
            bucket=os.getenv("NEWS_STORAGE_BUCKET", cls.bucket),
            source_file=os.getenv("NEWS_SOURCE_FILE", cls.source_file),
            source=os.getenv("NEWS_SOURCE", cls.source),
            processing_version=os.getenv("NEWS_PROCESSING_VERSION", cls.processing_version),
            spark_master=os.getenv("NEWS_SPARK_MASTER", cls.spark_master),
            processing_date=os.getenv("NEWS_PROCESSING_DATE") or None,
            run_id=os.getenv("NEWS_PIPELINE_RUN_ID") or None,
            azure_storage_account=os.getenv("AZURE_STORAGE_ACCOUNT") or None,
            azure_storage_container=os.getenv("AZURE_STORAGE_CONTAINER") or None,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        errors: list[str] = []
        if self.environment not in {"local", "test", "cloud"}:
            errors.append("ENVIRONMENT must be local, test, or cloud")
        if self.storage_provider not in {"s3", "adls"}:
            errors.append("OBJECT_STORAGE_PROVIDER must be s3 or adls")
        if self.storage_provider == "s3":
            if self.storage_scheme != "s3a":
                errors.append("OBJECT_STORAGE_SCHEME must be s3a for the current S3 adapter")
            for name, value in (
                ("NEWS_STORAGE_ENDPOINT", self.endpoint),
                ("NEWS_STORAGE_ACCESS_KEY", self.access_key),
                ("NEWS_STORAGE_SECRET_KEY", self.secret_key),
                ("NEWS_STORAGE_BUCKET", self.bucket),
            ):
                if not value.strip():
                    errors.append(f"{name} is required for OBJECT_STORAGE_PROVIDER=s3")
        else:
            if self.storage_scheme != "abfss":
                errors.append("OBJECT_STORAGE_SCHEME must be abfss for ADLS Gen2")
            if not self.azure_storage_account:
                errors.append("AZURE_STORAGE_ACCOUNT is required for OBJECT_STORAGE_PROVIDER=adls")
            if not self.azure_storage_container:
                errors.append("AZURE_STORAGE_CONTAINER is required for OBJECT_STORAGE_PROVIDER=adls")
        if not self.source.strip():
            errors.append("NEWS_SOURCE is required")
        if not self.processing_version.strip():
            errors.append("NEWS_PROCESSING_VERSION is required")
        if errors:
            raise ValueError("configuration validation failed:\n- " + "\n- ".join(errors))

    @property
    def storage_authority(self) -> str:
        if self.storage_provider == "s3":
            return self.bucket
        return (
            f"{self.azure_storage_container}@{self.azure_storage_account}"
            ".dfs.core.windows.net"
        )

    def object_uri(self, key: str) -> str:
        """Resolve a logical object key without exposing a provider to business logic."""
        return f"{self.storage_scheme}://{self.storage_authority}/{key.lstrip('/')}"

    def object_key(self, uri: str) -> str:
        prefix = f"{self.storage_scheme}://{self.storage_authority}/"
        if not uri.startswith(prefix):
            raise ValueError(f"URI does not belong to configured object storage: {uri}")
        return uri[len(prefix):]

    def s3a(self, key: str) -> str:
        """Backward-compatible Phase 01-05 alias; new code uses :meth:`object_uri`."""
        return self.object_uri(key)
