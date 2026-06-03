"""Automation test fixtures — Selenium and Playwright browser setup.

Provides pytest fixtures that manage browser lifecycle for both
Selenium WebDriver and Playwright, respecting environment configuration.
"""

from __future__ import annotations

import os
from typing import Generator

import pytest

from tests.automation.config.settings import AutomationSettings


@pytest.fixture(scope="session")
def settings() -> AutomationSettings:
    """Load automation settings from environment.

    Returns:
        AutomationSettings: Validated configuration for test execution.
    """
    return AutomationSettings.from_env()


# ──────────────────────────────────────────────────────────────────────────────
# Selenium Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def selenium_driver(settings: AutomationSettings) -> Generator:
    """Create and manage a Selenium WebDriver session.

    Uses Chrome by default; supports headless mode via settings.
    The driver is shared across all tests in the session for performance,
    with each test navigating to its own page.

    Args:
        settings: Automation configuration.

    Yields:
        WebDriver: Active Selenium Chrome WebDriver.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()

    if settings.browser.headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(
        f"--window-size={settings.browser.viewport_width},{settings.browser.viewport_height}"
    )

    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(settings.browser.implicit_wait)

    yield driver

    driver.quit()


@pytest.fixture
def selenium_page(selenium_driver, settings: AutomationSettings):
    """Provide a fresh page state for each Selenium test.

    Navigates to the base URL before each test and clears cookies after.

    Args:
        selenium_driver: Session-scoped WebDriver.
        settings: Automation configuration.

    Yields:
        WebDriver: The same driver, reset to base URL.
    """
    selenium_driver.get(settings.base_url)
    yield selenium_driver
    selenium_driver.delete_all_cookies()


# ──────────────────────────────────────────────────────────────────────────────
# Playwright Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def playwright_browser(settings: AutomationSettings) -> Generator:
    """Launch a Playwright browser instance for the session.

    Args:
        settings: Automation configuration.

    Yields:
        Browser: Active Playwright Chromium browser.
    """
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()

    browser = pw.chromium.launch(
        headless=settings.browser.headless,
        slow_mo=settings.browser.slow_mo,
    )

    yield browser

    browser.close()
    pw.stop()


@pytest.fixture
def playwright_page(playwright_browser, settings: AutomationSettings) -> Generator:
    """Create a new Playwright page (browser context) for each test.

    Each test gets an isolated browser context with its own cookies,
    localStorage, and session storage.

    Args:
        playwright_browser: Session-scoped browser.
        settings: Automation configuration.

    Yields:
        Page: Fresh Playwright page instance.
    """
    context = playwright_browser.new_context(
        viewport={
            "width": settings.browser.viewport_width,
            "height": settings.browser.viewport_height,
        },
        record_video_dir=settings.video_dir if os.getenv("RECORD_VIDEO") else None,
    )
    page = context.new_page()
    page.set_default_timeout(settings.browser.page_load_timeout * 1000)

    yield page

    page.close()
    context.close()


# ──────────────────────────────────────────────────────────────────────────────
# Playwright Async Fixtures (for async tests)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
async def async_playwright_page(settings: AutomationSettings):
    """Create an async Playwright page for async test functions.

    Args:
        settings: Automation configuration.

    Yields:
        Page: Async Playwright page instance.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=settings.browser.headless,
            slow_mo=settings.browser.slow_mo,
        )
        context = await browser.new_context(
            viewport={
                "width": settings.browser.viewport_width,
                "height": settings.browser.viewport_height,
            },
        )
        page = await context.new_page()
        page.set_default_timeout(settings.browser.page_load_timeout * 1000)

        yield page

        await page.close()
        await context.close()
        await browser.close()
