"""Transactional migration runner for the isolated pipeline-operations schema."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import OperationsSettings


HISTORY_TABLE = "public.pipeline_operations_schema_migrations"


def _directory() -> Path:
    return Path(os.getenv("PIPELINE_OPERATIONS_MIGRATIONS_DIR", "/app/operations/migrations"))


def _versions() -> list[str]:
    return sorted(path.name.removesuffix(".up.sql") for path in _directory().glob("*.up.sql"))


def _connect(settings: OperationsSettings):
    import psycopg
    return psycopg.connect(**settings.connection_kwargs)


def migrate_up(settings: OperationsSettings) -> list[str]:
    applied: list[str] = []
    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} "
            "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        cursor.execute(f"SELECT version FROM {HISTORY_TABLE}")
        existing = {row[0] for row in cursor.fetchall()}
        for version in _versions():
            if version in existing:
                continue
            cursor.execute((_directory() / f"{version}.up.sql").read_text(encoding="utf-8"))
            cursor.execute(f"INSERT INTO {HISTORY_TABLE}(version) VALUES (%s)", (version,))
            applied.append(version)
    return applied


def migrate_down(settings: OperationsSettings) -> str | None:
    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (HISTORY_TABLE,))
        if cursor.fetchone()[0] is None:
            return None
        cursor.execute(f"SELECT version FROM {HISTORY_TABLE} ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        version = None if row is None else row[0]
        if version:
            cursor.execute((_directory() / f"{version}.down.sql").read_text(encoding="utf-8"))
            cursor.execute(f"DELETE FROM {HISTORY_TABLE} WHERE version = %s", (version,))
        return version


def status(settings: OperationsSettings) -> dict:
    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (HISTORY_TABLE,))
        if cursor.fetchone()[0] is None:
            applied = []
        else:
            cursor.execute(f"SELECT version FROM {HISTORY_TABLE} ORDER BY version")
            applied = [row[0] for row in cursor.fetchall()]
    return {"available": _versions(), "applied": applied}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "down", "status"))
    args = parser.parse_args()
    settings = OperationsSettings.from_env()
    result = {
        "up": migrate_up,
        "down": migrate_down,
        "status": status,
    }[args.command](settings)
    print(json.dumps({"command": args.command, "result": result}, indent=2, default=str))


if __name__ == "__main__":
    main()
