# Identity và quyền truy cập Azure — đề xuất

Khởi tạo 22/10, cập nhật 23/10/2026. DRAFT, chưa tạo principal/role/Key Vault hoặc đăng nhập Azure.
Tenant, subscription, người cấp quyền và sign-off: **UNKNOWN/PENDING**.

| Principal tương lai | Quyền cần | Scope dự kiến | Owner/review còn thiếu |
|---|---|---|---|
| P11 migration operator | Đọc source, ghi subset canary, kiểm checksum | Temporary target filesystem/container, không subscription Owner | Cloud owner cấp/thu quyền có expiry/MFA |
| P11 Spark/byte adapter | Read/write/list và Delta log operations | Storage data role tại container được duyệt, ACL nếu cần | ETL + IAM owner kiểm negative access/expiry |
| P12 crawler | Đọc config, ghi Landing | Identity riêng, Landing paths | Không cấp quyền Gold/admin mặc định |
| P12 transformation | Đọc Bronze/Silver, ghi Silver/Gold | Path/container boundaries được review | Verify role/ACL thực sự cho Delta, không dựa tên role |
| Serving builder | Đọc Gold, ghi projection Qdrant/DuckDB | Identity tách data-lake writer | Endpoint credentials ở approved secret store |
| CI deployment | Build/push immutable image, deploy phạm vi được duyệt | Federated identity giới hạn repo/branch/environment | Repo/cloud admins review OIDC trust và approval |
| Monitoring/operator | Read metrics/logs, thao tác được duyệt | Reader/Monitoring scope | Không data write/subscription admin mặc định |

Ưu tiên Entra ID và storage data roles; Azure management roles không tự thay thế
data-plane role. Quyền cần cấp ở scope nhỏ nhất đủ hoạt động, với negative tests
cho prefix/operation ngoài phạm vi.
[Azure RBAC for blob data](https://learn.microsoft.com/en-us/azure/storage/blobs/assign-azure-role-data-access).

Local P11 chưa có AKS managed identity endpoint: phải chọn cơ chế login/token
provider hỗ trợ bởi **Hadoop 3.3.4 thực tế**, có expiry/refresh và không bake client
secret. Không mặc định nối DefaultAzureCredential của Python là Spark sẽ dùng
được. Byte adapter và ABFS là hai authentication integrations cần test riêng.

P12 có thể dùng AKS Workload Identity/federated tokens theo service account;
đây là target, chưa có trust policy/cluster hoặc token exchange được kiểm chứng.
[AKS Workload Identity](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview).

Secrets chưa thay bằng identity cần approved Key Vault/secret mount, người quản
lý lifecycle, audit logs và access review. Không dùng token đã lộ cho migration;
không hỏi/chuyển giá trị secret vào tài liệu. Signed URLs/SAS không được xuất qua
CLI logs, metrics labels hoặc manifest public. Record provisioning reference và
test result thay vì credential value; sign-off vẫn **PENDING**.
