# =============================================================================
# Helper Makefile for the ViFinNER RAG stack.
# Works with both Docker Compose v2 (`docker compose`) and GNU make.
# =============================================================================

COMPOSE ?= docker compose

.PHONY: help up down logs build rebuild ps \
        scrape ingest ask deploy lint \
        frontend-dev frontend-build data-contracts data-contracts-check \
        infra-up bronze-ingest silver-build test-pipeline \
        gold-build analytics-build analytics-query qdrant-index semantic-search retrieval-smoke test-gold serving-up \
        airflow-build airflow-init airflow-up airflow-down airflow-logs airflow-dags \
        airflow-test airflow-test-silver airflow-test-gold pipeline-run \
        metadata-infra-up metadata-up metadata-down metadata-migrate metadata-migrate-down \
        metadata-seed metadata-db-status kafka-topics debezium-register debezium-status \
        metadata-consume metadata-cdc-test test-metadata \
        hardening-build operations-migrate operations-status pipeline-services-up \
        pipeline-incremental pipeline-backfill pipeline-reprocess pipeline-resume \
        pipeline-status pipeline-reconcile pipeline-health qdrant-rebuild analytics-rebuild \
        test-hardening test-recovery test-idempotency test-incremental test-backfill phase5-test \
        release-prerequisites release-config-check release-runtime-check release-audit bootstrap local-stop \
        reset-derived local-reset-destructive test-release e2e-local ci-test \
        phase6-health phase6-report phase6-acceptance

help:
	@echo "Available targets:"
	@echo "  make up          - Start the full ViFinNER stack."
	@echo "  make down        - Stop and remove containers."
	@echo "  make build       - Build all Docker images."
	@echo "  make rebuild     - Rebuild images without cache."
	@echo "  make ps          - Show container statuses."
	@echo "  make logs        - Tail logs for every service."
	@echo "  make scrape      - Run a CafeF scrape once (host Python)."
	@echo "  make ingest      - Run the ingestion pipeline once (host Python)."
	@echo "  make ask Q='...' - Ask the chatbot a question."
	@echo "  make deploy      - Register Prefect deployments inside the worker."
	@echo "  make data-contracts       - Regenerate observed data profile and contract sections."
	@echo "  make data-contracts-check - Report source schema drift without writing files."
	@echo "  make infra-up            - Start local MinIO."
	@echo "  make bronze-ingest       - Upload the selected sample snapshot."
	@echo "  make silver-build        - Build Silver Delta tables with PySpark."
	@echo "  make test-pipeline       - Run unit and sample integration tests."
	@echo "  make gold-build          - Build durable Gold documents and chunks."
	@echo "  make analytics-build     - Build Gold analytics and local DuckDB."
	@echo "  make qdrant-index INDEX_LIMIT=0 - Embed and index Gold chunks."
	@echo "  make semantic-search QUERY='...' - Retrieve top chunks without an LLM."
	@echo "  make analytics-query QUERY='SELECT ...' - Query local DuckDB."
	@echo "  make retrieval-smoke     - Evaluate documented sample queries."
	@echo "  make test-gold           - Run Phase 02 unit and integration tests."
	@echo "  make airflow-up          - Initialize and start local Airflow on port 8088."
	@echo "  make airflow-down        - Stop local Airflow services (keep volumes)."
	@echo "  make airflow-logs        - Follow scheduler and webserver logs."
	@echo "  make airflow-dags        - List DAGs and import errors."
	@echo "  make airflow-test        - Run DAG import and structure tests."
	@echo "  make airflow-test-silver - Test Silver DAG; waits for triggered Gold DAG."
	@echo "  make airflow-test-gold   - Test the Gold DAG directly."
	@echo "  make pipeline-run        - Run the Airflow end-to-end local smoke path."
	@echo "  make metadata-up         - Start and configure the local metadata CDC control plane."
	@echo "  make metadata-down       - Stop metadata PostgreSQL, Kafka, and Debezium."
	@echo "  make metadata-migrate    - Apply control-plane PostgreSQL migrations."
	@echo "  make metadata-migrate-down - Revert the latest control-plane migration."
	@echo "  make metadata-seed       - Upsert deterministic CafeF development metadata."
	@echo "  make metadata-db-status  - Inspect WAL, publication, and replication slot."
	@echo "  make kafka-topics        - Ensure and list compacted metadata CDC topics."
	@echo "  make debezium-register   - Register/update the PostgreSQL Debezium connector."
	@echo "  make debezium-status     - Show connector and task status."
	@echo "  make metadata-consume    - Inspect bounded metadata CDC event summaries."
	@echo "  make metadata-cdc-test   - Run CDC lifecycle plus Connect/Kafka/PostgreSQL recovery tests."
	@echo "  make test-metadata       - Run Phase 04 unit tests."
	@echo "  make pipeline-incremental PROCESSING_DATE=YYYY-MM-DD - Process one logical partition."
	@echo "  make pipeline-backfill FROM_DATE=... TO_DATE=... - Backfill explicit fixture partitions."
	@echo "  make pipeline-reprocess PROCESSING_DATE=... - Explicitly reprocess one partition."
	@echo "  make pipeline-resume RUN_ID=... - Resume a failed run from its first failed stage."
	@echo "  make pipeline-status     - Show run history, checkpoint, and active locks."
	@echo "  make pipeline-reconcile  - Compare Silver, Gold, Qdrant, and DuckDB."
	@echo "  make pipeline-health     - Concise health check for local services and outputs."
	@echo "  make qdrant-rebuild      - Explicit full rebuild of the current Qdrant projection."
	@echo "  make analytics-rebuild   - Rebuild current Gold analytics and atomically refresh DuckDB."
	@echo "  make test-hardening      - Run Phase 05 unit and local integration tests."
	@echo "  make phase5-test         - Run all Phase 05 validation targets."
	@echo "  make bootstrap           - Idempotently initialize the Phase 01-06 local platform."
	@echo "  make local-stop          - Stop local release services without deleting volumes."
	@echo "  make reset-derived       - Delete only configured Qdrant and DuckDB serving state."
	@echo "  make local-reset-destructive CONFIRM=DELETE_LOCAL_RELEASE_DATA - Delete release data."
	@echo "  make e2e-local           - Run isolated Bronze-to-serving and rebuild acceptance."
	@echo "  make ci-test             - Run the CI-friendly contract/unit/DAG test selection."
	@echo "  make phase6-acceptance   - Run the final local release gate and write its report."

