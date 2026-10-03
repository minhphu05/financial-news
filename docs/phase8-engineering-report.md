# Phase08 engineering report — local multisource crawling

Verified: 2026-10-03. Branch: `feature/multisource-news-crawler`, base `e300b09`.

**Verdict: COMPLETE (LOCAL).** `make phase8-acceptance` exited 0. No commit/push or cloud deployment was performed. Cloud-release verdict remains **NOT READY FOR CLOUD MIGRATION** because credentials exist in Git history; crawler functionality does not resolve that owner/security action.

## Baseline and regression

Required documents, canonical contracts, actual jobs/services/migrations and legacy crawler modules were inspected. The Phase01 task exists as `docs/agent_tasks/01_bronze_silver_local.md`; the requested hyphenated path was absent. Legacy MongoDB/Prefect crawler output was incompatible with the released medallion boundary and was left unused. The new crawler reuses current storage, normalization/hash functions, Bronze ingestion, hardened processing, metadata configuration and monitoring; no downstream transformations were copied.

| Command/check | Actual result |
| --- | --- |
| `make phase6-acceptance` baseline | Exit 2 only at historical-credential release gate; functional prerequisites passed |
| `make phase7-acceptance` baseline | Exit 0; real quality, Qdrant failure/recovery and metadata CDC monitoring scenarios passed |
| Baseline CI | 23 unit tests, 1 Bronze/Silver Spark integration, 1 Gold Spark unit, 7 metadata tests, 7 original DAG tests passed |
| Baseline recovery/CDC | Backfill/idempotency/resume/schema drift, snapshot/INSERT/UPDATE/DELETE, connector restart, Kafka outage and PostgreSQL restart passed |
| `make test-gold` after crawler dependency build | 4 unit + 1 Spark unit + 1 full MinIO/Delta/Qdrant/DuckDB integration passed |
| `make test-hardening` first attempt | Failed with S3 HTTP 400 while reading a Silver parquet object in analytics |
| `make test-hardening` repeat | 9 unit tests and full incremental integration passed in 116.295 s |
| `make phase8-acceptance` | Exit 0; 26 crawler tests, all-five fixture vertical slice, 8 DAG tests, 6 monitoring unit tests, scheduler-managed DAG, 2 actual observability tests and final persisted report PASS |
| Focused Ruff | New crawler/report/test/DAG/metric modules: check and format-check passed |
| Docker Compose and diff hygiene | Configuration valid; `git diff --check` passed |

The S3 failure's root cause was not established. No speculative data transformation workaround was applied. Initial implementation checks also caught a wrong test response-key assumption, a Spark script-directory/stdlib `http` import collision, and batch identity reuse on content reversion. Those were corrected and the final workflow passed. A stale Prometheus bind directory was recreated; `promtool` and real APIs confirmed 15 loaded rules and the new dashboard.

## Source results

All five observed article/listing pages returned HTTP 200 with ordinary public HTTP. No browser rendering or source credential was required. Each observed parser and offline synthetic fixture passed; all five sources passed an explicit one-eligible-article live vertical slice.

| Source | Crawler key / canonical host | Fetch | Parser | Raw schema | Live articles | Chunks / Qdrant points | Reconciliation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CafeF | `cafef` / `cafef.vn` | public HTTP | v1 PASS | `cafef-raw-v1` | 1 | 3 / 3 | PASS |
| VnExpress | `vnexpress` / `vnexpress.net` | public HTTP | v1 PASS | `vnexpress-raw-v1` | 1 | 7 / 7 | PASS |
| Tuổi Trẻ | `tuoitre` / `tuoitre.vn` | public HTTP | v1 PASS | `tuoitre-raw-v1` | 1 | 3 / 3 | PASS |
| Thanh Niên | `thanhnien` / `thanhnien.vn` | public HTTP | v1 PASS | `thanhnien-raw-v1` | 1 | 12 / 12 | PASS |
| Báo Mới | `baomoi` / `baomoi.com` | public HTTP | v1 PASS | `baomoi-raw-v1` | 1 | 14 / 14 | PASS |

Total live evidence: **5 Silver articles, 5 Gold documents, 39 chunks/Qdrant points, 5 DuckDB articles across source files**. Blocked sources during this observation: **none**. This is tiny, dated evidence rather than broad layout or production stability coverage. Profiles/contracts retain actual URLs, selector evidence, robots and raw field types without committing real full article bodies. Source contracts are `docs/source-contracts/{cafef,vnexpress,tuoitre,thanhnien,baomoi}.md`.

