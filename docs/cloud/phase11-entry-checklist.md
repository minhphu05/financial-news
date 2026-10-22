# Phase11 entry gate — storage canary only

Khởi tạo 22/10, cập nhật 23/10/2026. **NO-GO — NOT AUTHORIZED TO MIGRATE**.

| Entry criterion | Evidence cần có | Hiện tại |
|---|---|---|
| Credentials bị lộ invalid tại issuer/deployment | Restricted owner action + verification refs | BLOCKED |
| Approved history remediation | Freeze/backup/collaborators/fresh clone + full refs/host review | PENDING |
| Existing Phase06 gate sạch | Audit JSON PASS và release report theo policy hiện hành | FAIL |
| P09 live + 24h/72h thực | UTC/monotonic/boot/coverage, actual live/scheduler histories, incidents | PENDING |
| Regression phù hợp sau credential changes | Tests/reconciliation bằng replacement, không chỉ fixtures trước rotation | BLOCKED — chưa có rotation |
| Dependency/container high-risk triage | Image/package/advisory IDs, reachability/fix/regression hoặc approved mitigation | OPEN; xem report Phase10 |
| ADLS/ABFS/Delta compatibility design | Version/auth/namespace/log semantics, canary tests | DRAFT, chưa review owner |
| IAM/network/cost/quota | Principal/scope, connectivity, subscription authority, budget/hard-stop | UNKNOWN/PENDING |
| Consistent source inventory và restore | Checksum/object/Delta/PG checkpoint + restore evidence | PENDING |
| Authorized gate decision | Security/repository/cloud owner sign-off có UTC và scope | NOT PROVIDED |

Sau khi tất cả gates được chứng minh và có GO, mục tiêu đầu tiên chỉ là local
Airflow/Spark read/write một ADLS storage canary đã duyệt; giữ MinIO rollback
anchor. Không migrate toàn stack, bật AKS/managed PostgreSQL hoặc benchmark trong
P11 storage scope. Phase12/13 là quyết định riêng.

Handoff cần clean commit/CI protections; sanitized incident closeout; source
ledger; runtime versions; HNS/layout; identity/network/cost constraints; parity
queries; rollback trigger/owner; measured P09 baseline và open-risk owners.
Coding agent chỉ chuẩn bị evidence; không ký thay chủ tài khoản hoặc spending authority.
Xem [Phase10 report](../phase10-security-cloud-readiness-report.md).
