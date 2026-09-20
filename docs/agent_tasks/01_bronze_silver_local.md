
The source of truth for data schemas and mappings is:

- docs/data-contracts.md
- artifacts/data-profile.json

Read both before implementing anything.

Do not invent source fields that are not documented there.

Implement the canonical schema defined in docs/data-contracts.md.
Do not redesign or silently modify the canonical contract.

If the implementation reveals a mismatch between the actual data and the contract:

1. stop the affected implementation,
2. report the mismatch,
3. explain its impact,
4. propose a contract change,
5. wait for approval before changing the canonical contract.

Now implement the first local vertical slice.

Scope ONLY:

existing repository sample news data
    ->
Bronze ingestion
    ->
MinIO Bronze
    ->
PySpark transformation
    ->
Delta Lake Silver on MinIO

Do NOT implement yet:

- crawler
- Airflow
- Debezium
- Kafka
- Kubernetes
- embeddings
- Qdrant
- Power BI
- frontend

Requirements:

1. Reuse existing repository code where appropriate.
2. Add Docker Compose MinIO only if the repository does not already contain
   equivalent object storage.
3. Create a configurable storage abstraction.
4. Create a canonical article schema.
5. Implement sample-data ingestion into Bronze.
6. Implement a real PySpark Bronze-to-Silver job.
7. Silver processing must include:
   - schema enforcement
   - HTML/boilerplate cleaning where applicable
   - Unicode normalization
   - whitespace normalization
   - timestamp normalization
   - canonical URL handling
   - content hashing
   - deduplication
   - malformed-record handling
8. Write Silver output as Delta Lake stored on MinIO.
9. Add metrics:
   - input count
   - output count
   - invalid count
   - duplicate count
   - processing duration
10. Add unit tests.
11. Add one integration test using the repository sample data.
12. Add Makefile commands:

make infra-up
make bronze-ingest
make silver-build
make test-pipeline

13. Update documentation with exact commands to inspect:
    - Bronze objects
    - Silver Delta table
    - processing metrics

Before modifying a file, inspect its current implementation.

At the end, show:

- files changed
- architecture implemented
- commands to run
- tests executed and their results
- remaining work

Do not continue to Gold until this vertical slice works.
