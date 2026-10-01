# Platform metrics exporter

The `platform-metrics-exporter` Compose service runs
`src.monitoring.exporter`. It reads Phase 05 run and stage metadata in a
read-only PostgreSQL session, probes bounded service health endpoints, and
exports low-cardinality metrics on port `9108`.

The exporter never uses `run_id`, article IDs, chunk IDs, URLs, or error text as
Prometheus labels. PostgreSQL provisioning creates the dedicated
`monitoring_exporter` login with `pg_monitor` plus `SELECT` access only.
