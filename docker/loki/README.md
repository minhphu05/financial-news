# Loki

Loki luu tru logs tu Fluent Bit va cho Grafana query bang LogQL.

## Chay local

```powershell
docker compose -f docker-compose.local.yml up -d loki fluent-bit grafana
```

URL:

- Loki ready: http://localhost:3100/ready
- Loki metrics: http://localhost:3100/metrics

Config: `docker/loki/loki-config.yaml`.

## Label hien co

Scraper logs:

```text
job="scraper"
service="scraper"
level="INFO|WARNING|ERROR|..."
source_name="cafef|..."
ticker_symbol="ACB|..."
keyword="..."
```

Pipeline logs:

```text
job="ingestion-pipeline"
service="ingestion-pipeline"
level="INFO|WARNING|ERROR|..."
stage="chunk|embed|upsert|clean|scrape|summary"
run_id="..."
```

## LogQL co ban

```logql
# Tat ca scraper logs
{job="scraper"}

# Loi scraper
{job="scraper", level=~"ERROR|CRITICAL"}

# Theo ticker
{job="scraper", ticker_symbol="ACB"}

# Parse JSON va format output
{job="scraper"} | json | line_format "{{.level}} {{.ticker_symbol}} {{.keyword}} | {{.message}}"

# Count logs theo level
sum by (level) (count_over_time({job="scraper"}[5m]))

# Tim message co text
{job="scraper"} |= "Keyword completed"
```

## Them loai log moi

1. Them input/output trong Fluent Bit.
2. Chon static label `job=<ten-service>`.
3. Chi promote nhung field can filter thuong xuyen thanh label.
4. Tao logs panel trong Grafana voi datasource `loki-main`.

## Retention va storage

Local config dung filesystem trong volume `loki_data` va schema TSDB. `reject_old_samples_max_age` dang la 7 ngay, nghia la Loki tu choi sample qua cu.

Neu muon reset local Loki data:

```powershell
docker compose -f docker-compose.local.yml down
docker volume rm financial-news_loki_data
docker compose -f docker-compose.local.yml up -d loki
```

## Troubleshooting

- `http://localhost:3100/ready` khong ready: xem logs `docker logs financial-local-loki`.
- Query Loki cham: giam time range hoac filter label truoc khi text search.
- Logs khong vao Loki: kiem tra Fluent Bit output errors va `docker logs financial-local-fluent-bit`.
