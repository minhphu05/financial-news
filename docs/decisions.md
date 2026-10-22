# Architecture decisions

## ADR-001 — MinIO is the local object-store substitute

**Decision:** use MinIO through S3 APIs and S3A locally. Keep object access and
Spark filesystem settings behind configuration/adapters.  
**Reason:** it exercises remote object storage and Delta locally without an
Azure dependency.  
**Consequence:** an ADLS adapter and ABFS connector remain future, separately
approved cloud work. Phase08 implements local crawling.

## ADR-002 — Bronze, Silver, and Gold are durable

**Decision:** immutable raw bytes/manifests form Bronze, Spark/Delta forms
Silver, and versioned RAG/Analytics datasets form Gold.  
**Consequence:** Silver rebuilds from Bronze and Gold rebuilds from Silver.

## ADR-003 — Qdrant and DuckDB are derived serving systems

**Decision:** Qdrant rebuilds from Gold RAG and DuckDB publishes atomically from
Gold Analytics. Neither is a source of truth.  
**Consequence:** loss is handled by rebuild, demonstrated by `make e2e-local`.

## ADR-004 — Airflow contains orchestration only

**Decision:** DAGs invoke independently tested CLI jobs and contain dependencies,
retries, and quality gates.  
**Consequence:** deployment can move without copying transformation logic into DAGs.

## ADR-005 — Kafka Phase 04 is the metadata control plane

**Decision:** PostgreSQL control tables emit CDC through WAL/Debezium to Kafka.
Article bodies, chunks, and embeddings do not use Kafka in this release.  
**Consequence:** future stock streaming needs separate topics and design.

## ADR-006 — News processing is incremental batch

**Decision:** one logical `(source, processing_date)` partition is processed with
run state, locks, checkpoints, idempotent merge, reprocess/backfill, resume, and
reconciliation.  
**Consequence:** a Kafka-triggered article pipeline is outside Phase 06.

## ADR-007 — Cloud migration follows the local release gate

**Decision:** complete reproducible Docker Compose acceptance before provisioning
Azure or Kubernetes. `local-rc1` is the proposed baseline; no tag is created
automatically.  
**Consequence:** future cloud migration begins with approved cloud decisions and
repeats the same contracts/fixture tests on cloud adapters. Phase08 local crawler
acceptance does not clear the historical credential release gate.

## ADR-008 — Crawl ingestion reuses the durable pipeline

**Decision:** Phase08 stores exact HTTP evidence/envelopes in immutable Landing,
uses source-specific adapters at the existing Bronze boundary and calls the
Phase05 runner for downstream processing. PostgreSQL `crawler_operations`
holds URL frontier, hashes, cooldown and durable pending batches; it is excluded
from metadata CDC. Airflow schedules bounded `crawl -> publish` source jobs.\
**Consequence:** unchanged observations do not create downstream batches; failed
publication resumes without another fetch. Gold Analytics remains full refresh.
The default-manual DAG has live scheduling opt-in and a default of one article
per source per run; Phase09 makes the recurring limit configurable within source
policy bounds. Neither setting guarantees complete daily coverage. Cloud migration must preserve Landing
and crawler state along with the medallion hierarchy; Qdrant/DuckDB remain
rebuildable. See [crawler operations](crawler-operations.md) and
[migration manifest](cloud-migration-manifest.md).

## ADR-009 — Separate scheduling, source policy and operational evidence

**Decision (Phase09, 2026-10-22):** parse the DAG schedule/global opt-in from
environment; read each source's enabled/live/HTTP/replay policy at task start.
Manual runs default to fixtures. Effective crawl capacity is the minimum of the
requested limit and source cap. Publisher tasks use `all_done` to attempt durable
backlog after a fetch failure, while preserving source policy, due time and
retry budget. Automatic publication has a bounded batch cap; a source advisory
lock protects claim/reclaim of interrupted attempts. Manual replay is a bounded
operator override, with `--respect-retry` available.

**Reason:** a cron expression alone cannot govern source access or downstream
recovery. Persisted skip/block/attempt state supports diagnosis and replay
without a new website fetch. Separate heartbeat, Landing and layer timestamps
avoid treating a skipped/successful crawl as proof of fresh serving data.

**Consequence/trade-off:** conservative caps and serial execution limit throughput;
metadata changes can reduce work below the requested batch size. The design
does not provide distributed request budgets or a transaction across all stores.
Source review records and backup references require operator verification.
Real-time burn-in evidence must include actual elapsed time, scheduler/live
history, sample gaps and resources; synthetic tests only validate gate logic.
Functional verification passed, but B1 live and real 24h/72h remain pending.

**Implementation:** `airflow/dags/news_crawling_pipeline.py`,
`src/crawling/{airflow_jobs,policy,jobs,state,reporting,burnin}.py`,
`operations/migrations/0003_continuous_crawling.up.sql` and
`src/monitoring/crawler_metrics.py`. See [runbook](crawler-operations.md) and
[Phase09 engineering report](phase9-engineering-report.md).
