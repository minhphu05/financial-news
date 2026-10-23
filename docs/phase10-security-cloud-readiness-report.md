# Phase10 — Security remediation và final cloud readiness

**Đối chiếu dependency P09 sau pilot, 23/10 lúc closeout:** đã có bốn giờ live
năm nguồn với 50 mẫu; pilot PENDING vì crawl failures/partial, clean B1 chưa
chốt PASS và formal 24h/72h vẫn PENDING. Xem [báo cáo vận hành](phase9-pilot-report-2026-10-23.md).
Các trạng thái “B1 chưa có live” trong checkpoint audit dưới đây là lịch sử.
Không chạy lại security scan/owner remediation trong lượt closeout; Phase10
vẫn NO-GO, không thay issuer/history/advisory/sign-off bằng pilot evidence.

Thực thi local **22–23/10/2026**, cập nhật báo cáo **23/10/2026**,
`Asia/Ho_Chi_Minh`. JSON evidence dùng UTC. Baseline: branch `development`, HEAD
`240823cc6f2c1fa77f1609467b46fe21bcd5f858`. Ban đầu chỉ specification Phase10 của
người dùng là untracked; file đó được giữ nguyên. Không commit/push/merge/rebase,
rewrite history, rotate tài khoản hoặc provision/migrate cloud.

**Kết luận: NO-GO — NOT AUTHORIZED TO MIGRATE. Phase10 chưa DONE.**
Audit/guardrails local và thiết kế phục vụ review đã thực hiện; incident chưa có
issuer invalidation, history gate còn FAIL, P09 B1/24h/72h còn PENDING và owner
sign-off chưa có. CI YAML không phải bằng chứng remote workflow/protection đã chạy.

## 1. Bài toán và failure ban đầu

Phase06 kiểm chứng local platform nhưng release gate bảo mật phát hiện credentials
trong lịch sử. Lượt này chạy lại `make release-audit`: CLI exit **0**, trong khi
JSON `status=FAIL`, với năm tên biến `API_TOKEN`, `JWT_SECRET_KEY`,
`OPENROUTER_API_KEY`, `VOYAGE_API_KEY`, `GEMINI_API_KEY`. Hai paths lịch sử là
root `.env` và nested Gemini `.env`. Không xuất giá trị hoặc hash của secret.

`make phase6-report` hiện exit **2** (Python report exit **1**) và giữ report FAIL.
Report đó còn tiêu thụ các artifact functional lịch sử; không coi nó là full
Phase06 acceptance mới. Wrapper `tools/phase10.py phase6-gate` đọc verdict JSON,
trả exit **1** khi audit FAIL; Make wrapper exit **2**. Checker/policy cũ không
bị sửa để làm gate xanh. Không chạy lại full `make phase6-acceptance` trong lượt này.

## 2. CP0 — Preflight và discrepancies

Repository public theo unauthenticated GitHub API. Local clone không shallow,
có 13 reachable refs tại preflight, gồm local/remote-tracking và hai refs nội bộ.
Public metadata báo năm branches, protected flags bằng 0, ba PR đã đóng, zero
forks, zero releases/assets và zero Actions runs tại thời điểm query. Đây là
inventory metadata, không là scan mọi PR/cache/clone hoặc xác nhận admin settings.
Không fetch, tạo tainted mirror hoặc thay remote.

Phase09 đã merge. Evidence functional PASS là tám checks giữ từ full-run cộng
focused scheduling recheck sau sửa teardown; B1 live, real 24h và 72h còn PENDING.
S3 HTTP400 lịch sử chưa có root cause, không được tái diễn/giải quyết trong lượt này.
Workstation có 16 Compose services đang chạy tại preflight; `.env` quyền `0600`.
Không có CI/pre-commit hoặc Gitleaks/Trivy/pip-audit được cài tại baseline.

