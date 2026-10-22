# Runbook ứng phó secret bị lộ

Khởi tạo 22/10, cập nhật 23/10/2026. Đây là quy trình cho người có quyền; chưa phải bằng chứng revoke.
Không yêu cầu gửi secret cho coding agent, issue hoặc chat.

## 1. Phát hiện và containment

Giữ release/cloud ở NO-GO; ngừng chia sẻ raw findings. Ghi finding ID, loại,
đường dẫn/commit, owner role và phạm vi refs/surface. Không ghi giá trị hoặc hash
của secret. Restricted incident detail, audit logs và bản sao tainted phải ở
ngoài repository, quyền truy cập/retention do owner quyết định. Không tự xóa
volumes, reset CDC offsets hoặc dừng toàn bộ stack để “làm sạch”.

Inventory hiện có năm tên biến lịch sử: `API_TOKEN`, `JWT_SECRET_KEY`,
`OPENROUTER_API_KEY`, `VOYAGE_API_KEY`, `GEMINI_API_KEY`. Không có bằng chứng các
giá trị hiện còn hoạt động hoặc đã vô hiệu. Không suy luận đây là Azure keys.
Repository public; clone/fork/cache ngoài quyền quản lý chưa được xác minh.

## 2. Owner thực hiện lifecycle

| Nhóm | Owner cần xác nhận | Thao tác và bằng chứng an toàn |
|---|---|---|
| Gemini / Voyage / OpenRouter | Chủ tài khoản tại issuer tương ứng | Xác định credential bị lộ trong console riêng; revoke/disable; kiểm tra usage/billing; ghi action ID/timestamp và kết quả issuer xác nhận invalid |
| API token nội bộ | App/service owner | Xác minh môi trường đã dùng, tạo replacement scope tối thiểu, cập nhật secret store, invalid token cũ và test client |
| JWT signing secret | App/auth owner | Xác định deployment/session bị ảnh hưởng, đổi signing material có kế hoạch, vô hiệu token/session cũ; kiểm tra authenticate/deny |
| Các secret khác phát hiện thêm | Owner của issuer | Mở rộng incident inventory; không tự cho là false positive hoặc đã được xử lý cùng năm biến trên |

Chỉ có record “đã thay `.env` local” không đủ đóng incident. Phải có bằng chứng
old credential invalid tại issuer/deployment, không dùng giá trị cũ trong test
log/process flags. Khi active leak cần revoke ngay, owner ghi rõ downtime và
sequencing; không phục hồi bằng cách bật lại credential lộ.

## 3. Runtime recovery sau rotation được phê duyệt

1. Xác định client/service liên quan, snapshot/backup có restore evidence và
   maintenance window; pause workload bị ảnh hưởng mà giữ durable state.
2. Cập nhật replacement ngoài Git; hạn chế quyền; không tạo account/cloud resource
   ngoài phạm vi đã duyệt. Không in environment hoặc connection string.
3. Kiểm Landing/Bronze read/write/checksum, Delta Silver/Gold, reconciliation,
   Qdrant/DuckDB, Airflow DAG controlled fixture, metadata CDC và monitoring.
4. Với PostgreSQL, phối hợp app/pool/Debezium DSN; giữ offsets và WAL continuity.
   Với MinIO, kiểm Delta log và các object writes. Với Airflow Fernet, dùng quy
   trình đúng version và backup encrypted metadata, không chỉ thay key rồi restart.
5. Xác nhận old secret invalid, theo dõi lỗi/alert rồi ghi evidence đã redact.

CLI Airflow có thao tác rotation encryption riêng; phải review thủ tục/version
được cài trước khi dùng. Lượt này không gọi thao tác đó.
[Airflow 2.11 CLI reference](https://airflow.apache.org/docs/apache-airflow/2.11.0/cli-and-env-variables-ref.html).

## 4. Đóng incident

Owner ghi finding ID, old-secret invalidation reference, replacement functional
test reference, thời gian UTC, người có quyền xác nhận và residual risks. Raw
provider logs giữ restricted. Sau đó mới xử lý history theo
[runbook Git](git-history-remediation-runbook.md), scan lại và chạy existing
Phase06 gate. GitHub khuyến nghị revoke/rotate trước khi cân nhắc rewrite; việc
rewrite cần phối hợp vì có thể tái nhập lịch sử từ clone cũ.
[GitHub sensitive data removal](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

Không ai được chuyển NO-GO thành GO chỉ từ scan sạch hoặc chữ ký của coding
agent. Signature có quyền, P09 time-based evidence và các gate còn lại vẫn bắt buộc.
