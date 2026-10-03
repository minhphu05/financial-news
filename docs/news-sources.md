# Các nguồn tin tức đã crawl và phạm vi thu thập

**Đối chiếu code và bằng chứng:** 03/10/2026. Tài liệu mô tả crawler Phase08 trong
`src/crawling`, dữ liệu mẫu có sẵn và kết quả live smoke đã ghi nhận. Đây không
phải báo cáo crawl mới hoặc cam kết thu thập đầy đủ mọi bài của các website.

## 1. Danh sách nguồn đến từ đâu?

Yêu cầu Phase08 xác định 5 nguồn: **CafeF, VnExpress, Báo Mới, Tuổi Trẻ và
Thanh Niên**. Xem [task Phase08](agent_tasks/08-multisource-crawling-ingestion-local.md).

Các trang chuyên mục kinh tế/kinh doanh cụ thể và CSS selectors là lựa chọn khi
triển khai, dựa trên phạm vi tin tức tài chính và HTML đã kiểm tra. Chúng chưa
phải bộ tiêu chí nội dung do người dùng xác nhận đầy đủ.

Hiện chưa có bộ lọc riêng theo mã cổ phiếu, từ khóa hay mức độ liên quan tài
chính. Một bài xuất hiện trên chuyên mục kinh tế vẫn có thể không phù hợp với
phạm vi nghiên cứu mong muốn. Trước khi thu thập diện rộng, cần chốt chuyên mục,
tiêu chí chọn/loại bài, khoảng thời gian và sản lượng mục tiêu.

## 2. Nguồn và chuyên mục mặc định

Các URL dưới đây là cấu hình mặc định trong
[sources.py](../src/crawling/sources.py), được seed vào PostgreSQL. Job đọc
`config.crawler.discovery_urls` từ metadata, nên cần kiểm tra cấu hình thực tế
nếu operator đã thay đổi chuyên mục.

| Nguồn | Key crawler / domain | Trang tìm URL bài viết mặc định | Phạm vi ban đầu |
|---|---|---|---|
| CafeF | `cafef` / `cafef.vn` | `https://cafef.vn/vi-mo-dau-tu.chn` | Vĩ mô, đầu tư |
| VnExpress | `vnexpress` / `vnexpress.net` | `https://vnexpress.net/kinh-doanh` | Kinh doanh |
| Tuổi Trẻ | `tuoitre` / `tuoitre.vn` | `https://tuoitre.vn/kinh-doanh.htm` | Kinh doanh |
| Thanh Niên | `thanhnien` / `thanhnien.vn` | `https://thanhnien.vn/kinh-te.htm` | Kinh tế |
| Báo Mới | `baomoi` / `baomoi.com` | `https://baomoi.com/kinh-te.epi` | Tin tổng hợp mục kinh tế |

Chuyên mục chỉ là điểm tìm link ban đầu. Crawler chưa duyệt đầy đủ phân trang,
archive hay mọi chuyên mục của từng báo.

## 3. Cơ chế crawl chung

```text
Đọc cấu hình nguồn từ PostgreSQL
  → HTTP GET robots.txt và trang chuyên mục
  → BeautifulSoup đọc a[href], kiểm tra domain/mẫu URL
  → Ghi URL vào frontier PostgreSQL
  → Chọn URL mới/retry/recheck đủ điều kiện trong giới hạn batch
  → HTTP GET trang bài viết
  → Lưu HTML gốc và envelope vào Landing
  → Parse vùng bài viết bằng CSS selectors
  → Lưu payload đã parse, adapter về schema input hiện có
  → Bronze → Spark/Silver → Gold → Qdrant/DuckDB
```

- HTTP client dùng `urllib.request`; parser dùng BeautifulSoup với `html.parser`.
- Crawler chạy theo quy tắc đã viết trong code; không dùng LLM để tự tìm field.
- Các trang mẫu đã kiểm chứng trả về nội dung trong HTML qua HTTP thông thường.
  Runtime hiện không render JavaScript bằng Selenium/Playwright.
- URL phải thuộc đúng domain nguồn và đúng mẫu bài viết. Link có query string
  hiện bị loại; fragment được canonicalization bỏ đi. Redirect khác domain bị chặn.
