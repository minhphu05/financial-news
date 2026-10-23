# Báo cáo vận hành thực tế từ trưa 23/10/2026 và chốt pilot bốn giờ

Ngày rà soát: **23/10/2026**. Mốc chốt báo cáo ngày là **22:58:35 +07:00**;
các kiểm tra trạng thái sau đó được lưu riêng trong evidence. Giờ trình bày dùng
`Asia/Ho_Chi_Minh`, JSON dùng UTC. Đây là kết quả chạy local, không phải benchmark.

## 1. Kết luận và phạm vi nghiệm thu

Phiên năm nguồn đã chạy đủ cửa sổ **14:04:58–18:04:58**, thu **50 mẫu** đến
**18:05:15** và tự pause DAG/tắt live cả năm nguồn. Không có collection error,
hard-stop hoặc thay boot ID trong mẫu. Tám chu kỳ theo lịch không overlap và đã
settle. Downstream xử lý thành công mọi batch được tạo trong phạm vi kiểm tra.

**Verdict pilot gốc vẫn PENDING**, do các failed/partial crawl của Tuổi Trẻ và
Báo Mới. Báo Mới tiếp tục gặp redirect không hỗ trợ ở sáu trong tám lượt theo
lịch; sửa xử lý lỗi giúp frontier tiến tiếp nhưng chưa làm nguồn này ổn định.
Không đổi verdict thành PASS sau khi loại bỏ lượt lỗi hoặc chỉ nhìn DAG xanh.

| Gate | Kết quả chốt | Ý nghĩa |
|---|---|---|
| Đủ thời gian và coverage pilot | Đạt phạm vi đo | Bốn giờ thực, 50 mẫu; không thay formal burn-in |
| Scheduling và cleanup | Đạt phạm vi đo | 8 actual scheduled DAG runs, không overlap; pause/disable PASS |
| Live ingestion năm nguồn | Có bằng chứng thực; có sự cố | Cả năm đã tạo dữ liệu và publish; chưa đạt trạng thái không lỗi |
| Downstream/reconciliation | PASS cho 45 batch từ trưa | Không có stage thất bại trong cohort; backlog live cuối kỳ bằng 0 |
| Pilot automatic acceptance | **PENDING** | Hai nguồn còn lịch sử failures/partial cần review |
| Formal Phase09 24h / 72h | **PENDING / PENDING** | Không có phiên đạt thời lượng tương ứng |
| Phase09 tổng thể / cloud | **Chưa DONE / NO-GO** | Security, restore và các điều kiện dài hạn chưa hoàn tất |

Source đối chiếu: `src/crawling/{burnin,reporting,jobs,policy}.py`,
`tools/phase9{,_pilot}.py`, `src/monitoring/exporter.py`, DAG crawler và alert rules.

## 2. Phương pháp và ba cửa sổ số liệu

1. **Từ trưa:** `[12:00:00, 22:58:35.936164)` ngày 23/10. Crawler ledger ghi
   live run đầu tiên trong cửa sổ lúc **13:56:50**; không suy là đã crawl từ 12h.
   Gồm khởi động hai nguồn, manual preflight, phục hồi và tám chu kỳ năm nguồn.
2. **Pilot:** start `2026-10-23T07:04:58.187749+00:00`, deadline UTC
   `11:04:58.187749`; mẫu cuối lúc `11:05:15.486888`. Bảng report pilot bên dưới
   dùng đúng report ở mẫu cuối, gồm phần settle sau deadline khoảng 17 giây.
   Các tác vụ đã hoàn tất trước deadline nên phần đuôi không thêm bài/batch.
3. **Scheduled-only:** chỉ tám actual scheduled runs bắt đầu từ **14:30 đến
   18:00** trong pilot. Không cộng manual repair/preflight vào kết quả này.

`reporting.aggregate` đếm crawl theo cohort **started_at trong [start,end)**,
nhưng reconciliation/latency theo **stage hoàn tất trong cửa sổ**. Vì thế các
tổng không luôn bằng nhau: Thanh Niên bắt đầu preflight lúc 14:04:58.050447,
sớm hơn pilot start khoảng **0,137 giây**, rồi publish trong pilot. Report pilot
ghi **8 bài mới Thanh Niên nhưng 9 reconciliation PASS**; đây là khác biệt grain,
không phải nhân bản hay mất dữ liệu. Tổng pilot là **38 new observations / 39
reconciliation PASS**, còn toàn cửa sổ từ trưa là **45 / 45**.

