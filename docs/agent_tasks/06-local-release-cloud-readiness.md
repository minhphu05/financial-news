
# Phase 06 — Local Release Candidate and Cloud Migration Readiness

## Context

This phase continues after:

Phase 00
Data profiling and data contracts

Phase 01
Bronze -> Silver
MinIO + PySpark + Delta Lake

Phase 02
Silver -> Gold
Qdrant + DuckDB

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
- quality gates
- metrics
- reconciliation
- health checks

The local news pipeline should now be functionally complete.

Phase 06 is the FINAL LOCAL-FOCUSED phase before actual cloud migration.

Do NOT provision or depend on real cloud infrastructure in this phase.

The goal is to turn the current local system into a reproducible,
environment-independent release candidate that can later migrate from:

LOCAL:

- MinIO
- Docker Compose
- local PostgreSQL
- local Kafka
- local Qdrant
- local Spark
- local Airflow

TO FUTURE CLOUD:

- Azure Data Lake Storage Gen2 or approved object storage
- Kubernetes
- managed or Kubernetes PostgreSQL
- Kafka cluster / managed Kafka
- scalable Spark execution
- cloud/Kubernetes Airflow
- scalable Qdrant deployment

without rewriting business transformation logic.

---

# Primary Goal

Produce a LOCAL RELEASE CANDIDATE with:

- reproducible clean setup
- environment-independent configuration
- no hidden developer-machine dependencies
- containerized application jobs
- validated storage abstraction
- validated service configuration abstraction
- deterministic bootstrap
- end-to-end acceptance tests
- disaster/rebuild procedure
- configuration profiles
- migration manifest
- local resource/performance baseline
- documented mapping from local components to future cloud components

Do not add new product features.

---

# Required Reading

Before doing anything, read:

- AGENTS.md
- docs/data-contracts.md
- artifacts/data-profile.json
- docs/agent_tasks/01-bronze-silver-local.md
- docs/agent_tasks/02-silver-gold-local.md
- docs/agent_tasks/03-airflow-orchestration-local.md
- docs/agent_tasks/04-metadata-cdc-local.md
- docs/agent_tasks/05-pipeline-hardening-local.md
- docs/agent_tasks/CURRENT_STATUS.md if present

Also inspect:

- docs/local-architecture.md
- docs/pipeline-operations.md
- docs/airflow-local.md
- docs/metadata-control-plane.md
- Docker Compose files
- Dockerfiles
- Makefile/task runner
- environment configuration
- storage abstraction
- Spark configuration
- Airflow DAGs
- PostgreSQL migrations
- Kafka/Debezium configuration
- Qdrant configuration
- DuckDB configuration
- tests
- recent git history

Do not assume documentation matches reality.

Verify the implementation.

---

# Scope

Implement ONLY:

1. verify Phase 01–05 functionality
2. environment/configuration audit
3. local/cloud boundary audit
4. remove inappropriate local hardcoding
5. normalize configuration profiles
6. validate storage abstraction
7. containerize required pipeline jobs where necessary
8. clean bootstrap workflow
9. clean teardown/reset workflow
10. end-to-end acceptance test
11. deterministic demo dataset/bootstrap
12. backup/rebuild verification
13. derived-store rebuild verification
14. dependency/version locking
15. local resource baseline
16. migration compatibility assessment
17. cloud migration manifest
18. release checklist
19. documentation
20. regression testing

Do NOT implement yet:

- actual Azure resources
- actual ADLS migration
- Kubernetes manifests
- Helm
- Terraform
- cloud networking
- cloud IAM
- managed Kafka
- managed PostgreSQL
- cloud Airflow
- cloud Spark
- production secrets manager
- crawler
- Flink
- stock streaming
- frontend
- LLM chatbot
- Power BI

---

# 1. Verify Phase 01–05 First

Run or inspect all relevant existing commands.

Verify at minimum:

