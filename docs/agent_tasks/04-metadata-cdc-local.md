
# Phase 04 — Metadata-driven Control Plane with PostgreSQL, Debezium, and Kafka

## Context

This task continues after:

Phase 01:
Sample News Data
    ->
MinIO Bronze
    ->
PySpark
    ->
Delta Lake Silver

Phase 02:
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

Phase 03:
Airflow
    ->
Silver DAG
    ->
Gold DAG

All existing processing jobs should already work independently and through Airflow.

Before implementing anything, read:

- AGENTS.md
- docs/data-contracts.md
- artifacts/data-profile.json
- docs/agent_tasks/01-bronze-silver-local.md
- docs/agent_tasks/02-silver-gold-local.md
- docs/agent_tasks/03-airflow-orchestration-local.md
- docs/agent_tasks/CURRENT_STATUS.md if present
- docs/local-architecture.md
- docs/airflow-local.md if present

Inspect the actual repository state.

Do not assume previous phases work merely because documentation says they do.

---

# Goal

Implement a LOCAL metadata-driven control plane:

Control Metadata
      |
      v
 PostgreSQL
      |
      | WAL / Logical Replication
      v
   Debezium
      |
      v
    Kafka
      |
      v
Metadata Change Events
      |
      +----------------------+
      |                      |
      v                      v
 inspection / consumer   future consumers
                         (crawler, scheduler,
                          monitoring, etc.)

The purpose of this phase is to prove that pipeline/source configuration can be
managed as DATA rather than being hardcoded into application source code.

This phase is about CONTROL PLANE events.

It is NOT the stock-market streaming pipeline.

---

# Architectural Distinction

There are now two logical planes.

## Data Plane

Actual financial-news data:

sample data
    ->
Bronze
    ->
Silver
    ->
Gold
    ->
Qdrant / DuckDB

## Control Plane

Configuration and metadata:

PostgreSQL
    ->
Debezium
    ->
Kafka
    ->
metadata consumers

Do not mix the two concepts.

Kafka in this Phase 04 carries CONTROL/METADATA events.

Future stock Kafka will carry MARKET DATA events.

Use clearly separated topic names.

---

# Scope

Implement ONLY:

1. PostgreSQL metadata/control-plane schema
2. local Kafka infrastructure
3. Kafka Connect / Debezium infrastructure
4. PostgreSQL logical replication configuration
5. Debezium PostgreSQL connector
6. metadata event contracts
7. Kafka topic conventions
8. metadata CDC smoke tests
9. metadata event inspection consumer/CLI
10. optional lightweight Airflow metadata lookup
11. tests
12. metrics/observability appropriate for CDC
13. documentation

Do NOT implement yet:

- crawler
- dynamic crawler scheduling
- Kafka-triggered Airflow
- dynamic DAG generation
- stock market streaming
- Flink
- Kubernetes
- cloud Kafka
- schema registry unless already required by the repository
- frontend
- Power BI
- LLM generation
- recommendation system
- complex metadata UI

---

# 1. Verify Previous Phases

Before modifying infrastructure, verify existing functionality.

At minimum inspect or run the repository equivalents of:

make infra-up
make bronze-ingest
make silver-build
make gold-build
make qdrant-index
make analytics-build
make test-pipeline
make test-gold
make airflow-test

Verify:

- MinIO works
- Silver Delta works
- Gold RAG works
- Qdrant works
- Gold Analytics works
- DuckDB works
- Airflow DAGs load
- Phase 03 smoke tests work

Do not break existing functionality.

If an existing phase is broken, fix only blockers required for Phase 04 and document
the changes.

---

# 2. Inspect Existing PostgreSQL Usage

The repository may already use PostgreSQL for:

- Airflow metadata
- application/domain data
- pipeline metrics
- configuration

Inspect first.

Do NOT accidentally use the Airflow metadata database as the domain/control-plane
database.

Prefer clear logical separation.

For example:

PostgreSQL server
    |
    +-- airflow database
    |
    +-- platform/control database

or equivalent schemas/databases according to existing conventions.

Document the choice.

---

# 3. Metadata Schema

Create a minimal and defensible metadata model.

Do not build a giant metadata platform.

At minimum consider the following logical entities.

## news_sources

Represents configured news sources.

Suggested fields:

source_id
source_name
source_type
enabled
base_url
description
config
created_at
updated_at

Notes:

- `config` may use JSONB only for source-specific optional configuration.
- Stable/general fields should remain normal relational columns.
- Do not store secrets in this table.

