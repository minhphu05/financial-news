# Local crawler operations — Phase08 / Phase09

**23/10/2026 pilot closeout:** [Kết quả chạy từ trưa và phiên bốn giờ](phase9-pilot-report-2026-10-23.md).
Window completed, 50 samples, eight scheduled cycles; pilot verdict PENDING
because source crawl failures/partial remain. DAG paused and all live policies
false after deadline; cron/global opt-in remain configured. Formal 24h/72h and
cloud gates are unchanged.

Phase09 extends the existing jobs with runtime live policy, bounded publisher retries, telemetry and evidence commands. Functional verification and real 24h/72h burn-in are separate gates; see [Phase09 engineering report](phase9-engineering-report.md). Earlier Phase08 results below remain dated evidence.

For the five source websites, default sections, parser behavior and live
verification scope, read [news sources](news-sources.md). For an explanation of
each project document and reading order, use [documentation guide](DOCUMENTATION_GUIDE.md).

Use the existing local platform first; see [README](../README.md), [local release](local-release.md) and [metadata control plane](metadata-control-plane.md) for baseline service/bootstrap credentials. The crawler uses public HTTP and requires **no news-site API credential**. Storage/PostgreSQL/Airflow continue using local service configuration. Historical credential exposure remains a separate repository release blocker.

## Initialize and verify

```sh
make crawler-init
make test-crawler
make phase8-acceptance
```

`crawler-init` builds the existing Spark/Airflow images with the pinned HTML parser, starts MinIO/Qdrant/PostgreSQL, applies operations migrations and seeds five crawler configurations. The Phase04 metadata schema must already exist from the established bootstrap. Existing configurations and enabled state are not overwritten by seed. Repeating migrations/seed is safe.

`phase8-acceptance` runs parser/policy/frontier tests, the five-source fixture vertical slice, Airflow import tests, a real scheduler-managed fixture DAG, and local exporter/Prometheus/Grafana checks. It makes no HTTP requests to news websites. Embedding uses the established actual FastEmbed model; the initial model download/cache is part of the existing platform setup.

## Explicit live smoke / small incremental batch

Phase09 requires both the explicit `--allow-live` command flag and source runtime `live_enabled=true`; missing policy means false. Before enabling a source, review its current access/robots/terms and record a reference with the policy command in the Phase09 workflow below. A denied source produces a persisted `SKIPPED` result without HTTP, rather than pretending to have fetched zero new articles successfully.

```sh
make crawler-live-smoke CRAWLER_SOURCE=all CRAWLER_LIMIT=1
make crawler-publish CRAWLER_SOURCE=all
make crawler-status
```

The smoke discovers one verified economic listing per source, checks robots, and fetches at most one eligible article per source. Default CLI scope is one; metadata defaults to three for application callers. Hard maximum is 20 per batch. A second normal run may legitimately discover new articles: it does not refetch known articles until eligible.

```sh
make crawler-crawl CRAWLER_SOURCE=cafef CRAWLER_LIMIT=3
make crawler-publish CRAWLER_SOURCE=cafef
```

One source failure is recorded without rolling back other source outputs. CLI returns exit 2 if any source is FAILED/BLOCKED; PARTIAL article failures are recorded and do not make Airflow retry the entire fetch batch. Use the source's status and individual attempt rows to investigate.

## Source configuration

Rows `crawler:cafef`, `crawler:vnexpress`, `crawler:tuoitre`, `crawler:thanhnien`, `crawler:baomoi` in `control_metadata.news_sources`. The existing CafeF sample row is preserved.

`config.crawler` holds adapter/schema/parser version, discovery URLs, request interval, User-Agent, recent window, recheck interval, attempt cap and processing version. Configuration is loaded directly from PostgreSQL on each batch; Kafka consumption is unnecessary. Config changes still flow through the existing metadata CDC publication.

Local defaults: 3 seconds/request, 20-second timeout, response cap 5 MB, up to two in-job retries for transient errors, three failed article attempts across batches, 6-hour recheck, 7 days since first discovery. Recent eligibility is based on first discovery, not a fabricated publication time. Robots crawl-delay can only increase pacing. Source HTTP 403/401 or challenge pages stop that source. No authentication/paywall/CAPTCHA bypass or proxy rotation.

