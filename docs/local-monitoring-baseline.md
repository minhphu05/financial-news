# Local monitoring baseline

This document records the Phase 07 measurements captured on 2026-10-01 local
time. They are descriptive observations from a development machine with warm
Docker and model caches. Eight operational samples are too few for a capacity
claim, percentile target, or production SLA.

## Environment and dataset

- Host: 20 logical CPUs, 15.32 GiB RAM.
- Spark master: `local[2]`.
- Phase 06 stable acceptance input: two fixture files, 2,930 bytes total.
- Phase 07 samples: isolated `phase07-monitoring.local` source, unique storage
  namespace, Qdrant collection and DuckDB file.
- Phase 07 normal samples retained in PostgreSQL: 8.
- Prometheus retention: 7 days by default.

## Stable Phase 06 acceptance result

| Observation | Result |
|---|---:|
| End-to-end E2E | 102.832 s |
| Silver articles | 3 |
| Gold documents | 3 |
| Gold chunks | 3 |
| Qdrant points | 3 |
| DuckDB articles | 3 |
| Missing/orphan/stale reconciliation counts | 0 |
| Gold rebuild from Silver | 4.622 s |
| Qdrant rebuild from Gold RAG | 4.413 s |
| Gold Analytics rebuild | 3.576 s |
| DuckDB rebuild from Gold Analytics | 0.042 s |

The E2E duration includes service checks, Spark startup and the rebuild proof;
it should not be compared directly with a single Phase 07 incremental run.

## Phase 07 operational runs

| Measurement | Samples | Minimum | Mean | Maximum |
|---|---:|---:|---:|---:|
| End-to-end run | 8 | 39.129 s | 44.147 s | 47.058 s |
| Bronze ingest | 8 | 0.014 s | 0.017 s | 0.029 s |
| Silver merge | 8 | 15.461 s | 25.590 s | 31.484 s |
| Gold RAG merge | 8 | 4.724 s | 5.412 s | 6.910 s |
| Gold Analytics refresh | 8 | 3.995 s | 4.161 s | 4.396 s |
| Qdrant upsert | 8 | 0.789 s | 1.729 s | 3.333 s |
| DuckDB publish | 8 | 1.255 s | 1.305 s | 1.354 s |
| Reconciliation | 8 | 2.149 s | 2.325 s | 2.482 s |
| Schema validation | 8 | 0.000 s | 0.000 s | 0.000 s |

The monitored normal fixture contributes one input and one output observation
per isolated run. Current Prometheus record series also include four Gold
documents/chunks/Qdrant points from the controlled Phase 07 scenario namespace.
Record gauges describe the latest matching stage observation, not cumulative
business volume.

## Resource snapshot

| Observation | Value |
|---|---:|
| Host CPU used ratio | 0.2105 |
| Host memory used | 9,299,369,984 bytes (8.66 GiB) |

This is one scrape-time observation, not an average over a complete run. On the
verified Docker/cgroup-v2 setup, cAdvisor did not attach stable Compose
container-name labels, so a credible per-service CPU/memory breakdown was not
available. The dashboard uses node exporter for host metrics and keeps cAdvisor
scraping available for hosts that expose useful container labels.

## Failure and recovery observations

The successful acceptance run produced these measurements:

- Two explicit normal executions completed in 45.508 s and 51.460 s.
- The malformed-fixture run completed in 55.538 s, recorded one invalid row,
  and fired `DataQualityGateFailed` according to the existing reject policy.
- With Qdrant stopped, the run failed after 52.516 s; the failed-stage counter
  increased from 2 to 3 and the pipeline failure alert fired.
- Resuming the same run after Qdrant recovery completed in 29.197 s; the Qdrant
  service alert resolved.
- Pausing Debezium made connector health and its alert fail while Kafka and
  PostgreSQL stayed healthy; resuming the connector restored health and cleared
  the alert.

## How to regenerate

```bash
cp .env.example .env
# Replace local password placeholders.
make monitoring-up
make monitoring-baseline
make phase7-acceptance
```

Generated machine-readable evidence:

- `artifacts/phase7-monitoring-baseline.json`
- `artifacts/phase7-acceptance.json`
- `artifacts/phase7-monitoring-checks.json`

These files are runtime evidence and are ignored by Git. A new baseline should
record host resources, code revision, cache state, fixture identity and sample
count before comparing results.
