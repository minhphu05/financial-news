# Current implementation status

**Chốt pilot 23/10/2026, rà soát từ trưa đến 22:58 +07:** phiên năm nguồn chạy
đủ **14:04:58–18:04:58**, thu **50 mẫu**, tự pause DAG/tắt live cả năm nguồn
khoảng 18:05. Không collection error/hard-stop/sample gap lớn; tám scheduled
cycles không overlap. **Pilot verdict PENDING**, không PASS: Tuổi Trẻ có lỗi
preflight/repair; Báo Mới còn sáu scheduled PARTIAL do unsupported redirect.
Riêng tám cycles tạo **34 bài**, toàn cửa sổ từ trưa tạo **45 bài mới/270 chunks**,
**45 batch reconciliation PASS**, backlog live cuối kỳ=0. Pilot report có
38 new observations/39 reconciliation PASS do cohort start và stage-completion
khác nhau; không cộng phiên hai nguồn bị hủy vào bốn giờ. B1 đã có live evidence
cả năm nhưng **chưa chốt clean overall PASS**; formal 24h/72h vẫn PENDING,
Phase09 chưa DONE, cloud NO-GO. Xem [báo cáo chốt phiên](../phase9-pilot-report-2026-10-23.md)
và [pilot guide](../phase9-pilot-guide-vi.md).

Hiện DAG paused, năm live policies=false, expiry đã hết; không có live run mới
trong ledger từ deadline đến 22:58. Cron 30 phút/global scheduled-live=true còn
giữ từ pilot, chưa restore manual environment; **không còn là trạng thái mọi env
flag đều off**. Services vẫn chạy để xem dashboard. `runtime.json` đã bổ sung
closeout, giữ launch metadata riêng; report/samples gốc không bị ghi đè.

Dashboard review 23/10/2026: sửa topic filter Kafka exporter/PromQL CDC, timestamp,
Instant tables/stats, filters và legend; 7 dashboards/68 target queries kiểm được.
Xem [hướng dẫn đọc Grafana](../grafana-dashboard-guide-vi.md) và
[review report](../grafana-dashboard-review-2026-10-23.md). Không đổi pilot/cloud gate.

Latest work checkpoint: **2026-10-23**, Phase10 local audit/prevention and design
pack prepared on baseline `240823c`. **Phase10 NOT DONE; cloud NO-GO.** Issuer
invalidation/history remediation, required P09 live/burn-in and owner sign-off
remain blocked/pending; dependency/image findings also remain open. See the
[Phase10 report](../phase10-security-cloud-readiness-report.md). The Phase09 and
documentation checkpoints below retain their actual execution dates/provenance.

Phase10 verification: 16 local guard/readiness tests PASS; selected runtime suite
passed 77 pipeline/crawler/PostgreSQL tests, 17 monitoring/metadata tests, 10 DAG
tests, five-source fixture E2E and monitoring/two crawler observability tests.
A separate metadata CDC lifecycle smoke succeeded. These are scoped current
checks, not full P05/07/08/09 acceptance reruns or replacement-credential tests.
Working-tree/index scan PASS; history scan FAIL (three pattern hits), existing
checker FAIL (five variable names). Exact commands/UTC/image/package metadata and
NO-GO decision are in ignored `artifacts/phase10/`; no raw secret values retained.
At the Phase10 audit checkpoint, cron/live switch and all five source live
policies were off. The later pilot settings and closeout supersede that runtime
snapshot; see the dated pilot section above.

Runbooks/design pack and evidence index are complete for review; issuer/history,
remote CI/protection and authorized cloud sign-off remain owner-dependent. The
existing `.gitignore` also ignores `docs/thesis/` and `docs/present-demo/`; their
Phase10 updates are local and are not included in a normal Git diff. No source
pipeline/canonical contract, local secret or history checker was changed.

Latest implementation checkpoint: **2026-10-22**, Phase09 developed on `feat/Phase-9`, base `583a382`.
Documentation review on 2026-10-22 started at `8bd1f7e` after the repository workflow merged Phase09; the branch/base above describe the implementation run, not the current checkout.
Functional verification is **PASS** (eight full-run checks plus a corrected scheduling recheck, all exit 0); real 24h/72h burn-in is **PENDING**, so Phase09 is not DONE. See the Phase09 section/report below.
Phase01–08 checkpoint details retain their original dates, including the 2026-10-03 Phase08 verification based on `e300b09`; those changes were subsequently committed/merged by the repository workflow. No Azure resource, Kubernetes manifest, Terraform, Helm, tag, Git commit, or push was created during the Phase09 work.

## Release verdict

**`NOT READY FOR CLOUD MIGRATION`**

The Phase06 implementation and its recorded functional local tests passed at that checkpoint. Current Phase09 verification is recorded separately below. The release
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
| 09 — Continuous local operations/burn-in | FUNCTIONAL PASS; PILOT PENDING; BURN-IN PENDING | Nine functional checkpoints PASS. Five-source 4h window completed with 50 samples/8 scheduled cycles; redirects keep pilot/B1 clean acceptance pending. Formal 24h/72h remain PENDING. |
| 10 — Security remediation/final cloud readiness | LOCAL GUARDS IMPLEMENTED; OVERALL NO-GO | Redacted history/tree/index/local-config scans, tested preventive controls, selected regressions and cloud design DRAFT. Existing Phase06 gate FAIL; no owner invalidation/history cleanup/sign-off; advisory findings and P09 required live evidence unresolved. |

