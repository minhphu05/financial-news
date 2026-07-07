# CafeF Scraper Instruction

This document explains how `CafefParser` extracts data from `https://cafef.vn`.

## Source Identity

```text
source name: cafef
base URL   : https://cafef.vn
language   : vi
parser     : src.scraper.cafef.cafef_scraper.CafefParser
```

CafeF is currently the only news source registered in `src/scraper/engine/registry.py`.

## When To Use This Instruction

Use this document when you need to:

- debug CafeF selectors,
- run CafeF manually from CLI,
- run CafeF from Prefect UI,
- onboard another engineer to the CafeF parser,
- compare CafeF behavior before and after parser edits.

## Input Data Required

CafeF scraping does not read keywords from a file at runtime. It reads active
keywords from PostgreSQL through `PostgresKeywordProvider`:

```text
core.stocks
scraping.keywords
```

For a ticker to be scraped, both conditions must be true:

- `core.stocks.is_active = true`
- `scraping.keywords.is_active = true`

The CLI `--ticket` argument only filters existing active keyword rows. If a
ticker has no active keywords, the scraper has nothing to search for.

## Search URL

Default template:

```text
https://cafef.vn/tim-kiem/trang-{page}.chn?keywords={keyword}
```

Override with environment variable:

```text
CAFEF_SEARCH_URL_TEMPLATE
```

Example for keyword `ACB`, page `1`:

```text
https://cafef.vn/tim-kiem/trang-1.chn?keywords=ACB
```

## Listing Extraction

CafeF listing pages are parsed by `parse_listing`.

Important selectors:

```text
empty result: div.search-content-wrap > span
item        : div.list-main > div.search-content-wrap > div.timeline.list-bytags > div.item
title/link  : h3.titlehidden > a
summary     : div.item-content > p.sapo
image       : div.item-content a.avatar img, div.item-content img
```

Each listing item returns a `ListingEntry`:

```text
url
title
summary
external_id
image_url
```

The source-native article id is extracted from URLs ending in:

```text
-<digits>.chn
```

## Detail Extraction

CafeF detail pages are parsed by `parse_detail`.

Important selectors:

```text
title          : h1.title
standard date  : p.dateandcat > span.pdate
magazine date  : a.link-source-name > span.time-source-detail
standard body  : div.contentdetail > div.detail-cmain.ss > div.detail-content.afcbc-body
fallback body  : table[style='border-collapse: collapse;'] > tbody > tr > td > span
category       : p.dateandcat > a.category-page__name, p.dateandcat a
```

Author selector candidates:

```text
p.author
div.author
span.author
p.pauthor
div.detail-author
p.detail-author
meta[name=author]
```

## Content Blocks

The parser preserves article reading order by emitting `ContentBlock` items:

- `type="text"` for text paragraphs.
- `type="image"` for images with optional captions.

The crawler stores these blocks in the article JSON payload in ADLS or MinIO.

## Run Commands

Use `minio` for local runs unless you intentionally want to write article JSON
to ADLS.

### Fastest Local Debug Run

Use this first when changing selectors:

```bash
python -m src.scraper.run --ticket ACB --source cafef --max-pages 1 --content-storage-backend minio
```

Why this command is the default debug command:

- one ticker,
- one source,
- one page,
- local object storage only,
- fastest path to confirm the parser still works.

Run all active tickers on CafeF:

```bash
python -m src.scraper.run --ticket all --source cafef --content-storage-backend minio
```

Run one ticker and cap pages:

```bash
python -m src.scraper.run --ticket ACB --source cafef --max-pages 2 --content-storage-backend minio
```

Run multiple tickers:

```bash
python -m src.scraper.run --ticket ACB,FPT,VCB --source cafef --max-pages 2 --content-storage-backend minio
```

Run CafeF while recording the run as a cron-style trigger in the crawl job note:

```bash
python -m src.scraper.run --ticket all --source cafef --triggered-by cron --content-storage-backend minio
```

