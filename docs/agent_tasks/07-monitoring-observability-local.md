
# Phase 07 — Local Monitoring, Observability, Alerting, and Operational Dashboards

## Context

This phase starts only after Phase 06 has produced a stable LOCAL RELEASE CANDIDATE.

Completed architecture:

Phase 01
Bronze -> Silver
MinIO + PySpark + Delta Lake

Phase 02
Silver -> Gold
Gold RAG -> Embedding -> Qdrant
Gold Analytics -> DuckDB

Phase 03
Airflow orchestration

Phase 04
Metadata-driven control plane
PostgreSQL -> Debezium -> Kafka

Phase 05
Pipeline hardening

- incremental processing
- idempotency
- backfill
- reprocessing
- recovery
- reconciliation
- quality gates
- run/stage metrics

Phase 06
Local release candidate

- reproducible bootstrap
- configuration abstraction
- clean environment
- cloud readiness
- migration manifest
- end-to-end acceptance

Phase 07 adds MONITORING AND OBSERVABILITY around the existing system.

It must not redesign the data pipeline.

---

# Primary Goal

Provide an operational view of the local financial-news platform.

The system should make it possible to answer:

- Are all critical services healthy?
- Is the pipeline currently running?
- When was the last successful run?
- Which stage failed?
- How long does each stage take?
- How many records were processed?
- How many records were invalid?
- How many duplicates were detected?
- Is Silver/Gold data fresh?
- Is Qdrant indexing healthy?
- Is DuckDB serving data available?
- Is Kafka healthy?
- Is Kafka consumer lag increasing?
- Is Debezium healthy?
- Is PostgreSQL healthy?
- Is Airflow healthy?
- Is MinIO healthy?
- Is the pipeline slower than its local baseline?
- Did a data-quality check fail?

The result should be a LOCAL monitoring stack that can later be migrated alongside
the application.

---

# Architecture

Target local monitoring architecture:

                         DATA PLATFORM

     MinIO
       |
     Spark
       |
     Delta
       |
    Gold Layer
    /       
Qdrant     DuckDB

      Airflow

 PostgreSQL
      |
  Debezium
      |
    Kafka

                         OBSERVABILITY

                     Prometheus
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
 Infrastructure     Pipeline Metrics   Data Quality
 Metrics            Metrics            Metrics

                         |
                         v
                       Grafana
                         |
                Dashboards / Alerts

Optional later extension:

Structured Logs
     ->
Loki
     ->
Grafana

Do NOT add Loki unless the existing logging architecture makes it low-cost and useful.

Metrics-first monitoring is the required Phase 07 scope.

---

# Required Reading

Before implementing anything, read:

- AGENTS.md
- docs/data-contracts.md
- artifacts/data-profile.json
- docs/agent_tasks/01-bronze-silver-local.md
- docs/agent_tasks/02-silver-gold-local.md
- docs/agent_tasks/03-airflow-orchestration-local.md
- docs/agent_tasks/04-metadata-cdc-local.md
- docs/agent_tasks/05-pipeline-hardening-local.md
- docs/agent_tasks/06-local-release-cloud-readiness.md
- docs/agent_tasks/CURRENT_STATUS.md if present

Also inspect:

- docs/local-architecture.md
- docs/pipeline-operations.md
- docs/airflow-local.md
- docs/metadata-control-plane.md
- docs/cloud-migration-plan.md
- docs/local-release-checklist.md
- docs/cloud-migration-manifest.md

Inspect actual repository state and git history.

Do not assume documentation is correct without verifying the running implementation.

---

# Scope

Implement ONLY:

1. Prometheus local monitoring
2. Grafana local dashboards
3. infrastructure/service metrics
4. pipeline operational metrics
5. data-quality metrics
6. freshness metrics
7. Airflow monitoring
8. PostgreSQL monitoring
9. Kafka monitoring
10. Debezium/Kafka Connect monitoring
11. MinIO monitoring
12. Qdrant monitoring
13. Docker/container resource monitoring where practical
14. alert rules
15. monitoring smoke tests
16. failure-injection demo scenarios
17. baseline dashboards
18. monitoring documentation
19. regression verification

Optional only if trivial:

- Loki for centralized logs

Do NOT implement:

