# Metadata CDC event contracts

Phase 04 publishes control-plane metadata changes. It does not publish article bodies, chunks, embeddings, analytical rows, or market prices.

## Envelope

Debezium 3.3.2.Final uses JSON converters with schemas disabled. A non-tombstone value has this logical shape:

```json
{
  "before": {"...": "previous row values"},
  "after": {"...": "new row values"},
  "source": {
    "connector": "postgresql",
    "db": "financial_metadata",
    "schema": "control_metadata",
    "table": "news_sources"
  },
  "op": "r|c|u|d",
  "ts_ms": 1790137209219
}
```

The inspector maps operations as follows:

| Debezium `op` | Inspector operation | `before` | `after` |
|---|---|---|---|
| `r` | `snapshot` | null | seeded row |
| `c` | `insert` | null | inserted row |
| `u` | `update` | previous row | committed row |
| `d` | `delete` | deleted row | null |
| Kafka null value | `tombstone` | unavailable | unavailable |

Both captured tables use `REPLICA IDENTITY FULL`, so UPDATE and DELETE events include complete previous rows. JSONB columns are represented by the installed connector as JSON strings inside the JSON envelope. Consumers must parse them only when they need the nested configuration.

## Topics and keys

| Table | Topic | Kafka key | Purpose |
|---|---|---|---|
| `control_metadata.news_sources` | `platform.control_metadata.news_sources` | `{"source_id":"<stable-id>"}` | Source availability and non-secret source configuration. |
| `control_metadata.pipeline_configs` | `platform.control_metadata.pipeline_configs` | `{"config_id":"<stable-id>"}` | Versioned pipeline settings already supported by the batch pipeline. |

Keys come from PostgreSQL primary keys. Debezium does not generate random event identifiers. Metadata topics use one partition and `cleanup.policy=compact`; ordering is therefore preserved per topic in this local slice. The delete envelope is followed by a null tombstone with the same key.

## Consumer behavior

Consumers should treat the stream as at-least-once and tolerate replay. A current-state consumer should upsert snapshot/insert/update values by `(topic, key)`, remove state on delete or tombstone, and remember topic/partition/offset when it needs idempotent processing. Database commit semantics, Kafka delivery, and consumer processing are separate guarantees.

The local `metadata-inspector` group is for interactive inspection. Independent future consumers must use their own group when each consumer needs the complete metadata stream.
