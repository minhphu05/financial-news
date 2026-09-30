
# Phase 05 — Pipeline Hardening, Incremental Processing, Recovery, and Observability

## Context

This phase continues after:

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

AND

Silver
    ->
Gold Analytics
    ->
DuckDB

Phase 03
Airflow orchestration

Phase 04
Metadata-driven control plane

PostgreSQL Metadata
    ->
Debezium
    ->
Kafka
    ->
Metadata CDC Events

The system currently has a working local architecture.

The goal of Phase 05 is NOT to add another major technology.

The goal is to make the existing pipeline:

- incremental
- idempotent
- restartable
- backfillable
- observable
- measurable
- recoverable
- easier to demonstrate and defend academically

Before implementing anything, read:

- AGENTS.md
- docs/data-contracts.md
- artifacts/data-profile.json
- docs/agent_tasks/01-bronze-silver-local.md
- docs/agent_tasks/02-silver-gold-local.md
- docs/agent_tasks/03-airflow-orchestration-local.md
- docs/agent_tasks/04-metadata-cdc-local.md
- docs/agent_tasks/CURRENT_STATUS.md if present
- docs/local-architecture.md
- docs/airflow-local.md if present
- docs/metadata-control-plane.md if present

Inspect the actual repository and git history.

Do not assume previous phases work merely because documentation says so.

---

# Goal

Harden the existing NEWS DATA PIPELINE.

Current logical data flow:

Sample / Incoming News Data
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
Gold RAG   Gold Analytics
    |            |
    v            v
Qdrant         DuckDB

Orchestrated by:

Airflow

Controlled/configured by:

PostgreSQL
    ->
Debezium
    ->
Kafka metadata events

After this phase, the pipeline should support:

NEW DATA
    ->
process only what is required
    ->
publish valid output
    ->
record run metadata

while also supporting:

BACKFILL
REPROCESS
RETRY
RECOVERY
RECONCILIATION

without creating uncontrolled duplicates.

---

# Important Architectural Principle

Do not confuse:

INCREMENTAL PROCESSING

with:

STREAM PROCESSING.

This news pipeline remains primarily batch/incremental batch.

Kafka/Flink stock-market streaming is a separate future pipeline.

Phase 05 does NOT introduce Flink.

---

# Scope

Implement ONLY:

1. processing/run identity
2. incremental Bronze processing
3. incremental Silver processing
4. incremental Gold processing
5. checkpoint/watermark state where justified
6. idempotency verification
7. backfill support
8. targeted reprocessing
9. failure recovery
10. reconciliation
11. data-quality gates
12. operational run metadata
13. structured metrics
14. structured logging improvements
15. pipeline health/status CLI
16. Airflow integration for incremental/backfill execution
17. tests
18. local performance baseline
19. documentation

Do NOT implement:

- crawler
- new source adapters
- Kubernetes
- cloud migration
- Flink
- stock market streaming
- frontend
- chatbot
- LLM answer generation
- Power BI
- Prometheus/Grafana unless already present and trivial to reuse
- complex enterprise data catalog
- full lineage platform
- recommendation system
- new ML models

---

# 1. Verify Phases 01–04 First

Before modifying code, verify the actual system.

At minimum inspect/run the repository equivalents of:

make infra-up
make bronze-ingest
make silver-build
make gold-build
make qdrant-index
make analytics-build
make test-pipeline
make test-gold
make airflow-test
make metadata-cdc-test

Verify:

- Bronze exists
- Silver Delta exists
- Gold datasets exist
- Qdrant retrieval works
- DuckDB analytics works
- Airflow DAGs load/run
- PostgreSQL metadata works
- Debezium connector works
- Kafka metadata CDC works

Record baseline status.

Do not unnecessarily refactor previous phases.

---

# 2. Inspect Current Processing Semantics

Before implementing incremental processing, determine exactly how the current pipeline behaves.

Answer:

- Does Bronze append or overwrite?
- How are Bronze objects named?
- How are partitions organized?
- How is article_id generated?
- How is content_hash generated?
- How does Silver currently deduplicate?
- Does Silver overwrite entire datasets?
- Does Delta MERGE currently exist?
- How are Gold chunks generated?
- Are chunk IDs stable?
- Does Qdrant use stable point IDs?
- Does Gold Analytics rebuild entirely?
- Does DuckDB rebuild or incrementally refresh?
- What state currently determines "already processed"?

