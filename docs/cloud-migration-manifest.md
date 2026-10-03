# Cloud migration manifest

This is a planning manifest. No migration or cloud connection has run.

Updated on 2026-10-03 for Phase08 local crawling. Cloud migration is a later
separately approved activity. Do not infer cloud readiness from local acceptance;
the historical credential release gate remains `NOT READY`.

## Object storage and Delta Lake

**Current:** configured MinIO bucket (local default `financial-news`); S3A;
immutable crawler Landing and Bronze, Delta Silver,
Delta/Parquet Gold.  
**Target:** ADLS Gen2 or approved object storage, decision pending.  
**Data to migrate:** Landing raw HTML, observation/parsed envelopes and adapter
batch inputs/manifests, all Bronze objects/manifests, Silver Delta directories,
Gold RAG Delta directories, Gold Analytics Parquet and manifests, operational
quality/reconciliation artifacts stored in the lake.  
**Configuration:** provider, scheme, account/container, authentication, Spark
filesystem connector and log-store settings.  
**Code impact:** new `ObjectStore` adapter and Spark storage configuration;
transformations should not change.  
**Validation:** object and partition counts, Landing/batch and Bronze checksums,
envelope-to-batch lineage, sample bytes, Silver
and Gold row/key counts, Delta `_delta_log` versions/history, manifest object
lists, sample row/hash comparison, replay idempotency.  
**Rollback:** stop cloud writers and restore the MinIO profile before any source
cutover; reconcile serving projections against MinIO Gold.

## Spark compute

**Current:** pinned Spark application image, `local[2]`, Delta 3.2.1 and Hadoop
AWS 3.3.4 packages.  
**Target:** managed Spark or Spark on Kubernetes, TBD.  
**Data:** none local to compute; caches are disposable.  
**Configuration:** master/deploy mode, executor sizing, object identity,
connector packages, log destination.  
**Code impact:** deployment/config only.  
**Validation:** Phase 01/02 transformations and Phase 05 incremental/recovery
tests against migrated storage; compare schemas/counts/hashes.  
**Rollback:** run the same job entrypoints in the local image against the retained
MinIO baseline.

## Airflow

**Current:** Airflow 2.11.2 LocalExecutor and PostgreSQL 16 metadata DB.  
**Target:** managed Airflow or Kubernetes deployment, TBD.  
**Data:** optionally migrate history; DAGs and job output are authoritative
elsewhere.  
**Configuration:** executor, database, DAG delivery, logs, service endpoints,
secrets; crawler cron/live opt-in, approved source scope and batch capacity.\
**Code impact:** deployment and command path adjustments only; DAGs remain thin.  
**Validation:** zero import errors, DAG structure tests, dated-file incremental
and five-source crawl/publish runs, retries, quality gates and pending-batch
resume. Validate timezone/schedule behavior while recurring live runs are paused;
unpause only after explicit cutover approval.\
**Rollback:** pause cloud DAGs and resume local scheduler with unchanged jobs.

## Metadata PostgreSQL

**Current:** PostgreSQL 17 with `control_metadata`, `pipeline_operations` and
`crawler_operations`.\
**Target:** managed PostgreSQL with logical replication, TBD.  
**Data:** all three schemas, migration history, checkpoints/run records as
approved. Crawler state includes `source_state`, `crawl_runs`, `frontier`,
`crawl_attempts`, `batches` and five `crawler:*` source configuration rows. Preserve
URL primary keys, hashes, eligibility/cooldown timestamps and manifest/run links.\
**Configuration:** host/port/database/user/TLS/password or workload identity,
WAL/slot retention.  
**Code impact:** none expected behind current settings/repository boundary.  
**Validation:** migrations (including `0002_crawler_operations`), constraints,
row counts, checkpoints, unchanged/changed URL handling and pending-batch replay.
Inspect publication membership and logical slot health: crawler/pipeline operations
remain excluded from metadata CDC.\
**Rollback:** retain local snapshot, restore the old DSN, and recreate/repoint the
connector after resolving split-brain risk.

## Kafka and Debezium