- cloud migration
- Azure resources
- Kubernetes
- Helm
- Terraform
- stock streaming
- Flink
- crawler
- frontend
- chatbot
- LLM generation
- Power BI
- enterprise APM
- distributed tracing platform
- ELK/OpenSearch stack

---

# 1. Verify Phase 01–06 First

Before changing infrastructure, verify the local release.

Run or inspect the equivalent of:

make bootstrap
make phase6-acceptance

Also verify:

make pipeline-health
make pipeline-reconcile
make test-idempotency
make test-incremental
make test-backfill

Verify:

- Bronze
- Silver
- Gold RAG
- Qdrant
- Gold Analytics
- DuckDB
- Airflow
- PostgreSQL
- Kafka
- Debezium
- incremental processing
- backfill
- recovery
- reconciliation

Record baseline state.

Do not mask existing failures by adding monitoring around a broken system.

---

# 2. Monitoring Principles

Monitoring must observe the existing architecture.

Do NOT modify transformation business logic merely to simplify dashboards.

Use existing metrics/run metadata from Phase 05 wherever possible.

Avoid duplicating the same metric in multiple stores without reason.

Distinguish:

SERVICE METRICS

PIPELINE METRICS

DATA QUALITY METRICS

BUSINESS/DATASET METRICS

---

# 3. Metrics Categories

Define metrics in four main categories.

## A. Infrastructure / Service

Examples:

service_up

CPU usage

memory usage

container restart count

disk/storage usage

request/error metrics where exposed

## B. Pipeline

Examples:

pipeline_runs_total
pipeline_runs_success_total
pipeline_runs_failed_total
pipeline_stage_duration_seconds
pipeline_records_input
pipeline_records_output
pipeline_retries_total
pipeline_last_success_timestamp

## C. Data Quality

Examples:

pipeline_invalid_records
pipeline_duplicate_records
pipeline_schema_drift_detected
pipeline_quality_gate_failures
pipeline_reconciliation_failures

## D. Freshness

Examples:

bronze_last_update_timestamp
silver_last_update_timestamp
gold_rag_last_update_timestamp
gold_analytics_last_update_timestamp
qdrant_last_index_timestamp
pipeline_data_freshness_seconds

Use names consistent with the repository's metrics conventions.

Do not invent dozens of metrics without operational value.

---

# 4. Prometheus

Add Prometheus to local Docker Compose if not already available.

Use:

- persistent storage
- configuration mounted from repository
- health check
- explicit scrape configuration

Do not hardcode secrets.

Prometheus should scrape only metrics that are meaningful.

---

# 5. Batch Pipeline Metrics Strategy

Batch jobs are short-lived.

Do not blindly expose a temporary HTTP server inside every batch job.

Prefer this strategy:

Phase 05 operational metadata
        |
        v
Pipeline Metrics Exporter
        |
        v
Prometheus

Implement a small long-running exporter if this fits the current architecture.

The exporter may query:

pipeline_runs
pipeline_stage_runs
quality/reconciliation state

and expose Prometheus-compatible metrics.

This keeps application jobs independent from Prometheus.

If the repository already uses another clean metrics mechanism, reuse it.

Do not create duplicate operational databases.

---

# 6. Pipeline Metrics Exporter

If needed, implement a lightweight service such as:

services/pipeline_metrics_exporter/

Responsibilities:

- read operational pipeline metadata
- expose /metrics
- remain read-only
- perform lightweight queries
- never modify pipeline state

Metrics should include useful labels such as:

pipeline
stage
source

Avoid high-cardinality labels such as:

run_id
article_id
chunk_id
URL

Never use unbounded IDs as Prometheus labels.

---

# 7. Airflow Monitoring

Inspect the installed Airflow version.

Prefer Airflow's supported native metrics mechanism.

Possible mechanisms may include:

- StatsD
- Prometheus-compatible exporter
- OpenTelemetry

Choose the simplest mechanism compatible with the installed Airflow version.

Monitor at minimum:

- DAG run success/failure
- task success/failure
- task duration
- scheduler health where available
- queued/running tasks if supported

Do not scrape Airflow internal database tables directly if a supported metrics mechanism
already exists.

---

# 8. PostgreSQL Monitoring

Use postgres_exporter or an equivalent established mechanism.

