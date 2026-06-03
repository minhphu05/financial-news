"""Page Object Model (POM) — Base page class for automation tests.

All page objects inherit from BasePage, which encapsulates common
interactions (navigation, waiting, screenshots) and provides a
consistent interface for both Selenium and Playwright tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class BasePage(ABC):
    """Abstract base page providing the shared interface.

    Subclasses implement Selenium or Playwright-specific logic.
    This allows tests to be written against a stable API regardless
    of the underlying automation library.

    Attributes:
        base_url: The frontend application base URL.
        path: The page-specific route path (e.g., "/news").
    """

    def __init__(self, base_url: str, path: str = "/") -> None:
        """Initialise the base page.

        Args:
            base_url: Root URL of the frontend application.
            path: Path component for this page.
        """
        self.base_url = base_url.rstrip("/")
        self.path = path

    @property
    def url(self) -> str:
        """Full URL for this page.

        Returns:
            str: base_url + path concatenation.
        """
        return f"{self.base_url}{self.path}"

    @abstractmethod
    def navigate(self) -> None:
        """Navigate the browser to this page."""
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check whether the page has fully loaded.

        Returns:
            bool: True if page-specific content is visible.
        """
        ...

    @abstractmethod
    def get_title(self) -> str:
        """Return the page document title.

        Returns:
            str: The <title> tag content.
        """
        ...

    @abstractmethod
    def take_screenshot(self, name: str) -> Optional[str]:
        """Capture a screenshot of the current page state.

        Args:
            name: Descriptive filename for the screenshot.

        Returns:
            Optional[str]: Path to the saved screenshot file.
        """
        ...
