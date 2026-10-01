# Local release candidate `local-rc1`

## Purpose

`local-rc1` is the reproducible Phase 06 baseline for the financial-news data
platform. It runs without cloud resources and keeps the approved data path:

```text
checked-in news fixture
  -> MinIO Bronze
  -> Spark + Delta Silver
  -> Gold RAG / Gold Analytics
  -> Qdrant / DuckDB
```

Airflow orchestrates standalone jobs. PostgreSQL, Debezium, and Kafka carry
control metadata only. Qdrant and DuckDB are disposable projections.

## Clean start

Required host tools are Docker Engine, Docker Compose v2, GNU Make, and Git.

```bash
git clone <repository-url>
cd financial-news
cp .env.example .env
# Replace every change-me-* local password in .env.
make bootstrap
make phase6-acceptance
```

`make bootstrap` validates the three configuration profiles, builds the common
pipeline, metadata, and Airflow images, waits on real health checks, creates the
MinIO bucket, applies both PostgreSQL migration sets, seeds control metadata,
creates Kafka topics, registers Debezium, initializes Airflow, and writes
`artifacts/local-bootstrap-status.json`. It is safe to rerun.

## Configuration profiles

| Profile | File | Purpose |
|---|---|---|
| Local example | `config/environments/local.env.example` | Docker DNS, MinIO S3A, local services |
| Test | `config/environments/test.env` | Isolated deterministic acceptance namespace |
| Future cloud template | `config/environments/future-cloud.env.example` | Syntax validation for ABFSS and remote service endpoints; no connection |

The canonical user-facing contract is `.env.example`. `Settings` validates the
environment, provider, scheme, authority, source, and processing version before
network or Spark work begins. Local data access uses `create_object_store()` and
`configure_storage()` boundaries. ADLS execution deliberately fails with a
Phase 08 message because its byte adapter, Hadoop ABFS connector, and identity
configuration are not installed in this release.

## Reset and rebuild

```bash
# Stop services and retain all volumes.
make local-stop

# Delete only the configured Qdrant collection and DuckDB file.
make reset-derived

# Explicitly delete Phase 01-06 service volumes and data/local outputs.
make local-reset-destructive CONFIRM=DELETE_LOCAL_RELEASE_DATA
```

The destructive target does not delete legacy MongoDB, Prefect, Redis, MLflow,
Grafana, Loki, or Prometheus volumes. Spark JAR and embedding model caches are
retained because they are dependencies, not platform data.

Rebuild order:

```text
Bronze -> Silver -> Gold -> Qdrant / DuckDB
```

- Silver loss: rerun Spark from immutable Bronze.
- Gold loss: regenerate the affected/current Gold datasets from Silver.
- Qdrant loss: run `make qdrant-rebuild` from Gold RAG.
- DuckDB loss: publish the file from the existing Gold Analytics manifest.

## Acceptance fixture

`tests/fixtures/local_release/2026-09-01.json` contains a valid article, a more
complete duplicate with the same canonical URL, a second valid article, and one
malformed row. `2026-09-02.json` repeats an unchanged article and adds one new
article. Together they prove validation, rejection, deduplication, immutable
Bronze identity, replay idempotency, incremental insertion, semantic retrieval,
analytics, and rebuilds. Phase 05 recovery tests cover dated backfill, forced
reprocess, stage resume, and schema drift before Bronze.

```bash
make e2e-local
```

The command uses `local-release.test`, collection
`local_release_acceptance_v1`, and `local-release-acceptance.duckdb`. It deletes
only that isolated state. It produces `artifacts/local-release-e2e.json`.

## Test entry points

| Category | Command | Scope |
|---|---|---|
| Unit | `make test-release` | configuration, URI boundary, provider boundary, version manifest |
| CI selection | `make ci-test` | contracts, Phase 01/02 integration, Phase 01/02/04/05/06 unit tests, DAG imports |
| Integration | `make test-pipeline`, `make test-gold`, `make test-hardening` | real MinIO/Delta/Qdrant/DuckDB paths |
| Recovery/slow | `make test-recovery`, `make metadata-cdc-test` | backfill/resume/outages/restarts |
| E2E | `make e2e-local` | isolated Bronze through both serving branches and rebuilds |
| Release acceptance | `make phase6-acceptance` | audit, CI, E2E, recovery, CDC, health, report |

Generated local release reports are ignored by Git and can be regenerated.

## Reproducibility baseline

The compatibility manifest is `config/release-versions.env`. The sensitive
combinations are Spark 3.5.3 + Delta 3.2.1 + Hadoop AWS 3.3.4, and Kafka 4.1.0 +
Debezium 3.3.2.Final. Runtime images and major Python packages are pinned.

The three release images were checked for duplicate and conflicting direct
dependencies. `news-pipeline` and `metadata-tools` use compatible pinned
`confluent-kafka` and `psycopg` versions; the Airflow image pins the same
pipeline libraries and matches the base Airflow version. The broad root
`requirements.txt`, API requirements, and frontend packages belong to legacy
crawler/RAG/application modules and are not installed into the Phase 01–06
release images. They remain `UNUSED FOR NOW` for this release and were not
upgraded or removed in Phase 06.

Measured on the Phase 06 verification host (20 logical CPUs, 15.32 GiB RAM):

| Workload | Dataset | Observed duration |
|---|---|---:|
| Phase 06 isolated E2E plus all three rebuild checks | 6 raw observations across 2 files / 3 final articles | 100.911 s |
| Phase 05 incremental integration | 5 logical daily runs / 3 final articles | 133.284 s |
| Phase 05 recovery/backfill | 3-day backfill plus outage/resume and drift checks | 334.200 s |

The acceptance fixture is 2,930 bytes. `data/raw` is about 199 MiB on this
checkout. Spark runs with `local[2]`; the observed JVM memory store is about 434
MiB under its default approximately 1 GiB process allocation. These numbers are
a local reproducibility baseline and do not predict cloud throughput.

## Known limits

- Spark uses a single local driver and S3 single-driver Delta log store.
- Kafka is one KRaft broker; Airflow uses LocalExecutor.
- Qdrant is one node and has no authentication in the local Docker network.
- The deterministic Phase 06 fixture embedding verifies retrieval mechanics;
  Phase 02 tests separately verify the pinned FastEmbed adapter.
- ADLS, Azure identity, Kubernetes resources, and production secret management
  are deferred to Phase 08.
- The current tree removes the formerly tracked `.env`, but likely credentials
  remain in Git history. Revoke/rotate them and choose a coordinated history
  rewrite or clean-repository migration before the release verdict can become
  `READY FOR CLOUD MIGRATION`.
