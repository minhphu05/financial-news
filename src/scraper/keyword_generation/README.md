# Keyword Generation

`keyword_generation/` creates LLM-generated scraping keywords for tickers missing active keywords in PostgreSQL.

## File

- `gemini_keyword_generator.py`: loads target tickers, calls Gemini, writes audit output, and persists generated keywords.

## How It Fits The Standard Flow

`src/flows/standard_scraper_flow.py` runs:

1. `market_data_task`
2. `missing_keyword_task`
3. `scrape_task`

`missing_keyword_task` uses this folder. It only generates keywords for tickers that do not already have active keywords.

## Required Environment

```text
GEMINI_API_KEY
METADATA_POSTGRES_HOST_EXTERNAL
METADATA_POSTGRES_EXTERNAL_PORT
METADATA_POSTGRES_USER
METADATA_POSTGRES_PASSWORD
METADATA_POSTGRES_DB
```

## Skip Keyword Generation

For manual UI runs where you only want to scrape using existing keywords:

```json
{
  "skip_keyword_generation": true
}
```

For CLI-only scraper runs, keyword generation is not part of `python -m src.scraper.run`; it is part of the standard Prefect flow.
