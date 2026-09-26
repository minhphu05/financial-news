
# Phase 03 — Local Airflow Orchestration

## Context

This task continues after:

Phase 01:

existing sample news data
    ->
MinIO Bronze
    ->
PySpark
    ->
Delta Lake Silver

Phase 02:

Silver Delta
    ->
Gold RAG chunks
    ->
Embedding
    ->
Qdrant

AND:

Silver Delta
    ->
Gold Analytics
    ->
DuckDB

Before implementing anything, read:

- AGENTS.md
- docs/data-contracts.md
- artifacts/data-profile.json
- docs/agent_tasks/01-bronze-silver-local.md
- docs/agent_tasks/02-silver-gold-local.md
- all architecture and implementation documentation produced by Phases 01 and 02

Inspect the actual repository and verify that Phase 01 and Phase 02 work.

Do not assume documentation is correct without checking the implementation.

---

# Goal

Add Apache Airflow as the LOCAL orchestration layer for the already-working
news data pipeline.

The target orchestration is:

                          Airflow
                             |
               +-------------+-------------+
               |                           |
               v                           v
          Silver DAG                   Gold DAG

Source/Sample Data                   Silver Delta
       |                                  |
       v                                  +------------------+
Bronze Ingestion                          |                  |
       |                                  v                  v
       v                             Gold RAG           Gold Analytics
Spark Bronze->Silver                     |                  |
       |                                  v                  v
       v                              Embedding           DuckDB
Silver Delta                             |
                                         v
                                      Qdrant

Airflow must orchestrate existing jobs.

Airflow must NOT become the location where transformation/business logic is implemented.

---

# Core Architectural Rule

Every important pipeline step must continue to work independently outside Airflow.

For example, commands equivalent to these must still work:

make bronze-ingest
make silver-build
make gold-build
make qdrant-index
make analytics-build

Airflow should invoke/reuse those existing jobs or their underlying application entrypoints.

Do NOT copy transformation logic into DAG files.

Bad:

@task
def clean_articles():
    # hundreds of lines of Spark/business logic

Good:

Airflow task
    ->
invoke existing bronze-to-silver job
    ->
observe result/status

DAG files should primarily contain:

- scheduling
- dependencies
- parameters
- retries
- orchestration
- lightweight validation
- observability hooks

---

# Scope

Implement ONLY:

1. local Airflow infrastructure
2. Airflow configuration
3. Silver DAG
4. Gold DAG
5. dependencies between tasks
6. dependencies between Silver and Gold processing
7. retries / failure behavior
8. pipeline parameters
9. lightweight quality gates
10. task-level metrics/status
11. DAG validation tests
12. local end-to-end Airflow smoke test
13. documentation

Do NOT implement yet:

- crawler
- Debezium
- Kafka
- metadata CDC
- Kubernetes
- cloud Airflow deployment
- LLM answer generation
- chatbot
- frontend
- Power BI
- stock streaming
- production monitoring stack
- complex backfill framework
- alert integrations such as Slack/email
- dynamic multi-source crawler orchestration

---

# 1. Verify Phase 01 and Phase 02 First

Before adding Airflow:

verify the existing commands or equivalent repository entrypoints.

At minimum verify:

make infra-up

make bronze-ingest

make silver-build

make gold-build

make qdrant-index

make analytics-build

make test-pipeline

make test-gold

Names may differ if the repository has established better conventions.

Confirm:

- MinIO is accessible
- Bronze data exists
- Silver Delta exists
- `_delta_log` exists
- Silver can be read successfully
- Gold RAG chunks exist
- Qdrant contains indexed chunks
- semantic retrieval works
- Gold analytics exists
- DuckDB can query Gold analytics

If a previous phase is broken:

- fix only blockers required for orchestration
- document the changes
- avoid unnecessary refactoring

---

# 2. Inspect Existing Airflow Code First

Before creating new Airflow files, inspect whether the repository already contains:

- Airflow Docker configuration
- DAGs
- plugins
- connections
- variables
- Airflow requirements
- operators
- custom hooks
- existing PostgreSQL metadata DB configuration

Classify existing Airflow code as:

- REUSE
- REFACTOR
- REMOVE/UNUSED
- NEW

Do not create a second parallel Airflow architecture if a usable one already exists.

---

# 3. Local Airflow Infrastructure

Add Airflow to the existing local Docker Compose environment if it is not already available.

Use the repository's existing Airflow version if one is already defined.

Otherwise choose a stable version compatible with the current Python/dependency stack.

The minimum required local Airflow components should be appropriate for the selected Airflow version.

Typical components may include:

- scheduler
- webserver / API server depending on Airflow version
- initialization/migration service
- metadata database

Do not add Celery/Redis unless the current architecture genuinely requires it.

For local development, prefer the simplest executor compatible with reliable execution.

Reuse PostgreSQL infrastructure where appropriate, but keep Airflow metadata logically separated from application/domain data.

For example:

airflow database/schema

must not be mixed conceptually with:

news/domain metadata database.

Do not hardcode credentials.

Use environment variables.

---

# 4. Airflow Configuration

Configuration should support local development without embedding environment-specific values in DAG code.

Examples of configuration:

AIRFLOW_HOME
AIRFLOW__CORE__EXECUTOR

MINIO_ENDPOINT
MINIO_ACCESS_KEY
MINIO_SECRET_KEY

BRONZE_NEWS_URI
SILVER_NEWS_URI
GOLD_RAG_URI
GOLD_ANALYTICS_URI

QDRANT_URL
QDRANT_COLLECTION

DUCKDB_PATH

EMBEDDING_PROVIDER
EMBEDDING_MODEL

Reuse existing project configuration where possible.

Do not create duplicate competing configuration systems.

---

# 5. DAG Design

Implement two logical DAGs consistent with the target architecture.

## DAG A — Silver Pipeline

Suggested DAG ID:

news_silver_pipeline

Conceptual flow:

start
  |
  v
validate_source_data
  |
  v
bronze_ingest
  |
  v
bronze_quality_check
  |
  v
spark_bronze_to_silver
  |
  v
silver_quality_check
  |
  v
publish_silver_success

The exact tasks should reuse actual Phase 01 entrypoints.

Do not create tasks merely to make the DAG look larger.

Every task should have a clear responsibility.

---

## DAG B — Gold Pipeline

Suggested DAG ID:

news_gold_pipeline

Conceptual flow:

validate_silver
      |
      v
build_gold_rag_chunks
      |
      +----------------------+
      |                      |
      v                      v
embed_and_index_qdrant   build_gold_analytics
      |                      |
      v                      v
rag_quality_check        analytics_quality_check
      |                      |
      +----------+-----------+
                 |
                 v
          publish_gold_success

Use the actual Phase 02 jobs.

Do not call an LLM.

This phase only orchestrates retrieval/indexing and analytical serving.

---

# 6. Silver -> Gold Dependency

Gold must not process incomplete/invalid Silver output.

Choose the simplest clean mechanism supported by the installed Airflow version.

Preferred choices in order:

1. Airflow Dataset/Asset scheduling if the existing Airflow version supports it cleanly
2. explicit TriggerDagRunOperator
3. another standard Airflow dependency mechanism already used in the repository

Avoid:

- custom polling loops
- sleeping inside tasks
- manually checking DAG database tables
- tightly coupling Gold implementation to Silver DAG internals

Document the chosen mechanism and why.

The logical behavior must be:

Silver successful
    ->
Silver quality checks pass
    ->
Gold may run

Silver failed
    ->
Gold must not automatically run on invalid output

Both DAGs should remain manually triggerable for debugging where practical.

---

# 7. Job Invocation Strategy

Inspect how Phase 01 and Phase 02 jobs currently execute.

Choose operators based on the actual implementation.

Possible examples:

- BashOperator
- PythonOperator for lightweight wrappers only
- DockerOperator
- SparkSubmitOperator
- custom operator/hook only if justified

Do not introduce a custom operator without need.

For Spark:

prefer invoking the existing real Spark job rather than embedding Spark transformation code inside the DAG.

For example:

Airflow
   ->
SparkSubmitOperator / existing command
   ->
bronze_to_silver.py

For normal application jobs:

Airflow
   ->
