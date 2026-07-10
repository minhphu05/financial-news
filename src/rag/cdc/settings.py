"""Settings for the Debezium + Redpanda CDC medallion worker."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CdcSettings:
    """Environment-backed settings for the CDC medallion worker."""

    kafka_bootstrap_servers: str
    kafka_topic: str
    kafka_group_id: str
    poll_timeout_ms: int
    max_poll_records: int
    auto_offset_reset: str
    checkpoint_table: str
    process_deletes: bool

    @classmethod
    def from_env(cls) -> "CdcSettings":
        return cls(
            kafka_bootstrap_servers=os.getenv("CDC_KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092"),
            kafka_topic=os.getenv("CDC_DEBEZIUM_TOPIC", "financial_metadata.core.article_metadata"),
            kafka_group_id=os.getenv("CDC_KAFKA_GROUP_ID", "financial-news-cdc-medallion"),
            poll_timeout_ms=int(os.getenv("CDC_POLL_TIMEOUT_MS", "1000")),
            max_poll_records=int(os.getenv("CDC_MAX_POLL_RECORDS", "10")),
            auto_offset_reset=os.getenv("CDC_AUTO_OFFSET_RESET", "earliest"),
            checkpoint_table=os.getenv(
                "CDC_CHECKPOINT_TABLE",
                "rag.cdc_file_processing_checkpoints",
            ),
            process_deletes=os.getenv("CDC_PROCESS_DELETES", "false").strip().lower()
            in {"1", "true", "yes", "y", "on"},
        )
