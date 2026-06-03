"""Unit tests for src/scraper/config.py.

Tests the configuration loader to ensure environment variables are
properly read, validated, and converted to the correct types.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestHelperFunctions:
    """Tests for _get, _get_int, _get_float, _resolve_path helpers."""

    def test_get_returns_env_value(self, monkeypatch):
        """Test that _get reads from environment correctly."""
        from src.scraper.config import _get

        monkeypatch.setenv("TEST_KEY_ABC", "hello")
        assert _get("TEST_KEY_ABC") == "hello"

    def test_get_returns_default_when_missing(self):
        """Test that _get returns default for unset variables."""
        from src.scraper.config import _get

        result = _get("DEFINITELY_NOT_SET_XYZ", "fallback")
        assert result == "fallback"

    def test_get_required_raises_on_missing(self):
        """Test that _get raises RuntimeError when required var is missing."""
        from src.scraper.config import _get

        with pytest.raises(RuntimeError, match="Missing required"):
            _get("NEVER_SET_VAR_123", required=True)

    def test_get_required_raises_on_empty(self, monkeypatch):
        """Test that _get raises RuntimeError when required var is empty string."""
        from src.scraper.config import _get

        monkeypatch.setenv("EMPTY_VAR", "")
        with pytest.raises(RuntimeError, match="Missing required"):
            _get("EMPTY_VAR", required=True)

    def test_get_int_parses_correctly(self, monkeypatch):
        """Test integer parsing from environment."""
        from src.scraper.config import _get_int

        monkeypatch.setenv("INT_VAR", "42")
        assert _get_int("INT_VAR", 0) == 42

    def test_get_int_returns_default(self):
        """Test integer fallback when variable is not set."""
        from src.scraper.config import _get_int

        assert _get_int("MISSING_INT_VAR", 99) == 99

    def test_get_float_parses_correctly(self, monkeypatch):
        """Test float parsing from environment."""
        from src.scraper.config import _get_float

        monkeypatch.setenv("FLOAT_VAR", "3.14")
        assert _get_float("FLOAT_VAR", 0.0) == pytest.approx(3.14)

    def test_get_float_returns_default(self):
        """Test float fallback when variable is not set."""
        from src.scraper.config import _get_float

        assert _get_float("MISSING_FLOAT_VAR", 1.5) == pytest.approx(1.5)

    def test_resolve_path_absolute(self):
        """Test that absolute paths are returned unchanged."""
        from src.scraper.config import _resolve_path

        result = _resolve_path("/tmp/absolute/path")
        assert result == Path("/tmp/absolute/path")

    def test_resolve_path_relative(self):
        """Test that relative paths are resolved against project root."""
        from src.scraper.config import PROJECT_ROOT, _resolve_path

        result = _resolve_path("data/raw")
        assert result == (PROJECT_ROOT / "data/raw").resolve()


class TestScraperSettings:
    """Tests for the ScraperSettings dataclass."""

    def test_postgres_dsn_property(self, mock_env):
        """Test that postgres_dsn is correctly composed from fields."""
        from src.scraper.config import ScraperSettings

        settings = ScraperSettings(
            source_name="cafef",
            base_url="https://cafef.vn",
            search_url_template="https://cafef.vn/tim-kiem/trang-{page}.chn?keywords={keyword}",
            start_page=1,
            max_pages=5,
            user_agent="Mozilla/5.0",
            request_timeout=10,
            max_retries=3,
            retry_delay=1.0,
            request_delay_min=0.5,
            request_delay_max=1.5,
            raw_input_dir=Path("/tmp/raw"),
            logs_dir=Path("/tmp/logs"),
            pg_host="db.example.com",
            pg_port=5432,
            pg_user="admin",
            pg_password="secret",
            pg_database="finance",
            metadata_table_name="articles",
            mongo_uri="mongodb://localhost:27017",
            mongo_db="news",
            mongo_collection="articles",
            consecutive_known_threshold=5,
        )

        expected_dsn = (
            "postgresql+psycopg2://admin:secret@db.example.com:5432/finance"
        )
        assert settings.postgres_dsn == expected_dsn

    def test_frozen_immutability(self, mock_env):
        """Test that ScraperSettings is frozen (immutable)."""
        from src.scraper.config import ScraperSettings

        settings = ScraperSettings(
            source_name="cafef",
            base_url="https://cafef.vn",
            search_url_template="t",
            start_page=1,
            max_pages=5,
            user_agent="UA",
            request_timeout=10,
            max_retries=3,
            retry_delay=1.0,
            request_delay_min=0.5,
            request_delay_max=1.5,
            raw_input_dir=Path("/tmp"),
            logs_dir=Path("/tmp"),
            pg_host="localhost",
            pg_port=5432,
            pg_user="u",
            pg_password="p",
            pg_database="db",
            metadata_table_name="t",
            mongo_uri="mongodb://localhost",
            mongo_db="db",
            mongo_collection="c",
            consecutive_known_threshold=5,
        )

        with pytest.raises(Exception):
            settings.source_name = "other"


class TestBuildMongoUri:
    """Tests for MongoDB URI construction."""

    def test_prefers_direct_uri(self, monkeypatch):
        """Test that MONGO_URI env var takes precedence."""
        from src.scraper.config import _build_mongo_uri

        monkeypatch.setenv("MONGO_URI", "mongodb://custom:27017/mydb")
        assert _build_mongo_uri() == "mongodb://custom:27017/mydb"

    def test_builds_from_components_with_auth(self, monkeypatch):
        """Test URI construction from individual credentials."""
        from src.scraper.config import _build_mongo_uri

        monkeypatch.delenv("MONGO_URI", raising=False)
        monkeypatch.setenv("MONGO_USER", "admin")
        monkeypatch.setenv("MONGO_PASSWORD", "pass123")
        monkeypatch.setenv("MONGO_HOST", "db.host")
        monkeypatch.setenv("MONGO_PORT", "27018")

        uri = _build_mongo_uri()
        assert uri == "mongodb://admin:pass123@db.host:27018/?authSource=admin"

    def test_builds_without_auth(self, monkeypatch):
        """Test URI construction without credentials."""
        from src.scraper.config import _build_mongo_uri

        monkeypatch.delenv("MONGO_URI", raising=False)
        monkeypatch.setenv("MONGO_USER", "")
        monkeypatch.setenv("MONGO_PASSWORD", "")
        monkeypatch.setenv("MONGO_HOST", "localhost")
        monkeypatch.setenv("MONGO_PORT", "27017")

        uri = _build_mongo_uri()
        assert uri == "mongodb://localhost:27017"