- infrastructure starts
- Bronze ingestion works
- Spark Silver processing works
- Delta Silver is readable
- Gold RAG builds
- embedding works
- Qdrant indexing works
- semantic retrieval works
- Gold Analytics builds
- DuckDB works
- Airflow DAGs load and run
- metadata PostgreSQL works
- Debezium connector works
- Kafka CDC works
- incremental processing works
- idempotency test passes
- backfill works
- reprocessing works
- reconciliation works
- health check works

Record actual results.

If previous functionality is broken:

fix only necessary regressions

and document the change.

---

# 2. Configuration Audit

Search the repository for environment-specific assumptions.

Detect examples such as:

localhost

127.0.0.1

hardcoded container names

hardcoded MinIO endpoint

hardcoded bucket names

hardcoded absolute paths such as:

/home/<developer></developer>/...

hardcoded PostgreSQL URLs

hardcoded Kafka brokers

hardcoded Qdrant URLs

hardcoded Airflow URLs

hardcoded Spark master addresses

hardcoded credentials

hardcoded object-storage schemes

Classify each occurrence:

VALID LOCAL DEFAULT
CONFIGURATION BUG
TEST FIXTURE
DOCUMENTATION ONLY

Do not blindly remove every "localhost".

Tests and explicit local profiles may legitimately contain local addresses.

---

# 3. Configuration Profiles

Create or normalize explicit environment profiles.

Conceptually:

config/
    local
    test
    future-cloud-template

Follow existing repository conventions.

Do not create another configuration framework if one already exists.

Local configuration may use:

ENVIRONMENT=local

Future template may use:

ENVIRONMENT=cloud

But application logic must not contain:

if cloud:
    completely different transformation logic

Environment differences belong primarily in adapters/configuration.

---

# 4. Environment Variable Contract

Create/update:

.env.example

Document required variables.

Group them logically.

Example categories:

## Runtime

ENVIRONMENT
LOG_LEVEL

## Object Storage

OBJECT_STORAGE_PROVIDER
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY
OBJECT_STORAGE_SECRET_KEY

## Data URIs

BRONZE_NEWS_URI
SILVER_NEWS_URI
GOLD_RAG_URI
GOLD_ANALYTICS_URI

## PostgreSQL

DATABASE_HOST
DATABASE_PORT
DATABASE_NAME
DATABASE_USER
DATABASE_PASSWORD

## Kafka

KAFKA_BOOTSTRAP_SERVERS

## Qdrant

QDRANT_URL
QDRANT_COLLECTION

## Embedding

EMBEDDING_PROVIDER
EMBEDDING_MODEL

## Airflow

existing required settings

Do not include real secrets.

---

# 5. Configuration Validation

Applications/jobs should fail early with clear messages when required
configuration is invalid or missing.

Bad:

connection error deep inside Spark 5 minutes later

Better:

configuration validation failed:
SILVER_NEWS_URI is missing

Reuse the existing settings/configuration system.

Do not introduce duplicate config loaders.

---

# 6. Storage Abstraction Audit

Verify that transformation code is not tightly coupled to MinIO.

Business logic should conceptually work with:

bronze_uri
silver_uri
gold_uri

rather than:

minio-specific implementation everywhere.

Local:

s3a://...

Future:

abfss://...

or another approved cloud URI.

Do NOT implement ADLS access yet.

Instead verify that cloud migration can occur by replacing:

configuration
+
storage adapter/configuration

rather than rewriting:

cleaning
deduplication
chunking
analytics
business logic.

Document any unavoidable provider-specific coupling.

---

# 7. Filesystem Audit

No production-path business logic should depend on a developer machine path.

Examples to remove from runtime logic:

/home/trongkhoi/...

/Users/name/...

C:\\Users\\...

Use:

project-relative paths for fixtures

or:

configured storage paths.

Tests may use temporary directories.

---

# 8. Containerization Audit

Inspect all pipeline components.

Identify which require reproducible images.

Potential components:

- pipeline application
- Spark jobs
- Airflow runtime
- metadata consumer
- helper CLI

Do not create one Docker image per tiny Python script unnecessarily.

