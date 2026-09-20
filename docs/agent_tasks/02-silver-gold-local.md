# Phase 02 — Silver to Gold Local Serving Pipeline

## Context

This task continues after Phase 01.

Phase 01 already implemented the local vertical slice:

existing sample news data
    ->
MinIO Bronze
    ->
PySpark Bronze-to-Silver transformation
    ->
Delta Lake Silver stored on MinIO

Before doing anything, read:

- AGENTS.md
- docs/data-contracts.md
- artifacts/data-profile.json
- docs/agent-tasks/01-bronze-silver-local.md
- documentation produced by Phase 01

Inspect the actual Phase 01 implementation and test results.

Do NOT assume Phase 01 works just because documentation says it does.

Verify the existing commands and inspect the actual Silver Delta output before
implementing Phase 02.

---

# Goal

Implement the next LOCAL vertical slice:

Silver Delta
    ->
optional enrichment boundary
    ->
Gold RAG documents/chunks
    ->
local embedding provider
    ->
Qdrant

AND

Silver Delta
    ->
Gold analytical datasets
    ->
DuckDB

The purpose of this phase is to make processed news data usable by downstream
retrieval and analytics components.

Do NOT implement RAG generation/LLM answering yet.

---

# Source of Truth

The source of truth for schemas and mappings remains:

- docs/data-contracts.md
- artifacts/data-profile.json

Do not invent source fields.

If Phase 01 output does not match the approved Silver contract:

1. stop the affected implementation,
2. document the mismatch,
3. explain the impact,
4. propose a correction,
5. do not silently modify the canonical contract.

---

# Scope

Implement ONLY:

1. Silver Delta reader
2. enrichment extension point
3. Gold RAG document/chunk generation
4. configurable embedding abstraction
5. one local/default embedding implementation
6. Qdrant local infrastructure
7. Qdrant indexing
8. semantic retrieval test/query
9. Gold analytical datasets
10. DuckDB local serving
11. tests
12. metrics
13. documentation

Do NOT implement yet:

- crawler
- Airflow
- Debezium
- Kafka
- Kubernetes
- cloud deployment
- LLM answer generation
- chatbot
- frontend
- Power BI
- production NER model training
- stock streaming pipeline

---

# 1. Verify Phase 01 First

Before modifying Phase 02 code:

Run or inspect the equivalent of:

make infra-up
make bronze-ingest
make silver-build
make test-pipeline

Verify:

- Bronze objects exist
- Silver Delta table exists
- `_delta_log` exists
- Silver records can be read
- deduplication works
- malformed records are handled
- Phase 01 metrics exist

If Phase 01 is broken, fix only blockers required for Phase 02 and document every
change.

Do not unnecessarily refactor working Phase 01 code.

---

# 2. Silver Reader

Create or reuse a reusable Silver data access layer.

Downstream jobs must not hardcode physical paths throughout business logic.

Conceptually:

SilverArticleRepository
    ->
Delta Lake

The storage location must come from configuration.

Example local configuration:

SILVER_NEWS_URI=s3a://<bucket>/silver/news

Do not hardcode MinIO credentials or endpoints in source code.

---

# 3. Enrichment Boundary

Create an extension point for NLP enrichment.

The thesis contains a separate ViFinNER / Financial NER component, but Phase 02 must
NOT depend on a production NER model being available.

Create an interface conceptually similar to:

ArticleEnricher
    enrich(article) -> enriched_article

Provide a no-op/default implementation.

Future implementations may add:

- entities
- stock_symbols
- financial_events

The pipeline must work when these fields are empty.

Do not fabricate NER output.

Do not implement fake entities merely to make tests pass.

If existing repository code already provides real NER inference, inspect and reuse it
only if integration is clean and does not expand this task significantly.

---

# 4. Gold RAG Document Contract

Read the Gold/RAG contract from docs/data-contracts.md.

Implement the approved contract rather than inventing a new one.

A Gold RAG document/chunk will generally require concepts such as:

- chunk_id
- article_id
- chunk_index
- text
- title
- source
- source_url
- published_at
- entities
- stock_symbols

Only populate fields supported by the contract and Silver data.

Fields not currently available must remain null/empty according to the approved
contract.

---

# 5. Chunking

Implement deterministic article chunking.

Requirements:

- do not destroy the original Silver article
- preserve article_id
- assign deterministic chunk IDs
- preserve useful article metadata
- configurable chunk size
- configurable overlap
- prevent empty chunks
- maintain chunk ordering
- handle short articles
- handle long articles

Prefer paragraph/sentence-aware boundaries when practical.

Do not build an overly complex semantic chunker in this phase.

The implementation should be replaceable later.

Configuration examples:

CHUNK_SIZE=
CHUNK_OVERLAP=

Do not scatter these values as magic constants.

---

# 6. Gold RAG Dataset

Persist generated chunks as a durable Gold dataset BEFORE indexing them into Qdrant.

Qdrant is a serving/index layer, not the source of truth.

Conceptual flow:

Silver Delta
    ->
Chunking
    ->
Gold RAG Dataset
    ->
Embedding
    ->
Qdrant

Store the Gold RAG dataset using the project's existing object-storage conventions.

Prefer Delta or Parquet according to the architecture already established in the repo.

Example logical location:

gold/rag/news_chunks/

Do not make Qdrant the only place where chunks exist.

---

# 7. Embedding Abstraction

Create a provider abstraction conceptually similar to:

EmbeddingProvider
    embed_documents(texts)
    embed_query(text)

Do not tightly couple the pipeline to OpenAI, Gemini, Voyage, or another commercial
provider.

Support configuration such as:

EMBEDDING_PROVIDER=
EMBEDDING_MODEL=

For LOCAL development, provide a provider that can run without paid API credentials
when practical.

A local Hugging Face / sentence-transformer style model is preferred if it integrates
cleanly with the existing repository.

If downloading a model would make automated tests unreliable, provide a deterministic
test embedding provider for tests while keeping the real local provider for actual demo
execution.

Clearly distinguish:

- production/demo embedding provider
- deterministic test provider

Do not present fake/test embeddings as real semantic embeddings.

---

# 8. Qdrant Local Infrastructure

Add Qdrant to Docker Compose only if no equivalent vector database already exists.

Use persistent local volume storage.

Configuration must come from environment variables.

Examples:

QDRANT_URL=
QDRANT_COLLECTION=
EMBEDDING_DIMENSION=

Do not hardcode hostnames inside application logic.

---

# 9. Qdrant Indexing

Implement an idempotent indexing job:

Gold RAG Dataset
    ->
Embedding
    ->
Qdrant

Store vector plus payload metadata.

Useful payload fields should come from the approved contract, for example:

- chunk_id
- article_id
- title
- source
- source_url
- published_at
- stock_symbols
- entities

Use stable point IDs where possible.

Rerunning indexing must not create uncontrolled duplicate points.

Record indexing metrics:

- input chunk count
- embedded chunk count
- indexed chunk count
- failed chunk count
- duration

---

# 10. Semantic Retrieval

Implement a simple retrieval layer or CLI for validating the index.

Conceptual flow:

query
    ->
query embedding
    ->
Qdrant
    ->
top-k chunks

Return:

- score
- chunk text
- article ID
- title
- source
- source URL
- published time when available

Provide a command such as:

make semantic-search QUERY="..."

or an equivalent CLI consistent with the repository.

This is NOT yet a chatbot.

Do not call an LLM.

The goal is only to prove that retrieval works.

---

# 11. Retrieval Smoke Evaluation

Use actual sample articles from the repository.

Create a small set of deterministic/manual smoke queries based on known article
content.

For each query document expected relevant article(s) where possible.

The evaluation does not need to be academically complete yet.

At minimum provide:

- query
- expected article identifier/title
- retrieved top-k results
- whether expected result appears in top-k

Do not fabricate evaluation results.

Persist the evaluation fixture/results in an appropriate tests or artifacts directory.

---

# 12. Gold Analytics Dataset

Create analytical transformations from Silver.

Do not duplicate the RAG chunk representation.

Create useful news-level analytical datasets supported by CURRENT data.

Possible examples, only if supported by data:

- article counts by date
- article counts by source
- article counts by category
- publication timeline
- content-length statistics

If enrichment fields are currently available, optionally include:

- article counts by entity
- article counts by stock symbol

Do not invent analytical dimensions absent from the dataset.

Persist analytical Gold output before serving it through DuckDB.

Example logical location:

gold/analytics/

---

# 13. DuckDB

Use DuckDB as the LOCAL analytical serving engine.

