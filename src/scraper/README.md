# Scraper Package Guide

`src/scraper` contains the source-agnostic news crawling engine, source parsers, metadata storage, and local CLI entrypoint for the Financial News scraper.

## What Lives Here

- `run.py`: CLI entrypoint for manual scraper runs.
- `config.py`: environment-driven scraper settings.
- `engine/`: generic orchestration for crawling any registered news source.
- `storage/`: PostgreSQL metadata repository plus ADLS/MinIO content writers.
- `cafef/`: implemented CafeF parser.
- `vietstock/`: market data scraper for HOSE/HNX metrics and VN30/HNX30 memberships.
- `keyword_generation/`: Gemini keyword generation for tickers missing active keywords.
- `legacy/`: older scraper implementation kept for reference/migration only.
- `notebook/`: exploratory notebooks.

Prefect orchestration is outside this package in `src/flows`. The scraper package is the execution engine; Prefect decides when and with which parameters to call it.

## Data Flow

1. Load settings from `.env` and shell environment.
2. Open PostgreSQL metadata connection.
3. Resolve source parsers via `engine/registry.py`.
4. Read active `(ticker, keyword)` pairs from PostgreSQL.
5. For every source and keyword, crawl listing pages and detail pages.
6. Store full article JSON/images in the configured content backend.
7. Store metadata, source, stock links, crawl jobs, and crawl logs in PostgreSQL.

## Content Backend Safety

Production default is ADLS:

```text
CONTENT_STORAGE_BACKEND=adls
```

Local testing can use MinIO:

```text
CONTENT_STORAGE_BACKEND=minio
```

You can also override per run:

```bash
python -m src.scraper.run --ticket all --content-storage-backend minio
python -m src.scraper.run --ticket all --content-storage-backend adls
```

MinIO does not affect ADLS unless the backend is explicitly set to `minio`.

## Run Modes

### 1. Automation By Prefect Schedule

Prefect deployments are registered by:

```bash
python -m src.flows.deploy
```

In local Docker, this is the `prefect-worker` service in `docker-compose.local.yml`.

Current deployments:

- `financial-news-market-data/noon`: market data at 12:00 ICT.
- `financial-news-market-data/afternoon`: market data at 15:00 ICT.
- `financial-news-standard-scraper/daily`: scheduled news run at 16:00 ICT.
- `financial-news-standard-scraper/manual`: manual UI/API trigger.

Daily news uses the active keyword table and runs all tickers unless parameters override it.

### 2. Manual From Prefect UI

Open:

```text
http://localhost:4201
```

Go to `Deployments`, choose `financial-news-standard-scraper/manual`, then click `Run`.

Useful parameter examples:

```json
{
  "tickers": null,
  "source_filter": null,
  "skip_market_data": false,
  "skip_keyword_generation": false,
  "content_storage_backend": "minio"
}
```

Run only ACB on CafeF:

```json
{
  "tickers": ["ACB"],
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

### 3. Manual CLI Without Prefect

Run all active tickers on all registered sources:

```bash
python -m src.scraper.run --ticket all --content-storage-backend minio
```

Run one ticker:

```bash
python -m src.scraper.run --ticket ACB --source cafef --max-pages 2 --content-storage-backend minio
```

Run several tickers:

```bash
python -m src.scraper.run --ticket ACB,FPT,VCB --source cafef --content-storage-backend minio
```

### 4. Docker Local Infrastructure

Start local infra in Docker Desktop:

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose -f docker-compose.local.yml up -d --pull never postgresql-prefect redis-prefect prefect-server prefect-services postgresql minio prefect-worker
```

Check status:

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" compose -f docker-compose.local.yml ps
```

## Adding A New Source

Yes: create a new source folder and a `{source}_scraper.py` parser.

Minimum pattern for `thanhnien`:

```text
src/scraper/thanhnien/
  __init__.py
  thanhnien_scraper.py
  THANHNIEN_INSTRUCTION.md
```

The parser must subclass `BaseParser` and implement:

- `build_search_url`
- `is_listing_exhausted`
- `parse_listing`
- `parse_detail`

Then register it in `src/scraper/engine/registry.py`.

See `SOURCE_ONBOARDING.md` for the full checklist.
