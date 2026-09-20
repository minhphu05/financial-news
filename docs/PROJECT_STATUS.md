# Hiện trạng dự án Financial News / ViFinNER

**Thời điểm rà soát:** 20/09/2026 · **Nhánh:** `development` · **Commit:** `037038a`

**Đối chiếu đề cương khóa luận:** xem [`THESIS_ALIGNMENT.md`](THESIS_ALIGNMENT.md). Đề cương xác định **ba đầu ra**: nghiên cứu ViFinNER, website/RAG, và streaming dữ liệu giá cổ phiếu + Power BI. Tài liệu hiện trạng này chủ yếu mô tả những gì đã có trong repository; không nên hiểu hai hướng mã đang có là toàn bộ phạm vi khóa luận.

## 1. Dự án đang làm gì?

Repository hiện thể hiện rõ hai hướng công việc:

1. **Ứng dụng tin tức tài chính và hỏi đáp RAG:** thu thập bài viết CafeF theo mã cổ phiếu/từ khóa, lưu metadata vào PostgreSQL và nội dung vào MongoDB; làm sạch, chia đoạn, tạo embedding bằng Voyage AI, lưu vector vào Qdrant; dùng OpenRouter để trả lời câu hỏi có dẫn nguồn. FastAPI cung cấp API, React cung cấp giao diện.
2. **Nghiên cứu NER tài chính tiếng Việt (ViFinNER):** chuẩn bị dữ liệu gán nhãn thực thể và mã nguồn huấn luyện nhiều mô hình BiLSTM, CRF, XLM-R, PhoBERT, span NER. Phần này hiện nằm riêng trong `src/model/`; chưa thấy được nối vào luồng phục vụ RAG/API.

**Đầu ra thứ ba trong đề cương — dữ liệu giá cổ phiếu theo luồng và Power BI — chưa thấy có collector, Kafka/Flink job, dữ liệu OHLCV hoặc dashboard trong repo.** Danh mục mã VN50 trên website chỉ phục vụ tra cứu tin tức/số bài theo mã, chưa phải dữ liệu thị trường.

Đây là **trạng thái của mã và dữ liệu trong repository**, không phải xác nhận hệ thống đang chạy ngoài thực tế. Khi rà soát, `docker compose config --quiet` hợp lệ nhưng `docker compose ps` không liệt kê container đang chạy. Môi trường Python hiện tại thiếu `pytest`, `pydantic_settings`, `pymongo`, `prefect`, `qdrant_client` và `polars`, nên chưa chạy được kiểm thử hay một lượt pipeline đầy đủ.

## 2. Luồng chính được cấu hình hiện nay

```text
data/raw/vn30.xlsx
    → src/scraper (CafeF, lọc trùng và crawl tăng dần)
    → PostgreSQL: news_articles, scrape_runs, scrape_progress
    → MongoDB: financial_news.articles_content
    → src/pipeline/core.py (làm sạch → chia đoạn → Voyage AI)
    → MongoDB: financial_news.cafef_clean + Qdrant: financial_news_chunks
    → FastAPI /stocks, /news, /chat → React
                         ↘ Redis cache, trích dẫn bài nguồn
```

`docker-compose.yml` chạy `prefect-worker` bằng `python -m src.flows.deploy`. Bộ triển khai này chỉ đăng ký **full pipeline hằng ngày lúc 06:00 giờ Việt Nam** và một bản chạy thủ công; luồng tương ứng là `src/flows/full_pipeline_flow.py`. API khởi tạo MongoDB, Qdrant, Voyage AI, OpenRouter và Redis cache qua `src/rag/api/server.py`. Giao diện có các trang `/`, `/news`, `/news/:ticker`, `/chat`.

Ngoài đường chính còn có **scraper MongoDB-only** tại `src/rag/ingestion/daily_scraper.py` và bộ flow cũ `src/rag/flows/`. `make scrape` hiện gọi scraper MongoDB-only, trong khi `python -m src.scraper.run` và Prefect đang dùng scraper PostgreSQL + MongoDB. Hai đường có quy tắc dừng sớm khác nhau, nên số liệu và cách xử lý bài mới không thể mặc nhiên coi là giống nhau.

## 3. Đã có những gì?