`new_articles` là phân loại observation của crawler. Đã kiểm thêm metrics Silver:
45 inserted articles, 0 invalid records trong 45 batch của cửa sổ từ trưa; không
dùng riêng crawler counter để khẳng định insert ở Silver. Không cộng các snapshot
metrics lũy kế giữa 50 mẫu. Không cộng phiên hai nguồn bị hủy vào bốn giờ năm nguồn.

## 3. Kết quả từ trưa đến mốc chốt

| Nguồn | Crawl runs bắt đầu | SUCCESS | FAILED | PARTIAL | SKIPPED | Bài mới | Batch/reconciliation PASS | Chunks mới |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CafeF | 12 | 12 | 0 | 0 | 0 | 12 | 12 | 90 |
| VnExpress | 12 | 12 | 0 | 0 | 0 | 12 | 12 | 51 |
| Tuổi Trẻ | 13 | 9 | 1 | 1 | 2 | 9 | 9 | 63 |
| Thanh Niên | 11 | 9 | 0 | 0 | 2 | 9 | 9 | 57 |
| Báo Mới | 13 | 3 | 1 | 7 | 2 | 3 | 3 | 9 |
| **Tổng** | **61** | **45** | **2** | **8** | **6** | **45** | **45** | **270** |

Sáu SKIPPED thuộc hai lượt scheduled lúc chuẩn bị, khi chỉ CafeF/VnExpress được
bật live; ba nguồn còn lại bị `source_live_disabled`. Không coi đây là sáu lần
HTTP lỗi. Có **10 scheduled DAG runs** trong toàn cửa sổ từ trưa, nhưng chỉ
**8** thuộc phiên năm nguồn bốn giờ; hai lượt đầu không chứng minh coverage năm nguồn.

45 batch đều `SUCCESS`, mỗi batch có publisher attempts=1 và đủ tám stage
`schema_validation`, `bronze_ingest`, `silver_merge`, `gold_rag_merge`,
`gold_analytics_refresh`, `duckdb_publish`, `qdrant_upsert`, `reconciliation`.
Ledger đã kiểm có **360 stage records SUCCESS**, không có stage thất bại trong
cohort này. Gold tạo thêm 45 documents và 270 chunks theo các fields
`run_documents_produced`/`run_chunks_produced`; không lấy tổng current ở mỗi batch
rồi cộng lại. Tất cả năm nguồn backlog live cuối kỳ=0, reconciliation FAIL=0.

### Snapshot sau lần publish cuối của từng nguồn

| Nguồn | Silver articles / Gold documents / DuckDB articles | Gold chunks / Qdrant points |
|---|---:|---:|
| CafeF | 13 / 13 / 13 | 93 / 93 |
| VnExpress | 13 / 13 / 13 | 58 / 58 |
| Tuổi Trẻ | 10 / 10 / 10 | 66 / 66 |
| Thanh Niên | 10 / 10 / 10 | 69 / 69 |
| Báo Mới | 4 / 4 / 4 | 23 / 23 |
| **Tổng** | **50 / 50 / 50** | **309 / 309** |

Đây là `counts` của **last successful reconciliation** theo source/crawl-v1,
bao gồm dữ liệu có sẵn trước trưa; không phải 50 bài mới hôm nay hoặc tổng mọi
collection/version trong Qdrant. Các checks missing/orphan/duplicate/stale trong
các snapshot này bằng 0. Lượt closeout đọc lại ledger, không chạy rebuild hay
fresh reconciliation ghi dữ liệu. Chưa có đánh giá chất lượng retrieval/RAG.

## 4. Kết quả riêng pilot và tám chu kỳ theo lịch

| Nguồn | Pilot started runs | Pilot FAILED / PARTIAL | Pilot bài mới | Pilot reconciliation PASS | Scheduled SUCCESS / PARTIAL | Scheduled bài mới |
|---|---:|---:|---:|---:|---:|---:|
| CafeF | 9 | 0 / 0 | 9 | 9 | 8 / 0 | 8 |
| VnExpress | 9 | 0 / 0 | 9 | 9 | 8 / 0 | 8 |
| Tuổi Trẻ | 11 | 1 / 1 | 9 | 9 | 8 / 0 | 8 |
| Thanh Niên | 8 | 0 / 0 | 8 | 9 | 8 / 0 | 8 |
| Báo Mới | 11 | 1 / 7 | 3 | 3 | 2 / 6 | 2 |
| **Tổng** | **48** | **2 / 8** | **38** | **39** | **34 / 6** | **34** |

