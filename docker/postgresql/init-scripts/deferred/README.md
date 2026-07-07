# Deferred PostgreSQL Init Scripts

These scripts are intentionally not mounted into the local PostgreSQL container during scraper local setup.

Current local setup mounts only:

```text
docker/postgresql/init-scripts/001-create-scraper-schema.sql
```

The files in this folder are kept for reference and can be reviewed/re-enabled later if the RAG metadata schema or utility views are needed again.
