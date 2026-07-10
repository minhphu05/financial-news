# Architecture Overview

This document describes the full system architecture of the **Financial News RAG Stack** — from raw web scraping through storage, log aggregation, and observability.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Financial News RAG Stack                              │
│                                                                               │
│  ┌──────────────┐   scrape    ┌────────────────────────────────────────┐    │
│  │  Source Sites│ ──────────► │           Scraper Pipeline              │    │
│  │  cafef.vn    │             │  run.py → pipeline.py → page_scraper.py│    │
│  │  vnexpress   │             │          → detail_scraper.py           │    │
│  │  (future)    │             └───────────┬────────────────────────────┘    │
│  └──────────────┘                         │                                  │
│                                           │ persist                          │
│                          ┌────────────────┴────────────────┐                │
│                          ▼                                  ▼                │
│               ┌──────────────────┐              ┌──────────────────┐        │
│               │  PostgreSQL 17   │              │    MongoDB 8     │        │
│               │  (Metadata DB)   │              │  (Content Store) │        │
│               │                  │              │                  │        │
│               │  news_articles   │              │ articles_content │        │
│               │  scrape_runs     │              │   (full body)    │        │
│               │  scrape_progress │              │                  │        │
│               └──────────────────┘              └──────────────────┘        │
│                                                                               │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ Observability Plane ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    │
│                                                                               │
│  ┌───────────────┐  tail   ┌────────────┐  push   ┌───────┐                │
│  │  JSON Logs    │ ──────► │ Fluent Bit │ ──────► │ Loki  │                │
│  │ logs/scraper/ │         │  (shipper) │         │ (log  │                │
│  │ *.json.log    │         └────────────┘         │  DB)  │                │
│  └───────────────┘                                └───┬───┘                │
│                                                        │ query              │
│  ┌────────────────────────────────────────────────────▼───┐                │
│  │                      Grafana                            │                │
│  │   Dashboards: Scraper Overview, Error Tracking,         │                │
│  │   Ticker Activity, Prometheus Metrics                   │                │
│  └────────────────────────────────────────────────────────┘                │
│                                                                               │
│  ┌──────────────┐  scrape   ┌────────────┐   push    ┌──────────────┐      │
│  │  Fluent Bit  │ ─────────►│ Prometheus │ ◄──────── │ Pushgateway  │      │
│  │  /metrics    │           │  (metrics) │           │ (batch jobs) │      │
│  └──────────────┘           └────────────┘           └──────────────┘      │
│                                                                               │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ Orchestration Plane ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │                    Prefect Platform                           │           │
│  │  prefect-server (4200) ← prefect-services ← prefect-worker   │           │
│  │  Backed by: PostgreSQL 14 (metadata) + Redis 7 (messaging)   │           │
│  └──────────────────────────────────────────────────────────────┘           │
│                                                                               │
│  ┌──────────────────┐                                                        │
│  │   MLflow (5555)  │  ← Experiment tracking for future ML models           │
│  └──────────────────┘                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Service Inventory

| Service | Image | Host Port | Purpose |
|---------|-------|-----------|---------|
| `financial-metadata-psql` | postgres:17 (custom) | **5434** | Article metadata + scrape tracking |
| `vifinner-mongo` | mongodb-community-server:8.0 | **27018** | Full article body (content) |
| `financial-prefect-psql` | postgres:14 | 5432 | Prefect workflow metadata |
| `financial-redis` | redis:7 | 6379 | Prefect messaging broker |
| `financial-pf-server` | prefecthq/prefect:3 | **4200** | Prefect UI + API |
| `financial-pf-services` | prefecthq/prefect:3 | — | Prefect background services |
| `financial-pf-worker` | custom (ingestion) | — | Executes Prefect flows |
| `financial-mlflow` | custom | **5555** | Experiment tracking |
| `financial-loki` | grafana/loki:3.1.0 | **3100** | Log storage backend |
| `financial-grafana` | grafana/grafana:11.1.0 | **3000** | Dashboards & log explorer |
| `financial-fluent-bit` | fluent/fluent-bit:3.1 | 2020 | Log shipper |
| `financial-prometheus` | prom/prometheus:2.53 | **9090** | Metrics storage |
| `financial-pushgateway` | prom/pushgateway:1.9 | **9091** | Batch metrics relay |
| `financial-local-redpanda` | redpandadata/redpanda:v24.2.7 | **19092** | Kafka-compatible CDC event bus |
| `financial-local-debezium` | debezium/connect:2.7.3.Final | **8083** | PostgreSQL logical replication connector |
| `financial-local-qdrant` | qdrant/qdrant:v1.12.1 | **6333/6334** | Vector store for article chunks |
| `financial-local-cdc-medallion-worker` | custom (ingestion) | — | Consumes CDC events and writes Qdrant embeddings |

