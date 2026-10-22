# Phase 10 — Security / Secret Remediation Gate & Final Cloud Readiness

> **Loại:** Engineering implementation plan / AI coding-agent task specification  
> **Đường dẫn đề xuất trong repo:** `docs/agent_tasks/10-security-secret-remediation-final-cloud-readiness.md`  
> **Hệ thống:** Graduation Thesis — financial-news data platform  
> **Phạm vi:** Security remediation + cloud-readiness verification; **KHÔNG triển khai/migrate Azure**  
> **Trạng thái:** `PLANNED — NOT EXECUTED` (không có bằng chứng Phase 10 đã làm)  
> **Nguồn nền:** `CHAT_CONTEXT_HANDOVER_LATEST.md`, Phase 09 task plan, và repository hiện tại (ưu tiên cao nhất).  
> **Ngày lập plan:** 2026-10-22

---

## 0. Executive summary

### 0.1 Bối cảnh được handover xác nhận

- Dự án triển khai **local-first**: MinIO, Spark/Delta, Airflow, PostgreSQL, Debezium/Kafka metadata CDC, Qdrant, DuckDB, Prometheus/Grafana.
- Phase 08 báo cáo PASS local acceptance (`make phase8-acceptance`, exit 0) với **5 news sources**: **CafeF, VnExpress, Tuổi Trẻ, Thanh Niên, Báo Mới**; mỗi nguồn có raw schema riêng nhưng **canonical contract không đổi**.
- Phase 09 được lập kế hoạch để bật lịch crawl tự động có kiểm soát, đo burn-in 24/72h và hoàn thiện khả năng vận hành local. **Không tự giả định Phase 09 đã PASS** nếu repo/log thực tế không chứng minh.
- Phase 06 local/cloud readiness function được báo cáo đã hoạt động, nhưng **cloud release gate bị BLOCK bởi một credential từng xuất hiện trong Git history**; trước đó acceptance exit 2 ở security gate.
- Roadmap: **P09 continuous local operations → P10 security & final cloud readiness → P11 Azure storage migration → P12 cloud platform migration → P13 benchmark → P14 thesis demo**.

### 0.2 Mục tiêu Phase 10

Chuyển trạng thái từ:

```text
LOCAL VALIDATED (+ Phase 09 stable if proven)
CLOUD RELEASE = NOT READY (historical credential)
```

sang:

```text
SECURITY INCIDENT REMEDIATED WITH EVIDENCE
REPO / BUILD / RUNTIME GUARDS VERIFIED
AZURE MIGRATION PRECONDITIONS DOCUMENTED
FORMAL CLOUD GO / NO-GO RECORDED
```

**Phase 10 không đồng nghĩa “đã chạy trên Azure”.** GO chỉ cho phép **bắt đầu Phase 11** theo phạm vi đã phê duyệt.

### 0.3 Đóng góp cho khóa luận

1. **Security engineering:** có bằng chứng cách phát hiện, xử lý, ngăn tái lộ credentials.
2. **Release governance:** release gate định lượng/kiểm chứng được thay vì tuyên bố cloud-ready cảm tính.
3. **Reproducibility:** cấu hình, dependency, container, rollback và kiểm chứng data contract được chuẩn hóa.
4. **Cloud-migration risk reduction:** đánh giá trước các điểm khác biệt MinIO/S3 ↔ ADLS Gen2, identity/network, cost, compatibility.
5. **Evidence:** tạo tài liệu và bằng chứng kỹ thuật để bảo vệ quyết định chỉ migrate khi gate sạch.

### 0.4 Definition of Done (cấp phase)

- [ ] P09 được xác minh theo repo (functional acceptance và trạng thái burn-in **thật**, không giả định).
- [ ] Đã xác định được phạm vi, loại và đường đi phát tán của historical credential **mà không ghi lộ lại giá trị**.
- [ ] Mọi credential bị ảnh hưởng được revoke/rotate (hoặc có bằng chứng đã vô hiệu hóa), xác minh không còn hiệu lực.
- [ ] Có quyết định remediation cho Git history; nếu rewrite, có phê duyệt, backup kiểm soát, phối hợp contributors và verify toàn bộ refs/remotes có liên quan.
- [ ] Không còn leak chưa xử lý; công cụ scan/Phase 06 gate không bị bypass; mọi exception phải có quyết định của người phụ trách và **không được tự chuyển gate thành PASS**.
- [ ] Scan staged/working tree/history, CI artifacts, Docker build/runtime configurations; kết quả được redacted.
- [ ] Pre-commit/CI/push protections hoặc cơ chế tương đương được cấu hình/test; không commit secret, `.env`, HTML live, runtime artifacts.
- [ ] Relevant regressions, operational smoke tests, security acceptance đều PASS; không làm gãy P05/P07/P08/P09.
- [ ] Có cloud-readiness design pack cho ADLS, IAM, network, IaC, cost, backup/rollback, baseline parity **không provisioning**.
- [ ] Có report, evidence index, risk register và bảng quyết định GO/NO-GO được ký xác nhận bởi người có quyền.

> **Hard gate:** Nếu credential chưa được vô hiệu hóa, historical-security gate còn BLOCK, hoặc Phase 09 chưa có bằng chứng vận hành theo yêu cầu, kết luận phải là `NO-GO` hoặc `CONDITIONAL / BLOCKED`; tuyệt đối không ghi `CLOUD READY`.

---

## 1. Scope, dependencies, non-goals, invariants

### 1.1 In scope

- Read-only audit repo, history, active refs, remotes, forks/PRs nếu liên quan.
- Secret inventory, incident classification, exposure assessment và containment.
- Rotation/revocation phối hợp với chủ sở hữu credential; xác minh ứng dụng vẫn hoạt động sau đổi credentials.
- Controlled cleanup Git history **khi được phê duyệt và có cơ sở**.
- Preventive guardrails cho local development, Git, CI/CD, image và runtime.
- Dependencies/container/configuration security baseline & policy review.
- Revalidate Phase 06 cloud security gate cùng regression các phase liên quan.
- Cloud target readiness assessment, interfaces, security model, compatibility/test plans, budgets và rollback design.
- Báo cáo đánh giá, acceptance matrix, review checkpoint, handoff Phase 11.

### 1.2 Out of scope