Prefer a maintainable image strategy.

Document image responsibilities.

---

# 9. Application Image

Where appropriate, create/reuse a common project image containing:

- application code
- pipeline CLI
- required Python dependencies
- data-processing utilities

Spark-specific requirements may use an appropriate Spark image strategy.

Do not install unrelated infrastructure inside the application image.

---

# 10. Image Reproducibility

Pin important dependencies sufficiently for thesis reproducibility.

Audit:

Python version

Spark version

Delta Lake version

Airflow version

PostgreSQL version

Kafka version

Debezium version

Qdrant version

DuckDB version

major Python dependencies

embedding model identifier

Do not unnecessarily freeze OS transitive packages unless project conventions require it.

Document compatibility-sensitive combinations such as:

Spark ↔ Delta

Kafka ↔ Debezium

---

# 11. Clean Machine Bootstrap

The project must provide a reproducible bootstrap from a clean developer environment.

Target experience conceptually:

git clone ...
cp .env.example .env
make bootstrap
make phase6-acceptance

Do not assume:

existing MinIO buckets

existing PostgreSQL tables

existing Kafka topics

existing Debezium connector

existing Qdrant collection

existing DuckDB database

existing Airflow database

These should be created through documented bootstrap procedures.

---

# 12. Bootstrap Command

Create/reuse a command equivalent to:

make bootstrap

It should orchestrate initialization without embedding business transformations unnecessarily.

Conceptual responsibilities:

1. validate dependencies
2. start infrastructure
3. wait for services to become healthy
4. initialize MinIO/buckets
5. run database migrations
6. initialize Airflow if required
7. register Debezium connector if appropriate
8. seed metadata
9. prepare required directories/storage
10. report system status

It should be safe enough to rerun.

---

# 13. Clean Reset

Provide a command such as:

make local-reset

or:

make clean-state

This should clearly distinguish:

SOFT RESET

from:

DESTRUCTIVE RESET.

Do not accidentally delete persistent developer data without an explicit destructive command.

Example:

make reset-derived

may remove:

Qdrant
DuckDB derived serving state

but retain Bronze/Silver durable data.

A full destructive reset should require an explicit command/name.

---

# 14. Rebuild Hierarchy

Document which layers can rebuild others.

Expected:

Bronze
  ->
Silver
  ->
Gold
  ->
Qdrant / DuckDB

Therefore:

Qdrant loss
  ->
rebuild from Gold RAG

DuckDB loss
  ->
rebuild from Gold Analytics

Gold loss
  ->
rebuild from Silver

Silver loss
  ->
rebuild from Bronze

Do not make a derived serving system the sole source of truth.

---

# 15. Disaster/Rebuild Test

Create a safe local test that verifies rebuildability.

At minimum:

Scenario A:
delete isolated/test Qdrant collection
    ->
rebuild from Gold
    ->
retrieval works again

Scenario B:
remove isolated/test DuckDB
    ->
rebuild from Gold Analytics
    ->
queries work again

Where practical:

Scenario C:
rebuild Gold fixture outputs from Silver

Do not destroy real developer state during automated tests.

---

# 16. Local Release Dataset

Define a stable small demo/acceptance dataset.

Do not depend on arbitrary changing production-like local files.

Reuse existing sample fixtures where possible.

The acceptance dataset should support:

- deduplication
- valid article
- malformed case
- incremental new article
- semantic retrieval
- analytics
- backfill/reprocessing

Document which fixture demonstrates which capability.

---

# 17. End-to-End Acceptance Test

Create a command:

make e2e-local

or equivalent.

From a controlled test state it should prove:

sample input
    ->
Bronze
    ->
Silver
    ->
Gold RAG
    ->
Qdrant
    ->
semantic retrieval

AND:

Silver
    ->
Gold Analytics
    ->
DuckDB

AND verify orchestration/operational components as appropriate.

Do not require paid external APIs.

---

# 18. Full Local Acceptance

Create a higher-level command:

make phase6-acceptance