SPARK_PACKAGES = io.delta:delta-spark_2.12:3.2.1,org.apache.hadoop:hadoop-aws:3.3.4
SPARK_SUBMIT = /opt/spark/bin/spark-submit --packages $(SPARK_PACKAGES) --conf spark.jars.ivy=/opt/news-ivy
INDEX_LIMIT ?= 0
export NEWS_SEARCH_QUERY = $(QUERY)
export NEWS_ANALYTICS_SQL = $(QUERY)

infra-up:
	$(COMPOSE) up -d minio

bronze-ingest: infra-up
	$(COMPOSE) run --rm news-pipeline python3 -m src.news_pipeline.bronze

silver-build: infra-up
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/silver.py

test-pipeline: infra-up
	$(COMPOSE) run --rm news-pipeline python3 -m unittest discover -s tests -p 'test_news_pipeline_unit.py' -v
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/tests/test_news_pipeline_integration.py

serving-up: infra-up
	$(COMPOSE) up -d qdrant

gold-build: infra-up
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/gold_rag.py

analytics-build: infra-up
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/analytics.py
	$(COMPOSE) run --rm --user 0 news-pipeline python3 -m src.news_pipeline.duckdb_serving build

analytics-query:
	$(COMPOSE) run --rm -e NEWS_ANALYTICS_SQL news-pipeline python3 -m src.news_pipeline.duckdb_serving query

qdrant-index: serving-up
	$(COMPOSE) run --rm -e NEWS_INDEX_LIMIT=$(INDEX_LIMIT) news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/qdrant_index.py

semantic-search: serving-up
	$(COMPOSE) run --rm -e NEWS_SEARCH_QUERY news-pipeline python3 -m src.news_pipeline.semantic_search

