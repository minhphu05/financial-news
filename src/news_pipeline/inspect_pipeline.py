"""Inspect Bronze objects, Silver Delta tables, and processing metrics."""

from pathlib import Path
import sys

from src.news_pipeline.bronze import file_sha256
from src.news_pipeline.config import Settings
from src.news_pipeline.storage import create_object_store


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("bronze", "silver", "metrics"):
        raise SystemExit("Usage: inspect_pipeline.py bronze|silver|metrics")
    settings = Settings.from_env()
    store = create_object_store(settings)
    ingestion_id = file_sha256(Path(settings.source_file))
    prefix = f"silver/{settings.source}/{ingestion_id}/{settings.processing_version}"
    if sys.argv[1] == "bronze":
        print("\n".join(store.list_keys(f"bronze/{settings.source}/{ingestion_id}/")))
        print(store.get_bytes(f"bronze/{settings.source}/{ingestion_id}/manifest.json").decode())
    elif sys.argv[1] == "metrics":
        print(store.get_bytes(f"{prefix}/metrics.json").decode())
    else:
        from src.news_pipeline.silver import create_spark

        spark = create_spark(settings)
        try:
            for table in ("articles", "article_mentions", "rejects"):
                frame = spark.read.format("delta").load(settings.object_uri(f"{prefix}/{table}"))
                print(f"{table}: {frame.count()} rows; columns={frame.columns}")
                frame.show(2, truncate=80)
        finally:
            spark.stop()


if __name__ == "__main__":
    main()
