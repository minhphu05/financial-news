# Chạy thử và giám sát pipeline local trong 4 giờ

**Phiên 23/10 đã kết thúc:** đủ cửa sổ 14:04:58–18:04:58, 50 mẫu; cleanup PASS
khoảng 18:05. Verdict pilot **PENDING** do failed/partial crawl, đặc biệt Báo Mới
còn sáu scheduled partial. Đọc [báo cáo kết quả và tồn đọng](phase9-pilot-report-2026-10-23.md).
DAG paused/live policies off; cron/global switch vẫn giữ cấu hình pilot.
Các checkpoint khởi động bên dưới là lịch sử, không phải trạng thái đang chạy.

Cập nhật 23/10/2026. Đây là **pilot ngắn được người dùng yêu cầu**, không thay
thế burn-in 24h/72h trong specification Phase09. Phase09 chưa DONE và cloud vẫn
NO-GO. Trạng thái từng phiên nằm trong `artifacts/phase9/pilot/` (ignored).

## Phạm vi và điều kiện

- Chạy cả năm nguồn: CafeF, VnExpress, Tuổi Trẻ, Thanh Niên và Báo Mới.
- Lịch 30 phút/lượt, tối đa một article/nguồn/lượt; đây không phải cam kết có
  bài mới mỗi lượt hoặc chỉ một HTTP request. Robots/listing/retry cũng tạo request.
- Giữ pacing tối thiểu ba giây; không bypass robots, challenge, block hoặc cooldown.
- Spark chạy `local[2]` trong môi trường Airflow; embedding dùng FastEmbed hiện có.
- Máy phải hoạt động và có mạng. Collector được chạy bằng user systemd service
  kèm sleep/idle inhibitor; không cần giữ chat/terminal mở. Không bảo đảm chống
  mất điện, forced suspend, logout dừng user manager hoặc Docker bị tắt.

## Những dịch vụ được bật

MinIO, PostgreSQL operations/control metadata, Qdrant, Airflow scheduler/webserver
và database riêng của Airflow; `airflow-init` là job khởi tạo một lần. Monitoring
gồm Prometheus, Grafana, platform/postgres/kafka/airflow-statsd exporters,
node-exporter và cAdvisor. Giữ Kafka/Debezium vì monitoring stack hiện phụ thuộc
chúng và kiểm CDC metadata. Kafka không mang article bodies. DuckDB là file,
không có DuckDB server; không cần frontend, API/chatbot, Prefect, MLflow hay MongoDB.

| Trang | URL | Quan sát |
|---|---|---|
| Airflow | <http://localhost:8088/dags/news_crawling_pipeline/grid> | DAG runs, crawl/publish và task logs |
| Grafana | <http://localhost:3000/dashboards> | Crawler, operations, chất lượng và tài nguyên |
| Prometheus | <http://localhost:9090/targets> | Target up/down; `/alerts` xem cảnh báo |
| MinIO Console | <http://localhost:9001> | Landing/Bronze/Delta/Gold; không đưa raw HTML lên Git |
| Qdrant | <http://localhost:6333/dashboard> | Collection/point theo nguồn |

Nếu cần đăng nhập, dùng tài khoản local đang cấu hình; tài liệu không chép secret.

## Quy trình và bằng chứng

1. Kiểm health, không có run/writer đang hoạt động được quan sát, kiểm backlog.
   Lưu baseline và bản sao dữ liệu trước khi ghi live. Lượt chuẩn bị này đã tạo
   MinIO volume archive và PostgreSQL custom dump private, có checksum và kiểm
   đọc archive/TOC; **chưa diễn tập full restore**. Recovery reference ghi rõ giới hạn.
2. Kiểm robots/listing bằng user agent thật, pacing và giới hạn hiện có. Review
   ngày 23/10 ghi HTTP 200 cho cả năm listing, robots cho phép đường dự kiến; không
   suy ra quyền tái phân phối hoặc bỏ qua kiểm robots ở lượt chạy sau.
3. Chạy B1 live nhỏ, kiểm cả crawl và publish/reconciliation. Manual DAG cần
   `fixture_mode=false`, `allow_live=true`, chọn cả năm nguồn và `limit=1`.
4. Bật cron `*/30 * * * *`, giới hạn 1 và scheduled-live switch; kiểm scheduler
   parsed config. DAG vẫn `catchup=False`, một active run/task. Manual defaults
   vẫn fixture-safe.
