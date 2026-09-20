FROM apache/spark:3.5.3-java17-python3

USER root
RUN python3 -m pip install --no-cache-dir \
        boto3==1.35.99 \
        duckdb==1.4.1 \
        fastembed==0.8.0 \
        qdrant-client==1.13.1 \
    && mkdir -p /opt/news-ivy /opt/news-models \
    && chown 185:185 /opt/news-ivy /opt/news-models
WORKDIR /app
ENV PYTHONPATH=/app
USER 185
