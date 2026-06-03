"""Ask the LangChain RAG chatbot from the command line.

Usage::

    python scripts/ask_langchain.py "Lãi suất ACB tháng này thế nào?"
    python scripts/ask_langchain.py "Tin về FPT?" --ticker FPT
"""

from __future__ import annotations

import argparse
import sys

from src.rag_langchain import LangChainRAGChatbot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask the LangChain RAG chatbot.")
    parser.add_argument("question", nargs="+", help="User question (positional).")
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Optional ticker filter (e.g. ACB, FPT, BCM).",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    if not args.question:
        print("Usage: python scripts/ask_langchain.py 'your question'")
        sys.exit(1)

    question = " ".join(args.question)
    filters = {"ticker_symbol": args.ticker.upper()} if args.ticker else None

    bot = LangChainRAGChatbot()
    response = bot.ask(question, filters=filters)

    print("\n=== ANSWER ===")
    print(response.answer)
    print(f"\n(latency: {response.latency_ms:.1f} ms, sources: {len(response.citations)})")
    print("\n=== CITATIONS ===")
    for c in response.citations:
        print(
            f"[{c['index']}] {c.get('title') or '(no title)'} — "
            f"{c.get('ticker_symbol') or '-'} — {c.get('article_link')}"
        )


if __name__ == "__main__":
    main()
