# Database Schema Reference

This document describes every table in **PostgreSQL** and every collection in **MongoDB** used by the financial-news stack.

---

## PostgreSQL 17 — `financial_metadata`

Connection details (from `.env`):

```bash
Host:     localhost
Port:     5434
Database: financial_metadata
User:     metadata_user
Password: metadata_password
```

DSN: `postgresql+psycopg2://metadata_user:metadata_password@localhost:5434/financial_metadata`

Connect via psql:
```bash
psql -h localhost -p 5434 -U metadata_user -d financial_metadata
```

---

### Table: `news_articles`

Stores deduplicated metadata for every article scraped. The `news_id` column is the stable cross-store identifier that links this table to MongoDB.

```sql
CREATE TABLE news_articles (
    news_id         TEXT        PRIMARY KEY,
    source          TEXT        NOT NULL,          -- e.g. 'cafef'
    url             TEXT        NOT NULL,
    title           TEXT,
    summary         TEXT,
    author          TEXT,
    ticker_symbol   TEXT,                          -- VN30 ticker, e.g. 'BCM'
    keyword         TEXT,                          -- search keyword that found this article
    created_at      TIMESTAMPTZ,                   -- article publication date (from source)
    scraped_at      TIMESTAMPTZ NOT NULL,          -- when the scraper persisted this row
    updated_at      TIMESTAMPTZ                    -- last upsert timestamp
);
```

#### Column Details

| Column | Type | Notes |
|--------|------|-------|
| `news_id` | TEXT PK | Numeric ID extracted from the CafeF URL slug (e.g. `"123456789"`) |
| `source` | TEXT NOT NULL | Source site identifier; always `"cafef"` currently |
| `url` | TEXT NOT NULL | Full canonical URL of the article |
| `title` | TEXT | Article headline; `NULL` if parse failed |
| `summary` | TEXT | Short excerpt from the listing page; `NULL` if not available |
| `author` | TEXT | Byline; `NULL` if not present on detail page |
| `ticker_symbol` | TEXT | The VN30 ticker that triggered discovery of this article |
| `keyword` | TEXT | Exact keyword string used in the search query |
| `created_at` | TIMESTAMPTZ | Article's own publication timestamp; `NULL` if parsing failed |
| `scraped_at` | TIMESTAMPTZ | UTC timestamp when the scraper wrote this row |
| `updated_at` | TIMESTAMPTZ | Set on every upsert — useful for tracking re-scrapes |

#### Indexes

```sql
-- Implicit primary key index on news_id

-- Ticker + date queries (most common access pattern)
CREATE INDEX ix_news_articles_ticker_created
    ON news_articles(ticker_symbol, created_at DESC);

-- Date-range queries across all tickers
CREATE INDEX ix_news_articles_created_at
    ON news_articles(created_at DESC);

-- Source filtering
CREATE INDEX ix_news_articles_source
    ON news_articles(source);
```

#### Common Queries

```sql
-- Articles per ticker
SELECT ticker_symbol, COUNT(*) AS total
FROM news_articles
GROUP BY ticker_symbol
ORDER BY total DESC;

-- Latest 10 articles for a ticker
SELECT news_id, title, created_at
FROM news_articles
WHERE ticker_symbol = 'BCM'
ORDER BY created_at DESC
LIMIT 10;

-- Articles in a date range
SELECT *
FROM news_articles
WHERE created_at BETWEEN '2026-01-01' AND '2026-05-31'
  AND ticker_symbol = 'ACB'
ORDER BY created_at DESC;

-- How many articles were scraped today
SELECT COUNT(*)
FROM news_articles
WHERE scraped_at >= CURRENT_DATE;

-- Articles with missing publication date
SELECT news_id, title, url
FROM news_articles
WHERE created_at IS NULL;
```

#### UPSERT Behaviour

The storage layer uses PostgreSQL's `ON CONFLICT` to handle duplicate scrapes:

```sql
INSERT INTO news_articles (news_id, source, url, ...)
VALUES (...)
ON CONFLICT (news_id) DO UPDATE SET
    title        = EXCLUDED.title,
    summary      = EXCLUDED.summary,
    updated_at   = NOW();
```

This means **re-scraping an existing article only updates metadata fields** — it does not create duplicate rows.

---

### Table: `scrape_runs`

Audit log for every scraper invocation. One row per `run_pipeline()` call.

```sql
CREATE TABLE scrape_runs (
    run_id              SERIAL      PRIMARY KEY,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    duration_seconds    FLOAT,
    source              TEXT        NOT NULL,       -- 'cafef'
    triggered_by        TEXT        NOT NULL,       -- 'manual' | 'cron' | 'prefect'
    tickers_filter      TEXT,                       -- JSON array or NULL (= all tickers)
    articles_found      INTEGER     DEFAULT 0,
    articles_new        INTEGER     DEFAULT 0,
    articles_skipped    INTEGER     DEFAULT 0,
    pages_crawled       INTEGER     DEFAULT 0,
    errors_count        INTEGER     DEFAULT 0,
    status              TEXT        NOT NULL DEFAULT 'running',
    error_message       TEXT
);
```

#### Column Details

