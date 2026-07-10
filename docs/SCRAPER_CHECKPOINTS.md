# Scraper Checkpoints and Resume

This document explains how the financial-news scraper resumes after failures.

## Why Checkpoints Exist

The scraper can run across many sources, tickers, keywords, and listing pages. If the process fails in the middle, rerunning from the beginning wastes time and may repeatedly hit the same site pages.

The checkpoint mechanism records progress per logical unit:

```text
source_name + ticker + keyword + run_key
```

On the next run with the same `run_key`, the scraper:

- skips units already marked `COMPLETED`,
- retries units marked `FAILED` or `RUNNING`,
- resumes paginated HTTP sources from `last_page_completed + 1` when possible,
- continues relying on article `url_hash` idempotency to avoid duplicate article rows.

## Storage Table

Checkpoints are stored in PostgreSQL:

```text
scraping.scrape_checkpoints
```

Important columns:

| Column | Meaning |
| --- | --- |
| `source_name` | Parser/source name such as `cafef`. |
| `ticker` | Stock ticker such as `ACB`. |
| `keyword` | Search keyword being crawled. |
| `keyword_id` | Source keyword row id when available. |
| `run_key` | Resume scope. Same key means same resumable run. |
| `status` | `PENDING`, `RUNNING`, `COMPLETED`, or `FAILED`. |
| `last_page_completed` | Deepest listing page fully processed. |
| `pages_crawled` | Pages crawled in the latest attempt for this unit. |
| `articles_found` | Article links found in the latest attempt. |
| `articles_persisted` | New article metadata persisted in the latest attempt. |
| `articles_skipped` | Already-known articles skipped in the latest attempt. |
| `errors_count` | Error count recorded for this unit. |
| `last_error_category` | Last failure category such as `LISTING_UNREACHABLE`. |
| `last_error_message` | Last failure message. |
| `last_started_at` | Last attempt start timestamp. |
| `last_completed_at` | Completion timestamp when status is `COMPLETED`. |
| `updated_at` | Last checkpoint update timestamp. |

The table is created in two ways:

- Fresh database: `docker/postgresql/init-scripts/001-create-scraper-schema.sql`.
- Existing database: `MetadataRepository.connect()` ensures the table exists.

## Default Resume Scope

If you do not provide a checkpoint key, the scraper builds a deterministic daily key:

```text
YYYY-MM-DD|sources=<sources>|tickers=<tickers>|max_keywords=<n|all>|max_pages=<n>
```

This means a failed run can be retried on the same day with the same parameters and it will continue. A new day normally starts a new checkpoint scope, which prevents scheduled daily jobs from being skipped forever.

For long runs that may continue across days, pass an explicit key.

## CLI Usage

Resume is enabled by default:

```powershell
python -m src.scraper.run --ticket ACB --source cafef --max-pages 5 --content-storage-backend minio
```

Use an explicit checkpoint key when you want to retry the same failed run later:

```powershell
python -m src.scraper.run `
  --ticket ACB,FPT `
  --source cafef `
  --max-pages 5 `
  --checkpoint-key manual-2026-07-10-cafef-bank-test `
  --content-storage-backend minio
```

Disable resume and crawl from the configured start page:

```powershell
python -m src.scraper.run --ticket ACB --source cafef --no-resume --content-storage-backend minio
```

## Prefect Usage

Manual deployment parameters can include:

```json
{
  "tickers": ["ACB", "FPT"],
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio",
  "resume_from_checkpoint": true,
  "checkpoint_key": "manual-2026-07-10-cafef-bank-test"
}
```

Set `resume_from_checkpoint=false` to force a clean recrawl for the selected run scope.

## Inspect Checkpoints

Show latest checkpoint rows:

```powershell
docker exec financial-local-metadata-psql psql -U metadata_user -d financial_metadata -c "
select source_name, ticker, keyword, run_key, status, last_page_completed,
       articles_found, articles_persisted, articles_skipped,
       last_error_category, updated_at
from scraping.scrape_checkpoints
order by updated_at desc
limit 20;
"
```

Find failed units for a run key:

```powershell
docker exec financial-local-metadata-psql psql -U metadata_user -d financial_metadata -c "
select source_name, ticker, keyword, last_page_completed, last_error_category, last_error_message
from scraping.scrape_checkpoints
where run_key = 'manual-2026-07-10-cafef-bank-test'
  and status = 'FAILED'
order by updated_at desc;
"
```

Count status by run:

```sql
select run_key, status, count(*)
from scraping.scrape_checkpoints
group by run_key, status
order by run_key desc, status;
```

## Reset Checkpoints

Delete one run scope:

```powershell
docker exec financial-local-metadata-psql psql -U metadata_user -d financial_metadata -c "
delete from scraping.scrape_checkpoints
where run_key = 'manual-2026-07-10-cafef-bank-test';
"
```

Delete one keyword checkpoint:

```sql
delete from scraping.scrape_checkpoints
where source_name = 'cafef'
  and ticker = 'ACB'
  and keyword = 'ACB'
  and run_key = 'manual-2026-07-10-cafef-bank-test';
```

Force one completed keyword to retry:

```sql
update scraping.scrape_checkpoints
set status = 'FAILED', last_error_category = 'MANUAL_RETRY', updated_at = now()
where source_name = 'cafef'
  and ticker = 'ACB'
  and keyword = 'ACB'
  and run_key = 'manual-2026-07-10-cafef-bank-test';
```

## How It Behaves During Failure

1. Before a keyword starts, checkpoint status becomes `RUNNING`.
2. After every fully processed listing page, `last_page_completed` and counters are updated.
3. If the keyword finishes without error, status becomes `COMPLETED`.
4. If listing fetch/parser/pipeline fails, status becomes `FAILED` with error details.
5. On rerun with the same key:
   - `COMPLETED` units are skipped,
   - `FAILED`/`RUNNING` units are retried,
   - if `last_page_completed > 0`, crawling starts at the next page.

## Limits and Safety Notes

- Article-level idempotency still comes from `core.article_metadata.url_hash`; checkpointing does not replace deduplication.
- Page-level resume is most useful for HTTP paginated parsers such as CafeF. Browser/scroll-based parsers may still restart at their first rendered page because they do not expose stable page cursors.
- If a site changes ordering between attempts, a page-level resume can theoretically miss newly inserted articles at earlier pages. For critical recrawls, use `--no-resume` or delete the checkpoint key.
- Daily default run keys prevent old completed checkpoints from causing future scheduled runs to skip work.

## Monitoring Checkpoints

The scraper logs checkpoint decisions as structured JSON events:

- `checkpoint_skip`
- `Keyword completed`

Grafana dashboard `1 - Scraping Realtime Operations` shows keyword progress and live logs. You can also query Loki:

```logql
{job="scraper"} | json | event="checkpoint_skip"
```
