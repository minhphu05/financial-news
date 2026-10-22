# Network, chi phí và rollback — thiết kế chưa phê duyệt

Khởi tạo 22/10, cập nhật 23/10/2026. Không provision resource hoặc tự chọn ngân sách/region.

## Network và trust boundaries

P11 giữ Spark/Airflow/PostgreSQL/Kafka/Qdrant local. Source crawl outbound HTTP
vẫn theo policy/robots từng nguồn, độc lập data-plane storage. Storage target cần
TLS, endpoint allowlist hoặc private endpoint có đường DNS/VPN phù hợp máy local;
không bật public unrestricted chỉ để canary chạy. Public/private endpoint, VNet,
subnet/NSG, DNS, cert/audit logs và người vận hành: **PENDING REVIEW**.

P12 mới đánh giá network AKS và database. Tách ingress UI/API khỏi internal
PostgreSQL/Kafka/Connect/Qdrant; không mang wildcard-bound local ports/plaintext
defaults vào cloud. Local inventory ghi `cadvisor` privileged/socket mount và
nhiều wildcard ports; Phase10 ghi rủi ro, chưa tự đổi port hoặc recreate services.

## Worksheet chi phí — chưa có giá hoặc measured cloud workload

| Hạng mục | Input owner phải cung cấp | Cách ước tính / trạng thái |
|---|---|---|
| ADLS capacity/replication | GB theo closed inventory, region, SKU, retention | GB-month × đơn giá trong subscription; PENDING |
| Storage operations | Read/write/list/rename + Delta small files/log commits | Số operations × tariff phù hợp; PENDING measurement |
| Network | Upload, egress, private endpoint/VPN và DNS | GB + service-hours; không mặc định miễn phí |
| Local compute P11 | Spark hours và máy vận hành | Giữ local; không giả lập thành Azure compute bill |
| P12 AKS/DB/ACR | VM/node hours, managed disk, DB tier, registry/egress | Chưa chọn sizes/count/region; PENDING |
| Monitoring/backup | Ingest GB, retention, restore/copy volume | Tách storage, logs và restore charges; PENDING |

Subscription/spending authority, currency/region, quota, approved ceiling,
notification recipient và teardown owner đều **UNKNOWN/PENDING**. Dùng pricing
calculator/billing theo subscription khi owner cung cấp input; không tạo con số
giá hoặc workload thay người dùng. Tag đề xuất: project, environment, owner role,
cost-center và expiry; tên cụ thể chờ policy.

Azure budget alerts **không tự dừng consumption/resource**. P11 cần hard-stop ở
quy trình/operator/automation được duyệt riêng; chưa có stop automation hay budget
đã tạo. Không coi một notification threshold là cost cap.
[Azure budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).

## Rollback scope storage-only

| Trigger | Stop và điều tra | Recovery |
|---|---|---|
| Checksum/object set/Delta log mismatch | Pause target writer và giữ evidence | Quay config về MinIO checkpoint đã đóng, reconcile trước resume |
| Auth/permission/expiry hoặc DNS/TLS lỗi | Không retry vô hạn hoặc mở quyền rộng | Sửa scoped identity/network sau review; source không bị ghi đè |
| Latency/cost/backlog vượt ngưỡng owner duyệt | Pause theo runbook, lưu timestamps/resource/incident | MinIO anchor; threshold và GO review lại, không tự bịa SLO |
| Operational state lệch lake | Không advance checkpoint hoặc replay bừa | Restore/reconcile đúng lake + metadata reference, rebuild derived serving |

Rollback không migrate/revert PostgreSQL/Kafka/Qdrant compute cùng lúc. Không
đẩy dữ liệu target mâu thuẫn về source; phân tích và review conflict trước. Source
anchor chỉ được retire sau parity, rollback drill và owner sign-off. RPO/RTO,
backup retention và restore proof **PENDING**; đường dẫn backup tồn tại không đủ.

## IaC workflow dự kiến

Chưa tạo Terraform/Bicep scaffolding vì chưa được yêu cầu riêng. Khi được duyệt:
review modules storage/HNS/identity/RBAC/network, pin providers, encrypted restricted
state backend, non-secret tfvars schema, validate/plan và independent approval
trước apply. Không đưa state file hoặc plan chứa sensitive values vào Git/artifact
public. Owner chịu trách nhiệm preview chi phí, teardown và xác minh resource inventory.
