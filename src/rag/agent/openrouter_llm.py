"""OpenRouter LLM client.

Wraps the OpenAI-compatible OpenRouter API using the ``openai`` SDK so
that any model available on OpenRouter can be used for chat completions
without changing application code.

Available models (as of mid-2026)
----------------------------------
* ``nvidia/nemotron-3-super-120b-a12b:free``
* ``poolside/laguna-m.1:free``
* ``openai/gpt-oss-120b:free``
* ``google/gemma-4-31b-it:free``
* ``deepseek/deepseek-v4-flash:free``

The list is configured in ``settings.openrouter.available_models`` so new
models can be added without touching application code. Callers choose the
model per-request; the default falls back to
``settings.openrouter.default_model``.

Security
--------
Model IDs provided by users are always validated against the allowlist in
``settings.openrouter.available_models`` to prevent prompt-injection via
crafted model names.
"""

from __future__ import annotations

from typing import ClassVar, List, Optional

from openai import OpenAI

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)


class OpenRouterLLM:
    """Chat-completion client backed by OpenRouter.

    The client is configured once at construction time. Individual
    :meth:`generate` calls may override the model, temperature, and token
    budget on a per-request basis.

    Parameters
    ----------
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.
    """

    # Class-level constant so callers can read the list without constructing
    # the client (e.g. for API documentation / validation).
    AVAILABLE_MODELS: ClassVar[List[str]] = [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "poolside/laguna-m.1:free",
        "openai/gpt-oss-120b:free",
        "google/gemma-4-31b-it:free",
        "deepseek/deepseek-v4-flash:free",
    ]

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        cfg = self._settings.openrouter
        api_key = cfg.api_key.get_secret_value()
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is empty. "
                "Set it in the environment or in `.env`."
            )
        # OpenRouter is fully OpenAI-compatible — we just point the SDK at a
        # different base_url.
        self._client = OpenAI(
            api_key=api_key,
            base_url=cfg.base_url,
        )
        self._default_model = cfg.default_model
        self._allowed_models = set(cfg.available_models)
        self._temperature = cfg.temperature
        self._max_tokens = cfg.max_tokens

    # -- public API ---------------------------------------------------------
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Call the OpenRouter chat-completion endpoint and return generated text.

        Parameters
        ----------
        system_prompt : str
            System message sent as the first turn.
        user_prompt : str
            User message (the RAG-augmented question + context).
        model : Optional[str]
            OpenRouter model identifier. When ``None``, falls back to
            ``settings.openrouter.default_model``.
            Value is validated against ``settings.openrouter.available_models``;
            an unknown ID raises :class:`ValueError`.
        temperature : Optional[float]
            Sampling temperature. Overrides the settings default when provided.
        max_tokens : Optional[int]
            Maximum tokens in the completion. Overrides the settings default.

        Returns
        -------
        str
            Generated text. Empty string when the model returns no content.

        Raises
        ------
        ValueError
            If ``model`` is not in the allowed models list.
        """
        resolved_model = self._resolve_model(model)
        resolved_temp = temperature if temperature is not None else self._temperature
        resolved_tokens = max_tokens if max_tokens is not None else self._max_tokens

        logger.debug(
            "OpenRouter request | model=%s | temp=%.2f | max_tokens=%d",
            resolved_model,
            resolved_temp,
            resolved_tokens,
        )

        response = self._client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=resolved_temp,
            max_tokens=resolved_tokens,
        )

        text: str = ""
        if response.choices:
            text = response.choices[0].message.content or ""

        logger.debug(
            "OpenRouter response | model=%s | tokens_used=%s",
            resolved_model,
            getattr(response.usage, "total_tokens", "n/a"),
        )
        return text.strip()

    def available_models(self) -> List[str]:
        """Return the list of models the user may choose from.

        Returns
        -------
        list[str]
            Sorted list of allowed model identifiers.
        """
        return sorted(self._allowed_models)

    # -- internals ----------------------------------------------------------
    def _resolve_model(self, model: Optional[str]) -> str:
        """Validate and resolve the model identifier.

        Parameters
        ----------
        model : Optional[str]
            Caller-supplied model ID, or ``None`` to use the default.

        Returns
        -------
        str
            Validated model identifier.

        Raises
        ------
        ValueError
            If the caller supplies a model ID that is not in the allowlist.
        """
        if model is None:
            return self._default_model

        if model not in self._allowed_models:
            raise ValueError(
                f"Model '{model}' is not allowed. "
                f"Choose one of: {sorted(self._allowed_models)}"
            )
        return model