Mỗi chu kỳ có năm source crawl runs. Tám DAG runs đều `success`, các task của
tám lượt này đều success ở Airflow. Tuy nhiên, job có thể trả structured
`PARTIAL` mà task vẫn thành công; preflight manual còn có hai task `failed`
nhưng DAG success vì các leaf publish dùng `all_done`. **DAG/task success không
thay kết quả nghiệp vụ trong crawler ledger.**

Actual start các cycle là 14:30, 15:00, 15:30, 16:00, 16:30, 17:00, 17:30 và
18:00; DAG run_id chứa mốc data interval trước đó 30 phút. Lượt cuối kết thúc
**18:03:43**. Không overlap, `max_active_runs=1`, `max_active_tasks=1`.

## 5. Sự cố và nguyên nhân

### 5.1. Redirect ở frontier Tuổi Trẻ và Báo Mới

Preflight năm nguồn ghi hai FAILED `not_a_supported_source_url`. Diagnostic lúc
xử lý sự cố cho thấy URL Tuổi Trẻ cũ về trang chủ, URL Báo Mới từ dạng `-c` sang
dạng `-r` ngoài article pattern. Response HTTP 200 vẫn có thể không phải article
được hỗ trợ. Ban đầu ValueError thoát khỏi per-URL handling, để URL còn NEW.

Bản sửa trong `jobs.crawl` chuyển lỗi final-URL validation thành nonretryable
`FetchError('unsupported_article_redirect', 200)`, ghi PERMANENT_FAILURE cho URL
đó. Không mở rộng host/pattern hoặc vượt robots. Hai bounded repair runs ghi
PARTIAL; recrawl một URL hợp lệ của mỗi nguồn và publish sau đó thành công.
Test redirect synthetic với PostgreSQL thật đã được lưu từ lượt sửa.

Tuổi Trẻ sau phục hồi đạt **8/8 scheduled SUCCESS**. Báo Mới chỉ **2/8 SUCCESS**,
sáu scheduled runs còn lại PARTIAL cùng mã `unsupported_article_redirect`,
HTTP status 200. Cộng repair, Báo Mới có bảy terminal redirect attempts; Tuổi Trẻ
có một. Không ghi nhận parser failures hay blocked/rate-limited trong metrics
cohort; không gọi tám redirect attempts này là tám HTTP 4xx/5xx.

Việc frontier không kẹt cùng URL đã được chứng minh ở phạm vi quan sát. Nhưng
giới hạn một article candidate/lượt khiến một URL bị từ chối có thể tiêu hết
lượt đó. Báo Mới không tạo bài sau **16:00:39** dù scheduler vẫn hoạt động. Đây
là suy giảm thu thập, không được che bởi pending=0: không tạo batch thì không
có downstream backlog. Chưa xác minh bằng request mới rằng mọi redirect sau đó
có cùng trang đích; ledger chỉ lưu mã/status. Closeout không crawl lại website.

### 5.2. Dashboard/CDC và cảnh báo tạm thời

Trong pilot đã sửa regex topic Kafka exporter và truy vấn CDC, recreate riêng
exporter; broker/CDC/pipeline không restart. Bảy dashboard/68 target queries đã
qua audit, có hướng dẫn đọc riêng. Chi tiết tại
[dashboard review](grafana-dashboard-review-2026-10-23.md).

Prometheus range query bước 60 giây trong pilot có warning
`DataQualityGateFailed` tại bốn hostname live: Báo Mới 1, Thanh Niên 2,
Tuổi Trẻ 5, VnExpress 6 **query points có firing**. Đây không phải số incident
hay số phút outage chính xác. Exporter chọn **latest attempt**, trả gate=0 khi
schema/Silver chưa cùng SUCCESS, kể cả RUNNING; rule `for: 0s` có thể cảnh báo
trong lúc xử lý bình thường. Ledger đã hoàn tất của 45 live batch không có stage
failed và Silver invalid_count=0; warning không đủ chứng minh dữ liệu lỗi.
Muốn quy mọi query point về một attempt cần lịch sử trạng thái chi tiết hơn.

Tại closeout còn năm firing series của `phase05-recovery.local`: quality,
Silver stale, hai Gold stale theo layer, no recent successful pipeline. Đây là
namespace drill lịch sử, giữ nguyên dữ liệu/rules. Không xóa lịch sử hoặc silence
để tạo dashboard xanh. Không thấy critical firing series trong query history
pilot đã lấy; kết luận bị giới hạn bởi độ phân giải 60 giây, không chứng minh
không từng có gián đoạn ngắn giữa các điểm.

## 6. Coverage, tài nguyên và lưu trữ

