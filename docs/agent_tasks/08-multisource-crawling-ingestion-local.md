
# Phase 08 — Multi-source News Crawling, Incremental Ingestion, and Existing Pipeline Integration

## 0. Context

This phase starts after the local financial-news platform has been completed through
Phase 07.

Existing system:

Phase 00
Data profiling and data contracts

Phase 01
Sample Data
    ->
MinIO Bronze
    ->
PySpark
    ->
Delta Lake Silver

Phase 02
Silver
    ->
Gold RAG
    ->
Embedding
    ->
Qdrant

AND:

Silver
    ->
Gold Analytics
    ->
DuckDB

Phase 03
Airflow orchestration

Phase 04
Metadata Control Plane

PostgreSQL
    ->
Debezium
    ->
Kafka

Phase 05
Pipeline hardening

- incremental processing
- idempotency
- backfill
- reprocessing
- recovery
- reconciliation
- data quality
- operational metadata

Phase 06
Local Release Candidate / Cloud Readiness

Phase 07
Monitoring & Observability

- Prometheus
- Grafana
- alerts
- service monitoring
- pipeline monitoring
- freshness
- failure/recovery observability

Phase 08 introduces REAL NEWS SOURCES into the existing platform.

This phase is LOCAL ONLY.

Do NOT migrate to cloud.

---

# 1. News Sources

The target news sources for this phase are:

1. CafeF
2. VnExpress
3. Báo Mới
4. Tuổi Trẻ
5. Thanh Niên

Each source may have:

- different HTML
- different URL structures
- different article schemas
- different timestamp formats
- different content structures
- different image representation
- different category representation
- different author representation
- different pagination/discovery behavior

The architecture MUST NOT assume that these five sources share a raw schema.

---

# 2. Primary Goal

Build a multi-source crawling subsystem that can:

discover new articles

    ->

fetch individual articles

    ->

preserve source-specific raw data

    ->

store raw crawl results durably

    ->

track crawl state

    ->

avoid unnecessarily re-crawling old unchanged articles

    ->

map source-specific records through source adapters

    ->

feed the EXISTING Bronze/Silver/Gold pipeline

    ->

allow Airflow orchestration

    ->

expose crawler metrics to the existing Phase 07 observability stack

without rewriting the existing data-processing architecture.

---

# 3. Target Architecture

The target architecture is:

                         NEWS SOURCES

       CafeF   VnExpress   Tuổi Trẻ   Thanh Niên   Báo Mới
         |         |          |           |           |
         v         v          v           v           v

                       SOURCE CRAWLERS

       discovery
           |
       URL frontier
           |
       fetch
           |
       parse
           |
       raw result
           |
           v

                       LANDING STORAGE

                    source-specific RAW

           |
           v

                      SOURCE ADAPTER

         CafeFAdapter
         VnExpressAdapter
         TuoiTreAdapter
         ThanhNienAdapter
         BaoMoiAdapter

           |
           v

                EXISTING INGESTION BOUNDARY

           |
           v

                    MinIO Bronze

           |
           v

                   PySpark Silver

           |
           v

                       Gold
                  /            
                 /              
                v                v
           Gold RAG         Gold Analytics
                |                |
                v                v
             Qdrant            DuckDB

ORCHESTRATION:

Airflow

CONTROL PLANE:

PostgreSQL Metadata
       |
    Debezium
       |
     Kafka

OBSERVABILITY:

Crawler/Pipeline metrics
       |
   Prometheus
       |
     Grafana

---

# 4. Architectural Rule — Crawler Is Not the Data Pipeline

Crawler responsibility:

"How do I obtain data from this website?"

Source Adapter responsibility:

"How do I interpret this source's raw data?"

Core Data Pipeline responsibility:

"How do I process canonical platform data?"

Airflow responsibility:

"When and in what order do these jobs run?"

These responsibilities MUST remain separated.

Do not put:

BeautifulSoup
CSS selectors
Playwright page logic
HTTP crawling logic

inside Airflow DAG files.

Do not put:

source-specific field mapping

inside shared Spark transformation logic unless the current Phase 01 architecture
already defines that as its approved normalization boundary.

---

# 5. Important Rule — Inspect Existing Phase 01 Contract Before Integration

Before deciding where source adapters write data, inspect:

docs/data-contracts.md

artifacts/data-profile.json

Phase 01 implementation

current Bronze representation

current Silver reader

Do NOT silently redefine the current Bronze/Silver contract.

There are two possible patterns.

Pattern A:

Crawler RAW
    ->
Landing
    ->
Source Adapter
    ->
existing Bronze contract
    ->
existing Silver pipeline

Pattern B:

Crawler RAW
    ->
Bronze source-specific envelope
    ->
Source Adapter during Bronze -> Silver
    ->
canonical Silver

Choose whichever matches the ACTUAL approved current architecture.

Do not introduce a second competing Bronze definition.

Document the chosen boundary.

---

# 6. Phase 08 Must Be Implemented Incrementally

Do not start by crawling thousands of articles.

Implement in this order:

Stage 08A
Source reconnaissance and schema profiling

Stage 08B
Single-article parser for all five sources

Stage 08C
Source adapters and raw schema versioning

Stage 08D
URL discovery

