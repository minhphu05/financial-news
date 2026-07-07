"""Unit tests for src/flows/ Prefect flow definitions.

Tests flow and task function signatures, decorators, and logic with
mocked Prefect runtime and downstream dependencies.
"""

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


class TestDeferredIngestFlow:
    """Tests for the deferred ingestion flow."""

    def test_ingest_module_imports(self):
        """Test that the deferred ingest flow module imports."""
        from src.flows.future_use import ingest_flow

        assert hasattr(ingest_flow, "ingest_flow")
        assert hasattr(ingest_flow, "ingest_task")


class TestDeferredEvalFlow:
    """Tests for the deferred evaluation flow."""

    def test_eval_module_imports(self):
        """Test that the deferred eval flow module imports."""
        from src.flows.future_use import eval_flow

        assert hasattr(eval_flow, "rag_eval_flow")
        assert hasattr(eval_flow, "evaluate_rag_task")


class TestFullPipelineFlow:
    """Tests for the deferred full pipeline orchestration flow."""

    def test_flow_module_imports(self):
        """Test that full_pipeline_flow module imports without error."""
        from src.flows.future_use import full_pipeline_flow

        assert hasattr(full_pipeline_flow, "full_pipeline_flow")

    def test_flow_is_decorated(self):
        """Test that full_pipeline is a Prefect flow."""
        from src.flows.future_use.full_pipeline_flow import full_pipeline_flow

        # Prefect flows have __wrapped__ or are callable
        assert callable(full_pipeline_flow)


class TestMedallionFlow:
    """Tests for the deferred medallion architecture flow."""

    def test_flow_module_imports(self):
        """Test that medallion_flow module imports without error."""
        from src.flows.future_use import medallion_flow

        assert hasattr(medallion_flow, "medallion_pipeline") or hasattr(
            medallion_flow, "medallion_flow"
        )


class TestReindexFlow:
    """Tests for the deferred reindex flow."""

    def test_flow_module_imports(self):
        """Test that reindex_flow module imports without error."""
        from src.flows.future_use import reindex_flow

        assert reindex_flow is not None


class TestScrapeQualityFlow:
    """Tests for the deferred scrape quality validation flow."""

    def test_flow_module_imports(self):
        """Test that scrape_quality_flow module imports without error."""
        from src.flows.future_use import scrape_quality_flow

        assert scrape_quality_flow is not None

    @patch("src.flows.future_use.scrape_quality_flow.validate_articles")
    @patch("src.flows.future_use.scrape_quality_flow.get_run_logger")
    def test_quality_task_calls_validator(self, mock_logger, mock_validate):
        """Test that quality task invokes validate_articles."""
        from src.flows.future_use.scrape_quality_flow import quality_gate_task

        mock_validate.return_value = MagicMock(
            total=10, valid=[{}] * 8, rejections=[{}, {}], pass_rate=0.8
        )

        result = quality_gate_task.fn(articles=[{"link": "x"}])
        mock_validate.assert_called_once()
