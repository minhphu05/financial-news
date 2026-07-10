# cAdvisor

cAdvisor expose metrics Docker container CPU, memory, network va filesystem cho Prometheus.

## Chay local

```powershell
docker compose -f docker-compose.local.yml up -d cadvisor prometheus
```

URL:

- cAdvisor UI/metrics: http://localhost:8080
- Prometheus target: http://localhost:9090/targets?search=cadvisor

## Metrics hay dung

```promql
# CPU theo container
sum by (name) (rate(container_cpu_usage_seconds_total{name=~"financial-.*|financial-local-.*", image!=""}[1m]))

# Memory theo container
sum by (name) (container_memory_working_set_bytes{name=~"financial-.*|financial-local-.*", image!=""})

# Network RX/TX
sum by (name) (rate(container_network_receive_bytes_total{name=~"financial-.*|financial-local-.*"}[1m]))
sum by (name) (rate(container_network_transmit_bytes_total{name=~"financial-.*|financial-local-.*"}[1m]))

# Container con duoc thay gan day khong
container_last_seen{name=~"financial-.*|financial-local-.*"}
```

## Khi them service moi

Neu service dung container name bat dau bang `financial-` hoac `financial-local-`, dashboard runtime se tu nhan. Neu dung ten khac, cap nhat regex trong dashboard `7 - Local Platform Runtime`.

## Troubleshooting

- Target cadvisor DOWN: Docker Desktop chua expose duong dan mount hoac container thieu quyen `privileged`.
- Khong thay container: container chua co `image` label hoac regex dashboard khong match `name`.