retrieval-smoke: serving-up
	$(COMPOSE) run --rm --user 0 news-pipeline python3 -m src.news_pipeline.retrieval_smoke
	cp data/local/gold-retrieval-smoke-results.json artifacts/gold-retrieval-smoke-results.json

test-gold: serving-up
	$(COMPOSE) run --rm news-pipeline python3 -m unittest discover -s tests -p 'test_news_gold_unit.py' -v
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/tests/test_news_gold_spark_unit.py
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/tests/test_news_gold_integration.py

airflow-build:
	$(COMPOSE) build airflow-init

airflow-init: airflow-build
	$(COMPOSE) up airflow-init

airflow-up: serving-up airflow-init
	$(COMPOSE) up -d airflow-scheduler airflow-webserver

airflow-down:
	$(COMPOSE) stop airflow-scheduler airflow-webserver airflow-postgres

airflow-logs:
	$(COMPOSE) logs -f --tail=200 airflow-scheduler airflow-webserver

airflow-dags: airflow-init
	$(COMPOSE) run --rm airflow-cli airflow dags list
	$(COMPOSE) run --rm airflow-cli airflow dags list-import-errors

airflow-test: airflow-init
	$(COMPOSE) run --rm airflow-cli python3 -m unittest tests.test_airflow_dags -v
	$(COMPOSE) run --rm airflow-cli airflow dags list-import-errors

airflow-test-silver: airflow-up
	$(COMPOSE) run --rm airflow-cli python3 /app/tools/airflow_smoke.py news_silver_pipeline

airflow-test-gold: airflow-up
	$(COMPOSE) run --rm airflow-cli python3 /app/tools/airflow_smoke.py news_gold_pipeline

pipeline-run: airflow-test-silver

metadata-infra-up:
	$(COMPOSE) up -d postgresql kafka

metadata-migrate: metadata-infra-up
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.migrations up
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.database provision

metadata-migrate-down: metadata-infra-up
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.migrations down

metadata-seed: metadata-migrate
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.seed

kafka-topics: metadata-infra-up
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.topics ensure
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.topics list

debezium-register: metadata-seed kafka-topics
	$(COMPOSE) up -d debezium
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.connector register
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.connector wait

metadata-up: debezium-register

metadata-down:
	$(COMPOSE) stop debezium kafka postgresql

metadata-db-status: metadata-up
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.database inspect

debezium-status: metadata-up
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.connector status

metadata-consume: metadata-up
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.consumer --from-beginning

test-metadata:
	python3 -m unittest tests.test_metadata_control -v

metadata-cdc-test: metadata-up test-metadata
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.smoke --mode lifecycle --output /app/artifacts/metadata-cdc-smoke.json
	$(COMPOSE) restart debezium
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.connector wait
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.smoke --mode recovery --output /app/artifacts/metadata-cdc-recovery.json
	$(COMPOSE) stop kafka
	$(COMPOSE) run --rm --no-deps metadata-tools python3 -m src.metadata_control.kafka_outage write --output /app/artifacts/metadata-cdc-kafka-recovery.json
	$(COMPOSE) up -d --wait kafka
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.connector wait --timeout 180
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.kafka_outage verify --output /app/artifacts/metadata-cdc-kafka-recovery.json
	$(COMPOSE) restart postgresql
	$(COMPOSE) up -d --wait postgresql
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.connector wait --timeout 180
	$(COMPOSE) run --rm metadata-tools python3 -m src.metadata_control.smoke --mode postgres-recovery --output /app/artifacts/metadata-cdc-postgres-recovery.json


# Phase 05: hardened incremental batch pipeline.
DATE ?=
FROM ?=
TO ?=
PROCESSING_DATE ?= $(if $(DATE),$(DATE),$(shell date +%F))
FROM_DATE ?= $(FROM)
TO_DATE ?= $(TO)
PARTITION_DIR ?= /app/data/partitions
PARTITION_PATTERN ?= {date}.json
SOURCE_FILE ?= /app/data/raw/cafef_news_raw_final.json
RUN_ID ?=

hardening-build:
	$(COMPOSE) build news-pipeline metadata-tools airflow-init

