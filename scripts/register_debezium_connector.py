"""Register the Debezium connector that streams article_metadata changes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests


DEFAULT_CONNECT_URL = "http://localhost:8083"
DEFAULT_CONFIG = Path("docker/debezium/connectors/postgres-article-metadata.json")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register Debezium PostgreSQL connector.")
    parser.add_argument("--connect-url", default=DEFAULT_CONNECT_URL, help="Debezium Connect URL.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Connector JSON file.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config_path = Path(args.config)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    _apply_env_overrides(payload["config"])
    name = payload["name"]
    base = args.connect_url.rstrip("/")

    response = requests.put(f"{base}/connectors/{name}/config", json=payload["config"], timeout=30)
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))


def _apply_env_overrides(config: dict[str, str]) -> None:
    overrides = {
        "database.hostname": os.getenv("DEBEZIUM_POSTGRES_HOST"),
        "database.port": os.getenv("DEBEZIUM_POSTGRES_PORT"),
        "database.user": os.getenv("DEBEZIUM_POSTGRES_USER", os.getenv("METADATA_POSTGRES_USER")),
        "database.password": os.getenv("DEBEZIUM_POSTGRES_PASSWORD", os.getenv("METADATA_POSTGRES_PASSWORD")),
        "database.dbname": os.getenv("DEBEZIUM_POSTGRES_DB", os.getenv("METADATA_POSTGRES_DB")),
        "topic.prefix": os.getenv("DEBEZIUM_TOPIC_PREFIX"),
        "slot.name": os.getenv("DEBEZIUM_SLOT_NAME"),
        "publication.name": os.getenv("DEBEZIUM_PUBLICATION_NAME"),
    }
    for key, value in overrides.items():
        if value not in (None, ""):
            config[key] = str(value)


if __name__ == "__main__":
    main()
