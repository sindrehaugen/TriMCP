"""
trimcp.providers.google_gemini
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
LLM provider for Google Gemini models.

Structured output strategy
--------------------------
Per the spec: "schema-in-prompt + parsing".  We embed the Pydantic JSON
schema in the system prompt and request ``application/json`` response MIME.
The Gemini API (``generateContent``) also supports a ``responseSchema`` field
in the ``generationConfig`` for models that support it (gemini-2.0+); we
include it when building the request body.

Supported models
----------------
  gemini-2.0-pro | gemini-2.0-flash
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import ValidationError

from trimcp.providers.base import (
    LLMProvider,
    LLMProviderError,
    LLMTimeoutError,
    LLMValidationError,
    Message,
    ResponseModelT,
)
from trimcp.providers.local_cognitive import _parse_and_validate

log = logging.getLogger(__name__)

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_TIMEOUT = 120.0


class GoogleGeminiProvider(LLMProvider):
    """Calls the Google Gemini ``generateContent`` API.

    Parameters
    ----------
    api_key:
        Google AI Studio API key (``TRIMCP_GEMINI_API_KEY``).
    model:
        Gemini model name, e.g. ``"gemini-2.0-flash"``.
    timeout:
        Request timeout in seconds.
    base_url:
        Override API base URL.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        base_url: str = _GEMINI_API_BASE,
    ) -> None:
        self._api_key  = api_key
        self._model    = model
        self._timeout  = timeout
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: List[Message],
        response_model: Type[ResponseModelT],
    ) -> ResponseModelT:
        schema     = response_model.model_json_schema()
        schema_str = json.dumps(schema, indent=2)

        contents, system_instruction = self._build_contents(messages, schema_str)
        body: Dict[str, Any] = {
            "contents":             contents,
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema":   schema,
            },
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = (
            f"{self._base_url}/models/{self._model}:generateContent"
            f"?key={self._api_key}"
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"{self.model_identifier()} timed out after {self._timeout}s",
                provider=self.model_identifier(),
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                f"HTTP request to Gemini failed: {exc}",
                provider=self.model_identifier(),
            ) from exc

        if not resp.is_success:
            raise LLMProviderError(
                f"Gemini API returned HTTP {resp.status_code}",
                provider=self.model_identifier(),
                status_code=resp.status_code,
                upstream_message=resp.text[:500],
            )

        data        = resp.json()
        raw_content = self._extract_text(data)
        return _parse_and_validate(raw_content, response_model, self.model_identifier())

    def model_identifier(self) -> str:
        return f"google_gemini/{self._model}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_contents(
        self,
        messages: List[Message],
        schema_str: str,
    ):
        """Convert Message list to Gemini ``contents`` format.

        Gemini uses ``USER`` / ``MODEL`` roles (not ``assistant``).
        System messages are collapsed into ``systemInstruction``.
        The schema is appended to the first user turn so the model always
        sees it even when ``responseSchema`` is ignored by older models.
        """
        system_parts: List[str] = []
        contents: List[dict]    = []

        for msg in messages:
            role = msg.role.value
            if role == "system":
                system_parts.append(msg.content)
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg.content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": msg.content}]})

        # Append schema reminder to the last user turn (or add a new one).
        schema_reminder = (
            f"\n\nReturn ONLY valid JSON that matches this schema:\n{schema_str}"
        )
        if contents and contents[-1]["role"] == "user":
            contents[-1]["parts"][-1]["text"] += schema_reminder
        else:
            contents.append({
                "role":  "user",
                "parts": [{"text": schema_reminder}],
            })

        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return contents, system_instruction

    def _extract_text(self, data: dict) -> str:
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMProviderError(
                f"Unexpected Gemini response shape: {str(data)[:300]}",
                provider=self.model_identifier(),
            ) from exc
