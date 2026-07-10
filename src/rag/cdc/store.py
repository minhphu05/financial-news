"""PostgreSQL checkpoint store for CDC medallion processing."""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.scraper.config import ScraperSettings


class CdcCheckpointStore:
    """Persist article-file processing state in PostgreSQL."""

    def __init__(self, scraper_settings: ScraperSettings, table_name: str) -> None:
        self._settings = scraper_settings
        self._table = table_name
        self._engine: Engine = create_engine(self._settings.postgres_dsn, pool_pre_ping=True, future=True)

    def ensure_schema(self) -> None:
        ddl = f"""
        CREATE SCHEMA IF NOT EXISTS rag;
        CREATE TABLE IF NOT EXISTS {self._table} (
            article_id UUID PRIMARY KEY,
            event_key TEXT NOT NULL,
            source_id UUID,
            crawl_job_id UUID,
            url TEXT NOT NULL,
            url_hash VARCHAR(64),
            json_path TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'RECEIVED',
            bronze_document JSONB,
            silver_document JSONB,
            qdrant_points INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            bronze_completed_at TIMESTAMPTZ,
            silver_completed_at TIMESTAMPTZ,
            gold_completed_at TIMESTAMPTZ,
            failed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_cdc_file_processing_status
            ON {self._table} (status);
        CREATE INDEX IF NOT EXISTS ix_cdc_file_processing_updated_at
            ON {self._table} (updated_at DESC);
        CREATE INDEX IF NOT EXISTS ix_cdc_file_processing_json_path
            ON {self._table} (json_path);
        """
        with self._engine.begin() as connection:
            connection.execute(text(ddl))

    def close(self) -> None:
        self._engine.dispose()

    def is_completed(self, article_id: str) -> bool:
        stmt = text(f"SELECT status FROM {self._table} WHERE article_id = :article_id")
        with self._engine.begin() as connection:
            status = connection.execute(stmt, {"article_id": article_id}).scalar_one_or_none()
        return status == "GOLD_DONE"

    def mark_received(self, event) -> None:
        stmt = text(
            f"""
            INSERT INTO {self._table} (
                article_id, event_key, source_id, crawl_job_id, url, url_hash, json_path,
                status, received_at, updated_at
            ) VALUES (
                :article_id, :event_key, :source_id, :crawl_job_id, :url, :url_hash, :json_path,
                'RECEIVED', now(), now()
            )
            ON CONFLICT (article_id) DO UPDATE SET
                event_key = EXCLUDED.event_key,
                source_id = EXCLUDED.source_id,
                crawl_job_id = EXCLUDED.crawl_job_id,
                url = EXCLUDED.url,
                url_hash = EXCLUDED.url_hash,
                json_path = EXCLUDED.json_path,
                status = CASE
                    WHEN {self._table}.status = 'GOLD_DONE' THEN {self._table}.status
                    ELSE 'RECEIVED'
                END,
                last_error = NULL,
                updated_at = now()
            """
        )
        with self._engine.begin() as connection:
            connection.execute(stmt, _event_params(event))

    def mark_started(self, article_id: str) -> None:
        self._execute_status(
            article_id,
            "PROCESSING",
            extra_sql="started_at = COALESCE(started_at, now()), attempts = attempts + 1, last_error = NULL",
        )

    def mark_bronze_done(self, article_id: str, document: dict[str, Any]) -> None:
        stmt = text(
            f"""
            UPDATE {self._table}
            SET status = 'BRONZE_DONE',
                bronze_document = CAST(:document AS JSONB),
                bronze_completed_at = now(),
                updated_at = now()
            WHERE article_id = :article_id
            """
        )
        with self._engine.begin() as connection:
            connection.execute(stmt, {"article_id": article_id, "document": json.dumps(document, ensure_ascii=False)})

    def mark_silver_done(self, article_id: str, document: dict[str, Any]) -> None:
        stmt = text(
            f"""
            UPDATE {self._table}
            SET status = 'SILVER_DONE',
                silver_document = CAST(:document AS JSONB),
                silver_completed_at = now(),
                updated_at = now()
            WHERE article_id = :article_id
            """
        )
        with self._engine.begin() as connection:
            connection.execute(stmt, {"article_id": article_id, "document": json.dumps(document, ensure_ascii=False)})

    def mark_gold_done(self, article_id: str, qdrant_points: int) -> None:
        stmt = text(
            f"""
            UPDATE {self._table}
            SET status = 'GOLD_DONE',
                qdrant_points = :qdrant_points,
                gold_completed_at = now(),
                failed_at = NULL,
                last_error = NULL,
                updated_at = now()
            WHERE article_id = :article_id
            """
        )
        with self._engine.begin() as connection:
            connection.execute(stmt, {"article_id": article_id, "qdrant_points": qdrant_points})

    def mark_failed(self, article_id: str, error: str) -> None:
        stmt = text(
            f"""
            UPDATE {self._table}
            SET status = 'FAILED',
                last_error = :error,
                failed_at = now(),
                updated_at = now()
            WHERE article_id = :article_id
            """
        )
        with self._engine.begin() as connection:
            connection.execute(stmt, {"article_id": article_id, "error": error[:4000]})

    def _execute_status(self, article_id: str, status: str, *, extra_sql: Optional[str] = None) -> None:
        extra = f", {extra_sql}" if extra_sql else ""
        stmt = text(
            f"""
            UPDATE {self._table}
            SET status = :status,
                updated_at = now()
                {extra}
            WHERE article_id = :article_id
            """
        )
        with self._engine.begin() as connection:
            connection.execute(stmt, {"article_id": article_id, "status": status})


def _event_params(event) -> dict[str, Any]:
    return {
        "article_id": event.article_id,
        "event_key": event.event_key,
        "source_id": event.source_id or None,
        "crawl_job_id": event.crawl_job_id or None,
        "url": event.url,
        "url_hash": event.url_hash or None,
        "json_path": event.json_path,
    }
