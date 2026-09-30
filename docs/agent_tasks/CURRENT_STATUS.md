# Current implementation status

Verified on 2026-09-30 from base commit `0eede5d` plus the current Phase 05 working tree.

## Phase status

| Phase | Status | Verification |
|---|---|---|
| 01 — Bronze/Silver | COMPLETE | Four unit tests and one Spark/Delta integration test passed. The canonical 15,457-record sample produced 12,673 Silver articles, 25 rejects, 2,759 duplicate inputs, and 15,431 article mentions. |
| 02 — Silver/Gold | COMPLETE | Four unit tests, one Spark unit test, and one Spark integration test passed. Gold RAG, bounded Qdrant indexing/retrieval, Gold Analytics, and DuckDB publishing passed. |
| 03 — Airflow | COMPLETE | Seven DAG tests passed with zero import errors. The original DAG remains valid, and the Phase 05 incremental DAG completed an actual Airflow retry/resume smoke run. |
| 04 — Metadata CDC | COMPLETE | Seven unit tests and the full PostgreSQL → WAL → Debezium → Kafka lifecycle/recovery suite passed again after Phase 05. |
| 05 — Pipeline hardening | COMPLETE | Nine unit tests, the isolated incremental integration suite, the three-partition backfill/reprocess/recovery suite, reconciliation, rebuild, health, and Airflow smoke checks passed. |

Phase 06 has not started.

## Phase 01–04 regression evidence

The following existing gates passed against the actual local services:

```bash
make test-pipeline test-gold
make airflow-test
METADATA_CDC_PASSWORD=phase05-validation-only make metadata-cdc-test
```

Results:

- Phase 01: 4 unit tests and 1 Spark/Delta integration test passed.
- Phase 02: 4 unit tests, 1 Spark unit test, and 1 integration test passed.
- Airflow: 7 tests passed; all DAG files imported without error.
- Phase 04: 7 unit tests passed; snapshot, INSERT/UPDATE/DELETE/tombstone, Connect restart, Kafka outage recovery, and PostgreSQL restart all passed.
- The Phase 04 publication is still restricted to `control_metadata.news_sources` and `control_metadata.pipeline_configs`. Phase 05 operational tables are not captured by Debezium.

The established Phase 04 control-plane identifiers remain unchanged:

- PostgreSQL database/schema: `financial_metadata.control_metadata`
- Publication: `metadata_cdc_publication`
- Replication slot: `metadata_cdc_slot`
- Connector: `metadata-control-plane`
- Topics: `platform.control_metadata.news_sources`, `platform.control_metadata.pipeline_configs`

No article content is published to Kafka.

## Phase 05 implemented local slice

The hardened data plane is:

```text
Date-partitioned input
  -> immutable content-addressed Bronze object and logical partition reference
  -> Delta MERGE into current Silver articles/mentions/rejects
  -> affected-article manifest
  -> Delta MERGE into current Gold documents/chunks
  -> deterministic Gold Analytics refresh
  -> atomic DuckDB replacement
  -> targeted Qdrant upsert/delete
  -> cross-system reconciliation
  -> checkpoint advance after the complete publish boundary
```

The application runner supports:

```bash
make pipeline-incremental DATE=YYYY-MM-DD
make pipeline-backfill FROM=YYYY-MM-DD TO=YYYY-MM-DD
make pipeline-reprocess DATE=YYYY-MM-DD
make pipeline-resume RUN_ID=<existing-run-id>
make pipeline-status
make pipeline-reconcile
make pipeline-health
```

`reprocess` requires the explicit `--force-reprocess` guard. Backfill and reprocess runs do not advance the normal incremental checkpoint.

### Identity and state

- Application `run_id` is accepted independently of Airflow and reused on resume.
- Processing identity contains pipeline name/config hash, source, partition date, trigger type, processing version, chunker version, and embedding settings where relevant.
- Current Silver paths use `silver/current/{source}/{processing_version}/...`.
- Current Gold paths use `gold/current/rag/{source}/{processing_version}/{chunker_version}/...` and `gold/current/analytics/{source}/{processing_version}/...`.
- Bronze raw objects remain immutable and content-addressed. Logical references use `bronze/partitions/source={source}/processing_date={date}/{ingestion_id}.json`.
- Silver writes an immutable per-run affected-article manifest below `silver/operations/...`.
- Stable `article_id`, `content_hash`, `chunk_id`, and Qdrant UUID point-ID rules are preserved.

### Operational PostgreSQL schema

Migration `operations/migrations/0001_pipeline_operations.up.sql` creates schema `pipeline_operations` and:

- `pipeline_runs`
- `pipeline_stage_runs`
- `pipeline_checkpoints`
- `pipeline_partition_locks`

The tables record run/stage status, timings, counters, failures, checkpoints, and concurrency locks. They are outside the Phase 04 Debezium publication.

### Incremental and recovery semantics