---

## Docker Networks

```
financial-net  (bridge)
  ├── financial-metadata-psql
  ├── financial-prefect-psql
  ├── financial-redis
  ├── financial-mlflow
  ├── financial-pf-server
  ├── financial-pf-services
  ├── financial-pf-worker         ← also in vifinner-net
  ├── financial-loki
  ├── financial-grafana
  ├── financial-fluent-bit
  ├── financial-prometheus
  └── financial-pushgateway

vifinner-net  (bridge)
  ├── vifinner-mongo
  └── financial-pf-worker
```

The scraper runs **on the host machine** (not in Docker). It connects to:
- PostgreSQL via `localhost:5434`
- MongoDB via `localhost:27018` (Docker maps 27018 → 27017 inside container)

---

## Data Flows

### 1. Scraping Flow

```
vn30.xlsx  →  pipeline.py  →  per-keyword loop  →  page_scraper.py
                                                         │
                          ┌──────────────────────────────┤
                          │  for each listing page:       │
                          │    parse_listing_page()        │
                          │    for each article entry:     │
                          │      article_exists()?  → skip │
                          │      scrape_article_detail()   │
                          │      StorageManager.save()     │
                          │        → MongoDB (content)     │
                          │        → PostgreSQL (metadata) │
                          │      update scrape_progress    │
                          └──────────────────────────────┘
```

### 2. Log Flow

```
scraper (Python process)
  │
  ├── Console handler    → colored output (developer)
  ├── Plain file handler → logs/scraper/*.log
  └── JSON file handler  → logs/scraper/*.json.log
                                    │
                               Fluent Bit
                              (tails *.json.log)
                                    │
                                  Loki
                              (stores indexed)
                                    │
                                Grafana
                              (query & display)
```

### 3. Metrics Flow (optional)

```
Scraper script
  │
  └── POST metrics → Pushgateway:9091
                           │
                      Prometheus
                     (scrapes every 15s)
                           │
                        Grafana
                     (time series panels)
```

### 4. CDC Medallion Flow

```text
core.article_metadata insert/update
  │
  └── PostgreSQL logical WAL
          │
       Debezium
          │
          ▼
Redpanda topic: financial_metadata.core.article_metadata
          │
          ▼
cdc-medallion-worker
  ├── checkpoint state → rag.cdc_file_processing_checkpoints
  ├── read article JSON → MinIO or ADLS
  ├── bronze → raw normalized document
  ├── silver → cleaned article text
  └── gold → chunks + Voyage embeddings → Qdrant
```

The CDC worker is idempotent at two levels: `article_id` is the checkpoint primary key, and Qdrant point IDs are deterministic UUID5 values from `article_link#chunk_index`. Detailed operations are documented in `CDC_MEDALLION_PIPELINE.md`.

---

## Source Code Layout

```
src/
├── scraper/
│   ├── config.py          # ScraperSettings dataclass — all knobs from .env
│   ├── models.py          # SQLAlchemy ORM: NewsArticle, ScrapeRun, ScrapeProgress
│   ├── storage.py         # StorageManager: dual-store (Postgres + Mongo) UPSERT
│   ├── http_client.py     # HttpClient with retry + jitter
│   ├── parsers.py         # HTML parsers: listing page + detail page
│   ├── page_scraper.py    # Keyword-level crawler with incremental early-stop
│   ├── detail_scraper.py  # Individual article fetcher
│   ├── pipeline.py        # Top-level orchestrator — loads Excel, loops keywords
│   └── run.py             # CLI entry point
└── utils/
    ├── __init__.py
    └── logger.py          # ColoredFormatter + JsonFormatter + thread-local context
```

---

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Metadata DB | PostgreSQL 17 | ACID, indexes on ticker/keyword/date, UPSERT via ON CONFLICT |
| Content DB | MongoDB 8 | Flexible schema for variable-length article bodies |
| Log aggregation | Loki | Lightweight, label-based querying, integrates natively with Grafana |
| Log shipper | Fluent Bit | Low memory footprint vs Logstash, native Loki output plugin |
| Metrics | Prometheus + Pushgateway | Industry standard; Pushgateway suits batch/cron jobs |
| Orchestration | Prefect 3 | Python-native, supports async flows, good local dev experience |
| Experiment tracking | MLflow | Future ML model training; artifact versioning |
| CDC event bus | Debezium + Redpanda | PostgreSQL WAL events decouple scraping from downstream RAG processing |
| Vector store | Qdrant | Local/dev vector database with deterministic idempotent upserts |
</content>
</invoke>