Document findings before changing behavior.

Do not implement incremental logic based on guesses.

---

# 3. Processing Identity

Every logical processing run must have an identifiable run ID.

Reuse Airflow DAG run ID where appropriate, but application jobs should also be usable outside Airflow.

Define a logical structure such as:

run_id
pipeline_name
source
processing_date / partition
started_at
finished_at
status
trigger_type

Trigger types may include:

NORMAL
BACKFILL
REPROCESS
MANUAL

Do not tightly couple processing modules to Airflow internals.

---

# 4. Operational Metadata

Reuse the PostgreSQL infrastructure established in Phase 04 if appropriate.

Do NOT use Airflow internal metadata tables for domain pipeline state.

Create or reuse a separate operational schema/table structure.

Consider:

pipeline_runs

Fields may include:

run_id
pipeline_name
trigger_type
source
partition_start
partition_end
started_at
finished_at
status
error_message
airflow_dag_id
airflow_run_id
created_at

And optionally:

pipeline_stage_runs

Fields may include:

stage_run_id
run_id
stage_name
input_uri
output_uri
input_count
output_count
invalid_count
duplicate_count
started_at
finished_at
duration_ms
status
error_message

Keep this lightweight.

Do not build an enterprise metadata catalog.

IMPORTANT:

These operational tables should NOT automatically become part of Phase 04 Debezium
CDC unless there is an explicit architectural reason.

Do not flood metadata Kafka topics with pipeline-run metrics.

---

# 5. Incremental Boundary

Define the unit of incremental processing based on the actual Bronze/Silver layout.

Prefer existing partitions such as:

source
+
ingestion_date

or another existing contract-supported partition.

Do not invent event-level streaming semantics for news.

Example:

bronze/news/
    source=cafef/
        ingestion_date=2026-09-29/

Then incremental processing may logically operate on:

(source, ingestion_date)

Document the chosen incremental boundary.

---

# 6. Bronze Incremental Behavior

Bronze remains the immutable/raw layer.

Rerunning ingestion with identical source records must not create uncontrolled duplicate
logical records.

Use existing:

raw_record_hash
content hash
stable identifiers

where appropriate.

Do not destroy raw historical data merely to achieve deduplication.

Distinguish:

physical raw copies

from:

logical duplicate records.

Document Bronze semantics clearly.

---

# 7. Silver Incremental Processing

Change or extend Silver processing so that a normal run does not require unnecessarily
rebuilding the entire dataset.

Use Delta Lake capabilities where appropriate.

Possible mechanisms include:

partition-aware processing

and/or:

Delta MERGE

based on stable identifiers.

Do not blindly MERGE without first verifying the current article identity strategy.

The expected behavior is conceptually:

New Bronze Partition
       |
       v
Read affected records
       |
       v
Clean / Normalize
       |
       v
Deduplicate
       |
       v
Delta MERGE / safe partition write
       |
       v
Silver

A rerun of the same logical partition must converge toward the same logical Silver state.

---

# 8. Article Identity

Verify that article IDs are deterministic.

The same logical article processed twice should normally retain the same article_id.

Document exactly how article_id is generated.

Potential inputs may include:

canonical URL

or another approved stable source identity.

Do not change the approved contract silently.

If article identity is currently unstable, report and fix it carefully.

---

# 9. Content Change Semantics

Define behavior when:

same canonical article
+
same article_id
+
content changes

Possible reasons:

- article edited by publisher
- updated title
- content correction

Choose and document a defensible behavior.

Examples:

update current Silver record

or

preserve version history if already architecturally supported.

Do not introduce complex temporal versioning unless necessary.

At minimum ensure updated content does not silently create unrelated duplicate articles.

---

# 10. Gold RAG Incremental Processing

Gold RAG should process only articles that require regeneration when practical.

Determine whether regeneration is required based on:

- new article
- content changed
- chunk configuration changed
- enrichment changed

Stable article input should produce stable chunk IDs.

Rerunning identical input must not generate duplicate logical chunks.

Conceptually:

changed Silver article
       |
       v
rebuild that article's chunks
       |
       v
replace/upsert affected Gold chunks
       |
       v
Qdrant upsert

Do not rebuild all embeddings if only one article changed unless current architecture
makes incremental indexing impractical.

If full rebuild is temporarily required, document it honestly.