Discrepancies chính: không có handover file; không chỉ một variable bị ảnh hưởng;
Phase09 không DONE; branch/base Phase09 trong report là lịch sử; CLI audit exit 0
không phải security PASS; cloud/issuer/admin authority không được mặc định có.
Chi tiết: `artifacts/phase10/{preflight.json,preflight-summary.md,discrepancy-register.md,remote-surface-metadata.json}`.

## 3. CP1 — Discovery, threat model và phạm vi containment

Gitleaks **8.30.1**, release Linux x64 từ upstream, được kiểm archive SHA-256 và
version/help thực tế. Scan `git --log-opts="--all --full-history"` phát hiện
**ba pattern hits** ở hai `.env` paths lịch sử. Existing checker kiểm env blobs
và trả năm tên biến; granularity hai công cụ khác nhau, không phải ba/five live keys mới.

| Surface | Kết quả đã kiểm chứng | Giới hạn |
|---|---|---|
| Tracked + untracked non-ignored working tree | PASS, zero findings ở lần scan cuối trước tài liệu closeout | Symlinks không follow; phạm vi theo Git file inventory |
| Git staged diff | PASS ở repository hiện tại; không có thay đổi được stage bởi agent | Synthetic staged-secret case được kiểm riêng ở repo tạm |
| All locally reachable history | FAIL, ba Gitleaks hits; Phase06 năm variable names | Không remote-only PR/fork/cache hoặc unreachable object scan |
| Ignored local env/key config | Ba generic hits: JWT_SECRET_KEY, API_TOKEN, METADATA_CDC_PASSWORD trong `.env` | Đây là private runtime configuration, không chứng minh current values đã lộ hoặc giống historical values |
| Image Config.Env / CreatedBy | Sáu raw generic hits qua ba exact image IDs | Triaged public GPG release-signing fingerprints; raw verdict không bị xóa |
| Remote metadata | Public API inventory đọc được | Raw CI logs/private protections/fork/clone/cache không được quét |
| Evidence bundle | Metadata-only output và final bundle scan/triage | Không xem Git ignore là bằng chứng sanitization |

Threat model gồm unauthorized API usage/billing, giả mạo application/session khi
token/signing material từng dùng, clone/cache tái phát tán, image/build context
bake secret và log/CI re-exposure. Không có bằng chứng abuse hoặc issuer validity;
những mục đó **UNKNOWN**, không khẳng định đã compromised hoặc đã an toàn.

Finding IDs P10-SEC-001–005, owner roles, severity và trạng thái OPEN nằm trong
`sanitized-secret-inventory.md`. Không gửi old key tới provider để “thử còn sống”,
không đổi `.env`/access role/credential hoặc chặn toàn stack. Guardrails và NO-GO
là containment trong quyền agent; issuer containment vẫn BLOCKED.

## 4. CP2 — Rotation/recovery: kế hoạch có thể review, chưa thực thi

Issuer owners phải revoke/disable và xác minh old values invalid; app/auth owner
xác nhận phạm vi API/JWT deployments/sessions. Evidence cần action reference,
UTC, owner role, issuer/deployment invalidation result và tests bằng replacement,
không secret values. Việc xóa giá trị trong `.env` local của checkpoint trước
không chứng minh issuer revocation.

[Incident runbook](security/incident-response-runbook.md) mô tả sequencing,
maintenance/backup, client dependencies, Fernet/PG/MinIO/CDC concerns và rollback
bằng **new** credentials. Post-rotation runtime acceptance **BLOCKED**, vì chưa
có replacement được owner thực thi. Fixture PASS bên dưới không thay test này.

## 5. CP3 — History remediation decision

Đã chuẩn bị [runbook và approval checklist](security/git-history-remediation-runbook.md)
và `remediation-decision.md`. Owner cần quyết định cleanup/clean-history migration,
freeze, restricted backup/retention, tool/version, rehearsal, collaborators và
remote PR/cache/clone scope. Không tự ký risk acceptance, tạo tainted backup,
rewrite remote/local refs, gc/purge, force-push hoặc clean clone.