Stage 08E
Crawler frontier / incremental state

Stage 08F
Landing storage

Stage 08G
Bronze integration

Stage 08H
Airflow orchestration

Stage 08I
Monitoring

Stage 08J
Real-data end-to-end validation

Complete and test each stage before expanding volume.

---

# 7. Required Reading Before Implementation

Read:

AGENTS.md

docs/data-contracts.md

artifacts/data-profile.json

docs/agent_tasks/CURRENT_STATUS.md

docs/agent_tasks/01-bronze-silver-local.md

docs/agent_tasks/02-silver-gold-local.md

docs/agent_tasks/03-airflow-orchestration-local.md

docs/agent_tasks/04-metadata-cdc-local.md

docs/agent_tasks/05-pipeline-hardening-local.md

docs/agent_tasks/06-local-release-cloud-readiness.md

docs/agent_tasks/07-monitoring-observability-local.md

Also inspect:

README

Makefile

Docker Compose

application configuration

storage abstraction

current Bronze code

current Silver Spark code

Airflow DAGs

metadata database migrations

operational metadata

Prometheus configuration

Grafana dashboards

existing tests

existing data fixtures

recent git history

Do not implement Phase 08 based only on this task document.

The actual repository is the current source of truth.

---

# 8. Verify Phase 01–07 First

Before adding crawlers, verify the existing platform is healthy.

At minimum verify the repository equivalents of:

pipeline health

Phase 01 tests

Phase 02 tests

Airflow DAG tests

metadata CDC test

Phase 05 hardening tests

Phase 06 acceptance

Phase 07 monitoring acceptance

Do not mask an existing broken pipeline by introducing crawler code.

Record the baseline.

---

# 9. Legal / Operational Crawling Boundary

Crawl only publicly accessible content.

Respect:

- robots.txt where applicable
- website terms/policies
- reasonable request rates
- Retry-After responses
- normal HTTP behavior

Do NOT implement:

- CAPTCHA bypass
- paywall bypass
- authentication bypass
- anti-bot circumvention
- IP rotation designed to evade restrictions
- account/session abuse

If a source cannot be crawled normally:

record the exact blocker

and stop work for that source.

Do not implement bypass mechanisms.

---

# 10. HTTP Strategy

Prefer the simplest client that works.

Order of preference:

HTTP client
    ->
HTML parser

Only use browser automation if the required article data is actually rendered
client-side and cannot be obtained reliably through normal requests.

Possible tools:

requests/httpx
BeautifulSoup/lxml

Playwright only when necessary.

Do not automatically use Selenium/Playwright for every source.

Each source should document which mechanism it requires and why.

---

# 11. Source Reconnaissance

Before writing production crawler code, inspect at least one known article from every source.

For each source determine:

- article URL pattern
- canonical URL
- title location
- description/sapo location
- article body structure
- published timestamp
- author
- category
- tags if present
- image URLs
- original publisher metadata if relevant
- pagination behavior
- embedded JSON/JSON-LD availability
- redirects
- HTTP requirements
- whether JavaScript rendering is required

Do not invent CSS selectors.

Inspect the actual source.

---

# 12. Produce Source Profiles

Create:

artifacts/source-profiles/

with files equivalent to:

cafef.json
vnexpress.json
tuoitre.json
thanhnien.json
baomoi.json

Each profile should record:

source

sample URLs inspected

raw field names

field types

nullable behavior

timestamp format

URL representation

content structure

image representation

category representation

author representation

known inconsistencies

discovery method

fetch mechanism

schema version

Do not store full copyrighted article bodies inside profiling artifacts unnecessarily.

---

# 13. Source Contract Documentation

Create:

docs/source-contracts/

with:

cafef.md
vnexpress.md
tuoitre.md
thanhnien.md
baomoi.md

Each document must explain:

- raw source structure
- parsing strategy
- required fields
- optional fields
- known missing fields
- source-specific behavior
- schema version
- canonical mapping

---

# 14. Mapping Matrix

Create:

docs/source-mapping-matrix.md

Conceptual example:

| Canonical    | CafeF | VnExpress | Tuổi Trẻ | Thanh Niên | Báo Mới |
| ------------ | ----- | --------- | ---------- | ----------- | --------- |
| title        | ...   | ...       | ...        | ...         | ...       |
| description  | ...   | ...       | ...        | ...         | ...       |
| content      | ...   | ...       | ...        | ...         | ...       |
| published_at | ...   | ...       | ...        | ...         | ...       |
| source_url   | ...   | ...       | ...        | ...         | ...       |

Populate this ONLY from actual source inspection.

Do not fabricate mappings.

---

# 15. Common Raw Crawl Envelope

Source payloads are allowed to differ.

However, all crawler outputs should use a stable envelope.

Conceptually:

{
  "source": "cafef",
  "schema_version": "cafef-raw-v1",
  "crawl_run_id": "...",
  "crawler_version": "...",
  "requested_url": "...",
  "final_url": "...",
  "crawled_at": "...",
  "http_status": 200,
  "payload": {
    "...": "source-specific raw data"
  }
}

Required envelope metadata should include only information useful for:

- lineage
- replay
- debugging
- deduplication
- parser/version tracking

Do not force every source's payload into one raw schema.

---

# 16. Raw Schema Versioning

