# CDC Medallion Pipeline

Tai lieu nay mo ta pipeline xu ly file news da scrape theo kieu event-driven:

```text
PostgreSQL core.article_metadata
  -> Debezium PostgreSQL connector
  -> Redpanda topic financial_metadata.core.article_metadata
  -> cdc-medallion-worker
  -> MinIO/ADLS article JSON
  -> Bronze -> Silver -> Gold
  -> Qdrant financial_news_chunks
```

## Muc tieu

- Tu dong phat hien article metadata moi sau scraping thong qua PostgreSQL CDC.
- Doc `json_path` tu `core.article_metadata` de lay file content trong MinIO hoac ADLS.
- Luu checkpoint tung article theo tung stage de retry an toan.
- Chuan hoa raw article thanh bronze/silver/gold.
- Tao chunk, embed bang Voyage AI, va upsert vao Qdrant bang deterministic point id.

## Thanh phan

| Thanh phan | Vai tro |
| --- | --- |
| `postgresql` | Metadata DB, chua `core.article_metadata`, bat `wal_level=logical`. |
| `debezium` | Kafka Connect worker doc logical WAL tu PostgreSQL. |
| `redpanda` | Kafka-compatible broker luu CDC event. |
| `cdc-medallion-worker` | Python worker consume Debezium event va xu ly medallion. |
| `minio` / ADLS | Noi luu article JSON da scrape. |
| `qdrant` | Vector store cho chunk embeddings. |
| `rag.cdc_file_processing_checkpoints` | Checkpoint table cho tung article file. |

## Luong xu ly

1. Scraper ghi metadata vao `core.article_metadata`, trong do `json_path` tro den file JSON da luu trong MinIO/ADLS.
2. Debezium nhan insert/update tu PostgreSQL logical WAL.
3. Debezium phat message vao topic `financial_metadata.core.article_metadata`.
4. Worker parse event, bo qua delete/tombstone, va lay `id`, `url`, `url_hash`, `json_path`.
5. Worker insert/update checkpoint voi status `RECEIVED`.
6. Worker doc file JSON tu MinIO/ADLS.
7. Bronze: tao document raw normalized, luu vao `bronze_document`, status `BRONZE_DONE`.
8. Silver: clean text bang `TextCleaner`, tinh `content_hash`, luu vao `silver_document`, status `SILVER_DONE`.
9. Gold: chunk text bang `TextChunker`, embed bang `VoyageAIEmbedder`, upsert vao Qdrant, status `GOLD_DONE`.
10. Worker commit Kafka offset chi sau khi xu ly xong event.

## Checkpoint model

Bang checkpoint:

```sql
SELECT *
FROM rag.cdc_file_processing_checkpoints
ORDER BY updated_at DESC
LIMIT 20;
```

Cac status chinh:

| Status | Y nghia |
| --- | --- |
| `RECEIVED` | Da nhan CDC event, chua xu ly. |
| `PROCESSING` | Worker dang xu ly article. |
| `BRONZE_DONE` | Da doc file JSON va luu raw normalized document. |
| `SILVER_DONE` | Da clean text va tao silver document. |
| `GOLD_DONE` | Da upsert chunk embeddings vao Qdrant. |
| `FAILED` | Xu ly loi, `last_error` chua nguyen nhan gan nhat. |

Query theo doi queue:

```sql
SELECT status, count(*) AS total
FROM rag.cdc_file_processing_checkpoints
GROUP BY status
ORDER BY status;
```

Query cac loi gan nhat:

```sql
SELECT article_id, json_path, attempts, last_error, updated_at
FROM rag.cdc_file_processing_checkpoints
WHERE status = 'FAILED'
ORDER BY updated_at DESC
LIMIT 20;
```

## Idempotency

Pipeline duoc thiet ke de chay lai an toan:

- Checkpoint dung `article_id` lam primary key.
- Neu article da `GOLD_DONE`, worker se skip event tiep theo cho cung `article_id`.
- Qdrant point id duoc tao bang UUID5 tu `article_link#chunk_index`, nen upsert lai khong tao duplicate.
- Kafka offset chi commit sau khi worker xu ly event xong.

## Chay local

Start stack:

```powershell
docker compose -f docker-compose.local.yml up -d --build postgresql minio redpanda debezium qdrant cdc-medallion-worker
```

Dang ky Debezium connector:

```powershell
python scripts/register_debezium_connector.py
```

Kiem tra connector:

```powershell
Invoke-RestMethod http://localhost:8083/connectors/postgres-article-metadata/status | ConvertTo-Json -Depth 8
```

Kiem tra worker logs:

```powershell
docker logs -f financial-local-cdc-medallion-worker
```

Chay worker mot lan tu host de debug:

```powershell
python -m src.rag.cdc.worker --once
```

Xu ly toi da N message:

```powershell
python -m src.rag.cdc.worker --max-messages 10
```

## Bien moi truong quan trong

| Bien | Mac dinh | Y nghia |
| --- | --- | --- |
| `CDC_KAFKA_BOOTSTRAP_SERVERS` | `redpanda:9092` | Kafka/Redpanda broker cho worker. |
| `CDC_DEBEZIUM_TOPIC` | `financial_metadata.core.article_metadata` | Topic Debezium cua article metadata. |
| `CDC_KAFKA_GROUP_ID` | `financial-news-cdc-medallion` | Consumer group id. |
| `CDC_AUTO_OFFSET_RESET` | `earliest` | Doc tu dau neu group chua co offset. |
| `CDC_CHECKPOINT_TABLE` | `rag.cdc_file_processing_checkpoints` | Bang checkpoint. |
| `CONTENT_STORAGE_BACKEND` | `minio` trong compose local | Backend doc article JSON: `minio` hoac `adls`. |
| `MINIO_ENDPOINT` | `minio:9000` | Endpoint MinIO trong Docker network. |
| `QDRANT_HOST` | `qdrant` | Qdrant host trong Docker network. |
| `QDRANT_COLLECTION` | `financial_news_chunks` | Collection luu chunks. |
| `VOYAGE_API_KEY` | rong | Bat buoc de tao embeddings. |

## Retry va reset

Retry cac article failed: chi can sua nguyen nhan loi va update status ve `RECEIVED` hoac de event moi den lai.

```sql
UPDATE rag.cdc_file_processing_checkpoints
SET status = 'RECEIVED', last_error = NULL, updated_at = now()
WHERE status = 'FAILED';
```

Retry mot article cu the:

```sql
UPDATE rag.cdc_file_processing_checkpoints
SET status = 'RECEIVED', last_error = NULL, updated_at = now()
WHERE article_id = '<article-uuid>';
```

Neu Kafka offset da commit nhung muon worker xu ly lai article, co hai cach local/dev:

1. Reset checkpoint status va tao update nho tren `core.article_metadata` de Debezium phat event moi.
2. Reset consumer group offset bang `rpk group seek` trong Redpanda neu can replay topic.

Vi du tao event moi:

```sql
UPDATE core.article_metadata
SET updated_at = now()
WHERE id = '<article-uuid>';
```

## Mo rong pipeline

Them stage moi:

1. Them cot checkpoint neu can audit output cua stage.
2. Them method trong `src/rag/cdc/store.py`.
3. Chen stage trong `src/rag/cdc/processor.py` sau silver hoac truoc gold.
4. Cap nhat docs va dashboard neu stage co metric moi.

Them source storage moi:

1. Mo rong `ContentDocumentReader` trong `src/rag/cdc/content_reader.py`.
2. Them env var vao `docker-compose.local.yml`.
3. Cap nhat tai lieu trong file nay.

Them CDC table moi:

1. Cap nhat Debezium connector `table.include.list`.
2. Tao parser event rieng trong `src/rag/cdc/events.py`.
3. Tao worker/processor rieng neu business logic khac article metadata.

## Gioi han hien tai

- Worker can `VOYAGE_API_KEY`; neu bien nay rong, embedder se fail som va article se vao `FAILED`.
- Docker Hub/DNS cua may local dang co van de trong phien lam viec nay, nen viec pull image Redpanda/Debezium/Qdrant co the bi chan cho toi khi network duoc sua.
- Debezium chi duoc dung trong local compose voi replication factor 1; production can cau hinh bao mat, replication, retention va monitoring rieng.
