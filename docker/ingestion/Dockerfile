# Image used by the Prefect worker that runs both scrape_flow and ingest_flow
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip install --upgrade pip  \
    && pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts

# Default command: register Prefect deployments. The compose file overrides
# this with a "prefect worker start" invocation for the worker service.
CMD ["python", "-m", "src.rag.flows.deploy"]