operations-migrate:
	$(COMPOSE) up -d postgresql
	$(COMPOSE) run --rm --no-deps metadata-tools python3 -m src.pipeline_operations.migrations up

operations-status: operations-migrate
	$(COMPOSE) run --rm --no-deps metadata-tools python3 -m src.pipeline_operations.migrations status

pipeline-services-up: serving-up operations-migrate

pipeline-incremental: pipeline-services-up
	$(COMPOSE) run --rm --user 0 -e NEWS_SOURCE_FILE=$(SOURCE_FILE) -e NEWS_PROCESSING_DATE=$(PROCESSING_DATE) news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/pipeline_runner.py incremental --date $(PROCESSING_DATE) --source-file $(SOURCE_FILE) $(if $(RUN_ID),--run-id $(RUN_ID),)

pipeline-backfill: pipeline-services-up
	@test -n "$(FROM_DATE)" -a -n "$(TO_DATE)" || (echo "Usage: make pipeline-backfill FROM_DATE=YYYY-MM-DD TO_DATE=YYYY-MM-DD PARTITION_DIR=/app/data/partitions"; exit 2)
	$(COMPOSE) run --rm --user 0 news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/pipeline_runner.py backfill --from-date $(FROM_DATE) --to-date $(TO_DATE) --partition-dir $(PARTITION_DIR) --file-pattern '$(PARTITION_PATTERN)' $(if $(RUN_ID),--run-id $(RUN_ID),)

pipeline-reprocess: pipeline-services-up
	$(COMPOSE) run --rm --user 0 -e NEWS_SOURCE_FILE=$(SOURCE_FILE) -e NEWS_PROCESSING_DATE=$(PROCESSING_DATE) news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/pipeline_runner.py reprocess --date $(PROCESSING_DATE) --source-file $(SOURCE_FILE) --force-reprocess $(if $(RUN_ID),--run-id $(RUN_ID),)

pipeline-resume: pipeline-services-up
	@test -n "$(RUN_ID)" || (echo "Usage: make pipeline-resume RUN_ID=<failed-run-id>"; exit 2)
	$(COMPOSE) run --rm --user 0 news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/pipeline_runner.py resume --run-id $(RUN_ID)

pipeline-status: operations-migrate
	$(COMPOSE) run --rm --no-deps news-pipeline python3 -m src.pipeline_operations.cli status

pipeline-reconcile: pipeline-services-up
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/reconciliation.py --run-id $${RUN_ID:-manual-$$(date +%s)}

qdrant-rebuild: serving-up
	$(COMPOSE) run --rm -e NEWS_INDEX_LIMIT=$(INDEX_LIMIT) news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/qdrant_rebuild.py

analytics-rebuild: infra-up
	$(COMPOSE) run --rm --user 0 news-pipeline $(SPARK_SUBMIT) /app/src/news_pipeline/analytics_rebuild.py

pipeline-health:
	$(COMPOSE) run --rm --no-deps news-pipeline python3 -m src.news_pipeline.health --compact

test-hardening: pipeline-services-up
	$(COMPOSE) run --rm --no-deps news-pipeline python3 -m unittest tests.test_pipeline_hardening -v
	$(COMPOSE) run --rm --user 0 news-pipeline $(SPARK_SUBMIT) /app/tests/test_pipeline_hardening_integration.py
	cp data/local/phase5-integration-results.json artifacts/phase5-integration-results.json


test-recovery: pipeline-services-up
	$(COMPOSE) run --rm --user 0 news-pipeline python3 /app/tests/test_pipeline_runner_recovery.py
	cp data/local/phase5-recovery-results.json artifacts/phase5-recovery-results.json

test-idempotency: test-hardening

test-incremental: test-hardening

test-backfill: test-recovery

phase5-test: data-contracts-check test-hardening test-recovery airflow-test

# Phase 06: reproducible local release and cloud-readiness gate.
release-prerequisites:
	python3 tools/local_release.py prerequisites

