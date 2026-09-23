FROM apache/spark:3.5.3-java17-python3 AS spark-runtime

FROM apache/airflow:2.11.2-python3.10

USER root
COPY --from=spark-runtime /opt/java/openjdk /opt/java/openjdk
COPY --from=spark-runtime /opt/spark /opt/spark
RUN mkdir -p /app /opt/news-ivy /opt/news-models /opt/airflow/local \
    && chown -R airflow:0 /app /opt/news-ivy /opt/news-models /opt/airflow/local \
    && chmod -R g+rwX /app /opt/news-ivy /opt/news-models /opt/airflow/local

ENV JAVA_HOME=/opt/java/openjdk \
    SPARK_HOME=/opt/spark \
    PATH=/opt/spark/bin:/opt/java/openjdk/bin:${PATH} \
    PYTHONPATH=/app

USER airflow
RUN python3 -m pip install --no-cache-dir \
        apache-airflow==2.11.2 \
        'chardet<6' \
        duckdb==1.4.1 \
        fastembed==0.8.0 \
        qdrant-client==1.13.1

WORKDIR /app
