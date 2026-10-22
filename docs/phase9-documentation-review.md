# Rà soát tài liệu sau Phase09

Ngày rà soát: **22/10/2026**. Checkout bắt đầu tại `8bd1f7e`, sau merge Phase09
trong repository. Đây là cập nhật tài liệu dựa trên source và evidence đã có;
không chạy crawler, khởi động stack, bật lịch hay thực thi lại acceptance.

Trạng thái hiện tại: **functional verification PASS** theo tám checkpoint giữ
từ full-run cộng focused scheduling recheck sau sửa rollback. **B1 live, B2 24h,
B3 72h PENDING**; Phase09 chưa DONE. Cloud vẫn **NOT READY FOR CLOUD MIGRATION**.
Các log thất bại và provenance được giữ trong
[Phase09 engineering report](phase9-engineering-report.md).

## 1. Những tài liệu và claim đã cập nhật

| Nhóm tài liệu | Nội dung cũ hoặc dễ hiểu sai | Nội dung hiện hành |
|---|---|---|
| [README](../README.md), [mục lục](DOCUMENTATION_GUIDE.md), [CURRENT_STATUS](agent_tasks/CURRENT_STATUS.md) | Điểm đọc/demo và inventory chủ yếu đến Phase07/08; branch implementation có thể bị hiểu là checkout hiện tại | Điều hướng qua Phase09, phân biệt lịch sử implementation với checkout; functional PASS và các gate còn pending |
| [Kiến trúc local](local-architecture.md), [kiến trúc crawler](crawling-architecture.md) | Một số sơ đồ đặt Analytics sau enrichment; batch theo lịch được mô tả cố định một bài | Analytics đọc Silver trực tiếp; env default một bài nhưng effective limit còn chịu source cap; runtime policy là gate riêng |
| [Airflow](airflow-local.md), [pipeline operations](pipeline-operations.md), [ADR](decisions.md) | Opt-in schedule chưa giải thích đủ source policy, replay và đường fetch lỗi | Manual mặc định fixture; publish `all_done`; automatic replay có cap/due/budget/backoff, source lock và reclaim; manual override có giới hạn |
| [Demo guide](demo-guide-vi.md), `docs/present-demo/BAO_CAO_TIEN_DO_VA_DEMO.md` | Kịch bản thiên về Phase07/08, thiếu điều kiện live sau Phase09 | Điểm bắt đầu/demo vận hành mới; bảy dashboard provisioned/19 rules; historical live evidence tách fixture và denied scheduler drill |
| [Baseline monitoring](local-monitoring-baseline.md), [release guide](local-release.md), [checklist](local-release-checklist.md) | Các kết quả Phase06/07 có thể bị đọc như lần kiểm chứng mới nhất | Giữ nguyên số đo và dấu checked lịch sử, dẫn đến runbook/report hiện hành; không suy ra SLO, release hoặc cloud readiness |
| [Data contracts](data-contracts.md), [nguồn tin](news-sources.md) | Snapshot/proposal và quan sát website cũ dễ bị hiểu thành inventory/runtime schema hiện tại | Giữ profile gốc; chỉ rõ năm adapters và schema thực tế; operational migration không mở rộng canonical contract; không crawl website lại |
| [Cloud plan](cloud-migration-plan.md), [manifest](cloud-migration-manifest.md) | Thiếu state/policy mới; từng mô tả không có env batch-limit | Mang theo block latch, attempts/eligibility, policy và migration 0003; env limit có nhưng không vượt source policy; cloud vẫn Future Work |
| [Phase08 report](phase8-engineering-report.md), [thesis alignment](THESIS_ALIGNMENT.md), [Phase09 report](phase9-engineering-report.md) | Báo cáo checkpoint cũ thiếu liên kết đến vận hành mới | Giữ kết quả gốc, bổ sung boundary và điều hướng; không đổi 7/15 lịch sử thành 7/19 cho lần chạy cũ |
| `docs/thesis/` | Analysis/evidence/outline/report/diagrams/future work/reproduction trước Phase09 | Bổ sung E41–E46, H10, source policy/replay/reporting, provenance functional và N5 thực nghiệm live/burn-in còn pending |

Các tài liệu `monitoring-observability.md` và `crawler-operations.md` đã có phần
Phase09 từ lượt implementation; được dùng làm nguồn đối chiếu, không viết lại
chỉ để tạo diff. Specifications `agent_tasks/01–09` và
`docs/thesis/THESIS_WRITING_PLAN.md` giữ nguyên yêu cầu gốc.

## 2. Đối chiếu implementation và giới hạn

