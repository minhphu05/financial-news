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
        airflow-test airflow-test-silver airflow-test-gold pipeline-run

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
