# Debezium PostgreSQL CDC

Debezium chay trong Kafka Connect va doc logical WAL tu PostgreSQL metadata DB. Connector hien tai chi theo doi bang `core.article_metadata`, vi day la bang chua `json_path` cua file news da scrape.

## Services

- Compose service: `debezium`
- REST API: http://localhost:8083
- Connector config: `connectors/postgres-article-metadata.json`
- Output topic mac dinh: `financial_metadata.core.article_metadata`

## Yeu cau PostgreSQL

Metadata PostgreSQL phai bat logical replication:

```text
wal_level=logical
max_replication_slots=10
max_wal_senders=10
```

`docker-compose.local.yml` da cau hinh cac tham so nay cho service `postgresql`.

## Dang ky connector

Sau khi stack chay:

```powershell
python scripts/register_debezium_connector.py
```

Neu Connect API khong dung port mac dinh:

```powershell
python scripts/register_debezium_connector.py --connect-url http://localhost:8083
```

Script se doc file JSON va override cac truong database neu cac bien moi truong sau ton tai:

- `DEBEZIUM_POSTGRES_HOST`
- `DEBEZIUM_POSTGRES_PORT`
- `DEBEZIUM_POSTGRES_USER` hoac `METADATA_POSTGRES_USER`
- `DEBEZIUM_POSTGRES_PASSWORD` hoac `METADATA_POSTGRES_PASSWORD`
- `DEBEZIUM_POSTGRES_DB` hoac `METADATA_POSTGRES_DB`
- `DEBEZIUM_TOPIC_PREFIX`
- `DEBEZIUM_SLOT_NAME`
- `DEBEZIUM_PUBLICATION_NAME`

Trong Docker network, connector dung host `postgresql` va port `5432`. Khi chay script tu host Windows, khong set `DEBEZIUM_POSTGRES_HOST=localhost`, vi `localhost` luc do se tro vao container Debezium chu khong phai metadata Postgres.

## Kiem tra connector

```powershell
Invoke-RestMethod http://localhost:8083/connectors | ConvertTo-Json
Invoke-RestMethod http://localhost:8083/connectors/postgres-article-metadata/status | ConvertTo-Json -Depth 8
```

## Reset connector

Neu can doc lai tu dau trong moi truong dev:

```powershell
Invoke-RestMethod http://localhost:8083/connectors/postgres-article-metadata -Method Delete
python scripts/register_debezium_connector.py
```

Neu can reset slot/publication hoan toan, dung pgAdmin hoac psql va chi lam khi chac chan khong can offset cu.

## Mo rong them bang

Cap nhat `table.include.list` trong connector config, vi du:

```json
"table.include.list": "core.article_metadata,core.article_stock_mapping"
```

Sau do dang ky lai connector. Neu worker moi can xu ly topic moi, tao consumer rieng hoac mo rong parser trong `src/rag/cdc/events.py`.
