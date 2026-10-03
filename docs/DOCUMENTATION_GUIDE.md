# Hướng dẫn đọc tài liệu dự án

**Điểm bắt đầu:** dùng tài liệu này để chọn tài liệu cần đọc, không cần đọc hết
repository theo thứ tự file. Đối chiếu danh mục ngày **03/10/2026**, sau Phase08
local multisource crawling. Đây là mục lục và hướng dẫn; không thay thế contracts,
runbooks hay bằng chứng kiểm chứng của từng phase.

## 1. Đọc lần đầu theo thứ tự nào?

1. [README](../README.md): dự án làm gì, kiến trúc tổng thể, lệnh cơ bản.
2. [CURRENT_STATUS](agent_tasks/CURRENT_STATUS.md): phase đã hoàn thành, bằng chứng
   thực chạy và blocker còn tồn tại.
3. [Local architecture](local-architecture.md): data plane, control plane,
   orchestration, monitoring; phần local và target cloud.
4. [News sources](news-sources.md): 5 báo, chuyên mục, cơ chế crawl và phạm vi đã chứng minh.
5. [Data contracts](data-contracts.md): input/canonical Silver/Gold, identity và quality rules.
6. Chọn runbook theo công việc ở bảng dưới.

Checkpoint hiện tại: Phase01–08 đã có implementation local; crawl thật mới có
bằng chứng tiny smoke 1 bài/nguồn. Schedule live mặc định tắt. Cloud deployment
chưa thực hiện và release gate vẫn `NOT READY FOR CLOUD MIGRATION` vì vấn đề
credential lịch sử. Xem CURRENT_STATUS để lấy kết quả và trạng thái mới nhất.

## 2. Tôi cần làm gì thì đọc tài liệu nào?

| Nhu cầu | Đọc đầu tiên | Đọc tiếp |
|---|---|---|
| Nắm tình hình để tiếp tục project | [CURRENT_STATUS](agent_tasks/CURRENT_STATUS.md) | [README](../README.md), [local architecture](local-architecture.md) |
| Biết đã crawl báo nào, lấy bài như thế nào | [news-sources.md](news-sources.md) | [source mappings](source-mapping-matrix.md), source contract tương ứng |
| Chạy crawler, schedule mỗi ngày, kiểm tra incremental | [crawler-operations.md](crawler-operations.md) | [crawler architecture](crawling-architecture.md), [pipeline operations](pipeline-operations.md) |
| Khởi động môi trường local sạch | [local-release.md](local-release.md) | [README](../README.md), [release checklist](local-release-checklist.md) |
| Tìm schema, field mapping hoặc quy tắc dedup | [data-contracts.md](data-contracts.md) | [source mappings](source-mapping-matrix.md), [metadata events](metadata-event-contracts.md) |
| Chạy/tìm lỗi Bronze → Silver | [bronze-silver-local.md](bronze-silver-local.md) | [data contracts](data-contracts.md), [pipeline operations](pipeline-operations.md) |
| Chạy/tìm lỗi Gold, Qdrant, DuckDB | [silver-gold-local.md](silver-gold-local.md) | [pipeline operations](pipeline-operations.md), [local release](local-release.md) |
| Resume batch lỗi, backfill, reconciliation | [pipeline-operations.md](pipeline-operations.md) | [crawler operations](crawler-operations.md) nếu input là crawl |
| Hiểu DAG hoặc kiểm tra lịch Airflow | [airflow-local.md](airflow-local.md) | [crawler operations](crawler-operations.md) cho DAG crawl |
| Kiểm tra PostgreSQL → Debezium → Kafka | [metadata-control-plane.md](metadata-control-plane.md) | [metadata-event-contracts.md](metadata-event-contracts.md) |
| Xem dashboard, metrics, alerts hoặc service lỗi | [monitoring-observability.md](monitoring-observability.md) | [local baseline](local-monitoring-baseline.md) |
| Demo với giảng viên | [demo-guide-vi.md](demo-guide-vi.md) | [news sources](news-sources.md), [Phase08 report](phase8-engineering-report.md) |
| Báo cáo tiến độ và demo Phase08 theo lời thoại | [present-demo/BAO_CAO_TIEN_DO_VA_DEMO.md](present-demo/BAO_CAO_TIEN_DO_VA_DEMO.md) | [CURRENT_STATUS](agent_tasks/CURRENT_STATUS.md), [Phase08 live E2E](../artifacts/phase8-live-e2e.json) |
| Vẽ sơ đồ pipeline hiện tại | [local-architecture.md](local-architecture.md) | [crawling-architecture.md](crawling-architecture.md), [monitoring](monitoring-observability.md) |
| Chuẩn bị lên cloud | [cloud-migration-plan.md](cloud-migration-plan.md) | [migration manifest](cloud-migration-manifest.md), [credential remediation](credential-remediation.md), [release checklist](local-release-checklist.md) |
| Hiểu lý do chọn công nghệ/giới hạn | [decisions.md](decisions.md) | [local architecture](local-architecture.md) |
| Đối chiếu đồ án với đề cương | [THESIS_ALIGNMENT.md](THESIS_ALIGNMENT.md) | [CURRENT_STATUS](agent_tasks/CURRENT_STATUS.md), docs ViFinNER |