| Quan sát trong 50 mẫu | Kết quả | Giới hạn |
|---|---|---|
| Mẫu đầu → cuối | 14:05:01.538727 → 18:05:15.486888 | Lấy mẫu khoảng 5 phút; không phải continuous tracing |
| Khoảng cách mẫu lớn nhất | 308,713 giây | Dưới gate 750 giây; không chứng minh mọi request giữa hai mẫu |
| Monotonic từ start đến mẫu cuối | 14.413,948 giây | Trên 14.400 giây; cùng một boot ID |
| Collection errors / hard-stop samples | 0 / 0 | Theo collector đã triển khai |
| Sáu required scrape targets | Đều up=1 ở cả 50 mẫu | `up` là exporter/scrape availability, không full correctness |
| RAM workstation khả dụng | Min 2,19; median 5,09; max 7,37 GiB | Máy dùng chung; không là RAM riêng pipeline hoặc capacity benchmark |
| CPU utilization, rolling 5 phút | Min 4,34%; median 9,45%; max 32,79% | Theo 50 điểm; không là peak CPU tức thời |
| Host filesystem free | 303,55 → 296,26 GiB; min 296,26 | Không quy toàn bộ khoảng giảm 7,29 GiB cho dữ liệu tin tức |

| Selected prefixes | Bytes ở mẫu đầu | Bytes ở mẫu cuối | Chênh lệch |
|---|---:|---:|---:|
| CafeF | 84.154.298 | 86.493.198 | +2.338.900 |
| VnExpress | 1.473.517 | 4.887.604 | +3.414.087 |
| Tuổi Trẻ | 593.263 | 6.236.970 | +5.643.707 |
| Thanh Niên | 887.153 | 4.504.529 | +3.617.376 |
| Báo Mới | 222.900 | 645.120 | +422.220 |
| **Tổng chênh lệch** | — | — | **+15.436.290** |

Listing các prefix được chọn đều complete trong 50 mẫu theo cap scanner. Phạm
vi gồm live Landing, same-host Bronze và Silver/Gold current; có dữ liệu cũ,
không bao trùm mọi snapshot/operations/model cache/Docker/host filesystem. Đây
là **chênh snapshot**, không gross bytes đã ghi hay phép đo dung lượng production.

Latency Landing→Silver p50 theo nguồn CafeF/VnExpress/Tuổi Trẻ/Thanh Niên/Báo Mới
lần lượt **60,057 / 114,124 / 125,380 / 176,456 / 133,819 giây**, số mẫu
**9 / 9 / 9 / 9 / 3**. Landing→Gold RAG p50 tương ứng **67,223 / 124,157 /
132,090 / 184,257 / 141,994 giây**. Đây là các batch/stage hoàn tất trong report
pilot, gồm thời gian chờ điều phối; không latency mạng, embedding riêng hoặc
phản hồi người dùng. **p95=N/A** vì từng nguồn dưới 20 mẫu. Không suy thành SLO.

Alert-history query-step coverage của pilot là **241/241** ở report mẫu cuối.
Toàn cửa sổ 12:00–22:58 có **547/659** query steps với Prometheus self-scrape
data, nên **không có bằng chứng alert liên tục từ trưa**. Coverage query-step
không tương đương raw scrape uptime, không tự gán thời gian thiếu cho pipeline
outage. Mẫu resource riêng bốn giờ vẫn có đủ coverage nêu trên.

## 7. Dừng đúng hạn và trạng thái sau pilot

Deadline UTC `11:04:58.187749`. Hai cleanup attempts có `reason=deadline`, đều
PASS, ghi lúc **18:05:06** và **18:05:11**. Đây là thời điểm ghi sau chuỗi lệnh,
không phải khẳng định pause hoàn tất ngay đúng giây deadline. Theo implementation,
source gate `live_until` từ chối lượt live mới kiểm tra sau deadline độc lập với
collector; không hủy các request đã bắt đầu. Mẫu cuối: DAG paused,
active scheduled runs=[], không task đang chạy được quan sát; last run đã settle.

Đối chiếu lúc closeout: DAG vẫn paused, năm source live_enabled=false, deadline
đã hết hạn; cron vẫn `*/30 * * * *`, global scheduled-live switch vẫn true và
limit=1 trong scheduler process. Đây là cấu hình giữ lại từ pilot, **chưa phục
hồi cron/manual hoàn toàn**. Các gate pause/source-off/expiry đang ngăn live.
Không recreate scheduler hoặc sửa `.env` trong lượt phân tích này. Cần chuẩn bị
cấu hình có chủ đích trước phiên sau; unpause riêng lẻ không đủ bật nguồn.

