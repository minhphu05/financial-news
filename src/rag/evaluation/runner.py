"""Evaluation runner — executes the eval dataset and logs to MLflow."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from src.rag.agent import FinanceRAGChatbot
from src.rag.config import Settings, get_settings
from src.rag.evaluation.dataset import EvalItem, load_eval_dataset
from src.rag.evaluation.metrics import (
    ItemResult,
    aggregate_metrics,
    score_item,
)
from src.rag.mlops import MLflowTracker
from src.rag.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class EvalReport:
    """Aggregate report returned by :class:`RAGEvaluator.run`."""

    metrics: Dict[str, float]
    per_item: List[ItemResult]
    run_id: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def mark_done(self) -> None:
        """Stamp ``finished_at`` with UTC now."""
        self.finished_at = datetime.now(timezone.utc)

    def as_dict(self) -> Dict[str, Any]:
        """JSON-serialisable view of the report."""
        return {
            "metrics": self.metrics,
            "per_item": [asdict(r) for r in self.per_item],
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
class RAGEvaluator:
    """Run the RAG eval set against a :class:`FinanceRAGChatbot`.

    Parameters
    ----------
    chatbot : FinanceRAGChatbot
        Bot under test.
    settings : Optional[Settings]
        Settings override.
    tracker : Optional[MLflowTracker]
        Override the default tracker (for tests).
    """

    def __init__(
        self,
        chatbot: FinanceRAGChatbot,
        settings: Optional[Settings] = None,
        tracker: Optional[MLflowTracker] = None,
    ) -> None:
        self._chatbot = chatbot
        self._settings = settings or get_settings()
        self._tracker = tracker or MLflowTracker(
            experiment=self._settings.mlflow.experiment_rag,
            settings=self._settings,
        )

    # -- public API --------------------------------------------------------
    def run(
        self,
        items: Optional[Sequence[EvalItem]] = None,
        run_name: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> EvalReport:
        """Execute the evaluation.

        Parameters
        ----------
        items : Optional[Sequence[EvalItem]]
            Custom item set. Defaults to :func:`load_eval_dataset`.
        run_name : Optional[str]
            MLflow run name (defaults to a UTC timestamp).
        tags : Optional[dict]
            Extra MLflow tags.

        Returns
        -------
        EvalReport
            Aggregate results.
        """
        items = list(items) if items is not None else load_eval_dataset()
        run_name = run_name or f"rag-eval-{int(time.time())}"

        per_item: List[ItemResult] = []
        with self._tracker.start_run(run_name=run_name, tags=tags or {}) as run:
            run.log_params(
                {
                    "chat_model": self._settings.gemini.chat_model,
                    "embedding_model": self._settings.gemini.embedding_model,
                    "top_k": self._settings.retrieval.top_k,
                    "score_threshold": self._settings.retrieval.score_threshold,
                    "items": len(items),
                }
            )
            for idx, item in enumerate(items):
                result = self._score_one(item)
                per_item.append(result)

                run.log_metrics(
                    {
                        "keyword_recall": result.keyword_recall,
                        "ticker_recall": (
                            result.ticker_recall if result.ticker_recall is not None else -1.0
                        ),
                        "latency_ms": result.latency_ms,
                    },
                    step=idx,
                )

            metrics = aggregate_metrics(per_item)
            run.log_metrics(metrics)
            run.log_dict(
                {
                    "metrics": metrics,
                    "per_item": [asdict(r) for r in per_item],
                },
                name="rag_eval_report.json",
            )
            report = EvalReport(metrics=metrics, per_item=per_item)
            report.mark_done()
            return report

    # -- internals ---------------------------------------------------------
    def _score_one(self, item: EvalItem) -> ItemResult:
        """Run the chatbot on one item and score the response."""
        started = time.monotonic()
        try:
            response = self._chatbot.ask(question=item.question)
            answer = response.answer
            citations = list(response.citations)
            error: Optional[str] = None
        except Exception as exc:  # noqa: BLE001
            logger.exception("RAG eval failed for %s: %s", item.id, exc)
            answer = ""
            citations = []
            error = str(exc)

        latency_ms = (time.monotonic() - started) * 1000
        return score_item(
            item=item,
            answer=answer,
            citations=citations,
            latency_ms=latency_ms,
            cache_hit=False,
            error=error,
        )