## 3. Vai trò của từng tài liệu đang dùng

### Tổng quan, trạng thái và hợp đồng

| Tài liệu | Nội dung và lúc nên đọc |
|---|---|
| [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md) | Mục lục này; tìm điểm bắt đầu và phân biệt tài liệu hiện hành với lịch sử. |
| [README.md](../README.md) | Tổng quan, cấu trúc repository, setup, commands và giới hạn; bắt đầu khi mới vào dự án. |
| [AGENTS.md](../AGENTS.md) | Quy tắc làm việc cho coding agent; phải đọc trước khi sửa repo. Crawler từng ngoài scope, Phase08 đã được yêu cầu riêng. |
| [agent_tasks/CURRENT_STATUS.md](agent_tasks/CURRENT_STATUS.md) | Checkpoint tổng hợp, kết quả kiểm chứng, blocker; đọc trước khi tiếp tục phase hoặc báo cáo completion. |
| [local-architecture.md](local-architecture.md) | Kiến trúc local đã triển khai, sơ đồ data/control/operations và target cloud; dùng để hiểu/vẽ pipeline. |
| [data-contracts.md](data-contracts.md) | Approved schemas, identity/hash/dedup, timestamp, quality và enrichment boundary; đọc trước khi đổi transformation/schema. |
| [decisions.md](decisions.md) | ADR về durable lake, serving derived, Airflow, metadata Kafka và crawler integration; đọc khi cân nhắc kiến trúc. |
| [THESIS_ALIGNMENT.md](THESIS_ALIGNMENT.md) | Đối chiếu đề cương với các nhánh dự án; có bản rà soát lịch sử và checkpoint bổ sung, không coi toàn bộ đồ án đã hoàn thành. |

### Data plane và crawler

