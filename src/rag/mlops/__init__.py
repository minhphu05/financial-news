"""MLOps / LLMOps integration — MLflow tracking for ViFinNER.

* :class:`MLflowTracker` — generic wrapper that handles experiment +
  run lifecycle and degrades gracefully when MLflow is not installed.
* :class:`NERMlflowCallback` — minimal callback you can plug into a
  training loop to log per-epoch metrics.
"""

from src.rag.mlops.tracker import MLflowTracker, NERMlflowCallback

__all__ = ["MLflowTracker", "NERMlflowCallback"]
