# Prometheus

Prometheus thu thap metrics cho scraper, observability stack va container runtime.

## Chay local

```powershell
docker compose -f docker-compose.local.yml up -d prometheus pushgateway cadvisor node-exporter fluent-bit loki grafana
```

URL local:

- Prometheus UI: http://localhost:9090
- Targets: http://localhost:9090/targets
- Query UI: http://localhost:9090/graph

Config chinh nam o `docker/prometheus/prometheus.yaml`.

## Cac scrape job hien co

- `prometheus`: self-monitoring.
- `pushgateway`: scraper/ingestion batch metrics.
- `rag-api`: API live metrics o `/metrics`.
- `fluent-bit`: log shipper internal metrics.
- `loki`: Loki internal metrics.
- `grafana`: Grafana internal metrics.
- `cadvisor`: Docker container CPU/RAM/network.
- `node-exporter`: host CPU/RAM/filesystem.

## Them metrics moi vao Prometheus

1. Neu service da co endpoint `/metrics`, them job vao `scrape_configs`:

```yaml
- job_name: "my-service"
  metrics_path: "/metrics"
  scrape_interval: 5s
  static_configs:
    - targets: ["my-service:8080"]
```

2. Neu la batch job khong chay lien tuc, push metrics vao Pushgateway:

```python
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

registry = CollectorRegistry()
metric = Gauge("my_job_rows_total", "Rows processed", ["stage"], registry=registry)
metric.labels(stage="scrape").set(123)
push_to_gateway("pushgateway:9091", job="my-job", registry=registry)
```

3. Kiem tra target trong Prometheus:

```promql
up{job="my-service"}
```

4. Dung metric trong Grafana panel.

## Quy uoc metric nen dung

- Counter: su kien tich luy, ten ket thuc bang `_total`.
- Gauge: gia tri hien tai, vi du `scraper_run_active`.
- Histogram: latency/size distribution, vi du `request_duration_seconds_bucket`.
- Label nen it cardinality: `source`, `stage`, `status`, `ticker` khi can thiet.
- Tranh label qua cao cardinality nhu raw URL, title, full exception text.

## PromQL huu ich

```promql
# Target nao down
up == 0

# Scraper co dang chay khong
max(scraper_run_active)

# Tien do keyword
sum(scraper_keywords_processed_total) / clamp_min(sum(scraper_keywords_total), 1)

# Fluent Bit co loi output khong
sum(rate(fluentbit_output_errors_total[5m]))

# CPU container theo service
sum by (name) (rate(container_cpu_usage_seconds_total{name=~"financial-.*|financial-local-.*", image!=""}[1m]))
```

## Troubleshooting

- `up{job="..."} == 0`: service chua start, sai hostname, sai port, hoac endpoint `/metrics` loi.
- Khong thay scraper metrics: kiem tra `PUSHGATEWAY_URL` trong worker va `http://localhost:9091`.
- Docker Hub/DNS loi: Prometheus image chua pull duoc, can sua DNS/network truoc khi start stack moi.