- Tạo Azure Resource Group, Storage Account/ADLS, ACR, AKS, PostgreSQL Flexible Server hoặc tài nguyên trả phí.
- Migrating / copying dữ liệu production/local sang Azure trong Phase 10.
- Deploy Terraform/Bicep thật; thay cluster/orchestrator hoặc thiết kế lại stack.
- Scaling/benchmark local vs cloud (Phase 13); migration validation production (P11/P12).
- Thay canonical contract, raw contract, incremental semantics hoặc định nghĩa lại Kafka làm article queue.
- Add 5+ news sources, crawler throughput optimization, xây frontend/RAG serving facade.
- Force-push/rewrite remote history, delete refs/tags, rotate cloud keys hoặc thay user access **khi chưa có explicit approval và kế hoạch phối hợp**.

### 1.3 Architectural invariants

```text
CafeF / VnExpress / Tuổi Trẻ / Thanh Niên / Báo Mới
  -> source-specific crawler + Landing RAW
  -> Bronze -> Spark/Delta Silver -> Gold RAG / Gold Analytics
  -> Qdrant / DuckDB

Airflow = orchestrator
PostgreSQL + Debezium + Kafka = metadata control-plane CDC
Qdrant/DuckDB = derived, rebuildable serving stores
Landing/Bronze/Silver/Gold + operational metadata = durable truth
```

- `control_metadata.news_sources.config`, `crawler_operations` và Airflow DAG `news_crawling_pipeline` giữ đúng vai trò.
- Không tự tạo ticker, NER, sentiment hay financial events nếu pipeline không thực sự sinh ra chúng.
- Không thêm URL/article ID/run ID làm Prometheus metric labels.
- Không giữ secret trong Git repo, tests fixture public, config templates, documentation, screenshots, log hoặc artifact evidence.
- Revoke/rotate **luôn ưu tiên trước** việc thảo luận rewrite history. Git history cleanup **không làm credential đã lộ trở nên an toàn trở lại**.

### 1.4 Source-of-truth precedence

1. Code/config/test/log ở repository hiện tại.
2. `docs/agent_tasks/CURRENT_STATUS.md`.
3. Engineering reports mới nhất (`phase9`, `phase8`, `phase6`).
4. Phase task files.
5. `CHAT_CONTEXT_HANDOVER_LATEST.md`.

**Agent phải ghi discrepancies**, không sử dụng handover làm bằng chứng implementation mới nhất.

---

## 2. Preflight & release inventory — P10.0

### 2.1 Trước khi thay đổi repo

Đọc tối thiểu:

```text
AGENTS.md
README.md
Makefile
.gitignore
.gitattributes
.pre-commit-config.yaml        # nếu tồn tại
.github/workflows/            # nếu tồn tại

docs/data-contracts.md
artifacts/data-profile.json
docs/agent_tasks/CURRENT_STATUS.md
docs/agent_tasks/05-pipeline-hardening-local.md
docs/agent_tasks/06-local-release-cloud-readiness.md
docs/agent_tasks/07-monitoring-observability-local.md
docs/agent_tasks/08-multisource-crawling-ingestion-local.md
docs/agent_tasks/09-continuous-local-crawling-scheduling-burnin.md

docs/phase8-engineering-report.md
docs/phase9-engineering-report.md                 # nếu Phase 09 đã tạo
docs/crawler-operations.md
docs/crawling-architecture.md
docs/source-mapping-matrix.md
```

Inspect `Dockerfile*`, `docker-compose*`, `airflow/`, `spark/`, application config files, IaC nếu có, `requirements`/lockfiles và secret-loading code.

### 2.2 Read-only commands được phép chạy trước

```bash
cd /home/trongkhoi/financial-news

git branch --show-current
git status --short
git status --branch
git log --oneline --decorate -n 20
git remote -v
git branch -a
git tag --list
git diff --stat

git ls-files
```

**Không** chạy `git log -p`, `git show` hoặc `git grep` hiển thị raw secret lên terminal/chat/shared log. Mọi search credential phải dùng scanner có redaction và quy trình bảo vệ kết quả.

Đọc trạng thái Phase 09: actual tests/exit codes, burn-in start/end/duration, source status, outstanding incidents, Phase 09 git integration status. Nếu chưa hoàn tất, đánh dấu **prerequisite pending** và chỉ thực hiện phần P10 độc lập (audit/readiness doc) khi an toàn.

### 2.3 Snapshot / state capture

Tạo **sanitized** preflight record chứa:

- Branch, base commit SHA, changes count (không lưu nội dung secret).
- Repo visibility (public/private), host, access roles (không ghi tokens).
- Active refs/remotes/forks/PRs có khả năng chứa commit bị ảnh hưởng.
- CI provider, existing protection rules, scanning/gates.
- Container/image registry và các artifact có thể tồn tại.
- Owners: app, secrets, Git admins, cloud account (chỉ role, không ghi personal secrets).
- P09 evidence, open issues, S3 HTTP 400 unresolved status.

**Output:** `artifacts/phase10/preflight-summary.md` và `artifacts/phase10/discrepancy-register.md`.

### 2.4 P10.0 exit criteria

- [ ] Current-state facts có provenance và timestamps.
- [ ] Không tự sửa/delete/stage/push file.
- [ ] Xác định owners & permissions cho credential lifecycle và remote history operations.
- [ ] Không có hành động rủi ro cao xảy ra trong preflight.

---

## 3. Secret discovery, classification & containment — P10.1

### 3.1 Threat/scope inventory

Khảo sát tối thiểu các loại credential:

| Category | Ví dụ nguồn có thể phát sinh | Ứng xử |
|---|---|---|
| Azure | tenant/app secrets, storage key, connection string, SAS | Classify, revoke/rotate, prefer identity |
| Git/CI | PAT, deploy key, workflow secret, webhook token | Revoke & restrict privileges |
| MinIO/S3 | root/access/secret keys, S3 endpoint configs | Replace & validate read/write paths |
| PostgreSQL | app/admin passwords, connection strings | Rotate; minimize admin usage |
| Airflow | admin/DB/Fernet/session secrets | Rotate per product migration guidance; prevent invalidating encrypted connections |
| Kafka/Connect/Debezium | DB credentials, SASL/API credentials | Rotate; check connector health |
| Qdrant/Grafana/Prometheus | API keys, dashboards datasources creds | Rotate where relevant |
| Other | private keys, certs, `.env`, dumped payloads | Remove exposure, revoke if usable |

