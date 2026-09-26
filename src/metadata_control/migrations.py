"""Small transactional migration runner for the isolated control-plane schema."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import MetadataSettings
from .database import connect


HISTORY_TABLE = "public.metadata_control_schema_migrations"


def _directory() -> Path:
    return Path(os.getenv("METADATA_MIGRATIONS_DIR", "/app/metadata/migrations"))


def _versions() -> list[str]:
    return sorted(path.name.removesuffix(".up.sql") for path in _directory().glob("*.up.sql"))


def migrate_up(settings: MetadataSettings) -> list[str]:
    applied: list[str] = []
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            cursor.execute(f"SELECT version FROM {HISTORY_TABLE}")
            existing = {row[0] for row in cursor.fetchall()}
            for version in _versions():
                if version in existing:
                    continue
                cursor.execute((_directory() / f"{version}.up.sql").read_text(encoding="utf-8"))
                cursor.execute(f"INSERT INTO {HISTORY_TABLE}(version) VALUES (%s)", (version,))
                applied.append(version)
    print(json.dumps({"direction": "up", "applied": applied}, indent=2))
    return applied


def migrate_down(settings: MetadataSettings) -> str | None:
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", (HISTORY_TABLE,))
            if cursor.fetchone()[0] is None:
                version = None
            else:
                cursor.execute(f"SELECT version FROM {HISTORY_TABLE} ORDER BY version DESC LIMIT 1")
                row = cursor.fetchone()
                version = None if row is None else row[0]
                if version:
                    cursor.execute((_directory() / f"{version}.down.sql").read_text(encoding="utf-8"))
                    cursor.execute(f"DELETE FROM {HISTORY_TABLE} WHERE version = %s", (version,))
    print(json.dumps({"direction": "down", "reverted": version}, indent=2))
    return version


def status(settings: MetadataSettings) -> dict:
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", (HISTORY_TABLE,))
            if cursor.fetchone()[0] is None:
                applied: list[str] = []
            else:
                cursor.execute(f"SELECT version FROM {HISTORY_TABLE} ORDER BY version")
                applied = [row[0] for row in cursor.fetchall()]
    result = {"available": _versions(), "applied": applied}
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "down", "status"))
    args = parser.parse_args()
    settings = MetadataSettings.from_env()
    {"up": migrate_up, "down": migrate_down, "status": status}[args.command](settings)


if __name__ == "__main__":
    main()
