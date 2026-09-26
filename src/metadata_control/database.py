"""PostgreSQL connection helpers and CDC privilege provisioning."""

from __future__ import annotations

import argparse
import json

from .config import MetadataSettings


def connect(settings: MetadataSettings, *, cdc: bool = False, autocommit: bool = False):
    import psycopg

    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.database,
        user=settings.cdc_user if cdc else settings.admin_user,
        password=settings.cdc_password if cdc else settings.admin_password,
        autocommit=autocommit,
    )


def provision(settings: MetadataSettings) -> dict:
    from psycopg import sql

    with connect(settings, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (settings.cdc_user,))
            role = sql.Identifier(settings.cdc_user)
            password = sql.Literal(settings.cdc_password)
            if cursor.fetchone() is None:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN REPLICATION PASSWORD {}").format(role, password),
                )
            else:
                cursor.execute(sql.SQL("ALTER ROLE {} WITH LOGIN REPLICATION PASSWORD {}").format(role, password))
            cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(settings.database), role))
            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(settings.schema), role))
            cursor.execute(
                sql.SQL("GRANT SELECT ON TABLE {}, {} TO {}").format(
                    sql.Identifier(settings.schema, "news_sources"),
                    sql.Identifier(settings.schema, "pipeline_configs"),
                    role,
                )
            )
            cursor.execute(
                sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}").format(
                    sql.Identifier(settings.schema), role
                )
            )
            cursor.execute("SELECT 1 FROM pg_publication WHERE pubname = %s", (settings.publication,))
            if cursor.fetchone() is None:
                cursor.execute(
                    sql.SQL("CREATE PUBLICATION {} FOR TABLE {}, {}").format(
                        sql.Identifier(settings.publication),
                        sql.Identifier(settings.schema, "news_sources"),
                        sql.Identifier(settings.schema, "pipeline_configs"),
                    )
                )
    result = {
        "cdc_user": settings.cdc_user,
        "publication": settings.publication,
        "captured_tables": list(settings.captured_tables),
    }
    print(json.dumps(result, indent=2))
    return result


def inspect(settings: MetadataSettings) -> dict:
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SHOW wal_level")
            wal_level = cursor.fetchone()[0]
            cursor.execute(
                "SELECT pubname, pubinsert, pubupdate, pubdelete, pubtruncate FROM pg_publication WHERE pubname = %s",
                (settings.publication,),
            )
            publication = cursor.fetchone()
            cursor.execute(
                "SELECT schemaname || '.' || tablename FROM pg_publication_tables WHERE pubname = %s ORDER BY 1",
                (settings.publication,),
            )
            tables = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT slot_name, plugin, slot_type, active, database FROM pg_replication_slots WHERE slot_name = %s",
                (settings.slot,),
            )
            slot = cursor.fetchone()
    result = {
        "wal_level": wal_level,
        "publication": None if publication is None else {
            "name": publication[0], "insert": publication[1], "update": publication[2],
            "delete": publication[3], "truncate": publication[4], "tables": tables,
        },
        "replication_slot": None if slot is None else {
            "name": slot[0], "plugin": slot[1], "type": slot[2], "active": slot[3], "database": slot[4],
        },
    }
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("provision", "inspect"))
    args = parser.parse_args()
    settings = MetadataSettings.from_env()
    (provision if args.command == "provision" else inspect)(settings)


if __name__ == "__main__":
    main()
