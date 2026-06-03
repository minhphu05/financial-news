"""Run the RAG evaluation harness from the command line.

Usage::

    python scripts/run_eval.py                         # use bundled dataset
    python scripts/run_eval.py --run-name baseline-v1  # custom MLflow name
"""

from __future__ import annotations

import argparse
import json

from src.rag.agent import FinanceRAGChatbot, GeminiLLM
from src.rag.databases import PgVectorRepository
from src.rag.evaluation import RAGEvaluator
from src.rag.ingestion import GeminiEmbedder
from src.rag.retrieval import Retriever


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ViFinNER RAG eval suite.")
    parser.add_argument(
        "--run-name",
        type=str,
        default=None,
        help="MLflow run name (default: rag-eval-<unix-ts>).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = _parse_args()
    with PgVectorRepository() as pg:
        embedder = GeminiEmbedder()
        chatbot = FinanceRAGChatbot(
            retriever=Retriever(embedder=embedder, pgvector=pg),
            llm=GeminiLLM(),
        )
        evaluator = RAGEvaluator(chatbot=chatbot)
        report = evaluator.run(run_name=args.run_name)

    print(json.dumps(report.metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
