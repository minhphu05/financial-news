# Prefect Orchestration Platform

## 1. Giới thiệu

Prefect là một **Workflow Orchestration Platform** dùng để xây dựng, quản lý và tự động hóa các luồng xử lý dữ liệu (workflow/data pipeline) bằng Python.

Prefect giúp:

* Tự động hóa ETL/ELT pipeline
* Scheduling workflow
* Monitoring quá trình chạy
* Retry khi task lỗi
* Quản lý dependency giữa các task
* Theo dõi log và trạng thái thực thi

Khác với nhiều orchestration platform truyền thống, Prefect hoạt động theo mô hình:

```text
Code-first Orchestration
```

Tức là workflow được viết trực tiếp bằng Python thay vì phải định nghĩa bằng DSL hoặc file cấu hình phức tạp.

---

# 2. Kiến trúc tổng quát của Prefect

Prefect gồm 2 thành phần chính:

```text
+----------------------+
|    Prefect Server    |
|----------------------|
| REST API             |
| Scheduler            |
| UI Dashboard         |
| Database             |
+----------+-----------+
           ^
           |
           | HTTP API
           |
+----------+-----------+
|     Prefect Client   |
|----------------------|
| Python SDK           |
| @flow                |
| @task                |
| Worker               |
+----------------------+
```

---

# 3. Prefect Client (Python SDK)

## 3.1 Cài đặt

```bash
pip install prefect
```

Phần Client là thư viện Python dùng để:

* Định nghĩa workflow
* Định nghĩa task
* Execute workflow
* Report trạng thái execution lên Server

---

## 3.2 Flow và Task

Trong Prefect:

* `@flow` dùng để định nghĩa workflow
* `@task` dùng để định nghĩa từng đơn vị công việc nhỏ

Ví dụ:

```python
from prefect import flow, task

@task
def extract():
    print("Extracting data")

@task
def transform():
    print("Transforming data")

@flow
def etl_pipeline():
    extract()
    transform()

etl_pipeline()
```

---

## 3.3 Vai trò của Client

Khi flow chạy:

* Client sẽ execute code Python
* Đồng thời gửi trạng thái lên Prefect Server

Ví dụ:

* Task bắt đầu chạy
* Task completed
* Task failed
* Flow completed

Thông tin này được gửi thông qua HTTP REST API.

---

# 4. Prefect Server

## 4.1 Vai trò

Prefect Server là backend orchestration của hệ thống.

Server cung cấp:

* REST API
* Scheduling
* Workflow orchestration
* Logging
* State management
* Monitoring dashboard

---

## 4.2 Khởi động Server

```bash
prefect server start
```

Mặc định:

```text
UI Dashboard: http://127.0.0.1:4200
API Endpoint: http://127.0.0.1:4200/api
```

---

## 4.3 Chức năng của Server

Prefect Server giúp:

* Lưu lịch sử chạy flow/task
* Theo dõi trạng thái workflow
* Tự động scheduling
* Retry task khi lỗi
* Quản lý deployment
* Quản lý work pool và worker

Nếu chỉ có Python SDK mà không có Server:

* Không có giao diện monitoring
* Không xem được lịch sử chạy
* Không scheduling tự động
* Không orchestration tập trung

---

# 5. Giao tiếp giữa Client và Server

Prefect sử dụng HTTP REST API để giao tiếp.

## 5.1 Push-based Communication

Khi chạy flow bằng tay:

```python
my_flow()
```

Client sẽ chủ động gửi trạng thái execution lên Server.

Ví dụ:

```text
Client -> Server
POST /flow_runs
POST /task_runs
```

Đây là mô hình:

```text
Push-based state reporting
```

---

## 5.2 Pull-based Communication

Khi sử dụng Worker:

* Worker sẽ polling Server liên tục
* Hỏi xem có job nào cần chạy không

Ví dụ:

```text
Worker -> Server
GET /work_pools/.../get_runs
```

Nếu có flow pending:

* Worker kéo job về
* Execute flow
* Report trạng thái ngược lại

Đây là mô hình:

```text
Pull-based execution
```

---

# 6. PREFECT_API_URL

Client cần biết địa chỉ API của Server thông qua biến môi trường:

```bash
export PREFECT_API_URL=http://127.0.0.1:4200/api
```

Khi flow chạy:

```python
my_flow()
```

Prefect SDK sẽ gửi request tới API Server thông qua URL này.

---

# 7. Worker và Work Pool

## 7.1 Work Pool

Work Pool dùng để định nghĩa môi trường thực thi workflow.

Ví dụ:

* Local Process
* Docker
* Kubernetes
* ECS
* Cloud Run

Work Pool đóng vai trò như hàng đợi công việc (job queue).

---

## 7.2 Worker

Worker là một tiến trình nền dùng để polling job từ Server.

Khởi động Worker:

```bash
prefect worker start --pool my-pool
```

Worker sẽ:

1. Polling Server
2. Kiểm tra flow pending
3. Kéo flow về chạy
4. Report trạng thái execution

---

# 8. Scheduling

Prefect hỗ trợ scheduling workflow tự động.

Ví dụ:

* Chạy mỗi ngày
* Chạy mỗi giờ
* Cron scheduling
* Interval scheduling

Ví dụ cron:

```python
from prefect.server.schemas.schedules import CronSchedule
```

---

# 9. Retry và Failure Handling

Prefect hỗ trợ:

* Retry task khi lỗi
* Delay giữa các lần retry
* Timeout
* Failure state management

Ví dụ:

```python
@task(retries=3, retry_delay_seconds=5)
def fetch_data():
    pass
```

---

# 10. Logging và Monitoring

Prefect cung cấp:

* Centralized logging
* Flow run history
* Task state visualization
* Runtime monitoring

Tất cả được hiển thị trên Web UI.

---

# 11. Ưu điểm của Prefect

## 11.1 Code-first

Workflow là Python thật:

```python
if x > 5:
    task_a()
else:
    task_b()
```

Không cần DSL riêng như nhiều orchestration tool khác.

---

## 11.2 Dễ mở rộng

Có thể chạy trên:

* Local machine
* Docker
* Kubernetes
* Cloud environment

---

## 11.3 Monitoring trực quan

Có Dashboard để:

* Theo dõi flow
* Debug lỗi
* Xem log
* Theo dõi trạng thái runtime

---

# 12. So sánh Prefect và Airflow

| Tiêu chí         | Prefect      | Airflow      |
| ---------------- | ------------ | ------------ |
| Workflow Style   | Code-first   | DAG-first    |
| Language         | Python       | Python       |
| Dynamic Workflow | Tốt          | Hạn chế      |
| UI Monitoring    | Có           | Có           |
| Scheduling       | Có           | Có           |
| Retry            | Có           | Có           |
| Setup            | Đơn giản hơn | Phức tạp hơn |

---

# 13. Kết luận

Prefect là một nền tảng orchestration hiện đại giúp xây dựng và quản lý workflow bằng Python một cách linh hoạt và trực quan.

Prefect phù hợp cho:

* Data Engineering
* ETL/ELT pipeline
* Machine Learning pipeline
* Workflow automation
* Cloud-native orchestration

Với mô hình code-first và kiến trúc client-server, Prefect giúp đơn giản hóa việc phát triển, monitoring và scheduling workflow trong các hệ thống dữ liệu hiện đại.