**Handover không chỉ rõ loại credential đã từng bị commit.** Không được tự kết luận đó là Azure/MinIO/PostgreSQL token nếu repo chưa xác nhận.

### 3.2 Scan surfaces

- [ ] Entire repository history trên **tất cả refs có thể reach**, không chỉ HEAD.
- [ ] Working tree, staged changes, untracked files có nguy cơ được commit.
- [ ] Branches/tags, release assets, forks/clones (nếu có quyền/được cộng tác).
- [ ] PR diffs, cached objects, build/test artifact, CI logs.
- [ ] Dockerfiles, image layers/build args, Compose config, Kubernetes manifests (nếu có), Helm values.
- [ ] Documentation, examples, notebooks, screenshot outputs, traces/log dumps.
- [ ] Runtime service config and mounts ở local, permissions trên volumes; không export secret values vào report.
- [ ] Tham chiếu từ `git submodule`/LFS (nếu tồn tại).

### 3.3 Tooling strategy

- Ưu tiên local scanner đáng tin cậy, ví dụ **Gitleaks** hoặc **TruffleHog**, được pin phiên bản phù hợp repo; kết hợp với existing Phase 06 historical credential checker.
- Kiểm tra **version + CLI help thực tế** trước khi chạy; cú pháp scanner có thể thay đổi giữa các releases.
- Scan full Git refs và scan working tree; dùng `--redact` hoặc tính năng tương đương để không ghi plaintext secret.
- False positives được **triage có chứng cứ**; không tạo blanket allowlist để che cả loại secret.
- Khi một hit có vẻ thật, chuyển qua quy trình restricted incident review; không copy-paste token sang issue/AI chat.
- Mục tiêu là phát hiện cả secret cũ lẫn secret đang active, tránh phụ thuộc duy nhất vào GitHub push protection vì độ bao phủ pattern có giới hạn.

### 3.4 Finding schema (safe to commit after sanitization)

```yaml
finding_id: P10-SEC-001
status: OPEN                # OPEN | CONTAINED | REMEDIATED | FALSE_POSITIVE
category: UNKNOWN          # resolved by secure owner review
source_surface: GIT_HISTORY
ref_scope: "branches/tags (redacted detail)"
affected_file_path: "<safe relative path or REDACTED>"
first_seen_commit: "<non-secret SHA if safe>"
credential_value: "<NEVER RECORD>"
owner_role: "repository maintainer"
revoke_or_rotate: PENDING
history_remediation: PENDING
verification: PENDING
notes: "Do not paste raw scanner matches into this file"
```

**Không** hash và công bố giá trị credential nếu không có mục đích bảo mật rõ ràng; không đẩy raw findings lên Git. Chi tiết incident nhạy cảm lưu ngoài repo ở nơi truy cập giới hạn.

### 3.5 Immediate containment rules

1. Nếu thấy secret còn active: **stop sharing and prioritize revoke/rotate** với owner.
2. Tạm ngăn release/merge ảnh hưởng, đóng quyền liên quan khi cần.
3. Đánh giá nơi secret đã được sử dụng; review audit logs phù hợp khả năng truy cập.
4. Không tự dừng/xoá toàn bộ local services hoặc thay key nếu chưa có plan khôi phục.
5. Nếu phát hiện rò rỉ rộng hơn dự kiến, mở incident và điều chỉnh scope trước khi làm tiếp.

### 3.6 P10.1 exit criteria

- [ ] Security inventory đầy đủ theo các surface có quyền truy cập.
- [ ] Every confirmed finding có ID/owner/severity/state (không plaintext secret).
- [ ] Exposure assessment và initial containment documented.
- [ ] Cloud gate tiếp tục BLOCK khi tồn tại confirmed unresolved credential.

---

## 4. Revoke / rotate & runtime recovery — P10.2

### 4.1 Trình tự chuẩn cho từng confirmed credential

1. Xác định service và owner quản lý identity/credential.
2. Xác định nơi credential được tham chiếu; lập kế hoạch cập nhật runtime/local secrets **ngoài Git**.
3. Tạo credential thay thế với scope và TTL/quyền tối thiểu khi cần; ưu tiên secretless identity cho future cloud.
4. Cập nhật secret store/runtime references có kiểm soát; không sửa committed `.env` chứa secret mới.
5. Validate ứng dụng và health checks bằng credential mới.
6. Revoke/disable credential cũ, kiểm tra bằng provider/system audit rằng credential cũ không còn hợp lệ (tránh đưa giá trị cũ vào log).
7. Check alert/monitoring, khả năng rollback runtime bằng credential **mới**, không tái kích hoạt secret lộ.
8. Ghi bằng chứng redacted (owner action ID, timestamp, functional tests), không ghi credential value.

**Ngoại lệ sequencing:** Khi rủi ro active leak cao, revoke ngay trước rồi xử lý outage cần thiết; decision cần được ghi rõ trong incident report.

### 4.2 Service-specific concerns

- **Airflow:** thay Fernet key không đúng procedure có thể mất khả năng giải mã connections; kiểm tra version, migration procedure và backup encrypted metadata phù hợp trước khi rotate.
- **PostgreSQL:** thay connection pool credentials có thể tác động Debezium/Airflow/Spark; smoke đầy đủ từng client.
- **MinIO/S3:** kiểm tra Landing/Bronze/Silver/Gold read/write, multipart/Delta logs, dữ liệu bền vững.
- **Kafka/Debezium:** xác minh CDC connector resume và offset continuity, không reset offsets không cần thiết.
- **Monitoring:** bảo vệ dashboard datasource credentials và log redaction.
- **Azure:** nếu secret bị lộ là Azure credential, cần owner xác thực trạng thái token/account và revoke ở issuer; **không provision cloud trong phase này**.

### 4.3 Runtime acceptance sau rotate

- [ ] Crawler fixture smoke PASS; live test chỉ khi đã có opt-in và chính sách cho phép.
- [ ] Landing/Bronze/Silver/Gold reconciliation PASS trên sample có kiểm soát.
- [ ] Qdrant + DuckDB serve dữ liệu sample đúng, không duplicate ngoài contract.
- [ ] Airflow DAG parse & controlled run PASS.
- [ ] PostgreSQL → Debezium → Kafka metadata CDC smoke PASS nếu bị ảnh hưởng.
- [ ] Prometheus/Grafana collection & alert smoke PASS.
- [ ] Không có leaked value/URL signed credentials trong logs hoặc committed config.

