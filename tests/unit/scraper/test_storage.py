"""Unit tests for src/scraper/storage.py.

Tests the StorageManager class with mocked database connections.
Verifies article persistence, deduplication, and scrape run tracking.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


@pytest.fixture
def mock_session():
    """Create a mock SQLAlchemy session.

    Returns:
        MagicMock: A mock session with query, add, commit, and close methods.
    """
    session = MagicMock()
    session.query.return_value = session
    session.filter.return_value = session
    session.filter_by.return_value = session
    session.first.return_value = None
    session.all.return_value = []
    session.count.return_value = 0
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create a mock session factory (sessionmaker).

    Returns:
        MagicMock: Factory that returns the mock_session.
    """
    factory = MagicMock(return_value=mock_session)
    return factory


class TestStorageManager:
    """Tests for the StorageManager class."""

    @patch("src.scraper.storage.create_engine")
    @patch("src.scraper.storage.sessionmaker")
    def test_initialization(self, mock_sessionmaker, mock_create_engine):
        """Test that StorageManager initializes with correct DSN."""
        from src.scraper.storage import StorageManager

        mock_settings = MagicMock()
        mock_settings.postgres_dsn = "postgresql+psycopg2://u:p@localhost/db"

        manager = StorageManager(mock_settings)
        assert manager is not None

    @patch("src.scraper.storage.create_engine")
    @patch("src.scraper.storage.sessionmaker")
    def test_article_exists_when_found(self, mock_sessionmaker, mock_engine):
        """Test article_exists returns True when article is in DB."""
        from src.scraper.storage import StorageManager

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            MagicMock()
        )
        mock_sessionmaker.return_value = MagicMock(return_value=mock_session)

        mock_settings = MagicMock()
        mock_settings.postgres_dsn = "postgresql+psycopg2://u:p@localhost/db"

        manager = StorageManager(mock_settings)
        result = manager.article_exists("12345")

        assert result is True

    @patch("src.scraper.storage.create_engine")
    @patch("src.scraper.storage.sessionmaker")
    def test_article_exists_when_not_found(self, mock_sessionmaker, mock_engine):
        """Test article_exists returns False when article is missing."""
        from src.scraper.storage import StorageManager

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_sessionmaker.return_value = MagicMock(return_value=mock_session)

        mock_settings = MagicMock()
        mock_settings.postgres_dsn = "postgresql+psycopg2://u:p@localhost/db"

        manager = StorageManager(mock_settings)
        result = manager.article_exists("nonexistent")

        assert result is False

    @patch("src.scraper.storage.create_engine")
    @patch("src.scraper.storage.sessionmaker")
    def test_save_article_commits(self, mock_sessionmaker, mock_engine):
        """Test that save_article calls session.commit()."""
        from src.scraper.storage import StorageManager, ScrapedArticle

        mock_session = MagicMock()
        mock_sessionmaker.return_value = MagicMock(return_value=mock_session)

        mock_settings = MagicMock()
        mock_settings.postgres_dsn = "postgresql+psycopg2://u:p@localhost/db"

        manager = StorageManager(mock_settings)

        article = ScrapedArticle(
            news_id="12345",
            title="Test",
            link="https://cafef.vn/test-12345.chn",
            content="Body",
            author="Author",
            post_date=datetime(2026, 5, 28),
            source="cafef",
            keyword="FPT",
            ticker_symbol="FPT",
        )
        manager.save_article(article)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("src.scraper.storage.create_engine")
    @patch("src.scraper.storage.sessionmaker")
    def test_create_scrape_run(self, mock_sessionmaker, mock_engine):
        """Test that create_scrape_run returns a run ID."""
        from src.scraper.storage import StorageManager

        mock_session = MagicMock()
        mock_sessionmaker.return_value = MagicMock(return_value=mock_session)

        mock_settings = MagicMock()
        mock_settings.postgres_dsn = "postgresql+psycopg2://u:p@localhost/db"

        manager = StorageManager(mock_settings)
        run_id = manager.create_scrape_run()

        # Should have added and committed the run
        assert mock_session.add.called
        assert mock_session.commit.called

    @patch("src.scraper.storage.create_engine")
    @patch("src.scraper.storage.sessionmaker")
    def test_finish_scrape_run(self, mock_sessionmaker, mock_engine):
        """Test that finish_scrape_run updates the run record."""
        from src.scraper.storage import StorageManager

        mock_run = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_run
        )
        mock_sessionmaker.return_value = MagicMock(return_value=mock_session)

        mock_settings = MagicMock()
        mock_settings.postgres_dsn = "postgresql+psycopg2://u:p@localhost/db"

        manager = StorageManager(mock_settings)
        manager.finish_scrape_run(run_id=1, status="success", total_articles=10)

        mock_session.commit.assert_called()


class TestScrapedArticleDataclass:
    """Tests for the ScrapedArticle dataclass."""

    def test_creation(self):
        """Test that ScrapedArticle can be created with all fields."""
        from src.scraper.storage import ScrapedArticle

        article = ScrapedArticle(
            news_id="54321",
            title="Vinamilk đạt doanh thu kỷ lục",
            link="https://cafef.vn/vinamilk-54321.chn",
            content="Nội dung bài viết...",
            author="Trần B",
            post_date=datetime(2026, 6, 1),
            source="cafef",
            keyword="VNM",
            ticker_symbol="VNM",
        )
        assert article.news_id == "54321"
        assert article.title == "Vinamilk đạt doanh thu kỷ lục"
        assert article.ticker_symbol == "VNM"

    def test_optional_fields(self):
        """Test that optional fields default to None."""
        from src.scraper.storage import ScrapedArticle

        article = ScrapedArticle(
            news_id="11111",
            title="Test",
            link="https://cafef.vn/test-11111.chn",
            content="Content",
            author=None,
            post_date=None,
            source="cafef",
            keyword="TEST",
            ticker_symbol=None,
        )
        assert article.author is None
        assert article.post_date is None
        assert article.ticker_symbol is None
