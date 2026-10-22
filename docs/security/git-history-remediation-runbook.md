# Quyết định và runbook remediation lịch sử Git

Khởi tạo 22/10, cập nhật 23/10/2026. Trạng thái: **PENDING OWNER APPROVAL — NOT EXECUTED**.
Đây là phương án review, không là quyền rewrite/force-push hoặc tạo tainted backup.

## Quyết định cần chốt

Revoke/verify old credentials trước. Gate Phase06 hiện vẫn phát hiện năm tên biến
nhạy cảm ở `.env` và
`src/model/llms_inference/gemini_models/config/.env`; scanner mới không thay checker
cũ. Owner chọn controlled cleanup hoặc lịch sử repo sạch với kế hoạch collaborators.
Risk acceptance đơn thuần không làm existing gate PASS. Không tạo blanket allowlist.

| Đầu vào phê duyệt | Cần ghi | Hiện tại |
|---|---|---|
| Issuer invalidation | Restricted action/reference, UTC, owner role | NOT VERIFIED |
| Freeze/review | Repo admin, collaborators, branches/tags/PRs, khoảng thời gian | PENDING |
| Backup | Nơi ngoài repo, access, encryption, retention và người được restore | PENDING; không tạo clone chứa secret trong lượt này |
| Scope | Hai path đã xác nhận, các findings khác nếu discovery bổ sung | Hai path là scope tối thiểu, không bảo đảm toàn bộ exposure |
| Remote support | Forks, PR refs/cache, release assets, CI logs và cloned copies | Chưa có quyền/admin review đầy đủ |

## Rehearsal sau khi có phê duyệt

Tạo disposable mirror ở nơi restricted, pin và kiểm version/help của
`git-filter-repo`. Ghi mapping refs/old SHA, tree/contracts và giới hạn cleanup.
Loại đúng affected paths/content; không sửa working repo đang có task người dùng.
Scan toàn relevant refs ở bản diễn tập, chạy integrity/fsck và so sánh tree để
chứng minh không mất code/dữ liệu ngoài scope. Không gọi đây là rehearsal PASS
khi mới có runbook hoặc dựa vào số đo của checkpoint cũ.

Khi rehearsal đạt và owner đồng ý, admin phối hợp update remote; không cung cấp
một lệnh destructive auto-run trong Make/CI. Collaborators re-clone hoặc xử lý
branch theo hướng dẫn admin; không merge lịch sử tainted vào branch đã clean.
Scan fresh clone từ remote, kiểm refs/forks/cache trong quyền kiểm soát, chạy
Phase06 audit/report cùng regressions. Chỉ giải freeze khi các check và acknowledgment
được lưu. Không rollback bằng push lại old refs chứa secret.

## Điều kiện dừng và phạm vi scan

Dừng nếu còn active/unknown credential, unauthorized push, mất tree/contracts,
build/test không tái lập hoặc phát hiện tainted history quay lại. Gitleaks
`--all --full-history` chỉ bao phủ local reachable refs, kể cả remote-tracking refs
đã có; không đồng nghĩa đã fetch/scan toàn remote-only PR refs, unreachable objects,
fork/cache hoặc mọi clone. Không tự fetch/clone thêm các bản sao chứa secret để
làm đẹp coverage khi chưa có kế hoạch restricted storage.

Lượt Phase10 chỉ scan refs local và public metadata, không rewrite, xóa ref/tag,
gc/purge, remote mutation hoặc tạo bản backup tainted. Verdict vẫn NO-GO.
[GitHub: removal process và side effects](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