### 4.4 P10.2 exit criteria

**BẮT BUỘC:** confirmed credentials bị lộ đã được revoke/rotated và verified invalid. Nếu owner không thể xác minh: `BLOCKED`, không báo GO.

---

## 5. Git history remediation decision & execution — P10.3

### 5.1 Decision gate: có bắt buộc rewrite không?

**GitHub khuyến cáo ưu tiên revoke/rotate**; rewrite lịch sử có side effects nghiêm trọng: đổi commit SHAs, làm hỏng open PR references, nguy cơ đồng đội re-push commits cũ và tái nhiễm.

Cần quyết định theo finding cụ thể:

| Tình huống | Hướng xử lý |
|---|---|
| Secret active hoặc chưa thể revoke | **NO-GO**; revoke/contain trước |
| Secret revoked, còn historical hit, existing Phase 06 gate vẫn fail | Xác định yêu cầu của gate; chuẩn bị controlled history cleanup hoặc remediation được owner chấp thuận công khai; **không bypass** |
| Có nhiều clones/forks/PRs chứa secret | Coordinate remediation, treat all exposure copies, escalate Git host support nếu cần |
| Confirmed false positive | Ghi rationale và review, configure narrow exception (nếu được phép); không chặn vô hạn |
| Credential thật đã revoke nhưng history cleanup gây ảnh hưởng lớn | Owner quyết định risk acceptance có biện pháp bù; **không auto-mark PASS** nếu gate hiện hữu vẫn BLOCK |

### 5.2 Pre-rewrite authorization (required)

- [ ] Có written approval của repository owner và các collaborator liên quan.
- [ ] Freeze window cho writes/merges/pushes, xác nhận branch protection requirements.
- [ ] Lưu bản sao phục hồi **an toàn, offline, access-restricted**, có retention/deletion policy; bản sao vẫn chứa dữ liệu nhạy cảm.
- [ ] Có mapping old refs/commits → expected new refs và impact lên tags/releases/CI.
- [ ] Có tool/version xác nhận (ví dụ `git-filter-repo`) và rehearsal trên **disposable mirror clone**.
- [ ] Có hướng dẫn collaborators re-clone/rebase, không merge lịch sử ô nhiễm vào repo đã clean.
- [ ] Có kế hoạch xử lý forks, PR refs/cached GitHub views, LFS nếu cần.

### 5.3 Safe operation outline (KHÔNG auto-execute)

```text
Approval & freeze
  -> secure disposable clone
  -> run pinned history-rewrite tool scoped to exact leaked paths/content
  -> scan rewritten local history and all refs
  -> compare repository integrity (tree, contracts, tests, tags)
  -> authorized coordinated remote update ONLY
  -> host/fork/cache remediation if required
  -> contributor re-clone/rebase
  -> scan remote and CI fresh checkout
  -> release history freeze
```

**Không cung cấp lệnh force-push destructive chạy mặc định trong plan**. Coding agent chỉ chuẩn bị phương án, dry-run report và hướng dẫn. Chỉ operator được ủy quyền mới thực hiện remote mutation sau approval.

### 5.4 Verify post-cleanup

- Scan *all relevant refs*: branch, tag, protected refs, PR refs mà host cung cấp, release references, reachable objects.
- Independent fresh clone check tại remote khi được quyền.
- `git fsck`/integrity check và old/new tree diff để phát hiện mất code ngoài dự kiến.
- Re-run Phase 06 historical secret gate, Phase 08/09/P05/P07 relevant regressions.
- Collaborator acknowledgment no tainted clone re-push.
- Host support for cached views/PR refs nếu thực sự cần và có điều kiện.
- Report unresolved remnants (forks/cache/third-party clones) và residual risk; không hứa xóa sạch mọi bản sao ngoài quyền kiểm soát.

### 5.5 Stop conditions

- Scanner vẫn phát hiện credential active, checksum mismatch hoặc mất nội dung ngoài scope.
- Unauthorized/uncoordinated pushes/PR merge.
- Không thể phục hồi ability to build/test.
- Có dấu hiệu lịch sử cũ bị tái nhập.

**P10.3 exit:** owner-approved remediation path được thực thi đầy đủ khi cần; existing gate PASS theo policy hiện hành, hoặc `NO-GO` nếu không thể đạt. Không âm thầm tắt/loại bỏ checker.

---

## 6. Prevent re-exposure & supply-chain hardening — P10.4

### 6.1 Repository hygiene

- [ ] `.gitignore` loại `.env`, runtime secrets, raw HTML, dumps, `.pem`/keys phù hợp, temp artifacts, generated credential files.
- [ ] Có `.env.example`/config example **placeholders only**; không thay sample values bằng credential thật.
- [ ] File permission/secret mounts tối thiểu; exclude from Docker build context bằng `.dockerignore`.
- [ ] Scan new code/commits, PRs và historical refs phù hợp.
- [ ] Implement pre-commit local scan + CI secret scan; kiểm tra hành vi exit nonzero khi phát hiện synthetic sentinel.
- [ ] Push protection/secret scanning trên host nếu plan/account hỗ trợ; không xem là cơ chế bao phủ duy nhất.
- [ ] Suppression allowlist hẹp, documented, reviewed, có expiry nếu cần.

### 6.2 CI/CD guardrail (design)

```text
Pull request / push
    ├── secret-scan changes + repo policy
    ├── dependency audit (triage findings)
    ├── config lint / IaC static checks (if present)
    ├── unit + integration tests
    ├── container/manifest scans (if build enabled)
    └── release gate summary (machine + human-readable)
```

- Không dùng thật token trong unit tests; dùng fixture giả và không giống credential valid.
- Artifact retention và access limits phù hợp; logs redacted.
- CI permissions least privilege; secrets không được expose trên PR không tin cậy.
- Nếu GitHub Actions → Azure được lên kế hoạch trong Phase 11/12: chuẩn bị OIDC/federated identity design, **chưa cần cloud secret/service principal** trong P10.

### 6.3 Dependency & image inventory

- [ ] List pinned Python dependencies, base images, Dockerfiles; note unpinned or EOL components.
- [ ] Dependency vulnerability scan theo ecosystem thực tế, triage theo exploitability/environment.
- [ ] Container image scan & runtime user/root, privileged mode, volume mounts, Docker socket, exposed ports.
- [ ] Docker build validation không bake secrets vào layers, `ARG`/`ENV` hoặc build cache.
- [ ] Pin dependency or image digests khi hợp lý; updates không được gây breaking change không kiểm thử.
- [ ] SBOM (nếu feasible), image digest/version manifest.

