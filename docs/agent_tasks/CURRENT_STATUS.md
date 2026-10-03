# Current implementation status

Latest verification: 2026-10-03, Phase08 crawler branch based on `e300b09`.
Earlier Phase01–07 checkpoint details below retain their original dates. No Azure resource, Kubernetes manifest, Terraform, Helm, tag, Git
commit, or push was created.

## Release verdict

**`NOT READY FOR CLOUD MIGRATION`**

The Phase 06 implementation and every functional local test pass. The release
gate remains closed because `.env` was committed in the first repository commit
and later commits also exposed credential-shaped values. The current tree removes the
file from tracking and ignores future `.env` files, but deletion from the next
commit does not remove the values from Git history.

Affected credential names, with values intentionally omitted:

- `API_TOKEN`
- `JWT_SECRET_KEY`
- `OPENROUTER_API_KEY`
- `VOYAGE_API_KEY`
- `GEMINI_API_KEY`

Required owner action before changing the verdict: revoke or rotate the exposed
credentials, choose a coordinated history rewrite or clean repository migration,
then scan a fresh clone and rerun `make phase6-acceptance`.

## Phase status

| Phase | Implementation | Latest verification |
|---|---|---|
| 01 — Bronze/Silver | COMPLETE | Four unit tests and the real Spark/Delta integration passed. The post-change CI integration also passed. |
| 02 — Silver/Gold | COMPLETE | Four unit tests, one Spark unit test, and the full MinIO/Delta/Qdrant/DuckDB integration passed after Phase 06 changes. |
| 03 — Airflow | COMPLETE | Seven DAG tests passed; all DAGs import with zero errors. Bootstrap starts healthy scheduler and webserver instances. |
| 04 — Metadata CDC | COMPLETE | Seven unit tests plus snapshot, lifecycle, Connect restart, Kafka outage, and PostgreSQL restart tests passed. |
| 05 — Pipeline hardening | COMPLETE | Nine unit tests, the full incremental integration, and the full recovery/backfill suite passed after Phase 06 changes. |
| 06 — Local release/cloud readiness | IMPLEMENTED; RELEASE BLOCKED | Clean bootstrap, configuration profiles, E2E, rebuilds, health, and regression checks passed. Security audit keeps the aggregate report at FAIL. |
| 07 — Local monitoring/observability | COMPLETE | Fresh Phase07 acceptance passed; original 6 dashboards/12 alerts remain functional. Phase08 adds one dashboard and three alerts. |
| 08 — Multisource crawling/ingestion | COMPLETE (LOCAL) | `make phase8-acceptance` exit 0; 26 crawler tests, 8 DAG tests, 6 monitoring unit tests, 2 real observability tests, all-five fixture scheduler run, all-five tiny live E2E. |

## Verified local architecture

```text
Existing dated news data
  -> MinIO Bronze (immutable bytes + manifest)
  -> Spark cleaning/validation/deduplication
  -> Delta Silver
  -> enrichment hook
  -> Gold RAG documents/chunks -> Qdrant
  -> Gold Analytics           -> DuckDB

Airflow -> standalone job commands

PostgreSQL control_metadata
  -> WAL / pgoutput
  -> Debezium metadata-control-plane
  -> Kafka platform.control_metadata.*

Pipeline/service/native metrics
  -> Prometheus
  -> Grafana dashboards + local alert rules
```

Bronze, Silver, and Gold remain the durable hierarchy. Qdrant and DuckDB are
derived serving systems and were proven rebuildable. Kafka carries only control
metadata; news article content is not sent through Kafka.

## Phase 01–05 verification

The full pre-change baseline passed with the original phase commands. The
following post-change regression evidence covers every modified execution path:

- Phase 01: four unit tests and one Spark/Delta integration test passed.
- Phase 02: four unit tests, one Spark unit test, and one full integration test
  passed. The only warning was Python `ResourceWarning` output for Spark test
  sockets after the successful test.
