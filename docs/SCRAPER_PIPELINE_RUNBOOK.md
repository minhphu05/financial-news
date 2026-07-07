# Scraper Pipeline Runbook

This runbook is the operator guide for the current local Financial News scraper pipeline.

## Current Architecture

The current scraper path is:

```text
Prefect schedule or manual trigger
  -> src.flows.standard_scraper_flow.standard_scraper_flow
  -> optional market data task
  -> optional missing keyword generation task
  -> src.flows.scrape_flow.scrape_task
  -> src.scraper.engine.pipeline.run_pipeline
  -> source parser, currently CafeF
  -> PostgreSQL metadata plus ADLS or MinIO article JSON
```

The canonical news scraping engine is `src.scraper.engine.pipeline.run_pipeline`. Prefect is only the trigger and orchestration layer.

## Active vs Inactive Flows

Current active flow files:

- `src/flows/deploy.py`
- `src/flows/standard_scraper_flow.py`
- `src/flows/scrape_flow.py`

Inactive flows reserved for later work are stored in:

- `src/flows/future_use/`

Those files are intentionally outside the active deployment path and are not served by `python -m src.flows.deploy`.

## Prerequisites

Local infrastructure should provide:

- PostgreSQL metadata database on `METADATA_POSTGRES_HOST_EXTERNAL` and `METADATA_POSTGRES_EXTERNAL_PORT`.
- Prefect server on `http://localhost:4201` for UI/API operation.
- MinIO for local article JSON storage when `CONTENT_STORAGE_BACKEND=minio`.
- Active rows in `core.stocks` and `scraping.keywords`.

The PostgreSQL schema is created by `docker/postgresql/init-scripts/001-create-scraper-schema.sql` when the metadata Postgres container initializes a fresh data volume.

## Environment Variables

Important scraper variables:

```text
METADATA_POSTGRES_HOST_EXTERNAL=localhost
METADATA_POSTGRES_EXTERNAL_PORT=5434
METADATA_POSTGRES_USER=metadata_user
METADATA_POSTGRES_PASSWORD=metadata_password
METADATA_POSTGRES_DB=financial_metadata
CONTENT_STORAGE_BACKEND=minio
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=financialnews-datalake
MINIO_SECURE=false
SCRAPER_MAX_PAGES=200
SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD=100
LOGS_DIR=./logs/scraper
```

Use `CONTENT_STORAGE_BACKEND=minio` for local testing. Use `adls` only when the Azure storage settings are configured and you intentionally want to write to ADLS.

## Run Mode 1: Manual CLI

Manual CLI is best for parser debugging and small controlled runs.

What this mode does:

- Calls `python -m src.scraper.run` directly.
- Bypasses Prefect orchestration completely.
- Runs only the news scraping engine.
- Does not run market data collection.
- Does not generate missing keywords.

When to use it:

- You are debugging a parser such as CafeF.
- You want quick feedback with a single ticker.
- You want to cap crawling with `--max-pages`.
- You want to test MinIO output locally before using ADLS.

Run one ticker on CafeF and cap the crawl to one page per keyword:

```powershell
python -m src.scraper.run --ticket ACB --source cafef --max-pages 1 --content-storage-backend minio
```

Run multiple tickers:

```powershell
python -m src.scraper.run --ticket ACB,FPT,VCB --source cafef --max-pages 2 --content-storage-backend minio
```

Run every active ticker on every registered source:

```powershell
python -m src.scraper.run --ticket all --source all --content-storage-backend minio
```

CLI options:

- `--ticket`: `all`, one ticker, or comma-separated tickers.
- `--source`: `all`, one source, or comma-separated sources.
- `--max-pages`: per-run override for `SCRAPER_MAX_PAGES`.
- `--triggered-by`: stored in the crawl job note. Values are `manual`, `cron`, or `prefect`.
- `--content-storage-backend`: `minio` or `adls`.

The CLI does not run Vietstock market data and does not generate missing keywords. It only consumes active keyword rows that already exist in PostgreSQL.

Typical operator sequence:

1. Start local dependencies.
2. Confirm the ticker already has active keywords in PostgreSQL.
3. Run one ticker on one source with `--max-pages 1`.
4. Inspect logs in `logs/scraper`.
5. If the result is correct, widen to more pages or more tickers.

## Run Mode 2: Manual Prefect UI

Manual UI is best when you want the standard orchestration shape and Prefect run history.

What this mode does:

- Starts a deployment already registered by `src.flows.deploy`.
- Keeps a Prefect run record, parameters, and logs.
- Can run the full standard flow or only the news stage.

When to use it:

- You want the same orchestration path used by automation.
- You want to control `skip_market_data` or `skip_keyword_generation`.
- You want manual trigger history and status in Prefect.

Open:

```text
http://localhost:4201
```

Choose deployment:

```text
financial-news-standard-scraper/manual
```

Debug one ticker on CafeF only:

