"""Parse Debezium JSON envelopes into small control-plane event summaries."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


OPERATION_NAMES = {"r": "snapshot", "c": "insert", "u": "update", "d": "delete"}


@dataclass(frozen=True)
class MetadataEvent:
    topic: str
    partition: int
    offset: int
    key: dict[str, Any]
    operation: str
    entity: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    changed_fields: tuple[str, ...]
    event_timestamp: int | None

    def summary(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "partition": self.partition,
            "offset": self.offset,
            "key": self.key,
            "operation": self.operation,
            "entity": self.entity,
            "changed_fields": list(self.changed_fields),
            "before": self.before,
            "after": self.after,
            "event_timestamp": self.event_timestamp,
        }


def _decode_json(value: bytes | str | None) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def parse_event(*, topic: str, partition: int, offset: int, key: bytes | str, value: bytes | str | None) -> MetadataEvent:
    decoded_key = _decode_json(key)
    if not isinstance(decoded_key, dict) or not decoded_key:
        raise ValueError("CDC message key must be a nonempty JSON object")
    payload = _decode_json(value)
    entity = topic.rsplit(".", 1)[-1]
    if payload is None:
        return MetadataEvent(topic, partition, offset, decoded_key, "tombstone", entity, None, None, (), None)
    if not isinstance(payload, dict):
        raise ValueError("CDC message value must be a JSON object or tombstone null")
    op = payload.get("op")
    if op not in OPERATION_NAMES:
        raise ValueError(f"Unsupported Debezium operation: {op!r}")
    before = payload.get("before")
    after = payload.get("after")
    if before is not None and not isinstance(before, dict):
        raise ValueError("Debezium before value must be an object or null")
    if after is not None and not isinstance(after, dict):
        raise ValueError("Debezium after value must be an object or null")
    if op == "u":
        fields = sorted(key for key in set(before or {}) | set(after or {}) if (before or {}).get(key) != (after or {}).get(key))
    elif op in ("c", "r"):
        fields = sorted(after or {})
    else:
        fields = sorted(before or {})
    source = payload.get("source") or {}
    return MetadataEvent(
        topic=topic,
        partition=partition,
        offset=offset,
        key=decoded_key,
        operation=OPERATION_NAMES[op],
        entity=source.get("table", entity),
        before=before,
        after=after,
        changed_fields=tuple(fields),
        event_timestamp=payload.get("ts_ms"),
    )


class MetadataState:
    """Small idempotent current-state projection used by tests and demonstrations."""

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], dict[str, Any]] = {}
        self.seen_offsets: set[tuple[str, int, int]] = set()

    def apply(self, event: MetadataEvent) -> bool:
        position = (event.topic, event.partition, event.offset)
        if position in self.seen_offsets:
            return False
        self.seen_offsets.add(position)
        key = json.dumps(event.key, sort_keys=True, separators=(",", ":"))
        identity = (event.topic, key)
        if event.operation in ("delete", "tombstone"):
            self.values.pop(identity, None)
        elif event.after is not None:
            self.values[identity] = event.after
        return True
