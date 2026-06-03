# ==================================================================================================================
# MLFlow tracking server with SQLite backend + local artifact store.
# Mount a volume at /mlflow/store to persist runs across container restarts.
# ==================================================================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install "mlflow==3.10.*"

WORKDIR /mlflow
RUN mkdir -p /mlflow/store /mlflow/artifacts

EXPOSE 5000

CMD ["mlflow", "server", \
     "--host", "0.0.0.0", \
     "--port", "5000", \
     "--backend-store-uri", "sqlite:////mlflow/store/mlflow.db", \
     "--default-artifact-root", "/mlflow/artifacts"]
