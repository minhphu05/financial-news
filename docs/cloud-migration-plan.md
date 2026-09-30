# Local to cloud migration plan

## Release boundary

Phase 06 prepares migration and does not provision cloud infrastructure. The
cleaning, normalization, validation, deduplication, enrichment hook, chunking,
and analytical aggregation code consumes logical object URIs and data contracts.
Provider and deployment changes remain at configuration and adapter boundaries.

## Component mapping

| Concern | Implemented local | Future cloud target | Migration type | Transformation code impact |
|---|---|---|---|---|
| Durable object storage | MinIO, S3 API, `s3a://` | ADLS Gen2 or approved object storage | ADAPTER CHANGE + DATA MIGRATION + CONFIG ONLY | None expected |
| Delta tables | Delta 3.2.1 on MinIO | Delta on cloud object storage | CONFIG ONLY + DATA MIGRATION | None expected |
| Spark compute | Spark 3.5.3 `local[2]` container | Managed Spark or Spark on Kubernetes, TBD | DEPLOYMENT CHANGE + CONFIG ONLY | None expected |
| Orchestration | Airflow 2.11.2 LocalExecutor | Managed Airflow or Kubernetes Airflow, TBD | DEPLOYMENT CHANGE | DAG command wiring only if runtime paths change |
| Metadata database | PostgreSQL 17 Docker | Managed PostgreSQL, TBD | DATA MIGRATION + CONFIG ONLY | None expected |
| CDC | Debezium Connect 3.3.2 | Managed/Kubernetes Kafka Connect, TBD | DEPLOYMENT CHANGE + CONFIG ONLY | None expected |
| Kafka | Kafka 4.1.0, one KRaft broker | Multi-broker/managed Kafka, TBD | DEPLOYMENT CHANGE | None expected |
| Vector serving | Qdrant 1.13.1 Docker | Qdrant Cloud or Kubernetes, TBD | CONFIG ONLY; prefer rebuild | None expected |
| Analytical serving | DuckDB local file | TBD after Power BI serving evaluation | CODE CHANGE REQUIRED only for a new serving adapter | Gold Analytics unchanged |
| Secrets | Local `.env` | Approved cloud secret manager and workload identity | DEPLOYMENT CHANGE + CONFIG ONLY | None expected |
| Deployment | Docker Compose | Kubernetes | DEPLOYMENT CHANGE | None in transformations |

## ADLS Gen2 readiness checklist

- [x] Transformation code resolves logical keys through `Settings.object_uri()`.
- [x] Byte access uses the `ObjectStore` protocol and factory.
- [x] Spark filesystem settings live in `spark_storage.configure_storage()`.
- [x] The future template resolves valid `abfss://container@account.dfs.core.windows.net/...` URIs.
- [x] Bronze, Silver, and Gold remain the durable hierarchy.
- [ ] Approve an Azure storage account and container naming scheme.
- [ ] Choose authentication: managed identity, workload identity, or service principal.
- [ ] Add Hadoop Azure/ABFS connector versions compatible with Spark 3.5.3 and Delta 3.2.1.
- [ ] Implement an ADLS `ObjectStore` adapter for manifests and small object reads/writes.
- [ ] Select the Delta log-store settings required by the chosen Spark distribution.
- [ ] Test read/write/merge/history against a nonproduction ADLS container.
- [ ] Migrate Bronze/Silver/Gold and validate counts, partitions, hashes, and Delta history.

S3 path-style access, MinIO endpoint, static access keys, and
`S3SingleDriverLogStore` are isolated local adapter settings. They must not be
carried into the ABFS deployment.

## Kubernetes readiness inventory

No manifests are produced in Phase 06.

| Component | Type | Persistent state | Readiness input | Main configuration/resource concern |
|---|---|---|---|---|
| Pipeline/Spark application image | JOB | None; writes object storage | process exit + metrics | CPU/memory, Spark deploy mode, object identity |
| Airflow scheduler/webserver | SCHEDULER/CONTROL | Airflow metadata DB and logs | `/health`, scheduler job check | executor choice, DAG delivery, log storage |
| PostgreSQL | STATEFUL | control and operations schemas | `pg_isready` | HA, backups, WAL retention, logical slots |
| Kafka | STATEFUL | broker logs and Connect topics | metadata/topic request | broker count, replication, storage, TLS/SASL |
| Debezium Connect | SCHEDULER/CONTROL | offsets/config/status in Kafka | connector/task REST status | plugin image, network, database credentials |
| Qdrant | STATEFUL serving | vector index, rebuildable | collection/API request | disk, replicas, snapshots or Gold rebuild |
| MinIO | STATEFUL local only | Bronze/Silver/Gold | MinIO readiness endpoint | replaced by cloud object storage |
| DuckDB publisher | JOB | generated file | validated query/count | destination and consumer delivery, TBD |

Every service needs configuration through ConfigMaps/environment and secrets
through the chosen secret facility. Stateful components require persistent
volume and disruption/backup decisions. Jobs retain their current CLI entrypoints.

## Suggested Phase 07 sequence

1. Approve cloud providers, regions, network boundaries, identity model, and the
   analytical serving target.
2. Revoke/rotate the credentials found in historical `.env`, coordinate Git
   history remediation, and verify a fresh clone contains no secret material.
3. Create a nonproduction landing zone outside this repository's Phase 06 work.
4. Add the ADLS byte adapter and compatible ABFS Spark connector, then run the
   same fixture contracts against a temporary container.
5. Deploy PostgreSQL and migrate schemas; verify logical replication support.
6. Deploy Kafka/Connect and replay the metadata CDC lifecycle.
7. Deploy Spark job execution and Airflow; retain standalone job commands.
8. Copy durable lake data with validation in the migration manifest.
9. Rebuild Qdrant and the analytical serving layer from Gold.
10. Run Phase 01–06 regression and a cloud acceptance gate before cutover.
11. Keep MinIO available for rollback until hashes, counts, Delta history, and
    serving queries are accepted.