---

# 11. Chunk Version Awareness

Record enough information to identify when chunks were produced.

Examples:

chunking_version
chunk_size
chunk_overlap

Reuse existing configuration conventions.

If chunk configuration changes, document whether:

- all affected documents require re-chunking
- Qdrant requires reindexing

Do not pretend old and new chunking strategies are interchangeable.

---

# 12. Embedding Version Awareness

Persist or record:

embedding_provider
embedding_model
embedding_dimension
embedding_version/config identifier where practical

If the embedding model changes:

existing vectors may no longer be compatible.

The system must detect or clearly report dimension incompatibility.

Do not mix embeddings from incompatible models in one Qdrant collection without an
explicit design.

---

# 13. Qdrant Idempotency

Verify stable point IDs.

Repeated indexing of the same chunk must perform:

UPSERT

or equivalent stable replacement.

It must not produce:

chunk A
chunk A copy 2
chunk A copy 3

Provide an automated idempotency test.

---

# 14. Deleted / Removed Article Semantics

Define behavior when an article is removed or marked invalid upstream.

At minimum determine:

- should it remain historically in Bronze?
- should it remain in Silver?
- should its Gold chunks remain?
- should Qdrant remove them?

Do not assume hard delete is always correct.

For the current project, choose the simplest documented behavior consistent with
existing contracts.

---

# 15. Gold Analytics Incremental Processing

Evaluate current Gold Analytics generation.

Prefer affected-partition recomputation rather than full rebuild when practical.

For aggregate data:

if one date/source partition changes,

recompute affected aggregates safely.

Do not implement complicated incremental cube logic if a partition rebuild is simpler
and deterministic.

Correctness is more important than micro-optimization.

---

# 16. DuckDB Serving Refresh

Document how DuckDB sees updated Gold Analytics data.

Possible pattern:

Gold Parquet/Delta
    ->
DuckDB views

If views directly read files, verify freshness behavior.

If materialized tables are used, provide a repeatable refresh mechanism.

Reruns must remain deterministic.

---

# 17. Checkpoint / Watermark State

Introduce checkpoint state only where it solves a real problem.

Potential state:

pipeline
source
last_successful_partition
last_successful_run
updated_at

Do not treat this as event-time watermarking.

This is BATCH PROCESSING STATE.

Keep terminology distinct from future Flink watermarks.

A failed partition must not advance the successful checkpoint.

---

# 18. Backfill Support

Add a controlled backfill mechanism.

Conceptually:

pipeline backfill
    --source ...
    --from-date ...
    --to-date ...

or equivalent repository CLI.

Airflow should support manually initiated backfill using parameters where practical.

Backfill requirements:

- explicit date/partition range
- clear logging
- deterministic order where useful
- idempotent writes
- run metadata
- no accidental processing of unlimited history

Provide a command equivalent to:

make pipeline-backfill FROM=2026-09-01 TO=2026-09-07

Follow repository conventions.

---

# 19. Reprocessing Support

Backfill and reprocessing are not identical.

Backfill:

process historical partitions that may never have been processed.

Reprocess:

intentionally run an already processed partition again.

Support explicit reprocessing.

Example:

make pipeline-reprocess DATE=2026-09-20

or equivalent.

Reprocessing must not create uncontrolled duplicates.

---

# 20. Force / Safety Controls

If a force option exists, make it explicit.

For example:

--force-reprocess

Do not silently overwrite large ranges.

Potentially require:

source
date/range

when force mode is used.

Do not add interactive prompts that break Airflow automation unless a non-interactive
flag exists.

---

# 21. Recovery from Partial Failure

Define recovery behavior.

Example:

Bronze succeeded
Silver succeeded
Gold RAG failed
Gold Analytics succeeded

A retry should NOT necessarily rerun everything from Bronze.

Prefer restarting at the failed stage when safe.

Document:

what can be retried independently

and:

what must be recomputed together.

---

# 22. Stage Status

Operational metadata should make partial completion visible.

For example:

run_id = abc

bronze_ingest       SUCCESS
silver_transform    SUCCESS
gold_rag            FAILED
qdrant_index        NOT_STARTED
gold_analytics      SUCCESS

Do not report the whole pipeline as fully successful when a required branch failed.

---

# 23. Reconciliation

Implement a lightweight reconciliation command.

The purpose is to compare expected relationships between layers.

