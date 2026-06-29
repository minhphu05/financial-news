# CafeF Source

`cafef/` contains the implemented parser for CafeF news pages.

## Files

- `cafef_scraper.py`: `CafefParser`, the source-specific parser.
- `CAFEF_INSTRUCTION.md`: detailed selector and run guide.

## Registered Source Name

Use this source name in CLI and Prefect UI:

```text
cafef
```

## Quick Local Test

```bash
python -m src.scraper.run --ticket ACB --source cafef --max-pages 1 --content-storage-backend minio
```

## Prefect UI Manual Run

Deployment:

```text
financial-news-standard-scraper/manual
```

Parameters for one ticker:

```json
{
  "tickers": ["ACB"],
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

Parameters for all tickers on CafeF:

```json
{
  "tickers": null,
  "source_filter": "cafef",
  "content_storage_backend": "minio"
}
```