| Tài liệu | Nội dung và lúc nên đọc |
|---|---|
| [bronze-silver-local.md](bronze-silver-local.md) | Commands ingest sample, Spark cleaning, Delta Silver và cách inspect output Phase01. |
| [silver-gold-local.md](silver-gold-local.md) | Chunking/enrichment hook, embeddings/Qdrant, analytics/DuckDB, commands và quality gates Phase02. |
| [pipeline-operations.md](pipeline-operations.md) | Hardened runner, incremental/backfill/reprocess/resume, locks/checkpoints/reconciliation và xử lý lỗi Phase05. |
| [news-sources.md](news-sources.md) | Nguồn đã crawl, nguồn gốc lựa chọn, chuyên mục, kỹ thuật, selectors, số liệu live smoke và real/fixture distinction. |
| [crawling-architecture.md](crawling-architecture.md) | Ranh giới crawler/Landing/adapter/pipeline, state và cách tích hợp lại jobs cũ. |
| [crawler-operations.md](crawler-operations.md) | Khởi tạo, CLI, source config, HTTP policy, schedule hằng ngày, incremental/recheck, backfill và recovery. |
| [source-mapping-matrix.md](source-mapping-matrix.md) | So sánh raw schema từng nguồn và mapping vào approved input/Silver; dùng khi đổi parser/adapter. |
| [source-contracts/cafef.md](source-contracts/cafef.md) | Raw fields, selector, timestamp, schema/parser và quan sát của CafeF. |
| [source-contracts/vnexpress.md](source-contracts/vnexpress.md) | Raw fields, selector, `pubdate` và quan sát của VnExpress. |
| [source-contracts/tuoitre.md](source-contracts/tuoitre.md) | Raw fields, selector, timestamp và quan sát của Tuổi Trẻ. |
| [source-contracts/thanhnien.md](source-contracts/thanhnien.md) | Raw fields, selector, timestamp và quan sát của Thanh Niên. |
| [source-contracts/baomoi.md](source-contracts/baomoi.md) | Raw fields/selector và attribution của Báo Mới; không dedup giữa nguồn ở crawler. |
| [phase8-engineering-report.md](phase8-engineering-report.md) | Báo cáo triển khai, actual tests/live evidence, regression, fixes và giới hạn ở checkpoint Phase08. |

### Orchestration, metadata, monitoring và demo

| Tài liệu | Nội dung và lúc nên đọc |
|---|---|
| [airflow-local.md](airflow-local.md) | DAGs, dependencies/retries, UI, smoke/import tests; có mục riêng cho crawler Phase08. |
| [metadata-control-plane.md](metadata-control-plane.md) | Schema/migrations control metadata, publication/slot, Connect/Kafka và CDC lifecycle/recovery Phase04. |
| [metadata-event-contracts.md](metadata-event-contracts.md) | Envelope CDC, topics, keys, snapshot/update/delete/tombstone và consumer behavior. |
| [monitoring-observability.md](monitoring-observability.md) | Metrics sources, exporter, 7 dashboards/15 rules, setup và troubleshooting Phase07/08. |
| [local-monitoring-baseline.md](local-monitoring-baseline.md) | Resource/timing/failure observations ở baseline Phase07; dùng để so sánh, không xem như benchmark cloud. |
| [demo-guide-vi.md](demo-guide-vi.md) | Hướng dẫn tiếng Việt để demo services/data/SQL/retrieval/failure và crawler; phần đầu giữ baseline Phase07, phần cuối có demo Phase08. |
| [present-demo/BAO_CAO_TIEN_DO_VA_DEMO.md](present-demo/BAO_CAO_TIEN_DO_VA_DEMO.md) | Lời thoại báo cáo tiến độ Phase01–08, demo fixture/live evidence, fallback, Q&A và dẫn chứng tới source docs/artifacts. |

### Release, bảo mật và cloud

| Tài liệu | Nội dung và lúc nên đọc |
|---|---|
| [local-release.md](local-release.md) | Clean bootstrap, profiles, reset/rebuild, acceptance và baseline local release Phase06. |
| [local-release-checklist.md](local-release-checklist.md) | Release gates, bằng chứng cần đạt và cách hiểu READY/NOT READY. |
| [credential-remediation.md](credential-remediation.md) | Các loại credential lộ trong lịch sử, rotation/revocation, diễn tập và quy trình history remediation; không chứa giá trị secret. |
| [cloud-migration-plan.md](cloud-migration-plan.md) | Local → cloud mapping, ADLS/Kubernetes readiness và thứ tự migration tương lai; không phải cloud đã triển khai. |
| [cloud-migration-manifest.md](cloud-migration-manifest.md) | Theo từng component: data/config/code impact, validation/rollback; có Landing và crawler frontier/outbox cutover. |

