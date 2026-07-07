# Thanh Nien Scraper Instruction

## Source Identity

```text
source name: thanhnien
base URL   : https://thanhnien.vn
search URL : https://thanhnien.vn/tim-kiem.htm?keywords={keyword}
parser     : src.scraper.thanhnien.thanhnien_scraper.ThanhnienParser
```

Thanh Nien search is JavaScript-rendered and loads more results while the page
scrolls. The source therefore uses Playwright for listing pages and the normal
HTTP client for detail pages.

## Listing Behavior

- Build the search URL by URL-encoding the keyword into
  `https://thanhnien.vn/tim-kiem.htm?keywords={keyword}`.
- Read the expected result count from `div.total span.value`.
- Scroll until the parsed unique listing count reaches the total, or until the
  page stops yielding new items for several rounds.
- Parse each `div.box-category-item` into a `ListingEntry`.

Relevant listing selectors:

```text
item        : div.box-category-item
title/link  : a.box-category-link-title
summary     : a.box-category-sapo
image       : img.box-category-avatar
total count : div.total span.value
source id   : div.box-category-item[data-id], fallback URL suffix -{id}.htm
```

## Detail Behavior

The parser stores the same content document fields as CafeF through the shared
crawler: title, summary, author, tag, type/category, language, published_at,
content, blocks, cover_image, ticker, matched_keyword, URL, and URL hash.

Missing detail fields are returned as `None`, so they become `null` in the JSON
content document.

## Duplicate Policy

The shared crawler checks duplicates before detail scraping by source-native id
or URL hash. Existing articles are skipped. The run stops once
`SCRAPER_CONSECUTIVE_KNOWN_THRESHOLD` consecutive known articles are seen; the
default is 100.

## Manual Commands

```bash
python -m src.scraper.run --ticket ACB --source thanhnien --content-storage-backend minio
python -m src.scraper.run --ticket ACB --source cafef,thanhnien --content-storage-backend minio
```

Playwright must be installed with Chromium available:

```bash
playwright install chromium
```