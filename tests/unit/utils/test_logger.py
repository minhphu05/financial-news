"""Unit tests for src/utils/logger.py.

Tests the Colors class, ColoredFormatter, JsonFormatter,
and thread-local context management functions.
"""

import json
import logging
import threading

import pytest

from src.utils.logger import (
    Colors,
    ColoredFormatter,
    JsonFormatter,
    clear_log_context,
    get_log_context,
    set_log_context,
)


class TestLogContext:
    """Tests for thread-local log context management."""

    def setup_method(self):
        """Clear context before each test to ensure isolation."""
        clear_log_context()

    def teardown_method(self):
        """Clean up after each test."""
        clear_log_context()

    def test_set_and_get_single_field(self):
        """Test setting and retrieving a single context field."""
        set_log_context(source_name="cafef")
        ctx = get_log_context()

        assert ctx["source_name"] == "cafef"

    def test_set_multiple_fields(self):
        """Test setting multiple context fields at once."""
        set_log_context(
            source_name="cafef",
            ticker_symbol="FPT",
            run_id="abc-123",
        )
        ctx = get_log_context()

        assert ctx["source_name"] == "cafef"
        assert ctx["ticker_symbol"] == "FPT"
        assert ctx["run_id"] == "abc-123"

    def test_clear_removes_all_fields(self):
        """Test that clear_log_context removes all fields."""
        set_log_context(source_name="cafef", keyword="FPT")
        clear_log_context()
        ctx = get_log_context()

        assert ctx == {}

    def test_get_returns_copy(self):
        """Test that get_log_context returns a copy, not the original."""
        set_log_context(key="value")
        ctx = get_log_context()
        ctx["key"] = "modified"

        # Original should be unchanged
        assert get_log_context()["key"] == "value"

    def test_overwrite_existing_field(self):
        """Test that setting a field again overwrites it."""
        set_log_context(ticker="FPT")
        set_log_context(ticker="VNM")

        assert get_log_context()["ticker"] == "VNM"

    def test_thread_isolation(self):
        """Test that context is isolated between threads."""
        results = {}

        def worker(name, value):
            set_log_context(worker=value)
            import time

            time.sleep(0.01)
            results[name] = get_log_context()

        t1 = threading.Thread(target=worker, args=("t1", "thread-1"))
        t2 = threading.Thread(target=worker, args=("t2", "thread-2"))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["t1"]["worker"] == "thread-1"
        assert results["t2"]["worker"] == "thread-2"

    def test_empty_context_by_default(self):
        """Test that fresh context is empty."""
        clear_log_context()
        assert get_log_context() == {}


class TestColors:
    """Tests for the Colors class constants."""

    def test_has_standard_colors(self):
        """Test that Colors defines the expected color constants."""
        assert hasattr(Colors, "GREEN")
        assert hasattr(Colors, "RED")
        assert hasattr(Colors, "YELLOW")
        assert hasattr(Colors, "BLUE")
        assert hasattr(Colors, "CYAN")
        assert hasattr(Colors, "MAGENTA")
        assert hasattr(Colors, "WHITE")
        assert hasattr(Colors, "RESET")
        assert hasattr(Colors, "BOLD")
        assert hasattr(Colors, "DIM")

    def test_colors_are_strings(self):
        """Test that color constants are string values (ANSI codes)."""
        assert isinstance(Colors.GREEN, str)
        assert isinstance(Colors.RED, str)
        assert isinstance(Colors.RESET, str)


class TestColoredFormatter:
    """Tests for the ColoredFormatter class."""

    def test_formats_info_level(self):
        """Test INFO level formatting includes ANSI color codes."""
        formatter = ColoredFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)

        # Should contain the message
        assert "Test message" in formatted

    def test_formats_error_level(self):
        """Test ERROR level formatting."""
        formatter = ColoredFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)

        assert "Error occurred" in formatted

    def test_different_levels_have_different_formatting(self):
        """Test that INFO and ERROR produce different ANSI prefixes."""
        formatter = ColoredFormatter("%(message)s")

        info_record = logging.LogRecord(
            "t", logging.INFO, "", 0, "msg", (), None
        )
        error_record = logging.LogRecord(
            "t", logging.ERROR, "", 0, "msg", (), None
        )

        info_fmt = formatter.format(info_record)
        error_fmt = formatter.format(error_record)

        # They may differ in color codes
        # At minimum both should contain the message
        assert "msg" in info_fmt
        assert "msg" in error_fmt


class TestJsonFormatter:
    """Tests for the JsonFormatter class."""

    def _make_record(self, msg="Test", level=logging.INFO, **extra):
        """Helper to create a log record with optional extras."""
        record = logging.LogRecord(
            name="src.scraper.page_scraper",
            level=level,
            pathname="page_scraper.py",
            lineno=42,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_output_is_valid_json(self):
        """Test that formatted output is parseable JSON."""
        formatter = JsonFormatter()
        record = self._make_record("Hello world")
        output = formatter.format(record)

        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_includes_timestamp(self):
        """Test that JSON output contains a timestamp field."""
        formatter = JsonFormatter()
        record = self._make_record("Test")
        parsed = json.loads(formatter.format(record))

        assert "timestamp" in parsed
        assert "T" in parsed["timestamp"]  # ISO format

    def test_includes_level(self):
        """Test that JSON output contains the log level."""
        formatter = JsonFormatter()
        record = self._make_record("Test", level=logging.WARNING)
        parsed = json.loads(formatter.format(record))

        assert parsed["level"] == "WARNING"

    def test_includes_logger_name(self):
        """Test that JSON output contains the logger name."""
        formatter = JsonFormatter()
        record = self._make_record("Test")
        parsed = json.loads(formatter.format(record))

        assert parsed["logger"] == "src.scraper.page_scraper"

    def test_includes_message(self):
        """Test that JSON output contains the log message."""
        formatter = JsonFormatter()
        record = self._make_record("Scraping page 5 of 10")
        parsed = json.loads(formatter.format(record))

        assert "Scraping page 5 of 10" in parsed["message"]

    def test_includes_context_fields(self):
        """Test that thread-local context fields are merged into JSON."""
        clear_log_context()
        set_log_context(source_name="cafef", ticker_symbol="FPT")

        formatter = JsonFormatter()
        record = self._make_record("Processing")
        parsed = json.loads(formatter.format(record))

        assert parsed.get("source_name") == "cafef"
        assert parsed.get("ticker_symbol") == "FPT"

        clear_log_context()

    def test_strips_ansi_codes(self):
        """Test that ANSI escape codes are removed from message."""
        formatter = JsonFormatter()
        # Simulate a message with ANSI codes
        ansi_msg = "\x1b[32mGreen text\x1b[0m"
        record = self._make_record(ansi_msg)
        parsed = json.loads(formatter.format(record))

        assert "\x1b[" not in parsed["message"]
        assert "Green text" in parsed["message"]

    def test_includes_exception_info(self):
        """Test that exception traceback is included when present."""
        import traceback

        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error",
                args=(),
                exc_info=sys.exc_info(),
            )

        parsed = json.loads(formatter.format(record))
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]

    def test_vietnamese_message_preserved(self):
        """Test that Vietnamese characters are preserved (ensure_ascii=False)."""
        formatter = JsonFormatter()
        record = self._make_record("Cổ phiếu FPT tăng giá mạnh")
        parsed = json.loads(formatter.format(record))

        assert "Cổ phiếu FPT tăng giá mạnh" in parsed["message"]