It should combine relevant checks without simply running every slow command blindly.

Verify at minimum:

- service health
- schema/data contract check
- Bronze/Silver
- Gold
- Qdrant retrieval
- DuckDB query
- Airflow DAG validity
- metadata CDC
- incremental processing
- idempotency
- reconciliation

Produce a concise acceptance summary.

---

# 19. Acceptance Report

Generate an artifact such as:

artifacts/local-release-report.json

and/or:

artifacts/local-release-report.md

Record:

timestamp
git commit
environment
service versions
test results
record counts
pipeline durations
known warnings

Do not commit volatile reports if repository conventions exclude generated artifacts.

At minimum provide a reproducible generation command.

---

# 20. Local Resource Baseline

Measure current local resource expectations.

Document:

CPU environment
RAM
Docker resources where known
Spark worker configuration
sample dataset size

Record practical observations:

startup time
pipeline duration
peak memory if readily measurable
storage usage

Do not claim these numbers represent production scalability.

They establish a migration baseline.

---

# 21. Scale-readiness Reasoning

Document how major components scale conceptually.

Example:

MinIO local
    ->
cloud object storage

Spark local/standalone
    ->
Spark workers / Kubernetes

Airflow local
    ->
distributed/Kubernetes deployment

Kafka single broker
    ->
multi-broker cluster

PostgreSQL local
    ->
managed PostgreSQL

Qdrant local
    ->
Qdrant cluster/cloud

Do not benchmark hypothetical cloud scale.

Clearly distinguish:

architectural scalability

from:

measured local performance.

---

# 22. Local-to-Cloud Component Mapping

Create:

docs/cloud-migration-plan.md

Include a table:

| Concern | Local | Future Cloud | Migration Type |

Examples:

Object storage
MinIO
ADLS Gen2
configuration + Spark connector

Orchestration
Airflow Docker
Airflow on Kubernetes/cloud
deployment

Compute
Spark local/standalone
Spark on Kubernetes/managed Spark
deployment/configuration

Metadata DB
PostgreSQL Docker
managed PostgreSQL
data/schema migration

Kafka
single local broker
managed/multi-broker Kafka
infrastructure

Vector DB
Qdrant Docker
Qdrant Cloud/Kubernetes
data rebuild/migration

Analytics
DuckDB
TBD
evaluate

Do not invent final cloud choices that have not been approved.

Mark undecided items as TBD.

---

# 23. Migration Classification

For each component classify future migration as:

CONFIG ONLY

ADAPTER CHANGE

DEPLOYMENT CHANGE

DATA MIGRATION

CODE CHANGE REQUIRED

The ideal outcome is that most data-processing business logic requires:

NO CODE CHANGE

or minimal adapter/config changes.

Document exceptions.

---

# 24. Azure Data Lake Readiness

The target architecture currently mentions Azure Data Lake Storage Gen2.

Do NOT connect to Azure in Phase 06.

Instead inspect what would be required to migrate:

MinIO S3A

to:

ADLS Gen2 ABFS/ABFSS

Identify:

- Spark filesystem connector requirements
- URI differences
- authentication differences
- Delta compatibility considerations
- environment variables/secrets required

Create a checklist.

Do not add real Azure credentials.

---

# 25. Kubernetes Readiness

Do NOT create Kubernetes manifests yet.

Instead identify each currently containerized service and classify:

STATELESS

STATEFUL

JOB

SCHEDULER/CONTROL

Examples may include:

pipeline app
Spark
Airflow
PostgreSQL
Kafka
Debezium/Kafka Connect
Qdrant

Document:

persistent storage needs
ports
health probes
configuration
secrets
resource considerations

This will become input for the future Kubernetes phase.

---

# 26. Health Checks

Audit Docker health checks.

Every critical service should have a meaningful health/readiness check where practical.

Examples:

MinIO
PostgreSQL
Kafka
Kafka Connect
Qdrant
Airflow

Do not confuse:

container running

with:

application ready.

Reuse Phase 05 pipeline-health command.

Improve only where necessary.