## 4. Tài liệu giao việc theo phase

Các file trong `agent_tasks` là **yêu cầu triển khai/Definition of Done**, không
phải bằng chứng đã hoàn thành. Khi resume, đối chiếu task với CURRENT_STATUS,
code, tests và artifacts; không rebuild completed work chỉ vì task viết ở thì tương lai.

| File | Phạm vi |
|---|---|
| [01_bronze_silver_local.md](agent_tasks/01_bronze_silver_local.md) | Sample → Bronze → Spark Silver. Tên file thật có underscores. |
| [02-silver-gold-local.md](agent_tasks/02-silver-gold-local.md) | Silver → Gold RAG/Analytics → Qdrant/DuckDB. |
| [03-airflow-orchestration-local.md](agent_tasks/03-airflow-orchestration-local.md) | Thin Airflow orchestration cho standalone jobs. |
| [04-metadata-cdc-local.md](agent_tasks/04-metadata-cdc-local.md) | PostgreSQL metadata WAL → Debezium → Kafka; không phải stock streaming. |
| [05-pipeline-hardening-local.md](agent_tasks/05-pipeline-hardening-local.md) | Incremental/idempotency, state, recovery và reconciliation. |
| [06-local-release-cloud-readiness.md](agent_tasks/06-local-release-cloud-readiness.md) | Local release/clean bootstrap/rebuildability và readiness; không provision cloud. |
| [07-monitoring-observability-local.md](agent_tasks/07-monitoring-observability-local.md) | Monitoring/dashboard/alert/failure verification; các khuyến nghị cloud ở task là lịch sử. |
| [08-multisource-crawling-ingestion-local.md](agent_tasks/08-multisource-crawling-ingestion-local.md) | 5 nguồn, discovery/parser/adapter, Landing, incremental và tích hợp pipeline. Phase08 hiện là crawling local. |

## 5. Tài liệu lịch sử hoặc thuộc application cũ

Những file này vẫn có giá trị tra cứu, nhưng không phải runbook/checkpoint của
data pipeline hiện tại. Không nhầm MongoDB/Prefect/legacy scraper với đường
Landing → Bronze → Spark/Delta → Gold.

| File | Mô tả | Tài liệu hiện tại nên ưu tiên |
|---|---|---|
| [repo-audit.md](repo-audit.md) | Audit ngày 20/09 trước khi build medallion. | CURRENT_STATUS, local-architecture |
| [implementation-plan.md](implementation-plan.md) | Plan local-batch ban đầu; milestone numbers không phải agent phase numbers. | CURRENT_STATUS, agent_tasks đúng phase |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Hiện trạng historical ở commit ngày 20/09. | CURRENT_STATUS |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Legacy scraper/application architecture. | local-architecture, crawling-architecture |
| [SCRAPER.md](SCRAPER.md) | `src/scraper`, keyword/VN30, PostgreSQL/Mongo. | news-sources, crawler-operations |
| [INCREMENTAL_SCRAPING.md](INCREMENTAL_SCRAPING.md) | Cursor theo keyword của scraper cũ. | crawler-operations, pipeline-operations |
| [RUNBOOK.md](RUNBOOK.md) | Commands vận hành application/scraper cũ. | local-release, crawler-operations |
| [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md) | Setup application stack cũ. | README, local-release, `.env.example` |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | Tables/collections của legacy PostgreSQL/Mongo application; không phải toàn bộ schemas Phase04/05/08. | metadata-control-plane, pipeline-operations, crawler-operations và SQL migrations |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Legacy Loki/Fluent Bit logging stack. | monitoring-observability |
| [ENV_GUIDE.md](../ENV_GUIDE.md) | Root environment guide cho RAG/application cũ. | `.env.example`, local-release |
| [QUICK_REFERENCE.md](../QUICK_REFERENCE.md) | Root commands/environment reference của application; có lệnh start toàn stack. | README, Makefile commands cho subset cần dùng |
| [INSTRUCTION.md](../INSTRUCTION.md) | Root commands chạy `src.scraper.run` theo ticker. | crawler-operations cho Phase08 |
| [docker/prefect/theory.md](../docker/prefect/theory.md) | Ghi chú Prefect của hướng orchestration cũ. | airflow-local |