| Mảng | Hiện trạng theo repository | Mã/tài liệu chính |
|---|---|---|
| Thu thập CafeF | Có CLI, parser, retry HTTP, lọc trùng bằng `news_id`, bảng theo dõi từng lần chạy và tiến độ theo từ khóa. Đọc từ `vn30.xlsx`. | `src/scraper/`, `docs/SCRAPER.md`, `docs/INCREMENTAL_SCRAPING.md` |
| Lưu trữ | Scraper ghi metadata PostgreSQL và nội dung MongoDB. Phía RAG đọc MongoDB, ghi bài đã làm sạch, Qdrant lưu các đoạn vector. | `src/scraper/storage.py`, `src/rag/databases/` |
| Ingest/RAG | Đã viết làm sạch, chia đoạn, Voyage AI embed, truy xuất Qdrant, tạo trả lời OpenRouter và dẫn nguồn. Có lớp Redis semantic cache. | `src/pipeline/core.py`, `src/rag/ingestion/`, `src/rag/retrieval/`, `src/rag/agent/`, `src/rag/caching/` |
| Điều phối và quan sát | Có Prefect, MLflow, Prometheus/Pushgateway, Fluent Bit, Loki, Grafana và các dashboard cấu hình sẵn. | `src/flows/`, `docker-compose.yml`, `docker/grafana/`, `docs/OBSERVABILITY.md` |
| API/giao diện | Đã có API sức khỏe, danh mục VN50, tin tức, danh sách model, chat, feedback; React có giao diện duyệt tin và chat có chọn model/lọc mã. | `src/rag/api/`, `frontend/src/` |
| Đánh giá/kiểm thử | Có 35 câu hỏi RAG mẫu; có 272 hàm kiểm thử trong `tests/` và 198 hàm kiểm thử trong `src/model/tests/` theo rà soát tĩnh. Chưa có kết quả chạy test ở môi trường này. | `data/eval/`, `src/rag/evaluation/`, `tests/`, `src/model/tests/` |
| NER | Có dữ liệu gán nhãn, mã mô hình, script huấn luyện và tài liệu nghiên cứu. Không thấy checkpoint mô hình đã huấn luyện trong repository. | `src/model/`, `data/labeled/` |

### Dữ liệu hiện có trong repository

- `data/raw/cafef_news_raw.json`: **11.242** bản ghi; `cafef_news_raw_final.json`: **15.457** bản ghi. Đây là các tệp dữ liệu lưu sẵn, **không phải** số bài hiện nằm trong MongoDB.
- `data/labeled/ner/raw/output_ner.jsonl`: **59.175** dòng. Bộ NER `final_train/dev/test_vifinner.jsonl` lần lượt có **36.750 / 7.890 / 7.852** dòng.
- `data/labeled/span/`: **10.247** tệp JSON; `data/eval/rag_eval.jsonl`: **35** câu hỏi.
- `data/labeled/span_tags/3_EVENT_clean.json` có **62.391** câu như đề cương báo cáo ở giai đoạn chọn câu. Dữ liệu NER cuối cùng có **15 nhãn BIO/O, ứng với 7 loại thực thể** (`ASSET`, `DATE`, `MONEY`, `ORG`, `PERSON`, `RATE`, `VOLUME`). Đề cương nêu **8 loại**, thêm `EVENT`; tài liệu NER lại mô tả **10 loại**, thêm cả `TICKER`, `PRICE`. Cần đối chiếu quy trình lọc và phạm vi thí nghiệm trước khi công bố kết quả.

### Bằng chứng vận hành đã lưu

Log `logs/scraper/scrape_20260604T023806.json.log` ghi nhận một lượt chạy ngày **04/06/2026**: 5 mã, 19 từ khóa, 865 bài tìm thấy, **4 bài mới lưu**, 861 bài bỏ qua. Sau bước scrape, CLI dừng ở auto-ingest vì môi trường lúc đó thiếu `pydantic_settings`. Log này chứng minh scraper từng kết nối và lưu được dữ liệu; nó **không** chứng minh ingest, API hoặc chatbot đã chạy thông suốt. Các số trên chỉ thuộc lượt chạy đó.

## 4. Các điểm chưa hoàn tất hoặc cần sửa trước khi coi là chạy trọn vẹn

