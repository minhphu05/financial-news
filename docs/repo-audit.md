# Financial-news pipeline repository audit

**Audit date:** 2026-09-20. **Scope:** repository at `development` / `037038a`, including the existing sample data, application code, Docker configuration, tests, and documentation. This is a static audit plus read-only data profiling and `docker compose config --quiet`; it does not claim that a pipeline or container has run successfully. Existing working-tree changes were left alone.

## What exists today

The operational design in this repository is a CafeF scraper feeding PostgreSQL metadata and MongoDB article bodies, followed by Python cleaning, chunking, Voyage AI embeddings, and Qdrant. Prefect schedules the combined scrape/ingest path; FastAPI and React serve news and chat. A separate `src/model/` tree contains ViFinNER research and labeled data. The requested **local batch lakehouse** (MinIO, Spark, Delta Lake, DuckDB) does not yet exist. The architecture diagram and thesis proposal describe a **target**, not a deployed state. The requested work starts with the files already under `data/`; crawling is outside this implementation phase.

Repository map:

| Area | Contents |
|---|---|
| `data/raw/` | Three CafeF JSON snapshots, `news_titles.jsonl`, and `vn30.xlsx` lookup data. |
| `data/labeled/`, `data/eval/` | NER/span research artifacts and 35 RAG evaluation questions. |
| `src/scraper/` | Current crawler, parsers, HTTP client, SQLAlchemy models, PostgreSQL/Mongo persistence. |
| `src/pipeline/`, `src/rag/ingestion/` | Two Python ingestion paths; cleaning, chunking, embedding. |
| `src/model/preprocessing/medallion/` | Earlier Polars/Mongo/PGVector medallion attempt. |
| `src/rag/databases/`, `src/rag/config/` | Mongo, Qdrant, legacy PGVector adapters and runtime settings. |
| `src/flows/`, `src/rag/flows/` | Newer and older Prefect flows. |
| `src/rag/api/`, `src/rag/retrieval/`, `frontend/` | RAG serving, search, and UI. |
| `src/model/` | NER annotation, training, exploratory notebooks, and research code. |
| `docker/`, `docker-compose.yml` | Existing application, data stores, Prefect, and observability containers. |
| `scripts/`, `Makefile`, `tests/`, `docs/` | Entry points, tests, and operational/research documents. |

## Existing data: actual source and shape

All inspected article URLs in the largest snapshot point to **`cafef.vn`**. There is no second news publisher in these raw files. `vn30.xlsx` is a 30-company ticker/keyword lookup, not another news feed. The NER and RAG evaluation files are derived/ancillary datasets, not additional Bronze news inputs.

| File | Rows | Distinct article URLs | Interpretation |
|---|---:|---:|---|
| `data/raw/cafeF_news.json` | 11,242 | 9,236 | Earlier CafeF export without `title`. |
| `data/raw/cafef_news_raw.json` | 11,242 | 9,236 | Earlier export with `title`. |
| `data/raw/cafef_news_raw_final.json` | 15,457 | 12,698 | Largest available snapshot; **candidate canonical local seed**. |
| `data/raw/news_titles.jsonl` | 11,242 | 9,236 | Title derivative of the earlier export. |
| `data/raw/vn30.xlsx` | 30 companies | — | Columns: `ticket_symbol`, `company_name_vi`, `company_name_en`, `Keywords`. |

The 9,236 URLs in each earlier JSON are all present in the final JSON. Do **not** ingest these files as independent batches and sum their counts. In the final JSON, 2,042 URLs occur more than once, producing 2,759 rows beyond one row per URL. Among these groups, 1,159 have multiple ticker values and 2,041 have multiple keyword values; article deduplication must retain those observations in a separate relation or array. There are 25 rows with null or blank/whitespace `context` (2 null and 23 blank strings); 17 of these are null or exactly empty strings. The final snapshot has 30 ticker values and 90 keyword values; these counts describe fields in the file, not confirmed distinct securities or search terms after normalization.

