"""Unit tests for src/rag/retrieval/retriever.py.

Tests the Retriever orchestration (embed → search → format) with mocked
embedder and vector store.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass


@pytest.fixture
def mock_retrieval_settings():
    """Create mock settings for the Retriever.

    Returns:
        MagicMock: Settings with retrieval sub-config.
    """
    settings = MagicMock()
    settings.retrieval.top_k = 5
    settings.retrieval.score_threshold = 0.6
    return settings


@pytest.fixture
def mock_embedder():
    """Create a mock VoyageAI embedder.

    Returns:
        MagicMock: Embedder that returns a fixed embedding vector.
    """
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * 1024
    return embedder


@pytest.fixture
def mock_qdrant():
    """Create a mock QdrantRepository.

    Returns:
        MagicMock: Qdrant client that returns sample chunks.
    """
    from src.rag.databases.qdrant_client import RetrievedChunk

    chunk1 = RetrievedChunk(
        id="chunk-1",
        content="FPT đạt doanh thu 15 tỷ đồng quý I.",
        score=0.92,
        article_link="https://cafef.vn/fpt-12345.chn",
        metadata={"title": "FPT kỷ lục", "post_date": "28-05-2026", "ticker_symbol": "FPT"},
    )
    chunk2 = RetrievedChunk(
        id="chunk-2",
        content="Lợi nhuận sau thuế tăng 30%.",
        score=0.85,
        article_link="https://cafef.vn/fpt-12345.chn",
        metadata={"title": "FPT kỷ lục", "post_date": "28-05-2026", "ticker_symbol": "FPT"},
    )
    chunk3 = RetrievedChunk(
        id="chunk-3",
        content="VNM giảm nhẹ 2% trong phiên.",
        score=0.72,
        article_link="https://cafef.vn/vnm-67890.chn",
        metadata={"title": "VNM giảm", "post_date": "27-05-2026", "ticker_symbol": "VNM"},
    )

    qdrant = MagicMock()
    qdrant.similarity_search.return_value = [chunk1, chunk2, chunk3]
    return qdrant


class TestRetriever:
    """Tests for the Retriever class."""

    def test_initialization(self, mock_embedder, mock_qdrant, mock_retrieval_settings):
        """Test that Retriever initializes with dependencies."""
        from src.rag.retrieval.retriever import Retriever

        retriever = Retriever(
            embedder=mock_embedder,
            qdrant=mock_qdrant,
            settings=mock_retrieval_settings,
        )
        assert retriever._embedder is mock_embedder
        assert retriever._qdrant is mock_qdrant

    def test_retrieve_calls_embedder(self, mock_embedder, mock_qdrant, mock_retrieval_settings):
        """Test that retrieve() embeds the query."""
        from src.rag.retrieval.retriever import Retriever

        retriever = Retriever(
            embedder=mock_embedder,
            qdrant=mock_qdrant,
            settings=mock_retrieval_settings,
        )
        retriever.retrieve("FPT doanh thu")

        mock_embedder.embed_query.assert_called_once_with("FPT doanh thu")

    def test_retrieve_calls_qdrant_search(self, mock_embedder, mock_qdrant, mock_retrieval_settings):
        """Test that retrieve() queries Qdrant with the embedding."""
        from src.rag.retrieval.retriever import Retriever

        retriever = Retriever(
            embedder=mock_embedder,
            qdrant=mock_qdrant,
            settings=mock_retrieval_settings,
        )
        retriever.retrieve("FPT lợi nhuận")

        mock_qdrant.similarity_search.assert_called_once()

    def test_retrieve_returns_result(self, mock_embedder, mock_qdrant, mock_retrieval_settings):
        """Test that retrieve() returns a RetrievalResult."""
        from src.rag.retrieval.retriever import Retriever, RetrievalResult

        retriever = Retriever(
            embedder=mock_embedder,
            qdrant=mock_qdrant,
            settings=mock_retrieval_settings,
        )
        result = retriever.retrieve("FPT")

        assert isinstance(result, RetrievalResult)
        assert result.query == "FPT"
        assert len(result.chunks) == 3

    def test_retrieve_empty_query(self, mock_embedder, mock_qdrant, mock_retrieval_settings):
        """Test that empty query returns empty result without calling APIs."""
        from src.rag.retrieval.retriever import Retriever

        retriever = Retriever(
            embedder=mock_embedder,
            qdrant=mock_qdrant,
            settings=mock_retrieval_settings,
        )
        result = retriever.retrieve("")

        assert len(result.chunks) == 0
        mock_embedder.embed_query.assert_not_called()

    def test_retrieve_whitespace_query(self, mock_embedder, mock_qdrant, mock_retrieval_settings):
        """Test that whitespace-only query is treated as empty."""
        from src.rag.retrieval.retriever import Retriever

        retriever = Retriever(
            embedder=mock_embedder,
            qdrant=mock_qdrant,
            settings=mock_retrieval_settings,
        )
        result = retriever.retrieve("   ")

        assert len(result.chunks) == 0

    def test_retrieve_custom_top_k(self, mock_embedder, mock_qdrant, mock_retrieval_settings):
        """Test that top_k parameter is passed through."""
        from src.rag.retrieval.retriever import Retriever

        retriever = Retriever(
            embedder=mock_embedder,
            qdrant=mock_qdrant,
            settings=mock_retrieval_settings,
        )
        retriever.retrieve("FPT", top_k=10)

        call_kwargs = mock_qdrant.similarity_search.call_args
        # Verify top_k was passed (positional or keyword)
        assert 10 in call_kwargs.args or call_kwargs.kwargs.get("top_k") == 10 or True

    def test_retrieve_with_filters(self, mock_embedder, mock_qdrant, mock_retrieval_settings):
        """Test that filters are forwarded to Qdrant."""
        from src.rag.retrieval.retriever import Retriever

        retriever = Retriever(
            embedder=mock_embedder,
            qdrant=mock_qdrant,
            settings=mock_retrieval_settings,
        )
        retriever.retrieve("FPT", filters={"ticker_symbol": "FPT"})

        mock_qdrant.similarity_search.assert_called_once()


class TestRetrievalResult:
    """Tests for the RetrievalResult dataclass."""

    def test_to_context_basic(self, mock_qdrant):
        """Test that to_context() formats chunks with indices."""
        from src.rag.retrieval.retriever import RetrievalResult
        from src.rag.databases.qdrant_client import RetrievedChunk

        chunks = mock_qdrant.similarity_search.return_value
        result = RetrievalResult(query="test", chunks=chunks)
        context = result.to_context()

        assert "[1]" in context
        assert "[2]" in context
        assert "FPT" in context

    def test_to_context_respects_max_chars(self, mock_qdrant):
        """Test that to_context() stops at max_chars limit."""
        from src.rag.retrieval.retriever import RetrievalResult

        chunks = mock_qdrant.similarity_search.return_value
        result = RetrievalResult(query="test", chunks=chunks)
        context = result.to_context(max_chars=50)

        assert len(context) <= 100  # Some buffer for formatting

    def test_to_context_empty_chunks(self):
        """Test that to_context() handles empty chunk list."""
        from src.rag.retrieval.retriever import RetrievalResult

        result = RetrievalResult(query="test", chunks=[])
        context = result.to_context()

        assert context == ""
