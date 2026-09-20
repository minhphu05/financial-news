# Local Bronze → Silver news pipeline

This slice imports `data/raw/cafef_news_raw_final.json` (15,457 CafeF export observations). It stores the exact source bytes and a manifest in MinIO Bronze, then uses PySpark to produce three Delta tables on MinIO: canonical `articles`, `article_mentions`, and `rejects`. `metrics.json` is written after all three Delta writes succeed. No crawler or downstream Gold job runs here.

## Run

From the repository root, with Docker Compose available:

```bash
make infra-up
make bronze-ingest
make silver-build
make test-pipeline
```

`make silver-build` requires Bronze ingestion first. `make test-pipeline` runs four fast unit tests and an end-to-end sample test that ingests Bronze and reads back all three Delta tables. The first Spark run downloads pinned Delta 3.2.1 and Hadoop AWS 3.3.4 jars into a persistent Ivy volume. Spark runs in local mode inside a Docker container; MinIO persists in the `news_minio_data` Compose volume. The MinIO S3 API is at `http://localhost:9000` and its console at `http://localhost:9001` (default local credentials: `minioadmin` / `minioadmin`).

## Inspect stored results

These commands use the same configured storage adapter and selected source snapshot as the jobs:

```bash
docker compose run --rm news-pipeline python3 -m src.news_pipeline.inspect_pipeline bronze
docker compose run --rm news-pipeline python3 -m src.news_pipeline.inspect_pipeline metrics
docker compose run --rm news-pipeline /opt/spark/bin/spark-submit --packages io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4 --conf spark.jars.ivy=/opt/news-ivy /app/src/news_pipeline/inspect_pipeline.py silver
```

Bronze keys are `bronze/cafef.vn/<source-file-sha256>/raw.json` and `manifest.json`. Silver keys are under `silver/cafef.vn/<source-file-sha256>/cafef-v1.1/`. The inspection command displays row counts, columns, and two rows from each Delta table. The metrics file reports input, output, invalid, duplicate, shared-content-hash groups, mention counts, and processing duration. The processing version includes the lineage schema revision; the canonical article contract remains version 1.

## Contract and behavior

The canonical article columns come directly from [data-contracts.md](data-contracts.md#6-proposed-canonical-silver-article-contract). Article identity is SHA-256 of `source` plus normalized URL, so repeated URL observations become one article. Distinct `(article_id, ticker_symbol, keyword)` associations remain in `article_mentions`, with both the original export `index` (`source_index`) and the JSON array offset (`source_row_position`). Blank/null bodies, invalid required fields, or invalid URLs go to `rejects` with ingestion ID, row position, original index when available, and reason. Source JSON and Mongo `_id` remain unchanged in Bronze. Unverified export metadata do not become publication or crawl time.

URL normalization lowercases scheme and host, removes fragments, default ports, and trailing path slashes, while preserving the path and query. Text cleaning decodes HTML entities, strips HTML tags where present, normalizes Unicode to NFC, removes standalone CafeF footer lines, and collapses whitespace. Only standard 12-hour CafeF `post date` values are parsed in `Asia/Ho_Chi_Minh`; nonstandard 24-hour-plus-meridiem strings retain `published_at_raw` and have null `published_at`.

`NEWS_STORAGE_ENDPOINT`, `NEWS_STORAGE_ACCESS_KEY`, `NEWS_STORAGE_SECRET_KEY`, `NEWS_STORAGE_BUCKET`, `NEWS_SOURCE_FILE`, `NEWS_PROCESSING_VERSION`, and `NEWS_SPARK_MASTER` configure access and job behavior. MinIO is an S3-compatible adapter; transformations have no MinIO-specific logic. For another S3 endpoint, set those environment variables in Compose or shell. Keep a single Spark driver writing a given Delta table path at a time.
