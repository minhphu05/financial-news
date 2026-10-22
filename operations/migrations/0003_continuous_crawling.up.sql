-- Additive operational state only; canonical contracts and CDC are unchanged.
ALTER TABLE crawler_operations.crawl_runs DROP CONSTRAINT crawl_runs_status_check;
ALTER TABLE crawler_operations.crawl_runs ADD CONSTRAINT crawl_runs_status_check
 CHECK(status IN ('RUNNING','SUCCESS','PARTIAL','FAILED','BLOCKED','SKIPPED'));
ALTER TABLE crawler_operations.crawl_runs DROP CONSTRAINT crawl_runs_trigger_type_check;
ALTER TABLE crawler_operations.crawl_runs ADD CONSTRAINT crawl_runs_trigger_type_check
 CHECK(trigger_type IN ('NORMAL','BACKFILL','RECRAWL','FIXTURE','SCHEDULED'));
ALTER TABLE crawler_operations.source_state ADD COLUMN blocked_at timestamptz;
ALTER TABLE crawler_operations.source_state ADD COLUMN blocked_reason text;
ALTER TABLE crawler_operations.batches ADD COLUMN attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0);
ALTER TABLE crawler_operations.batches ADD COLUMN last_attempt_at timestamptz;
ALTER TABLE crawler_operations.batches ADD COLUMN next_eligible_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE crawler_operations.batches DROP CONSTRAINT batches_status_check;
ALTER TABLE crawler_operations.batches ADD CONSTRAINT batches_status_check
 CHECK(status IN ('PENDING','RUNNING','SUCCESS','FAILED'));
CREATE INDEX batches_due ON crawler_operations.batches(source,next_eligible_at,created_at)
 WHERE status<>'SUCCESS';
