"""FastAPI HTTP layer exposing the ViFinNER RAG chatbot."""

from src.rag.api.server import create_app

__all__ = ["create_app"]