Monitor useful metrics such as:

- PostgreSQL availability
- active connections
- transaction activity
- database size where practical
- lock/wait issues where practical
- replication slot status relevant to Debezium

Do not expose sensitive SQL/query values.

---

# 9. Kafka Monitoring

Monitor Kafka using the simplest reliable mechanism compatible with the current Kafka setup.

Possible mechanisms:

- Kafka JMX metrics
- JMX Prometheus Exporter
- existing Kafka exporter if already used

Monitor at minimum:

- broker up
- topic/partition availability where supported
- produce/consume activity
- consumer lag for relevant consumer groups
- error indicators

Avoid introducing an unnecessarily complex Kafka monitoring platform.

---

# 10. Debezium / Kafka Connect Monitoring

Monitor:

- Kafka Connect availability
- connector status
- connector task status
- failed connector/task count
- source event activity if exposed
- restart/failure state

At minimum expose a clear metric equivalent to:

debezium_connector_up

for the PostgreSQL connector.

If native Prometheus metrics are unavailable, a lightweight exporter may query the
Kafka Connect REST API.

Do not parse Docker logs as the primary health mechanism if a structured endpoint exists.

---

# 11. MinIO Monitoring

Use MinIO's supported Prometheus metrics endpoint where compatible with the installed
version.

Monitor at minimum:

- MinIO availability
- storage usage
- request activity where useful

Avoid implementing a custom MinIO exporter if native metrics exist.

---

# 12. Qdrant Monitoring

Use Qdrant's native metrics endpoint if supported by the installed version.

Monitor at minimum:

- Qdrant availability
- collection/vector count where available
- request/error activity
- resource metrics where available

Do not make expensive collection scans for every Prometheus scrape.

---

# 13. DuckDB Monitoring

DuckDB is an embedded analytical serving engine, not a long-running server.

Do NOT force DuckDB into an infrastructure exporter model.

Monitor DuckDB operationally through pipeline/serving checks.

Useful metrics may include:

duckdb_last_refresh_timestamp
duckdb_analytics_rows
duckdb_health

These can come from the existing pipeline metrics exporter.

---

# 14. Docker Resource Monitoring

For local infrastructure, optionally use cAdvisor or an equivalent lightweight tool.

Monitor:

- CPU
- memory
- network
- container restart/activity

This allows correlation such as:

Spark duration increases
while
container CPU reaches saturation.

Do not add a full Kubernetes monitoring stack.

---

# 15. Grafana

Add Grafana to local Docker Compose.

Use:

- persistent storage
- provisioned Prometheus datasource
- provisioned dashboards where practical

The developer should not have to manually configure dashboards after each reset.

Do not commit production secrets.

---

# 16. Dashboard 1 — Platform Overview

Create a dashboard:

Financial News Platform — Overview

Show:

- MinIO health
- PostgreSQL health
- Kafka health
- Debezium health
- Airflow health
- Qdrant health
- pipeline overall status
- last successful pipeline run
- last failed pipeline run
- latest Silver freshness
- latest Gold freshness

This should be the main demo dashboard.

---

# 17. Dashboard 2 — Pipeline Operations

Create:

Financial News Pipeline — Operations

Show:

- runs by status
- success rate
- failure count
- run duration
- stage duration
- records input
- records output
- retry count
- backfill runs
- reprocessing runs

Where useful include stages:

Bronze
Silver
Gold RAG
Qdrant Index
Gold Analytics
DuckDB Refresh

---

# 18. Dashboard 3 — Data Quality

Create:

Financial News Pipeline — Data Quality

Show:

- invalid record count
- duplicate count
- duplicate rate
- quality gate failures
- schema drift status
- reconciliation failures
- Bronze -> Silver record relationship
- Silver -> Gold relationship where meaningful

Do not imply expected counts must always be equal.

Respect legitimate deduplication/filtering.

---

# 19. Dashboard 4 — Freshness

Create:

Financial News Pipeline — Freshness

Show:

- Bronze latest update
- Silver latest update
- Gold RAG latest update
- Qdrant latest index
- Gold Analytics latest update
- DuckDB latest refresh
- freshness lag

Provide clear units.

Use seconds/minutes/hours appropriately.

---

# 20. Dashboard 5 — Kafka / CDC

