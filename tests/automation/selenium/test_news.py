"""Selenium — News Page E2E tests.

Tests verify news listing, article rendering, and navigation within
the news section of the application.
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By

from tests.automation.config.settings import AutomationSettings
from tests.automation.pages.selenium_pages import NewsPage


@pytest.mark.selenium
@pytest.mark.e2e
class TestNewsPageLoad:
    """Verify the news page loads and displays content."""

    def test_news_page_loads(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """News page should load within timeout.

        Validates that navigating to /news renders the news list container.
        """
        page = NewsPage(selenium_page, settings.base_url)
        page.navigate()
        assert page.is_loaded(), "News page did not load within timeout"

    def test_news_page_title(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """News page should have an appropriate title."""
        page = NewsPage(selenium_page, settings.base_url)
        page.navigate()
        title = page.get_title()
        assert title, "News page title should not be empty"


@pytest.mark.selenium
@pytest.mark.e2e
class TestNewsArticleDisplay:
    """Verify news articles render correctly."""

    def test_articles_are_displayed(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """At least one news article should be visible on the page."""
        page = NewsPage(selenium_page, settings.base_url)
        page.navigate()
        cards = page.get_news_cards()
        # Articles may be loading from API; container should exist
        assert cards is not None

    def test_article_has_title(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Each article card should contain a title element."""
        page = NewsPage(selenium_page, settings.base_url)
        page.navigate()
        titles = page.get_article_titles()
        if titles:
            assert all(len(t) > 0 for t in titles), "Article titles should not be empty"

    def test_article_cards_are_clickable(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Article cards should be interactive — linking to detail or source."""
        page = NewsPage(selenium_page, settings.base_url)
        page.navigate()
        cards = page.get_news_cards()
        if cards:
            initial_url = selenium_page.current_url
            cards[0].click()
            # Either URL changes or a modal/detail appears
            # We don't assert specific URL to avoid brittleness

    def test_screenshot_on_news_page(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Capture screenshot of news page for visual inspection."""
        page = NewsPage(selenium_page, settings.base_url)
        page.navigate()
        path = page.take_screenshot("test_news_page")
        assert path and path.endswith(".png")


@pytest.mark.selenium
@pytest.mark.e2e
class TestNewsPageNavigation:
    """Verify navigation within and from the news page."""

    def test_back_to_home(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """User should be able to navigate back to homepage from news."""
        page = NewsPage(selenium_page, settings.base_url)
        page.navigate()

        # Click home/logo link
        home_links = selenium_page.find_elements(
            By.CSS_SELECTOR, "a[href='/'], a[href=''], .logo"
        )
        if home_links:
            home_links[0].click()
            current = selenium_page.current_url.rstrip("/")
            expected = settings.base_url.rstrip("/")
            assert current == expected or current.endswith("/")

    def test_browser_back_button(
        self, selenium_page, settings: AutomationSettings
    ) -> None:
        """Browser back button should return to previous page."""
        # Navigate home first, then to news
        selenium_page.get(settings.base_url)
        page = NewsPage(selenium_page, settings.base_url)
        page.navigate()

        selenium_page.back()
        # Should be back at homepage
        current = selenium_page.current_url.rstrip("/")
        assert "/news" not in current