Raw JSON is an array of records with top-level `_id`, `link`, `title`, `post date`, `summary`, `context`, `ticket symbol`, `ticket name`, `keyword`, `page`, and `index`. `metadata` is a **nested** object holding `Date` and `Time` from the export. Fields with spaces and the source typo `ticket` need explicit mapping; there is no top-level `source`. `_id` is an export document ID, not a durable article key. `post date` is free-form text such as `02-02-2026 - 07:32 AM`; at least one record uses `16:44 PM`. Keep the original string, parse conservatively, and capture failures rather than silently inventing a timestamp or timezone. The source can be derived from the URL host, with a verified allowlist. URL identity should be canonicalized explicitly, then paired with source (CafeF URL numeric ID is a possible secondary key).

Other data: `data/labeled/ner/raw/output_ner.jsonl` has 59,175 rows; the final NER train/dev/test splits contain 36,750/7,890/7,852 samples. `data/labeled/span_tags/3_EVENT_clean.json` has 62,391 rows; `data/labeled/span/` has 10,247 JSON files. These may later feed the enrichment hook, but they are not part of the initial news Bronze seed. `data/eval/rag_eval.jsonl` contains 35 questions for downstream evaluation. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the broader thesis/research context.

## Existing processing and schemas

| Path | Current input → output | Audit finding |
|---|---|---|
| `src/scraper/` | CafeF HTML → PostgreSQL `news_articles`, `scrape_runs`, `scrape_progress` + Mongo article bodies | Designed for future collection; not needed to process existing local files. |
| `src/pipeline/core.py` | Explicit scraped IDs → Mongo raw/clean → cleaner/chunker/Voyage → Qdrant | Clear stage boundaries, but tied to Mongo and direct vector writes; no durable Silver/Gold. |
| `src/rag/ingestion/pipeline.py` | Mongo backlog scans → Mongo clean → Qdrant | Duplicates the core ingestion path and uses a different discovery mechanism. |
| `src/model/preprocessing/medallion/` | Mongo → Polars Bronze/Silver → PGVector Gold | Prototype is not the requested storage path. Imports refer to missing `src.preprocessing`; Gold references `GeminiEmbedder` and PGVector exports that are unavailable. Reuse cleaning/dedup rules as test cases, not its runtime assumptions. |
| `src/rag/ingestion/cleaner.py` | Flat scraper dict → cleaned flat dict | Useful NFC, whitespace and boilerplate rules; does not read the nested/raw spaced-field JSON schema directly. |
| `src/rag/ingestion/chunker.py` | Clean text → ordered, overlapping chunks | Reusable pure splitting logic; configuration is currently coupled to RAG settings. |
| `src/rag/quality/validators.py` | Flat scraped article → Pydantic validation/rejections | `ScrapedArticleV1` requires flat `link/title/context`; currently described as a Mongo Bronze gate. It cannot validate the raw export as-is and should not discard immutable Bronze records. |
| `src/rag/databases/qdrant_client.py` | Embedded chunks → vector points | Existing adapter and payload. Point ID is URL plus chunk index; version/content changes need a stronger identity and stale-point cleanup. |

The current PostgreSQL ORM schema in `src/scraper/models.py` is crawler metadata: `news_articles` keyed by `news_id`, `scrape_runs`, and `scrape_progress`. `news_articles.content_ref` points to MongoDB. `docker/postgresql/init-scripts/001-create-schema.sql` instead defines a different `rag_metadata` schema (`articles`, `embeddings`, `ner_labels`, `extraction_spans`, `processing_events`, `datasets`, `dataset_members`, `user_activity`). The SQL scripts are **not installed by the current Dockerfile or Compose mount**. Neither schema is a verified Silver/Gold contract. Mongo raw/clean collections and Qdrant payloads are schemaless documents; the API response models in `src/rag/api/schemas.py` assume flat fields and `post_date: str`. The proposed contracts are in [local-architecture.md](local-architecture.md).

## Runtime and dependency inventory

`docker-compose.yml` validates syntactically and defines 18 services. Present: two PostgreSQL services (one for Prefect, one for metadata), MongoDB, Qdrant, Redis, Prefect server/services/worker, FastAPI, frontend, MLflow, Loki, Fluent Bit, Grafana, Prometheus, Pushgateway, cAdvisor, and node-exporter. Its worker runs `python -m src.flows.deploy`; `make deploy` invokes the older `src.rag.flows.deploy`. The metadata PostgreSQL initialization script mount and Dockerfile copy are commented out. No MinIO, Spark, Airflow, Kafka, Delta Lake, DuckDB, or Flink service/job/dependency was found. `requirements.txt` includes Polars/PyArrow and Prefect, but no PySpark/Delta/S3/DuckDB packages. Docker Compose validation does not establish that services can start or exchange data.

