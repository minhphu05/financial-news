# Scraper — How It Works

This document covers the full scraper pipeline: from reading the keyword spreadsheet to persisting articles in PostgreSQL and MongoDB.

---

## Overview

The scraper targets [CafeF.vn](https://cafef.vn) — a Vietnamese financial news site — and collects articles associated with VN30 ticker symbols. Each run:

1. Reads `data/raw/vn30.xlsx` to get `(ticker, keywords)` pairs.
2. For each keyword, paginates through CafeF's search results.
3. Fetches the detail page of each new article.
4. Persists metadata → PostgreSQL, full content → MongoDB.
5. Records run-level stats and cursor progress for the next incremental run.

---

## Quick Start

```bash
# Full run — all tickers
python -m src.scraper.run

# Filter to specific tickers
python -m src.scraper.run --ticker BCM
python -m src.scraper.run --ticker ACB --ticker BID

# Override max pages for a quick smoke test
python -m src.scraper.run --ticker BCM --max-pages 2

# Mark as cron-triggered (recorded in scrape_runs table)
python -m src.scraper.run --triggered-by cron
```

### Output Files

Every invocation creates two log files in `logs/scraper/`:

| File | Format | Purpose |
|------|--------|---------|
| `scrape_20260528T231245_BCM.log` | Plain text | Human-readable run log |
| `scrape_20260528T231245_BCM.json.log` | JSON (one object per line) | FluentBit ingestion → Loki |

---

## Configuration

All knobs live in `.env` (no hardcoding). The `ScraperSettings` dataclass in `src/scraper/config.py` reads them at startup via `get_settings()` (cached with `@lru_cache`).

### Key Variables

```bash
# Source
SOURCE_NAME=cafef
CAFEF_BASE_URL=https://cafef.vn
CAFEF_SEARCH_URL_TEMPLATE=https://cafef.vn/tim-kiem/trang-{page}.chn?keywords={keyword}
CAFEF_START_PAGE=1
CAFEF_MAX_PAGES=200                  # Max listing pages per keyword

# HTTP behavior
CAFEF_USER_AGENT=Mozilla/5.0 ...
CAFEF_REQUEST_DELAY_MIN=0.5          # Min seconds between requests
CAFEF_REQUEST_DELAY_MAX=1.5          # Max seconds (random jitter)
SCRAPER_TIMEOUT=30                   # Per-request timeout
SCRAPER_MAX_RETRIES=3                # Retry attempts on failure

# Incremental scraping
SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD=10   # Early-stop: consecutive seen articles

# Storage
METADATA_POSTGRES_HOST_EXTERNAL=localhost
METADATA_POSTGRES_EXTERNAL_PORT=5434
MONGO_URI=mongodb://admin:admin@localhost:27018/?authSource=admin
```

---

## Module Reference

### `src/scraper/config.py` — Settings

```python
from src.scraper.config import get_settings

settings = get_settings()
print(settings.max_pages)          # 200
print(settings.postgres_dsn)       # postgresql+psycopg2://...
print(settings.consecutive_known_threshold)  # 10
```

`ScraperSettings` is a **frozen dataclass** — immutable after construction. `get_settings()` is decorated with `@lru_cache(maxsize=1)`, so `.env` is parsed exactly once per process.

To override a setting for a single run without editing `.env`:
```bash
CAFEF_MAX_PAGES=5 python -m src.scraper.run --ticker BCM
```

---

### `src/scraper/parsers.py` — HTML Parsing

Pure functions, no I/O — safe to unit test in isolation.

#### `extract_news_id(url) → str | None`
Extracts the numeric ID from a CafeF URL slug.

```python
from src.scraper.parsers import extract_news_id

extract_news_id("https://cafef.vn/ngan-hang/acb-tang-truong-123456789.chn")
# → "123456789"
```

Regex: `-(\d+)\.chn(?:[?#].*)?$`

#### `parse_listing_page(html, base_url) → list[ListingEntry]`
Scrapes all article references from a search results page.

```python
@dataclass(frozen=True)
class ListingEntry:
    news_id: str
    url: str
    title: Optional[str]
    summary: Optional[str]
```

#### `is_listing_exhausted(html) → bool`
Returns `True` when CafeF signals "no results found" — used to stop pagination early.

#### `parse_detail_page(html) → ArticleDetail`
Extracts the full body, author, and publication date from an individual article page.

```python
@dataclass(frozen=True)
class ArticleDetail:
    title: Optional[str]
    content: Optional[str]
    author: Optional[str]
    created_at: Optional[datetime]
```

---

### `src/scraper/http_client.py` — HTTP Client

```python
class HttpClient:
    def get(self, url: str) -> requests.Response | None
```

Wraps `requests.Session` with:
- **Retry loop** — `max_retries` attempts with exponential backoff starting at `retry_delay` seconds.
- **Jittered delay** — a random pause between `request_delay_min` and `request_delay_max` seconds after every successful response. Prevents rate-limiting.
- **Persistent session** — `User-Agent` and `Accept-Language` headers set once for the session lifetime.
- Returns `None` (not raises) on total failure so the caller can decide to skip or abort.

Use as a context manager:
```python
with HttpClient(settings) as client:
    resp = client.get("https://cafef.vn/...")
    if resp:
        html = resp.text
```

---

### `src/scraper/storage.py` — StorageManager

Single entry point for all database writes. Lazily initializes both connections.

```python
with StorageManager(settings) as storage:
    # Check if article already exists (deduplication)
    if not storage.article_exists(news_id):
        storage.save_article(article)

    # Scrape run tracking
    run_id = storage.create_scrape_run(source="cafef", triggered_by="cron")
    # ... after scraping ...
    storage.finish_scrape_run(run_id, articles_new=42, status="completed")

    # Incremental cursor
    progress = storage.get_progress(source="cafef", keyword="ACB")
    storage.update_progress(source="cafef", keyword="ACB", last_page_scraped=3)
```

#### `save_article(article: ScrapedArticle)`
Atomic dual-store write:
1. **MongoDB first** — `replace_one({"_id": news_id}, document, upsert=True)`
2. **PostgreSQL second** — `INSERT ... ON CONFLICT (news_id) DO UPDATE`

MongoDB is written first so that a successfully committed PostgreSQL row always implies the content is reachable.

#### `article_exists(news_id) → bool`
Queries only the `news_id` primary key column — minimal I/O, used on every article before fetching the detail page.

---

### `src/scraper/page_scraper.py` — Keyword Crawler

```python
result = scrape_keyword(context, settings, client, storage)
# result = {
#     "persisted": 15,
#     "skipped": 45,
#     "found": 60,
#     "pages": 3,
#     "newest_news_id": "123456789",
#     "early_stopped": True,
#     "is_exhausted": False
# }
```

**Termination conditions** (whichever comes first):
1. `is_listing_exhausted()` returns `True` (site says no more results).
2. `max_pages` listing pages visited.
3. Listing page unreachable after all retries.
4. **Incremental early-stop** — `consecutive_known_threshold` already-seen articles in a row.

After completing, calls `storage.update_progress()` to record the cursor for the next run.

---

### `src/scraper/pipeline.py` — Orchestrator

Ties everything together:

```python
from src.scraper.config import get_settings
from src.scraper.pipeline import run_pipeline

settings = get_settings()
summary = run_pipeline(settings, only_tickers=["BCM", "ACB"], triggered_by="manual")
print(summary.render())
```

Lifecycle per run:
1. `create_scrape_run()` — inserts a `scrape_runs` row with `status='running'`.
2. Loads `vn30.xlsx` → filters by `only_tickers` if given.
3. Loops `(ticker, keyword)` pairs → calls `scrape_keyword()`.
4. Aggregates counters across all keywords.
5. `finish_scrape_run()` — updates the row with final stats and `status='completed'`.

---

## Input Data: vn30.xlsx

Located at `data/raw/vn30.xlsx`. Expected columns:

| Column | Example | Description |
|--------|---------|-------------|
| `ticket_symbol` | `BCM` | VN30 ticker symbol |
| `company_name_vi` | `Becamex IDC` | Vietnamese company name |
| `company_name_en` | `Becamex IDC Corp` | English company name |
| `Keywords` | `["BCM", "Becamex"]` | Search terms (Python list or its string repr) |

The `Keywords` column can be either a real Python list or a string like `'["BCM", "Becamex"]'` — both are handled by `_coerce_keywords()`.

---

## Output: What Gets Stored

### PostgreSQL — `news_articles`

One row per unique article. See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for full column details.

```sql
SELECT news_id, ticker_symbol, title, created_at, scraped_at
FROM news_articles
WHERE ticker_symbol = 'BCM'
ORDER BY created_at DESC
LIMIT 10;
```

### MongoDB — `financial_news.articles_content`

```json
{
  "_id": "123456789",
  "news_id": "123456789",
  "content": "<full article body text>",
  "url": "https://cafef.vn/...",
  "scraped_at": "2026-05-28T17:30:00Z"
}
```

Query from mongosh:
```javascript
use financial_news
db.articles_content.find({ news_id: "123456789" })
db.articles_content.countDocuments()
```

---

## Adding a New Source (e.g. VNExpress)

The scraper is designed to support multiple sources. To add VNExpress:

1. **Add a new parser** — create `src/scraper/vnexpress_parsers.py` implementing:
   - `extract_news_id(url)`
   - `parse_listing_page(html, base_url) → list[ListingEntry]`
   - `parse_detail_page(html) → ArticleDetail`
   - `is_listing_exhausted(html) → bool`

2. **Add config** — add env vars to `.env`:
   ```bash
   VNEXPRESS_BASE_URL=https://vnexpress.net
   VNEXPRESS_SEARCH_URL_TEMPLATE=https://vnexpress.net/search?q={keyword}&p={page}
   SOURCE_NAME_VNEXPRESS=vnexpress
   ```

3. **Reuse the rest** — `HttpClient`, `StorageManager`, `pipeline.py` are source-agnostic. Only `page_scraper.py` may need a small adaptation to pass the right parser set.

4. **Logs** — set `source_name` in `set_log_context()` so Loki labels route logs correctly.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Listing page 404 / network error | `client.get()` returns `None` → keyword aborted, error logged |
| Detail page fetch fails | Article skipped; error logged; `errors_count` incremented |
| DB write failure | Exception caught; article skipped; `errors_count` incremented |
| `KeyboardInterrupt` | Caught in `run.py` → returns exit code 130; partial progress saved |
| Unhandled exception | Caught in `run.py` → returns exit code 1; `scrape_runs.status='failed'` |

---

## Scheduled Daily Runs

To run the scraper daily via cron:

```bash
# crontab -e
# Runs at 06:00 every day, logs output
0 6 * * * cd /path/to/financial-news && /opt/anaconda3/bin/python -m src.scraper.run --triggered-by cron >> /var/log/scraper-cron.log 2>&1
```

Or via Prefect (see `src/flows/` for deployment flows).
</content>
