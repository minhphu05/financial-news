# Qdrant Local Vector Store

Qdrant luu vector embeddings cua article chunks sau khi CDC medallion worker xu ly gold stage.

## Service

- Compose service: `qdrant`
- REST API: http://localhost:6333
- gRPC: localhost:6334
- Collection mac dinh: `financial_news_chunks`
- Persistent volume: `qdrant_data`

## Collection schema

Collection duoc tao boi `QdrantRepository.ensure_collection()` trong `src/rag/databases/qdrant_client.py`.

Vector:

- Dimension: `QDRANT_EMBEDDING_DIM`, mac dinh `1024`
- Distance: `cosine`

Payload fields quan trong:

- `article_link`
- `chunk_index`
- `content`
- `title`
- `ticker_symbol`
- `ticker_name`
- `post_date`
- `source`
- `keyword`
- `content_hash`
- `json_path`
- `embedded_at`

Point ID duoc tao deterministic bang UUID5 tu `article_link#chunk_index`, nen upsert lai cung article se khong tao duplicate.

## Kiem tra nhanh

Kiem tra Qdrant san sang:

```powershell
Invoke-RestMethod http://localhost:6333/readyz
```

Liet ke collections:

```powershell
Invoke-RestMethod http://localhost:6333/collections | ConvertTo-Json -Depth 8
```

Kiem tra collection chinh:

```powershell
Invoke-RestMethod http://localhost:6333/collections/financial_news_chunks | ConvertTo-Json -Depth 8
```

Dem points:

```powershell
Invoke-RestMethod http://localhost:6333/collections/financial_news_chunks/points/count `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"exact": true}' | ConvertTo-Json -Depth 8
```

## Reset local vectors

Chi dung trong dev khi muon build lai vector store tu dau:

```powershell
Invoke-RestMethod http://localhost:6333/collections/financial_news_chunks -Method Delete
```

Sau do replay CDC hoac update lai checkpoint/event de worker upsert lai.

## Luu y

- Qdrant khong tu tao embeddings; worker tao embeddings bang Voyage AI truoc khi upsert.
- `VOYAGE_EMBEDDING_DIM` phai khop `QDRANT_EMBEDDING_DIM`.
- Neu doi dimension, can xoa/recreate collection local vi Qdrant khong cho doi vector size tren collection da ton tai.