429/503 Retry-After becomes a persisted source cooldown; no requests are made before expiry. Other transient failures use bounded exponential retry/backoff. 404 and parser failures are not repeatedly retried by the normal frontier. An explicit recrawl is required after diagnosis.

## Bounded manual recrawl and historical backfill

```sh
docker compose run --rm --user 0 --no-deps news-pipeline \
  python3 -m src.crawling.cli recrawl --source cafef \
  --url 'https://cafef.vn/tang-truong-gdp-viet-nam-9-thang-nam-2026-cao-ky-luc-trong-15-nam-tro-lai-day-rieng-quy-iii-gan-can-moc-10-188261003092740641.chn' \
  --limit 1 --allow-live
```

Backfill requires an operator-reviewed JSON array of 1–20 actual source article URLs. It does not guess archive pagination or enumerate a whole website. Place the manifest under `data/local/crawler-urls.json`, then:

```sh
docker compose run --rm --user 0 --no-deps news-pipeline \
  python3 -m src.crawling.cli backfill --source cafef \
  --url-file /app/local/crawler-urls.json --from-date 2026-10-01 \
  --to-date 2026-10-03 --limit 20 --allow-live
make crawler-publish CRAWLER_SOURCE=cafef
```

Only reviewed publication timestamps in the requested date window are adapted/ingested. Unsupported timestamps and outside-window observations remain in Landing and are counted; they do not advance ingestion hashes or hide later normal ingestion. Completed frontier rows are skipped on a repeated backfill; eligible NEW/RETRY rows allow bounded continuation. Explicit recrawl can revisit an older article without destroying previous evidence. Both respect source cooldown/robots.

## Storage, identity, outbox and lineage

- `landing/live/<source>/html/<sha>.html`: exact HTTP bytes.
- `landing/live/<source>/observations/<crawl_run_id>/<url-sha>.json`: envelope before parsing; `.parsed.json`: source-specific parsed payload.
- `landing/live/<source>/batches/<batch_id>/`: immutable adapter input and lineage manifest.
- Fixture evidence lives in `landing/fixture/`; frontier names start with `fixture:` or test-owned namespaces. Live frontier uses the five fixed source keys.
- Existing Bronze retains adapter JSON array bytes by checksum. Existing Silver uses source **host**, e.g. `vnexpress.net`; the crawler config key is `vnexpress`.
- Live processing version `crawl-v1`, fixture version `fixture-crawl-v1`; the legacy sample's `cafef-v1.1` remains separate.
- Content hash and article ID reuse `normalize_observation`/`normalize_text`. Title/summary/publication changes also create a new observation signature. Layout-only changes do not create an update. Unchanged rechecks retain raw evidence but create no downstream batch.
- A batch ID includes its crawl event identity. If an article returns to an older body, that is a new update, even if Bronze bytes already exist.
- After Landing and Bronze commit, frontier hashes and PENDING outbox rows commit in one PostgreSQL transaction. Source advisory locks prevent concurrent selection/publishing. Crashed RUNNING source runs are marked interrupted by the next lock holder.
- Publisher restores/checksums the adapter input and calls the existing Phase05 `execute` API with MANUAL semantics, so multiple batches on one day are processed. Its stable pipeline run ID allows failed runs to resume from successful stages. No crawler transformation is copied downstream.
- `crawler_operations.batches` links manifest, crawl run, processing date and downstream pipeline run. Parsed envelopes link original URL/raw HTML; Silver identity/hash and Gold/Qdrant chunk IDs remain the existing lineage.

## Serving isolation and recovery

Existing reconciliation is source scoped. Live Qdrant collections: `crawler_<source>_v1`. Fixture collections: `fixture_crawler_<source>_v1`. DuckDB files live under configured `CRAWLER_WORK_DIR` as `<source>.duckdb` / `fixture-<source>.duckdb`. The public Qdrant endpoint, storage authority and PostgreSQL endpoint remain in existing configuration.

