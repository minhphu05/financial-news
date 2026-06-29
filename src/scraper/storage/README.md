# Scraper Storage

`storage/` contains all persistence-related code for scraper runs.

## Files

- `models.py`: SQLAlchemy ORM mappings for scraper tables.
- `repository.py`: PostgreSQL metadata repository.
- `inputs.py`: keyword providers, currently from PostgreSQL.
- `adls_writer.py`: ADLS and MinIO content writers plus writer factory.

## What Goes Where

PostgreSQL stores metadata:

- Stocks and index memberships.
- Keywords.
- Sources.
- Crawl jobs and crawl logs.
- Article metadata and article-stock links.

ADLS or MinIO stores content:

- Full article JSON.
- Downloaded images.
- Ordered text/image blocks.

## Backend Selection

Default:

```text
CONTENT_STORAGE_BACKEND=adls
```

Local MinIO:

```text
CONTENT_STORAGE_BACKEND=minio
```

Per-run override:

```bash
python -m src.scraper.run --ticket ACB --source cafef --content-storage-backend minio
```

Prefect UI parameter:

```json
{
  "content_storage_backend": "minio"
}
```

## Local Docker Endpoints

When running inside Docker Compose:

```text
METADATA_POSTGRES_HOST_EXTERNAL=postgresql
METADATA_POSTGRES_EXTERNAL_PORT=5432
MINIO_ENDPOINT=minio:9000
```

When running from host:

```text
METADATA_POSTGRES_HOST_EXTERNAL=localhost
METADATA_POSTGRES_EXTERNAL_PORT=5434
MINIO_ENDPOINT=localhost:9000
```

## Safety Rule

Never point a local MinIO run at production ADLS credentials. Keep `content_storage_backend=minio` for local runs and `adls` for production runs.