Create a local database or repeatable initialization script.

Suggested location:

data/local/analytics.duckdb

or follow an existing project convention.

Create views/tables only for datasets actually available.

Examples:

vw_news_daily
vw_news_by_source
vw_news_by_category

Names can differ if repository conventions suggest better names.

DuckDB should consume Gold analytical data, not raw Bronze data.

Provide commands such as:

make analytics-build
make analytics-query

The query command should allow the developer to verify actual Gold data.

---

# 14. Metrics

Record metrics for Phase 02.

Gold RAG:

- Silver articles read
- Gold documents/chunks produced
- average chunks per article
- empty/rejected chunks
- processing duration

Embedding/Qdrant:

- chunks embedded
- chunks indexed
- failures
- indexing duration

Analytics:

- input article count
- output aggregation row counts
- processing duration

Use the existing metrics conventions from Phase 01 where practical.

Do not introduce an unrelated metrics architecture if Phase 01 already has one.

---

# 15. Tests

Add unit tests for at least:

- deterministic chunk IDs
- chunk boundaries
- overlap behavior
- short article handling
- metadata propagation
- embedding-provider abstraction
- Qdrant payload construction
- analytical transformations

Add integration tests for:

Silver Delta
    ->
Gold chunks

and where practical:

Gold chunks
    ->
test/local embedding
    ->
Qdrant
    ->
retrieval

and:

Silver
    ->
Gold analytics
    ->
DuckDB

Tests must not require paid APIs.

---

# 16. Makefile / Task Commands

Add or reuse commands equivalent to:

make gold-build

make qdrant-index

make semantic-search QUERY="..."

make analytics-build

make analytics-query

make test-gold

Do not break Phase 01 commands:

make infra-up
make bronze-ingest
make silver-build
make test-pipeline

If repository conventions use another task runner, preserve those conventions.

---

# 17. Documentation

Create or update documentation explaining:

Silver
    ->
Gold RAG
    ->
Qdrant

and:

Silver
    ->
Gold Analytics
    ->
DuckDB

Document:

- storage paths
- configuration
- chunking parameters
- embedding provider
- Qdrant collection
- DuckDB location
- commands to run
- commands to inspect data
- metrics output
- known limitations

Update docs/local-architecture.md if appropriate.

Do not rewrite unrelated documentation.

---

# 18. Local Architecture After This Phase

The expected local architecture should be:

                         MinIO
                           |
                    Bronze News
                           |
                        Spark
                           |
                    Silver Delta
                      /       \
                     /         \
             RAG Gold       Analytics Gold
                |                |
             Chunks            DuckDB
                |
            Embedding
                |
              Qdrant
                |
         Semantic Retrieval

The following still remain outside the current scope:

Airflow
Debezium
Kafka
Kubernetes
LLM Generation
Frontend
Power BI
Cloud deployment

---

# 19. Definition of Done

Phase 02 is DONE only when this can be demonstrated locally:

1. Existing Silver Delta data can be read.

2. Silver articles are converted into deterministic Gold chunks.

3. Gold chunks are persisted outside Qdrant.

4. Chunks can be embedded using the configured local/demo embedding provider.

5. Vectors and payloads are indexed in Qdrant.

6. A semantic query returns relevant repository articles/chunks.

7. Silver articles can be transformed into Gold analytical datasets.

8. DuckDB can query those Gold analytical datasets.

9. Unit/integration tests pass.

10. No paid API credentials are required for automated tests.

11. Phase 01 still works.

---

# 20. Working Rules

Before modifying a file:

- inspect the existing implementation
- reuse existing modules where appropriate
- do not rewrite working code unnecessarily
- preserve repository conventions

Every job should work independently before orchestration is introduced.

Do not place orchestration concerns into processing modules.

Keep local/cloud differences behind configuration.

Maintain idempotency where practical.

Do not silently change data contracts.

Do not implement anything beyond the defined scope.

---

# Final Report

When finished, report:

1. Phase 01 verification result
2. files created
3. files modified
4. architecture implemented
5. Gold data locations
6. Qdrant collection information
7. DuckDB datasets/views
8. commands to run
9. tests executed
10. actual test results
11. retrieval smoke-test results
12. metrics produced
13. known limitations
14. remaining work for Phase 03

STOP after Phase 02.

Do not begin Airflow automatically.
