# Phase08 local crawler operations

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

Scheduled live runs use all five sources and the DAG's default **`limit=1` per source per run**, with a hard permitted range of 1–20. Manual trigger conf can change that run's limit. It does not change later scheduled defaults. The seeded PostgreSQL `max_articles=3` does not override the Airflow limit: the DAG explicitly passes its `limit` parameter. Changing the default for recurring runs currently requires an explicit DAG parameter change and verification; there is no scheduled batch-size environment variable yet.

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