## 6. Tài liệu nghiên cứu và tài liệu kèm module

| File | Khi nào đọc |
|---|---|
| [src/model/docs/README_VI.md](../src/model/docs/README_VI.md) | Tổng quan nhánh ViFinNER bằng tiếng Việt; khi làm NER/enrichment model. |
| [src/model/docs/README_EN.md](../src/model/docs/README_EN.md) | Tổng quan nhánh nghiên cứu bằng tiếng Anh. |
| [src/model/docs/RESEARCH_GAPS_VI.md](../src/model/docs/RESEARCH_GAPS_VI.md) | Phân tích khoảng trống nghiên cứu; dùng cho luận văn/thực nghiệm NER. |
| [src/model/docs/RESEARCH_GAPS_EN.md](../src/model/docs/RESEARCH_GAPS_EN.md) | Bản tiếng Anh của nghiên cứu gaps. |
| [frontend/README.md](../frontend/README.md) | Setup React/Vite application; frontend không thuộc Phase08 crawler release. |
| [tests/automation/README.md](../tests/automation/README.md) | Selenium/Playwright UI tests; không phải bằng chứng runtime crawler dùng browser. |
| [tests/fixtures/crawling/README.md](../tests/fixtures/crawling/README.md) | Provenance/nội dung tổng hợp của HTML fixtures, cách phân biệt với bài thật. |
| [monitoring/exporters/README.md](../monitoring/exporters/README.md) | Entrypoint, read-only access và cardinality rules của metrics exporter; xem runbook chính cho inventory Phase08. |

## 7. Khi cần xác minh bằng chứng thay vì đọc mô tả

| Cần xác minh | Nơi đọc |
|---|---|
| Dữ liệu sample và schema thực tế | [artifacts/data-profile.json](../artifacts/data-profile.json), [data contracts](data-contracts.md) |
| HTTP/parser/layout từng nguồn | `artifacts/source-profiles/*.json`; links từng nguồn trong [news-sources](news-sources.md) |
| Số bài crawl thật và kết quả downstream | [phase8-live-smoke.json](../artifacts/phase8-live-smoke.json), [phase8-live-e2e.json](../artifacts/phase8-live-e2e.json) |
| Acceptance/regression Phase08 | [phase8-acceptance.json](../artifacts/phase8-acceptance.json), [phase8-regression.json](../artifacts/phase8-regression.json), [engineering report](phase8-engineering-report.md) |
| SQL schema hiện hành | [metadata migrations](../metadata/migrations), [operations migrations](../operations/migrations) |
| Runtime selectors/source URL | [src/crawling/sources.py](../src/crawling/sources.py), source config PostgreSQL |
| Commands/config thực chạy | [Makefile](../Makefile), [.env.example](../.env.example), [docker-compose.yml](../docker-compose.yml), jobs và DAGs |

Nếu tài liệu và code/bằng chứng có vẻ mâu thuẫn: kiểm tra ngày, phạm vi
snapshot/live/fixture và phase; đối chiếu implementation. Approved data
contracts vẫn là ràng buộc: nếu code vi phạm contract, báo mismatch và xin quyết
định thiết kế, không âm thầm sửa contract để khớp code.

Khi thêm/đổi tên tài liệu, cập nhật mục lục này và README. Khi thay đổi behavior,
cập nhật runbook/contract liên quan và CURRENT_STATUS kèm kết quả kiểm chứng thật.
