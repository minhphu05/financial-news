# Adding A New News Source

This guide describes how to add a new news source such as `thanhnien`, `tuoitre`, `vnexpress`, or `baomoi`.

## Short Answer

Almost yes. For a new source, create a folder and a `{source}_scraper.py` file:

```text
src/scraper/{source}/
  __init__.py
  {source}_scraper.py
  {SOURCE}_INSTRUCTION.md
```

Then register the parser in `src/scraper/engine/registry.py`.

So the real answer is:

- create the source folder,
- implement the parser script,
- add the instruction markdown,
- register the parser.

You do not need to modify Prefect flows for a standard source.

## Required Parser Contract

Your parser must subclass `BaseParser` from `src.scraper.engine.base_parser`.

```python
from src.scraper.engine.base_parser import BaseParser
from src.scraper.engine.types import ArticleDetail, ListingEntry


class ThanhnienParser(BaseParser):
    name = "thanhnien"
    base_url = "https://thanhnien.vn"
    default_language = "vi"

    def build_search_url(self, keyword: str, page: int) -> str:
        ...

    def is_listing_exhausted(self, html: str) -> bool:
        ...

    def parse_listing(self, html: str) -> list[ListingEntry]:
        ...

    def parse_detail(self, html: str) -> ArticleDetail:
        ...
```

## Files To Add

### `src/scraper/{source}/{source}_scraper.py`

Contains only source-specific URL and DOM parsing logic. Do not put HTTP calls, database writes, or ADLS/MinIO writes here.

### `src/scraper/{source}/__init__.py`

Exports the parser:

```python
from src.scraper.thanhnien.thanhnien_scraper import ThanhnienParser

__all__ = ["ThanhnienParser"]
```

### `src/scraper/{source}/{SOURCE}_INSTRUCTION.md`

Documents selectors, pagination, URL format, known limitations, and test commands for that source.

## Register The Source

Edit `src/scraper/engine/registry.py`:

```python
from src.scraper.thanhnien import ThanhnienParser

_REGISTRY = {
    CafefParser.name: CafefParser,
    ThanhnienParser.name: ThanhnienParser,
}
```

After this, the source can be used by CLI and Prefect UI through `source_filter` / `--source`.

## Test Checklist

1. Parser imports successfully.
2. `build_search_url("ACB", 1)` returns a valid search URL.
3. `parse_listing(html)` returns `ListingEntry` objects with absolute URLs.
4. `parse_detail(html)` returns title, content, published date, and ordered blocks.
5. `python -m src.scraper.run --ticket ACB --source {source} --max-pages 1 --content-storage-backend minio` works locally.
6. Prefect manual run works with:

```json
{
  "tickers": ["ACB"],
  "source_filter": "{source}",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

## Parser Responsibilities

The parser owns:

- Search URL format.
- Empty/exhausted listing detection.
- Listing item selectors.
- Detail page selectors.
- Publication datetime parsing.
- Text/image block extraction.

The parser must not own:

- HTTP retry logic.
- Database access.
- ADLS or MinIO writes.
- Prefect scheduling.
- Keyword generation.
