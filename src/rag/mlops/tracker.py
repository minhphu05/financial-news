"""MLflow wrapper used across ViFinNER (DL training + RAG evaluation).

The tracker is intentionally lightweight:

* It uses MLflow's standard fluent API (``mlflow.set_experiment`` etc.).
* It works against any tracking backend (``file:./mlruns``, SQLite, or
  the bundled Docker server).
* It degrades gracefully when MLflow can't be reached — runs continue
  but logging is skipped with a warning. That way, the medallion
  pipeline or the eval runner never fails just because the tracking
  server is down.
"""

from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)

try:  # MLflow is optional at import time so tests don't need it installed.
    import mlflow  # type: ignore
    from mlflow.tracking import MlflowClient  # type: ignore

    _MLFLOW_AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    logger.warning("MLflow is not available (%s); tracking calls will no-op.", exc)
    mlflow = None  # type: ignore[assignment]
    MlflowClient = None  # type: ignore[assignment]
    _MLFLOW_AVAILABLE = False


class MLflowTracker:
    """Convenience wrapper around the fluent MLflow API.

    Parameters
    ----------
    experiment : str
        Name of the MLflow experiment (created if missing).
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.
    """

    def __init__(
        self,
        experiment: str,
        settings: Optional[Settings] = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._experiment = experiment
        self._enabled = _MLFLOW_AVAILABLE
        if self._enabled:
            try:
                mlflow.set_tracking_uri(self._settings.mlflow.tracking_uri)
                mlflow.set_experiment(experiment)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Disabling MLflow tracker (%s).", exc)
                self._enabled = False

    @property
    def enabled(self) -> bool:
        """Whether the tracker is wired to a working MLflow backend."""
        return self._enabled

    # -- run lifecycle -----------------------------------------------------
    @contextmanager
    def start_run(
        self,
        run_name: Optional[str] = None,
        tags: Optional[Mapping[str, str]] = None,
    ) -> Iterator["MLflowRun"]:
        """Start an MLflow run as a context manager.

        Yields a :class:`MLflowRun` that exposes :meth:`log_metrics`,
        :meth:`log_params`, :meth:`log_artifact_json` etc. When MLflow is
        disabled the context manager still yields a working stub so
        callers don't have to branch.
        """
        if not self._enabled:
            yield _NullRun()
            return

        try:
            with mlflow.start_run(run_name=run_name, tags=dict(tags or {})):
                yield _ActiveRun()
        except Exception as exc:  # noqa: BLE001
            logger.warning("MLflow run failed (%s); continuing without tracking.", exc)
            yield _NullRun()


# ---------------------------------------------------------------------------
# Active vs Null runs
# ---------------------------------------------------------------------------
class MLflowRun:
    """Interface implemented by both real and stubbed runs."""

    def log_params(self, params: Mapping[str, Any]) -> None:  # pragma: no cover - abstract
        ...

    def log_metrics(
        self,
        metrics: Mapping[str, float],
        step: Optional[int] = None,
    ) -> None:  # pragma: no cover - abstract
        ...

    def log_dict(self, data: Mapping[str, Any], name: str) -> None:  # pragma: no cover
        ...

    def log_tags(self, tags: Mapping[str, str]) -> None:  # pragma: no cover
        ...


class _ActiveRun(MLflowRun):
    """Real MLflow run. Delegates everything to the fluent API."""

    def log_params(self, params: Mapping[str, Any]) -> None:
        """Persist hyperparameters / configuration entries."""
        if not params:
            return
        mlflow.log_params({k: _stringify(v) for k, v in params.items()})

    def log_metrics(
        self,
        metrics: Mapping[str, float],
        step: Optional[int] = None,
    ) -> None:
        """Persist numerical metrics; non-numeric values are skipped."""
        numeric = {
            k: float(v)
            for k, v in metrics.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        if not numeric:
            return
        mlflow.log_metrics(numeric, step=step)

    def log_dict(self, data: Mapping[str, Any], name: str) -> None:
        """Persist a JSON-serialisable dict as a run artifact."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            mlflow.log_artifact(str(path))

    def log_tags(self, tags: Mapping[str, str]) -> None:
        """Attach key/value tags to the active run."""
        if not tags:
            return
        mlflow.set_tags(dict(tags))


class _NullRun(MLflowRun):
    """No-op stub used when MLflow is disabled."""

    def log_params(self, params: Mapping[str, Any]) -> None:  # noqa: D401
        """Drop the call silently."""
        return None

    def log_metrics(self, metrics: Mapping[str, float], step: Optional[int] = None) -> None:
        """Drop the call silently."""
        return None

    def log_dict(self, data: Mapping[str, Any], name: str) -> None:
        """Drop the call silently."""
        return None

    def log_tags(self, tags: Mapping[str, str]) -> None:
        """Drop the call silently."""
        return None


# ---------------------------------------------------------------------------
# NER training callback
# ---------------------------------------------------------------------------
class NERMlflowCallback:
    """Minimal callback to instrument an NER training loop.

    Example
    -------
    >>> tracker = MLflowTracker("vifinner-ner")
    >>> with tracker.start_run(run_name="bilstm_crf_v1") as run:
    ...     callback = NERMlflowCallback(run)
    ...     callback.on_train_start(params={"lr": 1e-3, "epochs": 5})
    ...     for epoch in range(5):
    ...         callback.on_epoch_end(epoch, train_loss=..., val_f1=...)
    ...     callback.on_train_end(test_metrics={"f1": 0.81})
    """

    def __init__(self, run: MLflowRun) -> None:
        self._run = run

    def on_train_start(
        self,
        params: Mapping[str, Any],
        tags: Optional[Mapping[str, str]] = None,
    ) -> None:
        """Log hyperparameters + tags at the start of training."""
        self._run.log_params(params)
        if tags:
            self._run.log_tags(tags)

    def on_epoch_end(
        self,
        epoch: int,
        train_loss: Optional[float] = None,
        val_loss: Optional[float] = None,
        val_f1: Optional[float] = None,
        **extra: float,
    ) -> None:
        """Log per-epoch training/validation metrics."""
        metrics: Dict[str, float] = {}
        if train_loss is not None:
            metrics["train_loss"] = float(train_loss)
        if val_loss is not None:
            metrics["val_loss"] = float(val_loss)
        if val_f1 is not None:
            metrics["val_f1"] = float(val_f1)
        for key, value in extra.items():
            if value is not None:
                metrics[key] = float(value)
        self._run.log_metrics(metrics, step=epoch)

    def on_train_end(
        self,
        test_metrics: Optional[Mapping[str, float]] = None,
        artifacts: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> None:
        """Log final test metrics + arbitrary artefacts."""
        if test_metrics:
            self._run.log_metrics(dict(test_metrics))
        for name, blob in (artifacts or {}).items():
            self._run.log_dict(blob, name)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _stringify(value: Any) -> str:
    """Render a Python value as a string for MLflow's param store."""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(value)
