"""Rebuild current Gold analytics and atomically refresh DuckDB."""

import json

from src.news_pipeline.analytics import build
from src.news_pipeline.duckdb_serving import publish
from src.news_pipeline.gold_config import GoldSettings
from src.news_pipeline.silver import create_spark
from src.news_pipeline.storage import S3ObjectStore


def main() -> None:
    settings = GoldSettings.from_env().for_current_tables()
    store = S3ObjectStore(settings.news)
    spark = create_spark(settings.news)
    try:
        analytics = build(settings, spark, store)
    finally:
        spark.stop()
    duckdb = publish(settings, store)
    print(json.dumps({"analytics": analytics, "duckdb": duckdb}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