---

# 27. Startup Dependency Robustness

Verify services/jobs do not rely only on arbitrary:

sleep 30

Prefer actual readiness checks.

Replace fragile fixed sleeps where practical.

Retries with bounded timeout are acceptable.

Do not build a complex service-discovery system.

---

# 28. Secret Audit

Search repository history/current files as practical for accidentally committed secrets.

At minimum inspect current tracked files.

Ensure no real:

passwords
API keys
access keys
cloud credentials

are committed.

Update:

.gitignore
.env.example

where required.

Do not print secrets in logs.

---

# 29. Dependency Security / Sanity Check

Inspect dependency files for:

unused major dependencies
duplicate packages
obvious version conflicts

Do not perform a broad upgrade of all dependencies.

Stability is more important before migration.

Only change dependencies when justified.

---

# 30. CI-Friendly Test Entry Point

Provide a single command suitable for future CI:

make ci-test

It should run:

unit tests
contract-related tests
DAG import tests
important integration tests that can run in CI

Separate heavy full-infrastructure acceptance where necessary.

Do not assume CI currently exists.

This phase prepares for it.

---

# 31. Test Categorization

Clearly categorize:

unit

integration

e2e

acceptance

slow/infrastructure

Use existing pytest markers or project conventions if available.

This enables cloud/CI phases to select appropriate tests.

---

# 32. Documentation Verification

Audit README/setup docs.

A new developer should not need private chat history to start the project.

The repository should explain:

what the system is

architecture

local requirements

bootstrap

run pipeline

run Airflow

test CDC

run incremental pipeline

run backfill

run reconciliation

run acceptance

reset/rebuild

known limitations

future cloud mapping

---

# 33. Architecture Documentation

Update:

docs/local-architecture.md

to reflect the actual final local release architecture.

Do not document aspirational components as already implemented.

Use clear labels:

IMPLEMENTED LOCAL

FUTURE CLOUD TARGET

---

# 34. Architecture Decision Records

If the repository has no decision log, create or update:

docs/decisions.md

Record major decisions already made, for example:

- MinIO used as local object-storage substitute
- Delta Lake as durable Silver
- Qdrant is derived vector serving
- DuckDB is local analytical serving
- Kafka Phase 04 is control plane
- Airflow contains orchestration only
- incremental batch for news
- cloud migration deferred until local release

Do not rewrite history inaccurately.

---

# 35. Migration Manifest

Create:

docs/cloud-migration-manifest.md

For every major component describe:

CURRENT

TARGET

DATA TO MIGRATE

CONFIG TO CHANGE

APPLICATION CODE IMPACT

VALIDATION TEST

ROLLBACK APPROACH

Example:

Component:
Object Storage

Current:
MinIO

Target:
ADLS Gen2

Data:
Bronze
Silver Delta
Gold

Code impact:
Expected minimal

Validation:
read Silver
Delta history
record counts
hash checks

Rollback:
switch storage config back to MinIO

Do not execute migration yet.

---

# 36. Data Migration Validation Strategy

Define future cloud validation.

For durable datasets consider:

record counts
partition counts
content hashes
Delta versions/history
sample row comparisons

For derived stores:

prefer rebuild when practical

instead of treating them as authoritative migration sources.

Example:

Qdrant
may be rebuilt from Gold

DuckDB
may be rebuilt from Gold Analytics

Document this.

---

# 37. Release Checklist

Create:

docs/local-release-checklist.md

Include checkboxes for:

Configuration
Storage
Bronze
Silver
Gold
Qdrant
DuckDB
Airflow
PostgreSQL
Kafka
Debezium
Incremental
Backfill
Recovery
Reconciliation
Security
Documentation
Acceptance tests

This becomes the gate before cloud migration.

---

# 38. Local Release Version

Introduce a simple project release identifier if one does not exist.

Do not build a complex release system.

A git tag will eventually be sufficient.

Document recommendation such as:

local-rc1

Do NOT create/push a tag automatically unless explicitly requested.

---

