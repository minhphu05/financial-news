# Pushgateway

Pushgateway nhan metrics tu batch job nhu scraper, sau do Prometheus scrape lai.

## Chay local

```powershell
docker compose -f docker-compose.local.yml up -d pushgateway prometheus
```

URL:

- Pushgateway UI/API: http://localhost:9091
- Prometheus target: http://localhost:9090/targets?search=pushgateway

## Khi nao dung Pushgateway

Dung cho batch job khong co HTTP server chay lien tuc:

- Scraper CLI/Prefect task.
- Batch ingestion.
- Offline evaluation.

Khong dung cho service online co `/metrics`; voi service online, de Prometheus scrape truc tiep.

## Push metrics tu Python

```python
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

registry = CollectorRegistry()
rows = Gauge("my_batch_rows_total", "Rows processed by batch", ["stage"], registry=registry)
rows.labels(stage="scrape").set(100)

push_to_gateway("pushgateway:9091", job="my-batch", registry=registry)
```

Host-side local run co the dung:

```powershell
$env:PUSHGATEWAY_URL = "localhost:9091"
python -m src.scraper.run --ticket ACB --source cafef --max-pages 1 --content-storage-backend minio
```

Trong Docker worker:

```text
PUSHGATEWAY_URL=pushgateway:9091
```

## Scraper metrics hien co

- `scraper_run_active`
- `scraper_keywords_total`
- `scraper_keywords_processed_total`
- `scraper_keywords_remaining`
- `scraper_articles_found_total`
- `scraper_articles_persisted_total`
- `scraper_articles_skipped_total`
- `scraper_pages_crawled_total`
- `scraper_errors_total`
- `scraper_errors_by_type`
- `scraper_run_duration_seconds`
- `scraper_last_run_timestamp_seconds`
- `scraper_keyword_duration_seconds`
- `scraper_keyword_articles_found_total`
- `scraper_keyword_articles_persisted_total`
- `scraper_keyword_articles_skipped_total`
- `scraper_keyword_pages_crawled_total`

## Xoa metrics cu

Pushgateway giu metric cu cho toi khi bi replace/delete. Xoa theo job:

```powershell
Invoke-RestMethod -Method Delete http://localhost:9091/metrics/job/scraper
```

## Troubleshooting

- Scraper log `Failed to push scraper metrics`: sai `PUSHGATEWAY_URL`, container khong cung network, hoac Pushgateway down.
- Prometheus khong thay metric: kiem tra target `pushgateway` co UP khong.
- Dashboard stale: metric cu con trong Pushgateway; xoa job va chay lai scraper.
