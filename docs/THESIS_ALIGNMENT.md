# Đối chiếu đề cương khóa luận với repository

**Rà soát:** 20/09/2026, nhánh `development`, commit `037038a`.

**Nguồn đối chiếu:** `CQUI_DECUONGKLTN_23520782_23521183.md` do nhóm cung cấp (bản ngày 05/09/2026), đặc biệt các mục 1, 4, 6, 7 và 8. Tài liệu này ghi lại những gì có thể kiểm tra từ mã và dữ liệu trong repository. Các kết quả nghiên cứu được **đề cương báo cáo** được giữ riêng với các kết quả **có thể kiểm chứng trong repository**.

> **Cập nhật 23/09/2026:** khoảng cách Spark/Airflow nêu trong bản rà soát ngày 20/09 đã được xử lý cho riêng pipeline tin tức local: Bronze → Spark Silver → Gold → Qdrant/DuckDB chạy độc lập và qua hai DAG Airflow. Xem [bronze-silver-local.md](bronze-silver-local.md), [silver-gold-local.md](silver-gold-local.md), và [airflow-local.md](airflow-local.md). Các nhận định bên dưới về NER, website/cá nhân hóa, dữ liệu giá, Kafka/Flink và Power BI vẫn là phạm vi của lần rà soát gốc và chưa được Phase 01–03 thay đổi.

> **Cập nhật Phase 04, 23/09/2026:** repository nay có PostgreSQL → Debezium → Kafka cho **metadata/configuration control plane**. Luồng này chỉ phát thay đổi của `news_sources` và `pipeline_configs`; nó không phải pipeline giá cổ phiếu Kafka/Flink được đề cương yêu cầu. Xem [metadata-control-plane.md](metadata-control-plane.md).

## Kết luận ngắn

**Dự án đúng hướng về bài toán tin tức và RAG, nhưng chưa bám sát toàn bộ đề cương đã nộp.** Trong ba đầu ra, website/RAG có nhiều thành phần đã viết; NER có dữ liệu và mã huấn luyện nhưng thiếu chuỗi bằng chứng thực nghiệm đầy đủ trong repo; pipeline giá cổ phiếu và Power BI chưa thấy triển khai. Hai thay đổi công nghệ lớn là **Prefect thay Airflow** và **Python/Polars thay Spark**. Đây là khác biệt so với phương pháp được nêu đích danh trong đề cương, không chỉ là cách đặt tên khác.

Nếu đề cương là cam kết kỹ thuật phải giữ, nhóm cần triển khai/đánh giá Airflow và Spark theo phạm vi đã ghi, hoặc thống nhất chỉnh đề cương với giảng viên hướng dẫn. Không thể chỉ đổi tên Prefect thành Airflow hay Polars thành Spark trong báo cáo.

## Ma trận ba đầu ra

| Đầu ra trong đề cương | Bằng chứng hiện có | Khoảng cách so với đề cương | Nhận định |
|---|---|---|---|
| **1. ViFinNER:** guideline, Gemini gợi nhãn, con người duyệt, 8 loại thực thể, Cohen's Kappa, so sánh baseline/XLM-R | Có dữ liệu thô và tập train/dev/test, mã tạo nhãn Gemini, notebook tiền xử lý, nhiều kiến trúc và script huấn luyện trong `src/model/`. Tệp `data/labeled/span_tags/3_EVENT_clean.json` có 62.391 câu. `data/labeled/ner/split/note.txt` nói tập cuối đã được chỉnh thủ công. | Chưa tìm thấy guideline độc lập, phiếu/nhật ký duyệt nhãn, cặp nhãn của hai annotator, script tái tính Kappa, bảng kết quả model hay checkpoint trong repo. Tập BIO cuối có **7 loại**, không có `EVENT`; tài liệu mô hình lại giới thiệu **10 loại**. | **Một phần; kết quả 0,88 Kappa và 87,12% Micro-F1 là số đề cương báo cáo, chưa tái kiểm chứng được ở repo này.** |
| **2. Tin tức, website, RAG:** Airflow theo lịch, Spark xử lý, web tra cứu, chatbot có nguồn | Có scraper CafeF, PostgreSQL/MongoDB, Prefect flow, Python cleaner/chunker, Voyage AI/Qdrant/OpenRouter, FastAPI và React. Có trang chủ, tin tức, trang theo mã, chatbot; dẫn nguồn bằng URL bài. | Không có DAG Airflow hoặc Spark job/dependency. Chưa có trang chi tiết bài viết nội bộ; thẻ tin mở CafeF. Tìm kiếm mới theo tiêu đề và mã, chưa theo chủ đề. Chưa xác nhận pipeline từ scrape đến chat chạy thông suốt. | **Đúng hướng sản phẩm, khác phương pháp đã cam kết, chưa chứng minh end-to-end.** |
| **3. Giá cổ phiếu và BI:** OHLCV, Kafka, Flink, event time/window, serving, Power BI | Có danh mục mã VN50 và số bài báo theo mã (`src/rag/lib/vn50.py`, API `/stocks`). | Không thấy collector/nguồn giá, schema OHLCV, Kafka/Flink, bảng aggregate giá hoặc file Power BI. Grafana hiện có là quan sát vận hành, không thay thế dashboard thị trường. | **Chưa bắt đầu trong repository.** Theo lịch mục 8.3, phần này dự kiến bắt đầu 01/10/2026; hiện là rủi ro tiến độ, chưa phải mốc đã quá hạn. |

