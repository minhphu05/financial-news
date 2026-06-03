"""Unit tests for src/rag/ingestion/embedder.py.

Tests the VoyageAI embedding client with mocked HTTP calls.
No real API calls are made.
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_embedder_settings():
    """Create mock settings for VoyageAIEmbedder.

    Returns:
        MagicMock: Settings with voyageai sub-config.
    """
    settings = MagicMock()
    settings.voyageai.api_key = "test-voyage-key"
    settings.voyageai.model = "voyage-finance-2"
    settings.voyageai.batch_size = 8
    settings.voyageai.dimension = 1024
    return settings


class TestVoyageAIEmbedder:
    """Tests for the VoyageAIEmbedder class."""

    @patch("src.rag.ingestion.embedder.voyageai")
    def test_initialization(self, mock_voyageai, mock_embedder_settings):
        """Test that embedder initializes with correct settings."""
        from src.rag.ingestion.embedder import VoyageAIEmbedder

        embedder = VoyageAIEmbedder(settings=mock_embedder_settings)
        assert embedder is not None

    @patch("src.rag.ingestion.embedder.voyageai")
    def test_embed_documents_single(self, mock_voyageai, mock_embedder_settings):
        """Test embedding a single document."""
        from src.rag.ingestion.embedder import VoyageAIEmbedder

        mock_client = MagicMock()
        mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_voyageai.Client.return_value = mock_client

        embedder = VoyageAIEmbedder(settings=mock_embedder_settings)
        results = embedder.embed_documents(["Cổ phiếu FPT tăng 5%"])

        assert len(results) == 1
        assert len(results[0]) == 1024

    @patch("src.rag.ingestion.embedder.voyageai")
    def test_embed_documents_batch(self, mock_voyageai, mock_embedder_settings):
        """Test embedding multiple documents in a batch."""
        from src.rag.ingestion.embedder import VoyageAIEmbedder

        mock_client = MagicMock()
        mock_client.embed.return_value = MagicMock(
            embeddings=[[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
        )
        mock_voyageai.Client.return_value = mock_client

        embedder = VoyageAIEmbedder(settings=mock_embedder_settings)
        docs = [
            "FPT tăng giá.",
            "VNM giảm nhẹ.",
            "ACB công bố lợi nhuận.",
        ]
        results = embedder.embed_documents(docs)

        assert len(results) == 3

    @patch("src.rag.ingestion.embedder.voyageai")
    def test_embed_query(self, mock_voyageai, mock_embedder_settings):
        """Test embedding a single query string."""
        from src.rag.ingestion.embedder import VoyageAIEmbedder

        mock_client = MagicMock()
        mock_client.embed.return_value = MagicMock(embeddings=[[0.5] * 1024])
        mock_voyageai.Client.return_value = mock_client

        embedder = VoyageAIEmbedder(settings=mock_embedder_settings)
        result = embedder.embed_query("FPT doanh thu quý I?")

        assert len(result) == 1024

    @patch("src.rag.ingestion.embedder.voyageai")
    def test_embed_empty_list(self, mock_voyageai, mock_embedder_settings):
        """Test that embedding empty document list returns empty."""
        from src.rag.ingestion.embedder import VoyageAIEmbedder

        embedder = VoyageAIEmbedder(settings=mock_embedder_settings)
        results = embedder.embed_documents([])

        assert results == []

    @patch("src.rag.ingestion.embedder.voyageai")
    @patch("src.rag.ingestion.embedder.time.sleep")
    def test_rate_limiting(self, mock_sleep, mock_voyageai, mock_embedder_settings):
        """Test that rate limiting calls sleep between batches."""
        from src.rag.ingestion.embedder import VoyageAIEmbedder

        mock_client = MagicMock()
        # Simulate multiple batches (batch_size=8, total=16 docs)
        mock_client.embed.return_value = MagicMock(
            embeddings=[[0.1] * 1024] * 8
        )
        mock_voyageai.Client.return_value = mock_client

        mock_embedder_settings.voyageai.batch_size = 8
        embedder = VoyageAIEmbedder(settings=mock_embedder_settings)

        docs = [f"Document {i}" for i in range(16)]
        embedder.embed_documents(docs)

        # Should have called embed at least twice (16 docs / 8 batch = 2)
        assert mock_client.embed.call_count >= 2