release-config-check:
	python3 tools/local_release.py validate-profile config/environments/local.env.example
	python3 tools/local_release.py validate-profile config/environments/test.env
	python3 tools/local_release.py validate-profile config/environments/future-cloud.env.example
	$(COMPOSE) config --quiet

release-runtime-check:
	python3 tools/local_release.py validate-runtime

release-audit:
	python3 tools/local_release.py audit

bootstrap: release-prerequisites release-config-check release-runtime-check hardening-build
	mkdir -p data/local artifacts
	$(COMPOSE) up -d --wait minio qdrant postgresql kafka
	$(COMPOSE) run --rm news-pipeline python3 -m src.news_pipeline.release bootstrap-storage
	$(COMPOSE) run --rm --no-deps metadata-tools python3 -m src.pipeline_operations.migrations up
	$(MAKE) metadata-up
	$(COMPOSE) up airflow-init
	$(COMPOSE) up -d --wait airflow-scheduler airflow-webserver
	python3 tools/local_release.py bootstrap-status

local-stop:
	$(COMPOSE) stop airflow-webserver airflow-scheduler debezium kafka postgresql qdrant minio airflow-postgres

reset-derived: serving-up
	$(COMPOSE) run --rm --user 0 news-pipeline python3 -m src.news_pipeline.release reset-derived

local-reset-destructive:
	python3 tools/local_release.py destructive-reset --confirm '$(CONFIRM)'

test-release:
	$(COMPOSE) run --rm --no-deps news-pipeline python3 -m unittest tests.test_local_release_unit -v

e2e-local: serving-up
	$(COMPOSE) run --rm --user 0 news-pipeline $(SPARK_SUBMIT) /app/tests/test_local_release_e2e.py
	cp data/local/local-release-e2e.json artifacts/local-release-e2e.json

ci-test: data-contracts-check infra-up
	$(COMPOSE) run --rm --no-deps news-pipeline python3 -m unittest \
		tests.test_news_pipeline_unit tests.test_news_gold_unit tests.test_pipeline_hardening \
		tests.test_local_release_unit -v
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/tests/test_news_pipeline_integration.py
	$(COMPOSE) run --rm news-pipeline $(SPARK_SUBMIT) /app/tests/test_news_gold_spark_unit.py
	$(MAKE) test-metadata
	$(MAKE) airflow-test
	python3 tools/local_release.py mark ci

phase6-health:
	$(COMPOSE) run --rm --no-deps \
		-e NEWS_SOURCE=local-release.test \
		-e NEWS_PROCESSING_VERSION=local-rc1-acceptance \
		-e NEWS_EMBEDDING_MODEL=local-release-token-hash-v1 \
		-e NEWS_EMBEDDING_DIMENSION=32 \
		-e NEWS_QDRANT_COLLECTION=local_release_acceptance_v1 \
		-e NEWS_DUCKDB_PATH=/app/local/local-release-acceptance.duckdb \
		news-pipeline python3 -m src.news_pipeline.health --compact

phase6-report:
	python3 tools/local_release.py report

phase6-acceptance: release-config-check release-audit ci-test e2e-local test-recovery metadata-cdc-test phase6-health
	$(MAKE) phase6-report

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

rebuild:
	$(COMPOSE) build --no-cache

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200

scrape:
	python scripts/run_scrape_once.py

ingest:
	python scripts/run_ingest_once.py

medallion:
	python scripts/run_medallion_once.py

eval:
	python scripts/run_eval.py

ingest-langchain:
	python scripts/run_langchain_ingest.py

ask:
	@if [ -z "$$Q" ]; then echo "Usage: make ask Q='your question'"; exit 1; fi
	python scripts/ask.py "$$Q"

ask-langchain:
	@if [ -z "$$Q" ]; then echo "Usage: make ask-langchain Q='your question'"; exit 1; fi
	python scripts/ask_langchain.py "$$Q"

deploy:
	$(COMPOSE) exec prefect-worker python -m src.rag.flows.deploy

frontend-dev:
	cd frontend && npm install && npm run dev

frontend-build:
	cd frontend && npm install && npm run build

data-contracts:
	python3 tools/generate_data_contracts.py

data-contracts-check:
	python3 tools/generate_data_contracts.py --check
