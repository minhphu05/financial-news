# Phase 02: Silver to Gold and local serving

This phase runs independently after the Phase 01 Bronze/Silver jobs. The input is the committed Silver Delta tables for the final CafeF snapshot. The output has two branches:

```text
Silver articles + article_mentions (Delta in MinIO)
  ├─ no-op enrichment → Gold documents + deterministic chunks (Delta in MinIO)
  │                       → FastEmbed local model → Qdrant → semantic search
  └─ Spark aggregations → Gold Parquet + manifest (MinIO)
                          → local analytics.duckdb → SQL query
```

The canonical field contract is [data-contracts.md](data-contracts.md). The current `stock_symbols` array is assembled from Silver `article_mentions.ticker_symbol`: these are **search ticker associations**, not confirmed text mentions or NER output. `entities` is null, `enrichment_status` is `unavailable`, and no financial events are inferred. The source `keyword` is not an editorial category.

## Run the local slice

From the repository root, with Docker Compose available:

```bash
make infra-up
make bronze-ingest
make silver-build
make test-pipeline
make gold-build
make analytics-build
make analytics-query QUERY='SELECT * FROM vw_news_by_source'
make qdrant-index INDEX_LIMIT=96
make semantic-search QUERY='Masan sử dụng dòng vốn hiệu quả'
make retrieval-smoke
make test-gold
```

`INDEX_LIMIT=96` makes a small real-model demonstration over the first 96 chunks ordered by `article_id, chunk_index`. Use `make qdrant-index` (default limit 0) to index every Gold chunk. Indexing the full sample requires substantially more local CPU time and vector storage. Repeating either command upserts the same point IDs and reconciles stale points **within the dedicated collection**. The smoke fixture at [gold_retrieval_queries.json](../tests/fixtures/gold_retrieval_queries.json) expects the first 96 chunks. Its actual top-5 results are saved to [gold-retrieval-smoke-results.json](../artifacts/gold-retrieval-smoke-results.json) by `make retrieval-smoke`.

The first FastEmbed run downloads multilingual MiniLM ONNX model weights into the persistent `news_model_cache` Docker volume. This is the **real local demo embedding provider** (384 dimensions); tests use a separate deterministic hash provider solely to verify indexing mechanics. No paid API credentials are required. Qdrant was already defined in Compose, using persistent `qdrant_data`; Phase 02 reuses it.

## Storage and configuration

The default input snapshot is `data/raw/cafef_news_raw_final.json`. Its SHA-256 is the `source_ingestion_id`; for the current checked-in snapshot it is `e374c2b68641e6695fe87227c654bac6ad483d03238ff118d9741976c9642d07`. `NEWS_SOURCE_INGESTION_ID` can select a different imported snapshot explicitly. The output prefix includes source, ingestion ID, Silver processing version, and for RAG the chunker version:

| Asset | Default location |
|---|---|
| Silver articles | `s3a://financial-news/silver/cafef.vn/<ingestion_id>/cafef-v1.1/articles` |
| Silver associations | `s3a://financial-news/silver/cafef.vn/<ingestion_id>/cafef-v1.1/article_mentions` |
| Gold documents | `s3a://financial-news/gold/rag/cafef.vn/<ingestion_id>/cafef-v1.1/sentence-v1-900-120/documents` |
| Gold chunks | Same RAG prefix plus `/chunks` |
| Gold RAG metrics | Same RAG prefix plus `/metrics.json` and `/qdrant_metrics.json` |
| Gold analytics | `s3a://financial-news/gold/analytics/cafef.vn/<ingestion_id>/cafef-v1.1/{news_daily,news_by_source,news_publication_status}` |
| Gold analytics manifest and metrics | Same analytics prefix plus `/manifest.json`, `/metrics.json`, `/duckdb_metrics.json` |
| Qdrant | `news_chunks_local_v1` at `NEWS_QDRANT_URL` (default Compose `http://qdrant:6333`) |
| DuckDB | `data/local/analytics.duckdb` on the host, `/app/local/analytics.duckdb` in the container |

`NEWS_STORAGE_*` and `NEWS_STORAGE_BUCKET` configure MinIO/S3 access in the existing storage adapter. `NEWS_SILVER_ARTICLES_URI`, `NEWS_SILVER_MENTIONS_URI`, `NEWS_GOLD_RAG_PREFIX`, and `NEWS_GOLD_ANALYTICS_PREFIX` configure dataset locations. `NEWS_CHUNK_SIZE` (default 900 characters) and `NEWS_CHUNK_OVERLAP` (default 120 characters) configure deterministic, sentence-preferred chunking. The chunk ID hashes article ID, content hash, chunker version, and position. `NEWS_EMBEDDING_PROVIDER`, `NEWS_EMBEDDING_MODEL`, `NEWS_EMBEDDING_DIMENSION`, `NEWS_QDRANT_URL`, `NEWS_QDRANT_COLLECTION`, `NEWS_INDEX_BATCH_SIZE`, and `NEWS_DUCKDB_PATH` configure the serving jobs. The local provider currently accepts `NEWS_EMBEDDING_PROVIDER=fastembed`; another provider can implement the `EmbeddingProvider` interface without changing Gold transformations.

The local `data/local` bind mount can be created by Docker with root ownership. The `analytics-build` target invokes only its DuckDB publish step as container root so it can atomically write this file. Queries run as the normal container user. `retrieval-smoke` uses the same approach to write a local result, then copies it into `artifacts/`.

## Inspect output and metrics

```bash
docker compose run --rm news-pipeline /opt/spark/bin/spark-submit \
  --packages io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4 \
  --conf spark.jars.ivy=/opt/news-ivy /app/src/news_pipeline/inspect_gold.py rag
docker compose run --rm news-pipeline /opt/spark/bin/spark-submit \
  --packages io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4 \
  --conf spark.jars.ivy=/opt/news-ivy /app/src/news_pipeline/inspect_gold.py analytics
docker compose run --rm news-pipeline python3 -m src.news_pipeline.inspect_gold metrics
make analytics-query QUERY='SELECT publication_status, SUM(article_count) FROM vw_news_publication_status GROUP BY 1'
```

The RAG metrics record Silver article count, Gold document/chunk counts, average chunks per article, empty article/chunk count, and duration. Qdrant metrics record input, embedded, indexed, failed, reconciled, and current point counts plus duration and model identity. Analytics metrics record input articles, row counts by dataset, and duration. The DuckDB publish metrics record validated row counts and duration.

`vw_news_daily` groups by source and publication date in `Asia/Ho_Chi_Minh`, with article count and mean content characters. `vw_news_by_source` reports total, parsed-date, unparsed-date counts and mean content characters. `vw_news_publication_status` reports counts by source and parsed-date status. Gold analytics is materialized in MinIO before DuckDB copies the committed Parquet objects listed in its manifest into local tables/views. DuckDB is a rebuildable serving file.

## Current limits

- The provided snapshot contains only CafeF articles. The default local collection currently demonstrates a bounded index; Gold contains all accepted sample chunks.
- Source publication strings that Phase 01 cannot parse remain null. Daily analytics excludes those articles while source and publication-status totals include them.
- No production NER, confirmed entity extraction, category dimension, LLM answer generation, Airflow, or cloud deployment is included in this phase.
- A collection belongs to one Gold chunk/model projection. The index job reconciles that whole collection; use a separate collection for another dataset or model.
- Run Gold builds, index updates, and DuckDB publication serially for now; a job registry and concurrent publish locking are outside Phase 02.
