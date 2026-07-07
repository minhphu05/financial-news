# Image used by the Prefect runner that registers and serves local deployments.
FROM prefecthq/prefect:3-latest

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --upgrade pip  \
    && pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install --with-deps chromium

COPY src ./src
COPY scripts ./scripts

# Default command: register Prefect deployments.
CMD ["python", "-m", "src.flows.deploy"]
