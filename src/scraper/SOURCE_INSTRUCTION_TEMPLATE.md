# {SOURCE} Scraper Instruction Template

Copy this file into a new source folder and rename it to `{SOURCE}_INSTRUCTION.md`, for example:

```text
src/scraper/thanhnien/THANHNIEN_INSTRUCTION.md
```

## Source Identity

```text
source name: {source}
base URL   : https://example.vn
language   : vi
parser     : src.scraper.{source}.{source}_scraper.{Source}Parser
```

## Search URL

Document the search URL template:

```text
https://example.vn/search?q={keyword}&page={page}
```

Document any environment variable override:

```text
{SOURCE}_SEARCH_URL_TEMPLATE
```

## Listing Extraction

Record selectors needed by `parse_listing`:

```text
empty result:
item        :
title/link  :
summary     :
image       :
external id :
```

Expected `ListingEntry` fields:

```text
url
title
summary
external_id
image_url
```

## Detail Extraction

Record selectors needed by `parse_detail`:

```text
title       :
date        :
body        :
category    :
author      :
image       :
caption     :
```

Expected `ArticleDetail` fields:

```text
title
content
summary
author
published_at
tag
type
language
blocks
```

## Content Blocks

Explain how the source represents:

- Text paragraphs.
- Inline images.
- Captions.
- Related-news widgets/noise to ignore.

## Run Commands

Run all active tickers on this source:

```bash
python -m src.scraper.run --ticket all --source {source} --content-storage-backend minio
```

Run one ticker and cap pages:

```bash
python -m src.scraper.run --ticket ACB --source {source} --max-pages 2 --content-storage-backend minio
```

## Prefect UI Manual Parameters

```json
{
  "tickers": ["ACB"],
  "source_filter": "{source}",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

## Known Risks

- DOM selectors that may change.
- Pagination edge cases.
- Date formats.
- Lazy-loaded images.
- Paywall or bot protection.
- Encoding or mobile/desktop layout differences.

## Validation Checklist

1. `build_search_url` returns a reachable URL.
2. `is_listing_exhausted` detects empty result pages.
3. `parse_listing` returns absolute article URLs.
4. `parse_detail` returns title, content, date, and blocks.
5. CLI local run succeeds with `--max-pages 1`.
6. Prefect manual run succeeds with `source_filter={source}`.