This phase deliberately serves per source; it does not introduce a unified multi-source query facade or silently overwrite another source's DuckDB tables. After publisher failure:

```sh
make crawler-status
make crawler-publish CRAWLER_SOURCE=vnexpress
```

No website fetch is required to replay a durable pending batch. Raw HTML also remains available for manual parser replay/investigation; the current CLI recrawl refetches an explicitly selected URL.

## Airflow

DAG ID: **`news_crawling_pipeline`**. Five static source groups, each `crawl -> publish`; 10 tasks, no per-article tasks, no heavy logic in DAG. One active DAG run and one active task. Fetch retries 0; application owns article retries. Publisher retries 1 and resumes durable batches.

Default schedule: **None**. Default manual run is fixture mode. Live mode requires explicit conf:

```sh
docker compose exec -T airflow-scheduler python3 /app/tools/airflow_smoke.py \
  news_crawling_pipeline --timeout 900 \
  --conf '{"sources":["cafef","vnexpress"],"fixture_mode":false,"allow_live":true,"limit":1}'
```

Offline demo:

```sh
make crawler-demo
make crawler-airflow-smoke
```

### Daily live scheduling (operator opt-in)

The following is an example configuration, **not an already enabled schedule**. After reviewing source policies and running bounded live acceptance, set these values in the ignored local `.env`:

```dotenv
AIRFLOW_NEWS_CRAWLER_SCHEDULE="0 6 * * *"
AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE=true
```

Apply the environment and verify DAG imports before unpausing:

```sh
docker compose up -d --force-recreate airflow-scheduler airflow-webserver
docker compose exec -T airflow-scheduler airflow dags list-import-errors
docker compose exec -T airflow-scheduler airflow dags unpause news_crawling_pipeline
```

`0 6 * * *` schedules a daily run at 06:00 in the DAG's `Asia/Ho_Chi_Minh` timezone. Airflow UI timestamps may use another display timezone. `catchup=False` does not recreate all missed calendar runs. The crawler discovers currently visible listing URLs and reads its persistent frontier; it does **not** restrict article publication dates to the Airflow data interval. Its batch processing date is the current Vietnam date at crawl time. Use the explicit backfill CLI for reviewed historical URLs.

Scheduled live runs use all five source groups and default **`limit=1` per source per run**, with a hard permitted range of 1–20. Phase09 adds `AIRFLOW_NEWS_CRAWLER_LIMIT` for the parsed recurring default. Manual trigger conf can change only that run's limit. The runtime effective fetch cap is the smaller of the requested limit and source `config.crawler.max_articles` (seed default three). Changing PostgreSQL policy does not alter the cron expression; changing schedule environment requires scheduler recreation/reparse.

Do not interpret a daily schedule as complete daily coverage. Discovery uses configured listing pages, not a verified full archive, and a one-article batch can accumulate a backlog. Newly discovered URLs have selection priority, so repeated backlog can delay eligible rechecks. Choose cadence/capacity only after observing discovered/fetched counts, frontier backlog, last successful crawl and pending publication batches. No production throughput or completeness SLA has been demonstrated.

The existing `news_incremental_pipeline` is a separate dated-file path. Crawled batches call the Phase05 runner directly through each source's `publish` task; do not enable the dated-file DAG as an extra consumer of crawler batches.

To stop recurring crawling, pause the DAG and restore manual defaults in `.env`:

```sh
docker compose exec -T airflow-scheduler airflow dags pause news_crawling_pipeline
```

```dotenv
AIRFLOW_NEWS_CRAWLER_SCHEDULE=
AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE=false
```

Recreate scheduler/webserver after restoring those values. Pausing prevents future scheduling; it does not cancel a run already in progress. These instructions do not themselves enable public website requests.

### Incremental behavior across daily runs