| Column | Type | Notes |
|--------|------|-------|
| `run_id` | SERIAL PK | Auto-increment integer |
| `started_at` | TIMESTAMPTZ | Wall-clock start time (UTC) |
| `finished_at` | TIMESTAMPTZ | `NULL` while status=running |
| `duration_seconds` | FLOAT | Total seconds; `NULL` while running |
| `source` | TEXT | Source site identifier |
| `triggered_by` | TEXT | One of `manual`, `cron`, `prefect` |
| `tickers_filter` | TEXT | JSON: `["BCM","ACB"]` or `NULL` for all tickers |
| `articles_found` | INTEGER | Total listings discovered on all pages |
| `articles_new` | INTEGER | Articles actually written to storage |
| `articles_skipped` | INTEGER | Already-existing articles (deduped) |
| `pages_crawled` | INTEGER | Listing pages fetched |
| `errors_count` | INTEGER | Count of non-fatal errors during the run |
| `status` | TEXT | `running` → `completed` / `failed` / `aborted` |
| `error_message` | TEXT | Top-level exception message for `failed` runs |

#### Status Flow

```
[process starts]
      │
   'running'
      │
      ├── normal completion  → 'completed'
      ├── unhandled exception → 'failed' (error_message populated)
      └── KeyboardInterrupt  → 'aborted'
```

#### Common Queries

```sql
-- Last 10 runs
SELECT run_id, started_at, duration_seconds, articles_new, status
FROM scrape_runs
ORDER BY started_at DESC
LIMIT 10;

-- All failed runs
SELECT run_id, started_at, error_message
FROM scrape_runs
WHERE status = 'failed'
ORDER BY started_at DESC;

-- Total articles scraped by trigger type
SELECT triggered_by, SUM(articles_new) AS total_new
FROM scrape_runs
WHERE status = 'completed'
GROUP BY triggered_by;

-- Average run duration (last 30 days)
SELECT AVG(duration_seconds) / 60 AS avg_minutes
FROM scrape_runs
WHERE status = 'completed'
  AND started_at >= NOW() - INTERVAL '30 days';

-- Runs still in 'running' state (potential zombies)
SELECT run_id, started_at
FROM scrape_runs
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '1 hour';
```

---

### Table: `scrape_progress`

Stores the incremental scraping cursor per `(source, keyword)` pair. Enables the scraper to resume from where it left off and skip already-seen articles.

```sql
CREATE TABLE scrape_progress (
    id                      SERIAL      PRIMARY KEY,
    source                  TEXT        NOT NULL,
    keyword                 TEXT        NOT NULL,
    ticker_symbol           TEXT,
    last_page_scraped       INTEGER     DEFAULT 0,
    last_scraped_at         TIMESTAMPTZ,
    last_scraped_news_id    TEXT,
    total_articles_scraped  INTEGER     DEFAULT 0,
    is_exhausted            BOOLEAN     DEFAULT FALSE,

    CONSTRAINT uq_scrape_progress_source_keyword
        UNIQUE (source, keyword)
);
```

#### Column Details

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | Auto-increment integer |
| `source` | TEXT NOT NULL | Source site identifier (`cafef`) |
| `keyword` | TEXT NOT NULL | Search keyword |
| `ticker_symbol` | TEXT | VN30 ticker this keyword belongs to |
| `last_page_scraped` | INTEGER | Last listing page number fully processed |
| `last_scraped_at` | TIMESTAMPTZ | UTC timestamp of most recent update |
| `last_scraped_news_id` | TEXT | Most recent `news_id` seen in this keyword's stream |
| `total_articles_scraped` | INTEGER | Cumulative count across all runs |
| `is_exhausted` | BOOLEAN | `TRUE` when source reports no more pages |

#### UPSERT Behaviour

Progress rows are created or updated after each keyword completes:

```sql
INSERT INTO scrape_progress (source, keyword, ticker_symbol, ...)
VALUES (...)
ON CONFLICT (source, keyword) DO UPDATE SET
    last_page_scraped     = EXCLUDED.last_page_scraped,
    last_scraped_at       = NOW(),
    last_scraped_news_id  = EXCLUDED.last_scraped_news_id,
    total_articles_scraped = scrape_progress.total_articles_scraped
                             + EXCLUDED.total_articles_scraped,
    is_exhausted          = EXCLUDED.is_exhausted;
```

#### Common Queries

```sql
-- Progress for all keywords
SELECT keyword, ticker_symbol, last_page_scraped, total_articles_scraped, is_exhausted
FROM scrape_progress
ORDER BY ticker_symbol, keyword;

-- Keywords marked as exhausted (all pages scraped)
SELECT keyword, ticker_symbol, last_page_scraped
FROM scrape_progress
WHERE is_exhausted = TRUE;

-- Keywords not yet started
SELECT k.ticker_symbol, k.keyword
FROM (VALUES ('BCM','BCM'),('BCM','Becamex'),('ACB','ACB')) AS k(ticker_symbol, keyword)
LEFT JOIN scrape_progress sp USING (keyword)
WHERE sp.keyword IS NULL;

-- Reset progress for a keyword (force full re-scrape)
DELETE FROM scrape_progress WHERE keyword = 'BCM';
-- or softer reset:
UPDATE scrape_progress
SET is_exhausted = FALSE, last_page_scraped = 0
WHERE keyword = 'BCM';
```

