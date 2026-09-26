"""Bounded metadata CDC inspector for local demonstrations."""

from __future__ import annotations

import argparse
import json
import time
from uuid import uuid4

from .config import MetadataSettings
from .events import parse_event


def consume(settings: MetadataSettings, *, timeout: int, max_events: int, from_beginning: bool) -> dict:
    from confluent_kafka import Consumer, KafkaError

    group = settings.consumer_group if not from_beginning else f"{settings.consumer_group}-{uuid4().hex[:8]}"
    consumer = Consumer({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "group.id": group,
        "auto.offset.reset": "earliest" if from_beginning else "latest",
        "enable.auto.commit": False,
    })
    counts = {"snapshot": 0, "insert": 0, "update": 0, "delete": 0, "tombstone": 0, "errors": 0}
    latest_offset: dict[str, int] = {}
    latest_timestamp = None
    observed = 0
    deadline = time.monotonic() + timeout
    consumer.subscribe(list(settings.data_topics))
    try:
        while observed < max_events and time.monotonic() < deadline:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() != KafkaError._PARTITION_EOF:
                    counts["errors"] += 1
                    print(json.dumps({"error": str(message.error())}), flush=True)
                continue
            try:
                event = parse_event(
                    topic=message.topic(), partition=message.partition(), offset=message.offset(),
                    key=message.key(), value=message.value(),
                )
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                counts["errors"] += 1
                print(json.dumps({"topic": message.topic(), "offset": message.offset(), "error": str(exc)}), flush=True)
                continue
            print(json.dumps(event.summary(), ensure_ascii=False), flush=True)
            counts[event.operation] += 1
            latest_offset[f"{event.topic}:{event.partition}"] = event.offset
            if event.event_timestamp is not None:
                latest_timestamp = max(latest_timestamp or event.event_timestamp, event.event_timestamp)
            observed += 1
    finally:
        consumer.close()
    result = {
        "consumer_group": group,
        "events_observed": observed,
        "counts": counts,
        "latest_offsets": latest_offset,
        "latest_event_timestamp": latest_timestamp,
    }
    print(json.dumps({"summary": result}, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--max-events", type=int, default=20)
    parser.add_argument("--from-beginning", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0 or args.max_events <= 0:
        raise SystemExit("--timeout and --max-events must be positive")
    consume(MetadataSettings.from_env(), timeout=args.timeout, max_events=args.max_events, from_beginning=args.from_beginning)


if __name__ == "__main__":
    main()