- Thiếu tiêu đề/vùng nội dung hợp lệ gây parser failure; HTML đã tải vẫn được giữ.
- Kiểm tra robots, mặc định cách request ít nhất 3 giây, timeout 20 giây và giới
  hạn response 5 MB. Retry/cooldown có giới hạn; bị chặn thì ghi nhận và dừng nguồn.

Chi tiết chính sách, recheck và phục hồi nằm trong
[crawler operations](crawler-operations.md). Source-specific selectors là cấu
hình dùng chung engine, không phải 5 hệ thống crawl tách rời.

## 4. Cách nhận dạng và đọc từng nguồn

| Nguồn | Mẫu path bài viết (regex) | Selector tiêu đề | Selector nội dung | Selector thời gian |
|---|---|---|---|---|
| CafeF | `-\d{6,}\.chn$` | `h1.title` | `div.afcbc-body` | `meta[property="article:published_time"]` |
| VnExpress | `-\d{6,}\.html$` | `h1.title-detail` | `article.fck_detail` | `meta[name="pubdate"]` |
| Tuổi Trẻ | `-\d{6,}\.htm$` | `h1.detail-title` | `div.afcbc-body` | `meta[property="article:published_time"]` |
| Thanh Niên | `-\d{6,}\.htm$` | `h1.detail-title` | `div.afcbc-body` | `meta[property="article:published_time"]` |
| Báo Mới | `-c\d+\.epi$` | `article.content-main h1` | `div.content-body` | `meta[property="article:published_time"]` |

Ví dụ CafeF: tải chuyên mục → tìm link đúng domain và hậu tố bài → tải HTML bài
→ đọc `h1.title` và `div.afcbc-body`. Selector chỉ hoạt động với layout đã hỗ trợ;
không đảm bảo mọi dạng bài/video/interactive trên báo đều parse được.

### Dữ liệu trích xuất

- **Tóm tắt:** cả 5 nguồn hiện đọc `meta[name="description"]`. Các field `sapo`
  hoặc `standfirst` trong payload là alias của parser, không chứng minh đã đọc
  một thẻ sapo riêng trong nội dung trang.
- **Body:** chỉ vùng bài viết, loại `script`, `style`, `iframe`, `nav` và một số
  vùng bài liên quan. Spark tiếp tục làm sạch/chuẩn hóa theo contract hiện có.
- **Metadata:** lưu author từ `article:author`, category từ metadata, URL ảnh
  trong body, canonical link và JSON-LD nếu có. Chỉ giữ URL ảnh, không tải ảnh.
- **JSON-LD:** giữ dạng chuỗi trong raw payload; hiện không dùng làm fallback
  để suy diễn tác giả, thời gian hoặc URL gốc.
- **Thời gian:** adapter chuyển ISO có timezone về định dạng phút giờ Việt Nam
  của input contract. Riêng CafeF chấp nhận ISO thiếu timezone như giờ Việt Nam.
  Giá trị không hỗ trợ được giữ nguyên, canonical `published_at` có thể null;
  không thay ngày đăng bằng thời gian crawl.

### Điểm riêng của Báo Mới

Báo Mới là nguồn tổng hợp. Parser giữ thêm `original_publisher` từ
`.content-meta a.bm-card-source` và `original_url` nếu thấy URL rõ trong phần
text của `.article-source a`. Nó không tự suy đoán domain báo gốc hoặc crawl tiếp
theo link redirect sang báo gốc.

Article vẫn mang source `baomoi.com` và URL Báo Mới. Hiện không deduplicate giữa
Báo Mới và bài tương tự ở một báo khác.

## 5. Đã crawl được bao nhiêu?

Theo [live smoke](../artifacts/phase8-live-smoke.json) và
[live end-to-end](../artifacts/phase8-live-e2e.json) ngày 03/10/2026:

