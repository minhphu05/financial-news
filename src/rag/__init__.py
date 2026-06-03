"""ViFinNER RAG system package.

This package implements the end-to-end Retrieval-Augmented Generation (RAG)
stack on top of the existing ViFinNER project:

* ``config``     - Pydantic-based settings loaded from environment variables.
* ``databases``  - MongoDB (raw store) and PGVector (vector store) clients.
* ``ingestion``  - Daily scraping, text cleaning, chunking, and embedding.
* ``retrieval``  - Semantic search over PGVector.
* ``agent``      - Gemini-powered RAG chatbot.
* ``flows``      - Prefect orchestration flows and deployments.
* ``api``        - FastAPI HTTP layer exposing the chatbot.
* ``utils``      - Logging and shared helpers.
"""

from src.rag.config.settings import get_settings  # noqa: F401

__all__ = ["get_settings"]
