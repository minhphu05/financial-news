# Multisource mapping into the existing pipeline

Phase 08 uses source-specific raw schemas. `docs/data-contracts.md` remains authoritative and unchanged.

| Source | Parser body (observed) | Raw schema | Publication evidence | Strategy |
| --- | --- | --- | --- | --- |
| CafeF | `div.afcbc-body` | cafef-raw-v1 | `article:published_time` | public HTTP |
| VnExpress | `article.fck_detail` | vnexpress-raw-v1 | `meta[name=pubdate]` | public HTTP |
| Tuổi Trẻ | `div.afcbc-body` | tuoitre-raw-v1 | `article:published_time` | public HTTP |
| Thanh Niên | `div.afcbc-body` | thanhnien-raw-v1 | `article:published_time` | public HTTP |
| Báo Mới | `div.content-body` | baomoi-raw-v1 | `article:published_time` | public HTTP |

Evidence: five profiles in `artifacts/source-profiles/`, five source contracts in `docs/source-contracts/`. One article and one economic listing per source were retrieved with ordinary HTTP on 2026-10-03. This is a point-in-time observation, not assurance of future access or all layout variants.

## Boundary

An adapter produces a JSON array accepted by `src/news_pipeline/source_schema.py`:

| Existing input | Adapter mapping | Silver result |
| --- | --- | --- |
| link | source-host URL validated by the existing canonical URL function | source_url, canonical_url, article_id |
| title | observed source heading | normalized title |
| summary | observed description/sapo, otherwise empty | description |
| context | observed article-body HTML | cleaned content, existing content_hash |
| post date | ISO timestamp converted to approved Vietnam local minute format; unsupported value retained | published_at or null, published_at_raw |

No ticker keyword/search-association fields are fabricated. Author, category, images, source native timestamps, crawl timestamps and Báo Mới attribution remain in the immutable Landing envelope. Current canonical normalization sets those optional metadata columns to null. Consumers needing those columns in canonical Silver require a separately approved mapping/contract revision; this phase does not silently populate them.

The adapter conversion is explicit and lossy at the canonical minute precision: original source timestamp including seconds and offset remains in Landing. Missing timestamps are not replaced with crawl time. CafeF unqualified publication timestamps use the contract's Vietnam timezone.

## Identity and change detection

Identity is still source plus source-host canonical URL. Content-change detection uses `normalize_text(body, body=True)` and SHA256 as in existing Silver; layout-only HTML edits do not trigger downstream updates. Title/summary/publication changes are also tracked as metadata changes and submitted through the existing pipeline. No cross-source crawler deduplication; Báo Mới keeps its own URL/source identity. Landing retains an explicit publisher/original URL only when present in the observed document.