Example checks:

Bronze records
    vs
Silver records

Silver article IDs
    vs
Gold RAG article IDs

Gold chunk IDs
    vs
Qdrant indexed IDs

Gold Analytics availability
    vs
DuckDB availability

Do not require exact equal counts where deduplication or filtering legitimately changes
counts.

Use contract-aware expectations.

Provide a command such as:

make pipeline-reconcile

Output a human-readable report.

---

# 24. Data Quality Gates

Reuse data quality checks from previous phases.

Consolidate them where practical.

Possible checks:

Bronze:

- readable data
- required raw identity available

Silver:

- article_id non-null
- title/content requirements according to contract
- valid timestamp where required
- duplicate article_id detection
- canonical URL validity where supported

Gold RAG:

- chunk_id non-null
- article_id linkage valid
- empty chunk rate
- duplicate chunk IDs

Qdrant:

- expected collection exists
- vector dimension correct
- indexed records available

Gold Analytics:

- datasets readable
- required aggregate dimensions valid

Do not invent arbitrary quality thresholds without justification.

---

# 25. Quality Failure Severity

Distinguish:

ERROR
WARN

Example:

missing required article_id
    ->
ERROR

optional author missing
    ->
WARN or allowed

Use data contracts as the basis.

Do not treat every null as failure.

---

# 26. Schema Drift Integration

Phase 00 already created:

make data-contracts-check

Integrate schema drift detection into an appropriate validation workflow.

Do NOT automatically update the canonical contract.

If source drift is detected:

report drift

and determine whether:

canonical mapping remains valid

or:

engineering review is required.

An unsafe contract mismatch should fail before corrupting Silver.

---

# 27. Structured Logging

Standardize or improve structured logs.

Include fields such as:

run_id
pipeline
stage
source
partition
duration
input_count
output_count
status

Avoid logging:

full article bodies
embeddings
credentials
secret configuration

Reuse existing logging architecture.

---

# 28. Metrics

Create/reuse consistent metrics across stages.

At minimum:

## Bronze

records_seen
records_written
duplicates_detected
duration

## Silver

input_count
output_count
invalid_count
duplicate_count
insert_count
update_count if supported
duration

## Gold RAG

articles_processed
chunks_created
chunks_replaced
chunks_rejected
duration

## Qdrant

points_upserted
points_deleted if applicable
failures
duration

## Analytics

input_count
affected_partitions
output_rows
duration

Persist metrics using existing conventions.

Do not introduce Prometheus just for this phase.

---

# 29. Pipeline Health Command

Provide one operational command such as:

make pipeline-health

It should inspect relevant local components:

MinIO
Delta/Silver readability
Qdrant
DuckDB
Airflow
PostgreSQL
Kafka
Debezium connector

The command should provide concise statuses.

Example:

MinIO                OK
Silver Delta         OK
Qdrant               OK
DuckDB               OK
Airflow              OK
PostgreSQL           OK
Kafka                OK
Debezium             OK

This is a developer/demo health check.

Do not build a full monitoring platform.

---

# 30. Airflow Incremental Integration

Update Airflow orchestration to use incremental processing.

Do not rewrite DAG architecture unnecessarily.

Normal scheduled/manual run should operate on an explicit logical partition.

Allow DAG parameters where appropriate:

source
processing_date
force_reprocess

Backfill may use:

from_date
to_date

or trigger one logical partition per run.

Prefer clarity over clever dynamic DAG behavior.

---

# 31. Airflow Retry and Recovery

Verify:

task retry
    ->
safe processing

A retry must not produce uncontrolled duplicates.

Document which tasks are:

safe to retry

and any that require:

cleanup/reconciliation.

Use Airflow retries only when the underlying operation is idempotent enough.

---

# 32. Concurrency Safety

Test behavior when two runs target the same logical partition.

Do not allow uncontrolled concurrent writes.

Use the simplest supported mechanism, possibly:

- Airflow concurrency controls
- pool
- max_active_runs
- database/state lock
- Delta transaction behavior

Do not design a complex distributed lock service unless required.

Document the chosen policy.

---

# 33. Rebuild Derived Stores

Derived serving systems should be rebuildable from durable Gold data.

At minimum document/provide:

Qdrant rebuild

from:

Gold RAG chunks

and DuckDB rebuild/refresh

from:

Gold Analytics.

Provide commands equivalent to:

