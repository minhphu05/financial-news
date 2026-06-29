# CafeF Scraper Instruction

This document explains how `CafefParser` extracts data from `https://cafef.vn`.

## Source Identity

```text
source name: cafef
base URL   : https://cafef.vn
language   : vi
parser     : src.scraper.cafef.cafef_scraper.CafefParser
```

CafeF is currently the only news source registered in `src/scraper/engine/registry.py`.

## Search URL

Default template:

```text
https://cafef.vn/tim-kiem/trang-{page}.chn?keywords={keyword}
```

Override with environment variable:

```text
CAFEF_SEARCH_URL_TEMPLATE
```

Example for keyword `ACB`, page `1`:

```text
https://cafef.vn/tim-kiem/trang-1.chn?keywords=ACB
```

## Listing Extraction

CafeF listing pages are parsed by `parse_listing`.

Important selectors:

```text
empty result: div.search-content-wrap > span
item        : div.list-main > div.search-content-wrap > div.timeline.list-bytags > div.item
title/link  : h3.titlehidden > a
summary     : div.item-content > p.sapo
image       : div.item-content a.avatar img, div.item-content img
```

Each listing item returns a `ListingEntry`:

```text
url
title
summary
external_id
image_url
```

The source-native article id is extracted from URLs ending in:

```text
-<digits>.chn
```

## Detail Extraction

CafeF detail pages are parsed by `parse_detail`.

Important selectors:

```text
title          : h1.title
standard date  : p.dateandcat > span.pdate
magazine date  : a.link-source-name > span.time-source-detail
standard body  : div.contentdetail > div.detail-cmain.ss > div.detail-content.afcbc-body
fallback body  : table[style='border-collapse: collapse;'] > tbody > tr > td > span
category       : p.dateandcat > a.category-page__name, p.dateandcat a
```

Author selector candidates:

```text
p.author
div.author
span.author
p.pauthor
div.detail-author
p.detail-author
meta[name=author]
```

## Content Blocks

The parser preserves article reading order by emitting `ContentBlock` items:

- `type="text"` for text paragraphs.
- `type="image"` for images with optional captions.

The crawler stores these blocks in the article JSON payload in ADLS or MinIO.

## Run Commands

Run all active tickers on CafeF:

```bash
python -m src.scraper.run --ticket all --source cafef --content-storage-backend minio
```

Run one ticker and cap pages:

```bash
python -m src.scraper.run --ticket ACB --source cafef --max-pages 2 --content-storage-backend minio
```

Run multiple tickers:

```bash
python -m src.scraper.run --ticket ACB,FPT,VCB --source cafef --max-pages 2 --content-storage-backend minio
```

## Prefect UI Manual Parameters

Deployment:

```text
financial-news-standard-scraper/manual
```

All tickers on CafeF:

```json
{
  "tickers": null,
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

Single ticker on CafeF:

```json
{
  "tickers": ["ACB"],
  "source_filter": "cafef",
  "skip_market_data": true,
  "skip_keyword_generation": true,
  "content_storage_backend": "minio"
}
```

## Known Risks

- CafeF DOM selectors may change without warning.
- Some older articles use table-based legacy body layouts; fallback selectors handle text-only extraction.
- Some magazine articles use a different container and date selector.
- Image URLs may be lazy-loaded through `data-original` or `data-src`.

## When Selectors Break

1. Save one listing HTML sample and one detail HTML sample.
2. Update selectors in `CafefParser` only.
3. Keep parser pure: no HTTP, DB, Prefect, ADLS, or MinIO logic.
4. Test with `--max-pages 1` and `--content-storage-backend minio`.
