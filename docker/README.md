# Docker Tooling Overview

Folder `docker/` chua Dockerfile va config cho app services, data services va observability tools.

## Observability tools

- `grafana/`: dashboard UI va provisioning.
- `prometheus/`: metrics scraper va PromQL source.
- `pushgateway/`: batch metrics endpoint cho scraper/ingestion.
- `fluent-bit/`: JSON log shipper vao Loki.
- `loki/`: log storage va LogQL source.
- `cadvisor/`: Docker container metrics.
- `node-exporter/`: host/runtime metrics.

## CDC and vector tools

- `debezium/`: PostgreSQL CDC connector config va REST registration notes.
- `redpanda/`: Kafka-compatible local broker cho Debezium events.
- `qdrant/`: vector store cho gold-layer embeddings.

## Start local stack

```powershell
docker compose -f docker-compose.local.yml up -d --build
```

Neu chi can observability sau khi local infra da chay:

```powershell
docker compose -f docker-compose.local.yml up -d prometheus pushgateway loki fluent-bit grafana cadvisor node-exporter
```

Neu chi can CDC medallion stack sau khi metadata DB va MinIO da chay:

```powershell
docker compose -f docker-compose.local.yml up -d --build redpanda debezium qdrant cdc-medallion-worker
python scripts/register_debezium_connector.py
```

## Local URLs

- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Pushgateway: http://localhost:9091
- Loki: http://localhost:3100
- Fluent Bit metrics: http://localhost:2020/api/v1/metrics/prometheus
- cAdvisor: http://localhost:8080
- Node Exporter: http://localhost:9100/metrics
- Debezium Connect: http://localhost:8083
- Redpanda Kafka: localhost:19092
- Redpanda Admin API: http://localhost:9644
- Qdrant: http://localhost:6333
- Prefect: http://localhost:4201
- MinIO: http://localhost:9001
- pgAdmin: http://localhost:5050

## Mo rong monitoring

- Muon them metric moi: xem `prometheus/README.md` va `pushgateway/README.md`.
- Muon them dashboard: xem `grafana/README.md`.
- Muon them log source: xem `fluent-bit/README.md` va `loki/README.md`.
- Muon them resource panel Docker: xem `cadvisor/README.md`.
- Muon them host panel: xem `node-exporter/README.md`.
- Muon them CDC connector: xem `debezium/README.md`.
- Muon inspect Kafka topic/consumer group: xem `redpanda/README.md`.
- Muon inspect/reset vector store: xem `qdrant/README.md`.

## CDC medallion pipeline

Tai lieu end-to-end nam tai `../docs/CDC_MEDALLION_PIPELINE.md`.

## Luu y hien tai

Neu Docker Hub hoac DNS ngoai bi loi, cac image Grafana/Loki/Prometheus moi co the chua pull duoc. Khi network duoc sua, chay lai lenh `docker compose -f docker-compose.local.yml up -d --build`.
