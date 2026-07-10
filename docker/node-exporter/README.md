# Node Exporter

Node Exporter expose host-level CPU, memory, filesystem metrics cho Prometheus.

## Chay local

```powershell
docker compose -f docker-compose.local.yml up -d node-exporter prometheus
```

URL:

- Node Exporter metrics: http://localhost:9100/metrics
- Prometheus target: http://localhost:9090/targets?search=node-exporter

## Metrics hay dung

```promql
# Host CPU busy
1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))

# Host memory used
1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)

# Filesystem used ratio
1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"})

# Disk free bytes
node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"}
```

## Luu y tren Docker Desktop / Windows

Node Exporter chay trong Linux VM cua Docker Desktop, nen metrics phan anh moi truong Docker/WSL thay vi toan bo Windows host theo nghia native. Van huu ich de theo doi resource stack local.

## Troubleshooting

- Target DOWN: kiem tra port `9100` co bi dung boi process khac khong.
- Filesystem panel nhieu mountpoint: loc bang `fstype` hoac `mountpoint` trong PromQL.