Each source must have a raw schema version.

Examples conceptually:

cafef-raw-v1
vnexpress-raw-v1
tuoitre-raw-v1
thanhnien-raw-v1
baomoi-raw-v1

If a source website changes structure:

do NOT overwrite the meaning of v1.

Create:

v2

or another explicit compatible version.

Historical raw records must remain interpretable.

---

# 17. Crawler Version

Record crawler/parser version where practical.

This helps answer:

"Which parser created this record?"

Do not use git commit hashes as the only parser-version strategy unless current project
conventions already do so.

---

# 18. Single Article Fetcher

Implement a source-independent fetch abstraction.

Conceptually:

fetch(url)
    ->
response metadata
    +
raw HTML/content

It should capture:

requested URL

final URL

HTTP status

fetch timestamp

relevant response metadata

raw body

Do not hide redirects.

---

# 19. Raw HTML Preservation

Where legally/operationally appropriate for local research, preserve fetched raw HTML
or equivalent raw response needed for parser replay.

Purpose:

parser bug
    ->
do not re-hit website
    ->
reparse saved response

The parsed JSON and raw response should be traceable to each other.

Do not store unnecessary unrelated assets.

Images themselves do not need to be downloaded unless the project explicitly requires it.

Preserving image URLs is normally sufficient.

---

# 20. Local Landing Storage

Use the existing object-storage abstraction.

Prefer MinIO for local durable landing data.

Conceptual path:

landing/
  news/
    source=cafef/
      crawl_date=YYYY-MM-DD/
        run_id=<crawl_run_id>/
          <url_hash>.html
          <url_hash>.json

Do not hardcode MinIO-specific business logic throughout crawler code.

Keep storage configuration externalized so a future cloud migration can use ADLS.

---

# 21. Source-specific Parser

Each source must have its own parser.

Conceptual structure:

src/
  crawling/
    sources/
      cafef/
        discovery.py
        parser.py
        adapter.py

      vnexpress/
        discovery.py
        parser.py
        adapter.py

      tuoitre/
        discovery.py
        parser.py
        adapter.py

      thanhnien/
        discovery.py
        parser.py
        adapter.py

      baomoi/
        discovery.py
        parser.py
        adapter.py

Actual repository layout should follow existing code conventions.

Do not create a second package architecture unnecessarily.

---

# 22. Parser Responsibility

A parser should transform:

raw response

into:

source-specific structured article data

It should NOT yet implement general Silver cleaning.

Example source-specific operations:

extract title

extract source timestamp

extract source description/sapo

join source-specific paragraph structures

extract original publisher metadata

extract image URLs

Shared normalization belongs downstream where current architecture defines it.

---

# 23. Parser Validation

For every source, define required and optional information based on actual source behavior.

Do not require fields that the source does not consistently provide.

Do not invent values such as:

author = "unknown"

unless the canonical contract explicitly requires that policy.

Missing source fields should remain null/absent according to contract.

---

# 24. Parser Fixtures

Save sanitized/local HTML fixtures for tests where appropriate.

Parser unit tests should NOT require internet access.

Create source-specific fixture sets.

Examples:

normal article

article without author

article with images

article with embedded table

article with unusual timestamp

article with optional sections

Do not rely solely on live web tests.

---

# 25. Source Adapter Layer

Crawler parser and source adapter are separate concepts.

Parser:

raw website
    ->
source-specific record

Adapter:

source-specific record
    ->
existing platform ingestion/canonical boundary

Conceptual interface:

NewsSourceAdapter

validate_raw(record)

map_to_platform(record)

get_source_identity(record)

get_schema_version(record)

Use the existing data-contract terminology.

Do not redesign the canonical contract silently.

---

# 26. Adapter Registry

Provide a registry so source dispatch is centralized.

Conceptually:

cafef
    ->
CafeFAdapter

vnexpress
    ->
VnExpressAdapter

tuoitre
    ->
TuoiTreAdapter

thanhnien
    ->
ThanhNienAdapter

baomoi
    ->
BaoMoiAdapter

Do not scatter:

if source == ...

across the pipeline.

---

# 27. URL Discovery

After single-article parsing works for all five sources, implement discovery.

Discovery should answer:

"What article URLs should be considered for crawling?"

Possible discovery sources:

home page

category/list page

RSS/feed

public sitemap

source-supported listing endpoint

Choose the most stable/public mechanism available for each source.

Do not assume all sources use the same discovery mechanism.

---

# 28. Discovery Result Contract

Discovery should produce normalized candidates.

Conceptually:

source

discovered_url

normalized_url

discovered_at

discovery_context

Do not fetch article bodies during URL-discovery logic unless required.

Separate discovery from article fetching.

---

# 29. URL Normalization

Define source-aware URL normalization.

Possible normalization may include:

fragment removal

known tracking query removal

canonical-link use

redirect resolution

Do not blindly remove query parameters if they are meaningful to that source.

The same logical article should ideally resolve to one stable identity.

---

# 30. Crawl Frontier

Incremental crawling requires persistent state.

Do not rely only on files already present in Landing.

Use PostgreSQL or the existing operational state infrastructure.

Create/reuse a crawler-specific schema/model.

Logical entities may include:

crawler_runs

