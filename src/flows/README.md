# Prefect Flow Guide

This folder contains the active Prefect orchestration layer for local scraper operations.

## Active Flow Modules

- `deploy.py`: registers deployments with the Prefect server.
- `standard_scraper_flow.py`: standard orchestrator for market data, missing keyword generation, and news scraping.
- `scrape_flow.py`: thin Prefect wrapper around the canonical scraper engine at `src.scraper.engine.pipeline.run_pipeline`.

Inactive RAG, ingestion, evaluation, and reindex flows are kept in `future_use/` for later reuse. They are not registered by the current `python -m src.flows.deploy` entrypoint.

## Inactive Flow Folder

`future_use/` stores Prefect flows that are intentionally not part of the current local scraper schedule.

These files are kept because they may be reused later for:

- RAG ingestion.
- Evaluation.
- Reindexing.
- Medallion processing.
- End-to-end orchestration experiments.

They are not imported by `deploy.py`, so moving them out of the active flow root reduces confusion when operating the current pipeline.

## Current Deployments

Running `python -m src.flows.deploy` registers these deployments:

- `financial-news-market-data/noon`: daily at 12:00 ICT, runs Vietstock market data with `session_note=MORNING`.
- `financial-news-market-data/afternoon`: daily at 15:00 ICT, runs Vietstock market data with `session_note=AFTERNOON`.
- `financial-news-standard-scraper/daily`: daily at 16:00 ICT, runs news scraping only because market data is already scheduled separately.
- `financial-news-standard-scraper/manual`: no schedule, used from Prefect UI/API for ad hoc runs.

## Standard Flow Stages

`standard_scraper_flow` performs these stages unless skipped by parameters:

1. `market_data_task`: scrapes HOSE/HNX metrics and VN30/HNX30 memberships from Vietstock, then writes them to PostgreSQL.
2. `missing_keyword_task`: finds index tickers without active keywords, generates five Gemini keywords, and persists them.
3. `scrape_task`: scrapes registered news sources through the generic scraper engine.

The current registered news sources are `cafef` and `thanhnien`.

## Manual CLI Run

Use the scraper CLI when you want to bypass Prefect and run the news scraping engine directly.

```powershell
python -m src.scraper.run --ticket ACB --source cafef --max-pages 1 --content-storage-backend minio
```

Run every active ticker and every registered source:

```powershell
python -m src.scraper.run --ticket all --source all --content-storage-backend minio
```

The CLI does not run market data or keyword generation. It only runs the news scraper engine.

## Manual Prefect UI Run

Start the local stack, then open the Prefect UI at:

```text
http://localhost:4201
```

Select deployment:

```text
financial-news-standard-scraper/manual
```

Useful one-ticker parameters:

```json
{
  "tickers": ["ACB"],
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

Full standard manual run:

```json
{
  "tickers": null,
  "source_filter": null,
  "skip_market_data": false,
  "skip_keyword_generation": false,
  "content_storage_backend": "minio"
}
```

## Automation

Local automation is handled by the `prefect-worker` service in `docker-compose.local.yml`:

```text
command: python -m src.flows.deploy
```

When this service starts, it connects to the local Prefect server and serves the four deployments listed above. Prefect then triggers scheduled runs by cron schedule.

## Choosing A Run Mode

Use CLI when:

- You are debugging one source parser.
- You want fast feedback with `--max-pages 1`.
- You do not need market data or keyword generation.

Use Prefect UI manual when:

- You want the same orchestration shape as automation.
- You want to skip or include individual standard stages.
- You want run history in Prefect.

Use scheduled automation when:

- The local stack should collect market data and news without manual intervention.
- You want the normal 12:00, 15:00, and 16:00 ICT cadence.

## Adding A Source To The Flow

A new source becomes available to both CLI and Prefect once it is registered in `src.scraper.engine.registry`. No Prefect code change is needed unless the new source needs source-specific scheduling or parameters.
