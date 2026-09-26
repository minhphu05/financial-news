"""Prove that PostgreSQL commits metadata while Kafka is down and CDC catches up."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from .config import MetadataSettings
from .connector import wait_until_running
from .database import connect, inspect
from .smoke import _consumer, _key_is, _wait_event


def write_while_kafka_is_down(settings: MetadataSettings, output: Path) -> dict:
    source_id = f"cdc-kafka-outage-{uuid4().hex[:12]}"
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO control_metadata.news_sources
                    (source_id, source_name, source_type, enabled, description, config)
                VALUES (%s, 'Kafka outage CDC proof', 'snapshot', true,
                        'Committed while Kafka was stopped', '{}'::jsonb)
                """,
                (source_id,),
            )
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT enabled FROM control_metadata.news_sources WHERE source_id = %s",
                (source_id,),
            )
            row = cursor.fetchone()
    if row != (True,):
        raise AssertionError("Metadata transaction was not committed while Kafka was unavailable")
    result = {
        "status": "database-committed-kafka-unavailable",
        "source_id": source_id,
        "committed_at": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def verify_after_kafka_recovery(settings: MetadataSettings, output: Path, timeout: int) -> dict:
    fixture = json.loads(output.read_text(encoding="utf-8"))
    source_id = fixture["source_id"]
    connector = wait_until_running(settings, timeout)
    topic = f"{settings.topic_prefix}.{settings.schema}.news_sources"
    seen = []
    consumer = _consumer(settings)
    try:
        inserted = _wait_event(
            consumer,
            lambda event: event.topic == topic and event.operation == "insert"
            and _key_is(event, "source_id", source_id),
            timeout=timeout, seen=seen,
        )
        with connect(settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM control_metadata.news_sources WHERE source_id = %s", (source_id,))
        deleted = _wait_event(
            consumer,
            lambda event: event.topic == topic and event.operation == "delete"
            and _key_is(event, "source_id", source_id),
            timeout=timeout, seen=seen,
        )
        tombstone = _wait_event(
            consumer,
            lambda event: event.topic == topic and event.operation == "tombstone"
            and _key_is(event, "source_id", source_id),
            timeout=timeout, seen=seen,
        )
    finally:
        consumer.close()
    database = inspect(settings)
    if not database["replication_slot"] or not database["replication_slot"]["active"]:
        raise AssertionError("Replication slot was not active after Kafka recovery")
    result = {
        "status": "success",
        "mode": "kafka-outage-recovery",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "database_commit_during_outage": fixture,
        "connector": connector,
        "database": database,
        "events": [inserted.summary(), deleted.summary(), tombstone.summary()],
        "events_scanned": len(seen),
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("write", "verify"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/app/artifacts/metadata-cdc-kafka-recovery.json"),
    )
    args = parser.parse_args()
    settings = MetadataSettings.from_env()
    if args.action == "write":
        write_while_kafka_is_down(settings, args.output)
    else:
        verify_after_kafka_recovery(settings, args.output, args.timeout)


if __name__ == "__main__":
    main()