| Observation/state | Current behavior |
|---|---|
| New canonical URL | Insert into persistent `(source, canonical_url)` frontier; process when selected within the batch limit. |
| Previously successful URL | Recheck only after `next_eligible_at`, and only within `recent_days` since first discovery. Defaults are 6 hours and 7 days. |
| Unchanged normalized content/title/summary/publication | Preserve raw Landing evidence; create no new downstream batch. HTML layout changes alone do not create an update. |
| Changed observation | Commit a new immutable adapted batch, then reuse Phase05 Silver/Gold/serving processing and reconciliation. |
| Transient source failure | Persist retry eligibility/cooldown; retry only eligible rows within existing attempt limits. |
| Downstream failure | Keep durable pending/failed batch and resume publisher without another website request. |
| URL absent from the next listing | Do not infer article deletion; there is no approved upstream article deletion contract. |

Six hours is an eligibility delay, not a separate timer: a daily DAG rechecks at its next selected run, not every six hours. Discovery state and hashes must survive scheduler/container restarts. Successful URLs outside the recent window require explicit recrawl if they need revisiting. NEW/RETRY rows are not excluded by that recent-success window.

Incremental ingestion does not mean every downstream operation is a delta-only computation: Silver/Gold use the existing hardened path, while Gold Analytics currently performs a deliberate full refresh. Qdrant and DuckDB remain derived serving systems, with source-scoped collections/files.

### Cloud deployment handoff

Keep the same source jobs and thin DAG. Supply service endpoints, storage/identity adapters and deployment settings outside parser/transformation logic. Preserve **both** Landing/Bronze/Silver/Gold and PostgreSQL `crawler_operations` plus source configuration; migrating only lake files loses frontier/hash/cooldown/outbox continuity. Suspend local scheduling and finish or record in-flight batches before taking a consistent cutover checkpoint. Keep cloud scheduling paused until migrated pending batches, per-source serving outputs and incremental replay reconcile.

ADLS execution is not installed: it still needs the byte adapter, compatible ABFS runtime and approved identity. No cloud services or Kubernetes resources have been provisioned. See [cloud migration plan](cloud-migration-plan.md) and [migration manifest](cloud-migration-manifest.md) for validation and rollback; the historical credential release blocker remains unresolved.

## Monitoring

```sh
make crawler-monitoring-smoke
make crawler-status
```

Dashboard: **Financial News — Multisource Crawling**, UID `news-crawler`. Metrics cover runs, discovered/fetched/changed/unchanged/failures, 429/403, retry/request counts, durations, freshness, frontier and pending batches. Labels are bounded `source`, `data_kind`, `status`, `outcome`; never URLs/article IDs/run IDs. Exporter reads PostgreSQL with the existing read-only monitoring role.

Alerts in `monitoring/prometheus/rules/financial-news.yml`: `CrawlerSourceBlocked`, `CrawlerParserFailures`, `CrawlerDownstreamBacklog`. Local windows/thresholds are editable operational configuration, not business logic. Manual mode does not imply a continuous freshness SLA. Recreate Prometheus/Grafana if an older bind mount does not see updated configuration; verify with `promtool` and APIs.

## Evidence / limitations

See `artifacts/phase8-live-smoke.json`, `phase8-live-e2e.json`, `phase8-fixture-e2e.json`, `phase8-acceptance.json` and source profiles. Test HTML uses explicitly synthetic bodies with observed DOM structures; full news content under `data/local` is excluded from Git. One live article/layout per source and tiny economic-listing smoke are not broad production coverage. Browser-only layouts, archive traversal, content licensing, unified serving, long retention and cloud deployment are outside this local verification.

## Phase09 controlled scheduling and unattended evidence

### Upgrade an existing local workspace

With standalone jobs idle, run `make crawler-init` before Phase09 commands. It builds the existing images, applies additive operations migrations and seeds only missing source rows. Migration `0003_continuous_crawling` adds operational skip/block/retry state; it does not change article contracts or add CDC tables. Existing source configuration and persisted lake/frontier data are retained. The target also recreates the exporter, Prometheus and Grafana to load current telemetry assets. Recreate the scheduler/webserver after changing their environment, then inspect `make phase9-config-check` and the parsed DAG before unpausing.

Operational rollback means pausing/disabling scheduling first. SQL downgrade is guarded and can refuse while Phase09-only statuses/history exist; do not delete operational evidence to force it. No downgrade was exercised as part of the local acceptance.