### 6.4 Local secrets posture

- [ ] Dev/operator secrets chỉ trong ignored local env/secret store; permissions phù hợp.
- [ ] Không ghi secret lên commandline flags dễ xuất hiện trong process list/history.
- [ ] Runtime logs redaction, Prometheus labels không leak article URLs/tokens.
- [ ] Network services local được hạn chế bind/expose cần thiết, credentials không để default production.
- [ ] Có runbook incident response cho credential leak tái diễn.

### 6.5 P10.4 exit

Deterministic CI/local proof: **safe synthetic negative test bị chặn**, normal harmless fixtures PASS, không có evidence leaks trong artifacts.

---

## 7. Final cloud readiness design review — P10.5

**Chỉ đánh giá thiết kế và chuẩn bị checklist. Không đăng nhập/provision Azure khi chưa được yêu cầu/ủy quyền.** Các ví dụ dưới đây là target design từ handover, không phải services đã tồn tại.

### 7.1 Cloud target inventory

| Component | Local | Target / sequencing | P10 deliverable |
|---|---|---|---|
| Durable object store | MinIO | P11: Azure Storage / ADLS Gen2 | Namespace/data migration plan |
| Data formats | Delta Silver/Gold | Keep Delta semantics | Compatibility checklist |
| Crawler | Docker Compose | P12: AKS workload | Image/identity/env design |
| Airflow + Spark | Local Docker | P12: AKS first; managed later optional | Runtime dependency matrix |
| PostgreSQL | Local Docker | P12: Azure PostgreSQL Flexible Server | Schema + backup/migration plan |
| Debezium/Kafka | Local Docker | P12: AKS first; Event Hubs later optional | CDC continuity plan |
| Qdrant | Local | P12: AKS or future managed | Rebuild/index plan |
| DuckDB | Local derived serving | P12 initial approach TBD | Mount/storage/refresh plan |
| Observability | Prometheus/Grafana | P12 initial AKS, managed optional | Metrics/alerts parity checklist |
| Container registry | Local images | P11/12: ACR | Immutable tag/digest strategy |
| Secret/config mgmt | local ignored config | Key Vault + identity | Secretless design/principle |

### 7.2 ADLS Gen2 readiness (priority because P11 is storage-first)

- [ ] List actual MinIO buckets/prefixes: Landing, Bronze, Silver Delta, Gold, operational exports; validate which stores are **durable truth**.
- [ ] Document object count, total bytes, file size distribution and retention (aggregated, sanitized); do not upload raw sample to plan.
- [ ] Define MinIO → ADLS Gen2 path mapping and reserved/naming rules.
- [ ] Plan Storage Account SKU, **hierarchical namespace (HNS)** and containers/filesystems; note HNS decision is not trivially reversible.
- [ ] Identify actual Spark/Delta/Hadoop versions and ABFS (`abfss://`) connector dependencies; check classpath, auth and compatibility.
- [ ] Verify code not hardcoded S3 endpoint/path semantics; create configuration abstraction plan, **no transformation semantic rewrite**.
- [ ] Define exact Delta transaction log preservation, version/history consistency, checksum/record-count/manifest reconciliation.
- [ ] Plan immutable Landing RAW retention and safe replication/replay semantics.
- [ ] Decide encryption at rest/TLS, data lifecycle, backup, soft delete/versioning where applicable.
- [ ] Prepare staged canary plan: **local Airflow/Spark read/write ADLS** in Phase 11 with tiny authorized dataset; not performed in Phase 10.
- [ ] Document network access and egress, allowlists/private endpoints if appropriate to scope/budget.

**Open design decision:** Spark/Hadoop connector compatibility and Delta transaction-log behavior must be **tested during P11**, not assumed from name similarity of MinIO/S3 and ADLS.

### 7.3 Identity & access matrix

Prefer **Microsoft Entra ID + Managed Identity / AKS Workload Identity**, Azure RBAC minimum scope, Key Vault for secrets that cannot yet be replaced by identity.

| Principal / future workload | Needed operation | Desired least privilege | Notes |
|---|---|---|---|
| P11 local migration operator | Read source + write target canary | Temporary scoped role | Expiry, MFA, audited |
| P11 Spark/ETL identity | Read/write designated ADLS paths | Storage data role at narrow scope | Verify Delta log write support |
| P12 Crawler/Airflow | Read config, write Landing | Workload identities + scoped rights | Isolate each workload |
| P12 analytics/RAG workloads | Read Gold, write derived index | Separate roles by component | Do not grant subscription owner |
| P12 CI deployment | Push images / deploy resources | Federated identity, target-scoped roles | OIDC trust restrictions |
| Operator/monitoring | Logs/metrics, alert actions | Reader/Monitoring roles | No data-plane write by default |

Identity design must include: who creates identities, key/role ownership, audit logging, access review, tenant/subscription scope, separation of admin and runtime operations.

### 7.4 Network / trust boundaries

- [ ] Diagram VNet/subnets/NSGs/private endpoints/east-west connections appropriate to budget.
- [ ] Map crawl **outbound HTTP** policy versus private data-plane access.
- [ ] Decide whether ADLS/PostgreSQL public endpoints are disabled or restricted during incremental transition; plan migration connectivity.
- [ ] TLS termination/cert rotation, DNS, firewall rules, least-exposed ingress.
- [ ] Review Azure region/data residency constraints and external sources' Terms/robots policies.

### 7.5 IaC readiness (no apply)

Proposed convention, adapt to actual repo:

```text
infra/
  terraform/
    modules/
      resource-group/
      storage-adls/
      identities-rbac/
      key-vault/
      monitoring/
    envs/
      thesis-dev/
        main.tf
        variables.tf
        outputs.tf
        terraform.tfvars.example  # placeholders; no credentials
```

**P10 goal:** document modules, naming/tagging conventions, state backend/security, review workflow, version pins, non-secret variable schema, preview/static checks. Creating directories/modules only if user explicitly wants IaC scaffolding now; **no `terraform apply`**.

### 7.6 Cost / quota / permissions readiness

