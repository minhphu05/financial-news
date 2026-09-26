FROM python:3.12-slim

RUN pip install --no-cache-dir \
    confluent-kafka==2.8.2 \
    psycopg[binary]==3.2.6

WORKDIR /app

CMD ["python3", "-m", "src.metadata_control.consumer", "--help"]