- Phase 03: seven DAG structure/import tests passed; `airflow dags
  list-import-errors` returned no rows.
- Phase 04: seven unit tests passed. The connector and task were `RUNNING` on
  Debezium `3.3.2.Final` after each recovery case.
- Phase 05 incremental integration scenario `4e9e2939c2` passed in 133.284 s:
  final state was 3 Silver articles, 3 Gold documents, 3 chunks, 3 Qdrant
  points, and 3 DuckDB articles; duplicates, missing outputs, orphan outputs,
  and stale points were all zero.
- Phase 05 recovery scenario `64a7ceeca9` passed in 334.200 s: repeated backfill
  affected counts were `[0, 0, 0]`, Qdrant required two attempts, upstream
  successful stages remained at one attempt, and schema drift failed before
  Bronze.

The canonical CafeF snapshot results remain unchanged: 15,457 raw records,
12,673 Silver articles, 25 rejects, 2,759 duplicate inputs, 15,431 mentions,
12,673 Gold documents, and 66,260 chunks.

## Phase 06 implementation

### Configuration and storage boundaries

- `Settings` now validates environment, provider, scheme, source, processing
  version, and provider-specific authority before network or Spark work.
- Transformation modules resolve logical keys through `object_uri()` and obtain
  byte storage through `create_object_store()`.
- Provider-specific Spark filesystem configuration lives in
  `spark_storage.configure_storage()`.
- The local provider remains MinIO/S3A. The future-cloud profile can express a
  valid ABFSS authority but fails clearly before execution because the ADLS byte
  adapter, Hadoop ABFS connector, and cloud identity belong to a later approved cloud phase.
- Local, test, and future-cloud profiles validate successfully.
- Service endpoints, ports, model paths, Qdrant collection, DuckDB path, and
  credentials are externalized through environment variables and Compose.

### Bootstrap and reset

A controlled destructive reset removed only Phase 01–06 containers, their
persistent data volumes, and generated `data/local` files. From that state:

```bash
METADATA_CDC_PASSWORD=phase06-bootstrap-local-only make bootstrap
```

passed and initialized MinIO, Qdrant, PostgreSQL, Kafka, Debezium, Airflow,
migrations, metadata seed, topics, connector, and storage. Running the same
bootstrap command a second time also passed, proving practical idempotency.

Eight long-running release services were running and healthy after bootstrap:
MinIO, Qdrant, metadata PostgreSQL, Kafka, Debezium, Airflow PostgreSQL,
Airflow scheduler, and Airflow webserver.

`make local-stop`, `make reset-derived`, and the guarded
`make local-reset-destructive CONFIRM=DELETE_LOCAL_RELEASE_DATA` provide soft
stop, derived-state reset, and controlled destructive reset paths.

### E2E and rebuildability

`make e2e-local` passed in 100.911 s using two stable, isolated fixture files:

- initial 4 raw observations produced 2 valid Silver articles, 1 reject, and 1
  duplicate;
- exact replay produced zero affected articles;
- the next partition produced 1 new and 1 unchanged article;
- final reconciliation found 3 Silver articles, 3 Gold documents, 3 chunks, 3
  Qdrant points, and 3 DuckDB articles with no duplicate, missing, orphan, or
  stale records;
- semantic retrieval returned the expected article;
- analytical query returned 3 articles;
- current Gold was deleted and rebuilt from Silver;
- the isolated Qdrant collection was deleted and rebuilt from Gold RAG;
- the isolated DuckDB file was deleted and rebuilt directly from Gold Analytics.

No recrawl or external paid API was needed.

### Metadata CDC evidence

- database/schema: `financial_metadata.control_metadata`
- captured tables: `control_metadata.news_sources`,
  `control_metadata.pipeline_configs`
- publication: `metadata_cdc_publication`
- replication slot: `metadata_cdc_slot`
- connector: `metadata-control-plane`
- topics: `platform.control_metadata.news_sources`,
  `platform.control_metadata.pipeline_configs`
