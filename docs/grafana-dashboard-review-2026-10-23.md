# Rà soát và sửa dashboard Grafana — 23/10/2026

**Bổ sung sau khi pilot kết thúc:** [báo cáo vận hành](phase9-pilot-report-2026-10-23.md)
ghi coverage, lỗi redirect và phân tích warning quality theo latest attempt.
Review/sửa dashboard bên dưới xảy ra trong pilot, giữ đúng provenance; pilot
cuối cùng PENDING, không suy thành acceptance PASS từ query audit.

## Phạm vi và kết luận

Rà soát cả bảy dashboard file-provisioned, đối chiếu với Prometheus/Grafana
đang chạy và source exporter. Có lỗi truy vấn/cấu hình thật cùng những vấn đề
hiển thị khiến người đọc dễ nhầm dữ liệu lịch sử với pilot. Đã sửa và bổ sung
[hướng dẫn đọc từng panel](grafana-dashboard-guide-vi.md).

Không sửa article/data contracts, không xóa metrics/ledger, không reset lỗi cũ,
không nới alert threshold hoặc biến pilot thành burn-in PASS. Dashboard UIDs,
tên dashboard và các panel ID cũ được giữ. Bổ sung panel ngữ cảnh/sức khỏe,
không tạo chức năng processing mới.

## Findings và cách xử lý

| Finding | Bằng chứng trước sửa | Cách sửa / giới hạn còn lại |
|---|---|---|
| Kafka exporter không xuất metrics topic metadata | `kafka_brokers=1` nhưng không có `kafka_topic_partitions`; Compose truyền topic regex bị escape thừa | Đổi arg thành `platform[.]control_metadata[.].*`. Recreate **chỉ kafka-exporter**; broker, Debezium và pipeline không restart. Metric sau sửa có hai topic, mỗi topic một partition tại checkpoint. |
| Bảng partition CDC có PromQL không hợp lệ | Truy vấn nguyên bản trả HTTP 400 do escape regex trong string | Dùng biến topic và regex hợp lệ; query API/Chrome đã đọc được hai hàng partition. |
| Timestamp giây được đưa thẳng vào formatter Date/Time | Exporter trả Unix seconds, panel dùng date unit | Nhân 1000; format `DD/MM/YYYY HH:mm:ss`, dashboard timezone +07. Chrome context timezone UTC vẫn hiển thị mốc xử lý đúng giờ Việt Nam. |
| Không có filter, live/fixture và datasets kiểm thử lẫn nhau | Crawler có 160 series outcomes; generic pipeline chứa source thử nghiệm | Crawler mặc định live + năm nguồn, có filter source/data_kind/layer. Pipeline mặc định năm hostname và pipeline chính. **Pipeline metrics vẫn có thể chứa fixture cùng hostname** vì family đó không có data_kind; đã ghi rõ. |
| Legend chung gây trùng/thiếu ngữ cảnh | Template dùng job/pipeline/source/stage/layer/status/component cho mọi query, nhiều nhãn không tồn tại | Dùng đúng nhãn từng query; thêm kind/outcome/topic/partition/device/cgroup ID phù hợp. Audit không thấy legend yêu cầu nhãn thiếu trong series hiện có. |
| Bảng/ô số dùng range query, dễ giữ giá trị quá khứ hoặc lặp hàng | Các targets không chỉ định instant/table | Ô số/bảng dùng Instant; bảng hiện label và value, ẩn scrape Time/job/instance. Đồ thị dùng Range và không nối qua null. Snapshot lấy tại cuối time range. |
| Bộ đếm lũy kế bị hiểu là số sự kiện của time range | `_total` thực chất là Gauge đọc ledger, có lịch sử retry/fixture | Đổi title/tooltip, chỉ rõ lũy kế và không dùng rate/increase cho các family này. Success ratio là toàn completed ledger trong bộ lọc, không là success rate pilot. |
| No data bị hiểu thành 0 lỗi | Alert count rỗng; exhausted không có row khi zero; consumer group không có offset | Chỉ fill zero khi có cơ sở metric tương ứng. Consumer lag vẫn N/A khi không có committed offsets; không tạo fake consumer/zero. |
| Targets up bị hiểu là app/database khỏe | CDC chỉ kiểm `up{job="postgresql"}` | Dùng `pg_up` cho DB; Overview tách scrape, DB collection, scheduler và connector. |
| Network bị gọi là host network | Host có Wi-Fi/Ethernet/bridge; node exporter chỉ có eth0/lo do namespace Docker | Đổi tên và giải thích đúng phạm vi namespace. Không đổi network mode/restart node exporter giữa pilot. Đây vẫn là giới hạn instrumentation. |
| Cgroup bị hiểu là RAM từng container có thể cộng | cAdvisor thiếu Docker name labels, có `/`, user.slice và nhiều nhóm con | Giữ raw Cgroup ID, ghi parent/child chồng lặp, không cộng thành tổng RAM container. |
| Cảnh báo cũ gây tưởng pilot đang lỗi | Checkpoint có năm alerts thuộc `phase05-recovery.local` | Giữ nguyên alert rules/data, thêm bảng chi tiết và giải thích source fixture. Không suy “mọi alert đều lịch sử” cho các lần đo tương lai. |

