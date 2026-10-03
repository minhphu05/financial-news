# vnexpress: source contract

Observed 2026-10-03; evidence: `artifacts/source-profiles/vnexpress.json`.

- Host: `vnexpress.net`. One public article returned HTTP 200.
- Fetch: ordinary HTTP, robots checked with the configured research User-Agent.
- Schema: `vnexpress-raw-v1`, source-specific payload inside crawl envelope.
- Observed title: `h1.title-detail`; body: `article.fck_detail`. Missing/empty nodes fail parsing.
- Discovery: `https://vnexpress.net/kinh-doanh`; article URLs must match the verified source pattern.
- Raw HTML, source timestamps, author/category/image metadata remain in Landing.
- Adapter boundary: JSON array containing `link`, `title`, `summary`, `context`, `post date`; no invented ticker fields.
- Explicit ISO publication time is converted to the existing Asia/Ho_Chi_Minh minute-resolution format. Unsupported times remain raw and normalize to null. CafeF timezone is interpreted as Vietnam local time, as in the existing contract.
- Current canonical author/category/crawled_at/image fields remain null; their values are preserved in the Landing sidecar. This does not change the canonical contract.
- Canonical identity remains `(source, canonical_url)` with existing SHA256 identity/hash functions. No cross-source crawler deduplication.
- Parser version `v1`. Layouts not represented by observed nodes are rejected.
- Robots restrictions and any HTTP 403/401/CAPTCHA stop that source; no bypass.

Sample observed: https://vnexpress.net/gdp-quy-iii-tang-9-95-5127865.html

Báo Mới attribution/original URL is retained only if explicitly present in the source DOM/JSON-LD. No publisher-domain guessing or redirect following to crawl the original article.

## Project-owned parsed payload

The following keys are parser output aliases for observed HTML/meta nodes, not official publisher API fields. This source has its own payload shape; the common envelope contains only crawl provenance/policy/schema information.

| Key | Observed Python type |
| --- | --- |
| `title_detail` | `str` |
| `description` | `str` |
| `fck_detail_html` | `str` |
| `pubdate` | `str` |
| `journalist` | `NoneType` |
| `json_ld` | `list` |
| `image_urls` | `list` |
| `category` | `str` |
| `observed_canonical_url` | `str` |
