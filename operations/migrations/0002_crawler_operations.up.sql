-- Operational crawler state is deliberately outside the CDC publication.
CREATE SCHEMA IF NOT EXISTS crawler_operations;
CREATE TABLE crawler_operations.source_state (
 source text PRIMARY KEY,
 cooldown_until timestamptz,
 last_success_at timestamptz
);
CREATE TABLE crawler_operations.crawl_runs (
 crawl_run_id text PRIMARY KEY,
 source text NOT NULL,
 trigger_type text NOT NULL CHECK(trigger_type IN ('NORMAL','BACKFILL','RECRAWL','FIXTURE')),
 status text NOT NULL CHECK(status IN ('RUNNING','SUCCESS','PARTIAL','FAILED','BLOCKED')),
 started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz,
 metrics jsonb NOT NULL DEFAULT '{}',
 error_message text
);
CREATE INDEX crawl_runs_source_time ON crawler_operations.crawl_runs(source,started_at DESC);
CREATE TABLE crawler_operations.frontier (
 source text NOT NULL,
 canonical_url text NOT NULL,
 first_seen_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz NOT NULL DEFAULT now(),
 last_fetched_at timestamptz,
 next_eligible_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL DEFAULT 'NEW' CHECK(status IN ('NEW','SUCCESS','RETRY','PERMANENT_FAILURE','PARSE_FAILURE','BLOCKED')),
 attempts integer NOT NULL DEFAULT 0,
 content_hash text,
 observation_hash text,
 parser_version text,
 last_http_status integer,
 last_error text,
 landing_key text,
 PRIMARY KEY(source,canonical_url)
);
CREATE INDEX frontier_due ON crawler_operations.frontier(source,next_eligible_at)
 WHERE status IN ('NEW','SUCCESS','RETRY');
CREATE TABLE crawler_operations.crawl_attempts (
 attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 crawl_run_id text NOT NULL REFERENCES crawler_operations.crawl_runs(crawl_run_id),
 canonical_url text NOT NULL,
 attempted_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL,
 http_status integer,
 error_message text,
 landing_key text
);
CREATE TABLE crawler_operations.batches (
 batch_id text PRIMARY KEY,
 crawl_run_id text NOT NULL REFERENCES crawler_operations.crawl_runs(crawl_run_id),
 source text NOT NULL,
 processing_date date NOT NULL,
 manifest_key text NOT NULL,
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SUCCESS','FAILED')),
 created_at timestamptz NOT NULL DEFAULT now(),
 published_at timestamptz,
 pipeline_run_id text,
 error_message text
);