| Ưu tiên | Vấn đề có thể xác nhận từ mã | Hệ quả |
|---|---|---|
| Cao | `src/rag/evaluation/runner.py` còn đọc `settings.gemini.*`, trong khi cấu hình hiện chỉ có `voyage` và `openrouter`. | Luồng đánh giá RAG sẽ lỗi khi bắt đầu ghi tham số MLflow. |
| Cao | `src/flows/medallion_flow.py` import `src.preprocessing.medallion` không tồn tại; mã medallion thực nằm ở `src/model/preprocessing/medallion/` và vẫn tham chiếu `GeminiEmbedder`/PGVector cũ. | Luồng medallion chưa dùng được như mô tả. |
| Cao | Nhiều script trong `scripts/` và các lệnh `make ingest`, `make ask`, `make eval`, `make medallion`, `make *-langchain` tham chiếu `GeminiEmbedder`, `PgVectorRepository` hoặc `src.rag_langchain` không được export/không tồn tại. `make deploy` gọi `src.rag.flows.deploy`, khác đường Prefect đang chạy trong Docker. | Hướng dẫn/lệnh tiện ích có thể lỗi hoặc chạy đường cũ. |
| Cao | `AsyncRAGService` tra semantic cache chỉ theo embedding câu hỏi; entry không phân biệt model, ticker filter, `top_k` hay ngưỡng điểm. | Hai câu hỏi gần nhau nhưng khác phạm vi/model có thể nhận lại câu trả lời và nguồn dẫn không phù hợp. |
| Trung bình | API khai báo `post_date` là `str`, nhưng scraper chính lưu `datetime` và cleaner giữ nguyên trường này. | Cần kiểm thử serialization `GET /news`/`GET /news/by-link` với dữ liệu do scraper chính tạo; có nguy cơ lỗi validation. |
| Trung bình | API lấy model cho phản hồi chat từ `AsyncChatResult.model`, nhưng lớp này không có trường đó; khi khách không chỉ định model, phản hồi dùng chuỗi rỗng. | UI không thể hiển thị model thực đã trả lời, nhất là khi cache hit. |
| Trung bình | `README.md` đang rỗng; `docs/ARCHITECTURE.md` chủ yếu mô tả tầng scraper, còn `frontend/README.md` dẫn tới `docs/en/12_frontend.md` và `docs/vi/12_giao_dien.md` không có trong repo. Một số hướng dẫn môi trường dùng cổng MLflow `5000`, Compose hiện mở cổng host `5555`. | Người mới khó tìm đúng đường chạy và tài liệu dễ gây nhầm. |

Các nhận định về lỗi ở bảng trên là **đối chiếu mã tĩnh**, trừ lượt chạy log nêu rõ ở mục 3. Chưa xác nhận số liệu chất lượng RAG/NER, số bài trong dịch vụ hiện hành hoặc khả năng triển khai production.

## 5. Nên tiếp tục từ đâu?

1. **Chốt phương pháp khóa luận:** đề cương nêu Airflow/Spark, code hiện dùng Prefect/Python/Polars. Cần thống nhất bổ sung đúng công nghệ trong đề cương hoặc chỉnh đề cương được chấp thuận; sau đó chốt đường chạy chuẩn và sửa các lệnh/script cũ.
2. **Xác minh pipeline xuyên suốt:** cài dependency từ `requirements.txt`, chạy kiểm thử; khởi động stack và kiểm tra scrape → clean → Qdrant → `/health` → `/news` → `/chat` với một mã và ít trang. Ghi lại số lượng bài/chunk thực tế.
3. **Sửa tính đúng của RAG:** khóa cache theo model và bộ lọc; truyền model thực trong response; sửa evaluator dùng OpenRouter/Voyage; bổ sung kiểm thử dữ liệu `post_date` do scraper chính sinh ra.
4. **Quyết định phạm vi NER:** giải thích chênh lệch 8 loại trong đề cương, 10 loại trong tài liệu model và 7 loại trong tập cuối; lưu guideline, bằng chứng Kappa/F1 và xác định cách NER sẽ tham gia ứng dụng (nếu có).
5. **Chuẩn bị Output 3:** chốt nguồn giá và schema OHLCV; làm Kafka/Flink, serving và Power BI theo mốc tháng 10 trong đề cương. Xác định rõ chức năng “cá nhân hóa” nêu ở tên đề tài.

## 6. Nơi đọc tiếp

- Cách scraper hoạt động: [`SCRAPER.md`](SCRAPER.md), [`INCREMENTAL_SCRAPING.md`](INCREMENTAL_SCRAPING.md), [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md).
- Vận hành và hạ tầng: [`RUNBOOK.md`](RUNBOOK.md), [`OBSERVABILITY.md`](OBSERVABILITY.md), [`docker-compose.yml`](../docker-compose.yml).
- Kiến trúc NER: [`README_VI.md`](../src/model/docs/README_VI.md), [`RESEARCH_GAPS_VI.md`](../src/model/docs/RESEARCH_GAPS_VI.md).
- Điểm vào mã hiện tại: [`src/flows/deploy.py`](../src/flows/deploy.py), [`src/scraper/run.py`](../src/scraper/run.py), [`src/rag/api/server.py`](../src/rag/api/server.py), [`frontend/src/App.tsx`](../frontend/src/App.tsx).