make qdrant-rebuild

make analytics-rebuild

These commands must not require re-crawling or rebuilding Bronze.

---

# 34. Failure Injection / Recovery Tests

Add controlled tests where practical.

Test at least:

Scenario A:
run same partition twice

Expected:
same logical output
no duplicate explosion

Scenario B:
Qdrant unavailable during indexing

Expected:
Gold chunks remain durable
run/stage records failure
after Qdrant returns, indexing can retry

Scenario C:
DuckDB update fails

Expected:
Gold Analytics remains durable
serving can be rebuilt

Scenario D:
Silver processing fails

Expected:
successful checkpoint does not advance

Scenario E:
schema drift/malformed input

Expected:
unsafe data does not silently corrupt Silver

---

# 35. Performance Baseline

Do NOT perform premature optimization.

Record a reproducible LOCAL baseline.

For current sample data report:

- number of raw records
- Bronze ingestion duration
- Silver processing duration
- Gold chunking duration
- embedding/indexing duration
- analytics duration
- end-to-end duration

Also report environment context where practical:

CPU
memory
Spark configuration

Do not present local results as production capacity.

The goal is to establish a baseline for thesis evaluation.

---

# 36. Idempotency Test

Provide a command such as:

make test-idempotency

Concept:

run partition
    ->
record logical counts/hashes

run same partition again
    ->
compare

Verify at minimum:

Silver article count
Silver stable IDs
Gold stable chunk IDs
Qdrant point count
Gold Analytics consistency

Do not rely only on "command exited 0".

Actually compare outputs.

---

# 37. Incremental Test

Provide a test that:

1. processes initial sample dataset
2. records output state
3. adds or exposes one new input record/fixture
4. processes next logical partition/increment
5. verifies old unaffected records remain stable
6. verifies new record appears
7. verifies only affected downstream data changes where practical

Do not mutate the repository's canonical sample data destructively.

Use fixtures/temp data.

---

# 38. Backfill Test

Test:

historical partition A
historical partition B
historical partition C

Run requested range:

A -> C

Verify:

all requested partitions processed

and rerunning the range remains logically idempotent.

---

# 39. Reconciliation Test

Intentionally create or simulate one mismatch in test isolation.

Verify reconciliation detects it.

Examples:

Gold chunk not indexed

or:

missing analytics serving output.

Do not corrupt developer persistent data to run this test.

Use isolated fixtures/test environments.

---

# 40. Makefile / Task Commands

Add/reuse commands equivalent to:

make pipeline-incremental

make pipeline-backfill FROM=... TO=...

make pipeline-reprocess DATE=...

make pipeline-reconcile

make pipeline-health

make test-idempotency

make test-incremental

make test-backfill

make qdrant-rebuild

make analytics-rebuild

make phase5-test

Preserve previous commands.

Follow repository conventions if another task runner is already established.

---

# 41. Documentation

Create:

docs/pipeline-operations.md

Document:

## Normal processing

How normal incremental runs work.

## Incremental boundary

What counts as a processing partition.

## Article identity

How deterministic IDs work.

## Checkpoint

What state advances and when.

## Idempotency

How each layer handles reruns.

## Backfill

Exact commands and behavior.

## Reprocessing

Exact commands and behavior.

## Failure recovery

How to resume each failed stage.

## Reconciliation

How consistency between layers is checked.

## Derived-store rebuild

How to rebuild Qdrant and DuckDB.

## Metrics

What is recorded.

## Health check

How to inspect services.

## Performance baseline

How it was measured.

## Limitations

Clearly document local/demo limitations.

Update:

docs/local-architecture.md

if required.

---

# 42. Architecture After Phase 05

Expected architecture:

                     CONTROL PLANE

            PostgreSQL Configuration
                     |
                  Debezium
                     |
                   Kafka

                    OPERATIONS

              Pipeline Run Metadata
              Checkpoints / Status
              Metrics / Reconciliation

                  ORCHESTRATION

                     Airflow
                  /          
          incremental       backfill
             runs             runs

                    DATA PLANE

                  MinIO Bronze
                       |
                       v
                  Delta Silver
                    /       
                   /         
                  v           v
             Gold RAG    Gold Analytics
                  |           |
                  v           v
               Qdrant       DuckDB

Properties after Phase 05:

- incremental
- idempotent
- rerunnable
- backfillable
- recoverable
- measurable
- reconcilable

