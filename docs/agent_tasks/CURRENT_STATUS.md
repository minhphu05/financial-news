# Current implementation status

Verified on 2026-09-23 from base commit `d5922ca`.

## Phase status

| Phase | Status | Verification |
|---|---|---|
| 01 — Bronze/Silver | COMPLETE | Four unit tests and one Spark/Delta integration test passed. Bronze ingestion and Silver build completed against MinIO. |
| 02 — Silver/Gold | COMPLETE | Four unit tests, one Spark unit test, and one Spark integration test passed. Gold RAG, Qdrant indexing, Gold Analytics, DuckDB build, and retrieval smoke completed. |
| 03 — Airflow | COMPLETE | Six DAG tests passed, DAG import errors were empty, and `news_silver_pipeline` completed successfully as run `smoke__20260923T043212347242Z__7d1a8cb2`, including its Gold dependency. |
| 04 — Metadata CDC | COMPLETE | Seven unit tests and the full PostgreSQL → WAL → Debezium → Kafka smoke/recovery suite passed. |

The Phase 01–03 regression was rerun after the Phase 04 services were enabled with:

```bash
make test-pipeline test-gold airflow-test pipeline-run
```

The combined command exited successfully.

## Phase 04 deployed local slice

- PostgreSQL database/schema: `financial_metadata.control_metadata`
- Tables: `news_sources`, `pipeline_configs`
- Migration: `0001_control_metadata`
- Seed keys: `cafef.vn`, `financial-news-local-v1`
- Publication: `metadata_cdc_publication`
- Logical slot: `metadata_cdc_slot` using `pgoutput`
- Connector: `metadata-control-plane`, connector and task both `RUNNING`
- Runtime versions: PostgreSQL 17, Kafka 4.1.0 in single-broker KRaft mode, Debezium 3.3.2.Final
- Topics: `platform.control_metadata.news_sources`, `platform.control_metadata.pipeline_configs`
- Topic policy: one partition and `cleanup.policy=compact`
- Keys: source table primary key `source_id`; pipeline table primary key `config_id`
- Snapshot: Debezium `initial`; restart resumes through retained Connect offsets and replication slot

No article content is published to Kafka. The MinIO/Delta news data plane and the Airflow orchestration layer remain independent of this metadata control plane.

## CDC evidence

`make metadata-cdc-test` proved:

1. Initial snapshots for both seeded tables.
2. INSERT, UPDATE `true → false`, UPDATE `false → true`, DELETE, and tombstone with a stable key.
3. Full UPDATE `before` and `after` values using `REPLICA IDENTITY FULL`.
4. Database constraints reject a blank source name and a nonpositive config version.
5. Kafka Connect restart resumes at later offsets without a new snapshot.
6. A metadata row commits while Kafka is stopped and reaches Kafka after broker recovery.
7. PostgreSQL restart retains the publication/slot and subsequent CDC events arrive.

Evidence artifacts:

- `artifacts/metadata-cdc-smoke.json` — lifecycle offsets 29–33
- `artifacts/metadata-cdc-recovery.json` — Kafka Connect recovery offsets 34–38
- `artifacts/metadata-cdc-kafka-recovery.json` — transaction committed during Kafka outage and recovered INSERT at offset 39
- `artifacts/metadata-cdc-postgres-recovery.json` — PostgreSQL recovery offsets 44–48

Final direct inspection showed `wal_level=logical`, exactly the two approved publication tables, `metadata_cdc_slot` active, compacted data topics, and connector/task state `RUNNING`.

## Current limits

- Local Kafka is a single plaintext broker; Kafka Connect REST has no authentication.
- The inspector is bounded and intended for demonstration. Consumers must tolerate at-least-once delivery and replay.
- Connector misconfiguration behavior is implemented and documented through nonzero status/wait commands; destructive failure injection is not part of the routine smoke run.
- Production secret management, multi-broker Kafka, monitoring, backups, managed cloud services, and Kubernetes remain future work.
- Phase 05 and all crawler, stock streaming, Flink, event-triggered Airflow, dynamic DAG, UI, Power BI, LLM, chatbot, and recommendation work remain unimplemented.