---

## MongoDB 8 — `financial_news_raw`

Connection details:

```bash
Host:     localhost
Port:     27018
Auth DB:  admin
User:     admin
Password: admin
```

URI: `mongodb://admin:admin@localhost:27018/?authSource=admin`

Connect via mongosh:
```bash
mongosh "mongodb://admin:admin@localhost:27018/financial_news_raw?authSource=admin"
```

---

### Collection: `financial_news_raw.articles_content`

Stores the full scraped content of each article. MongoDB is used here because article bodies are variable-length, semi-structured, and do not benefit from relational joins.

#### Document Schema

```json
{
  "_id":        "123456789",
  "news_id":    "123456789",
  "url":        "https://cafef.vn/...",
  "title":      "BCM báo lãi quý 1 tăng 30%",
  "content":    "Toàn văn bài viết...",
  "author":     "Nguyen Van A",
  "created_at": { "$date": "2026-05-28T10:00:00.000Z" },
  "scraped_at": { "$date": "2026-05-28T23:12:45.123Z" },
  "source":     "cafef",
  "ticker_symbol": "BCM",
  "keyword":    "BCM"
}
```

#### Field Details

| Field | Always Present | Description |
|-------|---------------|-------------|
| `_id` | ✓ | Same as `news_id` — string, not ObjectId |
| `news_id` | ✓ | Duplicate of `_id` for convenience |
| `url` | ✓ | Full article URL |
| `title` | ✓ | Article headline |
| `content` | | Full article body text (may be `null` if fetch failed) |
| `author` | | Byline text |
| `created_at` | | Publication date from the source site |
| `scraped_at` | ✓ | Scraper write timestamp |
| `source` | ✓ | Source site identifier |
| `ticker_symbol` | | VN30 ticker that triggered this discovery |
| `keyword` | | Search keyword |

#### Indexes

```javascript
// Primary key (implicit)
db.articles_content.getIndexes()
// _id is always indexed

// Add secondary indexes for common queries
db.articles_content.createIndex({ ticker_symbol: 1, created_at: -1 })
db.articles_content.createIndex({ scraped_at: -1 })
db.articles_content.createIndex({ source: 1, keyword: 1 })
```

#### Common Queries

```javascript
use financial_news_raw

// Total articles
db.articles_content.countDocuments()

// Articles for a ticker
db.articles_content.countDocuments({ ticker_symbol: "BCM" })

// Latest 5 articles for BCM
db.articles_content.find(
  { ticker_symbol: "BCM" },
  { title: 1, created_at: 1, url: 1 }
).sort({ created_at: -1 }).limit(5)

// Articles with missing content
db.articles_content.find(
  { content: null },
  { news_id: 1, url: 1, scraped_at: 1 }
)

// Full text of a specific article
db.articles_content.findOne({ _id: "123456789" }, { content: 1 })

// Articles scraped today
db.articles_content.find({
  scraped_at: { $gte: new Date(new Date().setHours(0,0,0,0)) }
}).count()

// Export to a file
// mongosh --eval 'db.articles_content.find({ticker_symbol:"BCM"}).toArray()' financial_news_raw > bcm.json
```

---

## Cross-Store Joins

The `news_id` is the shared key between PostgreSQL and MongoDB. To get full article data:

```python
from src.scraper.storage import StorageManager
from src.scraper.config import get_settings

settings = get_settings()
with StorageManager(settings) as storage:
    # Metadata from Postgres
    articles = storage.get_articles_by_ticker("BCM", limit=10)
    for article in articles:
        # Content from MongoDB
        content = storage.get_article_content(article.news_id)
        print(article.title, content["content"][:200] if content else "(missing)")
```

Or with raw psql + mongosh:

```sql
-- Step 1: Get news_ids from Postgres
SELECT news_id, title FROM news_articles WHERE ticker_symbol = 'BCM' LIMIT 5;
```

```javascript
// Step 2: Look up content in MongoDB
db.articles_content.find(
  { _id: { $in: ["123", "456", "789"] } },
  { title: 1, content: 1 }
)
```

---

## Schema Migrations

The ORM models are defined in `src/scraper/models.py`. All tables are created automatically on first run by:

```python
from src.scraper.storage import StorageManager
with StorageManager(settings) as storage:
    storage._create_tables()  # called automatically in __enter__
```

`Base.metadata.create_all(engine)` is idempotent — safe to run repeatedly. For destructive schema changes (column rename, drop), use manual `ALTER TABLE` statements.

### Recreate Tables (Development)

```bash
# Connect to the DB
psql -h localhost -p 5434 -U metadata_user -d financial_metadata

-- Drop and recreate (DESTRUCTIVE — dev only)
DROP TABLE IF EXISTS scrape_progress, scrape_runs, news_articles CASCADE;

-- Then restart the scraper — tables will be recreated
\q
python -m src.scraper.run --ticker BCM --max-pages 1
```
</content>
