# Incremental Scraping

This document explains how the scraper avoids re-downloading content it has already seen, how it resumes after being interrupted, and how to tune the relevant parameters.

---

## Problem

CafeF.vn does not provide an API. The only way to discover new articles for a ticker is to paginate through search results. Without any state management, every run would:

- Fetch the same listing pages repeatedly
- Hit the same already-known articles hundreds of times
- Take progressively longer as the article archive grows

**Incremental scraping** solves this by maintaining a cursor per `(source, keyword)` pair and stopping early when we detect we've reached content we already have.

---

## How It Works

### The Cursor — `scrape_progress`

After every keyword finishes, the scraper writes (or updates) a row in the `scrape_progress` table:

```
source   keyword  last_page_scraped  last_scraped_news_id  total_articles_scraped  is_exhausted
------   -------  -----------------  --------------------  ----------------------  ------------
cafef    BCM      8                  123456789             120                     false
cafef    Becamex  3                  987654321             45                      false
cafef    ACB      200                555000000             3000                    true
```

On the **next run**, the scraper can consult this cursor to decide where to start.

### The Early-Stop Mechanism

The key insight is: **CafeF search results are ordered newest-first**. So when the scraper finds a sequence of articles it already has in the database, all subsequent pages are guaranteed to contain only older, already-seen articles.

The early-stop algorithm (in `page_scraper.py`):

```python
consecutive_known = 0

for page in range(1, max_pages + 1):
    entries = parse_listing_page(html)

    for entry in entries:
        if storage.article_exists(entry.news_id):
            consecutive_known += 1
        else:
            consecutive_known = 0          # reset on any new article
            fetch_and_persist(entry)

        if consecutive_known >= settings.consecutive_known_threshold:
            logger.info("Early stop: %d consecutive known articles", consecutive_known)
            return result(early_stopped=True)

    if is_listing_exhausted(html):
        return result(is_exhausted=True)

return result(early_stopped=False, is_exhausted=False)
```

**Threshold tuning** — `SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD` (default: `10`):

| Value | Behaviour |
|-------|-----------|
| Low (3–5) | Stops very quickly — misses new articles interspersed with old ones |
| Default (10) | Balanced — unlikely to miss a burst of new articles in the middle |
| High (30+) | Thorough — more HTTP requests but safer on noisy feeds |

> **Why not stop on the first known article?** A ticker may have new articles on page 3 even if pages 1–2 are fully known (e.g., delayed indexing by CafeF, articles from overlapping keywords). A threshold of 10 consecutive known articles is a strong signal that we've exhausted the new content.

---

## First Run vs. Subsequent Runs

### First Run (no cursor)

```
keyword = "BCM"
no row in scrape_progress → start from page 1, no early-stop history

Page 1 → 10 new articles (all unknown)
Page 2 → 10 new articles
...
Page N → is_listing_exhausted() = True
→ is_exhausted = True written to scrape_progress
```

### Second Run (cursor exists)

```
keyword = "BCM"
scrape_progress: last_page_scraped=8, last_scraped_news_id="123456789"

Page 1 → article[0] known, article[1] known, ..., article[9] new
         → consecutive_known resets on article[9]
Page 2 → all 10 articles known
Page 3 → all 10 articles known
         → consecutive_known = 20 >= threshold 10
→ early_stop = True, only page 1 yielded new articles
```

### Re-scraping After a Source Update

If CafeF re-orders or re-indexes articles (rare but possible), the cursor may prevent discovery of some articles. To force a full re-scrape for a specific keyword:

```sql
-- Reset progress for a keyword
UPDATE scrape_progress
SET is_exhausted = FALSE, last_page_scraped = 0
WHERE source = 'cafef' AND keyword = 'BCM';

-- Or delete the cursor entirely
DELETE FROM scrape_progress WHERE keyword = 'BCM';
```

---

## Detecting Unscraped news_ids

Sometimes you want to find which `news_id` values are in PostgreSQL but their detail content is missing from MongoDB (e.g., a detail fetch failed mid-run).

```sql
-- Get news_ids that need re-fetching
-- (PostgreSQL side: all articles)
SELECT news_id FROM news_articles WHERE ticker_symbol = 'BCM';
```

```javascript
// MongoDB side: articles with null content
db.articles_content.find(
  { content: null, ticker_symbol: "BCM" },
  { news_id: 1 }
)
```

Then re-run the scraper — because it checks `article_exists(news_id)` which queries `news_articles` in PostgreSQL, it will **skip** metadata-only articles. To force re-fetch of content:

```sql
-- Option 1: Delete from Postgres to force full re-process
DELETE FROM news_articles WHERE news_id IN ('123', '456');
```