crawler_urls / crawl_frontier

crawl_attempts if genuinely useful

Do not reuse Airflow internal metadata tables.

---

# 31. crawler_runs

Track one logical crawler run.

Potential information:

crawl_run_id

source

trigger_type

started_at

finished_at

discovered_count

new_count

eligible_recheck_count

fetched_count

success_count

failed_count

status

Do not use these IDs as Prometheus labels.

---

# 32. Crawl Frontier State

For each logical source URL track enough state for incremental crawling.

Potential fields:

source

normalized_url

url_hash

first_seen_at

last_seen_at

last_crawled_at

last_success_at

last_http_status

crawl_status

attempt_count

content_hash

parser_version

schema_version

next_retry_at if required

Use the actual repository naming conventions.

---

# 33. URL Identity

Primary logical identity should usually be based on:

(source, canonical_or_normalized_url)

unless source analysis proves another identity is more reliable.

Do not use crawler-run ID as article identity.

---

# 34. Incremental Crawling

NORMAL crawling must NOT re-crawl the entire known website every schedule.

Normal flow:

discover latest candidate URLs

    ->

normalize

    ->

compare with crawl frontier

    ->

identify new URLs

    ->

identify recent articles eligible for recheck

    ->

fetch only eligible URLs

    ->

update frontier

This is INCREMENTAL CRAWLING.

---

# 35. Recent Article Recheck

News articles can be edited after publication.

A URL seen once must not necessarily be considered permanently immutable.

Implement configurable policy such as:

new URL
    ->
fetch

recent article
    ->
eligible for periodic recheck

old stable article
    ->
normally skip

Configuration might conceptually include:

recent_article_window_hours

recent_article_recheck_minutes

Do not hardcode the exact policy deep inside crawler code.

Choose conservative local defaults and document them.

---

# 36. Content Change Detection

After parsing, compute/reuse a stable content hash based on the approved article content
identity strategy.

Case A:

same URL
same content hash

Result:

no downstream logical content update required

Case B:

same URL
different content hash

Result:

article changed

    ->
existing incremental pipeline should update affected Silver/Gold records

Do not invent another incompatible content-hash algorithm if Phase 01/05 already defines one.

Reuse existing logic where possible.

---

# 37. HTTP Retry Policy

Crawler HTTP retry must be separate from Airflow task retry.

Reasonable retry candidates include:

timeouts

connection failures

HTTP 408

HTTP 429

temporary 5xx

Honor Retry-After where available.

Do not retry every 4xx indefinitely.

Use bounded exponential backoff where appropriate.

---

# 38. Parse Failure Policy

If HTTP fetch succeeds but parsing fails:

preserve raw response

record parse failure

record parser/schema version

do not publish a fake successful article

do not fabricate missing required values

Parser bugs should be replayable against Landing data.

---

# 39. Per-source Failure Isolation

One source failing must not invalidate successful work from other sources.

Example:

CafeF       SUCCESS
VnExpress   SUCCESS
Tuổi Trẻ    FAILED
Thanh Niên  SUCCESS
Báo Mới     SUCCESS

Expected:

successful source outputs remain committed

Tuổi Trẻ failure is recorded

Tuổi Trẻ can retry separately

monitoring reflects degraded source state

Do not roll back unrelated successful source batches.

---

# 40. Báo Mới Special Consideration

Báo Mới is an aggregator-style source and may overlap heavily with original publishers.

Do not deduplicate across sources inside the crawler.

Preserve:

source = baomoi

and where actually available:

original publisher

original URL

Do not invent original publisher metadata.

Cross-source logical deduplication belongs downstream according to the canonical
deduplication policy.

---

# 41. Crawl Backfill

Normal incremental crawl and historical backfill are different.

NORMAL:

latest/current articles

BACKFILL:

explicit historical period/pages

Backfill must be manually requested.

Conceptually:

crawler backfill
    --source cafef
    --from ...
    --to ...

Exact CLI should follow repository conventions.

Backfill should:

record trigger type

respect rate limits

be resumable where practical

not run automatically on normal schedule

---

# 42. Re-crawl / Reprocess

Support explicit controlled recrawl.

Examples:

one URL

one source/date window

records parsed by old parser version

Use cases:

parser bug fixed

source schema version changed

content update investigation

Explicit recrawl must not destroy previous raw evidence.

---

# 43. Integration with Phase 04 Metadata Control Plane

Inspect the existing `news_sources` metadata model.

Reuse it where practical.

Crawler configuration may logically need:

source enabled state

crawler/adapter key

base URL

crawl interval

raw schema version

recent recheck policy

Do NOT automatically add columns if an existing JSON/config field already cleanly supports
these settings.

Use a migration if schema changes are required.

Do not modify canonical ARTICLE contracts for crawler configuration.

---

# 44. Metadata CDC Behavior

When crawler/source configuration changes:

PostgreSQL metadata
    ->
Debezium
    ->
Kafka

should continue to expose the metadata CDC event.

However:

Phase 08 crawler does NOT need to consume Kafka events to operate.

Preferred current pattern:

Airflow/crawler runtime
    ->
read current metadata configuration from PostgreSQL

Kafka CDC remains the control-plane event stream.

Kafka-triggered crawler execution is future work.

---