Existing historical gate vẫn **FAIL**. Không dùng baseline, blanket allowlist,
comment suppression hoặc “đã rotate” chưa có chứng cứ để chuyển PASS. Previous
Phase06 rehearsal trong document giữ đúng ngày/phạm vi, không nhận là kết quả mới.

## 6. CP4 — Guardrails và supply chain

Đã thêm `.gitleaks.toml`, `.pre-commit-config.yaml`,
`.github/workflows/security.yml`, `tools/security_scan.py`, `tools/phase10.py`,
`tools/supply_chain_audit.py`, tests và Make entrypoints. `.gitignore`/
`.dockerignore` loại private env/key material và Phase10 runtime evidence khỏi
Git candidate/build context; không đổi pipeline contracts hoặc transformations.

Scanner wrapper pin version/checksum, dùng explicit config/redact 100%, bỏ
implicit ignore fingerprints/inline allow, giữ temporary report ngoài repo rồi
chỉ serialize whitelisted metadata. Thiếu/sai tool, shallow history, scan error
hoặc coverage gaps không thành PASS. Staged mode kiểm index bytes. Tests còn
xác nhận upstream private-key rule bằng **malformed fixture không có key material**,
không chỉ custom synthetic marker.

Pre-commit **4.3.0** validate-config PASS; actual hook chạy trong disposable repo:
normal exit **0**, synthetic leak exit **1**, marker không có trong streams.
Không cài hook vào `.git/` của repository này. CI có bốn jobs: guard tests,
current tree, history/release và direct dependencies; checkout pin SHA,
read-only token và không persisted credentials. Remote CI run/required checks/
push protection chưa được thực thi/xác nhận trong Phase10.

Trivy **0.76.1** kiểm image local từ Docker daemon, không pull target images,
quét advisory HIGH/CRITICAL. pip-audit **2.10.1** kiểm installed Python metadata
và exact direct declarations. Inventory container read-only/network-none,
không env/mount secrets của runtime. Tool không `--fix`, nâng version hoặc thêm
vulnerability ignore. Các số dưới là **package/advisory occurrences**, không
unique CVEs hay bằng chứng exploit đang xảy ra.

| Exact image tag tại scan | HIGH | CRITICAL | Installed Python audit |
|---|---:|---:|---|
| financial-news-news-pipeline | 1001 | 53 | FAIL; sáu package/version entries có advisory sau focused collection fix |
| financial-news-airflow:2.11.2 | 433 | 44 | FAIL; 55 affected package entries ở lượt đã lưu |
| financial-news-metadata-tools:phase04 | 44 | 0 | FAIL; pip là affected package entry ở lượt đã lưu |

Image IDs, installed versions, advisory IDs, skip/errors và timestamps nằm trong
`supply-chain.json`. Direct audit exit **1**, affected declarations gồm Airflow
2.11.2 và DuckDB 1.4.1. Các transitive declarations rộng ở root requirements,
mutable tags/no digests, metadata image default root và local wildcard ports /
privileged cAdvisor/socket là residual risks cần owner triage; không tự đổi
runtime hoặc nâng Airflow major trong nhiệm vụ này.