### Runtime policy and manual safety

`control_metadata.news_sources.enabled` remains the source switch. Optional keys added under the existing `config.crawler` object default to:

| Key | Default | Meaning |
|---|---:|---|
| `live_enabled` | false | Additional source-level live opt-in; absent also denies live |
| `request_timeout_seconds` | 20 | HTTP timeout; bounded 1–120 seconds |
| `http_retries` | 2 | Bounded 0–3 transient retries; existing Retry-After/robots behavior retained |
| `max_response_bytes` | 5,000,000 | Response bound, at most 5 MB |
| `publish_max_batches` | 2 | Maximum durable batches replayed per source publish call |
| `publish_max_attempts` | 5 | Automatic attempt budget; exhausted batches remain visible for review |
| `publish_retry_base_seconds` | 60 | Initial automatic retry delay |
| `publish_retry_max_seconds` | 3,600 | Exponential delay cap; up to 10% jitter within the cap |
| `heartbeat_max_age_seconds` | 7,200 | Local alert threshold; configurable, not a demonstrated SLA |

Existing delay/recheck/recent-window fields remain in the same JSON object. Seed does not overwrite existing operator rows. Migration `0003_continuous_crawling` adds operational skip/block and outbox attempt/eligibility fields, without changing article contracts or CDC publication. New defaults are applied in code to old configuration rows.

Inspect configuration from the actual scheduler environment:

```sh
make operations-migrate
make phase9-config-check
```

Enable a reviewed source explicitly; the reference must identify a real review, not a fabricated approval:

```sh
docker compose run --rm --no-deps news-pipeline \
  python3 -m src.crawling.operations policy --source cafef \
  --live-enabled true --policy-reviewed \
  --policy-reference 'path-or-URL-of-the-actual-dated-policy-review'
```

Review/enable each intended source individually. For the initial local cadence, configure the ignored `.env`:

```dotenv
AIRFLOW_NEWS_CRAWLER_SCHEDULE="*/30 * * * *"
AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE=true
AIRFLOW_NEWS_CRAWLER_LIMIT=1
```

Recreate scheduler/webserver as in the scheduling procedure above, check import errors and effective config, then unpause. The DAG retains `catchup=False`, one active run and one active task. Its manual defaults remain **fixture=true, allow_live=false even while the schedule is live-enabled**. Only actual Airflow `scheduled` run types use the automatic live switch; manual live still needs explicit conf and source policy.

Source disabled/live-denied/cooldown/block outcomes skip without a fetch. HTTP 401/403, challenge/robots blocks latch in `source_state`; future runs make no source requests until reviewed. Retry-After remains a persisted cooldown. Parser failures are distinct from successful HTTP responses; unavailable optional publication timestamps remain nullable by contract. A source fetch failure does not prevent its `publish` task from trying already accepted batches (`all_done` dependency), subject to current source enablement.

### Pause, isolate and rollback

Pause the DAG first. Disable affected source live policy without deleting any frontier, raw object or pending batch:

```sh
docker compose exec -T airflow-scheduler airflow dags pause news_crawling_pipeline
docker compose run --rm --no-deps news-pipeline \
  python3 -m src.crawling.operations policy --source cafef --live-enabled false
```

Restore empty schedule and `AIRFLOW_CRAWLER_ALLOW_SCHEDULED_LIVE=false` in `.env`, then recreate scheduler/webserver. Pausing does not cancel an already running task; its work remains bounded. Confirm in-flight work settles before backup or restart drills. Do not use destructive reset for scheduler rollback.

After diagnosing a latched block and reviewing current policy, clear only its operational latch. This preserves any Retry-After cooldown and does not enable live policy or bypass robots:

```sh
docker compose run --rm --no-deps news-pipeline \
  python3 -m src.crawling.operations clear-block --source cafef --policy-reviewed
```

### Backlog and recovery

