-- Never silently discard active/skip evidence to make a rollback fit old enums.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM crawler_operations.batches WHERE status='RUNNING') OR
    EXISTS(SELECT 1 FROM crawler_operations.crawl_runs WHERE status='SKIPPED' OR trigger_type='SCHEDULED')
 THEN RAISE EXCEPTION 'Pause jobs and archive/review Phase09 operational rows before downgrade';
 END IF;
END $$;
DROP INDEX crawler_operations.batches_due;
ALTER TABLE crawler_operations.batches DROP COLUMN attempts, DROP COLUMN last_attempt_at, DROP COLUMN next_eligible_at;
ALTER TABLE crawler_operations.source_state DROP COLUMN blocked_at, DROP COLUMN blocked_reason;
ALTER TABLE crawler_operations.batches DROP CONSTRAINT batches_status_check;
ALTER TABLE crawler_operations.batches ADD CONSTRAINT batches_status_check CHECK(status IN ('PENDING','SUCCESS','FAILED'));
ALTER TABLE crawler_operations.crawl_runs DROP CONSTRAINT crawl_runs_status_check;
ALTER TABLE crawler_operations.crawl_runs ADD CONSTRAINT crawl_runs_status_check CHECK(status IN ('RUNNING','SUCCESS','PARTIAL','FAILED','BLOCKED'));
ALTER TABLE crawler_operations.crawl_runs DROP CONSTRAINT crawl_runs_trigger_type_check;
ALTER TABLE crawler_operations.crawl_runs ADD CONSTRAINT crawl_runs_trigger_type_check CHECK(trigger_type IN ('NORMAL','BACKFILL','RECRAWL','FIXTURE'));