DuckDB advisory được upstream mô tả cho database encryption; current builder
không dùng encryption options. Đây là ghi nhận reachability ban đầu, **không** là
false-positive waiver hay version fix. Airflow/auth packages và OS/JAR candidates
cần review theo endpoint/trusted DAG author/runtime permissions.
[DuckDB upstream advisory](https://github.com/duckdb/duckdb/security/advisories/GHSA-vmp8-hg63-v2hp).

Sáu image-config hits GPG_KEY được đối chiếu là 40-hex public fingerprints dùng
`gpg --recv-keys`/`--verify`, cho ba exact image IDs. Raw scan vẫn FAIL, triage riêng
ghi false positives; không thêm allowlist. Chưa scan toàn final filesystem/deleted
image layers, remote registry/private CI logs; không tuyên bố images sạch secrets.

## 7. Kiểm chứng chức năng và các lần sửa trong Phase10

| Command/check thực sự chạy | Kết quả | Phạm vi |
|---|---|---|
| `make phase10-security-tools` | Exit 0 | Download/version/checksum, cache ngoài repo |
| Security/readiness tests | 16 tests PASS, exit 0 ở focused check cuối | Synthetic rejection, staged-byte safety, default rule, redaction, fail-closed, guard verdict và giữ mọi installed versions; acceptance trước đó có 15 tests |
| Pipeline/crawler/P05/P09 selected unit + PostgreSQL integration | 77 tests PASS, exit 0 | Exact container command tại `pipeline-unit-db.json` |
| Monitoring/metrics/metadata unit selection | 17 tests PASS, exit 0 | `monitoring-unit.json` |
| Airflow DAG tests | 10 tests PASS, exit 0 | Scheduler container, `airflow-dag-unit.json` |
| Existing five-source fixture E2E | Exit 0 | Real MinIO/PG/Spark/Delta/FastEmbed/Qdrant/DuckDB, update/replay/reconciliation; không public website |
| Monitoring smoke + crawler observability | Exit 0; hai integration tests PASS | Existing Prometheus/Grafana/services |
| Metadata CDC lifecycle smoke | Exit 0, result success | Snapshot/update/delete/tombstone/control-plane lifecycle; không restart toàn stack |
| `make release-audit` / Phase10 wrapper | CLI 0/JSON FAIL; wrapper Python 1/Make 2 | Giữ historical gate |
| `make phase6-report` | Make 2; aggregate report FAIL | Còn kết hợp historical function artifacts, không full acceptance mới |
| `make phase10-acceptance` | Make 2 / Python 2 | Expected NO-GO, tách local tests PASS khỏi issuer/history/P09 gates |

Actual commands/UTC/exit codes và counts được lưu trong metadata JSON; child
streams có thể chứa service context nên không lưu raw stdout/stderr. Các path
chỉ chứa artifact tổng hợp, không HTTP HTML hoặc credential values. Regressions
không dùng replacement credentials vì CP2 chưa thực hiện. Không chạy lại full
P05/P07/P08/P09 acceptance targets, không controlled live hoặc burn-in dài hạn.

Lần guard mở rộng đầu tiên FAIL do malformed private-key fixture ngắn hơn minimum
64 ký tự của upstream rule, không phải detector default đã tắt. Đã sửa fixture
vô hiệu đúng rule; không thêm key thật hoặc làm yếu scanner. Wrapper audit JSON
ban đầu không xử lý Make footer; sửa parse bằng JSONDecoder.raw_decode, không sửa
checker. Installed inventory Spark có setuptools 59.6.0 và 84.0.0 cùng tên khiến
single requirements audit conflict. Đã chia hai advisory query groups, giữ cả
hai phiên bản; focused retry không discard phiên bản cũ hoặc waive CVE.
Evidence initial/superseded giữ trong `attempt-1/` và diagnosis JSON.

## 8. CP5 — Azure readiness design pack

Đã tạo target architecture, ADLS preflight, IAM matrix, network/cost/rollback và
P11 entry checklist dưới `docs/cloud/`. Tất cả là **DRAFT / chưa owner review**.
P11 chỉ storage canary sau GO, giữ compute/PG/Kafka/Qdrant local. ABFS byte/Spark
adapters, identities và actual compatibility tests chưa triển khai. Không tạo
Terraform/Bicep scaffold, Azure account/resource hoặc migration data.

Thiết kế giữ logical keys và Delta logs/manifests, source-scoped serving, operational
checkpoints, exact checksum/schema/ID/row parity và rollback về MinIO. HNS có ràng
buộc không revert flat namespace; không giả định Blob versioning hỗ trợ HNS;
budget alerts không tự chặn tiêu dùng. Subscription/region/quota, cost input,
spending authority, network và restore evidence vẫn UNKNOWN/PENDING, không có giá
hoặc benchmark tự tạo. Official references gắn tại từng design document.

Read-only MinIO metadata inventory lúc **00:32 ngày 23/10/2026 (+07:00)** hoàn
thành năm pages cho bucket `financial-news`: **4.441 objects / 507.939.966 bytes**.
Bronze 85 objects, Landing 338, Silver 2.924, Gold 954, operations 140; tổng gồm
historical snapshots, fixture data và Delta logs, không phải article count.
Size bins và bytes theo prefix ở `source-storage-inventory.json`, không giữ raw
object keys/content. Listing không freeze writers và không có restore proof;
`migration_consistency=NOT_ESTABLISHED`. Không dùng thời gian listing làm benchmark
hoặc giả định đây là closed-writer ledger đã đủ điều kiện migrate.

## 9. CP6 — Acceptance matrix và risk decision

| ID | Trạng thái | Evidence / phần còn thiếu |
|---|---|---|
| A01 | PASS phạm vi local preflight | Branch/SHA/dirty baseline/ref count/API facts; owners chưa xác nhận quyền |
| A02 | VERIFIED STATUS; prerequisite PENDING | P09 functional có provenance; required live duration chưa có |
| A03 | PASS discovery phạm vi đã scan | Five-variable inventory + Gitleaks; không xác minh issuer validity |
| A04 | BLOCKED | Chưa owner revoke/verify old values |
| A05 | BLOCKED | Working tree sạch nhưng active historical validity và remote content chưa biết |
| A06 | PENDING APPROVAL | History decision/runbook sẵn, chưa owner ký |
| A07 | NOT EXECUTED | Không rewrite hoặc fresh clone; không thay bằng scan local |
| A08 | FAIL | Existing Phase06 history/security gate còn FAIL |
| A09 | PASS phạm vi local | Ignore/build context/scan configuration + deterministic proof |
| A10 | PASS local equivalent; remote PENDING | Actual hook/negative tests; YAML chưa có remote CI execution |
| A11 | OPEN / FAIL | Dependency/image candidates có inventory, triage ban đầu; chưa remediation/approval |
| A12 | BLOCKED | Chưa credentials replacement/issuer invalidation |
| A13 | PASS phạm vi selected regression | 77/17/10 tests, fixture E2E, monitoring/CDC lifecycle; full targets không chạy |
| A14 | DRAFT / INCOMPLETE | ADLS compatibility preflight có; actual canary/owner review chưa có |
| A15 | DRAFT / INCOMPLETE | Identity/access matrix có; principal/authority/sign-off chưa có |
| A16 | DRAFT / INCOMPLETE | Network/cost/rollback có; input/ngân sách/restore proof/owner còn thiếu |
| A17 | PASS phạm vi agent changes | Không login Azure, provision, IaC apply hoặc cloud copy |
| A18 | PASS phạm vi metadata outputs và final review | Evidence index/sanitized fields; raw findings giữ ngoài repo tạm rồi xóa |
| A19 | NO-GO; signature PENDING | Agent lập verdict từ blockers, không ký thay authorized owners |
| A20 | CHECKLIST PREPARED; ENTRY BLOCKED | P11 storage-only boundary rõ, không được bắt đầu migration |

Risk IDs R10-01–14 và owner roles tại `risk-register.md`. Phần chưa làm không
được biến thành PASS nhờ fixture test hoặc scan sạch. Scan FAIL phù hợp gate
không phải lý do sửa checker/allowlist để đóng phase.

## 10. Handoff và việc cần owner thực hiện

1. Issuer/app owners đóng P10-SEC-001–005 bằng invalidation + replacement recovery
   evidence an toàn; kiểm usage/billing/sessions trong scope đã dùng.
2. Repository admin phê duyệt remediation lịch sử, freeze/collaborators/backup,
   review remote scopes; triển khai CI/protections và kiểm fresh clone gate.
3. Runtime/security owners triage/fix/mitigate advisories bằng phiên bản tương
   thích, image rebuild và relevant regressions; không tự miễn trừ để GO.
4. Operator hoàn tất P09 B1 live → 24h → go/no-go → 72h thật; đóng incidents,
   restore/baseline evidence. Không chạy 24/72h trong CI.
5. Cloud/spending owners review design pack, scope/identity/network/cost/stop/
   rollback và ký GO. Khi đạt mới được đề nghị P11 ADLS canary; chưa có quyền tự migrate.

Các outputs runtime nằm trong ignored `artifacts/phase10/`, có thể thiếu ở fresh
clone; engineering report không thay raw machine evidence khi cần kiểm chứng mới.
Prepared by: coding agent, evidence assembly. **Approved by: PENDING** authorized
security/repository/cloud owners. Verdict kỹ thuật/report: **NO-GO**; quyết định
và chữ ký có thẩm quyền vẫn PENDING, không được coding agent ký thay.

## 11. Tái lập các kiểm tra trong scope

```sh
make phase10-preflight
make phase10-security-tools
make phase10-test
make phase10-security-scan       # hiện FAIL vì history; không bypass
make phase10-history-gate        # hiện FAIL dù old audit CLI exit 0
make phase10-dependency-audit    # hiện FAIL vì advisory, không auto-fix
make phase10-image-config-scan  # raw generic hits, cần đọc triage
make phase10-regressions        # ghi fixture state; cần stack đã healthy
make phase10-acceptance         # hiện exit 2 / NO-GO
make phase10-readiness-report   # hiện exit 2 / NO-GO
```

Image audit dùng verified Trivy 0.76.1 và `uv`/pip-audit 2.10.1 ngoài repo:
`python3 tools/supply_chain_audit.py --trivy /path/to/trivy --image <local-image>`.
Không đưa credentials lên command line. Tool inventory/scan là local-only, không
đăng nhập hay kiểm Azure resources. Sau mỗi thay đổi thực chất phải rerun phạm
vi tương ứng; không biến report trên thành lời hứa mọi môi trường đều PASS.

## 12. Kiểm tra closeout local và cập nhật tài liệu — 23/10/2026

- Focused guard/readiness suite cuối: **16 tests PASS**, exit 0; lint và format
  check qua cả năm Python files mới. Các runtime regression đã PASS phía trên
  giữ timestamps riêng, không chạy lại chỉ vì format/doc changes.
- Markdown links/headings/fences: **27 files, 383 local links, 28 linked headings,
  146 fenced blocks**, không lỗi. Luận văn giữ 53 sections/18 bảng/11 caption và
  thêm E47–E49 thành 49 nhóm evidence; outline/analysis/future work/reproduction
  và presentation được đồng bộ, cloud/security current state không bị gán sai.
- Data-contract read-only check exit 0, không schema drift hoặc volume changes;
  không regenerate profile hay đổi contract. Git diff không đổi source pipeline,
  DAG/migration/CDC, Compose hoặc existing history checker. Không có staged changes.
- Effective config check exit 0: cron `None`, scheduled live switch false, cả
  năm source live policies false; missing raw JSON key được xử lý bằng policy
  default false, không suy ra live từ null. `.env` vẫn quyền `0600`.
- CI YAML/TOML được parse/kiểm cấu trúc: bốn jobs, contents read, checkout SHA
  pinned, credentials không persisted, default rules bật, không blanket allowlist.
  Đây là static/local verification, **không** remote CI hoặc host protection proof.
- Evidence snapshot scan có một generic false positive trên generated preflight
  coverage-status enum. Raw FAIL và triage được giữ, không làm sạch verdict bằng
  suppressions; không phát hiện giá trị secret trong scope bundle đã review.
  Archive checksum/tool versions ghi tại `tools-manifest.json`.
- `git diff --check` PASS. `docs/thesis/`, `docs/present-demo/` và
  `artifacts/phase10/` đang Git ignored; tài liệu local/evidence không tự vào commit
  thông thường. Không stage, commit, push, history rewrite hoặc deploy.

Các kết quả closeout này hoàn tất phần triển khai/kiểm chứng local trong quyền
agent; **không đóng Phase10**. Owner-dependent incident/history/advisory/P09/
design-signature gates vẫn ở đúng trạng thái NO-GO/PENDING đã ghi.