## Reuse / compatibility audit

| Existing component | Decision | Scope |
| --- | --- | --- |
| ObjectStore / local MinIO adapter | KEEP | Landing reuses byte-storage interface; only obsolete cloud-phase error wording was corrected |
| Source schema gate / canonical normalization / hashing | KEEP | No schema or approved contract edits |
| Bronze / Spark Silver / Gold / Qdrant / DuckDB | KEEP | Existing standalone and Phase05 jobs reused; source-serving settings are injected outside transformation logic |
| Phase03 DAGs / job factories | KEEP | New source-batch DAG uses existing thin factories; original three DAGs remain |
| Phase04 PostgreSQL / Debezium / Kafka | KEEP | Config JSON reused; monitoring grants extended to operational crawler schema |
| Phase05 operations / migration runner | KEEP | Adds isolated crawler migration; no existing migration rewrite |
| Phase07 exporter / provisioning | REFACTOR (incremental) | Optional crawler snapshot/collector, one dashboard and three alerts |
| Legacy MongoDB/Prefect crawler modules | UNUSED FOR NOW | Their destination/HTTP retry rules do not satisfy the released boundary/policy; no wholesale replacement of legacy code |
| Browser automation / cloud migration | UNUSED FOR NOW | All observed targets supported ordinary HTTP; no cloud provisioning |

## Canonical boundary and Landing

Crawler knows website DOM/discovery; adapter knows source-payload mapping; canonical transforms remain in `src/news_pipeline`; DAGs call standalone jobs; monitoring reads operational state.

Source-specific project-owned payload aliases are wrapped by a common provenance envelope. Exact HTML, source schema/parser version, HTTP evidence, crawl time, native time/author/images/category and observed Báo Mới attribution remain in immutable `landing/live` or `landing/fixture` objects. Adapters emit only existing `link/title/summary/context/post date` fields as a JSON array. The existing schema gate validates that file before existing Bronze ingestion.

Native ISO timestamps explicitly convert to approved Vietnam-local minute format; native seconds/offset remain in Landing. Unsupported time stays raw and normalizes to null. Canonical author/category/images/crawled_at remain null as in current normalization; no NER/ticker/entity data is invented. `docs/data-contracts.md` and canonical schemas were not changed.

Identity/content hashing reuse existing normalization. Crawler dedup is source-scoped; no cross-source semantic dedup or original-publisher crawling is introduced. Báo Mới identity remains its own host/URL; publisher/original URL is stored only when present in source evidence.

## Persistent state and jobs

Migration `0002_crawler_operations` adds isolated schema `crawler_operations` with `source_state`, `crawl_runs`, `frontier`, `crawl_attempts`, `batches`; migration runner/history from Phase05 is reused. Up/down SQL exists; up was actually applied and repeated safely. Rollback was not executed against live collected data. Monitoring role receives read-only access. Existing CDC publication remains exactly `control_metadata.news_sources` and `control_metadata.pipeline_configs`; crawler state/content is not captured by Kafka.

Five configuration rows `crawler:<key>` reuse `news_sources.config`; the CafeF sample row is preserved. Runtime reads config directly, not Kafka CDC. Seed does not overwrite operator policy/enabled state.

Normal runs discover bounded latest economic listings, persist/deduplicate candidates, fetch NEW/eligible RETRY rows and recent successful rows due for recheck. Default recheck is 6 hours within 7 days since first discovery. CLI defaults one article; metadata default three; hard cap 20. No whole-site scheduled rescans. Manual backfill uses a reviewed 1–20 URL manifest and an explicit publication date window; manual recrawl selects explicit URLs. Out-of-window data does not advance ingestion hashes. Source advisory locks prevent concurrent batches.

Body hash plus normalized title/summary/publication signature detects changes. Unchanged observations produce no downstream batch. Changed and reverted content create distinct crawl-event batches, even when Bronze bytes already exist. Landing/Bronze commit before atomic frontier-hash/outbox commit. Publisher replays checksummed pending input through existing Phase05 MANUAL execution with a stable batch run ID; failures resume successful stages without refetching websites. Each source retains successful outputs when another fails.

Live/fixture processing versions, frontier namespaces, Landing prefixes, Qdrant collections and DuckDB files are separate. Serving is source scoped: `crawler_<key>_v1` vs `fixture_crawler_<key>_v1`; DuckDB uses configurable work directories. No unified serving facade was added and Qdrant/DuckDB remain derived.

