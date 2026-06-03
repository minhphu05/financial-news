"""Selenium Page Objects — concrete page implementations.

Each class maps to a frontend route and exposes high-level actions
that test scripts can call without knowing CSS selectors or DOM structure.
"""

from __future__ import annotations

import os
from typing import List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.automation.pages import BasePage


class SeleniumBasePage(BasePage):
    """Selenium-specific base page with WebDriver interactions.

    Attributes:
        driver: Selenium WebDriver instance.
        wait: WebDriverWait configured with the page timeout.
    """

    def __init__(
        self,
        driver: WebDriver,
        base_url: str,
        path: str = "/",
        timeout: int = 30,
    ) -> None:
        """Initialise with a Selenium WebDriver.

        Args:
            driver: Active Selenium WebDriver.
            base_url: Frontend application base URL.
            path: Route path for this page.
            timeout: Maximum wait time in seconds for element visibility.
        """
        super().__init__(base_url, path)
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    def navigate(self) -> None:
        """Navigate the browser to this page's URL."""
        self.driver.get(self.url)

    def get_title(self) -> str:
        """Return the browser document title.

        Returns:
            str: Current page title.
        """
        return self.driver.title

    def take_screenshot(self, name: str) -> Optional[str]:
        """Save a screenshot to the configured directory.

        Args:
            name: Base filename (without extension).

        Returns:
            Optional[str]: Full path to the saved PNG file.
        """
        screenshot_dir = os.getenv("TEST_SCREENSHOT_DIR", "tests/automation/screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        filepath = os.path.join(screenshot_dir, f"{name}.png")
        self.driver.save_screenshot(filepath)
        return filepath

    def wait_for_element(self, by: By, value: str, timeout: Optional[int] = None):
        """Wait for an element to become visible.

        Args:
            by: Selenium locator strategy (By.CSS_SELECTOR, By.ID, etc.).
            value: Locator value string.
            timeout: Override the default wait timeout.

        Returns:
            WebElement: The found element.
        """
        wait = WebDriverWait(self.driver, timeout) if timeout else self.wait
        return wait.until(EC.visibility_of_element_located((by, value)))

    def wait_for_elements(self, by: By, value: str, timeout: Optional[int] = None):
        """Wait for multiple elements to be present.

        Args:
            by: Selenium locator strategy.
            value: Locator value string.
            timeout: Override the default wait timeout.

        Returns:
            List[WebElement]: All matching elements.
        """
        wait = WebDriverWait(self.driver, timeout) if timeout else self.wait
        return wait.until(EC.presence_of_all_elements_located((by, value)))


class HomePage(SeleniumBasePage):
    """Page Object for the Home page (route: /)."""

    # Selectors — centralised for easy maintenance
    _HEADER_SELECTOR = "header"
    _STOCK_GRID_SELECTOR = "[data-testid='stock-grid'], .stock-grid, main"
    _SEARCH_INPUT_SELECTOR = "input[type='search'], input[placeholder*='search'], input[placeholder*='Tìm']"

    def __init__(self, driver: WebDriver, base_url: str, timeout: int = 30) -> None:
        """Initialise HomePage."""
        super().__init__(driver, base_url, "/", timeout)

    def is_loaded(self) -> bool:
        """Check if the home page has loaded by verifying header is visible.

        Returns:
            bool: True if page header is rendered.
        """
        try:
            self.wait_for_element(By.CSS_SELECTOR, self._HEADER_SELECTOR)
            return True
        except Exception:
            return False

    def get_stock_cards(self) -> List:
        """Get all stock cards displayed on the page.

        Returns:
            List[WebElement]: Stock card elements.
        """
        try:
            return self.wait_for_elements(
                By.CSS_SELECTOR, self._STOCK_GRID_SELECTOR
            )
        except Exception:
            return []

    def search(self, query: str) -> None:
        """Enter a search query if search input is available.

        Args:
            query: Text to enter in the search field.
        """
        try:
            search_input = self.wait_for_element(
                By.CSS_SELECTOR, self._SEARCH_INPUT_SELECTOR, timeout=5
            )
            search_input.clear()
            search_input.send_keys(query)
        except Exception:
            pass


class NewsPage(SeleniumBasePage):
    """Page Object for the News page (route: /news)."""

    _NEWS_LIST_SELECTOR = "[data-testid='news-list'], .news-list, main"
    _NEWS_CARD_SELECTOR = "[data-testid='news-card'], .news-card, article"
    _PAGINATION_SELECTOR = "[data-testid='pagination'], .pagination, nav"

    def __init__(self, driver: WebDriver, base_url: str, timeout: int = 30) -> None:
        """Initialise NewsPage."""
        super().__init__(driver, base_url, "/news", timeout)

    def is_loaded(self) -> bool:
        """Check if news list is visible.

        Returns:
            bool: True if news content has rendered.
        """
        try:
            self.wait_for_element(By.CSS_SELECTOR, self._NEWS_LIST_SELECTOR)
            return True
        except Exception:
            return False

    def get_news_cards(self) -> List:
        """Get all news article cards.

        Returns:
            List[WebElement]: News card elements.
        """
        try:
            return self.wait_for_elements(By.CSS_SELECTOR, self._NEWS_CARD_SELECTOR)
        except Exception:
            return []

    def get_article_titles(self) -> List[str]:
        """Extract text from all visible article titles.

        Returns:
            List[str]: List of article title strings.
        """
        cards = self.get_news_cards()
        titles = []
        for card in cards:
            try:
                title_el = card.find_element(By.CSS_SELECTOR, "h2, h3, .title")
                titles.append(title_el.text)
            except Exception:
                continue
        return titles


class StockNewsPage(SeleniumBasePage):
    """Page Object for the Stock-specific News page (route: /news/:ticker)."""

    _TICKER_HEADER_SELECTOR = "[data-testid='ticker-header'], .ticker-header, h1, h2"
    _ARTICLE_LIST_SELECTOR = "[data-testid='article-list'], .article-list, main"

    def __init__(
        self, driver: WebDriver, base_url: str, ticker: str, timeout: int = 30
    ) -> None:
        """Initialise StockNewsPage for a specific ticker.

        Args:
            driver: Selenium WebDriver.
            base_url: Frontend base URL.
            ticker: Stock ticker symbol (e.g., "FPT").
            timeout: Wait timeout.
        """
        super().__init__(driver, base_url, f"/news/{ticker}", timeout)
        self.ticker = ticker

    def is_loaded(self) -> bool:
        """Check if the stock-specific page has loaded.

        Returns:
            bool: True if ticker header is visible.
        """
        try:
            self.wait_for_element(By.CSS_SELECTOR, self._TICKER_HEADER_SELECTOR)
            return True
        except Exception:
            return False

    def get_ticker_name(self) -> str:
        """Get the displayed ticker name/symbol.

        Returns:
            str: Text content of the ticker header.
        """
        element = self.wait_for_element(By.CSS_SELECTOR, self._TICKER_HEADER_SELECTOR)
        return element.text


class ChatPage(SeleniumBasePage):
    """Page Object for the Chat page (route: /chat)."""

    _CHAT_INPUT_SELECTOR = "[data-testid='chat-input'], textarea, input[type='text']"
    _SEND_BUTTON_SELECTOR = "[data-testid='send-button'], button[type='submit'], button"
    _MESSAGE_SELECTOR = "[data-testid='chat-message'], .chat-message, .message"
    _CITATION_SELECTOR = "[data-testid='citation'], .citation-card, .citation"

    def __init__(self, driver: WebDriver, base_url: str, timeout: int = 30) -> None:
        """Initialise ChatPage."""
        super().__init__(driver, base_url, "/chat", timeout)

    def is_loaded(self) -> bool:
        """Check if chat interface is ready.

        Returns:
            bool: True if chat input is visible.
        """
        try:
            self.wait_for_element(By.CSS_SELECTOR, self._CHAT_INPUT_SELECTOR)
            return True
        except Exception:
            return False

    def send_message(self, message: str) -> None:
        """Type and send a chat message.

        Args:
            message: The question text to send.
        """
        input_el = self.wait_for_element(By.CSS_SELECTOR, self._CHAT_INPUT_SELECTOR)
        input_el.clear()
        input_el.send_keys(message)

        send_btn = self.wait_for_element(By.CSS_SELECTOR, self._SEND_BUTTON_SELECTOR)
        send_btn.click()

    def get_messages(self) -> List[str]:
        """Get all visible chat messages.

        Returns:
            List[str]: Text content of each message bubble.
        """
        try:
            elements = self.wait_for_elements(
                By.CSS_SELECTOR, self._MESSAGE_SELECTOR, timeout=60
            )
            return [el.text for el in elements]
        except Exception:
            return []

    def get_citations(self) -> List:
        """Get citation cards from the latest response.

        Returns:
            List[WebElement]: Citation card elements.
        """
        try:
            return self.wait_for_elements(
                By.CSS_SELECTOR, self._CITATION_SELECTOR, timeout=10
            )
        except Exception:
            return []

    def wait_for_response(self, timeout: int = 60) -> bool:
        """Wait for a bot response to appear.

        Args:
            timeout: Maximum wait time in seconds.

        Returns:
            bool: True if a response appeared within timeout.
        """
        try:
            self.wait_for_element(
                By.CSS_SELECTOR, self._MESSAGE_SELECTOR, timeout=timeout
            )
            return True
        except Exception:
            return False