- Silver Delta MERGE inserts new articles and updates changed articles by `article_id`.
- An unchanged partition produces zero affected articles.
- A metadata-only mention change marks its article affected so Gold/Qdrant metadata is refreshed while stable content/chunk/point IDs are retained.
- Gold RAG only rebuilds affected articles unless configuration identity requires a full bootstrap.
- Gold Analytics currently performs a full deterministic refresh because the local dataset is small and aggregate correctness is clearer than partial aggregate repair.
- DuckDB is published through a temporary file followed by atomic replacement; a failed build preserves the last good database and manifest.
- Qdrant applies targeted upserts and stale-point deletion for affected articles. A model/dimension identity mismatch requires a full current-state rebuild.
- Checkpoints advance only after all publish stages and reconciliation succeed.
- Resume skips previously successful stages and retries failed/incomplete stages using the same run ID.
- Resume rejects a changed source or data-shaping processing/chunking/embedding configuration before changing the stored run status; service endpoints may still change for outage recovery.
- Partition locking rejects overlap from another active run and allows the owning run to resume.

## Phase 05 test evidence

### Incremental/idempotency integration

`make test-hardening` passed the Spark/MinIO/Delta/Qdrant/DuckDB integration scenario `63c3e3de51`. The final fast unit suite contains nine tests and also passed:

- initial load: 2 affected articles
- identical replay: 0 affected articles
- one new article: 1 affected article
- one content change: 1 affected article
- one mention-only metadata change: 1 affected article
- final current state: 3 Silver articles, 3 Gold documents, 3 Gold chunks, 3 Qdrant points, and 3 DuckDB articles
- duplicate IDs, missing outputs, orphan outputs, and stale Qdrant points: all 0
- a deliberately removed Qdrant point was detected and repaired
- a simulated failure did not advance the checkpoint
- an overlapping partition lock was rejected

Evidence: `artifacts/phase5-integration-results.json`.

### Backfill/reprocess/recovery

`make test-recovery` passed scenario `c62f09bb61`:

- explicit backfill range: 2026-08-01 through 2026-08-03
- identical backfill replay affected counts: `[0, 0, 0]`
- forced reprocess succeeded without advancing the normal checkpoint
- simulated Qdrant outage occurred after Gold/Analytics/DuckDB had committed 5 documents
- checkpoint remained absent while the run was failed
- resume reused the same run ID, attempted Qdrant twice, and kept every successful upstream stage at one attempt
- checkpoint advanced to 2026-08-04 only after recovery and reconciliation
- unapproved source schema drift failed at `schema_validation` before Bronze

Evidence: `artifacts/phase5-recovery-results.json`.

### Airflow orchestration

The thin `news_incremental_pipeline` DAG delegates to the standalone runner and contains no transformation logic. It supports normal, backfill, reprocess, and resume configuration, uses `max_active_runs=1`, and does not depend on XCom for data movement.

Actual smoke evidence:

- first Airflow run: `smoke__20260929T163136689292Z__008d4d00` failed at Qdrant due to the container's inherited `nofile=1024` limit
- Compose was corrected to give Qdrant a `nofile` soft/hard limit of 65,536
- retry Airflow run: `smoke__20260929T164021686332Z__f237736e` succeeded
- application run ID reused for recovery: `phase05-airflow-smoke-v1`

The DAG schedule defaults to disabled because the checked-in sample is static; `AIRFLOW_NEWS_INCREMENTAL_SCHEDULE` enables an explicit local schedule.

### Rebuild and health evidence

- `make qdrant-rebuild` rebuilt a current-state four-chunk recovery fixture to four Qdrant points with zero failures.
- `make analytics-rebuild` rebuilt its analytics datasets and DuckDB file from four current Silver articles.
- `make pipeline-health` passed 8/8 checks for MinIO, Silver Delta, Qdrant, DuckDB, PostgreSQL, Kafka, Debezium, and Airflow using the isolated recovery configuration.

## Performance baseline

The local baseline is recorded in `artifacts/phase5-performance-baseline.json` with hardware/runtime context and limitations.

Canonical sample observations:

- Bronze first write: 2.750 s; identical rerun: 1.100 s
- Silver: 42.292 s for 15,457 inputs and 12,673 outputs
- Gold chunking: 30.258 s for 66,260 chunks
- Gold Analytics: 19.821 s
- DuckDB publish: 0.084 s
- Qdrant: 26.100 s for the bounded 96-point retrieval fixture; this is not a 66,260-point throughput claim

The latest isolated Phase 05 correctness run took 142.974 s. The three-partition recovery suite took 363.626 s. These are developer-laptop measurements with warm dependency caches and startup overhead, not production capacity results.

## Documentation and operator entry points

- `docs/pipeline-operations.md` — runbook, identity/state rules, recovery, reconciliation, health, metrics, rebuilds, and limitations
- `docs/local-architecture.md` — Phase 05 current-state architecture
- `docs/airflow-local.md` — incremental DAG configuration and smoke procedure
- `make help` — executable command list

## Current limits and Phase 06 recommendation

- Gold Analytics deliberately refreshes the full small current dataset; partition-aware aggregate repair can be evaluated when scale justifies the added state model.
- Silver mentions are cumulative for observed source metadata. A future explicit source-deletion contract is needed before safe hard-delete propagation.
- Local Kafka is a single plaintext broker and Kafka Connect REST has no authentication.
- Airflow's schedule remains opt-in while only static sample partitions exist.
- Delta retention/VACUUM policy, production secrets, backups, alert routing, managed cloud adapters, and Kubernetes remain future work.
- The next recommended phase is cloud/readiness hardening around storage adapters, retention, secrets, and deployment packaging while preserving the tested transformation contracts.

Crawler, stock streaming, Flink, event-triggered Airflow, dynamic DAG generation, UI, Power BI, LLM generation, chatbot, and recommendation features remain outside the implemented scope.