5. Bắt đầu phiên pilot và collector; ghi bằng chứng mỗi năm phút. Lệnh ví dụ
   dưới đây cần các reference thật của lần chạy, không tự tạo approval:

   ```sh
   python3 tools/phase9_pilot.py start --hours 4 --sources cafef vnexpress tuoitre thanhnien baomoi \
     --live-opt-in --backup-reference artifacts/phase9/pilot/recovery-plan.md \
     --policy-reference artifacts/phase9/pilot/source-policy-review.json
   python3 tools/phase9_pilot.py watch --session <session-do-start-in-ra>
   ```

   Vận hành thực tế dùng user systemd service và timer dừng độc lập, ghi tên
   unit/session trong `artifacts/phase9/pilot/runtime.json`. `start` tự nó không
   chạy collector. Không bắt đầu phiên mới trong khi phiên cũ còn hoạt động.
6. Hết giờ hoặc hard-stop: collector pause DAG và tắt live policy cả năm nguồn.
   Timer độc lập cũng thực hiện cleanup. Mỗi source có `live_until` trong
   operational config: gate từ chối lượt live mới khi hết hạn, kể cả collector
   chết. Field tùy chọn này không đổi article schema; fixture không bị deadline chặn.
   Timestamp không hợp lệ/không timezone bị từ chối. Các task đã bắt đầu vẫn
   phải hoàn tất trong giới hạn; pause không hủy task đang chạy.
7. Sau khi task settle, kiểm backlog, run failures và reconciliation, rồi review
   report. Không xóa dữ liệu để làm kết quả xanh. Report PASS chỉ chứng minh
   các điều kiện đo trong pilot; 24h/72h vẫn PENDING, không là benchmark hay RAG eval.

## Xem tiến độ, dừng sớm và phục hồi

```sh
# Mặc định dùng latest session, hoặc truyền --session đường-dẫn-cụ-thể.
python3 tools/phase9_pilot.py report
python3 tools/phase9_pilot.py stop
python3 tools/monitoring.py health
systemctl --user list-units 'financial-news-pilot*'
systemctl --user list-timers 'financial-news-pilot*'
```

`stop` ghi lý do operator stop; phiên không được coi là đủ bốn giờ. Collector
phát hiện stop record ở lần lấy mẫu tiếp theo. Khi hoàn tất, DAG/policy được
pause/disable; cron trong `.env` vẫn là 30 phút và global opt-in vẫn bật, nên
muốn về manual hoàn toàn phải khôi phục các giá trị trước pilot từ
`original-schedule.json`, rồi recreate scheduler/webserver **sau khi task settle**.
Không phục hồi cả `.env` hoặc chép secret vào báo cáo.

Nếu bị block/rate-limit, critical service down, reconciliation lỗi, thiếu metrics
hoặc vượt hard-stop tài nguyên, collector dừng. Giữ incident/samples, sửa đúng
nguyên nhân và review trước phiên mới; không bỏ qua block để tiếp tục crawl.
Mất điện/SIGKILL có thể ngăn cleanup: pause sau restart, xem policy expiry và coi
cửa sổ gián đoạn là không đủ bằng chứng. Dữ liệu đang lưu bền được giữ lại.

## Tình trạng đo

Thời điểm start/end, trạng thái collector và B1 được ghi trong runtime evidence.
Không đánh dấu PASS trước khi đủ bốn giờ thực và có samples/scheduler/live/reconciliation
đạt điều kiện. Báo cáo Phase09 và Phase10 trước đây giữ đúng ngày/phạm vi gốc.

## Lịch sử phiên — checkpoint khởi động 23/10/2026

- Năm nguồn được chọn: CafeF, VnExpress, Tuổi Trẻ, Thanh Niên, Báo Mới.
- Start **14:04:58 +07:00**, hết cửa sổ **18:04:58 +07:00**.
- Session: `artifacts/phase9/pilot/pilot-20261023T070458Z-474d3e.json`.
- Collector: `financial-news-pilot-20261023-070458.service`; timer:
  `financial-news-pilot-20261023-070458-deadline.timer`.
- Sleep/idle inhibitor là service riêng `financial-news-pilot-20261023-070458-awake.service`;
  collector dùng KillMode=mixed để graceful stop không gửi TERM đồng thời vào Docker child.
