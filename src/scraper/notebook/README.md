# Scraper Notebooks

`notebook/` is for exploratory scraping work, selector experiments, and one-off investigations.

## Current Notebook

- `cafef_test.ipynb`: CafeF parsing/testing notebook.

## Rules

- Do not treat notebooks as production entrypoints.
- Move stable parsing logic into `src/scraper/{source}/{source}_scraper.py`.
- Keep runbook instructions in Markdown files, not only notebooks.

## Suggested Workflow

1. Explore a source in a notebook.
2. Save representative HTML samples if needed.
3. Implement parser methods in a source folder.
4. Register the parser in `engine/registry.py`.
5. Test via CLI or Prefect manual run.
