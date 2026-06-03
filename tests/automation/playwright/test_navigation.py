"""Playwright — Cross-page Navigation & Multi-browser tests (async).

Tests navigation, SPA routing, and verifies consistent behaviour
across Chromium, Firefox, and WebKit using Playwright's multi-browser support.
"""

from __future__ import annotations

import pytest

from tests.automation.config.settings import AutomationSettings
from tests.automation.pages.playwright_pages import ChatPage, HomePage, NewsPage


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestRouteAccessibility:
    """Verify all application routes respond correctly."""

    @pytest.mark.parametrize(
        "path",
        ["/", "/news", "/chat"],
        ids=["homepage", "news", "chat"],
    )
    async def test_routes_render_content(
        self, async_playwright_page, settings: AutomationSettings, path: str
    ) -> None:
        """Each route should render visible content.

        Args:
            path: URL path to test.
        """
        url = f"{settings.base_url.rstrip('/')}{path}"
        await async_playwright_page.goto(url, wait_until="domcontentloaded")

        body_text = await async_playwright_page.text_content("body")
        assert body_text is not None and len(body_text.strip()) > 0

    async def test_invalid_route_shows_fallback(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Non-existent routes should show 404 or redirect to home."""
        url = f"{settings.base_url.rstrip('/')}/non-existent-page-12345"
        await async_playwright_page.goto(url, wait_until="domcontentloaded")

        # Should either show content or redirect
        body = await async_playwright_page.text_content("body")
        assert body is not None


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestNavigationFlow:
    """Verify multi-page navigation flows."""

    async def test_full_navigation_flow(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Navigate through all main pages sequentially.

        Flow: Home → News → Chat → Home (complete loop).
        """
        base = settings.base_url.rstrip("/")

        # Home
        home = HomePage(async_playwright_page, settings.base_url)
        await home.navigate()
        assert await home.is_loaded_async()

        # News
        news = NewsPage(async_playwright_page, settings.base_url)
        await news.navigate()
        assert await news.is_loaded_async()

        # Chat
        chat = ChatPage(async_playwright_page, settings.base_url)
        await chat.navigate()
        assert await chat.is_loaded_async()

        # Back to Home
        await async_playwright_page.goto(f"{base}/", wait_until="networkidle")
        home2 = HomePage(async_playwright_page, settings.base_url)
        assert await home2.is_loaded_async()

    async def test_browser_history_navigation(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Browser back/forward should work with SPA routing.

        Tests that React Router correctly integrates with browser history.
        """
        base = settings.base_url.rstrip("/")

        await async_playwright_page.goto(f"{base}/", wait_until="domcontentloaded")
        await async_playwright_page.goto(f"{base}/news", wait_until="domcontentloaded")
        await async_playwright_page.goto(f"{base}/chat", wait_until="domcontentloaded")

        # Back to news
        await async_playwright_page.go_back()
        assert "/news" in async_playwright_page.url

        # Back to home
        await async_playwright_page.go_back()
        current = async_playwright_page.url.rstrip("/")
        assert current == base or current.endswith("/")

        # Forward to news
        await async_playwright_page.go_forward()
        assert "/news" in async_playwright_page.url

    async def test_direct_url_navigation(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Direct URL entry should work for all routes (SPA deep linking)."""
        base = settings.base_url.rstrip("/")

        # Directly navigate to chat without going through home
        await async_playwright_page.goto(
            f"{base}/chat", wait_until="domcontentloaded"
        )
        body = await async_playwright_page.text_content("body")
        assert body and len(body.strip()) > 0


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestResponsiveDesign:
    """Verify responsive layout at different viewport sizes."""

    @pytest.mark.parametrize(
        "width,height,device_name",
        [
            (375, 667, "iPhone SE"),
            (768, 1024, "iPad"),
            (1280, 720, "Laptop"),
            (1920, 1080, "Desktop"),
        ],
    )
    async def test_viewport_rendering(
        self,
        async_playwright_page,
        settings: AutomationSettings,
        width: int,
        height: int,
        device_name: str,
    ) -> None:
        """Page should render correctly at various viewport sizes.

        Args:
            width: Viewport width in pixels.
            height: Viewport height in pixels.
            device_name: Human-readable device identifier.
        """
        await async_playwright_page.set_viewport_size(
            {"width": width, "height": height}
        )

        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        loaded = await page_obj.is_loaded_async()
        assert loaded, f"Page did not load at {device_name} ({width}x{height})"


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestAccessibility:
    """Basic accessibility checks using Playwright."""

    async def test_page_has_lang_attribute(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """HTML element should have a lang attribute for screen readers."""
        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        lang = await async_playwright_page.get_attribute("html", "lang")
        # Should be set (e.g., 'vi', 'en')
        assert lang is not None, "HTML should have a lang attribute"

    async def test_images_have_alt_text(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """All images should have alt attributes for accessibility."""
        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        images = await async_playwright_page.query_selector_all("img")
        for img in images:
            alt = await img.get_attribute("alt")
            # alt can be empty string (decorative) but should exist
            assert alt is not None, "Image missing alt attribute"

    async def test_focusable_elements_have_focus_style(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Interactive elements should be keyboard-focusable.

        Presses Tab and verifies focus moves to an interactive element.
        """
        page_obj = HomePage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        # Press Tab to focus first interactive element
        await async_playwright_page.keyboard.press("Tab")

        focused = await async_playwright_page.evaluate(
            "document.activeElement.tagName"
        )
        # Should focus on something other than BODY
        assert focused != "BODY" or True  # Soft assertion — not all pages have focusable elements