## Component disposition for the **local news pipeline**

Each existing component group below has one disposition. **KEEP** means preserve and use as-is where relevant; **REFACTOR** means retain useful logic but change its boundary/contract; **REPLACE** means retire its current role in this pipeline after a working replacement exists; **UNUSED FOR NOW** means preserve it outside this local phase. These labels do not authorize deletion.

| Existing component | Disposition | Reason / intended handling |
|---|---|---|
| `data/raw/cafef_news_raw_final.json` | KEEP | Immutable primary seed; record checksum and batch identity. |
| `data/raw/cafeF_news.json`, `cafef_news_raw.json`, `news_titles.jsonl` | UNUSED FOR NOW | Overlapping/derived snapshots; retain for lineage or regression checks. |
| `data/raw/vn30.xlsx` | KEEP | Optional ticker reference with its own schema/version, not news content. |
| `data/labeled/`, `data/eval/` | UNUSED FOR NOW | Research/evaluation inputs for later enrichment and serving checks. |
| `src/scraper/` and `src/rag/ingestion/http_utils.py` | UNUSED FOR NOW | No crawling in this phase; preserve working collection capability. |
| `src/rag/ingestion/daily_scraper.py` | REPLACE | Older second crawler path; consolidate only when collection is resumed. |
| `src/pipeline/core.py` | REFACTOR | Retain explicit stage/report pattern; remove Mongo/Qdrant coupling from transformation jobs. |
| `src/rag/ingestion/pipeline.py` | REPLACE | Duplicated backlog ingest; new file-to-lake jobs become canonical. |
| `src/model/preprocessing/medallion/` | REPLACE | Broken imports and Polars/Mongo/PGVector storage; extract useful normalization/dedup examples into Spark contract tests. |
| `src/rag/ingestion/cleaner.py` | REFACTOR | Preserve tested text rules; adapt raw field mapping and Spark execution. |
| `src/rag/ingestion/chunker.py` | REFACTOR | Preserve tested splitter; expose explicit parameters/version and deterministic output. |
| `src/rag/ingestion/{metrics,pipeline_logger}.py` | REFACTOR | Reuse logging/counter patterns with job run IDs and stage counts; current labels assume the old ingest path. |
| `src/rag/quality/validators.py` | REFACTOR | Apply after raw capture with export-aware mapping; retain rejects and reasons. |
| `src/rag/ingestion/embedder.py` | KEEP | Existing Voyage adapter is usable as an optional, credentialed vectorization backend. |
| `src/rag/databases/qdrant_client.py` | REFACTOR | Keep Qdrant adapter; align payload/point identity with Gold versioned chunks. |
| `src/rag/databases/mongo_client.py` and Compose `mongodb` | UNUSED FOR NOW | Existing API/crawler dependency; not a required lakehouse store. |
| `src/rag/databases/pgvector_client.py` | REPLACE | Legacy vector path conflicts with Qdrant target and current exports. |
| `src/rag/config/settings.py`, `src/scraper/config.py` | REFACTOR | Add explicit storage/job settings at boundaries; avoid requiring crawler/API settings to run batch jobs. |
| `src/flows/`, `src/rag/flows/`, Prefect services and their PostgreSQL/Redis | UNUSED FOR NOW | Keep historical orchestration; add Airflow only after standalone jobs pass. Older flow tree duplicates the newer one. |
| Compose `postgresql`, `docker/postgresql/Dockerfile` | REFACTOR | Keep local PostgreSQL for control metadata; simplify configuration and define a new job-run schema. |
| `docker/postgresql/init-scripts/` | UNUSED FOR NOW | Draft schema is not mounted and is not a pipeline contract. |
| Compose `qdrant` | KEEP | Local semantic index service already configured with persistence. |
| `src/rag/retrieval/`, `src/rag/agent/`, `src/rag/api/`, `frontend/` | UNUSED FOR NOW | Downstream consumers; adapt once Gold/Qdrant/DuckDB outputs are stable. |
| `src/rag/caching/`, `src/rag/evaluation/`, `src/rag/mlops/` | UNUSED FOR NOW | Serving/evaluation/experiment concerns, outside first batch path. |
| `src/rag/lib/`, `src/rag/utils/`, `src/utils/` | KEEP | Lookup and logging helpers, subject to normal tests when reused. |
| `src/model/` outside its medallion folder | UNUSED FOR NOW | NER research; potential enrichment adapter later, no pipeline dependency now. |
| `.env.example`, `frontend/.env.example`, `.dockerignore` | REFACTOR | Update only when the local pipeline runtime is implemented; keep actual `.env` and nested research credentials out of documentation and commits. |
| `AGENTS.md` | KEEP | Current local-first scope and implementation priority for contributors. |
| `scripts/`, `Makefile` | REFACTOR | Several entries import missing Gemini/PGVector/`src.rag_langchain`; add accurate local job commands only when jobs exist. |
| `docker/ingestion/`, `docker/api/`, `docker/frontend/`, `docker/mlflow/` | UNUSED FOR NOW | Existing app/Prefect images; avoid rebuilding them to start the minimal batch stack. |
| Compose observability services and `docker/{fluent-bit,grafana,loki,prometheus}/` | UNUSED FOR NOW | Useful later; local batch jobs first need simple logs/counters. |
| `tests/unit/rag/` cleaner/chunker/Qdrant-related tests | KEEP | Reuse as behavior reference; add tests for new contracts and integration boundaries. |
| `tests/unit/scraper/`, `tests/unit/flows/`, `tests/automation/`, `src/model/tests/` | UNUSED FOR NOW | Preserve tests for their respective components. |
| Existing `docs/`, root guides, `frontend/README.md` | REFACTOR | Keep as historical/current-component documentation; annotate or update runnable instructions when implementation changes. |
| `logs/`, `images/`, bytecode caches | UNUSED FOR NOW | Operational artifacts, illustration, and generated files; no pipeline input. |
| `requirements.txt`, `docker-compose.yml` | REFACTOR | Current dependency/stack definitions do not contain the local target; evolve incrementally with reproducible version checks. |