existing CLI/entrypoint

Airflow task code should remain thin.

---

# 8. Parameters

Make DAGs usable for both scheduled and manual runs.

Support reasonable parameters based on the existing data contracts and partitioning strategy.

Potential parameters:

- source
- processing_date
- force_rebuild
- embedding_provider

Only implement parameters actually useful for the existing pipeline.

Do not invent multi-source behavior if only one source is currently supported.

Use existing partition conventions from Phase 01/02.

Do not redesign the contracts.

---

# 9. Idempotency Expectations

Airflow retries must not create uncontrolled duplicates.

Verify existing jobs behave safely when rerun.

At minimum check:

Bronze:
same input rerun
    ->
no uncontrolled duplicate objects/records

Silver:
same partition rerun
    ->
consistent Delta result

Gold RAG:
same Silver input rerun
    ->
stable chunk IDs

Qdrant:
same indexing job rerun
    ->
upsert / stable points
    ->
no duplicate explosion

Analytics:
same run
    ->
consistent Gold/DuckDB output

Phase 03 does not need to solve every production-grade idempotency issue.

But document any limitations discovered.

---

# 10. Retry Policy

Configure sensible retries.

Do not use one retry policy blindly for every task.

Examples:

storage/network operation:

- retry may be appropriate

deterministic schema validation failure:

- retry probably does not help

Spark processing:

- limited retry may be appropriate

Qdrant indexing:

- limited retry may be appropriate if idempotent

Document retry behavior.

Avoid infinite retries.

---

# 11. Quality Gates

Use the existing Phase 01/02 metrics instead of recreating validation logic.

Silver quality gate should inspect metrics such as:

- input count
- output count
- invalid count
- duplicate count

Gold RAG quality gate may inspect:

- Silver article count
- generated chunk count
- empty/rejected chunks
- indexed chunk count
- failed indexing count

Analytics quality gate may inspect:

- input article count
- output row counts
- DuckDB availability

Do not hardcode arbitrary academic thresholds unless justified.

At minimum, clearly fail for impossible states such as:

- expected Silver output missing
- Gold output missing
- all input records rejected unexpectedly
- Qdrant indexing completely failed
- analytics output unreadable

---

# 12. XCom Rules

Do not pass datasets through XCom.

Do not pass:

- full articles
- DataFrames
- embeddings
- large JSON payloads

XCom may contain only lightweight metadata, for example:

- run_id
- output URI
- record counts
- metrics path
- success metadata

Actual datasets belong in storage.

---

# 13. Pipeline Run Identity

Introduce or reuse a lightweight run identifier.

A pipeline execution should be traceable across:

Bronze
    ->
Silver
    ->
Gold

At minimum preserve:

- Airflow DAG run ID
- logical processing date
- source when available

If existing Phase 01/02 metrics support run IDs, integrate with them.

Do not build a new complex metadata platform in Phase 03.

That belongs to later phases.

---

# 14. Scheduling

Choose conservative local schedules.

Do not accidentally enable aggressive schedules during development.

A reasonable local default may be:

schedule=None

for manual testing,

or a simple controlled development schedule if already established.

Catchup should generally be disabled unless the existing partition/backfill design explicitly supports it.

Document:

- how to manually trigger Silver
- how Gold gets triggered
- how to rerun a failed DAG

---

# 15. Failure Behavior

Document expected behavior for at least:

Case A:
Bronze ingestion fails

Expected:
Silver processing does not run.

Case B:
Spark fails

Expected:
Silver quality check and downstream Gold do not run.

Case C:
Silver quality gate fails

Expected:
Gold is not automatically triggered.

Case D:
Gold chunking fails

Expected:
Qdrant indexing does not run.

Case E:
Qdrant indexing fails

Expected:
analytics branch may still complete if branches are independent.

Case F:
DuckDB analytics fails

Expected:
RAG branch may still complete if branches are independent.

The DAG dependency graph should express this correctly.

---

# 16. Parallelism

Where dependencies allow, run independent Gold work in parallel.

Conceptually:

                build_gold_rag_chunks
                        |
                  embedding/index

Silver
  |
  +--------------------------------+
                                   |
                         build_gold_analytics
                                   |
                                DuckDB