**Current:** single Kafka 4.1.0 KRaft broker and Debezium 3.3.2.Final.  
**Target:** multi-broker/managed Kafka and managed/Kubernetes Connect, TBD.  
**Data:** metadata CDC topics and Connect config/offset/status topics; news
article content is excluded.  
**Configuration:** bootstrap servers, TLS/SASL, replication factors, connector
REST endpoint, publication/slot, credentials.  
**Code impact:** none expected in event contracts/consumer.  
**Validation:** snapshot, stable keys, update before/after, delete/tombstone,
restart, Kafka outage and PostgreSQL restart scenarios.  
**Rollback:** stop the new connector before restarting the local connector on the
retained slot/offset plan; prevent two connectors from owning the same slot.

## Qdrant

**Current:** one local Qdrant 1.13.1 service; baseline collection plus per-source
live `crawler_<source>_v1` and fixture `fixture_crawler_<source>_v1` collections.\
**Target:** Qdrant Cloud or Kubernetes, TBD.  
**Data:** no authoritative migration required; Gold chunks and embedding model
identity are the source.  
**Configuration:** URL, collection, authentication/TLS, batch sizing.  
**Code impact:** configuration only if the API remains compatible.  
**Validation:** rebuild from Gold, point IDs/count, missing/stale point check, and
documented semantic queries for each migrated live source. Fixture collections
must stay isolated; they are not production acceptance data.\
**Rollback:** repoint to local Qdrant and rebuild from the same Gold version.

## DuckDB / analytical serving

**Current:** atomic baseline local DuckDB file and per-source crawler files under
configured `CRAWLER_WORK_DIR`, built from their Gold Analytics manifests.\
**Target:** TBD after analytical/Power BI serving requirements are approved.  
**Data:** rebuild from Gold Analytics; the DuckDB file is not authoritative.  
**Configuration:** output path or future serving adapter settings.  
**Code impact:** a new publisher adapter may be required; Gold aggregations do
not change.  
**Validation:** manifest object list, table row counts, article totals, published
queries/views per source; keep `fixture-<source>.duckdb` separate from live files.\
**Rollback:** regenerate the local DuckDB file from retained Gold Analytics.

## Secrets and deployment

**Current:** ignored local `.env`, Docker Compose, local placeholder examples.  
**Target:** approved secret manager/workload identity and Kubernetes or managed
services.  
**Data:** no secret values are migrated through Git.  
**Configuration:** inject secrets at runtime; ConfigMaps/environment for
nonsecret values.  
**Code impact:** configuration/deployment only.  
**Validation:** repository secret scan, least-privilege access, rotation test,
health/readiness and clean deployment acceptance.  
**Rollback:** revoke cloud credentials and restore the local environment profile.

## Durable data validation ledger

For each copied durable prefix record source/target URI, file count, byte count,
partition count, Bronze SHA-256 manifest checks, Delta table version/history,
row/key counts, validation timestamp, tool version, and approver. Derived Qdrant
and DuckDB entries should reference the Gold manifest/version used for rebuild.

## Crawler cutover checkpoint

1. Pause the local crawler DAG and finish or explicitly record active crawl/publish
   runs. Pausing does not cancel an already running task.
2. Record the source config/processing versions, lake prefixes and a consistent
   PostgreSQL backup checkpoint. Inventory pending/failed batch IDs and their
   immutable manifests together with pipeline stage state.
3. Migrate Landing/Bronze/Silver/Gold and the three PostgreSQL schemas. Preserve
   relative object keys or validate any remapping against stored manifests/URIs.
4. Keep cloud live scheduling paused. Rebuild source-scoped serving from Gold,
   verify unchanged rechecks create no batch, changed content is published once,
   and pending batches resume without refetching websites.
5. Validate frontier backlog, freshness, parser failures, source cooldown and
   pending-publication monitoring. Approve cadence/capacity based on measured
   bounded runs; listing discovery is not an all-articles completeness guarantee.
6. Enable only the cloud scheduler after acceptance. For rollback, pause cloud
   writers first; reconcile any post-cutover lake and PostgreSQL state before
   restarting local writers. Restoring an old frontier alone can duplicate work
   or lose newer pending batches.