Scheduled/DAG publication honors `next_eligible_at`, attempt budget and batch cap. A held source advisory lock prevents double claim. The next lock holder converts an interrupted `RUNNING` publisher to retryable `FAILED`, preserving Landing/manifest/bytes. Repeated failures use bounded exponential backoff and remain visible when the budget is exhausted. A successful task can mean its bounded eligible pass finished while other batches remain deferred; the returned `status=PENDING` and `pending_batches_remaining` distinguish that case from an empty backlog.

Manual publisher calls are an explicit immediate replay of accepted data, still capped by source `publish_max_batches`; they do not refetch news websites. To honor the automatic eligibility/budget instead, use:

```sh
docker compose run --rm --user 0 --no-deps news-pipeline \
  /opt/spark/bin/spark-submit \
  --packages io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4 \
  --conf spark.jars.ivy=/opt/news-ivy /app/src/crawling/publish_runner.py \
  --source cafef --max-batches 1 --respect-retry
```

Inspect crawler status, pending age and retry exhaustion before a manual override. Repair service/configuration, replay durable batches, then require Phase05 reconciliation. Stage SUCCESS reuse assumes those outputs remain available; this phase does not add distributed transactions, event-time conflict resolution or a general guarantee for process death between every pair of commits. Raw HTML before the frontier/outbox commit remains durable but may need another fetch if that uncommitted crawl is restarted.

### Timestamp, metrics and report semantics

The crawler persists first/last **completed durable HTML Landing writes**, fetch/parse/new/update/unchanged counts and Airflow run context. A completed crawl heartbeat includes policy skips; `last_success_at` remains a successful crawl, not proof of downstream publication. Latest layer timestamps come from successful pipeline stages linked to outbox batches. Latency is first durable Landing → stage finish, not article publication age or user-visible response latency.

The crawler dashboard now includes heartbeat, pending age, layer freshness, measured Landing-to-layer interval, retry exhaustion, live policy and local resource context. New alerts cover parser success ratio (at least five attempts) or repeated empty discoveries (at least three in two hours), exhausted retries, oldest pending age and missing/stale heartbeat for enabled live sources. The two-hour empty-discovery window accommodates the proposed 30-minute cadence; synthetic alert tests cover that cadence and subsequent resolution. Empty listings are a drift suspicion, not proof that a website failed; known URLs with no due article are a separate normal no-new-work case. Block alerts also read the persisted latch so a blocked source is not silently considered recovered after an event window expires. These thresholds are local tunable configuration. Labels stay bounded; no URL/article/run IDs are metric labels. HTTP duration measures a request chain after its initial pacing wait; same-host redirect pacing inside that chain is included. There is no measured HTTP duration for synthetic transport.

The heartbeat alert is armed by `live_enabled` source policy rather than by cron. After a manual live smoke, disable that policy if recurring operation is not intended; otherwise a missing heartbeat is expected to warn after the configured age. Clearing a block latch can leave the recent block-event alert firing until its 15-minute observation window expires.

Generate a closed-window report; timezone offsets are required for explicit timestamps:

```sh
make phase9-daily-report
make phase9-daily-report START=2026-10-20T00:00:00+07:00 END=2026-10-21T00:00:00+07:00
make phase9-daily-report FIXTURE=1
```

The explicit window must already be closed. Reports under ignored `artifacts/phase9/daily-reports/` separate run cohorts, reconstructed pending-at-end, completion-based latency samples and alert-history observations. Latency samples are per outbox batch/stage, deduplicated across successful attempts; they are not a per-article latency distribution. p50 requires a measured sample; p95 stays N/A below 20 samples. Historical rows lacking Landing timestamps remain N/A. No mean article-arrival rate, throughput SLA or RAG-quality claim is inferred from these reports.

Alert-history coverage reports the number of query steps with Prometheus self-scrape data. An empty alert list with missing history remains unknown; even complete query-step availability does not prove uninterrupted raw scrapes or service uptime. Fixture reports aggregate all selected fixture namespaces and are not counts of the live business corpus.

`python3 -m src.crawling.operations storage` measures selected source prefixes through bounded S3 listing and PostgreSQL relation sizes. It is periodic administration, not an expensive Prometheus scrape. Truncated listings are explicitly lower bounds; same-host Bronze includes historical snapshots/fixtures. CPU/memory/disk are shared-workstation observations. Set `PHASE9_PROMETHEUS_URL` for a nondefault host Prometheus endpoint.