However:

do not parallelize steps that genuinely depend on one another.

The goal is a correct DAG, not maximum visual complexity.

---

# 17. Logging

Every task should produce useful logs.

Logs should make it possible to identify:

- processing source/partition
- input/output location
- run ID
- counts
- processing duration
- error reason

Do not log:

- credentials
- secrets
- full embeddings
- massive article content

Reuse existing structured logging if available.

---

# 18. Metrics

Phase 03 should expose existing processing metrics in orchestration context.

Do not rebuild the Phase 01/02 metrics system.

At minimum, a DAG run should make it possible to inspect:

Silver:

- input records
- output records
- invalid
- duplicates
- duration

Gold RAG:

- articles
- chunks
- indexed
- failed
- duration

Analytics:

- input rows
- output rows
- duration

The metrics may live in existing metric artifacts/storage.

Airflow should reference/surface them.

---

# 19. Airflow UI

The local environment must allow developers to inspect:

- DAG list
- DAG graph
- task state
- task logs
- DAG run history

Document the local Airflow URL.

Credentials must come from configuration/dev bootstrap and not be embedded as secrets in source code.

---

# 20. DAG Tests

Add automated tests.

At minimum:

## DAG import test

All DAG files load without import errors.

## DAG structure test

Verify important task IDs exist.

Verify critical dependencies.

Example:

bronze_ingest
    ->
spark_bronze_to_silver

and:

silver_quality_check
    ->
Silver completion / Gold trigger

## Configuration test

Missing required configuration should fail clearly.

## No-heavy-logic check

Keep processing modules separate from DAG definitions.

Do not duplicate transformation code in DAG tests.

---

# 21. Airflow Integration Smoke Test

Provide a reproducible local smoke test.

Preferred options depending on installed version:

airflow dags test <silver_dag> <date></date>

and:

airflow dags test <gold_dag> <date></date>

or an equivalent supported testing mechanism.

A complete smoke path must prove:

existing sample data
    ->
Airflow Silver DAG
    ->
Bronze
    ->
Spark
    ->
Silver

then:

Silver success
    ->
Airflow Gold DAG
    ->
Gold chunks
    ->
Qdrant

and:

Silver
    ->
Gold analytics
    ->
DuckDB

No paid external API should be required for automated smoke tests.

Use the existing deterministic/test embedding provider if necessary.

---

# 22. Makefile / Task Commands

Add or reuse commands equivalent to:

make airflow-up

make airflow-down

make airflow-logs

make airflow-dags

make airflow-test

make airflow-test-silver

make airflow-test-gold

make pipeline-run

Do not break existing commands:

make infra-up
make bronze-ingest
make silver-build
make gold-build
make qdrant-index
make analytics-build
make test-pipeline
make test-gold

`make pipeline-run` should provide a convenient local end-to-end orchestration path where practical.

Follow repository naming conventions if they differ.

---

# 23. Docker Compose

Integrate Airflow into the existing Compose setup.

Do not create unrelated duplicate Compose stacks unless necessary.

Ensure service dependencies are sane.

Typical dependency relationships may include:

Airflow
    ->
PostgreSQL metadata DB

pipeline tasks
    ->
MinIO
    ->
Qdrant
    ->
Spark where necessary

Use health checks where practical.

Do not rely only on container startup order when actual service health matters.

---

# 24. Environment Separation

Do not bake local-only assumptions into DAGs.

The same DAG structure should be capable of later running against cloud infrastructure by changing configuration.

For example:

LOCAL:

MinIO
Docker Compose
local Qdrant

Future:

ADLS
Kubernetes
managed/vector infrastructure

DAGs should reference logical configuration:

BRONZE_NEWS_URI
SILVER_NEWS_URI
GOLD_RAG_URI

rather than host-specific paths.

---

# 25. Documentation

Create/update documentation for Airflow.

Suggested file:

docs/airflow-local.md

Include:

## Architecture

Silver DAG

Gold DAG

relationship between them

## Setup

exact commands

## UI

URL and local login/bootstrap instructions

## Manual run

how to trigger DAGs

## DAG test

how to run locally without waiting for scheduler