Crawler implementation remains out of scope.

This table only represents metadata/configuration.

---

## pipeline_configs

Represents configurable processing settings.

Suggested fields:

config_id
pipeline_name
enabled
config_version
parameters
created_at
updated_at

Possible parameters may include only existing pipeline settings such as:

- source
- processing mode
- partition configuration
- chunk configuration references

Do not duplicate every environment variable into the database.

Infrastructure credentials must remain environment/secret configuration.

---

## Optional processing metadata

Reuse existing Phase 01-03 run/metrics tables if present.

Do not create duplicate run tracking systems unnecessarily.

---

# 4. Database Migrations

Use the repository's existing migration mechanism.

If Alembic or another migration tool already exists, reuse it.

Do not manage production-like schema using ad-hoc SQL only if migrations are already
available.

Migrations must be reproducible.

Provide:

create
upgrade
downgrade

where supported by existing tooling.

---

# 5. Seed Metadata

Create deterministic development seed data.

The seed should correspond to the currently available sample source.

Example conceptually:

source_id: current-news-source
enabled: true

Do not invent unsupported source-specific semantics.

The current `docs/data-contracts.md` remains the source of truth regarding actual data.

Provide a command such as:

make metadata-seed

Rerunning seed should be idempotent where practical.

---

# 6. PostgreSQL Logical Replication

Configure PostgreSQL for Debezium.

Requirements may include:

wal_level=logical

and appropriate replication settings supported by the PostgreSQL version.

Do not hardcode undocumented configuration.

Create/configure:

- publication strategy
- replication user
- permissions
- replication slot behavior

Use least privilege practical for local development.

Document clearly:

- which tables are captured
- which database/schema is captured
- replication slot name
- publication name

Do not capture unrelated Airflow metadata tables.

---

# 7. Kafka Infrastructure

Add Kafka to the existing Docker Compose environment if it does not already exist.

Prefer the repository's existing Kafka setup if present.

For local development:

- one broker is sufficient
- persistent volume where practical
- health check
- deterministic advertised listeners
- internal Docker networking
- host access for development tools where needed

Use KRaft or the existing repository convention.

Do not introduce ZooKeeper if the selected Kafka version/setup does not require it.

Do not add a multi-broker cluster merely to simulate scale.

The architecture should remain capable of scaling later.

---

# 8. Kafka Topic Naming

Clearly separate metadata/control topics from future stock data topics.

Use a naming convention such as:

metadata.news_sources
metadata.pipeline_configs

or Debezium-compatible names such as:

platform.metadata.news_sources
platform.metadata.pipeline_configs

The exact naming should follow Debezium and repository conventions.

Future market-data topics must remain distinct, for example:

stock.market.raw
stock.market.validated
stock.market.aggregated

Do not create the stock topics in this phase unless they already exist for another
reason.

Document the naming convention.

---

# 9. Kafka Connect / Debezium

Add Kafka Connect with the Debezium PostgreSQL connector.

Configuration must come from environment/config files where appropriate.

The connector must:

- connect to the control-plane PostgreSQL database
- capture only approved metadata tables
- publish CDC events to Kafka
- survive restart
- resume from offsets/replication slot
- expose connector status

Do not capture:

- Airflow internal tables
- large application data tables
- news article content
- embedding data
- unrelated analytics tables

CDC is only for control metadata in this phase.

---

# 10. Debezium Connector Configuration

Create a reproducible connector configuration.

Important concepts to configure/document:

- connector name
- database hostname
- database port
- database user
- database name
- plugin/decoding mode supported by PostgreSQL/Debezium version
- topic prefix
- schema include list
- table include list
- slot name
- publication name
- snapshot mode
- tombstone behavior where relevant

Do not include passwords in committed source files.

Use environment substitution or local secret configuration.

---

# 11. Snapshot Strategy

Define and document initial snapshot behavior.

The system should support:

initial state:
PostgreSQL already contains metadata
    ->
Debezium starts
    ->
initial metadata is published

then:

INSERT / UPDATE / DELETE
    ->
CDC events

Choose the simplest Debezium-supported strategy appropriate for local development.

Document implications of:

- first startup
- restart
- connector recreation
- deleting the replication slot

Do not create custom snapshot logic unless necessary.

---

# 12. CDC Event Contract

Document the logical event shape.

Create:

docs/metadata-event-contracts.md

Describe events conceptually:

{
  "before": ...,
  "after": ...,
  "operation": "...",
  "source": ...,
  "timestamp": ...
}

Do not hardcode assumptions about exact Debezium envelope fields without checking the
installed Debezium version.

For each captured table document:

- Kafka topic
- Kafka message key
- important payload fields
- INSERT behavior
- UPDATE behavior
- DELETE behavior

---

# 13. Event Keys

CDC events must use stable keys.

For example:

news_sources:
key = source_id

pipeline_configs:
key = config_id

Stable keys are important for:

- compaction
- current-state reconstruction
- idempotent consumers

Do not use random UUIDs at event publication time if the table already has a stable
primary key.

---

# 14. Delete Events

Explicitly test and document DELETE behavior.

Understand whether Debezium produces:

DELETE event
+
optional tombstone

depending on connector configuration.

Do not ignore deletion semantics.

The metadata consumer should not treat a deleted configuration as still active.

---

# 15. Metadata Consumer / Inspector

Implement a simple consumer or CLI for demonstrating the CDC flow.

Its purpose is inspection and verification, not production processing.

Example:

make metadata-consume

It should display useful information such as:

topic
key
operation
entity/table
changed fields
event timestamp

Do not log credentials.

Avoid dumping huge raw Kafka envelopes unless debug mode is enabled.

---

# 16. Optional Current-State Materializer

If useful and simple, implement a lightweight consumer that can reconstruct current
metadata state from CDC events.

For example:

Kafka CDC
    ->
metadata consumer
    ->
local current-state representation

This may be:

- in-memory for demo
- local JSON state
- a separate clearly excluded table/store

Do NOT write captured events back into the same captured table and cause CDC loops.

This feature is optional.

Do not overcomplicate Phase 04 to implement it.

---

# 17. Airflow Integration

Phase 03 already introduced Airflow.

For Phase 04, only introduce a LIGHTWEIGHT metadata integration if it improves the
architecture cleanly.

Preferred pattern:

Airflow DAG starts
    ->
load current approved pipeline/source config
    ->
use lightweight config values
    ->
invoke existing jobs

Airflow may query PostgreSQL metadata directly at DAG runtime.

Do NOT make Airflow consume Kafka CDC events directly in this phase.

Do NOT create Kafka-triggered DAG runs yet.

Do NOT dynamically generate one DAG per source.

Keep DAGs static and understandable.

If existing DAGs already have a clean configuration layer, adapt that layer rather than
rewriting the DAG architecture.

---

# 18. XCom Rules

If Airflow loads metadata, use XCom only for lightweight values.

Allowed examples:

source_id
processing_date
config_version
enabled
small parameter dictionary

Do NOT place:

full table snapshots
articles
DataFrames
embeddings
large JSON documents

into XCom.

---

# 19. Configuration Versioning

Metadata updates should be traceable.

At minimum preserve:

updated_at

and preferably:

config_version

for pipeline configuration.

A pipeline run should be able to report which metadata/config version it used.

Do not build full temporal versioning unless already supported cleanly.

---

# 20. CDC Acceptance Flow

The minimum successful demonstration must be:

STEP 1

PostgreSQL contains:

news_sources:
source A
enabled = true

STEP 2

Debezium captures initial state.

STEP 3

Kafka contains corresponding CDC event.

STEP 4

Run:

UPDATE news_sources
SET enabled = false
WHERE source_id = ...

STEP 5

Debezium emits UPDATE event.

STEP 6

metadata consumer displays:

entity = news_source
operation = update
source_id = ...
enabled: true -> false

STEP 7

Re-enable source.

Another CDC event appears.

This proves the local metadata-driven control plane.

---

# 21. Failure Scenarios

Test/document at least:

## A. Kafka unavailable

Expected:

- connector cannot publish
- failure/status visible
- PostgreSQL transaction itself remains independent

## B. Kafka Connect restart

Expected:

- connector resumes
- previously committed offsets are respected
- no uncontrolled replay beyond expected semantics

## C. PostgreSQL restart

Expected:

- infrastructure recovers
- connector reconnects

## D. Connector misconfiguration

Expected:

- connector status exposes clear failure
- no silent success

## E. Invalid metadata update

Database constraints should reject invalid values where appropriate.

Do not rely solely on CDC consumer validation.

---

# 22. Idempotency and Delivery Semantics

Do not claim exactly-once end-to-end unless actually demonstrated.

Document realistic semantics.

Debezium/Kafka CDC consumers should be designed assuming duplicate/replayed events
may occur.