# 45. Do NOT Use Kafka as Article Queue in Phase 08

Do not implement:

Crawler
    ->
Kafka article topic
    ->
Silver

The current news architecture is incremental batch.

Kafka already serves the metadata/control plane.

Only introduce an article queue if a future scaling requirement demonstrates that it is
needed.

---

# 46. Integration with Existing Bronze

Crawler integration must feed the existing Phase 01 Bronze path.

Do not create:

crawler_bronze_v2

parallel to:

existing_bronze

unless an explicit approved migration requires it.

The expected result is:

crawler output
    ->
Landing
    ->
adapter
    ->
existing Bronze ingestion
    ->
existing Silver

---

# 47. Preserve Existing Sample-data Ingestion

Existing sample-data ingestion should remain available.

Why:

tests

deterministic demo

offline development

regression testing

Crawler ingestion should be an ADDITIONAL input mode.

Conceptually:

InputProvider
    |
    +-- SampleFileInput
    |
    +-- CrawlerLandingInput

both converge at the existing ingestion boundary.

Do not break Phase 01 tests.

---

# 48. Airflow Architecture

Integrate crawler orchestration with the existing Phase 03 Airflow setup.

Do not rewrite Silver and Gold DAGs.

Introduce a crawler/ingestion DAG only if it fits the current DAG structure.

Suggested logical name:

news_crawl_ingestion

But inspect repository naming conventions before choosing the final DAG ID.

---

# 49. Development Schedule

During crawler development:

schedule = None

Run manually.

Do NOT immediately activate recurring web requests while parsers are unstable.

Only enable scheduling after:

all five single-article parsers pass

discovery works

frontier works

Landing works

rate limits are configured

failure isolation works

monitoring works

---

# 50. Recommended Local Production-like Schedule

After stabilization, use a conservative configurable incremental schedule.

A reasonable starting local/demo cadence is approximately every 15 minutes.

This is NOT a thesis SLA.

Make schedule configurable.

Recommended properties:

catchup = false

max active runs limited

no overlapping uncontrolled crawl runs

source-level concurrency bounded

Do not hardcode aggressive crawling intervals.

---

# 51. One DAG vs Five DAGs

Prefer avoiding five duplicated crawler DAGs.

Preferred approach:

one crawler orchestration DAG

with source-level TaskGroups or supported dynamic task mapping

for:

cafef

vnexpress

tuoitre

thanhnien

baomoi

if this works cleanly with the installed Airflow version.

Do NOT dynamically generate arbitrary DAG files from database rows.

If existing Airflow architecture makes separate DAGs clearly safer, document why.

---

# 52. Do NOT Create One Airflow Task per Article

Airflow manages jobs/batches, not every URL.

Bad:

500 URLs
    ->
500 permanent Airflow tasks

Preferred:

source crawl batch

or bounded URL chunks inside the crawler application.

The crawler engine should handle article-level fetching/retry state.

---

# 53. Airflow Logical Flow

Conceptually:

load crawler configuration
        |
        v
discover enabled sources
        |
        +------------------------------+
        |        |        |       |    |
        v        v        v       v    v
      CafeF     VNE      TT      TN   BM
        |        |        |       |    |
      crawl    crawl    crawl   crawl crawl
        |        |        |       |    |
      landing  landing  landing landing landing
        |        |        |       |    |
      validate validate validate ...
        |        |        |       |    |
      ingest Bronze
        |
        v
publish Bronze update
        |
        v
existing Silver pipeline
        |
        v
existing Gold pipeline

Actual dependency mechanism must reuse the Phase 03 design where possible.

---

# 54. Silver Triggering

After Bronze ingestion succeeds, connect to the existing Silver DAG using the existing
approved Airflow dependency mechanism.

Possible mechanisms depending on current Phase 03 implementation:

Airflow Assets/Datasets

or:

TriggerDagRunOperator

or another already-established mechanism.

Do not create polling loops.

Avoid triggering the same logical partition concurrently from multiple source tasks.

---

# 55. Partitioning

Use actual existing Bronze partition semantics.

Crawler integration should provide appropriate:

source

ingestion date

crawl date/run identity

where supported by the current contract.

Do not redesign partition layout without verifying Phase 01/05 assumptions.

---

# 56. Integration with Phase 05 Incremental Processing

Crawler changes should feed naturally into existing incremental processing.

Case:

new article

Expected:

new Bronze input
    ->
new Silver article
    ->
new Gold chunks
    ->
Qdrant upsert
    ->
analytics refresh as required

Case:

known URL, unchanged content

Expected:

no duplicate logical Silver article

no duplicate Qdrant points

Case:

known URL, changed content

Expected:

Silver update
    ->
affected Gold regenerated
    ->
Qdrant stable upsert

Reuse Phase 05 mechanisms.

Do not implement a second incremental system downstream.

---

# 57. Crawler Metrics

Integrate with Phase 07 observability.

At minimum expose/derive metrics equivalent to:

crawler_runs_total

crawler_runs_failed_total

crawler_articles_discovered

crawler_articles_new

crawler_articles_rechecked

crawler_articles_fetched

crawler_articles_success

crawler_articles_failed

crawler_parse_failures

crawler_http_failures

crawler_duration_seconds

crawler_last_success_timestamp

