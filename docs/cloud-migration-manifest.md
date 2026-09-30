# Cloud migration manifest

This is a planning manifest. No migration or cloud connection has run.

## Object storage and Delta Lake

**Current:** MinIO bucket `financial-news`; S3A; immutable Bronze, Delta Silver,
Delta/Parquet Gold.  
**Target:** ADLS Gen2 or approved object storage, decision pending.  
**Data to migrate:** all Bronze objects/manifests, Silver Delta directories,
Gold RAG Delta directories, Gold Analytics Parquet and manifests, operational
quality/reconciliation artifacts stored in the lake.  
**Configuration:** provider, scheme, account/container, authentication, Spark
filesystem connector and log-store settings.  
**Code impact:** new `ObjectStore` adapter and Spark storage configuration;
transformations should not change.  
**Validation:** object and partition counts, Bronze SHA-256, sample bytes, Silver
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
secrets.  
**Code impact:** deployment and command path adjustments only; DAGs remain thin.  
**Validation:** zero import errors, DAG structure tests, one incremental DAG run,
retries and quality gates.  
**Rollback:** pause cloud DAGs and resume local scheduler with unchanged jobs.

## Metadata PostgreSQL

**Current:** PostgreSQL 17 with `control_metadata` and `pipeline_operations`.  
**Target:** managed PostgreSQL with logical replication, TBD.  
**Data:** both schemas, migration history, checkpoints/run records as approved.  
**Configuration:** host/port/database/user/TLS/password or workload identity,
WAL/slot retention.  
**Code impact:** none expected behind current settings/repository boundary.  
**Validation:** migrations, constraints, row counts, checkpoints, publication
membership, logical slot health.  
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

**Current:** one local Qdrant 1.13.1 collection.  
**Target:** Qdrant Cloud or Kubernetes, TBD.  
**Data:** no authoritative migration required; Gold chunks and embedding model
identity are the source.  
**Configuration:** URL, collection, authentication/TLS, batch sizing.  
**Code impact:** configuration only if the API remains compatible.  
**Validation:** rebuild from Gold, point IDs/count, missing/stale point check, and
documented semantic queries.  
**Rollback:** repoint to local Qdrant and rebuild from the same Gold version.

## DuckDB / analytical serving

**Current:** atomic local DuckDB file built from a Gold Analytics manifest.  
**Target:** TBD after analytical/Power BI serving requirements are approved.  
**Data:** rebuild from Gold Analytics; the DuckDB file is not authoritative.  
**Configuration:** output path or future serving adapter settings.  
**Code impact:** a new publisher adapter may be required; Gold aggregations do
not change.  
**Validation:** manifest object list, table row counts, article totals, published
queries/views.  
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
