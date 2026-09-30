"""Transactional run, stage, checkpoint, and partition-lock operations."""

from __future__ import annotations

from datetime import date
import json
from typing import Any

from .config import OperationsSettings


class PartitionLockedError(RuntimeError):
    pass


class OperationsRepository:
    def __init__(self, settings: OperationsSettings):
        import psycopg
        from psycopg.rows import dict_row

        # Autocommit prevents read helpers from opening an outer transaction
        # that would otherwise roll back all nested stage transactions on close.
        self.connection = psycopg.connect(
            **settings.connection_kwargs, row_factory=dict_row, autocommit=True
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "OperationsRepository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def begin_run(
        self,
        *,
        run_id: str,
        pipeline_name: str,
        source: str,
        trigger_type: str,
        partition_start: date,
        partition_end: date,
        force_reprocess: bool,
        parameters: dict[str, Any],
        airflow_dag_id: str | None = None,
        airflow_run_id: str | None = None,
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_operations.pipeline_runs(
                    run_id, pipeline_name, source, trigger_type, partition_start,
                    partition_end, force_reprocess, status, parameters,
                    airflow_dag_id, airflow_run_id, started_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'RUNNING',%s::jsonb,%s,%s,now())
                """,
                (
                    run_id, pipeline_name, source, trigger_type, partition_start,
                    partition_end, force_reprocess, json.dumps(parameters),
                    airflow_dag_id, airflow_run_id,
                ),
            )

    def resume_run(self, run_id: str) -> dict:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_operations.pipeline_runs
                SET status='RUNNING', error_message=NULL, finished_at=NULL
                WHERE run_id=%s
                RETURNING *
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(f"Unknown pipeline run: {run_id}")
            return dict(row)

    def get_run(self, run_id: str) -> dict:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM pipeline_operations.pipeline_runs WHERE run_id=%s", (run_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(f"Unknown pipeline run: {run_id}")
            return dict(row)

    def finish_run(self, run_id: str, status: str, error_message: str | None = None) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_operations.pipeline_runs
                SET status=%s, error_message=%s, finished_at=now()
                WHERE run_id=%s
                """,
                (status, error_message, run_id),
            )

    def acquire_partition(
        self, pipeline_name: str, source: str, processing_date: date, run_id: str
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_operations.pipeline_partition_locks(
                    pipeline_name, source, processing_date, run_id
                ) VALUES (%s,%s,%s,%s)
                ON CONFLICT (pipeline_name, source, processing_date) DO UPDATE
                SET acquired_at=now()
                WHERE pipeline_operations.pipeline_partition_locks.run_id = EXCLUDED.run_id
                RETURNING run_id
                """,
                (pipeline_name, source, processing_date, run_id),
            )
            owner = cursor.fetchone()
            if owner is None:
                cursor.execute(
                    """
                    SELECT run_id FROM pipeline_operations.pipeline_partition_locks
                    WHERE pipeline_name=%s AND source=%s AND processing_date=%s
                    """,
                    (pipeline_name, source, processing_date),
                )
                held = cursor.fetchone()
                raise PartitionLockedError(
                    f"Partition {source}/{processing_date} is already owned by "
                    f"{held['run_id'] if held else 'another run'}"
                )

    def release_partition(
        self, pipeline_name: str, source: str, processing_date: date, run_id: str
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM pipeline_operations.pipeline_partition_locks
                WHERE pipeline_name=%s AND source=%s AND processing_date=%s AND run_id=%s
                """,
                (pipeline_name, source, processing_date, run_id),
            )

    def start_stage(
        self,
        run_id: str,
        stage_name: str,
        input_lineage: dict[str, Any] | None = None,
    ) -> int:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(MAX(attempt), 0) + 1 AS attempt
                FROM pipeline_operations.pipeline_stage_runs
                WHERE run_id=%s AND stage_name=%s
                """,
                (run_id, stage_name),
            )
            attempt = cursor.fetchone()["attempt"]
            cursor.execute(
                """
                INSERT INTO pipeline_operations.pipeline_stage_runs(
                    run_id, stage_name, attempt, status, input_lineage
                ) VALUES (%s,%s,%s,'RUNNING',%s::jsonb)
                RETURNING stage_run_id
                """,
                (run_id, stage_name, attempt, json.dumps(input_lineage or {})),
            )
            return cursor.fetchone()["stage_run_id"]

    def finish_stage(
        self,
        stage_run_id: int,
        status: str,
        *,
        metrics: dict[str, Any] | None = None,
        output_lineage: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_operations.pipeline_stage_runs
                SET status=%s, metrics=%s::jsonb, output_lineage=%s::jsonb,
                    error_message=%s, finished_at=now()
                WHERE stage_run_id=%s
                """,
                (
                    status, json.dumps(metrics or {}), json.dumps(output_lineage or {}),
                    error_message, stage_run_id,
                ),
            )

    def successful_stage(self, run_id: str, stage_name: str) -> dict | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM pipeline_operations.pipeline_stage_runs
                WHERE run_id=%s AND stage_name=%s AND status='SUCCESS'
                ORDER BY attempt DESC LIMIT 1
                """,
                (run_id, stage_name),
            )
            row = cursor.fetchone()
            return None if row is None else dict(row)

    def advance_checkpoint(
        self, pipeline_name: str, source: str, processing_date: date, run_id: str
    ) -> None:
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_operations.pipeline_checkpoints(
                    pipeline_name, source, last_successful_partition, last_successful_run_id
                ) VALUES (%s,%s,%s,%s)
                ON CONFLICT (pipeline_name, source) DO UPDATE
                SET last_successful_partition = GREATEST(
                        pipeline_operations.pipeline_checkpoints.last_successful_partition,
                        EXCLUDED.last_successful_partition
                    ),
                    last_successful_run_id = CASE
                        WHEN EXCLUDED.last_successful_partition >= pipeline_operations.pipeline_checkpoints.last_successful_partition
                        THEN EXCLUDED.last_successful_run_id
                        ELSE pipeline_operations.pipeline_checkpoints.last_successful_run_id
                    END,
                    updated_at = now()
                """,
                (pipeline_name, source, processing_date, run_id),
            )

    def checkpoint(self, pipeline_name: str, source: str) -> dict | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM pipeline_operations.pipeline_checkpoints
                WHERE pipeline_name=%s AND source=%s
                """,
                (pipeline_name, source),
            )
            row = cursor.fetchone()
            return None if row is None else dict(row)

    def run_stages(self, run_id: str) -> list[dict]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM pipeline_operations.pipeline_stage_runs
                WHERE run_id=%s ORDER BY stage_name, attempt
                """,
                (run_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def inspect(self, limit: int = 20) -> dict:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM pipeline_operations.pipeline_runs ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            runs = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT * FROM pipeline_operations.pipeline_checkpoints ORDER BY pipeline_name, source"
            )
            checkpoints = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT * FROM pipeline_operations.pipeline_partition_locks ORDER BY acquired_at"
            )
            locks = [dict(row) for row in cursor.fetchall()]
        return {"runs": runs, "checkpoints": checkpoints, "locks": locks}