Compose service disposition, stated individually so the proposed minimal stack is unambiguous:

| Existing service | Disposition | Local pipeline role |
|---|---|---|
| `qdrant` | KEEP | Reuse local semantic index after Gold exists. |
| `postgresql` | REFACTOR | Reuse local database for run/publication metadata. |
| `mongodb` | UNUSED FOR NOW | Needed by old crawler/API, not by the new lakehouse jobs. |
| `postgresql-prefect`, `redis-prefect`, `prefect-server`, `prefect-services`, `prefect-worker` | UNUSED FOR NOW | Existing Prefect stack; no orchestration in the first job milestones. |
| `api`, `frontend` | UNUSED FOR NOW | Existing consumers; integration follows stable Gold contracts. |
| `mlflow` | UNUSED FOR NOW | Experiment tracking is optional for initial batch correctness. |
| `loki`, `fluent-bit`, `grafana`, `prometheus`, `pushgateway`, `cadvisor`, `node-exporter` | UNUSED FOR NOW | Existing observability stack; local jobs first expose logs and reconciliation counts. |

## Main gaps and cautions

1. There is no independent Bronze seed job, Spark Silver job, Delta transaction log, Gold dataset, DuckDB serving build, or enrichment hook. Existing Qdrant is a serving projection only.
2. The raw export and live scraper use different field names/shapes. An explicit source adapter must normalize the raw schema before generic validation; preserve original records and bad-row diagnostics.
3. URL dedup alone would lose ticker/keyword observations. Content-hash dedup across **different URLs** also needs an explicit editorial policy; record possible duplicates first and preserve source links.
4. Standalone jobs, replay, versioned IDs, and reconciliation are prerequisites to scheduling. The existing Prefect deployments are not a substitute for verified Airflow jobs.
5. External embedding credentials may be unavailable locally. Gold articles/chunks and DuckDB analytics must work without embeddings; Qdrant indexing can then run as a separate optional job.

See [local-architecture.md](local-architecture.md) for the local target and [implementation-plan.md](implementation-plan.md) for the staged work. No pipeline code or crawling was performed for this audit.