Consumers should prefer:

stable event keys
+
idempotent state update

where practical.

Clearly distinguish:

database transaction semantics

from:

Kafka delivery semantics

from:

consumer processing semantics.

---

# 23. Kafka Consumer Groups

Use a clear consumer group for metadata inspection or materialization.

Example conceptually:

metadata-inspector

Future consumers may use independent groups.

Do not make every consumer share one group unless they should divide work.

Document this distinction.

---

# 24. Topic Retention / Compaction

Metadata topics often benefit from compaction.

Evaluate whether compacted topics are appropriate for the local metadata configuration.

If enabled, document:

cleanup.policy=compact

or appropriate combined policies.

Do not blindly apply compaction to future market-event topics.

Metadata topics and stock-event topics have different retention needs.

---

# 25. Observability

Provide simple local observability.

At minimum make it possible to inspect:

Kafka:

- topic list
- partitions
- offsets

Kafka Connect:

- connector status

Debezium:

- connector running/failed

PostgreSQL:

- replication slot
- publication

Consumer:

- consumed event count
- latest event timestamp

Do not introduce Prometheus/Grafana yet unless already present and trivial to reuse.

---

# 26. Metrics

Capture lightweight Phase 04 metrics where practical:

- CDC events observed
- inserts
- updates
- deletes
- consumer errors
- connector status
- latest consumed offset
- latest event timestamp

Do not build a new metrics platform if existing Phase 01-03 conventions can be reused.

---

# 27. Testing

Add automated tests.

## Unit Tests

Test:

- metadata model validation
- event parsing
- event key handling
- INSERT parsing
- UPDATE parsing
- DELETE parsing
- duplicate/replayed event handling where relevant

## Integration Tests

Use local containers where practical.

Test:

PostgreSQL INSERT
    ->
Debezium
    ->
Kafka
    ->
consumer receives event

Then:

PostgreSQL UPDATE
    ->
Kafka UPDATE event

Then:

PostgreSQL DELETE
    ->
Kafka DELETE/tombstone behavior

Automated tests must not require cloud services.

---

# 28. CDC Smoke Test

Provide one reproducible command such as:

make metadata-cdc-test

The command should:

1. verify PostgreSQL
2. verify Kafka
3. verify Kafka Connect
4. verify Debezium connector
5. insert/update a test metadata record
6. confirm corresponding Kafka CDC event
7. clean up test metadata safely

Do not destroy real local seed configuration during smoke testing.

Use a dedicated test row or fixture.

---

# 29. Makefile / Task Commands

Add/reuse commands equivalent to:

make metadata-up

make metadata-migrate

make metadata-seed

make debezium-register

make debezium-status

make kafka-topics

make metadata-consume

make metadata-cdc-test

make test-metadata

Do not break previous commands.

Follow repository conventions where naming differs.

---

# 30. Docker Compose

Integrate:

PostgreSQL control database
Kafka
Kafka Connect / Debezium

into the existing local infrastructure cleanly.

Do not create competing duplicate Compose stacks without reason.

Use:

- health checks
- named volumes
- environment configuration
- Docker networking

Pay attention to startup dependencies.

"container started" is not the same as "service ready".

---

# 31. Security

Do not commit:

- database passwords
- Kafka credentials
- API credentials
- cloud secrets

Use local `.env`.

Maintain `.env.example`.

Use a dedicated replication/database user where practical.

Do not use the PostgreSQL superuser as the normal application user unless unavoidable
for a clearly documented local-only bootstrap operation.

---

# 32. Local / Cloud Separation

Keep local-specific infrastructure behind configuration.

LOCAL:

PostgreSQL Docker
Kafka Docker
Kafka Connect / Debezium Docker

Future:

managed PostgreSQL
managed Kafka
cloud Kafka Connect / Debezium equivalent

Application code should not rely on:

localhost
specific Docker container IPs
developer home-directory paths

except through local environment configuration.

---

# 33. Documentation

Create:

docs/metadata-control-plane.md

Document:

## Purpose

Why metadata is separated from news data.

## Architecture

PostgreSQL
    ->
WAL
    ->
Debezium
    ->
Kafka
    ->
Consumers

## Metadata schema

news_sources
pipeline_configs

## CDC topics

topic names and meaning

## Event contract

INSERT / UPDATE / DELETE

## Setup

exact local commands

## Connector

how to register
how to inspect
how to restart

## PostgreSQL

logical replication configuration
publication
replication slot