Create:

Metadata Control Plane — CDC

Show:

- Kafka broker health
- metadata topic activity
- relevant consumer lag
- Debezium connector state
- connector task state
- CDC event rate if available
- latest CDC event timestamp
- PostgreSQL replication slot state where available

Make clear:

this dashboard is CONTROL PLANE CDC.

It is NOT stock market streaming.

---

# 21. Dashboard 6 — Local Resources

If resource metrics are available, create:

Local Infrastructure — Resources

Show:

- CPU usage per major service
- memory usage
- container state/restarts
- disk/storage usage where available

This dashboard will later provide the LOCAL performance baseline.

---

# 22. Grafana Provisioning

Prefer dashboards-as-code.

Store dashboard definitions in repository where practical.

Example:

monitoring/
    prometheus/
    grafana/
        provisioning/
        dashboards/

Do not require manual dashboard recreation after:

make local-reset

or:

make bootstrap

---

# 23. Alerts

Create meaningful local alert rules.

Do not create hundreds of alerts.

At minimum consider:

ServiceDown

PipelineRunFailed

PipelineNoSuccessfulRunRecently

SilverDataStale

GoldDataStale

QdrantIndexFailure

DataQualityGateFailed

ReconciliationFailed

DebeziumConnectorDown

KafkaConsumerLagHigh

Choose thresholds based on current local baseline or clearly configurable defaults.

Do not pretend arbitrary thresholds are production SLAs.

---

# 24. Alertmanager

Alertmanager is optional but recommended if integration is clean.

For local demo:

Prometheus
    ->
Alertmanager

No Slack/email integration is required.

The objective is to demonstrate alert state and routing.

Grafana alert visualization may also be sufficient if simpler.

Do not introduce external notification credentials.

---

# 25. Freshness Semantics

Define freshness precisely.

For example:

silver_freshness_seconds =
current_time - latest_successful_silver_output_time

Do not measure:

file modification time

if a more reliable pipeline timestamp already exists.

Document the source of each freshness metric.

---

# 26. Success Rate

Define pipeline success rate explicitly.

For example:

successful_runs / completed_runs

for a selected period.

Do not include still-running runs as failures.

Document query/window semantics.

---

# 27. Pipeline Duration

Monitor both:

end-to-end duration

and:

stage duration.

This supports thesis evaluation.

Do not confuse:

Airflow scheduling delay

with:

processing duration

unless explicitly labeled.

---

# 28. Data Volume Metrics

Track:

input records
output records

and relevant transformation effects.

Examples:

Bronze input
Silver output
duplicates
invalid

For RAG:

articles
chunks
Qdrant points

For analytics:

input articles
output aggregate rows

Avoid article-level Prometheus labels.

---

# 29. Baseline Capture

Use the stable Phase 06 acceptance dataset.

Run the pipeline multiple times if practical.

Record a LOCAL baseline.

At minimum:

- end-to-end duration
- Silver duration
- Gold RAG duration
- Qdrant indexing duration
- Gold Analytics duration
- record counts
- CPU/memory observations where available

Store baseline documentation in:

docs/local-monitoring-baseline.md

Do not claim statistical significance unless enough runs are measured.

---

# 30. Failure Injection

Add reproducible LOCAL demo scenarios.

Do not corrupt durable developer data.

At minimum test:

## Scenario A — Qdrant Down

Stop Qdrant.

Run affected downstream stage.

Expected:

- pipeline failure visible
- Qdrant health becomes unhealthy
- failure metric increments
- alert fires where configured

Restart Qdrant.

Retry.

Expected:

pipeline recovers.

---

## Scenario B — Debezium Connector Failure

Pause/stop or safely misconfigure a test connector if practical.

Expected:

- Debezium connector metric becomes unhealthy
- alert visible
- Kafka/PostgreSQL remain distinguishable from connector failure

Restore connector.

---

## Scenario C — Data Quality Failure

Use isolated malformed fixture.

Expected:

quality gate failure metric becomes visible.

Do not modify canonical sample data destructively.

---

# 31. Monitoring Smoke Test

Provide:

make monitoring-test

It should verify:

- Prometheus reachable
- expected scrape targets exist
- Grafana reachable
- pipeline exporter reachable if used
- critical service metrics exist