| Nguồn | URL bài được phát hiện ở smoke | Bài được fetch | Silver / Gold documents / DuckDB articles | Gold chunks / Qdrant points | Đối soát |
|---|---:|---:|---|---|---|
| CafeF | 39 | 1 | 1 / 1 / 1 | 3 / 3 | PASS |
| VnExpress | 50 | 1 | 1 / 1 / 1 | 7 / 7 | PASS |
| Tuổi Trẻ | 16 | 1 | 1 / 1 / 1 | 3 / 3 | PASS |
| Thanh Niên | 57 | 1 | 1 / 1 / 1 | 12 / 12 | PASS |
| Báo Mới | 61 | 1 | 1 / 1 / 1 | 14 / 14 | PASS |
| **Tổng** | **223** | **5** | **5 / 5 / 5** | **39 / 39** | **PASS** |

**Phát hiện URL không đồng nghĩa đã tải/parse bài đó.** Chỉ 5 bài trong lượt
smoke này có bằng chứng đi hết pipeline. Đây không phải tổng số bài hiện có
trong database sau mọi lượt chạy, cũng không phải bằng chứng coverage diện rộng.

| Nguồn | Contract/parser fields | Profile quan sát, URL bài mẫu và robots |
|---|---|---|
| CafeF | [cafef.md](source-contracts/cafef.md) | [cafef.json](../artifacts/source-profiles/cafef.json) |
| VnExpress | [vnexpress.md](source-contracts/vnexpress.md) | [vnexpress.json](../artifacts/source-profiles/vnexpress.json) |
| Tuổi Trẻ | [tuoitre.md](source-contracts/tuoitre.md) | [tuoitre.json](../artifacts/source-profiles/tuoitre.json) |
| Thanh Niên | [thanhnien.md](source-contracts/thanhnien.md) | [thanhnien.json](../artifacts/source-profiles/thanhnien.json) |
| Báo Mới | [baomoi.md](source-contracts/baomoi.md) | [baomoi.json](../artifacts/source-profiles/baomoi.json) |

## 6. Phân biệt dữ liệu mẫu, fixture và bài crawl thật

| Loại | Nguồn/vị trí | Cách hiểu |
|---|---|---|
| Snapshot có sẵn | CafeF trong `data/raw/`; batch chuẩn theo [data contracts](data-contracts.md) | Input lịch sử cho Phase01–07; không cộng số liệu snapshot vào 5 bài live smoke. |
| Fixture | `tests/fixtures/crawling`; Landing `landing/fixture/`; version `fixture-crawl-v1` | Nội dung tổng hợp kiểm thử parser/pipeline, không phải bằng chứng tin tức thật. |
| Crawl live | Landing `landing/live/<source>/`; version `crawl-v1` | HTML/payload thực thu qua HTTP; raw runtime nằm trong storage/local data bị ignore. |

Adapter đưa vào Bronze các field `link`, `title`, `summary`, `context`,
`post date`. Author/category/ảnh/crawl timestamp và attribution được giữ ở
Landing; các optional columns tương ứng trong canonical normalization hiện
vẫn null. Không tự tạo ticker/NER hay đổi approved contract.

Qdrant live dùng `crawler_<source>_v1`, fixture dùng
`fixture_crawler_<source>_v1`. DuckDB dùng file riêng theo nguồn trong
`CRAWLER_WORK_DIR`. Serving có thể dựng lại từ Gold.

## 7. Đọc tiếp và chạy kiểm chứng

```sh
make crawler-status
# Các lệnh dưới tạo request tới website khi operator chủ động chạy:
make crawler-live-smoke CRAWLER_SOURCE=all CRAWLER_LIMIT=1
make crawler-publish CRAWLER_SOURCE=all
```

- Cách khởi tạo, schedule, backfill, retry: [crawler operations](crawler-operations.md).
- Tích hợp vào pipeline: [crawler architecture](crawling-architecture.md).
- Mapping về schema: [source mapping matrix](source-mapping-matrix.md).
- Kết quả kỹ thuật/tests: [Phase08 report](phase8-engineering-report.md).
- Chọn tài liệu theo nhu cầu: [documentation guide](DOCUMENTATION_GUIDE.md).

Schedule mặc định tắt; Airflow default chỉ 1 bài/nguồn/lần chạy. Thay đổi layout,
phân trang, chất lượng/độ liên quan nội dung và khả năng thu đủ bài cần kiểm chứng
thêm trước khi tăng quy mô. Tài liệu này không bật schedule hoặc chạy crawl mới.
