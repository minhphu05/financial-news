"""End-to-end PostgreSQL WAL -> Debezium -> Kafka CDC smoke verification."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

from .config import MetadataSettings
from .connector import wait_until_running
from .database import connect, inspect
from .events import MetadataEvent, parse_event


def _consumer(settings: MetadataSettings):
    from confluent_kafka import Consumer

    consumer = Consumer({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "group.id": f"metadata-cdc-smoke-{uuid4().hex}",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe(list(settings.data_topics))
    return consumer


def _wait_event(consumer, predicate, *, timeout: int, seen: list[MetadataEvent]) -> MetadataEvent:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = consumer.poll(1.0)
        if message is None or message.error():
            continue
        event = parse_event(
            topic=message.topic(), partition=message.partition(), offset=message.offset(),
            key=message.key(), value=message.value(),
        )
        seen.append(event)
        if predicate(event):
            print(json.dumps(event.summary(), ensure_ascii=False), flush=True)
            return event
    raise TimeoutError("Timed out waiting for the expected metadata CDC event")


def _key_is(event: MetadataEvent, field: str, value: str) -> bool:
    return event.key == {field: value}


def _verify_database_constraints(settings: MetadataSettings) -> dict:
    rejected = []
    cases = (
        (
            "blank_source_name",
            "INSERT INTO control_metadata.news_sources (source_id, source_name, source_type) VALUES (%s, '', 'snapshot')",
            (f"invalid-{uuid4().hex[:12]}",),
        ),
        (
            "nonpositive_config_version",
            """
            INSERT INTO control_metadata.pipeline_configs
                (config_id, pipeline_name, source_id, config_version)
            VALUES (%s, 'invalid', 'cafef.vn', 0)
            """,
            (f"invalid-{uuid4().hex[:12]}",),
        ),
    )
    for name, statement, values in cases:
        try:
            with connect(settings) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(statement, values)
        except Exception as exc:
            if exc.__class__.__name__ not in {"CheckViolation", "IntegrityError"}:
                raise
            rejected.append(name)
        else:
            raise AssertionError(f"Database accepted invalid metadata case: {name}")
    return {"rejected_invalid_cases": rejected}


def _verify_snapshot(settings: MetadataSettings, consumer, seen: list[MetadataEvent], timeout: int) -> list[dict]:
    expected = {
        ("news_sources", "source_id", "cafef.vn"),
        ("pipeline_configs", "config_id", "financial-news-local-v1"),
    }
    found: list[MetadataEvent] = []
    deadline = time.monotonic() + timeout
    while expected and time.monotonic() < deadline:
        event = _wait_event(consumer, lambda _: True, timeout=max(1, int(deadline - time.monotonic())), seen=seen)
        matches = [item for item in expected if event.entity == item[0] and event.operation == "snapshot" and _key_is(event, item[1], item[2])]
        for item in matches:
            expected.remove(item)
            found.append(event)
    if expected:
        raise AssertionError(f"Initial snapshot events were not observed: {sorted(expected)}")
    return [event.summary() for event in found]


def _exercise_source_lifecycle(settings: MetadataSettings, consumer, seen: list[MetadataEvent], timeout: int, label: str) -> dict:
    source_id = f"cdc-{label}-{uuid4().hex[:12]}"
    topic = f"{settings.topic_prefix}.{settings.schema}.news_sources"
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO control_metadata.news_sources
                    (source_id, source_name, source_type, enabled, description, config)
                VALUES (%s, %s, 'snapshot', true, 'Dedicated CDC smoke fixture', '{}'::jsonb)
                """,
                (source_id, f"CDC smoke {label}"),
            )
    created = _wait_event(
        consumer,
        lambda event: event.topic == topic and event.operation == "insert" and _key_is(event, "source_id", source_id),
        timeout=timeout, seen=seen,
    )

    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE control_metadata.news_sources SET enabled = false WHERE source_id = %s", (source_id,))
    updated = _wait_event(
        consumer,
        lambda event: event.topic == topic and event.operation == "update" and _key_is(event, "source_id", source_id),
        timeout=timeout, seen=seen,
    )
    if updated.before is None or updated.after is None:
        raise AssertionError("UPDATE must contain both before and after values")
    if updated.before.get("enabled") is not True or updated.after.get("enabled") is not False:
        raise AssertionError("UPDATE did not preserve the expected enabled true -> false transition")

    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE control_metadata.news_sources SET enabled = true WHERE source_id = %s", (source_id,))
    reenabled = _wait_event(
        consumer,
        lambda event: event.topic == topic and event.operation == "update" and _key_is(event, "source_id", source_id)
        and event.after is not None and event.after.get("enabled") is True,
        timeout=timeout, seen=seen,
    )
    if reenabled.before is None or reenabled.after is None:
        raise AssertionError("Re-enable UPDATE must contain both before and after values")
    if reenabled.before.get("enabled") is not False or reenabled.after.get("enabled") is not True:
        raise AssertionError("UPDATE did not preserve the expected enabled false -> true transition")

    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM control_metadata.news_sources WHERE source_id = %s", (source_id,))
    deleted = _wait_event(
        consumer,
        lambda event: event.topic == topic and event.operation == "delete" and _key_is(event, "source_id", source_id),
        timeout=timeout, seen=seen,
    )
    tombstone = _wait_event(
        consumer,
        lambda event: event.topic == topic and event.operation == "tombstone" and _key_is(event, "source_id", source_id),
        timeout=timeout, seen=seen,
    )
    if deleted.before is None or deleted.before.get("source_id") != source_id:
        raise AssertionError("DELETE event did not contain the deleted row")
    offsets = [created.offset, updated.offset, reenabled.offset, deleted.offset, tombstone.offset]
    if offsets != sorted(set(offsets)):
        raise AssertionError(f"Lifecycle offsets are not unique and ordered: {offsets}")
    return {
        "source_id": source_id,
        "stable_key": created.key,
        "operations": [created.operation, updated.operation, reenabled.operation, deleted.operation, tombstone.operation],
        "offsets": offsets,
        "update_enabled": [updated.before["enabled"], updated.after["enabled"]],
        "reenable_enabled": [reenabled.before["enabled"], reenabled.after["enabled"]],
    }