## Các khác biệt ảnh hưởng đến việc bảo vệ khóa luận

### 1. Airflow/Spark so với Prefect/Python/Polars

Đề cương mục 4.2, 4.3.2, 5.4 và 5.5 đặt Airflow làm bộ điều phối trung tâm và Spark làm lớp xử lý batch. `docker-compose.yml` thực tế khởi chạy Prefect; deployment đang dùng là `src/flows/deploy.py` và `src/flows/full_pipeline_flow.py`. Làm sạch đang chạy qua `src/pipeline/core.py` và `src/rag/ingestion/cleaner.py`; nhánh medallion Polars nằm ở `src/model/preprocessing/medallion/` nhưng hiện import sai đường dẫn và còn tham chiếu Gemini/PGVector cũ, nên không phải một Spark job có thể thay thế trong báo cáo.

Lựa chọn kỹ thuật khác vẫn có thể đáp ứng **mục tiêu chức năng** (lập lịch, retry, làm sạch) nếu được chấp thuận, nhưng không chứng minh được các mục đánh giá dành riêng cho Airflow/Spark. Mốc Airflow 16–31/08 và Spark 01–15/09 trong mục 8.3 đã qua vào thời điểm rà soát. Cần chốt với giảng viên hướng dẫn: bổ sung Airflow/Spark để bám đề cương, hoặc sửa chính thức phần phương pháp và tiêu chí đánh giá cho kiến trúc hiện tại.

### 2. Dữ liệu NER cần một bảng truy vết rõ ràng

Đề cương nói 11.242 bài CafeF → 62.391 câu chứa sự kiện → bộ NER 8 loại (`ORG`, `PERSON`, `ASSET`, `EVENT`, `MONEY`, `RATE`, `VOLUME`, `DATE`). Trong repo:

- `data/raw/cafef_news_raw.json` có **11.242** bản ghi.
- `data/labeled/span_tags/3_EVENT_clean.json` có **62.391** câu, phù hợp số đề cương nêu ở bước trích câu.
- `data/labeled/ner/raw/output_ner.jsonl` có **59.175** dòng, trong đó có một số nhãn không chuẩn và 2 dòng không có khóa `tags`.
- Ba tập `data/labeled/ner/syllables/final_{train,dev,test}_vifinner.jsonl` có tổng **52.492** mẫu và 15 nhãn BIO/O, tức **7 loại thực thể**, thiếu `EVENT`. `TICKER` và `PRICE` trong `src/model/docs/README_VI.md` cũng không nằm trong tập cuối và ngoài 8 loại của đề cương.

Các số này có thể là các giai đoạn lọc khác nhau; repo chưa giải thích tiêu chí loại mẫu/chuyển nhãn. Cần lập bảng provenance từ 62.391 → 59.175 → 52.492, nêu rõ vì sao `EVENT` không có trong tập cuối, và thống nhất schema nhãn giữa guideline, dữ liệu, model, báo cáo. Nếu `EVENT` chỉ dùng để chọn câu mà không là nhãn BIO cuối, cần nói đúng như vậy và chỉnh mô tả “8 loại” cho thí nghiệm BIO.

Đề cương báo cáo Kappa **0,88** và XLM-R Large Micro-F1 **87,12%** từ nghiên cứu trước; không thấy artifact đủ để tính lại hai số này trong repository. Nên lưu protocol đánh giá, seed, split, cặp annotation độc lập, script tính Kappa, báo cáo precision/recall/F1 và checkpoint hoặc ít nhất bảng kết quả có provenance. Script Gemini trong `src/model/llms_inference/` còn dùng đường dẫn tuyệt đối của máy cũ, nên cần sửa để tái chạy được.

### 3. Website/RAG hiện có nhưng chức năng và đánh giá còn thiếu

Luồng tin tức và giao diện bám khá sát Output 2: scrape tăng dần, làm sạch, vector hóa, API tra cứu, chatbot có citation. Tuy nhiên:

- Đề cương yêu cầu trang chi tiết bài viết và lọc theo mã/chủ đề. `frontend/src/App.tsx` mới có `/`, `/news`, `/news/:ticker`, `/chat`; `NewsCard.tsx` mở bài gốc. API `/news` chỉ lọc `ticker` và tìm chuỗi trong `title`.
- Tên đề tài có “cá nhân hóa” nhưng chưa thấy tài khoản, watchlist, sở thích, gợi ý hay đặc tả kiểm thử cá nhân hóa. Đây là **khoảng trống phạm vi cần định nghĩa**, không thể suy ra chỉ từ lọc mã cổ phiếu.
- Bộ đánh giá RAG gồm 35 câu (`data/eval/rag_eval.jsonl`) và các metric keyword/ticker recall, refusal, latency. Đề cương còn yêu cầu retrieval relevance, groundedness và answer relevance; chưa thấy phép đo/nhãn đánh giá cho các tiêu chí đó. `src/rag/evaluation/runner.py` hiện đọc `settings.gemini.*` đã bị bỏ, nên luồng eval chưa chạy đúng với OpenRouter/Voyage.
- `src/rag/caching/async_inference.py` tra cache theo embedding câu hỏi mà không phân biệt model hay bộ lọc mã; cần sửa trước khi dùng số liệu chất lượng RAG. `docs/PROJECT_STATUS.md` ghi thêm các điểm kỹ thuật cần sửa.

### 4. Streaming/Power BI là đầu ra bắt buộc, hiện chưa có nền móng trong repo

Đề cương mục 4.3.3 yêu cầu nguồn giá, event backbone Kafka, xử lý Flink theo event time/window, lớp serving và Power BI. Repo hiện chỉ có **metadata mã cổ phiếu**, không có dữ liệu giá/khối lượng. Cần chốt nguồn dữ liệu được phép dùng, tần suất cập nhật và độ trễ có thể đạt; sau đó định nghĩa schema tối thiểu gồm mã, thời điểm sự kiện, OHLCV, nguồn và chất lượng dữ liệu. Một dashboard Grafana về log/CPU không đáp ứng Output 3.

Theo lịch đề cương, Kafka/Flink vào **01–12/10**, Power BI vào **13–20/10**, tích hợp/đánh giá vào **21–31/10/2026**. Vì chưa thấy mã nền tảng, cần chuẩn bị nguồn giá và hợp đồng dữ liệu ngay trong tháng 9 để các mốc tháng 10 có thể kiểm thử được.

## Thứ tự công việc đề xuất theo mốc đề cương

1. **Ngay bây giờ:** thống nhất với giảng viên hướng dẫn phương án Airflow/Spark; xác nhận thế nào là “cá nhân hóa”; chốt nguồn giá cổ phiếu và phạm vi cập nhật. Đây là các quyết định về phạm vi, không nên che bằng thay đổi tài liệu mô tả mã.
2. **Trước khi kết thúc phần web/RAG (30/09):** sửa đường chạy/scripting cũ, chạy smoke test từ CafeF đến `/chat`, kiểm tra citation; bổ sung trang chi tiết hoặc giải thích rõ thay thế bằng liên kết bài gốc; bổ sung tiêu chí groundedness và answer relevance với bộ câu hỏi có nhận xét con người.
3. **Song song:** hoàn thiện bảng lineage NER, bộ nhãn chính thức, guideline và artifact tái lập Kappa/F1. Phân biệt kết quả nghiên cứu đã báo cáo với kết quả tái chạy trên mã hiện tại.
4. **Trước 01/10:** có source contract và mẫu dữ liệu giá OHLCV. Sau đó triển khai Kafka producer, Flink processor, bảng serving, rồi Power BI theo đúng các mốc 8.3; đo latency, tỷ lệ sự kiện hợp lệ và freshness như mục 4.3.4.
5. **Trước nghiệm thu:** chạy test tích hợp và lưu bằng chứng: số bài/chunk, trạng thái job, kết quả RAG/NER, độ trễ streaming, ảnh/dashboard Power BI và hướng dẫn demo. Chỉ dùng số liệu đã đo trong báo cáo cuối.

## Giới hạn của lần rà soát

Ma trận dựa trên repository tại commit nêu trên và tệp đề cương được cung cấp. Không có container đang chạy khi kiểm tra; môi trường Python chưa cài dependency để chạy test. Có thể có guideline, checkpoint, kết quả nghiên cứu hoặc Power BI ở nơi khác chưa được đưa vào repo; tài liệu này đánh dấu chúng là **chưa có bằng chứng trong repo**, không phủ nhận chúng tồn tại bên ngoài.

Đọc hiện trạng kỹ thuật chi tiết hơn tại [`PROJECT_STATUS.md`](PROJECT_STATUS.md).
