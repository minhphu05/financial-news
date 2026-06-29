# Legacy Scraper

`legacy/` contains the older scraper implementation kept for reference and migration support.

## Current Status

Do not use this folder for new production work. The current standard path is:

```text
src/scraper/run.py
src/scraper/engine/
src/scraper/storage/
src/scraper/{source}/
src/flows/
```

## When To Look Here

Use legacy code only when:

- Comparing old parsing behavior.
- Recovering old selectors.
- Migrating an old source into the new `BaseParser` pattern.

New sources should not be added here.