- Health check PASS tại khởi động; chưa có kết quả bốn giờ. Hai nguồn đầu đã qua
  B1 live publish/reconciliation; lượt live năm nguồn mới được trigger và đang chạy.
- Phiên hai nguồn `pilot-20261023T070157Z-5a1649` dừng sớm do đổi scope. Timer cũ
  đã tắt; không tính gộp thời lượng. Có một cleanup attempt bị gián đoạn khi
  dừng service, được giữ riêng; lần kiểm lại pause/disable đạt PASS.
- Tests: 14 host tests và 27 tests trong Airflow runtime PASS, bao gồm deadline,
  fail-closed và anti-fake burn-in. Đây là unit tests, không phải uptime evidence.

Đọc report/health hiện tại thay vì suy diễn trạng thái tương lai từ checkpoint này.

## Sự cố URL cũ phát hiện trong pilot

Lượt live năm nguồn đầu tiên ghi lỗi `not_a_supported_source_url` ở Tuổi Trẻ
và Báo Mới. Probe có pacing xác nhận URL Tuổi Trẻ cũ chuyển về trang chủ HTTP 200;
URL Báo Mới cũ chuyển từ dạng `-c` sang trang `-r` ngoài article pattern đã hỗ trợ.
ValueError trước đây thoát ra mức run, để frontier vẫn NEW và lặp lại mãi.

Đã sửa hẹp tại crawl job: final URL không hợp lệ trở thành FetchError không
retryable, đi qua cơ chế failure hiện có để ghi PERMANENT_FAILURE theo URL và
cho frontier đi tiếp. Không mở rộng host/pattern, không bypass robots/redirect,
không thay parser hoặc data contract. Body ở redirect bị từ chối trước Landing
article, nên bằng chứng cho trường hợp này là status/attempt và diagnostic metadata.
Test PostgreSQL thật với synthetic redirect đã PASS; retry có giới hạn đã xác
minh hai URL bị cách ly đúng. Recrawl một URL mới từ listing hiện tại của mỗi
nguồn đã SUCCESS; publication/reconciliation cần xem ledger sau khi chạy xong.
Các failed/partial rows gốc được giữ; không suy DAG SUCCESS là mọi crawl thành
công vì publish dùng trigger rule all_done.

## Checkpoint sau phục hồi live năm nguồn

Tại 14:14:36 23/10/2026 +07:00, cả năm nguồn đã có live crawl và publication/reconciliation
SUCCESS/PASS. Closed-window report `five-source-checkpoint.json` (bắt đầu 13:55,
gồm cả B1 trước pilot) ghi pending_batches_end=0 và reconciliation FAIL=0 cho
mỗi nguồn. Tuổi Trẻ/Báo Mới vẫn giữ một failed run và một partial run khi xử lý
URL cũ; không xóa hoặc chuyển chúng thành thành công. Collector còn chạy, samples
đã thu không có collection_error/hard-stop tại checkpoint. Chưa đủ bốn giờ.

Bổ sung test real PostgreSQL + synthetic redirect: PASS. Regression cuối có
53 test cases, 42 chạy thành công và 11 skip theo environment (không bật các
DB suites cũ khi live đang chạy); không coi 11 skips là test đã chạy. Lint/format
phạm vi file thay đổi và git diff --check đạt. Code graph đã cập nhật AST.

Báo cáo CLI là thông tin: JSON verdict mới xác định PENDING/PASS/FAIL; exit 0 của
`report` không là acceptance PASS. Collector hoàn tất trả 0 khi PASS, 2 khi còn
PENDING cần review và 1 khi FAIL. Runtime unit đang chạy có thể đã nạp code trước
một thay đổi CLI exit-code; luôn dùng JSON report khi review kết quả.

## Đọc các dashboard

Xem [hướng dẫn từng dashboard/panel](grafana-dashboard-guide-vi.md) và
[báo cáo rà soát 23/10](grafana-dashboard-review-2026-10-23.md). Crawler mặc định
live, năm nguồn; pipeline metrics có thể gồm fixture cùng hostname. Trong lúc
pilot đã sửa Kafka exporter topic regex và dashboard hot reload; broker/pipeline
không restart. Không dùng các số lũy kế thay cho report cửa sổ thực.