```json
{
  "tickers": ["ACB"],
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

Run all active tickers on CafeF only:

```json
{
  "tickers": null,
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

Run the full standard flow manually:

```json
{
  "tickers": null,
  "source_filter": null,
  "skip_market_data": false,
  "skip_keyword_generation": false,
  "content_storage_backend": "minio"
}
```

Use `skip_market_data=true` when you only want news scraping. Use `skip_keyword_generation=true` when keyword rows are already present and you do not want to call Gemini.

Recommended UI parameter patterns:

- Parser debug: one ticker, one source, both skip flags `true`.
- Manual production-like run: all tickers, `source_filter=null`, both skip flags `false`.
- News-only run after market data already completed: `skip_market_data=true`, optionally `skip_keyword_generation=true`.

## Run Mode 3: Scheduled Automation

Automation is served by the local `prefect-worker` service in `docker-compose.local.yml`:

```text
python -m src.flows.deploy
```

The deploy script registers these schedules:

| Deployment | Schedule | Purpose |
| --- | --- | --- |
| `financial-news-market-data/noon` | 12:00 ICT daily | Vietstock market data, morning snapshot |
| `financial-news-market-data/afternoon` | 15:00 ICT daily | Vietstock market data, afternoon snapshot |
| `financial-news-standard-scraper/daily` | 16:00 ICT daily | News scraping only |
| `financial-news-standard-scraper/manual` | none | Manual UI/API trigger |

The scheduled daily news deployment sets `skip_market_data=true` because market data has dedicated schedules.

How local automation works end-to-end:

1. Docker starts `prefect-server`, `prefect-services`, metadata Postgres, MinIO, and `prefect-worker`.
2. `prefect-worker` runs `python -m src.flows.deploy`.
3. That process serves the active deployments to the Prefect server.
4. Prefect triggers each deployment by cron schedule.
5. The deployment calls the corresponding flow function.
6. The flow calls the canonical scraper engine for the news stage.

Operational note:

- If `prefect-worker` is not running, schedules exist only on paper; nothing is actively serving those deployments.

## Run Mode 4: Prefect API Or CLI Trigger

After deployments are served, a run can also be created through Prefect tooling/API. Use the same parameters as the UI manual run.

Typical deployment name:

```text
financial-news-standard-scraper/manual
```

Use API/CLI triggers for scripts that need to start a Prefect run but still want Prefect observability.

This mode is useful when:

- another service wants to trigger scraping programmatically,
- you want a scriptable manual trigger without using the UI,
- you still want Prefect logs and run history.

## What Gets Written

For each scraper run:

- `scraping.sources`: source registration such as `cafef`.
- `scraping.crawl_jobs`: one row for the run.
- `scraping.crawl_logs`: one row per source/keyword attempt.
- `core.article_metadata`: article metadata and content path.
- `core.article_stock_mapping`: article to ticker mappings.
- ADLS or MinIO: full article JSON payload with text/image blocks.
- `logs/scraper`: plain text and JSON logs for local inspection/Fluent Bit.

## Troubleshooting

If no articles are scraped:

1. Confirm `core.stocks` has active tickers.
2. Confirm `scraping.keywords` has active keywords for those tickers.
3. Run one ticker with `--max-pages 1`.
4. Check `logs/scraper` for parser or HTTP errors.
5. Check `scraping.crawl_jobs` and `scraping.crawl_logs` for failure details.

If the init SQL did not run:

- Postgres only runs `/docker-entrypoint-initdb.d` scripts when the data directory is empty.
- If `metadata_postgres_data` already exists, the schema will not be recreated automatically.

If a source selector breaks:

1. Save listing and detail HTML samples.
2. Update only the source parser, for example `src/scraper/cafef/cafef_scraper.py`.
3. Keep parser code free of HTTP, DB, storage, and Prefect logic.
4. Re-test with CLI and `--max-pages 1`.

## Adding A New Source

For a normal source, add:

```text
src/scraper/{source}/
  __init__.py
  {source}_scraper.py
  {SOURCE}_INSTRUCTION.md
```

Then register the parser in `src/scraper/engine/registry.py`.

After registration, both CLI and Prefect can use the source through `--source {source}` or `source_filter={source}`. No flow change is needed for standard news scraping.

See `src/scraper/SOURCE_ONBOARDING.md` for the parser contract and checklist.

## Adding A New Source: Exact Scope

Creating a new source is almost, but not entirely, just "add a folder and write a scraper script".

The minimum complete change set is:

1. Create `src/scraper/{source}/`.
2. Add `__init__.py`.
3. Add `{source}_scraper.py` implementing the parser contract.
4. Add `{SOURCE}_INSTRUCTION.md` documenting selectors, pagination, and run commands.
5. Register the parser in `src/scraper/engine/registry.py`.

You do not need to change Prefect flow code for a normal source. Once the parser is registered, the source is available to both:

- CLI via `--source {source}`
- Prefect via `source_filter={source}`

You only need flow changes if the new source requires a special schedule, source-specific parameters, or a custom orchestration stage.

Examples:

- Normal source: no flow change needed.
- Source with a different crawl window or legal rate limit: maybe add a separate deployment.
- Source that needs pre-processing before scraping: flow change may be required.