- [ ] Identify Azure subscription & spending authority **without asking for secret values**; mark UNKNOWN if unavailable.
- [ ] Produce service-by-service **cost-estimation worksheet/assumptions**, not fabricated exact prices.
- [ ] Select region rationale, expected GB, requests, egress, compute hours, AKS node sizes (future), log ingestion volumes.
- [ ] Budget/alerts/tagging and teardown ownership; no unexpected resource creation.
- [ ] Record quotas, tenant policies and service availability as **to verify** in actual subscription during P11/12.
- [ ] Define cost hard-stop/approval before enabling paid workloads.

### 7.7 Data privacy / crawling obligations

- [ ] Distinguish publicly accessible article content from unrestricted redistribution rights; respect website Terms, robots and lawful use.
- [ ] Plan retention for live HTML in private object storage (not Git), access control and deletion policy.
- [ ] Avoid uploading live data to unrestricted repositories/logs/issues.
- [ ] Confirm data classification and PII handling where appropriate.

### 7.8 Portability, rollback & benchmark preparation

- [ ] Document env parity matrix (versions, schemas, timezone, Spark configs, batch parameters, source policy).
- [ ] Define canonical data contracts and exact reconciliation queries for MinIO vs ADLS.
- [ ] Plan reversible **configuration switch** for storage backend, while preserving MinIO source as rollback anchor until verified.
- [ ] P11 rollback triggers: checksum mismatch, Delta log inconsistency, access denied, unbounded latency/cost, operational failures.
- [ ] P11 stop/rollback is **storage scope only**; do not concurrently migrate PostgreSQL/Kafka/Qdrant/compute.
- [ ] Preserve Phase 09 measured baseline and reproducible workload for Phase 13 comparison (do not claim benchmark yet).

### 7.9 P10.5 exit

A reviewer can explain **what will move first, which exact risks exist, how identities secure access, how to verify parity and how to stop/roll back** before any Azure resources are created.

---

## 8. Release verification / security gate — P10.6

### 8.1 Required validation layers

**Layer A — Static security:** sanitized secret scans, .gitignore/.dockerignore, repo policy, dependency/container scan, synthetic CI-negative test.

**Layer B — Existing platform functionality:** existing acceptance/smoke tests, registry/config verification, 5-source fixture data, DAG parsing, metadata CDC, Silver/Gold reconciliation, derived serving, monitoring.

**Layer C — Historical secret gate:** re-run **existing Phase 06 cloud readiness check**; inspect exact output/exit status and root cause. Do not modify it merely to produce exit 0.

**Layer D — P09 operations evidence:** last real burn-in results, incidents/S3 HTTP 400 status, backlog/freshness, no unresolved severity-critical blockers.

**Layer E — Cloud migration checklist:** architecture, identity, storage compatibility assumptions, cost/network/rollback/risk owners, signed gate decision.

### 8.2 Suggested targets (not existing until verified/implemented)

```bash
# Existing: confirm definitions and safe prerequisites in Makefile first
make phase8-acceptance
# Make target for Phase 06 should be discovered in repo; name not assumed.

# Proposed P10 targets, adapt to Makefile conventions:
make phase10-preflight
make phase10-security-scan       # scans with redacted outputs
make phase10-acceptance          # deterministic tests + prior gates
make phase10-readiness-report    # compile verified evidence, no provisioning
```

**Do not execute full 24/72h burn-in inside CI**. Consume signed/recorded Phase 09 time-based evidence; if absent, status stays pending.

### 8.3 Reporting statuses (must be separated)

```text
P10-SEC-INCIDENT      REMEDIATED | BLOCKED | IN_PROGRESS
P10-HISTORY-GATE      PASS | FAIL | BLOCKED
P10-CODE-REGRESSION   PASS | FAIL | BLOCKED
P10-P09-DEPENDENCY    VERIFIED | PENDING | FAILED
P10-AZURE-DESIGN      REVIEWED | INCOMPLETE
P10-OVERALL           GO | NO-GO | CONDITIONAL (NOT AUTHORIZED TO MIGRATE)
```

**Only `GO`** with complete evidence and explicit owner sign-off can allow entry to Phase 11. `CONDITIONAL` must not be interpreted as approval to create resources.

---

## 9. Phase 10 acceptance matrix

| ID | Requirement | Validation | Required evidence |
|---|---|---|---|
| A01 | Repo preflight performed; discrepancies recorded | Git/doc/code inspection | Preflight + commit SHA + date |
| A02 | Phase 09 status verified | Acceptance + burn-in report | Actual exit codes and time spans |
| A03 | Known historical credential correctly identified | Redacted scanning, restricted owner review | Sanitized finding ID & surface |
| A04 | Every confirmed exposed credential inactive | Provider/system invalidation & logs | Redacted rotation/revocation proof |
| A05 | No uncontrolled active leak remains | Follow-up scanning across relevant scopes | Sanitized scan summary |
| A06 | Git history remediation path is owner-approved | Decision record + impact review | Approval / exception record |
| A07 | If rewrite, all affected refs/clones addressed | Fresh clone scan + collaborator checklist | Cleanup verification |
| A08 | Existing Phase 06 historical/cloud gate passes | Existing release check | Exact command + exit 0 |
| A09 | Repo hygiene prevents reintroduction | `.gitignore`, `.dockerignore`, local checks | Tests / diff |
| A10 | CI scan fails on **synthetic** leak | Negative test in isolated fixture | Redacted CI log |
| A11 | Dependency/container findings triaged | Inventory + scanner | Risk/decision register |
| A12 | Runtime works with replacement credentials | Platform smoke/reconciliation | Test logs and health check |
| A13 | No regression to Phase 05/07/08/09 behavior | Existing suites | Commands, exit codes |
| A14 | Azure storage/HNS/ABFS/Delta migration risks mapped | Review design & matrix | ADLS compatibility plan |
| A15 | IAM/RBAC/key vault/OIDC strategy reviewed | Threat model / role review | Access matrix |
| A16 | Network, cost, ownership, rollback defined | Checklist review | Signed readiness worksheet |
| A17 | No unintended cloud resources/provisioning | IaC diff/change audit | Resource change log = none |
| A18 | Evidence artifacts sanitized and indexed | Repo artifact review | Evidence index |
| A19 | Go/no-go decision documented and approved | Gate checklist review | Signed decision record |
| A20 | P11 handoff explicit and bounded | Phase 11 readiness review | Entry criteria + migration plan |

### 9.1 Severity and release policy

**Hard NO-GO**, ví dụ:

- Active credential không thể xác minh revoked/rotated.
- History/release security check FAIL và không có quy trình xử lý được phê duyệt.
- Lost data/contract violation từ credential rotation.
- Missing Phase 09 required burn-in (nếu đây là entry gate đã chốt).
- No operator/subscription owner authorization, cost control hoặc rollback plan cho P11.
- Critical unmitigated vulnerability trong deployment path hoặc secrets in logs/images.

**Review-required (not auto GO):** S3 HTTP 400 vẫn unresolved nhưng occurrence + impact có số liệu; host-only cached references; medium vulnerability; missing optional IaC module; network/private endpoint choice.

**Không đặt numerical SLA giả.** Sử dụng evidence thực tế P09 và risk appetite của thesis team để định nghĩa threshold được approval.

---

## 10. Recommended work packages & checkpoints

| Checkpoint | Tasks | Artifact | Gate |
|---|---|---|---|
| CP0 | P10.0 baseline/preflight | Preflight + discrepancy | Scope and owners known |
| CP1 | P10.1 detection/containment | Sanitized inventory + incident | Active leaks contained |
| CP2 | P10.2 rotation + recovery | Provider verification + platform smoke | Exposed secrets invalid |
| CP3 | P10.3 Git history decision/cleanup | Approved playbook + fresh clone scan | Existing history gate verified |
| CP4 | P10.4 preventive guards | CI/pre-commit + dependency/image audit | Synthetic rejection verified |
| CP5 | P10.5 Azure readiness design | Target design + IAM/storage/cost/rollback | No-provision review PASS |
| CP6 | P10.6 final acceptance | Engineering report + GO/NO-GO | Phase 11 entry decision signed |

**Execution advice:** P10.1–P10.3 là critical path; P10.4/P10.5 có thể làm song song khi đã containment, nhưng không để document/IaC work làm mờ việc security gate còn BLOCK.

### 10.1 Suggested delivery slices

- **Slice 1:** preflight, read-only scan, triage — no destructive changes.
- **Slice 2:** replacement credential runtime plan + smoke (secrets owner executes rotations).
- **Slice 3:** approved Git history remediation with collaborators + clean gate.
- **Slice 4:** prevention checks + negative tests + regressions.
- **Slice 5:** cloud design pack (especially Storage/ADLS/ABFS).
- **Slice 6:** final evidence/sign-off; handoff to P11.

---

## 11. Required files / evidence organization

Adjust names to actual repo conventions; **do not commit sensitive scan output**.

```text
docs/agent_tasks/10-security-secret-remediation-final-cloud-readiness.md

docs/agent_tasks/CURRENT_STATUS.md
docs/phase10-security-cloud-readiness-report.md

docs/security/
  secret-handling-policy.md
  incident-response-runbook.md
  git-history-remediation-runbook.md

docs/cloud/
  azure-target-architecture.md
  adls-gen2-migration-preflight.md
  identity-access-matrix.md
  cloud-network-cost-rollback-plan.md
  phase11-entry-checklist.md

artifacts/phase10/
  preflight-summary.md
  discrepancy-register.md
  sanitized-secret-inventory.md
  remediation-decision.md
  security-scan-summary.md
  platform-regression-summary.md
  azure-readiness-assessment.md
  risk-register.md
  evidence-index.md
  go-no-go-decision.md

# RESTRICTED — OUTSIDE REPOSITORY:
# raw scanner results; credential values; sensitive audit logs;
# tainted Git clone backup; unreleased private incident details.
```

### 11.1 Minimum engineering report outline

1. Problem statement + exact initial Phase 06 failure.
2. Verified repo/P09 starting state.
3. Threat model + finding classifications (sanitized).
4. Rotation/revocation proof; runtime recovery.
5. Git history remediation decision, approvals, remote/fork/clone outcomes.
6. Guardrails introduced, CI negative tests and dependency findings.
7. Functional regression evidence, exact commands/exit codes.
8. Azure migration readiness decision matrix and unresolved incompatibilities.
9. Cost/network/IAM/rollback assumptions and reviewers.
10. GO/NO-GO, residual risks, required P11 entry tasks, timestamp + signatures.

### 11.2 Evidence index schema

```markdown
| Evidence ID | Description | Environment/commit | Command or method | Result | Path / approved restricted reference |
|---|---|---|---|---|---|
| EV-P10-001 | Repo preflight | local / <sha> | read-only Git | PASS | artifacts/phase10/preflight-summary.md |
| EV-P10-002 | Secret scan | local / <sha> | approved redacted scanner | PENDING | ... |
| EV-P10-003 | Credential invalidation | issuer/provider | owner-verified | PENDING | restricted reference only |
| EV-P10-004 | Phase 06 gate | local / <sha> | actual Make target | PENDING | ... |
| EV-P10-005 | GO/NO-GO review | team review | sign-off | PENDING | ... |
```

---

## 12. Failure scenarios / safety playbook

| Scenario | Stop/containment | Recovery/decision |
|---|---|---|
| Historical secret still found after cleanup | Stop release, do not suppress without review | Check refs/forks/cache, rotation state, repeat safe scan |
| Credential rotated, crawler cannot access MinIO | Disable affected workload safely, preserve state | Restore with **new** least-privilege credential; validate Landing |
| Debezium fails after DB rotate | Halt dependent CDC changes, capture sanitized logs | Update connector secret refs, check offsets, resume |
| History rewrite breaks collaborator branches | Hold pushes and further remote mutation | Coordinate re-clone/rebase; do not merge tainted history |
| CI scanner false positive | Do not permanently disable scan | Verify harmless fixture, add narrowly scoped exception |
| Secrets found in Docker image/layer | Do not publish/distribute image | Invalidate credential, rebuild clean image, retire affected digest |
| P09 burn-in has data loss or unstable backlog | Set P11 NO-GO | Fix underlying reliability issue, rerun actual verification |
| S3 HTTP 400 recurs | Capture timestamp and storage/Spark evidence | Root-cause analysis, no blind transformation patch |
| Azure design estimate exceeds budget | Stop P11 provisioning | Resize phased target/choose alternative after review |

### 12.1 Disaster avoidance for Git rewriting

A history rewrite is **not** rolled back casually by pushing old refs because it can re-expose secrets. Preserve a protected, restricted recovery artifact only when authorized. Prefer correcting the cleaned history forward and escalating to repository admins instead of reopening compromised refs.

