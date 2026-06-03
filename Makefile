# =============================================================================
# Helper Makefile for the ViFinNER RAG stack.
# Works with both Docker Compose v2 (`docker compose`) and GNU make.
# =============================================================================

COMPOSE ?= docker compose

.PHONY: help up down logs build rebuild ps \
        scrape ingest ask deploy lint \
        frontend-dev frontend-build

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