It does not need browser automation.

---

# 32. Monitoring Acceptance Test

Provide:

make phase7-acceptance

It should verify programmatically where practical:

- Prometheus healthy
- no unexpected critical scrape failures
- critical metrics exist
- dashboards are provisioned
- alert rules load
- pipeline metrics appear
- service metrics appear
- freshness metrics appear

Provide concise pass/fail output.

---

# 33. Monitoring Health

Extend:

make pipeline-health

or provide:

make monitoring-health

Show:

Prometheus     OK
Grafana        OK
PipelineExport OK
PostgreSQL     OK
Kafka Metrics  OK
Debezium       OK
MinIO Metrics  OK
Qdrant Metrics OK

Do not declare service health based solely on exporter health.

---

# 34. Metrics Cardinality Audit

Inspect Prometheus labels.

Do NOT use:

article_id
chunk_id
run_id
source_url
error stack trace

as unbounded labels.

Acceptable low-cardinality labels may include:

pipeline
stage
status
source if bounded
trigger_type

Document cardinality decisions.

---

# 35. Metrics Retention

For local development choose a reasonable short retention period.

Do not configure production-scale retention.

Document:

Prometheus retention

Grafana persistent volume behavior.

---

# 36. Logs

The application already has structured logging from previous phases.

Do not replace it.

Ensure logs contain useful correlation fields where applicable:

run_id
pipeline
stage
source
partition

If Loki is added:

use existing logs

rather than creating a second logging format.

Loki remains optional.

---

# 37. Tracing

Distributed tracing is OUT OF SCOPE for Phase 07 unless the repository already has it.

Do not introduce Jaeger/Tempo solely for architecture complexity.

Metrics + structured logs are sufficient for the current data pipeline.

---

# 38. Security

Do not expose real secrets through:

Prometheus labels

Grafana dashboards

exporter metrics

logs

configuration committed to repository.

Grafana local credentials must use environment configuration.

Do not commit production-like credentials.

---

# 39. Docker Compose

Integrate monitoring services into the existing local Compose environment.

Prefer:

Prometheus
Grafana
optional Alertmanager
optional cAdvisor
required exporters

Do not create a completely separate duplicate platform unless repository structure makes
a Compose override preferable.

A clean pattern may be:

docker-compose.yml
docker-compose.monitoring.yml

if it improves optional startup.

Example:

make monitoring-up

should start monitoring on top of the existing platform.

---

# 40. Makefile / Task Commands

Add/reuse commands equivalent to:

make monitoring-up
make monitoring-down
make monitoring-logs
make monitoring-health
make monitoring-test
make phase7-acceptance
make monitoring-baseline

Optional:

make failure-demo-qdrant
make failure-demo-cdc

Preserve all previous commands.

---

# 41. Documentation

Create:

docs/monitoring-observability.md

Document:

## Architecture

## Metrics sources

## Prometheus

## Grafana

## Exporters

## Pipeline metrics

## Data-quality metrics

## Freshness metrics

## Dashboards

## Alerts

## Failure injection

## Baseline

## Startup

## Shutdown

## Troubleshooting

## Known limitations

---

# 42. Local Architecture Update

Update:

docs/local-architecture.md

to include:

OBSERVABILITY PLANE

Prometheus
Grafana
Exporters
Alert rules

Do not change the existing data/control/orchestration architecture.

---

# 43. Monitoring Architecture Document

The final architecture should clearly separate:

DATA PLANE

Bronze
Silver
Gold

CONTROL PLANE

PostgreSQL
Debezium
Kafka

ORCHESTRATION

Airflow

OPERATIONS

Run state
checkpoints
reconciliation

OBSERVABILITY

Prometheus
Grafana
alerts
exporters

---

# 44. Cloud Readiness

Monitoring configuration should not unnecessarily assume local endpoints.

Use service discovery/configuration appropriate for local Compose.

Document future migration mapping:

Prometheus local
    ->
Prometheus/Kubernetes monitoring or managed monitoring

Grafana local
    ->
Grafana cloud/cluster/managed equivalent

Do NOT migrate anything yet.

---

# 45. Thesis Evaluation Mapping

Create a section mapping monitoring metrics to thesis evaluation criteria.

At minimum:

Batch Pipeline:

job success rate
processing duration
invalid records
duplicate records

Data Quality:

quality gate results
schema drift
reconciliation

Operational:

last successful run
freshness
retry/failure behavior

Control Plane:

CDC health
Kafka lag
Debezium status

Clearly distinguish metrics already required by the thesis from additional engineering
metrics.

---

# 46. Definition of Done

Phase 07 is complete only when:

1. Prometheus starts locally.
2. Grafana starts locally.
3. Critical monitoring targets are healthy.
4. Pipeline operational metrics are exposed.
5. Pipeline success/failure is visible.
6. Stage duration is visible.
7. Input/output counts are visible.
8. Duplicate/invalid counts are visible.
9. Freshness is visible.
10. PostgreSQL health is visible.
11. Kafka health/lag is visible where supported.
12. Debezium connector status is visible.
13. MinIO health/metrics are visible.
14. Qdrant health/metrics are visible.
15. DuckDB operational state is represented.
16. At least four useful dashboards exist:

    - overview
    - pipeline operations
    - data quality/freshness
    - metadata CDC
17. Alert rules exist.
18. Qdrant failure demo is observable.
19. Data-quality failure is observable.
20. Monitoring smoke test passes.
21. Phase 07 acceptance test passes.
22. Existing Phase 01–06 regression tests remain valid.
23. Local baseline is documented.
24. Monitoring documentation is reproducible.
25. No cloud infrastructure is required.

---

# 47. Acceptance Scenario — Normal Pipeline

Run normal pipeline.

Expected Grafana/Prometheus observations:

pipeline run starts

stage metrics change

record counts are recorded

duration is recorded

successful run count increases

last success timestamp updates

freshness returns to normal.

---

# 48. Acceptance Scenario — Pipeline Failure

Induce an isolated downstream failure.

Expected:

failed stage visible

pipeline failure count increments

overall success is not falsely reported

alert becomes pending/firing according to configured rule.

---

# 49. Acceptance Scenario — Recovery

Restore failed dependency.

Retry pipeline stage.

Expected:

successful retry visible

new successful run/stage recorded

health recovers

alert resolves where appropriate.

---

# 50. Acceptance Scenario — Data Quality

Process controlled malformed fixture.

Expected:

invalid/quality metric increases

quality gate status visible

pipeline behavior matches Phase 05 policy.

---

# 51. Acceptance Scenario — CDC Failure

Stop or pause Debezium connector safely.

Expected:

connector health becomes unhealthy

CDC dashboard shows issue

Kafka broker and PostgreSQL health remain distinguishable

restore connector

health returns.

---

# 52. Non-Goals

Do NOT add technology merely for visual complexity.

Do NOT implement:

- Kubernetes monitoring
- Azure Monitor
- cloud Grafana
- managed Prometheus
- ELK
- OpenSearch
- Jaeger
- Tempo
- production pager integrations
- stock streaming metrics
- Flink monitoring

Those belong to later phases.

---

# 53. Deliverables

At minimum create/update:

monitoring/prometheus/...

monitoring/grafana/...

monitoring/exporters/... if needed

docs/monitoring-observability.md

docs/local-monitoring-baseline.md

docs/local-architecture.md

Docker Compose monitoring configuration

Makefile/task commands

monitoring tests

acceptance tests

---

# 54. Final Report

At completion report:

1. Phase 01–06 verification status
2. monitoring architecture
3. Prometheus setup
4. Grafana setup
5. exporters added
6. pipeline metrics exposed
7. infrastructure metrics exposed
8. data-quality metrics
9. freshness metrics
10. Kafka metrics
11. Debezium metrics
12. Airflow metrics
13. PostgreSQL metrics
14. MinIO metrics
15. Qdrant metrics
16. DuckDB monitoring strategy
17. dashboards created
18. alert rules created
19. failure scenarios tested
20. local baseline
21. files created
22. files modified
23. commands added
24. tests executed
25. actual test results
26. acceptance result
27. regressions found/fixed
28. known limitations
29. exact demo commands
30. recommended Phase 08 cloud migration sequence
31. git status
32. recommended commit message

Update:

docs/agent_tasks/CURRENT_STATUS.md

at the end.

STOP after Phase 07.

Do NOT begin actual cloud migration.