Trong cửa sổ từ deadline đến **22:58:35**, ledger không có live crawl run mới
hoặc downstream reconciliation mới của năm nguồn. Không diễn giải thành không có
mọi HTTP request: review robots/diagnostic ngoài ledger không được đo đầy đủ.
Transient units/timer pilot không còn trong danh sách lúc closeout; điều này
phù hợp phiên đã kết thúc nhưng bằng chứng hoàn thành là samples/stop/report.
Monitoring health hiện PASS, stack vẫn chạy để xem dữ liệu/dashboard.

`runtime.json` ban đầu chỉ là launch metadata và còn ghi STARTED sau khi hết giờ.
Đã giữ bản gốc `runtime.launch.json`, cập nhật trạng thái CLOSED/PENDING kèm
review timestamp và đường dẫn bằng chứng. Không sửa report tự sinh lúc 18:05
hoặc tạo thêm sample lịch sử bằng thời điểm closeout.

## 8. Tồn đọng và thứ tự xử lý

1. **Báo Mới:** review các terminal redirects/frontier và mẫu URL hiện tại trong
   một nhiệm vụ có opt-in riêng; cân nhắc giới hạn riêng cho candidate attempts
   và accepted articles, kèm cap tổng HTTP/robots/pacing. Chưa triển khai trong
   closeout; không tăng tải hoặc chấp nhận mọi redirect để đạt đủ bài.
2. **B1 năm nguồn:** đã có successful live path của cả năm, nhưng lượt preflight
   không hoàn toàn sạch. Sau sửa cần controlled rerun và review lại kết quả;
   không ghi B1 overall PASS chỉ từ việc mỗi nguồn từng publish thành công.
3. **Alert semantics:** tách pending/running khỏi failed validation hoặc chọn
   completed attempts có ngữ cảnh. Cần tests firing/resolution trước đổi rule;
   chưa sửa rule/threshold trong lượt phân tích.
4. **Backup/restore:** đã có MinIO archive và PostgreSQL dump private, checksum
   và archive/TOC validation; **chưa full restore rehearsal**, chưa chứng minh DR.
5. **Formal 24h → 72h:** vẫn PENDING. Pilot có can thiệp sửa code/dashboard lúc
   đầu và traffic rất nhỏ, không thay kiểm chứng unattended nhiều ngày/HA.
6. **Cloud:** giữ NO-GO; owner credential invalidation, history remediation,
   advisory closure, sign-off và các gate Phase10 vẫn chưa đạt. Không deploy.

## 9. Evidence và khả năng kiểm tra lại

| Nhóm | Đường dẫn local (ignored) | Dùng để kiểm |
|---|---|---|
| Phiên gốc | `artifacts/phase9/pilot/pilot-20261023T070458Z-474d3e.{json,samples.json,report.json,stop.json,shutdown-attempts.jsonl}` | Duration, PENDING, shutdown, từng mẫu |
| Từ trưa / sau deadline | `artifacts/phase9/pilot/closeout/{noon-to-review,after-deadline}.json` | Closed windows, source outcomes, alert coverage |
| Ledger chi tiết | `artifacts/phase9/pilot/closeout/ledger-detail.json` | Runs/attempts/batches/stage metrics/source state; không article bodies/secrets |
| Airflow | `artifacts/phase9/pilot/closeout/{airflow-detail,current-scheduler}.json` | Task vs run states, actual start/settle, paused |
| Config sau dừng | `artifacts/phase9/pilot/closeout/current-config.json` | Live false, retained cron/global flag, expiry; không secret |
| Alerts | `artifacts/phase9/pilot/closeout/{pilot-alert-series,current-alerts}.json` | Full labels, sampled firing history/current |
| Tổng hợp | `artifacts/phase9/pilot/closeout/{summarize.py,summary.json,evidence-manifest.json}` | Tính lại từ saved evidence, file integrity hashes |
| Incident/review/tests | `artifacts/phase9/pilot/live-redirect-incident.json`, repair/regression logs; `artifacts/phase9/dashboard-review/` | Lượt sửa và kiểm chứng trước closeout |

Clone mới có thể không có ignored artifacts; khi đó báo cáo này là **báo cáo lịch
sử**, không phải bằng chứng máy đọc tái kiểm được ở clone đó. Không đưa raw dump,
HTML, secrets hoặc private backup lên Git để bổ sung bằng chứng. Lượt closeout
chỉ đọc runtime/ledger/Prometheus và cập nhật tài liệu/evidence, không chạy thêm
live crawl, fault injection hoặc full acceptance; không commit/push/deploy.
