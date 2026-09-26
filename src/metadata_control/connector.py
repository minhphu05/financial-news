"""Register and inspect the Debezium PostgreSQL connector through Kafka Connect."""

from __future__ import annotations

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import MetadataSettings


def _request(url: str, *, method: str = "GET", payload: dict | None = None) -> dict | list:
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            if response.status == 204:
                return {}
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Kafka Connect returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach Kafka Connect at {url}: {exc.reason}") from exc


def _redact(value):
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key == "database.password" else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def connector_config(settings: MetadataSettings) -> dict[str, str]:
    return {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "tasks.max": "1",
        "database.hostname": settings.postgres_host,
        "database.port": str(settings.postgres_port),
        "database.user": settings.cdc_user,
        "database.password": settings.cdc_password,
        "database.dbname": settings.database,
        "topic.prefix": settings.topic_prefix,
        "plugin.name": "pgoutput",
        "schema.include.list": settings.schema,
        "table.include.list": ",".join(settings.captured_tables),
        "slot.name": settings.slot,
        "slot.drop.on.stop": "false",
        "publication.name": settings.publication,
        "publication.autocreate.mode": "disabled",
        "snapshot.mode": "initial",
        "tombstones.on.delete": "true",
        "key.converter": "org.apache.kafka.connect.json.JsonConverter",
        "key.converter.schemas.enable": "false",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter.schemas.enable": "false",
        "heartbeat.interval.ms": "10000",
    }


def wait_for_api(settings: MetadataSettings, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    last = "Kafka Connect REST API is not ready"
    while time.monotonic() < deadline:
        try:
            _request(f"{settings.connect_url}/connectors")
            return
        except RuntimeError as exc:
            last = str(exc)
        time.sleep(2)
    raise TimeoutError(f"Kafka Connect REST API did not become ready within {timeout}s: {last}")


def register(settings: MetadataSettings, timeout: int = 120) -> dict:
    wait_for_api(settings, timeout)
    name = quote(settings.connector_name, safe="")
    url = f"{settings.connect_url}/connectors/{name}/config"
    result = _request(url, method="PUT", payload=connector_config(settings))
    safe = _redact(result)
    print(json.dumps({"name": settings.connector_name, "config": safe}, indent=2))
    return result


def status(settings: MetadataSettings) -> dict:
    name = quote(settings.connector_name, safe="")
    result = _request(f"{settings.connect_url}/connectors/{name}/status")
    print(json.dumps(result, indent=2))
    return result


def wait_until_running(settings: MetadataSettings, timeout: int = 120) -> dict:
    deadline = time.monotonic() + timeout
    last = "Kafka Connect is not ready"
    while time.monotonic() < deadline:
        try:
            current = status(settings)
            connector_state = current.get("connector", {}).get("state")
            tasks = current.get("tasks", [])
            if connector_state == "RUNNING" and tasks and all(task.get("state") == "RUNNING" for task in tasks):
                return current
            last = json.dumps(current)
        except RuntimeError as exc:
            last = str(exc)
        time.sleep(2)
    raise TimeoutError(f"Connector did not become RUNNING within {timeout}s: {last}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("register", "status", "wait"))
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    settings = MetadataSettings.from_env()
    if args.command == "register":
        register(settings, args.timeout)
    elif args.command == "status":
        status(settings)
    else:
        wait_until_running(settings, args.timeout)


if __name__ == "__main__":
    main()
