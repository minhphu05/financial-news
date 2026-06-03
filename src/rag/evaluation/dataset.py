"""Loader for the JSONL evaluation dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "eval" / "rag_eval.jsonl"


@dataclass
class EvalItem:
    """One question in the evaluation set.

    Attributes
    ----------
    id : str
        Stable identifier (``vif-XXX``).
    question : str
        User question in Vietnamese.
    expected_keywords : list[str]
        Keywords expected in a good answer.
    expected_tickers : list[str]
        Tickers expected among the retrieved citations.
    category : str
        Coarse-grained topic tag.
    difficulty : str
        ``easy`` / ``medium`` / ``hard``.
    """

    id: str
    question: str
    expected_keywords: List[str] = field(default_factory=list)
    expected_tickers: List[str] = field(default_factory=list)
    category: str = "general"
    difficulty: str = "medium"

    @classmethod
    def from_json(cls, data: dict) -> "EvalItem":
        """Hydrate from a JSON line."""
        return cls(
            id=str(data["id"]),
            question=str(data["question"]),
            expected_keywords=list(data.get("expected_keywords", [])),
            expected_tickers=[t.upper() for t in data.get("expected_tickers", [])],
            category=str(data.get("category", "general")),
            difficulty=str(data.get("difficulty", "medium")),
        )


def load_eval_dataset(path: Optional[Path] = None) -> List[EvalItem]:
    """Load the JSONL eval dataset from disk.

    Parameters
    ----------
    path : Optional[Path]
        Override the default ``data/eval/rag_eval.jsonl`` location.

    Returns
    -------
    list[EvalItem]
        Parsed items.
    """
    target = Path(path) if path else _DEFAULT_PATH
    if not target.exists():
        raise FileNotFoundError(f"Eval dataset not found at {target}")

    items: List[EvalItem] = []
    with target.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                items.append(EvalItem.from_json(json.loads(raw)))
            except (json.JSONDecodeError, KeyError) as exc:
                raise ValueError(
                    f"Failed to parse {target}:{line_no} — {exc}"
                ) from exc
    return items
