# Financial News / ViFinNER

Dự án khóa luận về dữ liệu tài chính Việt Nam, gồm ba đầu ra theo đề cương: nghiên cứu nhận dạng thực thể tài chính (ViFinNER), website tin tức và chatbot RAG, cùng pipeline dữ liệu giá cổ phiếu để phân tích trên Power BI.

**Hiện trạng:** repository đã có dữ liệu/mã NER và phần lớn mã cho website/RAG. Pipeline giá cổ phiếu Kafka/Flink và Power BI chưa có trong repo. Phần web/RAG hiện dùng Prefect và Python/Polars, khác Airflow/Spark được ghi trong đề cương. Chưa có lượt kiểm chứng end-to-end ở môi trường rà soát.

Đọc theo thứ tự:

1. [Đối chiếu đề cương và các khoảng cách cần xử lý](docs/THESIS_ALIGNMENT.md).
2. [Hiện trạng codebase và dữ liệu](docs/PROJECT_STATUS.md).
3. [Scraper CafeF](docs/SCRAPER.md), [sơ đồ dữ liệu](docs/DATABASE_SCHEMA.md), [hướng dẫn vận hành](docs/RUNBOOK.md).
4. [Kiến trúc mô hình NER](src/model/docs/README_VI.md).

Điểm vào ứng dụng hiện tại: `src/scraper/run.py` cho scraper chính, `src/flows/deploy.py` cho Prefect, `src/rag/api/server.py` cho FastAPI và `frontend/src/App.tsx` cho giao diện.
