# tuoitre: source contract

Observed 2026-10-03; evidence: `artifacts/source-profiles/tuoitre.json`.

- Host: `tuoitre.vn`. One public article returned HTTP 200.
- Fetch: ordinary HTTP, robots checked with the configured research User-Agent.
- Schema: `tuoitre-raw-v1`, source-specific payload inside crawl envelope.
- Observed title: `h1.detail-title`; body: `div.afcbc-body`. Missing/empty nodes fail parsing.
- Discovery: `https://tuoitre.vn/kinh-doanh.htm`; article URLs must match the verified source pattern.
- Raw HTML, source timestamps, author/category/image metadata remain in Landing.
- Adapter boundary: JSON array containing `link`, `title`, `summary`, `context`, `post date`; no invented ticker fields.
- Explicit ISO publication time is converted to the existing Asia/Ho_Chi_Minh minute-resolution format. Unsupported times remain raw and normalize to null. CafeF timezone is interpreted as Vietnam local time, as in the existing contract.
- Current canonical author/category/crawled_at/image fields remain null; their values are preserved in the Landing sidecar. This does not change the canonical contract.
- Canonical identity remains `(source, canonical_url)` with existing SHA256 identity/hash functions. No cross-source crawler deduplication.
- Parser version `v1`. Layouts not represented by observed nodes are rejected.
- Robots restrictions and any HTTP 403/401/CAPTCHA stop that source; no bypass.

Sample observed: https://tuoitre.vn/phuc-loi-cho-nguoi-gia-10026100114085356.htm

Báo Mới attribution/original URL is retained only if explicitly present in the source DOM/JSON-LD. No publisher-domain guessing or redirect following to crawl the original article.

## Project-owned parsed payload

The following keys are parser output aliases for observed HTML/meta nodes, not official publisher API fields. This source has its own payload shape; the common envelope contains only crawl provenance/policy/schema information.

| Key | Observed Python type |
| --- | --- |
| `detail_title` | `str` |
| `sapo` | `str` |
| `article_body_html` | `str` |
| `published_time` | `str` |
| `author` | `NoneType` |
| `json_ld` | `list` |
| `image_urls` | `list` |
| `category` | `NoneType` |
| `observed_canonical_url` | `str` |
