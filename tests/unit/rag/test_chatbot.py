"""Unit tests for src/rag/agent/chatbot.py.

Tests the FinanceRAGChatbot orchestration logic with mocked retriever and LLM.
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_chatbot_settings():
    """Create mock settings for FinanceRAGChatbot.

    Returns:
        MagicMock: Settings with openrouter sub-config.
    """
    settings = MagicMock()
    settings.openrouter.default_model = "anthropic/claude-3.5-sonnet"
    settings.retrieval.top_k = 5
    settings.retrieval.score_threshold = 0.6
    return settings


@pytest.fixture
def mock_retriever():
    """Create a mock Retriever.

    Returns:
        MagicMock: Retriever that returns a sample RetrievalResult.
    """
    from src.rag.databases.qdrant_client import RetrievedChunk
    from src.rag.retrieval.retriever import RetrievalResult

    chunks = [
        RetrievedChunk(
            id="c1",
            content="FPT đạt doanh thu 15 tỷ đồng.",
            score=0.92,
            article_link="https://cafef.vn/fpt-123.chn",
            metadata={"title": "FPT kỷ lục", "post_date": "28-05-2026", "ticker_symbol": "FPT"},
        ),
        RetrievedChunk(
            id="c2",
            content="Lợi nhuận tăng 30% so với cùng kỳ.",
            score=0.85,
            article_link="https://cafef.vn/fpt-123.chn",
            metadata={"title": "FPT kỷ lục", "post_date": "28-05-2026", "ticker_symbol": "FPT"},
        ),
        RetrievedChunk(
            id="c3",
            content="VNM giảm 2% trong phiên sáng.",
            score=0.72,
            article_link="https://cafef.vn/vnm-456.chn",
            metadata={"title": "VNM giảm", "post_date": "27-05-2026", "ticker_symbol": "VNM"},
        ),
    ]
    result = RetrievalResult(query="FPT doanh thu", chunks=chunks)

    retriever = MagicMock()
    retriever.retrieve.return_value = result
    return retriever


@pytest.fixture
def mock_llm():
    """Create a mock OpenRouterLLM.

    Returns:
        MagicMock: LLM that returns a predefined answer.
    """
    llm = MagicMock()
    llm.generate.return_value = (
        "FPT đạt doanh thu 15 tỷ đồng trong quý I/2026, "
        "tăng 25% so với cùng kỳ năm trước [1]."
    )
    return llm


class TestFinanceRAGChatbot:
    """Tests for FinanceRAGChatbot.ask()."""

    def test_ask_returns_chat_response(
        self, mock_retriever, mock_llm, mock_chatbot_settings
    ):
        """Test that ask() returns a ChatResponse with expected fields."""
        from src.rag.agent.chatbot import ChatResponse, FinanceRAGChatbot

        chatbot = FinanceRAGChatbot(
            retriever=mock_retriever,
            llm=mock_llm,
            settings=mock_chatbot_settings,
        )
        response = chatbot.ask("FPT doanh thu quý I?")

        assert isinstance(response, ChatResponse)
        assert len(response.answer) > 0
        assert "FPT" in response.answer

    def test_ask_calls_retriever(
        self, mock_retriever, mock_llm, mock_chatbot_settings
    ):
        """Test that ask() invokes the retriever with the question."""
        from src.rag.agent.chatbot import FinanceRAGChatbot

        chatbot = FinanceRAGChatbot(
            retriever=mock_retriever,
            llm=mock_llm,
            settings=mock_chatbot_settings,
        )
        chatbot.ask("VNM lợi nhuận?")

        mock_retriever.retrieve.assert_called_once()
        call_kwargs = mock_retriever.retrieve.call_args
        assert "VNM lợi nhuận?" in str(call_kwargs)

    def test_ask_calls_llm_generate(
        self, mock_retriever, mock_llm, mock_chatbot_settings
    ):
        """Test that ask() calls LLM.generate with system + user prompts."""
        from src.rag.agent.chatbot import FinanceRAGChatbot

        chatbot = FinanceRAGChatbot(
            retriever=mock_retriever,
            llm=mock_llm,
            settings=mock_chatbot_settings,
        )
        chatbot.ask("FPT tin tức mới nhất")

        mock_llm.generate.assert_called_once()
        call_kwargs = mock_llm.generate.call_args
        # Should pass system_prompt and user_prompt
        assert "system_prompt" in call_kwargs.kwargs or len(call_kwargs.args) >= 1

    def test_ask_uses_default_model(
        self, mock_retriever, mock_llm, mock_chatbot_settings
    ):
        """Test that ask() uses default model when none specified."""
        from src.rag.agent.chatbot import FinanceRAGChatbot

        chatbot = FinanceRAGChatbot(
            retriever=mock_retriever,
            llm=mock_llm,
            settings=mock_chatbot_settings,
        )
        response = chatbot.ask("FPT?")

        assert response.model == "anthropic/claude-3.5-sonnet"

    def test_ask_uses_custom_model(
        self, mock_retriever, mock_llm, mock_chatbot_settings
    ):
        """Test that ask() passes custom model to LLM."""
        from src.rag.agent.chatbot import FinanceRAGChatbot

        chatbot = FinanceRAGChatbot(
            retriever=mock_retriever,
            llm=mock_llm,
            settings=mock_chatbot_settings,
        )
        response = chatbot.ask("FPT?", model="google/gemini-2.0-flash")

        assert response.model == "google/gemini-2.0-flash"

    def test_citations_are_deduplicated(
        self, mock_retriever, mock_llm, mock_chatbot_settings
    ):
        """Test that duplicate articles produce only one citation each."""
        from src.rag.agent.chatbot import FinanceRAGChatbot

        chatbot = FinanceRAGChatbot(
            retriever=mock_retriever,
            llm=mock_llm,
            settings=mock_chatbot_settings,
        )
        response = chatbot.ask("FPT?")

        # 3 chunks but 2 unique articles (FPT has 2 chunks)
        assert len(response.citations) == 2

    def test_citations_sequential_indexing(
        self, mock_retriever, mock_llm, mock_chatbot_settings
    ):
        """Test that deduplicated citations are re-indexed from 1."""
        from src.rag.agent.chatbot import FinanceRAGChatbot

        chatbot = FinanceRAGChatbot(
            retriever=mock_retriever,
            llm=mock_llm,
            settings=mock_chatbot_settings,
        )
        response = chatbot.ask("FPT?")

        indices = [c["index"] for c in response.citations]
        assert indices == [1, 2]

    def test_answer_is_stripped(
        self, mock_retriever, mock_llm, mock_chatbot_settings
    ):
        """Test that LLM output whitespace is stripped."""
        from src.rag.agent.chatbot import FinanceRAGChatbot

        mock_llm.generate.return_value = "  Answer with spaces  \n"

        chatbot = FinanceRAGChatbot(
            retriever=mock_retriever,
            llm=mock_llm,
            settings=mock_chatbot_settings,
        )
        response = chatbot.ask("Test")

        assert not response.answer.startswith(" ")
        assert not response.answer.endswith("\n")


class TestDeduplicateCitations:
    """Tests for FinanceRAGChatbot._deduplicate_citations() static method."""

    def test_empty_chunks(self):
        """Test deduplication of empty chunk list."""
        from src.rag.agent.chatbot import FinanceRAGChatbot

        result = FinanceRAGChatbot._deduplicate_citations([])
        assert result == []

    def test_single_chunk(self):
        """Test deduplication with a single chunk."""
        from src.rag.agent.chatbot import FinanceRAGChatbot
        from src.rag.databases.qdrant_client import RetrievedChunk

        chunks = [
            RetrievedChunk(
                id="c1",
                content="Content",
                score=0.9,
                article_link="https://cafef.vn/a-1.chn",
                metadata={"title": "A", "post_date": "01-01-2026", "ticker_symbol": "X"},
            )
        ]
        result = FinanceRAGChatbot._deduplicate_citations(chunks)

        assert len(result) == 1
        assert result[0]["index"] == 1
        assert result[0]["article_link"] == "https://cafef.vn/a-1.chn"

    def test_keeps_highest_score_for_duplicate(self):
        """Test that when same article has multiple chunks, highest score wins."""
        from src.rag.agent.chatbot import FinanceRAGChatbot
        from src.rag.databases.qdrant_client import RetrievedChunk

        chunks = [
            RetrievedChunk(
                id="c1",
                content="Low score",
                score=0.7,
                article_link="https://cafef.vn/same-1.chn",
                metadata={"title": "Same", "post_date": "01-01-2026", "ticker_symbol": "X"},
            ),
            RetrievedChunk(
                id="c2",
                content="High score",
                score=0.95,
                article_link="https://cafef.vn/same-1.chn",
                metadata={"title": "Same", "post_date": "01-01-2026", "ticker_symbol": "X"},
            ),
        ]
        result = FinanceRAGChatbot._deduplicate_citations(chunks)

        assert len(result) == 1
        assert result[0]["score"] == 0.95