## Logs

how to inspect task logs

## Failure recovery

how to retry / clear a task

## Configuration

required environment variables

## Data locations

Bronze
Silver
Gold RAG
Gold Analytics

## Known limitations

what remains intentionally outside Phase 03

Also update:

docs/local-architecture.md

to show Airflow as orchestration above the already-existing jobs.

---

# 26. Architecture After Phase 03

Expected LOCAL architecture:

                         AIRFLOW
                            |
             +--------------+--------------+
             |                             |
        SILVER DAG                     GOLD DAG
             |                             |
             v                             v
       Sample Data                    Silver Delta
             |                          /       
             v                         /         
       MinIO Bronze             Gold RAG       Gold Analytics
             |                      |                |
             v                      v                v
           Spark                Embedding          DuckDB
             |                      |
             v                      v
       Delta Silver               Qdrant

Airflow is the CONTROL/ORCHESTRATION layer.

It is not the transformation/storage layer.

---

# 27. Definition of Done

Phase 03 is DONE only if all of the following are true:

1. Airflow starts locally.
2. Airflow UI can display the pipeline DAGs.
3. Silver DAG is valid and importable.
4. Gold DAG is valid and importable.
5. DAG files contain orchestration logic rather than duplicated transformation logic.
6. Silver DAG can successfully orchestrate:

sample data
    ->
Bronze
    ->
Spark
    ->
Silver

7. Gold DAG can successfully orchestrate:

Silver
    ->
Gold RAG
    ->
Embedding
    ->
Qdrant

and:

Silver
    ->
Gold Analytics
    ->
DuckDB

8. Gold does not automatically consume failed/invalid Silver output.
9. Existing Phase 01/02 standalone commands still work.
10. Retries do not create uncontrolled duplicates.
11. DAG import/structure tests pass.
12. Local DAG smoke tests pass.
13. Documentation contains exact setup/run/debug commands.
14. No Kafka, Debezium, Kubernetes, crawler, frontend, or LLM generation has been introduced.

---

# 28. Acceptance Scenarios

## Scenario A — Normal end-to-end execution

Given valid sample news data

When Silver pipeline runs

Then:

- Bronze exists
- Silver exists
- Silver quality gate passes

And Gold executes

Then:

- Gold RAG exists
- Qdrant index is updated
- Gold Analytics exists
- DuckDB is updated

---

## Scenario B — Silver processing failure

Given Spark processing fails

Then:

- Silver DAG fails
- Gold must not automatically process invalid Silver data

---

## Scenario C — Gold RAG branch failure

Given Qdrant indexing fails

Then:

- RAG branch reports failure
- failure is visible in Airflow
- analytics branch behavior follows the DAG dependency design
- no silent success is reported

---

## Scenario D — Analytics branch failure

Given DuckDB serving fails

Then:

- analytics branch reports failure
- RAG branch must not be unnecessarily corrupted if already independently successful

---

## Scenario E — Rerun

Given a successful previous run

When the same logical partition/run is executed again

Then:

- no uncontrolled duplicate Silver records
- no duplicate explosion in Qdrant
- analytics result remains consistent

---

# 29. Important Non-Goals

Do NOT implement these merely because Airflow makes them possible:

- crawler scheduling
- dynamic DAG generation per news website
- Kafka-triggered DAGs
- Debezium
- metadata-driven source configuration
- KubernetesExecutor
- CeleryExecutor unless genuinely necessary
- complex backfills
- external alerting systems
- RAG chatbot
- LLM generation

Those belong to future phases.

---

# 30. Final Report

At the end, report:

1. verification results for Phase 01
2. verification results for Phase 02
3. Airflow version/configuration
4. executor selected and why
5. DAGs created
6. DAG graph/task dependencies
7. Silver -> Gold trigger/dependency mechanism
8. files created
9. files modified
10. Docker Compose changes
11. Makefile/task commands added
12. tests executed
13. actual test results
14. smoke-test result
15. retry/idempotency findings
16. known limitations
17. exact commands for me to reproduce the pipeline
18. remaining work for Phase 04

STOP after Phase 03.

Do NOT automatically begin Phase 04.
