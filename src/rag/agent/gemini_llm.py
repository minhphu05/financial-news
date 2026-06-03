"""Thin wrapper around the Gemini chat completion API."""

from __future__ import annotations

from typing import Optional

from google import genai
from google.genai import types

from src.rag.config import Settings, get_settings
from src.rag.utils import get_logger

logger = get_logger(__name__)


class GeminiLLM:
    """Synchronous chat-completion wrapper for Gemini models.

    Parameters
    ----------
    settings : Optional[Settings]
        Settings override.
    client : Optional[genai.Client]
        Pre-built ``google.genai`` client (for tests).
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[genai.Client] = None,
    ) -> None:
        self._settings = settings or get_settings()
        api_key = self._settings.gemini.api_key.get_secret_value()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is empty. Set it in the environment or in `.env`."
            )
        self._client = client or genai.Client(api_key=api_key)
        self._model = self._settings.gemini.chat_model

    def generate(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        """Call Gemini and return the generated text.

        Parameters
        ----------
        system_instruction : str
            System prompt sent to Gemini.
        user_prompt : str
            User-facing prompt (typically built by ``prompts.build_user_prompt``).
        temperature : Optional[float]
            Override the default sampling temperature.
        max_output_tokens : Optional[float]
            Override the default ``max_output_tokens``.

        Returns
        -------
        str
            Generated text. Empty string if the model returned nothing.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature if temperature is not None else self._settings.gemini.temperature,
            max_output_tokens=max_output_tokens or self._settings.gemini.max_output_tokens,
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=config,
        )
        text = getattr(response, "text", None)
        if not text:
            try:
                text = response.candidates[0].content.parts[0].text
            except Exception:  # noqa: BLE001
                text = ""
        return text or ""
