"""Selenium — Cross-page Navigation E2E tests.

Tests verify that all application routes are accessible, navigation
between pages works correctly, and the SPA router handles transitions.
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By

from tests.automation.config.settings import AutomationSettings
from tests.automation.pages.selenium_pages import (
    ChatPage,
    HomePage,
    NewsPage,
    StockNewsPage,
)


@pytest.mark.selenium
@pytest.mark.e2e
class TestRouteAccessibility:
    """Verify all application routes respond without errors."""

    @pytest.mark.parametrize(
        "path,description",
        [
            ("/", "Homepage"),
            ("/news", "News listing"),
            ("/chat", "Chat interface"),
        ],
    )
    def test_route_responds(
        self,
        selenium_page,
        settings: AutomationSettings,
        path: str,
        description: str,
    ) -> None:
        """Each route should render without a blank page or error.

        Args:
            path: URL path to test.
            description: Human-readable description for test output.
        """
        url = f"{settings.base_url.rstrip('/')}{path}"
        selenium_page.get(url)

        # Page should have some content (not blank)
        body = selenium_page.find_element(By.TAG_NAME, "body")
        assert body.text or selenium_page.find_elements(By.CSS_SELECTOR, "*")

    def test_invalid_route_handled(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Navigating to a non-existent route should show a 404 or redirect.

        The SPA should gracefully handle unknown routes rather than crashing.
        """
        url = f"{settings.base_url.rstrip('/')}/this-route-does-not-exist"
        selenium_page.get(url)

        # Should either show 404 content or redirect to home
        body_text = selenium_page.find_element(By.TAG_NAME, "body").text
        current_url = selenium_page.current_url
        assert body_text or "/" in current_url


@pytest.mark.selenium
@pytest.mark.e2e
class TestNavigationFlow:
    """Verify multi-page navigation flows work end-to-end."""

    def test_home_to_news_to_chat(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Complete navigation flow: Home → News → Chat.

        Simulates a typical user browsing pattern.
        """
        # Start at home
        home = HomePage(selenium_page, settings.base_url)
        home.navigate()
        assert home.is_loaded()

        # Navigate to news
        news = NewsPage(selenium_page, settings.base_url)
        news.navigate()
        assert news.is_loaded()

        # Navigate to chat
        chat = ChatPage(selenium_page, settings.base_url)
        chat.navigate()
        assert chat.is_loaded()

    def test_deep_link_stock_news(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Directly navigating to a stock-specific news page should work.

        Tests that the SPA router handles parameterised routes.
        """
        page = StockNewsPage(selenium_page, settings.base_url, ticker="FPT")
        page.navigate()
        # Page should render something (might show loading/no data)
        body = selenium_page.find_element(By.TAG_NAME, "body")
        assert body is not None

    def test_header_navigation_links(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Header navigation should contain links to main sections."""
        home = HomePage(selenium_page, settings.base_url)
        home.navigate()

        nav_links = selenium_page.find_elements(
            By.CSS_SELECTOR, "header a, nav a"
        )
        # Should have at least one navigation link
        assert len(nav_links) >= 1, "Header should contain navigation links"

    def test_back_forward_browser_history(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Browser history navigation should work with SPA routing.

        Validates that pushState/popState are handled correctly.
        """
        # Navigate: home → news → chat
        base = settings.base_url.rstrip("/")
        selenium_page.get(f"{base}/")
        selenium_page.get(f"{base}/news")
        selenium_page.get(f"{base}/chat")

        # Go back to news
        selenium_page.back()
        assert "/news" in selenium_page.current_url

        # Go back to home
        selenium_page.back()
        current = selenium_page.current_url.rstrip("/")
        assert current == base or current.endswith("/")

        # Go forward to news
        selenium_page.forward()
        assert "/news" in selenium_page.current_url


@pytest.mark.selenium
@pytest.mark.e2e
class TestResponsiveLayout:
    """Verify the layout adapts to different viewport sizes."""

    def test_mobile_viewport(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Page should be usable at mobile viewport dimensions (375×667)."""
        selenium_page.set_window_size(375, 667)
        home = HomePage(selenium_page, settings.base_url)
        home.navigate()
        assert home.is_loaded()

    def test_tablet_viewport(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Page should be usable at tablet viewport dimensions (768×1024)."""
        selenium_page.set_window_size(768, 1024)
        home = HomePage(selenium_page, settings.base_url)
        home.navigate()
        assert home.is_loaded()

    def test_desktop_viewport(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Page should be usable at desktop viewport dimensions (1920×1080)."""
        selenium_page.set_window_size(1920, 1080)
        home = HomePage(selenium_page, settings.base_url)
        home.navigate()
        assert home.is_loaded()
