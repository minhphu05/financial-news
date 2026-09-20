
# Project Context

This repository is part of a graduation thesis about a Vietnamese financial
information platform.

## My responsibility

I am responsible for the financial-news data processing pipeline shown in the
architecture:

Existing news data
→ Bronze
→ Silver
→ Gold
→ Qdrant / DuckDB

Crawler implementation is OUT OF SCOPE for now.

## Target architecture

Production target:

- Azure Data Lake Gen2
- Delta Lake
- Airflow
- Spark
- PostgreSQL
- Debezium
- Kafka
- Qdrant
- DuckDB
- Docker/Kubernetes

## Current development environment

We are currently developing locally.

Use:

- ADLS → MinIO
- Kubernetes → Docker Compose
- PostgreSQL → Docker PostgreSQL
- Qdrant → Docker Qdrant
- Spark → local/standalone Docker Spark
- DuckDB → local file

Delta Lake should run on top of MinIO using the S3-compatible API.

Cloud-specific code must be isolated behind configuration/adapters.

## Current data

Sample news data already exists under ./data.

Do not build or redesign crawlers unless explicitly requested.

## Processing layers

### Bronze

Raw immutable news data.

### Silver

Spark performs:

- schema validation
- text/HTML cleaning
- Unicode normalization
- whitespace normalization
- timestamp normalization
- metadata normalization
- URL normalization
- content hashing
- deduplication
- quality checks

Silver is stored in Delta Lake.

### Enrichment

NER is developed separately in the thesis.

The pipeline must provide an enrichment interface so ViFinNER can later enrich:

- entities
- stock symbols
- financial events

Do not block the pipeline on NER model availability.

### Gold RAG

Silver/enriched articles:

- chunking
- metadata propagation
- embedding
- Qdrant indexing

Qdrant is a derived serving index, not source of truth.

### Gold Analytics

Create analytical datasets consumable by DuckDB and later Power BI.

## Airflow

Do not place heavy transformation logic inside DAG files.

Every job must first work independently from CLI/tests.

Airflow is only responsible for:

- scheduling
- orchestration
- dependency
- retries
- observability

## Development priority

P0:
data → Bronze → Spark → Silver

P1:
Silver → chunks → Qdrant
Silver → analytics → DuckDB

P2:
Airflow orchestration

P3:
metadata CDC using PostgreSQL + Debezium + Kafka

P4:
cloud migration and Kubernetes

## Important constraints

- Inspect existing implementation before changing code.
- Do not rewrite working modules unnecessarily.
- Prefer incremental refactoring.
- Preserve backward compatibility where reasonable.
- Keep cloud/local environment differences in configuration.
- All pipeline jobs must be idempotent where practical.
- Add tests for every core transformation.
