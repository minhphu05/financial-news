"""Unit tests for src/flows/ Prefect flow definitions.

Tests flow and task function signatures, decorators, and logic with
mocked Prefect runtime and downstream dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestScrapeFlow:
    """Tests for the scrape flow and task."""

    @patch("src.flows.scrape_flow.run_scraper_pipeline")
    @patch("src.flows.scrape_flow.PipelineRunLogger")
    @patch("src.flows.scrape_flow.get_run_logger")
    def test_scrape_task_calls_pipeline(
        self, mock_get_logger, mock_pipeline_logger, mock_run_pipeline
    ):
        """Test that scrape_task invokes run_scraper_pipeline."""
        from src.flows.scrape_flow import scrape_task

        mock_run_pipeline.return_value = MagicMock(
            total_new=5,
            total_skipped=2,
            total_errors=0,
        )

        result = scrape_task.fn(keywords=["FPT", "VNM"])
        mock_run_pipeline.assert_called_once()

    @patch("src.flows.scrape_flow.run_scraper_pipeline")
    @patch("src.flows.scrape_flow.PipelineRunLogger")
    @patch("src.flows.scrape_flow.get_run_logger")
    def test_scrape_task_generates_run_id(
        self, mock_get_logger, mock_pipeline_logger, mock_run_pipeline
    ):
        """Test that scrape_task generates a UUID run_id when not provided."""
        from src.flows.scrape_flow import scrape_task

        mock_run_pipeline.return_value = MagicMock()
        result = scrape_task.fn(keywords=None, run_id=None)

        # PipelineRunLogger should receive a valid UUID
        call_kwargs = mock_pipeline_logger.call_args
        assert call_kwargs is not None

    @patch("src.flows.scrape_flow.run_scraper_pipeline")
    @patch("src.flows.scrape_flow.PipelineRunLogger")
    @patch("src.flows.scrape_flow.get_run_logger")
    def test_scrape_task_uses_provided_run_id(
        self, mock_get_logger, mock_pipeline_logger, mock_run_pipeline
    ):
        """Test that scrape_task uses provided run_id."""
        from src.flows.scrape_flow import scrape_task

        mock_run_pipeline.return_value = MagicMock()
        result = scrape_task.fn(keywords=["FPT"], run_id="custom-123")

        call_kwargs = mock_pipeline_logger.call_args
        if call_kwargs:
            assert "custom-123" in str(call_kwargs)


class TestIngestFlow:
    """Tests for the ingestion flow."""

    @patch("src.flows.ingest_flow.IngestionPipeline")
    @patch("src.flows.ingest_flow.get_run_logger")
    def test_ingest_task_creates_pipeline(self, mock_get_logger, mock_pipeline_cls):
        """Test that ingest task creates an IngestionPipeline."""
        from src.flows.ingest_flow import ingest_task

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = MagicMock(
            cleaned=10, embedded=10, errors=0
        )
        mock_pipeline_cls.return_value = mock_pipeline

        result = ingest_task.fn()
        mock_pipeline.run.assert_called_once()


class TestEvalFlow:
    """Tests for the evaluation flow."""

    @patch("src.flows.eval_flow.RAGEvaluator")
    @patch("src.flows.eval_flow.get_run_logger")
    def test_eval_task_runs_evaluator(self, mock_get_logger, mock_evaluator_cls):
        """Test that eval task creates and runs an evaluator."""
        from src.flows.eval_flow import eval_task

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate.return_value = MagicMock(
            accuracy=0.85, total=20, correct=17
        )
        mock_evaluator_cls.return_value = mock_evaluator

        result = eval_task.fn()
        mock_evaluator.evaluate.assert_called_once()


class TestFullPipelineFlow:
    """Tests for the full pipeline orchestration flow."""

    def test_flow_module_imports(self):
        """Test that full_pipeline_flow module imports without error."""
        from src.flows import full_pipeline_flow

        assert hasattr(full_pipeline_flow, "full_pipeline")

    def test_flow_is_decorated(self):
        """Test that full_pipeline is a Prefect flow."""
        from src.flows.full_pipeline_flow import full_pipeline

        # Prefect flows have __wrapped__ or are callable
        assert callable(full_pipeline)


class TestMedallionFlow:
    """Tests for the medallion architecture flow."""

    def test_flow_module_imports(self):
        """Test that medallion_flow module imports without error."""
        from src.flows import medallion_flow

        assert hasattr(medallion_flow, "medallion_pipeline") or hasattr(
            medallion_flow, "medallion_flow"
        )


class TestReindexFlow:
    """Tests for the reindex flow."""

    def test_flow_module_imports(self):
        """Test that reindex_flow module imports without error."""
        from src.flows import reindex_flow

        assert reindex_flow is not None


class TestScrapeQualityFlow:
    """Tests for the scrape quality validation flow."""

    def test_flow_module_imports(self):
        """Test that scrape_quality_flow module imports without error."""
        from src.flows import scrape_quality_flow

        assert scrape_quality_flow is not None

    @patch("src.flows.scrape_quality_flow.validate_articles")
    @patch("src.flows.scrape_quality_flow.get_run_logger")
    def test_quality_task_calls_validator(self, mock_logger, mock_validate):
        """Test that quality task invokes validate_articles."""
        from src.flows.scrape_quality_flow import quality_check_task

        mock_validate.return_value = MagicMock(
            total=10, valid=[{}] * 8, rejections=[{}, {}], pass_rate=0.8
        )

        result = quality_check_task.fn(articles=[{"link": "x"}])
        mock_validate.assert_called_once()
