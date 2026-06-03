"""RAG evaluation harness for ViFinNER.

* :func:`load_eval_dataset` — read the bundled JSONL eval set.
* :class:`RAGEvaluator` — runs the chatbot against every item and
  computes retrieval / keyword / latency / refusal metrics.
* :class:`EvalReport` — aggregate report logged to MLflow.
"""

from src.rag.evaluation.dataset import EvalItem, load_eval_dataset
from src.rag.evaluation.metrics import (
    ItemResult,
    aggregate_metrics,
    score_item,
)
from src.rag.evaluation.runner import EvalReport, RAGEvaluator

__all__ = [
    "EvalItem",
    "EvalReport",
    "ItemResult",
    "RAGEvaluator",
    "aggregate_metrics",
    "load_eval_dataset",
    "score_item",
]