landing_last_write_timestamp

Use repository naming conventions.

---

# 58. Prometheus Cardinality

Allowed low-cardinality labels:

source

status

failure_type

Possibly HTTP status class if bounded.

Do NOT use:

URL

article_id

crawl_run_id

full exception

as Prometheus labels.

---

# 59. Metrics Persistence Strategy

Crawler jobs are batch jobs.

Do not make every crawler process rely on a long-lived embedded Prometheus server.

Prefer:

crawler operational metadata
    ->
existing Phase 07 metrics exporter
    ->
Prometheus

if this matches current monitoring architecture.

Reuse existing observability patterns.

---

# 60. Grafana Crawler Dashboard

Add a dashboard:

Financial News — Crawling

or the repository's naming convention.

It should show where data exists:

crawl success by source

last successful crawl

articles discovered

new articles

fetch success/failure

parse failures

crawl duration

Landing freshness

source health

Do not fabricate metrics unavailable from implementation.

---

# 61. Freshness

Define crawler freshness.

Example concept:

| current time                     |
| -------------------------------- |
| last successful crawl for source |

Also consider end-to-end freshness later:

crawl time
    ->
Silver/Gold availability

Do not confuse this with the existing Silver/Gold freshness metric.

---

# 62. Alerts

Integrate meaningful crawler alerts.

Potential rules:

CrawlerSourceDown

CrawlerNoSuccessfulRunRecently

CrawlerParseFailures

CrawlerHTTPFailureSpike

CrawlerLandingStale

Thresholds must be configurable and based on observed local behavior.

Do not pretend local thresholds are production SLAs.

---

# 63. Rate Limiting

Implement per-source rate limiting.

Do not rely solely on Airflow concurrency.

Crawler engine should support configurable:

request delay

max parallel requests

retry/backoff

Use conservative defaults.

Different sources may require different limits.

---

# 64. Airflow Pool / Concurrency

Where supported and useful, use a crawler Airflow pool or equivalent concurrency control.

Purpose:

prevent five sources from creating an uncontrolled request burst.

Do not create complex distributed rate-limit infrastructure.

---

# 65. Tests — Core Crawler

Add unit tests for:

URL normalization

raw envelope

retry classification

frontier eligibility

content-change detection

schema version dispatch

adapter registry

---

# 66. Tests — Parser

For EACH source test:

known article fixture

title extraction

content extraction

timestamp extraction

URL extraction

optional-field behavior

malformed/missing elements

schema version

Tests should normally run offline using fixtures.

---

# 67. Tests — Discovery

For EACH source:

test listing/discovery fixture

extract candidate URLs

normalize URLs

remove obvious duplicate URLs

do not fetch article bodies during discovery test unless design requires it

---

# 68. Live Smoke Tests

Provide optional explicit live tests.

Example concept:

make crawler-smoke SOURCE=cafef URL=...

or repository equivalent.

Live tests:

must not run automatically in normal CI

must crawl only a small number of public pages

must use conservative requests

must clearly report skipped/blocked sources

---

# 69. Single-article Acceptance

Before enabling discovery for a source, prove:

one known article URL

    ->

successful fetch

    ->

raw HTML persisted

    ->

parsed source record persisted

    ->

adapter produces valid platform input

No source proceeds to high-volume discovery until this passes.

---

# 70. Incremental Crawl Test

Use isolated fixtures/state.

Scenario:

first discovery:

10 URLs

Expected:

10 new URLs eligible

Second identical discovery:

same 10 URLs

Expected:

0 new URLs

Add one URL:

Expected:

1 new URL

This proves frontier behavior.

---

# 71. Recent Recheck Test

Scenario:

known recent article

first content hash = A

recheck content hash = A

Expected:

no logical update

Then:

content hash = B

Expected:

changed article state

downstream update eligibility

---

# 72. Failure Isolation Test

Simulate:

CafeF succeeds

VnExpress succeeds

Tuổi Trẻ parser fails

Thanh Niên succeeds

Báo Mới succeeds

Expected:

four successful sources remain committed

Tuổi Trẻ reports failure independently

overall orchestration reports partial/degraded state accurately

---

# 73. Landing Integration Test

Test:

fixture/raw article
    ->
crawler envelope
    ->
MinIO Landing

Verify:

correct path

metadata

raw content

parsed JSON

idempotent object naming where required

---

# 74. Bronze Integration Test

Test:

Landing
    ->
Source Adapter
    ->
existing Bronze

Then verify:

existing Phase 01 Silver build can consume it

without special manual repair.

---

# 75. Two-source Proof Before Five-source Full Run

Before attempting all five live sources end-to-end:

prove at least two structurally different sources can flow through:

crawler
    ->
Landing
    ->
adapter
    ->
Bronze
    ->
Silver
    ->
Gold

without changing shared Silver transformation logic.

CafeF + VnExpress are good candidates if technically accessible.

This demonstrates extensibility.

---

# 76. Five-source Acceptance

After the architecture is proven, run one controlled article/batch for every accessible
source.

Expected:

CafeF
VnExpress
Tuổi Trẻ
Thanh Niên
Báo Mới

all produce source-specific raw data

and valid downstream platform records where source access permits.

If a site blocks normal crawling, mark it BLOCKED with evidence.