```javascript
// Option 2: Delete from MongoDB only — the scraper will re-write content
db.articles_content.deleteMany({ content: null, ticker_symbol: "BCM" })
```

> Note: Option 2 alone won't trigger a re-scrape because `article_exists()` checks PostgreSQL. You'd need to pair it with deleting the PostgreSQL row, or write a dedicated "backfill" script.

---

## The `is_exhausted` Flag

When CafeF's search returns a "no results" page (`is_listing_exhausted()` returns `True`), the keyword is marked `is_exhausted = TRUE` in `scrape_progress`.

**Currently**, the scraper does NOT skip exhausted keywords — it still runs them (they terminate very quickly at page 1). This is intentional: new articles for a previously-exhausted keyword may appear when the source re-indexes. Setting `is_exhausted = TRUE` is informational only.

To act on this flag (skip exhausted keywords entirely), the pipeline would check:

```python
progress = storage.get_progress(source, keyword)
if progress and progress.is_exhausted:
    logger.info("Keyword %s is exhausted — skipping", keyword)
    continue
```

This optimization is not enabled by default but can be added when needed.

---

## Monitoring Incremental Progress

### Via Logs

Watch for early-stop messages in Grafana:

```logql
# Explore: find all early-stop events
{job="scraper"} |= "Early stop"

# Which keywords stopped early?
{job="scraper"} |= "Early stop" | json | line_format "{{.ticker_symbol}}/{{.keyword}}"
```

### Via Database

```sql
-- Overall coverage
SELECT
    ticker_symbol,
    COUNT(DISTINCT keyword) AS keywords,
    SUM(total_articles_scraped) AS total_scraped,
    MAX(last_scraped_at) AS last_run,
    BOOL_OR(is_exhausted) AS any_exhausted
FROM scrape_progress
GROUP BY ticker_symbol
ORDER BY ticker_symbol;

-- Keywords that stopped early (large page count suggests hitting the threshold)
SELECT keyword, ticker_symbol, last_page_scraped, total_articles_scraped
FROM scrape_progress
WHERE last_page_scraped < 200        -- didn't reach max_pages
  AND is_exhausted = FALSE           -- didn't exhaust the source
ORDER BY total_articles_scraped DESC;

-- Find new articles added in the last run
SELECT ticker_symbol, COUNT(*) AS new_articles
FROM news_articles
WHERE scraped_at >= (
    SELECT started_at FROM scrape_runs ORDER BY started_at DESC LIMIT 1
)
GROUP BY ticker_symbol;
```

---

## Environment Variables Reference

| Variable | Default | Effect |
|----------|---------|--------|
| `SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD` | `10` | Number of consecutive already-seen articles before stopping pagination |
| `CAFEF_MAX_PAGES` | `200` | Hard cap on listing pages per keyword (regardless of early-stop) |
| `CAFEF_START_PAGE` | `1` | First listing page to fetch (change to resume from a known page) |

### Example: Aggressive Daily Run

For a nightly cron that only needs the freshest articles:

```bash
SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD=5 \
CAFEF_MAX_PAGES=10 \
python -m src.scraper.run --triggered-by cron
```

### Example: Full Archive Backfill

For an initial full scrape of the entire history:

```bash
SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD=9999 \
CAFEF_MAX_PAGES=200 \
python -m src.scraper.run --triggered-by manual
```

Setting the threshold to a huge number effectively disables early-stop.

---

## Sequence Diagram

```
run.py
  └── run_pipeline()
        ├── storage.create_scrape_run()          → INSERT INTO scrape_runs (status='running')
        │
        ├── for each (ticker, keyword):
        │     ├── set_log_context(ticker, keyword, run_id)
        │     │
        │     └── scrape_keyword()
        │           ├── page = 1
        │           ├── consecutive_known = 0
        │           │
        │           ├── loop:
        │           │   ├── client.get(listing_page)
        │           │   ├── parse_listing_page() → [entry1, entry2, ...]
        │           │   │
        │           │   ├── for each entry:
        │           │   │   ├── article_exists(news_id)?
        │           │   │   │   ├── YES → consecutive_known += 1
        │           │   │   │   │         check threshold → early_stop?
        │           │   │   │   └── NO  → consecutive_known = 0
        │           │   │   │             client.get(detail_page)
        │           │   │   │             parse_detail_page()
        │           │   │   │             storage.save_article()
        │           │   │
        │           │   └── is_listing_exhausted? → break
        │           │
        │           └── storage.update_progress()   → UPSERT scrape_progress
        │
        └── storage.finish_scrape_run()             → UPDATE scrape_runs
```
</content>