## Khả năng đọc sau sửa

- Intro, title/tooltip tiếng Việt; cùng bộ nút điều hướng bảy dashboard.
- Timezone `Asia/Ho_Chi_Minh`, mặc định Last 1 hour, refresh 30s. Người dùng có
  thể chọn cửa sổ pilot cụ thể; không đánh đồng Last với delta trong time range.
- Filter pipeline/hostname; crawler source key/live/fixture/layer; CDC topic.
  Freshness mặc định lớp Silver cho biểu đồ/bảng để giảm số đường; các ô số
  từng lớp vẫn hiển thị đầy đủ.
- Boolean có mapping 0/1; cờ live là BẬT/TẮT, không là health. Duration/freshness
  có đơn vị, không tự đặt performance/SLA threshold. Qdrant native vectors ghi
  rõ là tất cả collection; DuckDB state ghi rõ là latest publish attempt.

## Kiểm chứng thực tế

Evidence nằm dưới ignored `artifacts/phase9/dashboard-review/`:

- `queries-before.json`: 61 truy vấn gốc, gồm lỗi parse CDC và các snapshot trước sửa.
- `queries-after.json`, tạo bằng `python3 tools/dashboard_audit.py`: **7 dashboard,
  68 target queries**, Prometheus và Grafana datasource query API PASS; kiểm
  default và single-variable selection, model provisioning khớp targets trong
  file. Không có NaN/Inf hoặc legend thiếu nhãn trong series có dữ liệu.
- Consumer lag không có series được giữ **N/A**. Đây không phải lag=0 hoặc query FAIL.
- Chrome headless local: mở bảy dashboard không có page JavaScript errors ở lần
  kiểm trang; kiểm riêng năm bảng bằng solo-panel view, gồm timestamp, record
  volumes, partition, cgroup và active alerts. Các bảng có tên cột/giá trị đọc được.
  Viewport/lazy rendering khiến script scroll toàn trang không đọc được mọi
  panel; không gọi đó là kiểm từng pixel của toàn bộ 68 panel. Query API đã kiểm
  mọi target; riêng bảng được kiểm thêm bằng rendering thật.
- Grafana file provider tự reload; không restart Grafana, Prometheus, Kafka broker,
  Airflow hoặc pipeline. Kafka exporter recreate giữa hai lần lấy mẫu collector.
  Health sau sửa PASS, collector pilot còn active, sample tiếp theo không ghi
  collection_error/hard-stop. Không suy “không có mọi outage” từ một checkpoint.
- Lint/format phạm vi tool mới và `git diff --check`; không chạy bộ fault injection
  dừng Qdrant/CDC trong khi pilot đang hoạt động.

Script audit là read-only; không chỉnh datasource qua API hoặc dùng credential
thật trong log. Kết quả audit là kiểm cấu hình/metrics/UI hiện có, không phải
benchmark, RAG evaluation hoặc xác nhận multi-day stability.

## Giới hạn và thao tác tiếp theo

F5/mở lại tab để nạp model mới. Dashboard provisioned nên sửa JSON trong repo,
không lưu chỉnh sửa UI rồi kỳ vọng còn sau reload. Đọc hướng dẫn trước khi dùng
số liệu vào luận văn: metrics pipeline có thể lẫn fixture cùng hostname, latest
attempt không phải một checkpoint nguyên tử toàn stack, `_total` không là delta
của phiên, network/cgroup còn giới hạn đã nêu.

Kết quả pilot sau bốn giờ phải review từ session/samples/report thật cùng các
incident đã giữ. Burn-in 24h/72h và cloud NO-GO không thay đổi vì dashboard xanh.