## HTTP policy and scheduling

Configured research User-Agent; robots support BOM, specific agents, wildcard/end-anchor rules, allow precedence and crawl-delay. Same-host redirect targets are checked and paced. Defaults: 3 seconds/request, 20-second timeout, 5 MB response limit, two transient HTTP/network retries, three failed article attempts across batches. Retry-After persists a source cooldown. 404 and parser failures are not continuously retried; 403/401/challenge stop a source. No bypass, proxy rotation, authentication or paywall logic exists.

DAG **`news_crawling_pipeline`**: five source groups, each `crawl -> publish`, 10 tasks. Actual default schedule **None**, catchup false, one active run/task. Fetch retries zero because application owns article failures; publisher retries once. Fixture is the safe manual default; live conf requires explicit opt-in. A later operator may set a conservative schedule through `AIRFLOW_NEWS_CRAWLER_SCHEDULE` plus `AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE=true`; the local example is approximately 15 minutes, not a production SLA. No schedule was enabled by this implementation.

Actual two-source and all-five-source scheduler smoke runs succeeded. All-five run: `smoke__20261003T061524548214Z__7540cd60`, **10/10 tasks SUCCESS**.

## Monitoring

The Phase07 exporter now reads crawler run/frontier/outbox state with its existing read-only PostgreSQL role. Six metric families cover run outcomes, article/request/retry counts, duration, freshness, frontier cardinality and pending batches. Only bounded `source/data_kind/status/outcome` labels; no URL/article/run IDs. Existing exporter tests and pre-crawler snapshot compatibility pass.

Seventh Grafana dashboard: **Financial News — Multisource Crawling**, UID `news-crawler`. Alerts: `CrawlerSourceBlocked`, `CrawlerParserFailures`, `CrawlerDownstreamBacklog`; total local rules 15, validated by `promtool` and actual APIs. Manual crawling does not imply a freshness SLA. Real metric/cardinality/dashboard/rule tests passed.

## Commands added

- `make crawler-build`, `crawler-init`, `crawler-status`, `test-crawler`.
- `make crawler-live-smoke`, `crawler-crawl`, `crawler-publish` (bounded explicit live collection).
- `make crawler-demo`, `crawler-airflow-smoke`, `crawler-monitoring-smoke`.
- `make phase8-acceptance` (offline websites, real local infrastructure).
- `python3 -m src.crawling.cli` commands: `seed`, `status`, `crawl`, `live-smoke`, `recrawl`, `backfill`, `publish`.

## Exact local reproduction

Prerequisite: existing Phase01–07 local bootstrap/service credentials, including the already initialized Phase04 metadata schema. No news-site API credential is needed.

```sh
make crawler-init
make phase8-acceptance
make crawler-live-smoke CRAWLER_SOURCE=all CRAWLER_LIMIT=1
make crawler-publish CRAWLER_SOURCE=all
make crawler-status
```

Fixture and Airflow demo:

```sh
make crawler-demo
make crawler-airflow-smoke
make crawler-monitoring-smoke
```

Explicit two-source live DAG:

```sh
docker compose exec -T airflow-scheduler python3 /app/tools/airflow_smoke.py   news_crawling_pipeline --timeout 900   --conf '{"sources":["cafef","vnexpress"],"fixture_mode":false,"allow_live":true,"limit":1}'
```

Controlled recrawl/backfill, runtime policy configuration and recovery details are in `docs/crawler-operations.md`.

## Known limitations and remaining blockers

- Source access and single-layout evidence are dated 2026-10-03; additional layouts/policy changes can fail and must be profiled before selector changes. Browser-only/restricted sources are not bypassed.
- Explicit historical URL manifests only; no broad archive discovery, deep pagination or production crawling guarantee.
- Minute-resolution canonical time and Landing-only optional source metadata follow the current contract; richer canonical mapping requires separate approval.
- Per-source serving, not one multi-source Qdrant/DuckDB query facade.
- Interrupted crawl runs recover on the next source lock holder; unpublished batches require publisher/DAG execution. Local raw/frontier retention is not yet a production archival policy.
- First S3 regression failed; repeat passed, root cause unknown. The observation is preserved honestly.
- Historical credential exposure still blocks cloud release; owner rotation/history-cleanup action is unchanged. Current `.env` is untracked/ignored; no new credentials were introduced.
- No Azure/ADLS/Kubernetes/Terraform/Helm or next phase implemented.

