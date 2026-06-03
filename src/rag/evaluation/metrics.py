"""Per-item and aggregate metrics for RAG evaluation."""

from __future__ import annotations

import statistics
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from src.rag.evaluation.dataset import EvalItem

_REFUSAL_MARKERS = (
    "không tìm thấy",
    "không có thông tin",
    "tôi không thể",
    "không đủ thông tin",
    "no information",
    "i don't have",
)


# ---------------------------------------------------------------------------
# Per-item result
# ---------------------------------------------------------------------------
@dataclass
class ItemResult:
    """Scoring for a single :class:`EvalItem`.

    Attributes
    ----------
    item_id : str
        Id of the corresponding :class:`EvalItem`.
    answer : str
        Generated answer.
    retrieved_tickers : list[str]
        Tickers extracted from citations (case-normalised).
    keyword_recall : float
        Fraction of ``expected_keywords`` found in the answer.
    ticker_recall : Optional[float]
        Fraction of ``expected_tickers`` matched by retrieved tickers, or
        ``None`` if the item has no expected tickers.
    refused : bool
        ``True`` when the answer matches a known refusal marker.
    latency_ms : float
        End-to-end latency in milliseconds.
    cache_hit : bool
        Whether the response came from the semantic cache.
    error : Optional[str]
        Exception message, if any.
    citations : list[dict]
        Raw citation entries returned by the chatbot.
    """

    item_id: str
    answer: str
    retrieved_tickers: List[str] = field(default_factory=list)
    keyword_recall: float = 0.0
    ticker_recall: Optional[float] = None
    refused: bool = False
    latency_ms: float = 0.0
    cache_hit: bool = False
    error: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _normalise(text: str) -> str:
    """Lowercase + NFC-normalise a string for keyword search."""
    return unicodedata.normalize("NFC", text or "").casefold()


def score_item(
    item: EvalItem,
    answer: str,
    citations: List[Dict[str, Any]],
    latency_ms: float,
    cache_hit: bool = False,
    error: Optional[str] = None,
) -> ItemResult:
    """Score a single chatbot answer.

    Parameters
    ----------
    item : EvalItem
        Reference question.
    answer : str
        Generated answer.
    citations : list[dict]
        Citation payload from the chatbot.
    latency_ms : float
        Wall-clock latency.
    cache_hit : bool
        Whether the answer came from the semantic cache.
    error : Optional[str]
        Exception text when the chatbot failed.
    """
    norm_answer = _normalise(answer)
    answer_words = norm_answer  # plain substring search is enough here

    keyword_recall = 0.0
    if item.expected_keywords:
        hits = sum(1 for kw in item.expected_keywords if _normalise(kw) in answer_words)
        keyword_recall = hits / len(item.expected_keywords)

    retrieved_tickers = [
        str(c.get("ticker_symbol") or "").upper()
        for c in citations
        if c.get("ticker_symbol")
    ]
    retrieved_tickers = [t for t in retrieved_tickers if t]

    ticker_recall: Optional[float] = None
    if item.expected_tickers:
        expected = {t.upper() for t in item.expected_tickers}
        hit = expected.intersection(retrieved_tickers)
        ticker_recall = len(hit) / len(expected) if expected else None

    refused = any(marker in norm_answer for marker in _REFUSAL_MARKERS)

    return ItemResult(
        item_id=item.id,
        answer=answer,
        retrieved_tickers=retrieved_tickers,
        keyword_recall=keyword_recall,
        ticker_recall=ticker_recall,
        refused=refused,
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        error=error,
        citations=citations,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def aggregate_metrics(results: Iterable[ItemResult]) -> Dict[str, float]:
    """Compute aggregate stats across a list of :class:`ItemResult`.

    Returns a dict containing:

    * ``items`` — total scored items.
    * ``errors`` — count of items that raised an exception.
    * ``keyword_recall_mean`` — mean keyword recall.
    * ``ticker_recall_mean`` — mean retrieval recall (only over items
      that have expected tickers).
    * ``refusal_rate`` — fraction of items that hit a refusal marker.
    * ``cache_hit_rate`` — fraction served from cache.
    * ``latency_p50_ms`` / ``latency_p95_ms`` — latency percentiles.
    """
    results = list(results)
    if not results:
        return {
            "items": 0,
            "errors": 0,
            "keyword_recall_mean": 0.0,
            "ticker_recall_mean": 0.0,
            "refusal_rate": 0.0,
            "cache_hit_rate": 0.0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
        }

    keyword = [r.keyword_recall for r in results]
    ticker = [r.ticker_recall for r in results if r.ticker_recall is not None]
    refusals = sum(1 for r in results if r.refused)
    cache_hits = sum(1 for r in results if r.cache_hit)
    latencies = sorted(r.latency_ms for r in results)
    errors = sum(1 for r in results if r.error)

    return {
        "items": len(results),
        "errors": errors,
        "keyword_recall_mean": statistics.fmean(keyword) if keyword else 0.0,
        "ticker_recall_mean": statistics.fmean(ticker) if ticker else 0.0,
        "refusal_rate": refusals / len(results),
        "cache_hit_rate": cache_hits / len(results),
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }


def _percentile(values: List[float], p: float) -> float:
    """Linear-interpolated percentile from a pre-sorted list."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    rank = p * (len(values) - 1)
    low = int(rank)
    high = min(low + 1, len(values) - 1)
    weight = rank - low
    return values[low] + (values[high] - values[low]) * weight
