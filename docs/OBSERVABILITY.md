# Observability — Logs, Metrics, and Dashboards

This document explains the full observability stack: JSON structured logging, FluentBit log shipping, Loki log storage, Prometheus metrics, and Grafana dashboards.

---

## Stack Overview

```
Python Scraper
  │
  ├── *.log          (plain text — developer console)
  └── *.json.log     (structured JSON — machine ingestion)
         │
    Fluent Bit        ← tails ./logs/scraper/*.json.log
         │
       Loki           ← indexes and stores logs
         │
      Grafana         ← queries and visualizes logs + metrics
         │
    Prometheus        ← scrapes Pushgateway + Fluent Bit /metrics
         ▲
    Pushgateway       ← scraper run + per-keyword progress metrics
```

  The canonical scraper now pushes Prometheus progress after each processed keyword, not only after the full run finishes. Grafana refreshes the scraping dashboard every 5 seconds and combines:

  - Prometheus metrics for run state, keyword progress, articles, duration, errors, and container health.
  - Loki logs for live scraper events, warnings, and errors.

---

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| Loki HTTP API | http://localhost:3100 | — |
| Prometheus | http://localhost:9090 | — |
| Pushgateway | http://localhost:9091 | — |
| Fluent Bit metrics | http://localhost:2020/metrics | — |

For the local stack, start `docker-compose.local.yml`; it includes Grafana, Loki, Fluent Bit, Prometheus, Pushgateway, cAdvisor, and Node Exporter alongside Prefect, PostgreSQL, and MinIO.

---

## Structured JSON Logging

### Log File Format

Every scraper run writes two files:

```
logs/scraper/
├── scrape_20260528T231245_BCM.log          ← plain text (human-readable)
└── scrape_20260528T231245_BCM.json.log     ← JSON per line (FluentBit input)
```

Filename anatomy: `scrape_{ISO8601}_{TICKER}.json.log`
- `ISO8601` — start timestamp in `%Y%m%dT%H%M%S` format
- `TICKER` — ticker symbol filter (or `ALL` if no filter)

### JSON Record Schema

Each line in `*.json.log` is a valid JSON object:

```json
{
  "timestamp": "2026-05-28T23:12:45.123456",
  "level": "INFO",
  "logger": "src.scraper.page_scraper",
  "message": "Page 2 scraped — found=10 persisted=3 skipped=7",
  "source_name": "cafef",
  "ticker_symbol": "BCM",
  "keyword": "BCM",
  "run_id": 42
}
```

| Field | Always Present | Description |
|-------|---------------|-------------|
| `timestamp` | ✓ | ISO 8601 with microseconds (UTC) |
| `level` | ✓ | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `logger` | ✓ | Python logger name (module path) |
| `message` | ✓ | Human-readable message (no ANSI escape codes) |
| `source_name` | Context | e.g. `cafef` |
| `ticker_symbol` | Context | e.g. `BCM`, `ACB` |
| `keyword` | Context | Search keyword used |
| `run_id` | Context | FK to `scrape_runs.run_id` |

Context fields are set via `set_log_context()` and apply to all log records in that thread until `clear_log_context()` is called.

### Setting Log Context in Code

```python
from src.utils.logger import set_log_context, clear_log_context, get_logger

logger = get_logger(__name__)

set_log_context(source_name="cafef", ticker_symbol="BCM", keyword="BCM", run_id=42)
logger.info("Starting keyword scrape")    # context fields auto-attached
# ... more logging ...
clear_log_context()
```

Context is stored in a `threading.local()` object — safe in multi-threaded use.

---

## Fluent Bit

### What It Does

Fluent Bit watches the `logs/scraper/` directory for `*.json.log` files, parses each line as JSON, and forwards the structured records to Loki. The local configuration flushes every second and checks for new log lines every second so Grafana logs panels stay close to live during scraping.

### Configuration Files

**`docker/fluent-bit/fluent-bit.conf`**

```ini
[INPUT]
    Name              tail
    Path              /var/log/scraper/*.json.log
    Parser            json
    DB                /var/log/flb_scraper.db
    Mem_Buf_Limit     5MB
    Refresh_Interval  5
    Tag               scraper.*

[FILTER]
    Name    record_modifier
    Match   scraper.*
    Record  hostname  ${HOSTNAME}
    Record  service   financial-news-scraper

[OUTPUT]
    Name            loki
    Match           scraper.*
    Host            loki
    Port            3100
    Labels          job=scraper, service=financial-news-scraper
    Label_Keys      $level,$source_name,$ticker_symbol,$keyword
    Auto_Kubernetes_Labels  off
```

**Key Details:**
- `DB` file — tracks the read offset for each log file, survives restarts (no duplicate ingestion).
- `Label_Keys` — promotes JSON fields `level`, `source_name`, `ticker_symbol`, and `keyword` to Loki labels. The `$` prefix is required by the Loki output plugin.
- `Mem_Buf_Limit` — caps in-memory buffer; back-pressure if Loki is unavailable.

**`docker/fluent-bit/parsers.conf`**

