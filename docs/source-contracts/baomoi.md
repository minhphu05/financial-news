# baomoi: source contract

Observed 2026-10-03; evidence: `artifacts/source-profiles/baomoi.json`.

- Host: `baomoi.com`. One public article returned HTTP 200.
- Fetch: ordinary HTTP, robots checked with the configured research User-Agent.
- Schema: `baomoi-raw-v1`, source-specific payload inside crawl envelope.
- Observed title: `article.content-main h1`; body: `div.content-body`. Missing/empty nodes fail parsing.
- Discovery: `https://baomoi.com/kinh-te.epi`; article URLs must match the verified source pattern.
- Raw HTML, source timestamps, author/category/image metadata remain in Landing.
- Adapter boundary: JSON array containing `link`, `title`, `summary`, `context`, `post date`; no invented ticker fields.
- Explicit ISO publication time is converted to the existing Asia/Ho_Chi_Minh minute-resolution format. Unsupported times remain raw and normalize to null. CafeF timezone is interpreted as Vietnam local time, as in the existing contract.
- Current canonical author/category/crawled_at/image fields remain null; their values are preserved in the Landing sidecar. This does not change the canonical contract.
- Canonical identity remains `(source, canonical_url)` with existing SHA256 identity/hash functions. No cross-source crawler deduplication.
- Parser version `v1`. Layouts not represented by observed nodes are rejected.
- Robots restrictions and any HTTP 403/401/CAPTCHA stop that source; no bypass.

Sample observed: https://baomoi.com/tang-truong-gdp-cai-thien-qua-tung-quy-9-thang-tang-9-01-c56187189.epi

Báo Mới attribution/original URL is retained only if explicitly present in the source DOM/JSON-LD. No publisher-domain guessing or redirect following to crawl the original article.

## Project-owned parsed payload

The following keys are parser output aliases for observed HTML/meta nodes, not official publisher API fields. This source has its own payload shape; the common envelope contains only crawl provenance/policy/schema information.

| Key | Observed Python type |
| --- | --- |
| `headline` | `str` |
| `sapo` | `str` |
| `content_html` | `str` |
| `aggregation_time` | `str` |
| `author` | `NoneType` |
| `json_ld` | `list` |
| `image_urls` | `list` |
| `category` | `str` |
| `observed_canonical_url` | `str` |
| `original_publisher` | `str` |
| `original_url` | `str` |