Do not fake successful crawling.

---

# 77. Real Data End-to-End Acceptance

For controlled small real-data input:

News Website
    ->
Crawler
    ->
Landing
    ->
Bronze
    ->
Silver
    ->
Gold RAG
    ->
Qdrant

AND:

Silver
    ->
Gold Analytics
    ->
DuckDB

Verify:

Airflow orchestration

Phase 05 idempotency

Phase 07 monitoring

Do not immediately perform high-volume crawling.

---

# 78. Makefile / Task Commands

Add/reuse commands conceptually equivalent to:

make crawler-profile

make crawler-test

make crawler-test-source SOURCE=cafef

make crawler-fetch SOURCE=cafef URL=...

make crawler-discover SOURCE=cafef

make crawler-run SOURCE=cafef

make crawler-run-all

make crawler-status

make crawler-backfill SOURCE=... FROM=... TO=...

make crawler-health

make test-crawler-incremental

make test-crawler-integration

make phase8-acceptance

Use existing repository naming conventions.

Do not break existing Phase 01–07 commands.

---

# 79. CLI Design

Provide a reusable CLI.

Conceptual actions:

profile

fetch-one

discover

crawl

backfill

recrawl

status

The CLI should work outside Airflow.

This is essential for debugging.

Airflow should call these stable application entrypoints.

---

# 80. Configuration

Extend `.env.example` only where necessary.

Possible crawler settings:

CRAWLER_USER_AGENT

CRAWLER_REQUEST_TIMEOUT

CRAWLER_DEFAULT_REQUEST_DELAY

CRAWLER_DEFAULT_MAX_CONCURRENCY

LANDING_NEWS_URI

Source-specific settings should prefer metadata/config rather than dozens of hardcoded
environment variables.

Do not commit credentials or sensitive cookies.

---

# 81. User-Agent

Use a clear configurable crawler User-Agent appropriate for legitimate research/local
development.

Do not impersonate unrelated browser identities solely to evade source restrictions.

---

# 82. Security

Do not store:

authentication secrets

session tokens

personal account cookies

inside Landing records.

Do not log secrets.

Crawler should not require personal login for the intended public-news workflow.

---

# 83. Logs

Use structured logging consistent with existing Phase 05/07 patterns.

Useful fields:

crawl_run_id

source

stage

status

counts

duration

Do not log complete article bodies.

Do not use URL as Prometheus label, though URL can appear in bounded/debug logs where appropriate.

---

# 84. Data Lineage

A crawled article should be traceable conceptually:

source URL

    ->

crawl run

    ->

Landing object

    ->

ingestion record

    ->

article_id

    ->

Silver

    ->

Gold chunk IDs

    ->

Qdrant points

Preserve necessary identifiers across boundaries.

---

# 85. Do Not Fabricate NER / Enrichment

Crawler integration must not fake:

entities

stock symbols

financial events

sentiment

If enrichment is unavailable, keep the existing optional enrichment behavior.

---

# 86. Do Not Change RAG Logic Unnecessarily

Phase 08 input should naturally feed the existing Phase 02 Gold RAG logic.

Do not rewrite chunking/embedding/Qdrant simply because data now comes from a crawler.

Only modify downstream code if genuine multi-source bugs are discovered.

---

# 87. Do Not Change Analytics Logic Unnecessarily

Gold Analytics should continue to operate on canonical Silver data.

The addition of source diversity may make `source` analytics more useful.

Do not add unsupported analytics fields.

---

# 88. Cross-source Deduplication

Different sources may publish the same/similar content.

Phase 08 should first ensure:

same-source URL/content idempotency.

Cross-source exact duplicate handling should reuse existing Silver deduplication if possible.

Near-duplicate semantic detection is optional/future work.

Do not build complex similarity deduplication unless current data demonstrates it is necessary.

---

# 89. Báo Mới Attribution

When Báo Mới exposes original-source attribution in a reliable field, preserve it.

Potential canonical/metadata concepts:

aggregation_source

original_publisher

original_url

ONLY if supported by the actual raw data and approved contract.

Do not silently add canonical fields.

If a canonical change is required:

report it for engineering approval.

---

# 90. Documentation

Create:

docs/crawling-architecture.md

docs/crawler-operations.md

docs/source-mapping-matrix.md

docs/source-contracts/cafef.md

docs/source-contracts/vnexpress.md

docs/source-contracts/tuoitre.md

docs/source-contracts/thanhnien.md

docs/source-contracts/baomoi.md

Update:

docs/local-architecture.md

docs/monitoring-observability.md

docs/agent_tasks/CURRENT_STATUS.md

as appropriate.

---

# 91. Crawling Architecture Documentation

Explain:

crawler core

source parser

source adapter

Landing

frontier

incremental crawling

recheck

backfill

Airflow

Bronze integration

monitoring

failure isolation

schema versioning

---

# 92. Operations Documentation

Document exact commands for:

fetch one article

discover URLs

run one source

run all sources

inspect crawler state

inspect Landing

run backfill

recrawl URL

check metrics

recover failed source

trigger through Airflow

---

# 93. Update Demo Guide

If:

docs/demo-guide-vi.md

exists, update it with an optional crawler demo section after Phase 08 succeeds.

