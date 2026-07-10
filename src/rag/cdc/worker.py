"""Redpanda/Debezium CDC worker entrypoint."""
from __future__ import annotations

import argparse
import json
from typing import Any

from src.rag.cdc.content_reader import ContentDocumentReader
from src.rag.cdc.events import parse_debezium_article_event
from src.rag.cdc.processor import CdcMedallionProcessor
from src.rag.cdc.settings import CdcSettings
from src.rag.cdc.store import CdcCheckpointStore
from src.rag.config import get_settings as get_rag_settings
from src.rag.databases import QdrantRepository
from src.rag.ingestion.embedder import VoyageAIEmbedder
from src.rag.utils import get_logger
from src.scraper.config import get_settings as get_scraper_settings

logger = get_logger(__name__)


def run_worker(*, max_messages: int | None = None, once: bool = False) -> int:
    """Run the CDC consumer loop."""
    from kafka import KafkaConsumer

    cdc_settings = CdcSettings.from_env()
    scraper_settings = get_scraper_settings()
    rag_settings = get_rag_settings()

    consumer = KafkaConsumer(
        cdc_settings.kafka_topic,
        bootstrap_servers=cdc_settings.kafka_bootstrap_servers.split(","),
        group_id=cdc_settings.kafka_group_id,
        enable_auto_commit=False,
        auto_offset_reset=cdc_settings.auto_offset_reset,
        max_poll_records=cdc_settings.max_poll_records,
        value_deserializer=_deserialize_json,
        key_deserializer=_deserialize_json,
    )

    processed = 0
    logger.info(
        "CDC worker listening topic=%s bootstrap=%s group_id=%s",
        cdc_settings.kafka_topic,
        cdc_settings.kafka_bootstrap_servers,
        cdc_settings.kafka_group_id,
    )

    store = CdcCheckpointStore(scraper_settings, cdc_settings.checkpoint_table)
    store.ensure_schema()

    with ContentDocumentReader(scraper_settings) as reader, QdrantRepository(rag_settings) as qdrant:
        processor = CdcMedallionProcessor(
            reader=reader,
            checkpoint_store=store,
            qdrant=qdrant,
            embedder=VoyageAIEmbedder(rag_settings),
            rag_settings=rag_settings,
        )
        try:
            while True:
                records = consumer.poll(timeout_ms=cdc_settings.poll_timeout_ms)
                if not records:
                    if once:
                        break
                    continue

                for partition_records in records.values():
                    for record in partition_records:
                        event = parse_debezium_article_event(record.value or {})
                        if event is None:
                            consumer.commit()
                            continue
                        report = processor.process(event)
                        logger.info("CDC process report: %s", report.as_dict())
                        consumer.commit()
                        processed += 1
                        if max_messages is not None and processed >= max_messages:
                            return processed
                if once:
                    break
        finally:
            consumer.close()
            store.close()

    return processed


def _deserialize_json(payload: bytes | None) -> Any:
    if payload in (None, b""):
        return None
    return json.loads(payload.decode("utf-8"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Debezium/Redpanda CDC medallion worker.")
    parser.add_argument("--max-messages", type=int, default=None, help="Stop after processing N article events.")
    parser.add_argument("--once", action="store_true", help="Poll once and exit when no records are available.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    processed = run_worker(max_messages=args.max_messages, once=args.once)
    print(json.dumps({"processed": processed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
