"""Idempotently seed metadata for the checked-in CafeF sample pipeline."""

from __future__ import annotations

import json

from .config import MetadataSettings
from .database import connect


def seed(settings: MetadataSettings) -> dict:
    source = {
        "source_id": "cafef.vn",
        "source_name": "CafeF sample snapshot",
        "source_type": "snapshot",
        "base_url": "https://cafef.vn",
        "description": "Checked-in CafeF news snapshot used by the local financial-news pipeline.",
        "config": {"input_path": "data/raw/cafef_news_raw_final.json"},
    }
    pipeline = {
        "config_id": "financial-news-local-v1",
        "pipeline_name": "financial-news-medallion",
        "source_id": source["source_id"],
        "config_version": 1,
        "parameters": {
            "processing_version": "cafef-v1.1",
            "chunk_size": 900,
            "chunk_overlap": 120,
            "processing_mode": "local-snapshot",
        },
    }
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO control_metadata.news_sources
                    (source_id, source_name, source_type, enabled, base_url, description, config)
                VALUES (%s, %s, %s, true, %s, %s, %s::jsonb)
                ON CONFLICT (source_id) DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    source_type = EXCLUDED.source_type,
                    base_url = EXCLUDED.base_url,
                    description = EXCLUDED.description,
                    config = EXCLUDED.config
                WHERE (news_sources.source_name, news_sources.source_type, news_sources.base_url,
                       news_sources.description, news_sources.config)
                    IS DISTINCT FROM
                      (EXCLUDED.source_name, EXCLUDED.source_type, EXCLUDED.base_url,
                       EXCLUDED.description, EXCLUDED.config)
                """,
                (
                    source["source_id"], source["source_name"], source["source_type"],
                    source["base_url"], source["description"], json.dumps(source["config"]),
                ),
            )
            cursor.execute(
                """
                INSERT INTO control_metadata.pipeline_configs
                    (config_id, pipeline_name, source_id, enabled, config_version, parameters)
                VALUES (%s, %s, %s, true, %s, %s::jsonb)
                ON CONFLICT (config_id) DO UPDATE SET
                    pipeline_name = EXCLUDED.pipeline_name,
                    source_id = EXCLUDED.source_id,
                    config_version = EXCLUDED.config_version,
                    parameters = EXCLUDED.parameters
                WHERE (pipeline_configs.pipeline_name, pipeline_configs.source_id,
                       pipeline_configs.config_version, pipeline_configs.parameters)
                    IS DISTINCT FROM
                      (EXCLUDED.pipeline_name, EXCLUDED.source_id,
                       EXCLUDED.config_version, EXCLUDED.parameters)
                """,
                (
                    pipeline["config_id"], pipeline["pipeline_name"], pipeline["source_id"],
                    pipeline["config_version"], json.dumps(pipeline["parameters"]),
                ),
            )
    result = {"news_source": source["source_id"], "pipeline_config": pipeline["config_id"]}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    seed(MetadataSettings.from_env())