| Claim | Source/evidence đối chiếu | Kết luận |
|---|---|---|
| Schedule và manual có điều kiện khác nhau | `airflow/dags/news_crawling_pipeline.py`, `src/crawling/airflow_jobs.py` | Schedule từ env lúc parse; manual fixture/allow-live mặc định true/false; source policy đọc lúc task chạy |
| Giới hạn crawl và replay | `src/crawling/policy.py`, `jobs.py`, `state.py` | Crawl min(requested, source cap); default publisher hai batches/năm attempts; manual replay có bounded override |
| State mới không phải article CDC | `operations/migrations/0003_continuous_crawling.up.sql`, `metadata/` | Thêm SKIPPED/SCHEDULED, block latch, RUNNING/attempt/due state; CDC vẫn chỉ hai bảng control metadata |
| Metrics/reporting không đo chất lượng truy xuất | `src/monitoring/crawler_metrics.py`, `src/crawling/reporting.py` | Heartbeat/Landing/layer riêng; latency theo batch/stage, p95 N/A dưới 20 samples; thiếu dữ liệu lịch sử không tự điền zero |
| Dashboard/rules là cấu hình provisioned | `monitoring/grafana/provisioning/dashboards/json/`, `monitoring/prometheus/rules/financial-news.yml` | Bảy dashboard, 19 rules; dashboard cũ tồn tại thêm trong volume không thay đổi inventory repository |
| Functional PASS không phải burn-in | `artifacts/phase9/acceptance.json`, `scheduler-smoke.json`, `burnin-24h.md`, `burnin-72h.md` | Full-run có lỗi teardown phát hiện sau đó; focused recheck thay checkpoint bị ảnh hưởng; B1/24h/72h vẫn pending |
| Analytics và enrichment | `src/news_pipeline/analytics.py`, `enrichment.py`, `gold_rag.py` | Analytics đọc Silver; NoOp trả entities null/status unavailable, stock symbols từ source associations; typed events/ViFinNER là Future Work |

Việc claim/reclaim ở source lock không làm toàn pipeline có exactly-once hoặc
cross-store atomic commit. Không thêm benchmark, số liệu performance, evaluation
RAG, chức năng cloud hay tuyên bố website còn truy cập được ở ngày rà soát.

## 3. Phân biệt lịch sử và bằng chứng mới

- Phase07: sáu dashboard/12 rules và các timing/resource samples là lịch sử.
- Phase08 ngày 03/10: bảy dashboard/15 rules; tiny live smoke năm bài và 39
  chunks/points. Không diễn giải thành live volume ngày 22/10 hoặc collection dài hạn.
- Phase09: evidence ghi 54 selected tests, 10 metrics tests, regressions và
  focused scheduler recheck. Hai cycle cuối là source-live-disabled, request 0;
  không thay B1 live. Lượt rà soát tài liệu không chạy lại các tests này.
- `artifacts/phase9/` là ignored runtime evidence; một fresh clone có thể thiếu
  JSON/log/session. Khi thiếu phải dùng engineering report như báo cáo lịch sử,
  không gọi đó là bằng chứng máy đọc vừa kiểm chứng lại.

## 4. Kiểm tra tài liệu

| Kiểm tra thực sự chạy trong lượt tài liệu | Kết quả | Giới hạn |
|---|---|---|
| Python stdlib kiểm tra Markdown local | PASS: 30 file được rà soát, 441 local links, 37 linked headings, 208 fenced blocks cân bằng | Gồm 28 file cập nhật và hai runbook đã có Phase09; không render Mermaid/PDF |
| Đối chiếu JSON dashboards, YAML rules và Python DAG AST | PASS: bảy dashboard, 19 rules, crawler UID `news-crawler` có 14 panels, bốn DAG | Kiểm cấu hình repository, không query service runtime |
| Outline/report/evidence | PASS: 53 sections khớp outline, sáu chương, 18 bảng, 11 caption hình không trùng, E01–E46 liên tục | Kiểm cấu trúc và tham chiếu; nội dung kỹ thuật được đối chiếu source riêng |
| Đọc acceptance JSON và log đã lưu | PASS: chín checkpoint exit 0; provenance giữ tám checks, metrics/unit logs ghi 54 và 10 tests; overall/burn-in PENDING | Không thực thi lại tests; không biến báo cáo lịch sử thành runtime proof mới |
| `PYTHONDONTWRITEBYTECODE=1 python3 tools/generate_data_contracts.py --check` | Exit 0; không source schema drift, không volume changes, mapping được hỗ trợ | Read-only; không regenerate profile/contract; không phải Silver integration test |
| So sánh generated observed block với HEAD | Byte-identical | Preamble phân biệt snapshot/proposal/runtime là phần sửa tay ngoài generated block |
| `git diff --check` và phạm vi diff | PASS; thay đổi trong README/Markdown dưới docs | Không kiểm runtime hoặc stage các file ignored |

Các kiểm tra này xác minh tính nhất quán của tài liệu và source/artifact;
không thay thế runtime acceptance. Lượt này không sửa source/config, không
chạy suite runtime, không bật live/schedule và không thực hiện thao tác Git ghi.

## 5. Tài liệu local đang bị Git ignore

`.gitignore` hiện có patterns `thesis` và `present-demo`. Vì vậy bảy artifact
được cập nhật trong `docs/thesis/` và báo cáo trong `docs/present-demo/` tồn tại
local nhưng không xuất hiện trong `git diff` thông thường. Không thay ignore
rules hoặc stage các file trong nhiệm vụ này; trạng thái này cần được biết khi
người dùng chuẩn bị commit tài liệu. Không commit/push/merge/rebase/deploy.
