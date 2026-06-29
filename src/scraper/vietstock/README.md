# Vietstock Market Data

`vietstock/` scrapes HOSE/HNX market data and persists stock metrics plus index memberships.

## File

- `vietstock_scraper.py`: fetches/parses price boards and persists market data.

## How It Runs In Prefect

`src/flows/standard_scraper_flow.py` uses `market_data_task` for market data.

Dedicated market deployments are registered in `src/flows/deploy.py`:

```text
financial-news-market-data/noon
financial-news-market-data/afternoon
```

## Manual UI Parameters

Run market data only through one of the market deployments:

```json
{
  "session_note": "AFTERNOON",
  "is_eod": false,
  "render": "auto",
  "browser_engine": "auto"
}
```

In `financial-news-standard-scraper/manual`, skip market data if you only want news scraping:

```json
{
  "skip_market_data": true
}
```

## Output Tables

Market data is persisted into PostgreSQL metadata tables such as:

- `core.stocks`
- `core.index_memberships`
- `core.stock_metrics`