## Git hygiene and suggested commits

No staging, commit, tag or push. Real observed full HTML and runtime logs/databases remain ignored under `data/local`; fixtures contain synthetic article text. Timestamp-only changes to older phase snapshots and the tracked root bytecode file produced by tests were restored; fresh evidence is in dedicated Phase08 artifacts.

Suggested reviewable commit breakdown:

1. `feat(crawling): add verified source parsers adapters and bounded HTTP policy`
2. `feat(crawling): persist frontier landing batches and reuse medallion jobs`
3. `feat(airflow): orchestrate local multisource crawler batches`
4. `feat(monitoring): expose crawler metrics dashboard and alerts`
5. `docs(crawling): record source contracts local acceptance and operations`

## Files created

- `airflow/dags/news_crawling_pipeline.py`
- `artifacts/phase8-acceptance.json`
- `artifacts/phase8-baseline.json`
- `artifacts/phase8-fixture-e2e.json`
- `artifacts/phase8-live-e2e.json`
- `artifacts/phase8-live-smoke.json`
- `artifacts/phase8-regression.json`
- `artifacts/source-profiles/baomoi.json`
- `artifacts/source-profiles/cafef.json`
- `artifacts/source-profiles/thanhnien.json`
- `artifacts/source-profiles/tuoitre.json`
- `artifacts/source-profiles/vnexpress.json`
- `docs/agent_tasks/08-multisource-crawling-ingestion-local.md`
- `docs/crawler-operations.md`
- `docs/crawling-architecture.md`
- `docs/phase8-engineering-report.md`
- `docs/source-contracts/baomoi.md`
- `docs/source-contracts/cafef.md`
- `docs/source-contracts/thanhnien.md`
- `docs/source-contracts/tuoitre.md`
- `docs/source-contracts/vnexpress.md`
- `docs/source-mapping-matrix.md`
- `monitoring/grafana/provisioning/dashboards/json/7-news-crawler.json`
- `operations/migrations/0002_crawler_operations.down.sql`
- `operations/migrations/0002_crawler_operations.up.sql`
- `src/crawling/__init__.py`
- `src/crawling/adapters.py`
- `src/crawling/airflow_jobs.py`
- `src/crawling/cli.py`
- `src/crawling/http_client.py`
- `src/crawling/jobs.py`
- `src/crawling/landing.py`
- `src/crawling/publish_runner.py`
- `src/crawling/sources.py`
- `src/crawling/state.py`
- `src/monitoring/crawler_metrics.py`
- `tests/fixtures/crawling/README.md`
- `tests/fixtures/crawling/baomoi-listing.html`
- `tests/fixtures/crawling/baomoi.html`
- `tests/fixtures/crawling/baomoi.json`
- `tests/fixtures/crawling/cafef-listing.html`
- `tests/fixtures/crawling/cafef.html`
- `tests/fixtures/crawling/cafef.json`
- `tests/fixtures/crawling/thanhnien-listing.html`
- `tests/fixtures/crawling/thanhnien.html`
- `tests/fixtures/crawling/thanhnien.json`
- `tests/fixtures/crawling/tuoitre-listing.html`
- `tests/fixtures/crawling/tuoitre.html`
- `tests/fixtures/crawling/tuoitre.json`
- `tests/fixtures/crawling/vnexpress-listing.html`
- `tests/fixtures/crawling/vnexpress.html`
- `tests/fixtures/crawling/vnexpress.json`
- `tests/test_crawler_metrics.py`
- `tests/test_crawling_e2e.py`
- `tests/test_crawling_observability.py`
- `tests/test_crawling_parsers.py`
- `tests/test_crawling_state.py`
- `tools/phase8_report.py`

## Files modified

- `.env.example`
- `Makefile`
- `README.md`
- `docker-compose.yml`
- `docker/airflow/Dockerfile`
- `docker/news-pipeline/Dockerfile`
- `docs/agent_tasks/CURRENT_STATUS.md`
- `docs/demo-guide-vi.md`
- `docs/local-architecture.md`
- `docs/monitoring-observability.md`
- `monitoring/prometheus/rules/financial-news.yml`
- `src/metadata_control/database.py`
- `src/monitoring/exporter.py`
- `src/news_pipeline/storage.py`
- `tests/test_airflow_dags.py`

Git status at handoff: **15 modified tracked files, 58 new untracked files, zero staged files**. The Phase08 task document was already supplied/untracked when this work began.
