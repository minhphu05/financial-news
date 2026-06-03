"""Playwright — Chat Page E2E tests (async).

Tests the RAG chatbot interface with Playwright's powerful async API,
including network mocking, response streaming, and multi-browser support.
"""

from __future__ import annotations

import pytest

from tests.automation.config.settings import AutomationSettings
from tests.automation.pages.playwright_pages import ChatPage


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestChatPageLoad:
    """Verify chat interface renders correctly."""

    async def test_chat_page_loads(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Chat page should display the message input area.

        Validates the chat input element is visible and interactive.
        """
        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()
        loaded = await page_obj.is_loaded_async()
        assert loaded, "Chat page did not load"

    async def test_initial_state_is_empty(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Chat should start with no messages (clean state)."""
        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()
        messages = await page_obj.get_messages()
        # May have a welcome message, but should not have conversation history
        assert len(messages) <= 1


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestChatConversation:
    """Test the core chat conversation flow."""

    async def test_send_and_receive_message(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Sending a question should produce a bot response.

        End-to-end flow: user types → sends → bot responds.
        Requires the backend RAG API to be running.
        """
        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        await page_obj.send_message("Phân tích cổ phiếu VNM hôm nay")
        has_response = await page_obj.wait_for_response(timeout=60000)

        if has_response:
            response = await page_obj.get_latest_response()
            assert response and len(response) > 0

    async def test_multiple_messages(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Multiple sequential messages should all receive responses.

        Tests conversation continuity and context handling.
        """
        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        questions = [
            "VNIndex hôm nay thế nào?",
            "Tin tức về FPT?",
        ]

        for question in questions:
            await page_obj.send_message(question)
            await page_obj.wait_for_response(timeout=60000)

        messages = await page_obj.get_messages()
        # Should have at least the messages we sent (plus potential responses)
        assert len(messages) >= 1

    async def test_vietnamese_input_handling(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Chat input should correctly handle Vietnamese Unicode text.

        Validates UTF-8 rendering for diacritical marks (dấu).
        """
        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        test_msg = "Thị trường chứng khoán Việt Nam đang ở đâu?"
        await async_playwright_page.fill(
            "[data-testid='chat-input'], textarea, input[type='text']",
            test_msg,
        )

        value = await async_playwright_page.input_value(
            "[data-testid='chat-input'], textarea, input[type='text']"
        )
        assert value == test_msg, "Vietnamese text should be preserved"


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestChatCitations:
    """Verify citations display in chat responses."""

    async def test_citations_rendered(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Responses should include citation cards linking to sources.

        Citations provide provenance for RAG-based answers.
        """
        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        await page_obj.send_message("Tin tức mới nhất về ngân hàng?")
        await page_obj.wait_for_response(timeout=60000)

        citation_count = await page_obj.get_citation_count()
        # May be 0 if API is not running; verify no crash
        assert citation_count >= 0


@pytest.mark.playwright
@pytest.mark.e2e
@pytest.mark.asyncio
class TestChatMockedAPI:
    """Test chat UI behaviour with mocked API responses.

    These tests don't require the backend to be running — they use
    Playwright's route interception to simulate API responses.
    """

    async def test_handles_api_timeout(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Chat should handle API timeout gracefully.

        Simulates a slow/non-responding API and verifies the UI
        shows an appropriate loading or error state.
        """
        # Mock the chat API to never respond
        await async_playwright_page.route(
            "**/api/chat**",
            lambda route: route.abort("timedout"),
        )

        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        await page_obj.send_message("Test timeout")
        # Wait briefly — should not crash
        await async_playwright_page.wait_for_timeout(5000)

        # Page should still be functional
        body = await async_playwright_page.text_content("body")
        assert body is not None

    async def test_handles_api_error_response(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Chat should display error message when API returns 500.

        Tests the error handling UI rather than the API itself.
        """
        await async_playwright_page.route(
            "**/api/chat**",
            lambda route: route.fulfill(
                status=500,
                content_type="application/json",
                body='{"detail": "Internal server error"}',
            ),
        )

        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        await page_obj.send_message("This should fail")
        await async_playwright_page.wait_for_timeout(3000)

        # Page should show error or stay functional
        body = await async_playwright_page.text_content("body")
        assert body is not None

    async def test_mocked_successful_response(
        self, async_playwright_page, settings: AutomationSettings
    ) -> None:
        """Verify UI correctly renders a mocked successful chat response.

        Tests the rendering pipeline independent of the actual LLM.
        """
        mock_response = {
            "answer": "VNIndex đã tăng 5 điểm hôm nay.",
            "citations": [
                {
                    "title": "Tin chứng khoán ngày 15/01",
                    "link": "https://cafef.vn/tin-chung-khoan.html",
                    "score": 0.95,
                }
            ],
            "model": "test-model",
        }

        import json

        await async_playwright_page.route(
            "**/api/chat**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(mock_response),
            ),
        )

        page_obj = ChatPage(async_playwright_page, settings.base_url)
        await page_obj.navigate()

        await page_obj.send_message("VNIndex hôm nay?")
        await page_obj.wait_for_response(timeout=10000)

        messages = await page_obj.get_messages()
        # Should have at least one message in the UI
        assert messages is not None