```ini
[PARSER]
    Name        json
    Format      json
    Time_Key    timestamp
    Time_Format %Y-%m-%dT%H:%M:%S.%L
    Time_Keep   On
```

### Volume Mount

The `docker-compose.yml` bind-mounts the host `./logs/scraper/` into Fluent Bit:

```yaml
volumes:
  - ./logs/scraper:/var/log/scraper:ro
```

The `:ro` (read-only) flag ensures Fluent Bit cannot accidentally modify log files.

---

## Loki

### Architecture

Loki stores logs as compressed chunks indexed only by **labels** (not full-text). Full-text search is done at query time by filtering the streamed chunks.

### Labels in This Stack

```
job            = "scraper"              (static, all logs)
service        = "financial-news-scraper" (static, all logs)
level          = "INFO" | "ERROR" | ...  (per-record)
source_name    = "cafef" | ...           (per-record, from context)
ticker_symbol  = "BCM" | "ACB" | ...    (per-record, from context)
keyword        = "BCM" | "Becamex" | ...  (per-record, from context)
```

### Configuration

Located at `docker/loki/loki-config.yaml`:

```yaml
auth_enabled: false
server:
  http_listen_port: 3100
common:
  path_prefix: /tmp/loki          # data directory inside container
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h
limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h   # 7 days
  ingestion_rate_mb: 16
  ingestion_burst_size_mb: 32
```

---

## Querying Loki — LogQL Reference

### Basic Syntax

```
{label_selector} [| filter_expression | format_expression]
```

Always start with a **label selector** in `{}`, then optionally pipe through filters.

### Stream Selectors

```logql
# All scraper logs
{job="scraper"}

# Only errors
{job="scraper", level="ERROR"}

# Specific ticker
{job="scraper", ticker_symbol="BCM"}

# Specific keyword
{job="scraper", keyword="Becamex"}

# Ticker + source combination
{job="scraper", ticker_symbol="ACB", source_name="cafef"}
```

### Text Filters

```logql
# Contains string (case-sensitive)
{job="scraper"} |= "persisted"

# Does NOT contain
{job="scraper"} != "DEBUG"

# Regex match
{job="scraper"} |~ "page [0-9]+ scraped"

# Case-insensitive regex
{job="scraper"} |~ "(?i)error"
```

### JSON Field Extraction

```logql
# Extract and filter on nested JSON fields
{job="scraper"} | json | run_id="42"

# Extract and display specific fields
{job="scraper"} | json | line_format "{{.ticker_symbol}} {{.message}}"

# Filter errors with context
{job="scraper"} | json | level="ERROR" | line_format "[{{.ticker_symbol}}] {{.message}}"
```

### Metric Queries (LogQL → Numbers)

```logql
# Count log lines per minute
count_over_time({job="scraper"}[1m])

# Error rate per 5 minutes
sum(count_over_time({job="scraper", level="ERROR"}[5m]))

# Log volume per ticker (last hour)
sum by (ticker_symbol) (count_over_time({job="scraper"}[1h]))

# Bytes ingested per minute
bytes_over_time({job="scraper"}[1m])

# Instant rate of logs per second
rate({job="scraper"}[5m])
```

### Practical Queries

```logql
# All logs from the last scrape run (run_id=42)
{job="scraper"} | json | run_id="42"

# All articles skipped (already existed)
{job="scraper"} |= "skipped"

# Show which pages caused early-stop
{job="scraper"} |= "early_stop" | json

# Pages with errors in the last 24h
{job="scraper", level="ERROR"} | json | line_format "{{.ticker_symbol}} | {{.message}}"

# Heatmap: log volume by ticker over last 24h
sum by (ticker_symbol) (count_over_time({job="scraper"}[1h]))
```

### Using the Loki HTTP API Directly

```bash
# Health check
curl http://localhost:3100/ready

# Query logs (URL-encoded)
curl -G http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={job="scraper", level="ERROR"}' \
  --data-urlencode 'start=2026-05-28T00:00:00Z' \
  --data-urlencode 'end=2026-05-29T00:00:00Z' \
  --data-urlencode 'limit=100' | python -m json.tool

# List all labels
curl http://localhost:3100/loki/api/v1/labels

# List values for a label
curl http://localhost:3100/loki/api/v1/label/ticker_symbol/values
```

---

## Grafana

### Accessing Grafana

Navigate to **http://localhost:3000** in your browser.  
Default credentials: `admin` / `admin`  
You will be prompted to change the password on first login.

### Pre-Provisioned Datasources

Both datasources are automatically configured when Grafana starts (no manual setup needed):

| Datasource | URL | Default |
|------------|-----|---------|
| Loki | http://loki:3100 | ✓ |
| Prometheus | http://prometheus:9090 | |

Configuration: `docker/grafana/provisioning/datasources/datasources.yaml`

### Pre-Provisioned Dashboard — Scraper Overview

The dashboard is automatically loaded from:
`docker/grafana/provisioning/dashboards/json/scraper-overview.json`

It contains 5 panels:

| Panel | Type | Query |
|-------|------|-------|
| **All Logs** | Logs panel | `{job="scraper"}` |
| **Errors Only** | Logs panel | `{job="scraper", level="ERROR"}` |
| **By Ticker** | Logs panel | `{job="scraper"} \| json \| line_format "{{.ticker_symbol}} {{.message}}"` |
| **Articles Scraped** | Gauge | Prometheus: `scraper_articles_persisted_total` |
| **Scrape Duration** | Time series | Prometheus: `scraper_run_duration_seconds` |

### Creating a New Dashboard

1. Go to **Dashboards → New → New Dashboard**
2. Click **Add visualization**
3. Select **Loki** as the data source
4. In the query builder:
   - Switch to **Code** mode for LogQL
   - Enter your query, e.g.: `{job="scraper", ticker_symbol="BCM"}`
5. For log panels, choose **Logs** visualization type
6. For metric panels, use a metric query:
   ```logql
   sum(count_over_time({job="scraper"}[5m]))
   ```

### Explore View

The **Explore** view (compass icon in the sidebar) is the best place for ad-hoc log investigation:

1. Select **Loki** as the datasource
2. Use **Label browser** to visually build a selector
3. Add filters in the query bar
4. Click **Run query**

**Tips:**
- Enable **Live** mode to tail logs in real time (good for watching an active scraper run)
- Use **Split** view to compare Loki logs alongside Prometheus metrics simultaneously
- Set the time range to `Last 1 hour` for recent scrape run debugging

### Useful Grafana Log Filters

In the Logs panel, you can add ad-hoc filters with the filter icon:
- `level` = `ERROR` → show only errors
- `ticker_symbol` = `BCM` → filter by ticker
- `keyword` → filter by keyword

---

## Prometheus Metrics

### Scraping Configuration

`docker/prometheus/prometheus.yaml` scrapes three targets:

```yaml
scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]

  - job_name: pushgateway
    honor_labels: true
    static_configs:
      - targets: ["pushgateway:9091"]

  - job_name: fluent_bit
    static_configs:
      - targets: ["fluent-bit:2020"]
    metrics_path: /metrics
```

### Pushing Metrics from the Scraper

Use the Pushgateway to push batch job metrics after a run completes:

```python
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

registry = CollectorRegistry()

g_persisted = Gauge(
    "scraper_articles_persisted_total",
    "Total articles persisted in this run",
    registry=registry,
)
g_duration = Gauge(
    "scraper_run_duration_seconds",
    "Duration of the scraper run in seconds",
    registry=registry,
)

g_persisted.set(summary.articles_new)
g_duration.set(summary.duration_seconds)

push_to_gateway(
    "localhost:9091",
    job="scraper",
    grouping_key={"ticker": ticker or "ALL"},
    registry=registry,
)
```

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `scraper_articles_persisted_total` | Gauge | New articles written this run |
| `scraper_articles_skipped_total` | Gauge | Articles already existing (deduped) |
| `scraper_run_duration_seconds` | Gauge | Wall-clock time for the full run |
| `scraper_errors_total` | Gauge | Count of errors during the run |
| `fluentbit_input_records_total` | Counter | Records read by Fluent Bit |
| `fluentbit_output_proc_records_total` | Counter | Records successfully sent to Loki |

### Querying Prometheus

```bash
# Open Prometheus UI
open http://localhost:9090

# API query
curl 'http://localhost:9090/api/v1/query?query=scraper_articles_persisted_total'

# Range query (last 24h)
curl 'http://localhost:9090/api/v1/query_range?query=scraper_articles_persisted_total&start=2026-05-28T00:00:00Z&end=2026-05-29T00:00:00Z&step=3600'
```

---

## Troubleshooting Observability

### Fluent Bit is not shipping logs

```bash
# Check Fluent Bit logs
docker-compose logs financial-fluent-bit

# Check Fluent Bit metrics endpoint
curl http://localhost:2020/metrics | grep fluentbit_output

# Common causes:
# 1. Log file path mismatch — ensure ./logs/scraper/ exists on the host
# 2. JSON parse failure — validate your log file with: cat logs/scraper/*.json.log | python -m json.tool
# 3. Loki unreachable — check docker network: docker exec financial-fluent-bit curl loki:3100/ready
```

### Loki returning no data

```bash
# Check Loki health
curl http://localhost:3100/ready
curl http://localhost:3100/loki/api/v1/labels

# Check for ingestion errors
docker-compose logs financial-loki | grep -i error

# Verify time range — Loki rejects logs older than reject_old_samples_max_age (7 days)
```

### Grafana datasource connection error

```bash
# Verify datasource connectivity from within Grafana container
docker exec financial-grafana wget -qO- http://loki:3100/ready
docker exec financial-grafana wget -qO- http://prometheus:9090/-/healthy

# Reprovision datasources
docker-compose restart financial-grafana
```

### Log files are empty / no JSON.log

Ensure the scraper was invoked in a way that writes JSON logs. Check `run.py`:
```bash
# The JSON log is created alongside the plain log — both should appear
ls -la logs/scraper/
```

If only the `.log` file exists but no `.json.log`, check that `json_log_file` is passed to `get_logger()` in `run.py`.
</content>
