# Grafana

Grafana hien thi dashboard cho scraping, ingestion, RAG serving, infrastructure va observability pipeline.

## Chay local

```powershell
docker compose -f docker-compose.local.yml up -d grafana prometheus loki fluent-bit
```

URL: http://localhost:3000

Dang nhap mac dinh:

- User: `admin`
- Password: `admin`

## Provisioning layout

```text
docker/grafana/provisioning/
  datasources/datasources.yaml
  dashboards/dashboards.yaml
  dashboards/json/*.json
```

Grafana tu dong load datasource va dashboard khi container start. Dashboard provider quet `dashboards/json` moi 30 giay.

## Dashboard hien co

1. `1 - Scraping Realtime Operations`: realtime scraper progress, keyword, errors, live logs.
2. `2 - Preprocessing & Chunking`: preprocessing/chunk metrics.
3. `3 - Embedding & Vectorization`: embedding/vector metrics.
4. `4 - RAG Serving & WebUI`: API/RAG serving metrics.
5. `5 - Infrastructure Health`: host/container baseline.
6. `6 - Observability Pipeline`: Prometheus, Loki, Fluent Bit, Grafana health.
7. `7 - Local Platform Runtime`: Prefect/PostgreSQL/MinIO/container runtime resources.

## Tao them dashboard Grafana

Cach khuyen nghi:

1. Tao dashboard tren UI Grafana.
2. Export JSON: Dashboard settings -> JSON model.
3. Luu vao `docker/grafana/provisioning/dashboards/json/<n>-<name>.json`.
4. Dat `uid` on dinh, vi du `scraper-my-feature`.
5. Dung datasource UID co san:

```json
{ "type": "prometheus", "uid": "prometheus-main" }
{ "type": "loki", "uid": "loki-main" }
```

6. Validate JSON:

```powershell
Get-Content docker/grafana/provisioning/dashboards/json/my-dashboard.json -Raw | ConvertFrom-Json
```

7. Restart hoac doi provisioning reload:

```powershell
docker compose -f docker-compose.local.yml restart grafana
```

## Thiet ke dashboard nen theo

- Row tren cung: 4-6 stat/gauge panel cho trang thai tong quan.
- Giua dashboard: timeseries cho xu huong.
- Duoi dashboard: table/log panel de drill-down.
- Refresh phu hop:
  - Scraping realtime: `5s`.
  - Serving/API: `10s`.
  - Infrastructure: `15s` hoac `30s`.
- Dung threshold mau ro rang: green normal, yellow warning, red critical.
- Tranh dashboard qua dai; neu qua 18-20 panels thi tach dashboard moi.

## Vi du Prometheus panel

```promql
sum by (source) (scraper_articles_persisted_total)
```

Legend:

```text
{{source}} persisted
```

## Vi du Loki logs panel

```logql
{job="scraper"} | json | line_format "{{.level}} {{.ticker_symbol}} {{.keyword}} | {{.message}}"
```

## Troubleshooting

- Dashboard khong hien: JSON invalid hoac duplicate `uid`.
- Panel Prometheus khong co data: vao Prometheus `/targets` xem job co UP khong.
- Panel Loki khong co logs: kiem tra Fluent Bit metrics va query `{job="scraper"}` trong Explore.
- Doi dashboard khong thay cap nhat: restart Grafana hoac doi provider reload 30 giay.
