# Cách đọc 7 dashboard Grafana của financial-news

**Sau phiên 23/10:** xem [báo cáo phân tích chạy thực tế](phase9-pilot-report-2026-10-23.md).
Pilot đã dừng, live TẮT là dự kiến. Chọn absolute range 14:04:58–18:05:15 để xem
lịch sử; số lũy kế không phải số bài trong range. Report PENDING dù tám DAG runs
xanh vì Báo Mới có sáu scheduled PARTIAL. Cảnh báo quality thoáng qua cần đối
chiếu trạng thái stage, không tự quy thành dữ liệu hỏng.

Cập nhật ngày **23/10/2026**, theo dashboard JSON đã provision và metrics thực tế.
Tài liệu này dùng để vận hành/demo local. Dashboard giúp quan sát hệ thống, không
là bằng chứng tự động rằng burn-in, cloud readiness hoặc chất lượng RAG đã đạt.

## 1. Bắt đầu từ đâu?

| Thứ tự | Dashboard | Câu hỏi cần trả lời |
|---|---|---|
| 1 | [Overview](http://localhost:3000/d/financial-news-overview) | Metrics, scheduler và các dịch vụ có đang hoạt động? |
| 2 | [Multisource Crawling](http://localhost:3000/d/news-crawler) | Từng nguồn live có chạy, bị chặn hoặc tồn đọng không? |
| 3 | [Operations](http://localhost:3000/d/financial-news-pipeline-operations) | Run/stage nào đang xử lý lâu hoặc từng thất bại? |
| 4 | [Data Quality](http://localhost:3000/d/financial-news-data-quality) | Reject/dedup/gate và đối soát có vấn đề gì? |
| 5 | [Freshness](http://localhost:3000/d/financial-news-freshness) | Lần cập nhật thành công gần nhất của từng lớp là khi nào? |
| 6 | [CDC](http://localhost:3000/d/financial-news-metadata-cdc) | Thay đổi metadata có đi qua PostgreSQL–Debezium–Kafka? |
| 7 | [Resources](http://localhost:3000/d/financial-news-local-resources) | Máy dùng chung có áp lực CPU/RAM/đĩa không? |

Nếu chỉ theo dõi pilot: mở **Overview → Crawling**, sau đó mới mở dashboard
chuyên sâu theo vấn đề. Các nút điều hướng ở đầu mỗi dashboard giữ thời gian
nhưng trả bộ lọc về mặc định, tránh truyền nhầm source key sang hostname.

## 2. Quy ước đọc chung

### Thời gian, bộ lọc và legend

- Giờ hiển thị là `Asia/Ho_Chi_Minh` (+07:00). Mặc định **Last 1 hour**, refresh
  **30s**. Muốn xem trọn pilot, đặt From `2026-10-23 14:04:58`, To `2026-10-23 18:05:15` khi xem phiên đã kết thúc; không
  hiểu phần thời gian chưa tới như dữ liệu đã thu. Sau khi hết phiên, dùng cửa sổ
  đóng theo actual start/end trong report, không chỉ theo giờ dự kiến.
- **Ô số và bảng** lấy snapshot tại **cuối time range**. Nếu To là một thời điểm
  quá khứ, đó là trạng thái quá khứ, không phải hệ thống hiện tại. **Đồ thị** là
  diễn biến trong khoảng chọn. Một đường nằm ngang có thể là ledger chưa đổi.
- Pipeline mặc định `financial_news_incremental`; nguồn hostname mặc định là năm
  website. Chọn một nguồn khi đồ thị quá nhiều đường. Metrics pipeline hiện chưa
  có nhãn live/fixture; fixture dùng cùng hostname có thể còn trong số này.
- Dashboard **Crawling** mặc định `data_kind=live`, cả năm source key. Chọn
  `fixture` để xem kiểm thử riêng. Bộ lọc lớp chỉ tác động panel downstream;
  cờ live config và RAM toàn máy không phụ thuộc live/fixture.
- Freshness có bộ lọc lớp cho biểu đồ/bảng, mặc định `silver`; các ô số từng
  lớp vẫn hiển thị đầy đủ.
- CDC có bộ lọc topic. Resources và các ô sức khỏe toàn stack không lọc theo
  nguồn tin. Tổng vector native Qdrant cũng bao gồm mọi collection.
- Legend phía dưới đồ thị ghi đúng nhãn, ví dụ `cafef · FAILED` hay
  `cafef.vn · silver`. Cột `Last *` là điểm cuối không null của đường trong
  khoảng chọn; không là trung bình, tổng hay số sự kiện mới. Tooltip ⓘ giải
  thích panel. Bấm legend để chọn/ẩn đường, kéo trên đồ thị để zoom thời gian.

| Source key ở Crawling | Hostname ở pipeline |
|---|---|
| `cafef` | `cafef.vn` |
| `vnexpress` | `vnexpress.net` |
| `tuoitre` | `tuoitre.vn` |
| `thanhnien` | `thanhnien.vn` |
| `baomoi` | `baomoi.com` |

### Số 0, màu và “Chưa có số liệu”

- **0 đo được** khác **No data/Chưa có số liệu**. Trước khi kết luận không có lỗi,
  kiểm ô exporter collection và scrape targets. Prometheus mất kết nối thường
  hiện lỗi truy vấn, không được coi là không có cảnh báo.
- Health scrape/collection: xanh `OK` ứng với 1, đỏ `LỖI` ứng với 0.
  Schema/publish/reconciliation dùng `SUCCESS`/`PASS` hoặc `CHƯA ...` màu cam vì
  latest attempt có thể đang chạy; cần xem trạng thái stage trước khi kết luận lỗi.
  Block latch dùng `KHÔNG`/`BỊ KHÓA`; slot CDC dùng `ACTIVE`/`INACTIVE`.
  Cờ cho phép live dùng **BẬT/TẮT**, màu xanh dương/xám; nó không là health check.
- Pending/exhausted: 0 hiển thị xanh, giá trị dương cam cần xem thêm; batch
  có thể chỉ đang chạy. Đây là phân biệt trạng thái, không là SLA được benchmark.
- Duration/freshness/ratio chủ yếu dùng màu trung tính. Không tự suy một ngưỡng
  production từ màu đường hoặc kích thước số.
- Không có consumer group/committed offsets thì consumer lag **N/A** là đúng,
  không tự đổi thành 0. Không có backlog thì pending age chỉ được điền 0 khi
  pending snapshot xác nhận bằng 0; backlog có mà thiếu mốc thời gian vẫn là N/A.

### Các loại số đếm thường bị nhầm

| Loại | Cách hiểu đúng | Không được hiểu là |
|---|---|---|
| `_runs_total`, `_articles_total`, stage attempts | Snapshot lũy kế ledger PostgreSQL | Số mới phát sinh trong Last 1 hour hoặc riêng pilot |
| `financial_news_pipeline_records` | Giá trị attempt stage gần nhất theo loại số liệu | Toàn corpus tại một checkpoint thống nhất |
| `silver_articles`, Gold/reconciliation current counts | Số current được stage/đối soát ghi nhận | Bằng Bronze batch input ở mọi thời điểm |
| Duration | Run/attempt/batch cụ thể được ghi nhận | p95, throughput hay benchmark |
| Freshness/age | Thời gian từ mốc successful stage hoặc crawl | Độ mới nội dung bài báo, published_at hoặc chất lượng tìm kiếm |
| Qdrant vectors | Vector/chunk; native metric là toàn instance | Số article của năm nguồn |
| Kafka offset/WAL bytes | Metadata transport/replication position | Số bài tin đã xử lý |

Các metric `_total` của exporter dự án là **Gauge trên ledger lưu bền**, không
bảo đảm counter đơn điệu: run đổi trạng thái, retry, fixture cleanup có thể làm
nhóm giảm. Không dùng `increase()`/`rate()` để tự tính số run của pilot. Báo cáo
cửa sổ đóng từ ledger mới là nguồn đúng cho số liệu theo khoảng thời gian.

| Trạng thái | Ý nghĩa khi điều tra |
|---|---|
| `SUCCESS` | Bước đó hoàn tất; crawl SUCCESS chưa đủ chứng minh publication/đối soát SUCCESS |
| `RUNNING` | Đang chạy; metrics attempt có thể chưa đầy đủ |
| `SKIPPED` | Không thực hiện theo policy/lựa chọn nguồn/cooldown; không là crawl thành công |
| `PARTIAL` | Có lỗi URL/parse hoặc chỉ hoàn thành một phần, phải đọc attempt/metrics |
| `FAILED` | Lượt đã thất bại; có thể sau đó đã được phục hồi |
| `BLOCKED` | Bị chặn; không clear latch/bypass nếu chưa review |

Run pipeline (Operations) và run crawl (Crawling) có mẫu số khác nhau: crawl có
thể lỗi trước khi tạo batch/pipeline run, nên pipeline SUCCESS 100% không chứng
minh crawl SUCCESS 100%.

DAG có publish `trigger_rule=all_done`; DAG/terminal task xanh **không chứng minh
mọi crawl task đều xanh**. Mở Grid/Graph của Airflow và đọc task cụ thể.

## 3. Đọc từng dashboard và từng panel

### 3.1. Financial News Platform — Overview — Sức khỏe tổng thể

Bắt đầu bằng targets và collection, rồi scheduler/CDC. Khi cảnh báo >0, đọc bảng alert để biết source. Một cảnh báo fixture cũ không tự chứng minh nguồn pilot đang lỗi.

[Mở dashboard](http://localhost:3000/d/financial-news-overview) · [JSON provision](../monitoring/grafana/provisioning/dashboards/json/1-financial-news-overview.json)

| Panel ID | Panel đang hiển thị | Cách đọc và giới hạn |
|---|---|---|
| 1 | **Dịch vụ: Prometheus có scrape được không?** (Số đếm/trạng thái) | 1 = scrape thành công; 0 = scrape lỗi. Exporter up chưa chứng minh database/ứng dụng khỏe: đọc thêm các ô collection, scheduler và CDC. |
| 2 | **Exporter đọc PostgreSQL thành công?** (Số đếm/trạng thái) | 1 = lần đọc read-only metadata gần nhất thành công. 0 hoặc thiếu dữ liệu: các panel dữ liệu không đủ tin cậy. |
| 3 | **Airflow scheduler khỏe?** (Số đếm/trạng thái) | Trạng thái từ Airflow health API. 1 không có nghĩa DAG đang unpause hoặc nguồn đang được phép live. |
| 4 | **Run pipeline theo trạng thái — lũy kế ledger** (Số đếm/trạng thái) | Lũy kế/snapshot từ PostgreSQL, không phải số phát sinh trong khoảng thời gian đang chọn; đổi time range chỉ đổi diễn biến hiển thị. Giữ cả lỗi đã phục hồi, không lấy increase()/rate() như counter đơn điệu. Lọc theo pipeline/hostname ở đầu trang. Metrics pipeline là snapshot ledger, có thể gồm fixture cùng hostname; chỉ dashboard Crawling có bộ lọc live/fixture. Không suy ra số bài trong cửa sổ pilot từ số lũy kế. |
| 5 | **Tuổi cập nhật thành công theo lớp** (Thời gian (giây tự đổi phút/giờ)) | Số giây kể từ successful stage gần nhất. Tăng giữa các lần xử lý là bình thường; không phải tuổi xuất bản bài báo. Lọc theo pipeline/hostname ở đầu trang. Metrics pipeline là snapshot ledger, có thể gồm fixture cùng hostname; chỉ dashboard Crawling có bộ lọc live/fixture. Không suy ra số bài trong cửa sổ pilot từ số lũy kế. |
| 6 | **Cảnh báo đang firing — toàn stack** (Số đếm/trạng thái) | 0 chỉ khi truy vấn Prometheus đang có dữ liệu và không có alert firing. Bao gồm cảnh báo dataset kiểm thử/lịch sử; xem bảng phía dưới. |
| 7 | **Vector Qdrant — tất cả collection** (Số đếm/trạng thái) | Native Qdrant metric: tổng vector toàn instance, gồm cả fixture/collection kiểm thử. Không phải số article và không lọc theo hostname. |
| 8 | **Lần publish DuckDB gần nhất thành công?** (Số đếm/trạng thái) | 1 = latest publish stage SUCCESS, 0 = attempt đang chạy hoặc lỗi. Đây là trạng thái ledger, không phải probe mở file DuckDB hiện tại. Lọc theo pipeline/hostname ở đầu trang. Metrics pipeline là snapshot ledger, có thể gồm fixture cùng hostname; chỉ dashboard Crawling có bộ lọc live/fixture. Không suy ra số bài trong cửa sổ pilot từ số lũy kế. |
| 9 | **Debezium connector RUNNING?** (Số đếm/trạng thái) | Chỉ CDC metadata, không là hàng đợi article. Xem dashboard CDC để kiểm task/slot/offset. |
| 10 | **Chi tiết cảnh báo đang firing** (Số đếm/trạng thái) | Cảnh báo toàn stack. source=phase05-recovery.local là dataset fault-injection cũ, không phải nguồn live. Không xóa alert để làm dashboard xanh. |

### 3.2. Financial News Pipeline — Operations — Vận hành pipeline

Chọn nguồn cần xem. Duration và record volumes là latest attempts; failed attempts lũy kế vẫn còn sau recovery. Đối chiếu run/stage với Airflow và PostgreSQL, không suy số run mới từ đoạn đường nằm ngang.

[Mở dashboard](http://localhost:3000/d/financial-news-pipeline-operations) · [JSON provision](../monitoring/grafana/provisioning/dashboards/json/2-financial-news-pipeline-operations.json)

| Panel ID | Panel đang hiển thị | Cách đọc và giới hạn |
|---|---|---|
| 1 | **Thời gian run hoàn tất gần nhất** (Thời gian (giây tự đổi phút/giờ)) | Runner started_at → finished_at; không gồm thời gian chờ Airflow. Một đường FAILED cũ có thể tồn tại cạnh SUCCESS mới. Không phải histogram/p95. |
| 2 | **Thời gian attempt stage gần nhất** (Thời gian (giây tự đổi phút/giờ)) | Snapshot attempt gần nhất của từng stage, không phải tổng thời gian của mọi stage trong cửa sổ. Chọn một nguồn để xem rõ. |
| 3 | **Run theo trạng thái — lũy kế ledger** (Số đếm/trạng thái) | Lũy kế/snapshot từ PostgreSQL, không phải số phát sinh trong khoảng thời gian đang chọn; đổi time range chỉ đổi diễn biến hiển thị. Giữ cả lỗi đã phục hồi, không lấy increase()/rate() như counter đơn điệu. |
| 4 | **Tỷ lệ run hoàn tất SUCCESS — toàn ledger** (Tỷ lệ 0–1 hiển thị %) | Loại RUNNING khỏi mẫu số. Không phải success rate riêng pilot hay SLO. Chưa có completed run: không tính 0%/100% giả. |
| 5 | **Record counts của attempt stage gần nhất** (Số đếm/trạng thái) | Bảng snapshot hiện tại: nguồn, stage, loại số liệu, giá trị. input/output/chunk/aggregation là đơn vị khác nhau, không cộng tất cả thành tổng bài. |
| 6 | **Nhịp scheduler nhận được / giây** (Nhịp/giây) | Counter native StatsD đổi sang rate cửa sổ 2 phút. Có reset khi restart; không phải số DAG run. Cần tối thiểu hai mẫu scrape. |
| 7 | **Attempt stage thất bại — lũy kế, kể cả đã phục hồi** (Số đếm/trạng thái) | Lũy kế/snapshot từ PostgreSQL, không phải số phát sinh trong khoảng thời gian đang chọn; đổi time range chỉ đổi diễn biến hiển thị. Giữ cả lỗi đã phục hồi, không lấy increase()/rate() như counter đơn điệu. Giá trị >0 không tự chứng minh stage hiện tại đang lỗi. |

### 3.3. Financial News Pipeline — Data Quality — Chất lượng và đối soát

Xem invalid và trạng thái gate cùng nhau. Duplicate có thể là dedup hoạt động đúng. Article/document/chunk là đơn vị khác nhau. Gate = 0 trong lúc stage RUNNING cần chờ/đọc trạng thái, không kết luận mất dữ liệu.

[Mở dashboard](http://localhost:3000/d/financial-news-data-quality) · [JSON provision](../monitoring/grafana/provisioning/dashboards/json/3-financial-news-data-quality.json)

| Panel ID | Panel đang hiển thị | Cách đọc và giới hạn |
|---|---|---|
| 1 | **Bản ghi invalid — Silver attempt gần nhất** (Số đếm/trạng thái) | Số reject ở latest Silver attempt, không phải tổng reject toàn kho. Khi attempt đang chạy hoặc chưa có metrics, số 0 chưa chứng minh dữ liệu đã được kiểm. |
| 2 | **Bản ghi duplicate — Silver attempt gần nhất** (Số đếm/trạng thái) | Số bản ghi loại trùng của attempt gần nhất. Giá trị dương có thể là hoạt động dedup bình thường. |
| 3 | **Tỷ lệ duplicate — Silver attempt gần nhất** (Tỷ lệ 0–1 hiển thị %) | duplicate/input của latest attempt. Không là tỷ lệ trùng toàn corpus hoặc toàn cửa sổ. |
| 4 | **Schema + Silver attempt gần nhất SUCCESS?** (Số đếm/trạng thái) | 1 khi cả latest schema_validation và silver_merge là SUCCESS. 0 có thể do đang chạy, chưa đủ stage hoặc lỗi; không đồng nghĩa mọi article đạt chất lượng nội dung. |
| 5 | **Đối soát gần nhất PASS?** (Số đếm/trạng thái) | 1 khi latest reconciliation SUCCESS và metrics.status=PASS; 0 nếu đang chạy/lỗi. So Silver/Gold/Qdrant/DuckDB theo contract; không đánh giá chất lượng câu trả lời RAG. |
| 6 | **Bronze/Silver: số của attempt gần nhất** (Số đếm/trạng thái) | input/output/invalid/duplicate là hiệu ứng batch; silver_articles là tổng current table. Không áp một đẳng thức cho các snapshot khác stage/thời điểm. |
| 7 | **Silver/Gold: article, document và chunk** (Số đếm/trạng thái) | Một article có thể tạo nhiều chunk. So current counts tại reconciliation; không kỳ vọng chunks = articles. Chọn một nguồn để tránh nhiều đường. |

### 3.4. Financial News Pipeline — Freshness — Độ mới của lần xử lý

Đọc ô hiện tại trước, rồi đồ thị. Đồ thị có thể còn mốc cũ trước khi nguồn được xử lý, làm trục Y lớn; chọn nguồn/zoom cửa sổ phù hợp, không xóa dữ liệu lịch sử để làm biểu đồ đẹp.

[Mở dashboard](http://localhost:3000/d/financial-news-freshness) · [JSON provision](../monitoring/grafana/provisioning/dashboards/json/4-financial-news-freshness.json)

| Panel ID | Panel đang hiển thị | Cách đọc và giới hạn |
|---|---|---|
| 1 | **Tuổi cập nhật theo nguồn và lớp** (Thời gian (giây tự đổi phút/giờ)) | Đường sawtooth giảm khi stage thành công, tăng khi chờ lượt mới. Khoảng trắng là thiếu mẫu, không nối qua outage. |
| 2 | **Tuổi cập nhật Bronze** (Thời gian (giây tự đổi phút/giờ)) | Snapshot tại cuối time range, tính từ latest successful stage. Không có ngưỡng SLA mới được suy diễn từ giá trị này. |
| 3 | **Tuổi cập nhật Silver** (Thời gian (giây tự đổi phút/giờ)) | Snapshot tại cuối time range, tính từ latest successful stage. Không có ngưỡng SLA mới được suy diễn từ giá trị này. |
| 4 | **Tuổi cập nhật Gold RAG** (Thời gian (giây tự đổi phút/giờ)) | Snapshot tại cuối time range, tính từ latest successful stage. Không có ngưỡng SLA mới được suy diễn từ giá trị này. |
| 5 | **Tuổi cập nhật Qdrant** (Thời gian (giây tự đổi phút/giờ)) | Snapshot tại cuối time range, tính từ latest successful stage. Không có ngưỡng SLA mới được suy diễn từ giá trị này. |
| 6 | **Tuổi cập nhật Gold Analytics** (Thời gian (giây tự đổi phút/giờ)) | Snapshot tại cuối time range, tính từ latest successful stage. Không có ngưỡng SLA mới được suy diễn từ giá trị này. |
| 7 | **Tuổi cập nhật DuckDB** (Thời gian (giây tự đổi phút/giờ)) | Snapshot tại cuối time range, tính từ latest successful stage. Không có ngưỡng SLA mới được suy diễn từ giá trị này. |
| 8 | **Mốc successful stage gần nhất — giờ Việt Nam** (Ngày giờ Việt Nam) | Epoch giây từ exporter được nhân 1000 cho Date/Time của Grafana. Đây là thời điểm xử lý, không phải published_at của article. |

### 3.5. Metadata Control Plane — CDC — CDC của metadata

Broker/connector/task/slot trước, offsets/lag sau. Không có metadata thay đổi thì CDC im lặng là bình thường. News article bodies không qua Kafka. Đổi cờ source/pipeline config mới là loại sự kiện của luồng này.

[Mở dashboard](http://localhost:3000/d/financial-news-metadata-cdc) · [JSON provision](../monitoring/grafana/provisioning/dashboards/json/5-financial-news-metadata-cdc.json)

| Panel ID | Panel đang hiển thị | Cách đọc và giới hạn |
|---|---|---|
| 1 | **Kafka metadata probe thành công?** (Số đếm/trạng thái) | 1 = bounded metadata request thành công. |
| 2 | **PostgreSQL chấp nhận kết nối?** (Số đếm/trạng thái) | Dùng pg_up để kiểm database, không chỉ HTTP scrape của exporter. |
| 3 | **Debezium connector RUNNING?** (Số đếm/trạng thái) | Connect REST: connector state. |
| 4 | **Tất cả Debezium task RUNNING?** (Số đếm/trạng thái) | Connect REST: toàn bộ tasks RUNNING. |
| 5 | **Replication slot đang active?** (Số đếm/trạng thái) | 1 = slot được sử dụng; cần đọc cùng lag và connector/task. |
| 6 | **Khoảng WAL tới confirmed flush LSN** (Dung lượng) | pg_current_wal_lsn - confirmed_flush_lsn, đơn vị bytes. Có thể gồm WAL không thuộc bảng CDC; không phải số article/Kafka backlog. Quan sát xu hướng, không tự đặt SLA. |
| 7 | **High watermark của topic/partition** (Số đếm/trạng thái) | Offset kế tiếp/high watermark, không phải số bài hoặc số event trong time range. Snapshot/schema/tombstone cũng tạo record. |
| 8 | **Lag của consumer group đã commit offset** (Số đếm/trạng thái) | Chưa có group/offset hợp lệ: No data là thiếu phép đo, không đổi thành lag=0. Exporter probe không commit offset; Debezium producer không tạo consumer group. |
| 9 | **Tuổi event metadata gần nhất** (Thời gian (giây tự đổi phút/giờ)) | Tuổi Kafka record có timestamp gần nhất. Không có metadata changes thì tuổi tăng bình thường; không suy thành CDC end-to-end latency. |
| 10 | **Số partition metadata theo Kafka exporter** (Số đếm/trạng thái) | Số partition do kafka-exporter quan sát cho từng topic. Regex dùng biến topic hợp lệ; thiếu metric phải kiểm exporter/topic filter. |

### 3.6. Local Infrastructure — Resources — Tài nguyên máy local

Đây là workstation dùng chung. Nhiều app ngoài đồ án ảnh hưởng CPU/RAM. Network chưa đo đúng toàn bộ NIC host do bridge namespace; bảng cgroup chưa ánh xạ tên Docker container. Không cộng cgroup cha/con.

[Mở dashboard](http://localhost:3000/d/financial-news-local-resources) · [JSON provision](../monitoring/grafana/provisioning/dashboards/json/6-financial-news-local-resources.json)

| Panel ID | Panel đang hiển thị | Cách đọc và giới hạn |
|---|---|---|
| 1 | **CPU bận — toàn workstation** (Phần trăm 0–100) | Trung bình mọi CPU từ node exporter, gồm ứng dụng khác. Cửa sổ rate 2 phút; không phải CPU riêng Spark. |
| 2 | **RAM sử dụng — toàn workstation** (Dung lượng) | MemTotal - MemAvailable, không phải RSS của pipeline; khác used theo công thức cache khác của công cụ hệ thống. |
| 3 | **Network nhận — namespace node-exporter** (Bytes/giây) | Compose dùng bridge network; /proc/net quan sát namespace exporter, hiện chỉ eth0. Không đại diện tải mạng card Wi-Fi/Ethernet host. |
| 4 | **Network gửi — namespace node-exporter** (Bytes/giây) | Cùng giới hạn namespace như network nhận. Không là lưu lượng crawler riêng. |
| 5 | **Dung lượng còn trống theo filesystem** (Dung lượng) | Dung lượng khả dụng từ node exporter. Đối chiếu df ở đúng filesystem; không phải riêng kích thước MinIO bucket. |
| 6 | **Top 15 cgroup RAM — không cộng parent/child** (Dung lượng) | cAdvisor trên máy này chưa có nhãn tên Docker container. Giữ Cgroup ID để nhận diện, gồm root/user.slice và nhóm con chồng lặp; không cộng các hàng. |
| 7 | **RAM khả dụng — toàn workstation** (Dung lượng) | Dùng để theo dõi áp lực bộ nhớ. Hard-stop pilot có floor vận hành riêng, không phải cấu hình capacity đã benchmark. |
| 8 | **Tỷ lệ RAM đang sử dụng** (Phần trăm 0–100) | Phần trăm toàn workstation, không tự gán ngưỡng production. |
| 9 | **Telemetry tài nguyên đang scrape được?** (Số đếm/trạng thái) | 0/No data: các đồ thị tài nguyên có thể thiếu mẫu. Không nối dữ liệu qua outage. |

### 3.7. Financial News — Multisource Crawling — Thu thập đa nguồn live

Trang chính để theo dõi pilot. Mặc định live, All = năm nguồn. Đọc hàng trên: collection, cờ live, block, pending, tuổi crawl và exhausted; sau đó xem đồ thị của riêng một nguồn để điều tra.

[Mở dashboard](http://localhost:3000/d/news-crawler) · [JSON provision](../monitoring/grafana/provisioning/dashboards/json/7-news-crawler.json)

| Panel ID | Panel đang hiển thị | Cách đọc và giới hạn |
|---|---|---|
| 1 | **Run crawl theo trạng thái — lũy kế ledger** (Số đếm/trạng thái) | Lũy kế/snapshot từ PostgreSQL, không phải số phát sinh trong khoảng thời gian đang chọn; đổi time range chỉ đổi diễn biến hiển thị. Giữ cả lỗi đã phục hồi, không lấy increase()/rate() như counter đơn điệu. SUCCESS crawl chưa chứng minh Gold/serving đã phát hành. |
| 2 | **Kết quả article — lũy kế ledger** (Số đếm/trạng thái) | Lũy kế/snapshot từ PostgreSQL, không phải số phát sinh trong khoảng thời gian đang chọn; đổi time range chỉ đổi diễn biến hiển thị. Giữ cả lỗi đã phục hồi, không lấy increase()/rate() như counter đơn điệu. fetched có thể parse lỗi; một URL được fetch nhiều lần không phải nhiều article duy nhất. |
| 3 | **Frontier: số URL hiện tại theo trạng thái** (Số đếm/trạng thái) | Snapshot tập URL NEW/RETRY/SUCCESS/PERMANENT_FAILURE/PARSE_FAILURE/BLOCKED. Không phải tất cả đều due; phải xem next_eligible_at/cooldown trong ledger. |
| 4 | **Batch chưa publish — diễn biến** (Số đếm/trạng thái) | 0 = không có batch chưa SUCCESS ở snapshot. >0 có thể đang chạy/retry hoặc lỗi; xem pending age và attempts. |
| 5 | **Thời gian crawl batch gần nhất** (Thời gian (giây tự đổi phút/giờ)) | Thời gian crawl/parse/Landing/Bronze, không gồm toàn bộ Spark/embedding/publication. Skip không có duration sẽ không giả lập 0. |
| 6 | **Tuổi lần crawl SUCCESS gần nhất** (Thời gian (giây tự đổi phút/giờ)) | Không gồm policy skip. Tuổi tăng giữa lịch 30 phút là bình thường. Không phải tuổi published_at của article. |
| 7 | **Tuổi heartbeat hoàn tất — kể cả skip** (Thời gian (giây tự đổi phút/giờ)) | Heartbeat cập nhật cả khi skip/policy deny. Vì thế heartbeat mới không chứng minh nguồn đã crawl live thành công. |
| 8 | **Tuổi batch pending lâu nhất** (Thời gian (giây tự đổi phút/giờ)) | 0 chỉ khi pending metric xác nhận không còn batch. Nếu có backlog nhưng thiếu timestamp thì giữ No data để điều tra, không bịa tuổi 0. |
| 9 | **Tuổi downstream thành công gắn với crawler** (Thời gian (giây tự đổi phút/giờ)) | Successful stage liên kết outbox của đúng live/fixture. Tăng khi không có article thay đổi là bình thường; không phải tuổi bài báo. |
| 10 | **Landing đầu tiên → stage hoàn tất gần nhất** (Thời gian (giây tự đổi phút/giờ)) | Độ trễ batch đo từ first durable HTML Landing đến stage finish, gồm chờ/retry. Snapshot gần nhất; không phải p95, tốc độ bài/giây hay benchmark. |
| 11 | **Batch hết retry budget cần review** (Số đếm/trạng thái) | 0 được suy từ pending snapshot đã thu được khi không có nhóm exhausted; không đổi thiếu toàn bộ telemetry thành 0. |
| 12 | **Cờ cấu hình cho phép live — không phải health** (Số đếm/trạng thái) | Chỉ cờ config của nguồn, không chịu data_kind filter, không đổi cron và không kiểm live_until. Quyền thực thi còn phụ thuộc expiry/robots/block/cooldown và DAG unpause. |
| 13 | **HTTP chain trung bình / request hop — toàn ledger** (Thời gian (giây tự đổi phút/giờ)) | Tổng HTTP elapsed / tổng request hops đã ghi. Initial pacing wait bị loại, redirect pacing trong chain được tính. Không phải độ trễ fetch article riêng hoặc trung bình cửa sổ; fixture không có phép đo HTTP thật. |
| 14 | **RAM khả dụng — toàn workstation** (Dung lượng) | Toàn máy dùng chung, không lọc theo source/data_kind; không phải RAM riêng crawler. |
| 15 | **Exporter đọc ledger thành công?** (Số đếm/trạng thái) | Kiểm ô này trước khi diễn giải No data ở các panel crawler. 1 = read-only DB snapshot thành công. |
| 16 | **Nguồn đang bị block latch?** (Số đếm/trạng thái) | 0 = không có block latch, 1 = bị khóa cần review policy. Không tự clear block hoặc bypass để làm xanh. |
| 17 | **Batch pending hiện tại** (Số đếm/trạng thái) | Snapshot theo live/fixture. 0 là không còn batch chờ; không chứng minh không từng lỗi trong phiên. |

## 4. Quy trình kiểm tra phiên pilot năm nguồn

1. Mở Overview với To=`now`. Critical targets và exporter collection phải có
   dữ liệu. Nếu collection lỗi, dừng việc diễn giải số 0/No data và kiểm
   [Prometheus targets](http://localhost:9090/targets).
2. Mở Crawling, chọn `live`, `All`; kiểm cả năm nguồn xuất hiện. Cờ BẬT chỉ là
   config: còn cron, unpause, `live_until`, robots/block/cooldown. Khi hết giờ
   pilot, cờ TẮT sau cleanup là đúng dự kiến, không là incident.
3. Xem latest successful crawl age và pending. Với lịch 30 phút, tuổi tăng giữa
   các lượt là bình thường. Không cam kết mỗi lượt có bài mới; bài cũ, unchanged,
   URL redirect hoặc không có URL due có thể khiến downstream không cập nhật.
4. Nếu pending tăng, chọn nguồn đó; xem oldest pending age, retry exhaustion,
   downstream freshness và Landing-to-stage. Mở task `source.publish` trong
   Airflow; nguồn lỗi riêng không được suy thành lỗi của mọi nguồn.
5. Nếu failed/partial total >0, xem nó tăng khi nào và mở task/attempt tương ứng.
   Trong đợt này từng có URL cũ Tuổi Trẻ về trang chủ và Báo Mới sang trang `-r`;
   đã ghi PERMANENT_FAILURE theo URL, recrawl URL mới và publish/reconciliation
   thành công. Số lỗi cũ vẫn phải được giữ. Dashboard không sửa lịch sử để xanh.
6. Dùng Quality để xem reconciliation gần nhất, Freshness để kiểm mốc stage,
   Resources để hiểu áp lực máy. Không lấy tỷ lệ SUCCESS toàn ledger làm kết quả
   4 giờ hoặc benchmark. CDC chỉ cần theo dõi phần metadata.
7. Kết luận sau khi đọc report thật, không chỉ chụp màn hình dashboard:

   ```sh
   python3 tools/phase9_pilot.py report
   python3 tools/monitoring.py health
   python3 tools/dashboard_audit.py
   ```

Xem [hướng dẫn pilot](phase9-pilot-guide-vi.md), [runbook crawler](crawler-operations.md)
và [trạng thái dự án](agent_tasks/CURRENT_STATUS.md). `report` là lệnh thông tin;
JSON verdict quyết định PENDING/PASS/FAIL, không suy từ exit 0. Không chạy full
failure-injection acceptance giữa lúc pilot nếu không muốn dừng dịch vụ.

## 5. Những tình huống nhìn giống lỗi nhưng cần phân biệt

| Dấu hiệu | Diễn giải và bước tiếp theo |
|---|---|
| Overview còn 5 alerts từ `phase05-recovery.local` ở checkpoint rà soát | Đây là dữ liệu fault-injection/lịch sử: DataQualityGateFailed, stale Silver/Gold, no recent success. Đọc label source và thời gian; không xóa/silence để làm xanh. Kiểm nguồn live riêng. |
| FAILED/PARTIAL không về 0 sau sửa | Đó là lũy kế ledger. So thời điểm tăng và latest success/reconciliation; lỗi đã xảy ra vẫn phải hiện. |
| Mọi ô pipeline cùng 0 hoặc No data | Kiểm collection, scrape target, bộ lọc và time range trước; không kết luận corpus rỗng. |
| Quality gate/Reconciliation tạm 0 khi publish đang chạy | Metric dùng latest attempt, không chỉ last successful. Xem trạng thái stage và chờ hoàn tất; không gọi 0 là content quality score. |
| Freshness tăng dù crawler vẫn chạy | Không có article thay đổi hoặc stage không chạy lại; so heartbeat, last successful crawl, new/unchanged và pending. |
| Consumer lag No data | Chưa có committed offset/group phù hợp có thể là bình thường. Chỉ kết luận 0 lag khi có metric thực; không tạo consumer group để trang trí biểu đồ. |
| CDC event age/WAL gap tăng | Có thể metadata đang ít thay đổi hoặc WAL khác không thuộc publication vẫn tăng. Xem broker/task/slot và xu hướng, không suy backlog article. |
| Cgroup dùng RAM rất lớn ở `/` và `user.slice` | Parent bao chứa child; không cộng bảng để tính tổng container. CPU/RAM là toàn máy dùng chung. |
| Network chỉ có `eth0` | Node exporter hiện ở bridge namespace. Đây không phải toàn bộ card Wi-Fi/Ethernet của host; panel đã đổi tên đúng phạm vi. |
| Biểu đồ không cập nhật giao diện mới | F5 hoặc mở lại dashboard. File provider reload nội dung nhưng tab cũ có thể giữ model cũ. Không sửa qua UI vì dashboard provisioned/read-only. |

## 6. Bằng chứng, nguồn và phạm vi kiểm chứng

Dashboard files là cấu hình chính thức, Grafana file provider poll mỗi 10 giây.
Hướng dẫn này đối chiếu với:

- [Exporter pipeline](../src/monitoring/exporter.py): `SnapshotReader.read`,
  `FinancialNewsCollector.collect`, `stage_record_counts`, `service_snapshot`.
- [Exporter crawler](../src/monitoring/crawler_metrics.py): `read`, `collect`,
  nhãn live/fixture và các mốc heartbeat/Landing/downstream.
- [Provisioning](../monitoring/grafana/provisioning/dashboards/dashboards.yaml),
  [datasource](../monitoring/grafana/provisioning/datasources/datasources.yaml),
  [Compose](../docker-compose.yml), [Prometheus rules](../monitoring/prometheus/rules/financial-news.yml).
- [Instant query của Grafana](https://grafana.com/docs/grafana/latest/datasources/prometheus/query-editor/):
  snapshot cho ô số/bảng; range query dùng cho diễn biến.
- [Quy ước đơn vị Grafana](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/configure-standard-options/):
  Date/Time cần Unix milliseconds; exporter phát seconds nên bảng nhân 1000.

Audit read-only tại thời điểm cập nhật: **7 dashboards, 68 target queries** hợp lệ
qua Prometheus và Grafana query API, kiểm cả default và single-variable selection,
không có giá trị NaN/Inf hoặc legend thiếu nhãn trong các series có dữ liệu.
Consumer lag không có series được ghi N/A. Browser headless dùng Chrome local để
kiểm các trang; xem [báo cáo sửa dashboard](grafana-dashboard-review-2026-10-23.md)
cho phạm vi UI và các giới hạn. Evidence máy sinh nằm trong ignored
`artifacts/phase9/dashboard-review/`, không đưa credential/raw HTML bài báo vào Git.

Kết quả audit là checkpoint cấu hình/khả năng query, không bảo đảm mọi tình huống
future/no-data, độ tin cậy multi-day hoặc chất lượng retrieval/RAG. Pilot 4 giờ
vẫn là phép đo riêng; burn-in 24h/72h và cloud gate không được đổi theo dashboard.
