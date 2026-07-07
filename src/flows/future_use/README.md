## Purpose

This folder stores Prefect flow modules that are not part of the current scraper deployment path.

They are preserved for future work such as ingestion, evaluation, reindexing, medallion processing, and end-to-end experiments.

## Current Status

- Not registered by `src.flows.deploy`
- Not served by the local `prefect-worker`
- Kept only for future reuse and reference

If one of these flows becomes active again later, it can be imported explicitly and wired back into `deploy.py`.
# Deferred Prefect Flows

These flow modules are kept for future reuse, but they are not part of the current local scraper deployment path.

Current active flow modules in `src/flows/`:

- `deploy.py`: registers Prefect deployments used by `docker-compose.local.yml`.
- `standard_scraper_flow.py`: orchestrates market data, keyword generation, and news scraping.
- `scrape_flow.py`: wraps the canonical `src.scraper.engine.pipeline.run_pipeline` news scraper.

Deferred modules:

- `full_pipeline_flow.py`: older scrape to ingestion composed pipeline.
- `ingest_flow.py`: legacy cleaning and embedding ingestion flow.
- `eval_flow.py`: RAG evaluation flow.
- `medallion_flow.py`: bronze to silver to gold ingestion flow.
- `reindex_flow.py`: Qdrant reindex flow.
- `scrape_quality_flow.py`: older MongoDB/Pydantic scrape quality flow.

To restore a deferred flow, move it back to `src/flows/`, update imports/deployment registration, then add or update the matching run instructions.