- snapshot mode: `initial`
- event keys: table primary keys (`source_id` and `config_id`)
- delete strategy: Debezium delete event followed by a tombstone

The acceptance run observed the initial snapshot and stable keys, UPDATE
before/after images, DELETE/tombstone, connector restart recovery, an event
committed while Kafka was unavailable, and CDC resumption after PostgreSQL
restart.

## Full Phase 06 acceptance

Command:

```bash
METADATA_CDC_PASSWORD=phase06-bootstrap-local-only make phase6-acceptance
```

Functional results:

| Check | Result |
|---|---|
| Local/test/future-cloud profile validation | PASS |
| Compose validation | PASS |
| Data contract drift check | PASS |
| Combined Phase 01/02/05/06 unit selection | PASS — 22 tests |
| Phase 01 Spark integration | PASS |
| Phase 02 Spark unit | PASS |
| Phase 04 unit tests | PASS — 7 tests |
| Airflow DAG tests/imports | PASS — 7 tests, zero import errors |
| Isolated E2E and all rebuild checks | PASS |
| Phase 05 backfill/recovery/schema drift | PASS |
| CDC lifecycle and all restart/outage tests | PASS |
| MinIO/Silver/Qdrant/DuckDB/PostgreSQL/Kafka/Debezium/Airflow health | PASS — 8/8 |
| Configuration/security audit | FAIL — historical credentials |
| Aggregate `artifacts/local-release-report.json` | FAIL, as required by the security gate |

The `make` command exits with code 2 only because `phase6-report` refuses to
mark the release ready while the security audit is failing. The functional
subcommands completed successfully.

## Machine coupling and secret audit

The Phase 01–07 runtime/configuration scan found:

- zero developer-specific absolute paths;
- zero static container IP dependencies;
- zero current credential-pattern matches;
- Docker DNS names, `/app` container paths, and host `localhost` endpoints only
  where they are explicit local defaults;
- 61 legacy NER notebook/script files with developer paths, classified
  `UNUSED FOR NOW` because they do not participate in the released data pipeline.

`.env` is staged for removal from Git and `.gitignore` excludes `.env` variants
while retaining `.env.example`. Placeholder templates contain no real cloud
credentials. Historical secret values are never printed by the audit or report.

The release Dockerfiles also passed a dependency sanity review. Their direct
runtime packages are pinned, shared Kafka/PostgreSQL client versions agree, and
the Airflow package matches its base image. The broader root/API/frontend
dependency sets serve legacy application modules outside the Phase 01–07
runtime, so Phase 06 did not perform an unrelated upgrade or removal.

## Local baseline

Verification host:

- 20 logical CPUs
- 15.32 GiB RAM
- Spark `local[2]`
- two acceptance fixture files, 2,930 bytes total
- Docker `29.8.1`
- Latest Phase 06 E2E rerun: 102.832 s
- Phase 05 incremental integration: 133.284 s
- Phase 05 recovery/backfill: 334.200 s

These measurements include local Docker/Spark startup overhead and warm caches.
They are reproducibility observations, not production capacity claims.

## Cloud migration readiness

The mapping and migration manifest are documented in:

- `docs/cloud-migration-plan.md`
- `docs/cloud-migration-manifest.md`
- `docs/local-release-checklist.md`
- `docs/decisions.md`

MinIO can be replaced at the configuration, object-store adapter, Spark
filesystem adapter, and deployment layers without rewriting cleaning,
normalization, deduplication, chunking, or aggregation logic. A later approved cloud phase still
must add an ADLS byte adapter, compatible Hadoop ABFS dependencies, Azure
identity, and nonproduction integration tests.

Kubernetes readiness is documented as a workload/state/readiness inventory.
No manifests exist yet. The inventory records jobs, control processes, stateful
services, persistent state, health signals, and configuration concerns so a
later deployment can preserve the tested CLI boundaries.

## Phase 07 monitoring and observability

The Phase 07 monitoring plane is metrics-first and observes the existing local
release without copying transformation logic:

- Prometheus `2.53.0` persists seven days by default and scrapes the pipeline
  exporter, PostgreSQL, Kafka, Airflow StatsD, MinIO, Qdrant, cAdvisor and node
  exporter.
- Grafana `11.1.0` provisions its Prometheus datasource and six dashboards from
  repository JSON: platform overview, operations, data quality, freshness,
  metadata CDC and local resources.
- The read-only pipeline exporter derives run, stage, record, quality,
  reconciliation, freshness, DuckDB, Debezium and CDC slot metrics from Phase
  05 operational state and structured service APIs.
- The PostgreSQL monitoring role is `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`
  and `NOREPLICATION`; it has `pg_monitor` plus read access to
  `control_metadata` and `pipeline_operations`.
- Twelve Prometheus rules cover service/Qdrant/connector availability, Kafka
  lag, pipeline failure/no recent success, Silver/Gold staleness, Qdrant stage
  failure, data quality, reconciliation and CDC slot state.
- Metrics use bounded pipeline/source/stage values. The acceptance audit found
  no `run_id`, article/chunk ID, URL, error text, stack, SQL or credential
  labels.

### Phase 07 acceptance evidence

`artifacts/phase7-acceptance.json` finished `PASS`:

- critical targets were healthy, all required metric categories were present,
  six dashboards were visible through the Grafana API, and 12 rules loaded;
- two explicit normal runs completed in 45.508 s and 51.460 s;
- an isolated malformed fixture recorded one invalid row and fired
  `DataQualityGateFailed` while valid data followed the Phase 05 reject policy;
- stopping Qdrant produced a failed downstream run in 52.516 s, increased the
  failed-stage total from 2 to 3 and fired the failure alert; restarting Qdrant
  and resuming the same run completed in 29.197 s and resolved service health;
- pausing Debezium made connector health fail and its alert fire while Kafka
  and PostgreSQL stayed healthy; resuming restored the connector and resolved
  the alert;
- final monitoring health was 8/8: Prometheus, Grafana, pipeline exporter,
  PostgreSQL, Kafka metrics, Debezium, MinIO metrics and Qdrant metrics.

Post-change regression also passed: data-contract drift was empty, 23 combined
unit tests passed, Phase 01 Spark integration passed, Phase 02 Spark test passed,
seven Phase 04 tests passed, seven Airflow tests passed with zero DAG import
errors, the isolated Phase 06 E2E/rebuild path passed in 102.832 s, and Phase 06
health remained 8/8.

The baseline contains eight Phase 07 successful operational runs: 39.129 s
minimum, 44.147 s mean and 47.058 s maximum. Mean Silver merge was 25.590 s,
Gold RAG 5.412 s, Gold Analytics 4.161 s, Qdrant 1.729 s, DuckDB 1.305 s and
reconciliation 2.325 s. These are descriptive local observations. On this
Docker/cgroup-v2 host, cAdvisor lacks stable Compose container-name labels, so
the resource dashboard reports honest host-level node-exporter observations
rather than claiming per-service measurements.

Implementation and reproduction details are in
`docs/monitoring-observability.md`; measurement context is in
`docs/local-monitoring-baseline.md`.

## Exact clean reproduction

```bash
git clone <repository-url>
cd financial-news
cp .env.example .env
# Replace every change-me-* value with a local development secret.
make local-reset-destructive CONFIRM=DELETE_LOCAL_RELEASE_DATA
make bootstrap
make phase6-acceptance
make monitoring-up
make monitoring-test
make phase7-acceptance
```

Until Git history remediation is complete, expect `make phase6-acceptance` to
finish its functional tests and then return nonzero with the security audit as
the sole failed gate. Run the monitoring commands separately after that expected
release-gate result. Regenerate ignored Phase 06 evidence at any time with
`make phase6-report`.

## Required blocker decision

Root cause: `.env` was tracked in commit `9f56478`; adding `.gitignore` now does
not remove earlier objects from Git history.

