# Local release checklist — `local-rc1`

The boxes below are release gates. Evidence is regenerated with
`make phase6-acceptance`; volatile JSON reports are ignored by Git.

## Configuration and security

- [x] Local, test, and future-cloud templates parse and validate.
- [x] Required object/provider settings fail early with clear errors.
- [x] Runtime transformations contain no developer-specific absolute path.
- [x] Runtime services use configuration rather than static container IPs.
- [x] `.env` is removed from tracking and ignored; `.env.example` has placeholders only.
- [x] Current runtime/configuration tree contains no detected credential pattern.
- [ ] Historical `.env` credentials are revoked/rotated and Git history is remediated.
- [x] Important image/package versions are pinned and checked against the manifest.

## Data plane

- [x] Bronze preserves fixture bytes and SHA-256 identity.
- [x] Silver validation, cleaning, normalization, rejection, and deduplication pass.
- [x] Gold RAG documents/chunks build from Silver.
- [x] Gold Analytics builds from Silver and publishes a manifest.
- [x] Qdrant indexing and semantic retrieval pass.
- [x] DuckDB tables and analytical query pass.
- [x] Gold can be rebuilt from Silver in an isolated namespace.
- [x] Qdrant can be deleted and rebuilt from Gold RAG.
- [x] DuckDB can be deleted and rebuilt from Gold Analytics.

## Orchestration and control plane

- [x] Airflow DAG import/structure tests pass with zero import errors.
- [x] PostgreSQL metadata and pipeline operations migrations are idempotent.
- [x] Kafka metadata topics are initialized.
- [x] Debezium connector and task reach `RUNNING`.
- [x] CDC snapshot, stable key, update before/after, delete, and tombstone pass.
- [x] Debezium, Kafka outage, and PostgreSQL restart recovery pass.

## Operations

- [x] Incremental insertion and unchanged-record behavior pass.
- [x] Same-input replay has zero affected articles.
- [x] Explicit reprocess, backfill, resume, and checkpoint behavior pass.
- [x] Schema drift fails before Bronze.
- [x] Cross-layer reconciliation and health checks pass.
- [x] `make bootstrap` succeeds from the controlled destructive reset and reruns safely.
- [x] Soft stop, serving reset, and explicit destructive reset commands are documented.

## Documentation and migration

- [x] README contains bootstrap, pipeline, Airflow, CDC, operations, acceptance, and rebuild commands.
- [x] Actual local architecture is labeled separately from future targets.
- [x] Local resource/timing baseline is recorded.
- [x] Local-to-cloud component mapping and ADLS checklist exist.
- [x] Kubernetes workload/state/readiness inventory exists without manifests.
- [x] Migration manifest includes data, config, code impact, validation, and rollback.
- [x] Phase 07 sequence is documented and no cloud resource has been provisioned.

## Verdict

**Current verdict: `NOT READY`** because likely credentials remain in Git history.
All other boxes must remain green after that remediation.

`READY FOR CLOUD MIGRATION` means ready to start the controlled Phase 07 adapter
and deployment work. It does not mean production ready. The final verdict must
match `artifacts/local-release-report.json` and `CURRENT_STATUS.md` after the
acceptance command completes.