### Manual Prefect UI Run For CafeF

Open Prefect UI:

```text
http://localhost:4201
```

Choose deployment:

```text
financial-news-standard-scraper/manual
```

Then use one of these parameter sets.

## What A CafeF Run Writes

Metadata is written to PostgreSQL:

```text
scraping.sources
scraping.crawl_jobs
scraping.crawl_logs
core.article_metadata
core.article_stock_mapping
```

Full article payloads are written to the configured content backend:

```text
CONTENT_STORAGE_BACKEND=minio  -> MinIO bucket
CONTENT_STORAGE_BACKEND=adls   -> ADLS filesystem
```

Each JSON payload contains article metadata plus ordered content blocks. Text
blocks preserve reading order; image blocks preserve image URL and caption when
available.

## Prefect UI Manual Parameters

Deployment:

```text
financial-news-standard-scraper/manual
```

All tickers on CafeF:

```json
{
  "tickers": null,
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

If you want the full standard flow before CafeF scraping, set both skips to
`false`. That will scrape market data first and generate missing keywords before
the news stage:

```json
{
  "tickers": null,
  "source_filter": "cafef",
  "skip_market_data": false,
  "skip_keyword_generation": false,
  "content_storage_backend": "minio"
}
```

## Automation Schedule

CafeF participates in the scheduled news deployment:

```text
financial-news-standard-scraper/daily
```

That deployment runs daily at 16:00 ICT and uses `source_filter=null`, which
means every source registered in `src/scraper/engine/registry.py`. Today that is
only `cafef`.

The dedicated market-data deployments run separately at 12:00 and 15:00 ICT.

Single ticker on CafeF:

```json
{
  "tickers": ["ACB"],
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

### Full Manual Standard Flow Ending In CafeF

Use this when you want the whole standard orchestration before the CafeF stage:

```json
{
  "tickers": null,
  "source_filter": "cafef",
  "skip_market_data": false,
  "skip_keyword_generation": false,
  "content_storage_backend": "minio"
}
```

Effect:

1. Vietstock market data runs.
2. Missing ticker keywords are generated if needed.
3. CafeF scraping runs last.

### What CafeF Needs To Work

Minimum runtime requirements:

- metadata Postgres reachable,
- active ticker rows in `core.stocks`,
- active keyword rows in `scraping.keywords`,
- MinIO or ADLS configured,
- network access to `https://cafef.vn`.

If any of these are missing, the parser may be correct but the run still produces no articles.

## Known Risks

- CafeF DOM selectors may change without warning.
- Some older articles use table-based legacy body layouts; fallback selectors handle text-only extraction.
- Some magazine articles use a different container and date selector.
- Image URLs may be lazy-loaded through `data-original` or `data-src`.

## When Selectors Break

1. Save one listing HTML sample and one detail HTML sample.
2. Update selectors in `CafefParser` only.
3. Keep parser pure: no HTTP, DB, Prefect, ADLS, or MinIO logic.
4. Test with `--max-pages 1` and `--content-storage-backend minio`.

## Parser Maintenance Checklist

Before changing behavior, verify these parser methods still match CafeF:

1. `build_search_url("ACB", 1)` returns a valid CafeF search page.
2. `is_listing_exhausted(html)` detects an empty search result page.
3. `parse_listing(html)` returns absolute article URLs and stable `external_id` values.
4. `parse_detail(html)` returns title, content, date, category, author when present, and ordered blocks.
5. A CLI run with `--ticket ACB --source cafef --max-pages 1 --content-storage-backend minio` completes.

If only CafeF changes, do not edit the generic crawler, storage repository, or
Prefect flow unless the parser contract itself needs to change.

## CafeF Change Boundary

Only edit `cafef_scraper.py` when the issue is:

- search URL shape,
- listing selectors,
- detail selectors,
- date parsing,
- body or image extraction,
- CafeF-specific DOM changes.

Do not edit Prefect flow files for normal CafeF selector maintenance.