Realistic options:

1. Revoke/rotate the credentials and coordinate a `git filter-repo` history
   rewrite plus force push. This preserves most repository history but every
   collaborator must re-clone or carefully reset. **Recommended.**
2. Revoke/rotate credentials and retain history. This minimizes repository
   disruption, but the release cannot satisfy the no-secret-history gate.
3. Revoke/rotate credentials and create a new clean repository from the current
   tree. This gives the cleanest boundary but loses normal commit ancestry.

After the owner completes option 1, scan a fresh clone and rerun the complete
acceptance command. Do not tag `local-rc1` until the report is PASS.

## Historical cloud migration recommendation (deferred)

1. Resolve the credential/history blocker and make the Phase 06 report PASS.
2. Approve cloud provider, region, network, identity, and analytical serving
   choices.
3. Create a nonproduction landing zone outside the Phase 01–07 local release.
4. Implement the ADLS byte adapter and ABFS Spark adapter at the existing
   boundaries; run the same fixture contracts against a temporary container.
5. Deploy and migrate PostgreSQL, then verify logical replication support.
6. Deploy Kafka/Debezium and replay the metadata lifecycle and recovery tests.
7. Deploy Spark execution and Airflow while retaining standalone job commands.
8. Copy Bronze/Silver/Gold using the migration manifest; validate hashes,
   counts, partitions, and Delta history.
9. Rebuild Qdrant and the selected analytical serving projection from Gold.
10. Run the full cloud acceptance gate before cutover and keep MinIO available
    until rollback criteria expire.

Crawler, frontend, LLM chatbot, Power BI, stock streaming, Flink, Azure
provisioning, ADLS migration, Kubernetes, Terraform, and Helm remain outside
Phase 07.

## Phase08 checkpoint — multisource crawling (2026-10-03)

Branch: `feature/multisource-news-crawler`; base commit `e300b09`.
The authorized Phase08 is now **local crawling**, with cloud migration deferred.
No commit, push, cloud resource or article Kafka queue has been created.

Status: **COMPLETE (LOCAL)** — `make phase8-acceptance` returned exit 0.
Cloud release remains blocked by historical credentials; no cloud work started.

### Previous platform verification

