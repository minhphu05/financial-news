"""Interactive CLI to query the ViFinNER RAG chatbot.

Usage::

    python scripts/ask.py "Lãi suất ACB tháng này như thế nào?"
"""

from __future__ import annotations

import sys

from src.rag.agent import FinanceRAGChatbot, GeminiLLM
from src.rag.databases import PgVectorRepository
from src.rag.ingestion import GeminiEmbedder
from src.rag.retrieval import Retriever


def main() -> None:
    """Entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/ask.py 'your question here'")
        sys.exit(1)

    question = " ".join(sys.argv[1:])

    with PgVectorRepository() as pg:
        embedder = GeminiEmbedder()
        retriever = Retriever(embedder=embedder, pgvector=pg)
        llm = GeminiLLM()
        bot = FinanceRAGChatbot(retriever=retriever, llm=llm)

        response = bot.ask(question)

    print("\n=== ANSWER ===")
    print(response.answer)
    print("\n=== CITATIONS ===")
    for c in response.citations:
        print(f"[{c['index']}] ({c['score']:.3f}) {c.get('title')} — {c['article_link']}")


if __name__ == "__main__":
    main()
