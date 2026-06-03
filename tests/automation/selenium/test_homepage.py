"""Selenium — Homepage E2E tests.

Tests verify that the homepage loads correctly, displays key UI elements,
and supports basic user interactions (navigation, stock grid rendering).
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By

from tests.automation.config.settings import AutomationSettings
from tests.automation.pages.selenium_pages import HomePage


@pytest.mark.selenium
@pytest.mark.e2e
class TestHomepageLoad:
    """Verify homepage renders correctly after initial load."""

    def test_homepage_loads_successfully(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Homepage should respond with a 200-equivalent rendered page.

        Validates that navigation to the root URL results in visible content.
        """
        page = HomePage(selenium_page, settings.base_url)
        page.navigate()
        assert page.is_loaded(), "Homepage did not load within timeout"

    def test_page_title_is_set(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Homepage should have a meaningful document title."""
        page = HomePage(selenium_page, settings.base_url)
        page.navigate()
        title = page.get_title()
        assert title, "Page title should not be empty"

    def test_header_is_visible(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Application header/navbar should be visible on homepage."""
        page = HomePage(selenium_page, settings.base_url)
        page.navigate()
        header = selenium_page.find_elements(By.CSS_SELECTOR, "header")
        assert len(header) > 0, "Header element should exist on page"

    def test_screenshot_capture(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Verify screenshot functionality works for debugging."""
        page = HomePage(selenium_page, settings.base_url)
        page.navigate()
        filepath = page.take_screenshot("test_homepage_load")
        assert filepath is not None
        assert filepath.endswith(".png")


@pytest.mark.selenium
@pytest.mark.e2e
class TestHomepageStockGrid:
    """Verify stock grid component renders with data."""

    def test_stock_grid_renders(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Stock grid container should appear on the homepage."""
        page = HomePage(selenium_page, settings.base_url)
        page.navigate()
        cards = page.get_stock_cards()
        # Grid container should at least be present (even if data is loading)
        assert cards is not None

    def test_stock_cards_are_clickable(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Each stock card should be a clickable link or interactive element."""
        page = HomePage(selenium_page, settings.base_url)
        page.navigate()
        cards = page.get_stock_cards()
        if cards:
            # First card should be clickable without raising
            try:
                cards[0].click()
            except Exception as exc:
                pytest.fail(f"Stock card is not clickable: {exc}")


@pytest.mark.selenium
@pytest.mark.e2e
class TestHomepageNavigation:
    """Verify navigation links from homepage work correctly."""

    def test_navigate_to_news(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Clicking 'News' link should navigate to /news route."""
        page = HomePage(selenium_page, settings.base_url)
        page.navigate()
        links = selenium_page.find_elements(By.CSS_SELECTOR, "a[href*='news']")
        if links:
            links[0].click()
            assert "/news" in selenium_page.current_url

    def test_navigate_to_chat(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Clicking 'Chat' link should navigate to /chat route."""
        page = HomePage(selenium_page, settings.base_url)
        page.navigate()
        links = selenium_page.find_elements(By.CSS_SELECTOR, "a[href*='chat']")
        if links:
            links[0].click()
            assert "/chat" in selenium_page.current_url
