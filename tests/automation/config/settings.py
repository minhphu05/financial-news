"""Automation test configuration — loaded from environment variables.

Provides:
    - Base URLs for the frontend and API
    - Browser configuration (headless, timeouts, viewport)
    - Screenshot and recording settings

Usage:
    from tests.automation.config.settings import AutomationSettings

    settings = AutomationSettings.from_env()
    print(settings.base_url)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class BrowserConfig:
    """Browser configuration for automation tests.

    Attributes:
        headless: Run browser in headless mode (no visible window).
        slow_mo: Milliseconds to slow down operations (useful for debugging).
        viewport_width: Browser viewport width in pixels.
        viewport_height: Browser viewport height in pixels.
        timeout: Default action timeout in milliseconds.
        navigation_timeout: Page navigation timeout in milliseconds.
        implicit_wait: Selenium implicit wait in seconds.
        page_load_timeout: Page load timeout in seconds.
    """

    headless: bool = True
    slow_mo: int = 0
    viewport_width: int = 1280
    viewport_height: int = 720
    timeout: int = 30000
    navigation_timeout: int = 60000
    implicit_wait: int = 10
    page_load_timeout: int = 30


@dataclass(frozen=True)
class AutomationSettings:
    """Centralised settings for all automation tests.

    All values are read from environment variables at construction time.
    No hardcoded values — every setting has a sensible default that can
    be overridden via the environment.

    Attributes:
        base_url: Frontend application URL.
        api_base_url: Backend API URL.
        browser: Browser configuration.
        screenshot_dir: Directory to save failure screenshots.
        video_dir: Directory to save test recordings.
        browsers: List of browser names to test across.
        retry_count: Number of retries for flaky tests.
    """

    base_url: str
    api_base_url: str
    browser: BrowserConfig
    screenshot_dir: str
    video_dir: str
    browsers: List[str]
    retry_count: int

    @classmethod
    def from_env(cls) -> AutomationSettings:
        """Construct settings from environment variables.

        Environment Variables:
            TEST_BASE_URL: Frontend URL (default: http://localhost:5173)
            TEST_API_BASE_URL: API URL (default: http://localhost:8000)
            TEST_HEADLESS: Run headless (default: true)
            TEST_SLOW_MO: Slow motion ms (default: 0)
            TEST_VIEWPORT_WIDTH: Viewport width (default: 1280)
            TEST_VIEWPORT_HEIGHT: Viewport height (default: 720)
            TEST_TIMEOUT: Action timeout ms (default: 30000)
            TEST_NAV_TIMEOUT: Navigation timeout ms (default: 60000)
            TEST_SCREENSHOT_DIR: Screenshot directory (default: tests/automation/screenshots)
            TEST_VIDEO_DIR: Video directory (default: tests/automation/videos)
            TEST_BROWSERS: Comma-separated browsers (default: chromium)
            TEST_RETRY_COUNT: Retry count (default: 2)

        Returns:
            AutomationSettings: Fully configured settings instance.
        """
        browser_config = BrowserConfig(
            headless=os.getenv("TEST_HEADLESS", "true").lower() in ("true", "1", "yes"),
            slow_mo=int(os.getenv("TEST_SLOW_MO", "0")),
            viewport_width=int(os.getenv("TEST_VIEWPORT_WIDTH", "1280")),
            viewport_height=int(os.getenv("TEST_VIEWPORT_HEIGHT", "720")),
            timeout=int(os.getenv("TEST_TIMEOUT", "30000")),
            navigation_timeout=int(os.getenv("TEST_NAV_TIMEOUT", "60000")),
            implicit_wait=int(os.getenv("TEST_IMPLICIT_WAIT", "10")),
            page_load_timeout=int(os.getenv("TEST_PAGE_LOAD_TIMEOUT", "30")),
        )

        browsers_raw = os.getenv("TEST_BROWSERS", "chromium")
        browsers = [b.strip() for b in browsers_raw.split(",") if b.strip()]

        return cls(
            base_url=os.getenv("TEST_BASE_URL", "http://localhost:5173"),
            api_base_url=os.getenv("TEST_API_BASE_URL", "http://localhost:8000"),
            browser=browser_config,
            screenshot_dir=os.getenv(
                "TEST_SCREENSHOT_DIR", "tests/automation/screenshots"
            ),
            video_dir=os.getenv("TEST_VIDEO_DIR", "tests/automation/videos"),
            browsers=browsers,
            retry_count=int(os.getenv("TEST_RETRY_COUNT", "2")),
        )
