# Preflight migration ADLS Gen2 — chưa thực thi

Khởi tạo 22/10, cập nhật 23/10/2026. DRAFT; mọi cloud canary dưới đây thuộc P11 **sau GO**.

## 1. Inventory và layout

Source default bucket là `financial-news`, cấu hình thực tế qua Settings.
Không ghi source credentials hoặc raw HTML vào checklist. Inventory chính xác
phải lấy ở checkpoint đóng writer và ghi object count/bytes/checksum manifest;
Phase10 đã list metadata toàn bucket tại 00:32 ngày 23/10/2026 (+07:00):
**4.441 objects / 507.939.966 bytes**, năm pages. Counts/size bins/prefixes ở
`artifacts/phase10/source-storage-inventory.json`; không giữ raw keys/bytes.
Đây là observed listing gồm historical/fixture/Delta logs, không là article count
hoặc inventory nhất quán để migrate vì chưa freeze writers/restore checkpoint.

| Local logical data | Target logical path | Xác minh bắt buộc |
|---|---|---|
| Landing HTML/envelopes/batch inputs | Cùng logical key dưới filesystem được duyệt | Exact bytes/SHA-256, envelope → batch lineage, private access |
| Bronze raw/manifests | Cùng prefix và relative key | Original bytes/checksum/row count, ingestion identifiers |
| Silver Delta snapshots/current | Cùng relative layout, gồm `_delta_log` | Files referenced bởi log, table version/history, row/schema/key/content hash |
| Gold documents/chunks Delta | Cùng relative layout/version | article/chunk IDs, entity null/status và processing/chunker versions |
| Gold Analytics Parquet/manifest | Cùng keys; rewrite chỉ physical URI bằng adapter được kiểm | Manifest object list, aggregate totals, pinned source version |
| Operations lake exports | Cùng logical key, controls riêng | Audit/reconciliation lineage, access policy |
| PostgreSQL và serving files | Giữ local trong P11 | Backup/checkpoint references; Qdrant/DuckDB rebuild từ đúng Gold |

Exact runtime prefixes đến từ Settings/GoldSettings và crawler Landing code,
không giả định mọi source dùng cùng path/collection. Unicode/URL-derived keys,
case sensitivity, slash/percent encoding và absolute URI trong manifest cần
contract tests. `Settings.object_key()` hiện theo provider; test cả accepted và
foreign URI, không silently đọc prefix MinIO khi target đã chuyển.

## 2. Compatibility cần làm tại P11

Pin Spark **3.5.3**, Delta **3.2.1**, Java **17**, Hadoop baseline **3.3.4**;
đối chiếu Hadoop thực tế trên classpath trước chọn `hadoop-azure` và transitive
Azure libraries. Không mang `S3SingleDriverLogStore`/S3A credentials sang ABFS.
Thêm byte adapter có cùng ObjectStore semantics và Spark authentication boundary,
không đổi cleaning/chunking/identity/CDC semantics.

ABFS là Hadoop connector cho ADLS Gen2; authentication và filesystem configuration
phải khớp version triển khai. Delta còn yêu cầu atomic visibility, mutual exclusion
và consistent listing, nên tên API tương tự không đủ chứng minh commit đúng.
[Hadoop 3.3.4 ABFS](https://hadoop.apache.org/docs/r3.3.4/hadoop-azure/abfs.html),
[Delta storage requirements](https://docs.delta.io/delta-storage/).

Canary cần: ensure/existence/read/write/list, checksum/replay, partial failure,
read-after-write, concurrent writer boundary và Delta create/read/MERGE/restart.
Kiểm auth expiry/access denied, rename/list semantics, TLS, DNS và credential
redaction. Không chạy hai backend writers cùng logical partition khi cutover.

## 3. Parity và go/no-go canary

1. Pause writer, settle queued/running jobs/outbox, đóng checkpoint; backup lake
   và operational metadata có restore evidence. Giữ source read-only để rollback.
2. Copy subset được duyệt cùng logs/manifests; so checksum từng object và exact
   object set với source ledger. Không ghi đè source hoặc tự VACUUM.
3. Đọc `DESCRIBE HISTORY delta.<path>` qua API/table path phù hợp runtime; so
   version/schema/rows. So `COUNT(*)`, `COUNT(DISTINCT article_id)` và anti-join
   `(article_id, content_hash, processing_version)` giữa hai backend.
4. Với chunks, so set `(chunk_id, article_id, content_hash, chunker_version)`;
   với Analytics, so từng aggregate dataset và manifest-listed files. So mentions
   theo actual distinct key, rejects theo lineage/reason; publication null giữ null.
5. Rebuild source-scoped serving; dùng existing reconciliation xác nhận missing/
   orphan/stale counts, DuckDB totals, sample deterministic lookup. Không gọi đó
   là evaluation retrieval/RAG hoặc benchmark cloud.
6. Thử rollback config về MinIO, rerun/read checkpoint và xác minh không duplicate.
   Sai bytes/log/schema/keys, access hoặc chi phí vượt giới hạn được duyệt → STOP.

## 4. Protection và retention

Không mặc định bật Blob versioning cho HNS: feature matrix hiện không hỗ trợ
versioning trên hierarchical namespace accounts. Review soft delete, lifecycle,
restore/backup và Delta retention như các cơ chế khác nhau; immutability policy
không được cản Delta writes/cleanup ngoài thiết kế.
[Azure feature support](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-feature-support-in-storage-accounts),
[data protection](https://learn.microsoft.com/en-us/azure/storage/blobs/data-protection-overview).

Object counts/bytes đã có observed snapshot; closed-writer source ledger, target
filesystem, TTL/retention, replica/SKU, authorized dataset và reviewer vẫn
**PENDING**. Không có copy/canary đã chạy ở Phase10.

Phân loại nội dung/PII, quyền sử dụng và retention cần owner review theo từng
nguồn; không suy quyền tái phân phối từ việc website public. Raw HTML giữ private,
không đưa vào Git/log/issue public; access/deletion/restore policy phải được chốt
trước khi copy dữ liệu thật lên target.
