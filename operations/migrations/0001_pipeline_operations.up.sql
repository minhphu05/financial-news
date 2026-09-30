CREATE SCHEMA IF NOT EXISTS pipeline_operations;

CREATE TABLE pipeline_operations.pipeline_runs (
    run_id text PRIMARY KEY,
    pipeline_name varchar(128) NOT NULL CHECK (btrim(pipeline_name) <> ''),
    source varchar(255) NOT NULL CHECK (btrim(source) <> ''),
    trigger_type varchar(16) NOT NULL CHECK (trigger_type IN ('NORMAL', 'BACKFILL', 'REPROCESS', 'MANUAL')),
    partition_start date NOT NULL,
    partition_end date NOT NULL,
    force_reprocess boolean NOT NULL DEFAULT false,
    status varchar(16) NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'SKIPPED')),
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(parameters) = 'object'),
    airflow_dag_id text,
    airflow_run_id text,
    error_message text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (partition_end >= partition_start),
    CHECK (trigger_type <> 'REPROCESS' OR force_reprocess)
);

CREATE TABLE pipeline_operations.pipeline_stage_runs (
    stage_run_id bigserial PRIMARY KEY,
    run_id text NOT NULL REFERENCES pipeline_operations.pipeline_runs(run_id) ON DELETE CASCADE,
    stage_name varchar(128) NOT NULL CHECK (btrim(stage_name) <> ''),
    attempt integer NOT NULL CHECK (attempt > 0),
    status varchar(16) NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'SKIPPED')),
    input_lineage jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(input_lineage) = 'object'),
    output_lineage jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(output_lineage) = 'object'),
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metrics) = 'object'),
    error_message text,
    started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamptz,
    UNIQUE (run_id, stage_name, attempt)
);

CREATE TABLE pipeline_operations.pipeline_checkpoints (
    pipeline_name varchar(128) NOT NULL,
    source varchar(255) NOT NULL,
    last_successful_partition date NOT NULL,
    last_successful_run_id text NOT NULL REFERENCES pipeline_operations.pipeline_runs(run_id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pipeline_name, source)
);

CREATE TABLE pipeline_operations.pipeline_partition_locks (
    pipeline_name varchar(128) NOT NULL,
    source varchar(255) NOT NULL,
    processing_date date NOT NULL,
    run_id text NOT NULL REFERENCES pipeline_operations.pipeline_runs(run_id) ON DELETE CASCADE,
    acquired_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pipeline_name, source, processing_date)
);

CREATE INDEX pipeline_runs_status_idx
    ON pipeline_operations.pipeline_runs(status, created_at DESC);
CREATE INDEX pipeline_stage_runs_run_idx
    ON pipeline_operations.pipeline_stage_runs(run_id, stage_name, attempt DESC);