---

# 43. Definition of Done

Phase 05 is complete only when:

1. A logical incremental-processing boundary is documented.
2. Normal processing can avoid unnecessary full rebuilds where technically practical.
3. Same input/partition can be processed repeatedly without uncontrolled duplicate
   logical data.
4. Silver IDs remain stable across reruns.
5. Gold chunk IDs remain stable.
6. Qdrant indexing is idempotent.
7. Analytics output remains deterministic.
8. Backfill works for an explicit range.
9. Reprocessing works for an already processed partition.
10. Failed processing does not advance a successful checkpoint.
11. Partial failures can be resumed/retried appropriately.
12. Pipeline runs/stages have traceable status.
13. Data quality gates exist.
14. Schema drift check is integrated appropriately.
15. Reconciliation can detect cross-layer inconsistencies.
16. Qdrant can be rebuilt from durable Gold RAG data.
17. DuckDB can be rebuilt/refreshed from Gold Analytics.
18. Pipeline health command works.
19. Idempotency automated test passes.
20. Incremental automated test passes.
21. Backfill test passes.
22. Previous Phase 01–04 functionality remains operational.
23. Local performance baseline is recorded.
24. Documentation provides reproducible commands.
25. No cloud/Kubernetes/Flink/frontend/LLM generation has been introduced.

---

# 44. Acceptance Scenario — Incremental New Data

Initial:

100 Silver articles

A new Bronze partition contains:

5 genuinely new articles
2 duplicates

After incremental run:

existing logical articles remain stable

5 new logical articles are added

duplicates do not produce duplicate Silver articles

only required Gold data is generated/replaced where practical.

---

# 45. Acceptance Scenario — Same Partition Rerun

Run partition:

2026-09-29

Record:

Silver IDs
Gold chunk IDs
Qdrant point count
Analytics results

Run identical partition again.

Expected:

same logical Silver state

stable chunk IDs

no Qdrant duplicate growth

equivalent analytics result.

---

# 46. Acceptance Scenario — Partial Failure

Silver succeeds.

Gold RAG durable chunks succeed.

Qdrant is unavailable.

Expected:

Gold durable chunks remain available

Qdrant stage is FAILED

overall run does not falsely report full success

after Qdrant recovers:

retry indexing only

no need to rebuild Bronze/Silver unnecessarily.

---

# 47. Acceptance Scenario — Backfill

Request:

FROM=2026-09-01
TO=2026-09-07

Expected:

only requested historical partitions are processed

run metadata records BACKFILL trigger type

rerunning the same backfill does not create duplicate logical outputs.

---

# 48. Acceptance Scenario — Schema Drift

Introduce test fixture containing an unexpected source schema change.

Expected:

schema drift detection reports the change

unsafe contract mismatch does not silently propagate to Silver

canonical contract is NOT automatically rewritten.

---

# 49. Non-Goals

Do not add technologies merely to make Phase 05 appear larger.

Specifically do NOT implement:

- Prometheus/Grafana unless already available
- Kubernetes
- Terraform
- ADLS
- cloud Kafka
- Flink
- stock streaming
- crawler
- frontend
- LLM chatbot
- production NER training
- complex data catalog
- full OpenLineage platform

Phase 05 is about reliability and operational correctness.

---

# 50. Final Report

At completion report:

1. Phase 01–04 verification status
2. incremental boundary selected
3. article identity strategy
4. checkpoint strategy
5. operational metadata schema
6. idempotency strategy per layer
7. Silver incremental strategy
8. Gold incremental strategy
9. Qdrant upsert/rebuild strategy
10. DuckDB refresh/rebuild strategy
11. backfill implementation
12. reprocessing implementation
13. recovery behavior
14. reconciliation checks
15. data-quality gates
16. schema-drift integration
17. metrics implemented
18. health-check implementation
19. files created
20. files modified
21. commands added
22. tests executed
23. actual test results
24. idempotency test result
25. incremental test result
26. backfill test result
27. reconciliation test result
28. performance baseline
29. regressions discovered/fixed
30. known limitations
31. exact commands to reproduce the Phase 05 demo
32. recommended Phase 06 work
33. git status
34. recommended commit message

Update:

docs/agent_tasks/CURRENT_STATUS.md

at the end.

STOP after Phase 05.

Do NOT begin Phase 06 automatically.
