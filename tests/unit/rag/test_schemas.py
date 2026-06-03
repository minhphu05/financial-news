"""Unit tests for src/rag/api/schemas.py.

Tests Pydantic request/response model validation, serialisation,
and constraint enforcement.
"""

import pytest
from pydantic import ValidationError


class TestChatRequest:
    """Tests for the ChatRequest Pydantic model."""

    def test_valid_minimal(self):
        """Test creating ChatRequest with only required field."""
        from src.rag.api.schemas import ChatRequest

        req = ChatRequest(question="FPT doanh thu quý I?")
        assert req.question == "FPT doanh thu quý I?"
        assert req.model is None
        assert req.top_k is None

    def test_valid_full(self):
        """Test creating ChatRequest with all optional fields."""
        from src.rag.api.schemas import ChatRequest

        req = ChatRequest(
            question="FPT lợi nhuận?",
            model="anthropic/claude-3.5-sonnet",
            top_k=10,
            score_threshold=0.7,
            filters={"ticker_symbol": "FPT"},
        )
        assert req.model == "anthropic/claude-3.5-sonnet"
        assert req.top_k == 10
        assert req.score_threshold == 0.7
        assert req.filters == {"ticker_symbol": "FPT"}

    def test_empty_question_rejected(self):
        """Test that empty question string is rejected."""
        from src.rag.api.schemas import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(question="")

    def test_top_k_bounds(self):
        """Test that top_k must be between 1 and 20."""
        from src.rag.api.schemas import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(question="test", top_k=0)

        with pytest.raises(ValidationError):
            ChatRequest(question="test", top_k=21)

    def test_score_threshold_bounds(self):
        """Test that score_threshold must be between 0.0 and 1.0."""
        from src.rag.api.schemas import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(question="test", score_threshold=-0.1)

        with pytest.raises(ValidationError):
            ChatRequest(question="test", score_threshold=1.5)

    def test_valid_score_threshold_boundaries(self):
        """Test that exact boundaries 0.0 and 1.0 are accepted."""
        from src.rag.api.schemas import ChatRequest

        req0 = ChatRequest(question="test", score_threshold=0.0)
        assert req0.score_threshold == 0.0

        req1 = ChatRequest(question="test", score_threshold=1.0)
        assert req1.score_threshold == 1.0


class TestChatResponse:
    """Tests for the ChatResponse Pydantic model."""

    def test_minimal_response(self):
        """Test creating response with required answer only."""
        from src.rag.api.schemas import ChatResponse

        resp = ChatResponse(answer="FPT đạt 15 tỷ.")
        assert resp.answer == "FPT đạt 15 tỷ."
        assert resp.citations == []
        assert resp.cache_hit is False

    def test_full_response(self):
        """Test creating response with all optional fields."""
        from src.rag.api.schemas import ChatResponse, Citation

        citation = Citation(
            index=1,
            score=0.92,
            article_link="https://cafef.vn/fpt-123.chn",
            title="FPT kỷ lục",
        )
        resp = ChatResponse(
            answer="FPT kỷ lục",
            citations=[citation],
            model="claude-3.5-sonnet",
            cache_hit=True,
            cache_score=0.98,
            latency_ms=450.5,
        )
        assert resp.cache_hit is True
        assert resp.cache_score == 0.98
        assert len(resp.citations) == 1


class TestCitation:
    """Tests for the Citation Pydantic model."""

    def test_valid_citation(self):
        """Test creating a valid citation."""
        from src.rag.api.schemas import Citation

        c = Citation(
            index=1,
            score=0.92,
            article_link="https://cafef.vn/fpt-123.chn",
            title="FPT kỷ lục",
            post_date="28-05-2026",
            ticker_symbol="FPT",
        )
        assert c.index == 1
        assert c.score == 0.92
        assert c.ticker_symbol == "FPT"

    def test_optional_fields_default_none(self):
        """Test that optional fields default to None."""
        from src.rag.api.schemas import Citation

        c = Citation(index=1, score=0.5, article_link="https://example.com")
        assert c.title is None
        assert c.post_date is None
        assert c.ticker_symbol is None


class TestHealthResponse:
    """Tests for the HealthResponse model."""

    def test_valid_health(self):
        """Test creating a valid health response."""
        from src.rag.api.schemas import HealthResponse

        h = HealthResponse(
            mongo_raw=1000,
            mongo_clean=800,
            mongo_embedded=750,
            qdrant_chunks=5000,
        )
        assert h.status == "ok"
        assert h.mongo_raw == 1000
        assert h.qdrant_chunks == 5000


class TestStockOut:
    """Tests for the StockOut model."""

    def test_valid_stock(self):
        """Test creating a valid stock entry."""
        from src.rag.api.schemas import StockOut

        stock = StockOut(
            ticker="FPT",
            name_vi="Công ty Cổ phần FPT",
            name_en="FPT Corporation",
            sector="Công nghệ",
            article_count=42,
        )
        assert stock.ticker == "FPT"
        assert stock.article_count == 42


class TestNewsArticleOut:
    """Tests for the NewsArticleOut model."""

    def test_valid_article(self):
        """Test creating a valid news article output."""
        from src.rag.api.schemas import NewsArticleOut

        article = NewsArticleOut(
            link="https://cafef.vn/fpt-123.chn",
            title="FPT kỷ lục",
            post_date="28-05-2026",
            summary="FPT đạt doanh thu kỷ lục",
            ticker_symbol="FPT",
            char_count=500,
        )
        assert article.link == "https://cafef.vn/fpt-123.chn"
        assert article.char_count == 500

    def test_minimal_article(self):
        """Test creating article with only required link field."""
        from src.rag.api.schemas import NewsArticleOut

        article = NewsArticleOut(link="https://cafef.vn/min-1.chn")
        assert article.title is None
        assert article.ticker_symbol is None


class TestModelsResponse:
    """Tests for the ModelsResponse model."""

    def test_valid_models(self):
        """Test creating a valid models response."""
        from src.rag.api.schemas import ModelsResponse

        resp = ModelsResponse(
            models=["claude-3.5-sonnet", "gemini-2.0-flash"],
            default="claude-3.5-sonnet",
        )
        assert len(resp.models) == 2
        assert resp.default == "claude-3.5-sonnet"


class TestNewsListResponse:
    """Tests for the NewsListResponse pagination model."""

    def test_valid_paginated_response(self):
        """Test creating a paginated news list."""
        from src.rag.api.schemas import NewsListResponse, NewsArticleOut

        items = [
            NewsArticleOut(link=f"https://cafef.vn/article-{i}.chn")
            for i in range(3)
        ]
        resp = NewsListResponse(items=items, total=100, skip=0, limit=10)
        assert resp.total == 100
        assert len(resp.items) == 3
        assert resp.skip == 0
        assert resp.limit == 10
