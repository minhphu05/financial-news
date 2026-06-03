# Image for the FastAPI chatbot service.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY docker/api/requirements-api.txt requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "src.rag.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
