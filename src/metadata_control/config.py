"""Environment-backed settings for the local metadata control plane."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re


_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required metadata configuration: {name}")
    return value


def _identifier(name: str, value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase PostgreSQL identifier")
    return value


@dataclass(frozen=True)
class MetadataSettings:
    postgres_host: str
    postgres_port: int
    database: str
    admin_user: str
    admin_password: str
    cdc_user: str
    cdc_password: str
    schema: str
    publication: str
    slot: str
    kafka_bootstrap_servers: str
    connect_url: str
    connector_name: str
    topic_prefix: str
    consumer_group: str

    @property
    def captured_tables(self) -> tuple[str, str]:
        return (
            f"{self.schema}.news_sources",
            f"{self.schema}.pipeline_configs",
        )

    @property
    def data_topics(self) -> tuple[str, str]:
        return tuple(f"{self.topic_prefix}.{table}" for table in self.captured_tables)

    @classmethod
    def from_env(cls) -> "MetadataSettings":
        try:
            port = int(os.getenv("METADATA_POSTGRES_INTERNAL_PORT", "5432"))
        except ValueError as exc:
            raise ValueError("METADATA_POSTGRES_INTERNAL_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError("METADATA_POSTGRES_INTERNAL_PORT must be between 1 and 65535")
        schema = _identifier("METADATA_CONTROL_SCHEMA", os.getenv("METADATA_CONTROL_SCHEMA", "control_metadata"))
        publication = _identifier(
            "METADATA_CDC_PUBLICATION", os.getenv("METADATA_CDC_PUBLICATION", "metadata_cdc_publication")
        )
        slot = _identifier("METADATA_CDC_SLOT", os.getenv("METADATA_CDC_SLOT", "metadata_cdc_slot"))
        cdc_user = _identifier("METADATA_CDC_USER", os.getenv("METADATA_CDC_USER", "metadata_cdc"))
        return cls(
            postgres_host=os.getenv("METADATA_POSTGRES_HOST", "postgresql"),
            postgres_port=port,
            database=os.getenv("METADATA_POSTGRES_DB", "financial_metadata"),
            admin_user=os.getenv("METADATA_POSTGRES_USER", "metadata_user"),
            admin_password=_required("METADATA_POSTGRES_PASSWORD"),
            cdc_user=cdc_user,
            cdc_password=_required("METADATA_CDC_PASSWORD"),
            schema=schema,
            publication=publication,
            slot=slot,
            kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            connect_url=os.getenv("DEBEZIUM_CONNECT_URL", "http://debezium:8083").rstrip("/"),
            connector_name=os.getenv("DEBEZIUM_CONNECTOR_NAME", "metadata-control-plane"),
            topic_prefix=os.getenv("METADATA_CDC_TOPIC_PREFIX", "platform"),
            consumer_group=os.getenv("METADATA_CONSUMER_GROUP", "metadata-inspector"),
        )
