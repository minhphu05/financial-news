"""Playwright Page Objects — async page implementations.

Each class corresponds to a frontend route and provides high-level
async methods for interacting with the page in Playwright tests.
"""

from __future__ import annotations

import os
from typing import List, Optional

from playwright.async_api import Page, expect

from tests.automation.pages import BasePage


class PlaywrightBasePage(BasePage):
    """Playwright-specific base page with async interactions.

    Attributes:
        page: Playwright Page instance.
        timeout: Default timeout in milliseconds.
    """

    def __init__(
        self,
        page: Page,
        base_url: str,
        path: str = "/",
        timeout: int = 30000,
    ) -> None:
        """Initialise with a Playwright Page.

        Args:
            page: Active Playwright Page object.
            base_url: Frontend application base URL.
            path: Route path for this page.
            timeout: Default timeout in milliseconds.
        """
        super().__init__(base_url, path)
        self.page = page
        self.timeout = timeout

    async def navigate(self) -> None:
        """Navigate the browser to this page's URL."""
        await self.page.goto(self.url, wait_until="networkidle")

    def get_title(self) -> str:
        """Return the page title (synchronous wrapper for compatibility).

        Returns:
            str: Not available synchronously; use get_title_async().
        """
        return ""

    async def get_title_async(self) -> str:
        """Return the browser document title.

        Returns:
            str: Current page title.
        """
        return await self.page.title()

    async def take_screenshot(self, name: str) -> Optional[str]:
        """Save a full-page screenshot.

        Args:
            name: Base filename (without extension).

        Returns:
            Optional[str]: Full path to the saved PNG file.
        """
        screenshot_dir = os.getenv("TEST_SCREENSHOT_DIR", "tests/automation/screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        filepath = os.path.join(screenshot_dir, f"{name}.png")
        await self.page.screenshot(path=filepath, full_page=True)
        return filepath

    def is_loaded(self) -> bool:
        """Synchronous stub — use is_loaded_async() instead.

        Returns:
            bool: Always False; use async version.
        """
        return False

    async def is_loaded_async(self) -> bool:
        """Check whether the page has fully loaded (async).

        Returns:
            bool: True if page content is visible.
        """
        return True


class HomePage(PlaywrightBasePage):
    """Playwright Page Object for the Home page (route: /)."""

    _HEADER_SELECTOR = "header"
    _STOCK_GRID_SELECTOR = "[data-testid='stock-grid'], .stock-grid, main"

    def __init__(self, page: Page, base_url: str, timeout: int = 30000) -> None:
        """Initialise HomePage."""
        super().__init__(page, base_url, "/", timeout)

    async def is_loaded_async(self) -> bool:
        """Check if home page header is visible.

        Returns:
            bool: True if the header element is present.
        """
        try:
            await self.page.wait_for_selector(
                self._HEADER_SELECTOR, timeout=self.timeout
            )
            return True
        except Exception:
            return False

    async def get_stock_count(self) -> int:
        """Count the number of stock cards displayed.

        Returns:
            int: Number of visible stock cards.
        """
        elements = await self.page.query_selector_all(self._STOCK_GRID_SELECTOR)
        return len(elements)

    async def click_stock(self, ticker: str) -> None:
        """Click a stock card by ticker text.

        Args:
            ticker: Stock ticker symbol to find and click.
        """
        await self.page.click(f"text={ticker}")


class NewsPage(PlaywrightBasePage):
    """Playwright Page Object for the News page (route: /news)."""

    _NEWS_CARD_SELECTOR = "[data-testid='news-card'], .news-card, article"
    _NEWS_TITLE_SELECTOR = "h2, h3, .title"

    def __init__(self, page: Page, base_url: str, timeout: int = 30000) -> None:
        """Initialise NewsPage."""
        super().__init__(page, base_url, "/news", timeout)

    async def is_loaded_async(self) -> bool:
        """Check if news content is visible.

        Returns:
            bool: True if at least one news card is present.
        """
        try:
            await self.page.wait_for_selector(
                self._NEWS_CARD_SELECTOR, timeout=self.timeout
            )
            return True
        except Exception:
            return False

    async def get_article_titles(self) -> List[str]:
        """Extract all article titles from the page.

        Returns:
            List[str]: Article title text strings.
        """
        cards = await self.page.query_selector_all(self._NEWS_CARD_SELECTOR)
        titles = []
        for card in cards:
            title_el = await card.query_selector(self._NEWS_TITLE_SELECTOR)
            if title_el:
                text = await title_el.text_content()
                if text:
                    titles.append(text.strip())
        return titles

    async def get_article_count(self) -> int:
        """Count visible articles.

        Returns:
            int: Number of article cards displayed.
        """
        cards = await self.page.query_selector_all(self._NEWS_CARD_SELECTOR)
        return len(cards)


class ChatPage(PlaywrightBasePage):
    """Playwright Page Object for the Chat page (route: /chat)."""

    _CHAT_INPUT_SELECTOR = "[data-testid='chat-input'], textarea, input[type='text']"
    _SEND_BUTTON_SELECTOR = "[data-testid='send-button'], button[type='submit'], button"
    _MESSAGE_SELECTOR = "[data-testid='chat-message'], .chat-message, .message"
    _CITATION_SELECTOR = "[data-testid='citation'], .citation-card, .citation"
    _LOADING_SELECTOR = "[data-testid='loading'], .loading, .spinner"

    def __init__(self, page: Page, base_url: str, timeout: int = 30000) -> None:
        """Initialise ChatPage."""
        super().__init__(page, base_url, "/chat", timeout)

    async def is_loaded_async(self) -> bool:
        """Check if chat input is ready.

        Returns:
            bool: True if chat input is visible.
        """
        try:
            await self.page.wait_for_selector(
                self._CHAT_INPUT_SELECTOR, timeout=self.timeout
            )
            return True
        except Exception:
            return False

    async def send_message(self, message: str) -> None:
        """Type a message and click send.

        Args:
            message: The chat question to send.
        """
        await self.page.fill(self._CHAT_INPUT_SELECTOR, message)
        await self.page.click(self._SEND_BUTTON_SELECTOR)

    async def wait_for_response(self, timeout: int = 60000) -> bool:
        """Wait for a bot response message to appear.

        Args:
            timeout: Maximum wait time in milliseconds.

        Returns:
            bool: True if a response appeared.
        """
        try:
            await self.page.wait_for_selector(
                self._MESSAGE_SELECTOR, timeout=timeout
            )
            return True
        except Exception:
            return False

    async def get_messages(self) -> List[str]:
        """Get all chat message texts.

        Returns:
            List[str]: All visible message text contents.
        """
        elements = await self.page.query_selector_all(self._MESSAGE_SELECTOR)
        messages = []
        for el in elements:
            text = await el.text_content()
            if text:
                messages.append(text.strip())
        return messages

    async def get_latest_response(self) -> Optional[str]:
        """Get the most recent bot response.

        Returns:
            Optional[str]: Latest message text, or None if empty.
        """
        messages = await self.get_messages()
        return messages[-1] if messages else None

    async def get_citation_count(self) -> int:
        """Count citation cards in the latest response.

        Returns:
            int: Number of citation elements visible.
        """
        citations = await self.page.query_selector_all(self._CITATION_SELECTOR)
        return len(citations)
