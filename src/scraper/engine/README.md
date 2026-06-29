# Scraper Engine

`engine/` is the source-agnostic crawl runtime. It knows how to crawl, deduplicate, persist, and summarize work, but it does not know the DOM layout of any news site.

## Files

- `base_parser.py`: abstract parser contract every source must implement.
- `types.py`: dataclasses shared between parsers, crawler, and storage.
- `registry.py`: maps source names such as `cafef` to parser classes.
- `crawler.py`: per-keyword crawl loop for one source and one keyword.
- `pipeline.py`: top-level run orchestration across sources and tickers.

## Runtime Flow

1. `pipeline.run_pipeline` resolves source names using `registry.resolve_sources`.
2. It opens PostgreSQL, HTTP client, and content writer.
3. It loads active keywords from PostgreSQL.
4. For each source and keyword, it calls `crawler.crawl_keyword`.
5. `crawler` fetches listing pages, parses article entries, skips known articles, fetches detail pages, uploads content, and writes metadata.

## Source Registry

Only registered sources can be used with `--source` or Prefect `source_filter`.

Current registered source:

```text
cafef
```

When adding `thanhnien`, create `src/scraper/thanhnien/thanhnien_scraper.py` and register `ThanhnienParser` in `registry.py`.

## Manual Testing

Run one source and one ticker:

```bash
python -m src.scraper.run --ticket ACB --source cafef --max-pages 1 --content-storage-backend minio
```

Run every registered source:

```bash
python -m src.scraper.run --ticket ACB --source all --max-pages 1 --content-storage-backend minio
```

## Important Invariants

- Deduplication is based on canonical URL hash and source-native `external_id` when available.
- `seen_ids` is shared per ticker so multiple keywords do not re-scrape the same article.
- Early stop is controlled by `SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD`.
- Parser code must stay pure: no network, DB, Prefect, ADLS, or MinIO logic.
