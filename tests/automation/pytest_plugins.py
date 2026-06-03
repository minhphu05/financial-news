"""Pytest configuration for automation tests — custom markers and plugins."""

import pytest


def pytest_configure(config):
    """Register custom markers for automation tests."""
    config.addinivalue_line("markers", "selenium: Selenium WebDriver tests")
    config.addinivalue_line("markers", "playwright: Playwright async tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests requiring a running app")
    config.addinivalue_line("markers", "slow: Tests that take longer than usual")