def run(mode: str, timeout: int, output: Path) -> dict:
    settings = MetadataSettings.from_env()
    connector = wait_until_running(settings, timeout)
    database = inspect(settings)
    if database["wal_level"] != "logical":
        raise AssertionError(f"Expected wal_level=logical, got {database['wal_level']}")
    if not database["publication"] or set(database["publication"]["tables"]) != set(settings.captured_tables):
        raise AssertionError("Publication does not contain exactly the approved metadata tables")
    if not database["replication_slot"] or database["replication_slot"]["plugin"] != "pgoutput":
        raise AssertionError("Debezium pgoutput replication slot is missing")
    constraints = _verify_database_constraints(settings)

    seen: list[MetadataEvent] = []
    consumer = _consumer(settings)
    try:
        snapshot = _verify_snapshot(settings, consumer, seen, timeout) if mode == "lifecycle" else []
        lifecycle = _exercise_source_lifecycle(settings, consumer, seen, timeout, mode)
    finally:
        consumer.close()
    recovered_database = inspect(settings)
    if not recovered_database["replication_slot"]["active"]:
        raise AssertionError("Replication slot did not become active after the CDC lifecycle")
    result = {
        "status": "success",
        "mode": mode,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "connector": connector,
        "database": recovered_database,
        "database_before_events": database,
        "database_constraints": constraints,
        "topics": list(settings.data_topics),
        "snapshot_events": snapshot,
        "lifecycle": lifecycle,
        "events_scanned": len(seen),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("lifecycle", "recovery", "postgres-recovery"), default="lifecycle")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", type=Path, default=Path("/app/artifacts/metadata-cdc-smoke.json"))
    args = parser.parse_args()
    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive")
    run(args.mode, args.timeout, args.output)


if __name__ == "__main__":
    main()
