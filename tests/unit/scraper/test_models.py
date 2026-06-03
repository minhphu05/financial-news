"""Unit tests for src/scraper/models.py.

Tests SQLAlchemy ORM models for the scraper module.
Validates column definitions, constraints, and relationships.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock


class TestNewsArticleModel:
    """Tests for the NewsArticle SQLAlchemy model."""

    def test_model_has_required_columns(self):
        """Test that NewsArticle has all expected columns."""
        from src.scraper.models import NewsArticle

        mapper = NewsArticle.__mapper__
        column_names = {col.key for col in mapper.column_attrs}

        expected_columns = {
            "news_id",
            "title",
            "link",
            "content",
            "post_date",
            "author",
            "source",
            "keyword",
            "ticker_symbol",
        }
        # Check that at least the expected columns are present
        assert expected_columns.issubset(column_names), (
            f"Missing columns: {expected_columns - column_names}"
        )

    def test_tablename(self):
        """Test that the table name is correctly defined."""
        from src.scraper.models import NewsArticle

        assert hasattr(NewsArticle, "__tablename__")
        assert isinstance(NewsArticle.__tablename__, str)
        assert len(NewsArticle.__tablename__) > 0

    def test_instantiation(self):
        """Test that a NewsArticle can be instantiated."""
        from src.scraper.models import NewsArticle

        article = NewsArticle(
            news_id="12345",
            title="Test Article",
            link="https://cafef.vn/test-12345.chn",
            content="Article body text",
            post_date=datetime(2026, 5, 28),
            author="Author",
            source="cafef",
            keyword="FPT",
            ticker_symbol="FPT",
        )
        assert article.news_id == "12345"
        assert article.title == "Test Article"
        assert article.source == "cafef"


class TestScrapeRunModel:
    """Tests for the ScrapeRun tracking model."""

    def test_model_exists(self):
        """Test that ScrapeRun model is defined."""
        from src.scraper.models import ScrapeRun

        assert ScrapeRun is not None

    def test_has_timing_fields(self):
        """Test that ScrapeRun has started_at and finished_at columns."""
        from src.scraper.models import ScrapeRun

        mapper = ScrapeRun.__mapper__
        column_names = {col.key for col in mapper.column_attrs}

        assert "started_at" in column_names or "start_time" in column_names
        assert "finished_at" in column_names or "end_time" in column_names

    def test_has_status_field(self):
        """Test that ScrapeRun has a status/state field."""
        from src.scraper.models import ScrapeRun

        mapper = ScrapeRun.__mapper__
        column_names = {col.key for col in mapper.column_attrs}

        assert any(
            name in column_names
            for name in ["status", "state", "result"]
        )


class TestScrapeProgressModel:
    """Tests for the ScrapeProgress tracking model."""

    def test_model_exists(self):
        """Test that ScrapeProgress model is defined."""
        from src.scraper.models import ScrapeProgress

        assert ScrapeProgress is not None

    def test_has_keyword_field(self):
        """Test that ScrapeProgress tracks keyword."""
        from src.scraper.models import ScrapeProgress

        mapper = ScrapeProgress.__mapper__
        column_names = {col.key for col in mapper.column_attrs}

        assert "keyword" in column_names

    def test_has_page_tracking(self):
        """Test that ScrapeProgress has page count fields."""
        from src.scraper.models import ScrapeProgress

        mapper = ScrapeProgress.__mapper__
        column_names = {col.key for col in mapper.column_attrs}

        page_fields = {"pages_scraped", "page_count", "current_page", "last_page"}
        assert any(field in column_names for field in page_fields)
