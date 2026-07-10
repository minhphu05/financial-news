# Redpanda Local Broker

Redpanda la Kafka-compatible broker dung lam event bus cho CDC pipeline.

## Services

- Compose service: `redpanda`
- Internal Kafka broker: `redpanda:9092`
- Host Kafka broker: `localhost:19092`
- Admin API: http://localhost:9644
- Schema Registry: http://localhost:18081
- Pandaproxy: http://localhost:18082

## Topic chinh

Debezium connector phat event vao topic:

```text
financial_metadata.core.article_metadata
```

Worker `cdc-medallion-worker` consume topic nay voi group:

```text
financial-news-cdc-medallion
```

## Lenh kiem tra

Trong container:

```powershell
docker exec -it financial-local-redpanda rpk topic list --brokers=localhost:9092
docker exec -it financial-local-redpanda rpk topic describe financial_metadata.core.article_metadata --brokers=localhost:9092
```

Doc mot so message gan nhat:

```powershell
docker exec -it financial-local-redpanda rpk topic consume financial_metadata.core.article_metadata --brokers=localhost:9092 --num 5
```

Kiem tra consumer group:

```powershell
docker exec -it financial-local-redpanda rpk group describe financial-news-cdc-medallion --brokers=localhost:9092
```

## Luu y van hanh local

- Redpanda dung single node, replication factor 1, phu hop local/dev.
- Du lieu duoc luu trong volume `redpanda_data`.
- Neu Docker Hub/DNS bi loi, image moi co the chua pull duoc. Sau khi sua network, chay lai `docker compose -f docker-compose.local.yml up -d redpanda`.