# 39. Definition of Local Release Candidate

The local pipeline is considered READY FOR CLOUD MIGRATION only when:

1. clean bootstrap succeeds
2. no developer-specific paths are required
3. configuration is externalized
4. no real secrets are committed
5. Bronze -> Silver works
6. Silver -> Gold works
7. Qdrant retrieval works
8. DuckDB analytics works
9. Airflow orchestration works
10. metadata CDC works
11. incremental processing works
12. idempotency tests pass
13. backfill works
14. reprocessing works
15. recovery behavior works
16. reconciliation passes
17. derived stores can be rebuilt
18. health checks pass
19. full local E2E acceptance passes
20. cloud migration mapping is documented
21. cloud migration manifest exists
22. local release checklist is complete

---

# 40. Acceptance Scenario — Clean Bootstrap

Start from controlled clean state.

Run:

make bootstrap

Then:

make phase6-acceptance

Expected:

all required local services initialize

pipeline works

acceptance report passes

No manual database editing should be required.

---

# 41. Acceptance Scenario — No Developer Machine Coupling

Search runtime/configuration code.

Expected:

no required dependency on:

/home/trongkhoi/...

developer usernames

container IPs

machine-specific absolute paths

Any valid test fixture paths must be clearly test-only.

---

# 42. Acceptance Scenario — Rebuild Serving Layer

Destroy isolated/test:

Qdrant serving state
DuckDB serving state

Rebuild.

Expected:

Qdrant restored from Gold RAG

DuckDB restored from Gold Analytics

No Bronze recrawl/reingestion required.

---

# 43. Acceptance Scenario — Environment Configuration

Start local system using local environment profile.

Expected:

no cloud credentials required.

Validate future cloud template syntactically where practical.

Expected:

configuration can express cloud endpoint/provider differences without rewriting
transformation code.

Do not attempt actual cloud connection.

---

# 44. Acceptance Scenario — Full Regression

Run:

Phase 01 tests
Phase 02 tests
Phase 03 tests
Phase 04 tests
Phase 05 tests
Phase 06 acceptance

Expected:

no unresolved regressions.

If an old test is obsolete due to an approved design change, document and update it
rather than simply deleting it.

---

# 45. Non-Goals

Do NOT implement:

Azure subscription/resource creation
ADLS account/container creation
Kubernetes manifests
Helm
Terraform
cloud IAM
managed Kafka
managed PostgreSQL
cloud Airflow
cloud Qdrant
cloud Spark
Flink
stock data streaming
crawler
frontend
Power BI
LLM generation

Phase 06 prepares migration.

It does not perform migration.

---

# 46. Deliverables

At minimum produce/update:

docs/cloud-migration-plan.md

docs/cloud-migration-manifest.md

docs/local-release-checklist.md

docs/local-architecture.md

docs/decisions.md if appropriate

.env.example

bootstrap/reset tooling

acceptance test tooling

CI-friendly test entry point

local release report generation

---

# 47. Final Report

At completion report:

1. Phase 01–05 verification status
2. configuration issues found
3. hardcoded environment dependencies removed
4. storage abstraction readiness
5. containerization changes
6. dependency/version compatibility state
7. bootstrap workflow
8. reset workflow
9. E2E acceptance workflow
10. rebuild test results
11. health check results
12. security/secret audit result
13. local resource baseline
14. local-to-cloud component mapping
15. ADLS readiness findings
16. Kubernetes readiness findings
17. migration manifest summary
18. files created
19. files modified
20. commands added
21. tests executed
22. actual test results
23. regressions fixed
24. remaining limitations
25. whether local system qualifies as READY FOR CLOUD MIGRATION
26. exact commands for clean reproduction
27. recommended Phase 07 migration sequence
28. git status
29. recommended commit message

Update:

docs/agent_tasks/CURRENT_STATUS.md

at the end.

Do not claim READY FOR CLOUD MIGRATION if required acceptance tests fail.

STOP after Phase 06.

Do NOT provision or migrate to cloud.