## Kafka

topic inspection
consumer commands

## Demo

exact commands for:

UPDATE source config
    ->
observe CDC event

## Failure recovery

restart Kafka Connect
connector failure
PostgreSQL restart

## Known limitations

explicitly state future work.

Also update:

docs/local-architecture.md

to show:

CONTROL PLANE:

PostgreSQL -> Debezium -> Kafka

above/beside:

DATA PLANE:

Bronze -> Silver -> Gold

---

# 34. Architecture After Phase 04

Expected LOCAL architecture:

                         CONTROL PLANE

                PostgreSQL Metadata
                        |
                        | WAL
                        v
                     Debezium
                        |
                        v
                      Kafka
                        |
                Metadata CDC Events
                        |
             +----------+----------+
             |                     |
             v                     v
       Inspector/CLI        Future Consumers

                         ORCHESTRATION

                         Airflow
                            |
             +--------------+--------------+
             |                             |
        Silver DAG                     Gold DAG

                         DATA PLANE

Sample News
    |
    v
MinIO Bronze
    |
    v
Spark
    |
    v
Delta Silver
   / 
  /   
 v     v
RAG   Analytics
 |       |
 v       v
Qdrant DuckDB

---

# 35. Important Conceptual Boundary

Do NOT make this:

PostgreSQL metadata
    ->
Debezium
    ->
Kafka
    ->
news article processing data path

unless specifically required.

The news article source of truth remains:

MinIO / Delta layers.

Kafka in Phase 04 communicates metadata/configuration changes.

This distinction must remain explicit in code and documentation.

---

# 36. Definition of Done

Phase 04 is DONE only when:

1. Control-plane PostgreSQL schema exists.
2. Metadata seed data exists.
3. PostgreSQL logical replication is configured.
4. Kafka starts locally.
5. Kafka Connect/Debezium starts locally.
6. Debezium PostgreSQL connector is registered and healthy.
7. Only approved metadata tables are captured.
8. Initial metadata snapshot can reach Kafka.
9. INSERT produces a CDC event.
10. UPDATE produces a CDC event.
11. DELETE behavior is verified.
12. Metadata events use stable keys.
13. A metadata consumer/CLI can inspect events.
14. Connector restart behavior is verified.
15. Phase 01-03 pipelines still work.
16. Kafka metadata topics are clearly distinct from future stock topics.
17. Automated tests pass.
18. A reproducible metadata CDC smoke test passes.
19. Documentation explains exact local setup/demo commands.
20. No stock streaming/Flink/crawler/Kubernetes/cloud implementation was introduced.

---

# 37. Acceptance Scenarios

## Scenario A — Source configuration update

Given:

source.enabled = true

When:

source.enabled becomes false

Then:

PostgreSQL commits update

Debezium captures update

Kafka receives CDC event

consumer observes:

true -> false

---

## Scenario B — Connector restart

Given:

connector has already processed events

When:

Kafka Connect restarts

Then:

connector resumes from stored state/offset

new database changes continue to appear

---

## Scenario C — New source metadata

Given:

a new source metadata row is inserted

Then:

CDC emits INSERT event

No crawler implementation is required.

---

## Scenario D — Source deletion

Given:

a source metadata row is deleted

Then:

DELETE semantics are observable and documented.

---

## Scenario E — Existing pipeline regression

After enabling Kafka/Debezium:

Phase 01-03 standalone and Airflow smoke tests must still pass.

---

# 38. Non-Goals

Do NOT implement:

Kafka -> Airflow event triggering

dynamic DAG generation

crawler implementation

per-source crawler workers

stock market Kafka producers

Flink

real-time stock processing

Kubernetes

cloud migration

schema registry unless genuinely required

monitoring platform

metadata management UI

These belong to later phases.

---

# 39. Final Report

At completion report:

1. Phase 01-03 verification status
2. PostgreSQL metadata schema
3. migrations created
4. seed metadata
5. Kafka version/configuration
6. Kafka Connect/Debezium version
7. Debezium connector configuration
8. publication name
9. replication slot name
10. captured tables
11. Kafka topics created
12. event key strategy
13. snapshot strategy
14. files created
15. files modified
16. Docker Compose changes
17. Makefile/task commands
18. tests executed
19. actual test results
20. CDC smoke-test results
21. restart/recovery results
22. known limitations
23. exact local demo commands
24. recommended work for Phase 05

STOP after Phase 04.

Do NOT automatically begin Phase 05.