## Verified local architecture

```text
Existing dated news data
  -> MinIO Bronze (immutable bytes + manifest)
  -> Spark cleaning/validation/deduplication
  -> Delta Silver
       -> no-op enrichment -> Gold RAG documents/chunks -> Qdrant
       -> Gold Analytics Parquet + manifest             -> DuckDB

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

Documentation validation: all 21 reviewed Markdown files passed local link/linked
heading and fenced-block checks. Static checks matched the documented DAG/source
defaults, migration table names, Make targets and recorded live/acceptance JSON.
`git diff --check` passed after fixing Markdown trailing whitespace. No runtime
test suite was rerun for this documentation-only change.

A second consistency review also updated the README repository tree/main
verification summary, the local architecture's primary diagram and the monitoring
runbook's primary inventory (seven dashboards/15 rules). The legacy application
environment guide is now labeled separately from the active platform setup.

### Source inventory and documentation navigation — 2026-10-03

Added `docs/news-sources.md`: user-specified five-source origin, implementation
choice of economic listings, actual selectors/HTTP mechanism, extraction
boundaries and recorded live smoke (223 discovered URLs, five fetched articles,
39 chunks/points). It distinguishes those measurements from the historical
sample and synthetic fixtures; no broader live collection is claimed.

Added `docs/DOCUMENTATION_GUIDE.md`: first-reading sequence, navigation by task,
an explanation of every document under `docs`, phase specifications versus
execution evidence, historical/application guides, research/module documents
and links to actual code/artifacts. README, crawler runbook/architecture and
source mapping link these entry points. Summary mapping was clarified to match
the parser's actual `meta[name="description"]` extraction.

This change is documentation-only; no source request, configuration change,
schedule activation or contract redesign was performed.

Validation passed: links/headings/fences in seven new/modified documents; catalogue
coverage of all 48 Markdown documents under `docs` and all 62 repository Markdown
documents outside data/artifacts; source settings/selectors and smoke totals
matched code/recorded JSON; `git diff --check` passed. No runtime tests were
rerun for this documentation-only change.


## Phase09 functional implementation checkpoint — 2026-10-22

**Composed functional verification PASS**, all nine checkpoints exit 0. The original full target exited 0, but extended verification found an extra scheduled cycle failed during teardown. Its evidence is retained in `artifacts/phase9/attempt-3/`. Eight unchanged full-run checks were retained; after correcting pause/settle/restore and the post-rollback check, `python3 tools/phase9_scheduler_smoke.py` was rerun with exit 0. This is a focused rerun, not another full target invocation. Includes 54 policy/report/burn-in/crawler tests, 10 metrics tests, Phase08 regression with 10 DAG tests and real five-source fixture pipeline, Phase05 and Phase07 regressions, real scheduler restart with durable fixture replay/reconciliation, and two actual scheduled safety cycles with all five live source policies denied; both remain SUCCESS after rollback and no queued/running cycles remain. The extra alert-cadence test passed after tuning the empty-discovery window; Prometheus loaded 19 rules and the existing crawler dashboard has 14 panels. Repository provisioning remains seven dashboards; workspace Grafana also contains one previously persisted dashboard, which was retained.

Canonical contracts, transformations/enrichment, Gold-derived serving and metadata-only CDC remain unchanged. Additive operations migration `0003_continuous_crawling` is applied; publication still covers only the two `control_metadata` tables. Scheduling configuration was restored to manual (`schedule=None`, scheduled-live=false), with all source live policies false. Runtime evidence is ignored under `artifacts/phase9/`; newly generated tracked Phase05/08 artifacts were archived there and restored to their committed historical snapshots. No commit, push, cloud deployment or credential-history remediation was performed.

**B0 functional: PASS. B1 controlled live cycles: PENDING. B2 24h: PENDING. B3 72h: PENDING. Overall Phase09: not DONE.** No real-duration collector session was started; actual burn-in start/end are N/A. Historical credential audit continues to block cloud readiness. Complete current policy/access review, backup/recovery verification and the runbook prerequisites before starting live collection. Passing a fixture algorithm test is not time-based evidence.

Implementation, failures/retries, acceptance matrix and limitations: [Phase09 engineering report](../phase9-engineering-report.md). Operator enable/pause/replay/report/rollback and real-duration collection: [crawler runbook](../crawler-operations.md#phase09-controlled-scheduling-and-unattended-evidence). The earlier Phase01–08 sections are dated history, not a claim that their original verification dates/counts were updated by this phase.

### Post-Phase09 documentation consistency — 2026-10-22

Reviewed the merged Phase09 source/evidence and synchronized README/navigation,
architecture/operations, demo/presentation, release/cloud planning and thesis
artifacts. Added ADR-009 and a
[documentation review](../phase9-documentation-review.md) with the affected claims
and verification scope. Corrected Analytics to read Silver directly and labeled
the NoOp enrichment/events boundary. Historical Phase06–08 results retain their
dates and measurements; Phase09 functional PASS does not complete B1/24h/72h.

Documentation checks cover local links/headings, balanced Markdown fences,
dashboard/rule/DAG inventory and thesis structure/evidence. The read-only
data-contract drift check passed without changes; the generated observed block
is byte-identical to HEAD. No runtime tests, services, schedules, source code or
configuration were changed. `docs/thesis/` and `docs/present-demo/` remain ignored
by existing Git rules; their local updates are documented in the review.