---

## 13. Phase 10 GO / NO-GO decision template

```markdown
# Phase 10 Cloud Readiness Decision

Date (local timezone): <YYYY-MM-DD HH:MM +07:00>
Repo + commit: <branch / SHA>
Reviewers/roles: <names or role IDs>

## Security
- Exposed credentials revoked/rotated: PASS / FAIL / BLOCKED
- History remediation & existing Phase 06 gate: PASS / FAIL / BLOCKED
- CI/push/working-tree controls: PASS / FAIL / BLOCKED
- Remaining sensitive exposure: NONE CONFIRMED / OPEN / UNKNOWN

## Platform
- Phase 09 verified: PASS / FAIL / PENDING
- Regressions/smoke tests: PASS / FAIL / BLOCKED
- Data contracts and serving unchanged: PASS / FAIL

## Cloud readiness
- ADLS/HNS/ABFS compatibility plan: REVIEWED / INCOMPLETE
- Identity/RBAC/key management: REVIEWED / INCOMPLETE
- Networking/cost/quota permissions: REVIEWED / INCOMPLETE
- Backup/rollback/reconciliation plan: REVIEWED / INCOMPLETE

Decision: GO / NO-GO / CONDITIONAL (NOT APPROVED TO MIGRATE)
Reason: <concise evidence-based rationale>
Residual risks: <list IDs + owners + follow-up>
Allowed next action (if GO): Start Phase 11 ADLS storage canary only, subject to budget and authorization.
Approved by: <authorized reviewer>
```

---

## 14. Phase 11 handoff package

When and only when P10 is **GO**, pass to Phase 11:

1. Clean release branch/commit and expected CI security controls.
2. Security remediation closeout and scoped risk acceptance records (sanitized).
3. Inventory of local buckets/prefixes, total data and canonical lineage.
4. Actual Spark/Delta/Hadoop and MinIO versions, storage access abstraction.
5. ADLS target layout, HNS decision, RBAC matrix, region/cost constraints.
6. Trial storage canary spec, checksum/Delta log/reconciliation acceptance.
7. Safe credentials/identities provision plan, no hardcoded keys.
8. Connectivity and rollback/stop playbook.
9. Phase 09 measured baseline for later parity/benchmark comparison.
10. Open issues register with owner, due date, severity and explicit P11 scope boundaries.

### 14.1 P11 first technical objective (NOT done in P10)

```text
Local MinIO Landing/Bronze/Silver/Gold
        |
        | controlled storage canary after authorization
        v
Azure Storage Account (ADLS Gen2)
        |
        +-- local Airflow / Spark can read & write target paths
        +-- Delta format + logs verified
        +-- checksum/count/semantic reconciliation
        +-- config rollback to MinIO verified
```

Do not migrate all services simultaneously. Kafka remains metadata CDC; Qdrant/DuckDB derived rebuild strategy stays intact.

---

## 15. Copy-paste AI coding-agent execution prompt

> Implement **Phase 10 — Security / Secret Remediation Gate & Final Cloud Readiness** for the financial-news repository using this document. First read `AGENTS.md`, data contracts, `CURRENT_STATUS.md`, Phase 06/08/09 tasks, Phase 08 and Phase 09 engineering reports and **inspect actual repo code/tests before modifying anything**. Phase 09 burn-in and Phase 08 Git integration are NOT automatically assumed complete; report discrepancies.
>
> Prioritize the historical credential issue: carry out **read-only, redacted** discovery and produce a finding/impact inventory **without disclosing secret values**. Do not paste raw credentials into stdout, commit messages, artifacts, or chat. Prepare a credential rotation/revocation plan for the authorized owner; do not silently change accounts or live secrets. For Git history, perform threat/risk assessment and a rehearsal plan, but **do not rewrite remote history, force-push, delete refs or merge changes without explicit approval and collaborator coordination**.
>
> Implement repository/CI security guardrails, using synthetic negative tests, and reuse the existing Phase 06 release gate rather than bypassing it. Run relevant existing acceptance/regression tests and record exact commands, exit codes and sanitized results. Keep architecture and canonical contracts unchanged; no new Kafka article queue, no Azure provisioning, no data migration. Preserve local configuration and operations.
>
> Produce the Phase 10 evidence bundle, readines­s design for Azure Storage/ADLS Gen2 and identity/network/cost/rollback, and issue an evidence-based **GO / NO-GO**. Mark blocked tests, unauthorized actions and unexecuted scans `PENDING` or `BLOCKED`, never fake PASS. Update `CURRENT_STATUS.md`, `docs/phase10-security-cloud-readiness-report.md` and associated runbooks only with verified facts. Execute work in CP0→CP6 checkpoints; after each report files changed, actual tests/results, decisions requiring human approval, and remaining blockers.

---

## 16. Official reference links (design guidance; external, not repo evidence)

- GitHub, *Removing sensitive data from a repository*: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- GitHub, *Secret scanning detection scope*: https://docs.github.com/en/code-security/reference/secret-security/secret-scanning-scope
- GitHub, *Managing security and analysis settings*: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-security-and-analysis-settings-for-your-repository
- Microsoft, *Azure Storage security recommendations*: https://learn.microsoft.com/en-us/azure/storage/common/secure-storage
- Microsoft, *ADLS Gen2 hierarchical namespace*: https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-namespace
- Microsoft, *Authorize blob access with Microsoft Entra ID*: https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory
- Microsoft, *AKS Workload Identity*: https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
- Microsoft, *Azure Well-Architected Framework*: https://learn.microsoft.com/en-us/azure/well-architected/what-is-well-architected-framework

**Phân biệt nguồn:** Các thông tin về 5 nguồn, Phase 08, Phase 06 blocker, thứ tự roadmap là từ **handover**. Workflow và checklists security/cloud trong plan là **đề xuất kỹ thuật cho Phase 10**, không phải code/test cloud đã tồn tại hoặc được hoàn thành.

---

## 17. Final continuation rule

**Không** tuyên bố `CLOUD READY` nếu chưa xác thực credentials đã bị vô hiệu hóa, gate bảo mật lịch sử sạch theo policy hiện tại, Phase 09 có đủ evidence đã chốt, regressions hoạt động và P11 có kế hoạch storage-only được phê duyệt. Mỗi `PASS` cần có command/test/report và thời gian thực; mỗi mục chưa làm phải `PENDING`/`BLOCKED`.