Do not rewrite working Phase 01–07 demo instructions unnecessarily.

---

# 94. Demo Scenario — One Article

Preferred first live demo:

one known CafeF URL

    ->
fetch

    ->
raw HTML

    ->
parsed JSON

    ->
Landing

    ->
Bronze

    ->
Silver

    ->
Gold

Show lineage.

---

# 95. Demo Scenario — Multi-source

Run a small controlled crawl from multiple sources.

Show:

different raw schemas

    ↓

different source adapters

    ↓

same canonical downstream representation

This is the central Phase 08 architecture demonstration.

---

# 96. Demo Scenario — Incremental

Run discovery.

Example observed result:

discovered = N
new = X

Run again without source change.

Expected:

new approximately 0 for identical discovered set

Do not rely on exact numbers from a live changing news site for automated assertions.

Use fixtures for deterministic test.

---

# 97. Demo Scenario — Article Update

Use fixture/replay to demonstrate:

same URL

old content hash

    ->

changed content

    ->

new hash

    ->

downstream update eligibility

Do not rely on waiting for a real publisher edit during thesis demo.

---

# 98. Demo Scenario — Source Failure

Disable or safely simulate failure of one source.

Expected:

other sources continue

Grafana reports failed/degraded source

crawler status records failure

No unrelated downstream data is lost.

---

# 99. Definition of Done

Phase 08 is complete only when:

1. Phase 01–07 regressions still pass.
2. All five target sources have documented source profiles.
3. All five sources have versioned raw schema documentation.
4. Single-article parsing works for each source that is normally publicly accessible.
5. Any source blocked from normal access is documented honestly.
6. Source-specific parsers have offline fixture tests.
7. Discovery exists for each accessible source.
8. URL normalization is tested.
9. Persistent crawl frontier exists.
10. Normal crawl is incremental.
11. Recent-article recheck exists/configured.
12. Same unchanged URL does not cause uncontrolled downstream duplicates.
13. Changed article content is detectable.
14. Raw Landing data is durable locally.
15. Source adapters map into the existing platform contract.
16. Existing Bronze/Silver pipeline consumes crawler-derived input.
17. At least two structurally different sources pass full Bronze -> Gold integration.
18. Small controlled runs for all accessible sources succeed.
19. Airflow can orchestrate crawler batches.
20. No one-Airflow-task-per-article design exists.
21. One source failure does not discard other sources' success.
22. Crawler state and run metrics are recorded.
23. Prometheus exposes crawler operational metrics.
24. Grafana includes crawler observability.
25. Relevant crawler alerts exist.
26. Backfill is explicit/manual.
27. Crawler CLI works independently of Airflow.
28. Phase 08 end-to-end acceptance passes.
29. Documentation is reproducible.
30. No cloud resources were introduced.

---

# 100. Explicit Non-goals

Do NOT implement in Phase 08:

Azure migration

ADLS migration

Kubernetes

Terraform

Helm

distributed crawler cluster

Kafka article queue

CAPTCHA bypass

paywall bypass

proxy rotation for evasion

LLM chatbot

stock streaming

Flink

new NER training

complex cross-source semantic dedup

frontend crawler management UI

---

# 101. Recommended Implementation Order

Implement in this exact broad order:

1. verify Phase 01–07
2. inspect current data contracts and Bronze boundary
3. profile all five news sources
4. build common crawler core
5. implement CafeF single article parser
6. implement VnExpress single article parser
7. implement Tuổi Trẻ single article parser
8. implement Thanh Niên single article parser
9. implement Báo Mới single article parser
10. create fixture tests for all parsers
11. implement source adapters
12. implement Landing storage
13. implement discovery for each source
14. implement crawl frontier
15. implement incremental policy
16. implement recent-article recheck
17. integrate Landing -> existing Bronze
18. prove two-source full pipeline
19. integrate all accessible sources
20. add Airflow orchestration
21. integrate crawler metrics into Phase 07 monitoring
22. add failure/recovery tests
23. run full Phase 08 acceptance
24. update documentation/status

Do not optimize crawl volume before correctness is proven.

---

# 102. Final Report

At completion report:

1. branch name
2. Phase 01–07 verification status
3. all sources investigated
4. source access status
5. fetch mechanism per source
6. raw schema version per source
7. source profile files
8. parser implementation per source
9. discovery implementation per source
10. source adapters
11. canonical mapping status
12. Landing layout
13. crawl frontier schema
14. incremental-crawl strategy
15. recent-article recheck policy
16. URL normalization strategy
17. content-change detection
18. backfill behavior
19. retry behavior
20. rate-limit behavior
21. Airflow DAG structure
22. scheduling configuration
23. Bronze integration mechanism
24. Phase 05 incremental integration
25. crawler metrics
26. Grafana dashboard
27. alerts
28. files created
29. files modified
30. tests executed
31. parser test results for each source
32. live smoke results for each source
33. two-source end-to-end result
34. five-source controlled test result
35. Phase 01–07 regression results
36. known source-specific limitations
37. exact commands for running locally
38. exact commands for crawler demo
39. git status
40. recommended commit messages

Update:

docs/agent_tasks/CURRENT_STATUS.md

Do NOT start cloud migration.

Do NOT begin the next phase automatically.
