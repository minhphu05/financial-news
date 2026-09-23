"""Airflow DAG import, structure, configuration, and thin-orchestration tests."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from airflow.models import DagBag


DAG_FOLDER = Path("/opt/airflow/dags")
if str(DAG_FOLDER) not in sys.path:
    sys.path.insert(0, str(DAG_FOLDER))

from news_pipeline_common import required_runtime_config  # noqa: E402


class AirflowDagTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bag = DagBag(dag_folder=str(DAG_FOLDER), include_examples=False)

    def test_all_dags_import_without_errors(self):
        self.assertEqual(self.bag.import_errors, {})
        self.assertIn("news_silver_pipeline", self.bag.dags)
        self.assertIn("news_gold_pipeline", self.bag.dags)

    def test_silver_dag_structure_and_gold_trigger(self):
        dag = self.bag.get_dag("news_silver_pipeline")
        expected = {
            "start", "validate_source_data", "bronze_ingest", "bronze_quality_check",
            "spark_bronze_to_silver", "silver_quality_check", "publish_silver_success",
            "trigger_gold_pipeline",
        }
        self.assertEqual(set(dag.task_ids), expected)
        chain = [
            "start", "validate_source_data", "bronze_ingest", "bronze_quality_check",
            "spark_bronze_to_silver", "silver_quality_check", "publish_silver_success",
            "trigger_gold_pipeline",
        ]
        for upstream, downstream in zip(chain, chain[1:]):
            self.assertIn(downstream, dag.get_task(upstream).downstream_task_ids)
        trigger = dag.get_task("trigger_gold_pipeline")
        self.assertEqual(trigger.trigger_dag_id, "news_gold_pipeline")
        self.assertTrue(trigger.wait_for_completion)
        self.assertFalse(dag.catchup)
        self.assertIsNone(dag.schedule_interval)

    def test_gold_parallel_branches_and_join(self):
        dag = self.bag.get_dag("news_gold_pipeline")
        expected = {
            "validate_silver", "build_gold_rag_chunks", "embed_and_index_qdrant",
            "rag_quality_check", "build_gold_analytics", "publish_duckdb",
            "analytics_quality_check", "publish_gold_success",
        }
        self.assertEqual(set(dag.task_ids), expected)
        self.assertEqual(
            dag.get_task("validate_silver").downstream_task_ids,
            {"build_gold_rag_chunks", "build_gold_analytics"},
        )
        self.assertIn("embed_and_index_qdrant", dag.get_task("build_gold_rag_chunks").downstream_task_ids)
        self.assertIn("rag_quality_check", dag.get_task("embed_and_index_qdrant").downstream_task_ids)
        self.assertIn("publish_duckdb", dag.get_task("build_gold_analytics").downstream_task_ids)
        self.assertIn("analytics_quality_check", dag.get_task("publish_duckdb").downstream_task_ids)
        final = dag.get_task("publish_gold_success")
        self.assertEqual(final.upstream_task_ids, {"rag_quality_check", "analytics_quality_check"})
        self.assertFalse(dag.catchup)
        self.assertIsNone(dag.schedule_interval)

    def test_commands_call_existing_entrypoints_and_disable_large_xcom(self):
        silver = self.bag.get_dag("news_silver_pipeline")
        gold = self.bag.get_dag("news_gold_pipeline")
        self.assertIn("src.news_pipeline.bronze", silver.get_task("bronze_ingest").bash_command)
        self.assertIn("/app/src/news_pipeline/silver.py", silver.get_task("spark_bronze_to_silver").bash_command)
        self.assertIn("/app/src/news_pipeline/gold_rag.py", gold.get_task("build_gold_rag_chunks").bash_command)
        self.assertIn("/app/src/news_pipeline/qdrant_index.py", gold.get_task("embed_and_index_qdrant").bash_command)
        self.assertIn("/app/src/news_pipeline/analytics.py", gold.get_task("build_gold_analytics").bash_command)
        for dag in (silver, gold):
            for task in dag.tasks:
                if hasattr(task, "bash_command"):
                    self.assertFalse(task.do_xcom_push)

    def test_missing_required_configuration_fails_clearly(self):
        required = ("NEWS_STORAGE_ENDPOINT", "NEWS_STORAGE_BUCKET", "NEWS_SOURCE_FILE", "NEWS_QDRANT_URL")
        with patch.dict(os.environ, {name: "" for name in required}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "Missing required pipeline configuration"):
                required_runtime_config()

    def test_dag_files_do_not_contain_transformation_implementations(self):
        forbidden = ("pyspark", "SparkSession", "normalize_observation", "ArticleChunker", "TextEmbedding")
        for filename in ("news_silver_pipeline.py", "news_gold_pipeline.py"):
            source = (DAG_FOLDER / filename).read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