Fresh pre-change `make phase6-acceptance` completed functional prerequisites but
returned exit 2 at the release/security report. `make phase7-acceptance` returned
exit 0. Evidence is in `artifacts/phase8-baseline.json`. The security gate remains
**NOT READY FOR CLOUD MIGRATION**: historical keys include `API_TOKEN`,
`JWT_SECRET_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `VOYAGE_API_KEY`.
Values are deliberately omitted. There is no news-site API key requirement for
these five public HTTP crawlers.

### Implemented boundaries

- Five source-specific raw payloads/common crawl envelopes, observed selectors,
  offline synthetic fixtures and source profiles/contracts.
- Robots-aware ordinary HTTP, same-host redirects, bounded pacing/retries,
  persistent Retry-After cooldown and no bypass.
- `crawler_operations` migration `0002_crawler_operations`: source state, crawl
  runs, frontier, attempts and durable batch outbox. Existing migration `0001`
  and canonical schemas remain unchanged.
- Separate crawler source configuration rows in existing
  `control_metadata.news_sources.config`; direct PostgreSQL reads, no CDC
  consumer dependency. Publication still captures only the two metadata tables.
- Exact HTML plus source payload/lineage in MinIO Landing; adapters emit the
  existing JSON-array Bronze contract. Metadata unsupported by current canonical
  normalization stays in Landing; no fabricated ticker/NER fields.
- Existing Phase05 runner handles Silver/Gold/Qdrant/DuckDB publication and resume.
  Source-specific serving matches existing reconciliation. Sample CafeF input and
  its processing version remain supported.
- Default-manual `news_crawling_pipeline`: five source groups, 10 tasks, one active
  DAG run/task; scheduled live crawling requires explicit configuration opt-in.
- Seventh Grafana dashboard **Financial News — Multisource Crawling**, bounded
  crawler metrics and three new alerts (15 total local alert rules).

### Evidence already verified

- 26 parser/HTTP/Landing/PostgreSQL/frontier tests passed, including bounded
  backfill, explicit recrawl, content reversion, retry cooldown and isolation.
- Eight DAG/import/structure tests passed.
- Six monitoring unit tests (three existing + three crawler) passed.
- Two-source scheduler-managed fixture DAG smoke passed.
- Final five-source fixture vertical slice passed in 229.472 s (earlier run
  370.206 s), with actual local
  FastEmbed/Delta/Qdrant/DuckDB, changed/unchanged behavior and outbox recovery.
- Five live sources each fetched one eligible article and passed full downstream
  reconciliation: CafeF 3 chunks/points; VnExpress 7; Tuổi Trẻ 3; Thanh Niên 12;
  Báo Mới 14. Total: 5 articles/documents, 39 chunks/Qdrant points, 5 DuckDB articles
  across source-specific files. See `artifacts/phase8-live-e2e.json`.

Final acceptance also passed a real **all-five-source scheduler DAG**: 10/10
source tasks SUCCESS, plus two exporter/Prometheus/Grafana integration tests.
`promtool` loaded 15 valid rules. Fresh full Gold regression passed (4 unit tests,
1 Spark unit, 1 complete serving integration). Fresh Phase05 regression passed
(9 unit tests, real incremental integration in 116.295 s).

The first Phase05 incremental regression attempt encountered S3 HTTP 400 while
reading a parquet file during analytics. The repeat passed. Root cause was not
established; no speculative transformation workaround was introduced. Both results
are recorded in `artifacts/phase8-regression.json`.

Acceptance evidence: `artifacts/phase8-acceptance.json`,
`artifacts/phase8-fixture-e2e.json`, `artifacts/phase8-live-smoke.json`,
`artifacts/phase8-live-e2e.json`, `artifacts/phase8-baseline.json`,
`artifacts/phase8-regression.json`. Full engineering report:
`docs/phase8-engineering-report.md`.

### Operational entry points

See `docs/crawler-operations.md` for initialization, fixture acceptance, explicit
live smoke, controlled recrawl/backfill, source config, storage lineage, serving
isolation, scheduler opt-in, monitoring and recovery. Default next activity is
bounded local collection/validation; cloud deployment remains outside this phase.

### Documentation consistency checkpoint — 2026-10-03

Documentation was checked against the crawler DAG, jobs, frontier SQL, migration,
storage factory and existing Phase08 evidence. README now includes the live input
path in its main architecture/status, rather than only in an appended section.
The daily scheduling example is 06:00 `Asia/Ho_Chi_Minh`, with explicit live
opt-in; this documentation update did not enable a schedule or run a live crawl.

Current scheduled default remains one article per source per run (hard maximum
20). Manual run conf does not update recurring defaults; the Airflow limit
overrides the seeded metadata batch-size default. Six-hour recheck eligibility
is evaluated at a selected crawl run, within seven days since first discovery;
it is not an independent timer. Listing discovery and batch limits do not imply
complete daily coverage. Gold Analytics still performs a full refresh.

Cloud plan/manifest now inventory immutable Landing and the `crawler_operations`
frontier/hash/cooldown/outbox state, per-source serving, consistent cutover and
rollback. Obsolete references assigning cloud deployment to Phase08 were removed
from current release guides. Legacy scraper/planning documents are labeled as
historical, with links to the current path. No contracts, runtime code, services
or release verdict changed; previous test evidence above remains the recorded
execution result, not a newly executed acceptance run.

Documentation validation: all 19 changed Markdown files passed local link/linked
heading and fenced-block checks. Static checks matched the documented DAG/source
defaults, migration table names, Make targets and recorded live/acceptance JSON.
`git diff --check` passed after fixing Markdown trailing whitespace. No runtime
test suite was rerun for this documentation-only change.
