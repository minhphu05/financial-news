"""Prefect flow: run the RAG evaluation harness and log to MLflow."""

from __future__ import annotations

from typing import Any, Dict, Optional

from prefect import flow, get_run_logger, task

from src.rag.agent import FinanceRAGChatbot, OpenRouterLLM
from src.rag.databases import QdrantRepository
from src.rag.evaluation import RAGEvaluator
from src.rag.ingestion import VoyageAIEmbedder
from src.rag.retrieval import Retriever


@task
def evaluate_rag_task(run_name: Optional[str]) -> Dict[str, Any]:
    """Build a chatbot and run the eval dataset against it."""
    logger = get_run_logger()
    with QdrantRepository() as qdrant:
        embedder = VoyageAIEmbedder()
        chatbot = FinanceRAGChatbot(
            retriever=Retriever(embedder=embedder, qdrant=qdrant),
            llm=OpenRouterLLM(),
        )
        evaluator = RAGEvaluator(chatbot=chatbot)
        report = evaluator.run(run_name=run_name)

    logger.info("RAG eval metrics: %s", report.metrics)
    return report.as_dict()


@flow(name="vifinner-rag-eval", log_prints=True)
def rag_eval_flow(run_name: Optional[str] = None) -> Dict[str, Any]:
    """Evaluate the current RAG configuration.

    Parameters
    ----------
    run_name : Optional[str]
        MLflow run name (defaults to a UTC timestamp).

    Returns
    -------
    dict
        Serialised :class:`EvalReport`.
    """
    return evaluate_rag_task(run_name=run_name)
