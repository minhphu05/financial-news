# Chính sách xử lý secret — Phase10

Áp dụng cho pipeline local và thay đổi tương lai. Khởi tạo 22/10, cập nhật 23/10/2026.
Trạng thái: guardrails có implementation; incident lịch sử chưa đóng, cloud NO-GO.

## Lưu trữ và sử dụng

Secret thật chỉ đặt trong `.env` local bị ignore/quyền `0600`, secret mount có
quyền tối thiểu hoặc secret store được chủ tài khoản quản lý. Không đưa secret
vào source, Docker `ARG`/`ENV`, image layer, notebook output, URL, command-line,
fixtures, screenshots, logs hoặc evidence. Template chỉ có placeholders; không
sao chép giá trị thật vào `.env.example`. Không dump `docker inspect`/Compose
đã interpolate hoặc environment ra terminal dùng chung.

Giá trị trong runtime env không tự chứng minh đã lộ ra Git; cũng không chứng minh
secret lịch sử đã vô hiệu. Local default và plaintext broker hiện tại không phải
cấu hình production. Không đưa raw HTML/live corpus vào Git. Ngoại lệ fixture
HTML tổng hợp đã track phải có provenance, không chứa secret hoặc nội dung live.

## Guardrails được thêm

`tools/security_scan.py` dùng Gitleaks **8.30.1**, archive Linux x64 được kiểm
SHA-256 trước cài ở cache ngoài repository. `.gitleaks.toml` kế thừa upstream
rules và thêm marker tổng hợp vô hiệu để kiểm tra negative case. Không có history
baseline/path allowlist; inline `gitleaks:allow` và implicit fingerprint ignore
không được dùng để bypass wrapper. Raw scanner streams không được xuất; file
redacted tạm nằm ngoài repo, rồi chỉ xuất rule/path/line/commit và trạng thái.
Không xuất match, secret, fingerprint/hash của secret, author/email/message.

```sh
make phase10-security-tools
make phase10-test
python3 tools/security_scan.py staged
python3 tools/security_scan.py working-tree
make phase10-security-scan
make phase10-history-gate
```

Exit `0` là PASS trong scope được ghi, `1` là finding/gate FAIL, `2` là BLOCKED.
Thiếu scanner/version sai/shallow history không được coi sạch. `ignored-config`
là inventory private local, không phải gate để xóa secret hợp lệ khỏi runtime.
Scan không xác minh hiệu lực ở provider, không OCR ảnh, không mở archive hoặc
bao phủ fork/PR cache/CI logs/image layers từ xa.

`.pre-commit-config.yaml` scan **index diff**, nên working tree sạch không che
được secret còn staged. Người vận hành cài pre-commit trong môi trường riêng và
chạy `pre-commit install`; lượt Phase10 không sửa hooks trong `.git/`. Local test
đã gọi đúng wrapper trên index của repository tạm. Workflow
`.github/workflows/security.yml` có guard tests, current tree, full-history gate
và direct dependency audit; `contents: read`, checkout pin SHA,
`persist-credentials: false`, không production credentials. Chưa có remote CI run
hoặc host protection nào được xác nhận chỉ từ file YAML.

GitHub quản lý quyền tạo/dùng secrets theo repo/environment/organization;
repo admin phải review quyền và required checks khi áp dụng CI.
[GitHub Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## Dependency và image

`tools/supply_chain_audit.py --direct-only` kiểm exact Python declarations trong
ba Dockerfile active, không thay dependency. Audit image local dùng Trivy
**0.76.1** cho HIGH/CRITICAL và pip-audit **2.10.1** cho installed Python metadata;
không truyền runtime secret/mount vào container inventory. Không tự nâng version,
bỏ advisory hoặc chạy `--fix`. Direct-only không bao phủ transitive/OS; skipped
package và scanner failure giữ BLOCKED. Registry, deleted layers, legacy images
và exploitability cần đánh giá riêng.
[pip-audit](https://github.com/pypa/pip-audit),
[Trivy container images](https://trivy.dev/docs/latest/target/container_image/).

Mọi exception cần finding ID, bằng chứng false positive, owner/reviewer và scope
hẹp; không allowlist cả dataset hoặc cả loại API key. Scanner PASS không thay
issuer invalidation, history gate hoặc owner sign-off. Xem
[incident runbook](incident-response-runbook.md) và
[báo cáo Phase10](../phase10-security-cloud-readiness-report.md).
