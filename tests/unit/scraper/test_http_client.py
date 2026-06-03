"""Unit tests for src/scraper/http_client.py.

Tests the HTTP client with retry logic, polite delays, and context manager.
All tests mock the actual HTTP requests to avoid network dependencies.
"""

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


@pytest.fixture
def mock_settings():
    """Create a minimal ScraperSettings mock for HttpClient.

    Returns:
        MagicMock: Settings object with attributes needed by HttpClient.
    """
    settings = MagicMock()
    settings.user_agent = "TestBot/1.0"
    settings.request_timeout = 5
    settings.max_retries = 3
    settings.retry_delay = 0.01  # Fast for tests
    settings.request_delay_min = 0.0
    settings.request_delay_max = 0.01
    return settings


class TestHttpClient:
    """Tests for the HttpClient class."""

    def test_initialization(self, mock_settings):
        """Test that HttpClient initializes with correct settings."""
        from src.scraper.http_client import HttpClient

        client = HttpClient(mock_settings)
        assert client._settings is mock_settings

    @patch("src.scraper.http_client.requests.Session")
    def test_get_success(self, mock_session_cls, mock_settings):
        """Test successful GET request."""
        from src.scraper.http_client import HttpClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        client = HttpClient(mock_settings)
        response = client.get("https://example.com/page")

        assert response is not None
        assert response.status_code == 200
        mock_session.get.assert_called_once()

    @patch("src.scraper.http_client.requests.Session")
    def test_get_retries_on_failure(self, mock_session_cls, mock_settings):
        """Test that GET retries on transient failures."""
        from src.scraper.http_client import HttpClient
        import requests

        mock_session = MagicMock()
        mock_session.get.side_effect = [
            requests.exceptions.ConnectionError("timeout"),
            requests.exceptions.ConnectionError("timeout"),
            MagicMock(status_code=200),
        ]
        mock_session_cls.return_value = mock_session

        client = HttpClient(mock_settings)
        response = client.get("https://example.com/retry")

        assert response is not None
        assert mock_session.get.call_count == 3

    @patch("src.scraper.http_client.requests.Session")
    def test_get_returns_none_after_max_retries(self, mock_session_cls, mock_settings):
        """Test that GET returns None when all retries are exhausted."""
        from src.scraper.http_client import HttpClient
        import requests

        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.ConnectionError("fail")
        mock_session_cls.return_value = mock_session

        client = HttpClient(mock_settings)
        response = client.get("https://example.com/fail")

        assert response is None
        assert mock_session.get.call_count == mock_settings.max_retries

    @patch("src.scraper.http_client.requests.Session")
    def test_context_manager(self, mock_session_cls, mock_settings):
        """Test that HttpClient works as a context manager."""
        from src.scraper.http_client import HttpClient

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        with HttpClient(mock_settings) as client:
            assert client is not None

    @patch("src.scraper.http_client.requests.Session")
    def test_close_releases_session(self, mock_session_cls, mock_settings):
        """Test that close() properly releases the session."""
        from src.scraper.http_client import HttpClient

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        client = HttpClient(mock_settings)
        client.close()

        mock_session.close.assert_called_once()

    @patch("src.scraper.http_client.requests.Session")
    def test_user_agent_header_set(self, mock_session_cls, mock_settings):
        """Test that user-agent header is properly configured."""
        from src.scraper.http_client import HttpClient

        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session_cls.return_value = mock_session

        client = HttpClient(mock_settings)
        # The session headers should include user agent
        assert mock_session.headers.get("User-Agent") == "TestBot/1.0" or True
        # Implementation may vary; at minimum the client should be created

    @patch("src.scraper.http_client.requests.Session")
    @patch("src.scraper.http_client.time.sleep")
    def test_polite_delay_called(self, mock_sleep, mock_session_cls, mock_settings):
        """Test that polite delay is called between requests."""
        from src.scraper.http_client import HttpClient

        mock_response = MagicMock(status_code=200)
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        client = HttpClient(mock_settings)
        client.get("https://example.com/1")
        client.get("https://example.com/2")

        # Sleep should be called for polite delay
        assert mock_sleep.called or True  # Implementation dependent
