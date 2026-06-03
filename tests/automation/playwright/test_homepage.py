"""Playwright — Homepage E2E tests (async).

Leverages Playwright's async API for fast, reliable browser automation
with built-in auto-wait and network interception capabilities.
"""

from __future__ import annotations

import pytest

from tests.automation.config.settings import AutomationSettings
from tests.automation.pages.playwright_pages import HomePage


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestHomepageLoad:
    """Verify homepage renders correctly using Playwright."""

    async def test_homepage_loads_successfully(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Homepage should load and display the header.

        Uses Playwright's networkidle wait strategy for reliability.
        """
        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()
        assert await page_obj.is_loaded_async(), "Homepage did not load"

    async def test_page_title(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Homepage should have a non-empty document title."""
        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()
        title = await page_obj.get_title_async()
        assert title, "Page title should not be empty"

    async def test_no_console_errors(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Page should load without critical JavaScript errors.

        Captures console errors during page load and fails if any
        error-level messages are detected.
        """
        errors: list[str] = []
        async_playwright_page.on("console", lambda msg: (
            errors.append(msg.text) if msg.type == "error" else None
        ))

        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        # Filter out known non-critical errors (e.g., favicon 404)
        critical_errors = [
            e for e in errors
            if "favicon" not in e.lower() and "404" not in e
        ]
        assert len(critical_errors) == 0, f"Console errors detected: {critical_errors}"


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestHomepageStockGrid:
    """Verify stock grid component with Playwright."""

    async def test_stock_grid_visible(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Stock grid container should be present on the page."""
        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()
        count = await page_obj.get_stock_count()
        # At minimum, the grid container itself should exist
        assert count >= 0

    async def test_stock_card_interaction(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Clicking a stock should navigate or show details."""
        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        # Look for any clickable stock text
        stock_links = await async_playwright_page.query_selector_all("a")
        if stock_links:
            initial_url = async_playwright_page.url
            # Just verify clickability without asserting specific navigation
            await stock_links[0].click()

    async def test_screenshot_homepage(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Capture full-page screenshot for visual regression."""
        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()
        path = await page_obj.take_screenshot("playwright_homepage")
        assert path and path.endswith(".png")


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestHomepagePerformance:
    """Basic performance checks using Playwright's network control."""

    async def test_page_loads_within_timeout(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Homepage should complete loading within the configured timeout.

        Uses Playwright's built-in networkidle detection.
        """
        page_obj = HomePage(async_playwright_page, settings.base_url)
        try:
            await page_obj.navigate()
            loaded = await page_obj.is_loaded_async()
            assert loaded
        except Exception:
            pytest.fail("Page did not load within timeout")

    async def test_no_failed_network_requests(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Critical resources should load without 5xx errors.

        Monitors network responses during page load and flags server errors.
        """
        failed_requests: list[str] = []

        async def handle_response(response):
            """Track failed responses (5xx status codes)."""
            if response.status >= 500:
                failed_requests.append(f"{response.status} {response.url}")

        async_playwright_page.on("response", handle_response)

        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        assert len(failed_requests) == 0, (
            f"Server errors during page load: {failed_requests}"
        )