### Functional acceptance and controlled drills

```sh
make phase9-acceptance
python3 tools/phase9_recovery.py
python3 tools/phase9_scheduler_smoke.py
```

Acceptance is offline for news websites; it uses real local services. The restart drill writes only fixture serving, injects a test endpoint failure, restarts the scheduler and verifies durable resume/reconciliation without another crawl. The scheduler safety drill temporarily uses a two-minute cron **only when every source live policy is disabled**, observes at least two actual scheduled cycles/skips, then pauses immediately and verifies that all queued/running cycles have settled before restoring the original manual environment. It checks history again after rollback, so an extra failed cycle cannot be hidden by the first two successes. It is not a live burn-in. Run drills with other source jobs idle; they intentionally restart the local scheduler. Neither command deletes live lake/frontier data.

### Short pilot with a fixed end time

A separate user-requested 1/2/4-hour pilot is available through
`python3 tools/phase9_pilot.py`; see the [Vietnamese pilot guide](phase9-pilot-guide-vi.md)
for the five-source run, services, UI links, evidence, stop and report commands.
A short pilot does not satisfy the following 24h/72h gates. Current session metadata
and user systemd units are recorded in ignored `artifacts/phase9/pilot/runtime.json`.

Source policy accepts optional `--live-until <timezone-aware-timestamp>` when
explicitly enabling a reviewed source. The gate denies new live work after this
deadline, even if its collector dies; invalid/naive values fail closed. Existing
policies without a deadline keep their previous behavior. Enabling a source without
`--live-until` explicitly clears an old deadline. Fixture transport is unaffected.
Collector/timer pause and disable live at the end; in-flight bounded work must
settle. Keep initial incidents in the report; a successful terminal publish task
with `all_done` is not proof that its preceding crawl succeeded.

### Real 24h → 72h burn-in

Before activation, pass functional acceptance, perform the bounded live-policy/access checks, confirm health/resources and record an actual backup/recovery reference. A consistent backup procedure must quiesce scheduler **and standalone writers**, preserve PostgreSQL control/operations/frontier/outbox together with Landing/Bronze/Delta/Gold, and verify restore into isolated destinations before relying on it. Database-only backup or a copy missing Delta logs is insufficient. Backup/restore completion is not implied by this runbook or by passing fixture tests.

After configuring reviewed source policies and the chosen cadence, start evidence collection explicitly:

```sh
python3 tools/phase9.py burnin-start --hours 24 --live-opt-in \
  --backup-reference path/to/actual-backup-or-reviewed-recovery-reference \
  --sources cafef vnexpress tuoitre thanhnien baomoi
# Use the session path printed by the previous command:
python3 tools/phase9.py watch --session artifacts/phase9/burnin-<actual-session>.json
make phase9-burnin-report SESSION=artifacts/phase9/burnin-<actual-session>.json
```

Keep the collector in a supervised terminal/session on the awake workstation. The collector does not schedule crawls; Airflow does. It samples telemetry/storage/resources every five minutes, records boot ID and monotonic time, and pauses the DAG on stop/error/completion. A block/rate-limit, reconciliation failure, unavailable critical target, less than 2 GiB disk free or less than 128 MiB available memory causes a conservative local hard stop; these floors are operational safeguards, not capacity results. Preserve evidence and review incidents before resuming. SIGKILL/power loss cannot run cleanup; pause the DAG immediately on recovery and treat the interrupted window as incomplete.

The report requires full real elapsed time, coverage without large gaps, stable boot identity, actual scheduled run evidence, live success, and reviewed backlog/failures. A fixture, an edited start date or a short test does not satisfy it. The automatic go/no-go is conservative: unresolved failures keep it from PASS. Only after a genuine 24h PASS and review, unpause for the next window and run `burnin-start --hours 72 --previous-24h-report <actual-pass-report>` with the same explicit prerequisites. Seven days is optional. `make phase9-burnin-report` without a real session returns PENDING.
