"""
trimcp.providers.anthropic_provider
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
LLM provider for Anthropic Claude models.

Structured output strategy
--------------------------
We use Anthropic's ``tool_use`` mechanism with a single synthetic tool whose
``input_schema`` is the Pydantic model's JSON schema.  Forcing the model to
call this tool yields a well-typed ``input`` dict that we then validate with
``response_model.model_validate()``.

This is more reliable than plain ``json_object`` prompting because the
model cannot produce non-JSON preamble when constrained to a tool call.

Reference:
  https://docs.anthropic.com/en/docs/tool-use

Supported models
----------------
  claude-opus-4-6 | claude-sonnet-4-6 | claude-haiku-4-5
"""
from __future__ import annotations

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

log = logging.getLogger(__name__)

_ANTHROPIC_API_BASE = "https://api.anthropic.com"
_ANTHROPIC_VERSION  = "2023-06-01"
_DEFAULT_TIMEOUT    = 120.0
_DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider(LLMProvider):
    """Calls Anthropic's Messages API with forced tool_use for structured output.

    Parameters
    ----------
    api_key:
        Anthropic API key (``TRIMCP_ANTHROPIC_API_KEY``).
    model:
        Anthropic model name, e.g. ``"claude-opus-4-6"``.
    max_tokens:
        Maximum tokens in the completion.
    timeout:
        Request timeout in seconds.
    base_url:
        Override the API base URL (useful for testing / proxies).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-4-6",
        *,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        timeout: float = _DEFAULT_TIMEOUT,
        base_url: str = _ANTHROPIC_API_BASE,
    ) -> None:
        self._api_key    = api_key
        self._model      = model
        self._max_tokens = max_tokens
        self._timeout    = timeout
        self._base_url   = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: List[Message],
        response_model: Type[ResponseModelT],
    ) -> ResponseModelT:
        tool_name = f"structured_{response_model.__name__.lower()}"
        schema    = response_model.model_json_schema()

        # Separate system messages from the conversation turns.
        system_parts = [m.content for m in messages if m.role.value == "system"]
        turn_messages = [
            {"role": m.role.value, "content": m.content}
            for m in messages
            if m.role.value != "system"
        ]
        system_prompt: Optional[str] = "\n\n".join(system_parts) or None

        body: Dict[str, Any] = {
            "model":      self._model,
            "max_tokens": self._max_tokens,
            "messages":   turn_messages,
            "tools": [
                {
                    "name":         tool_name,
                    "description":  f"Return a structured {response_model.__name__} object.",
                    "input_schema": schema,
                }
            ],
            # Force the model to always call the tool.
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers={
                        "x-api-key":         self._api_key,
                        "anthropic-version":  _ANTHROPIC_VERSION,
                        "Content-Type":       "application/json",
                    },
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"{self.model_identifier()} timed out after {self._timeout}s",
                provider=self.model_identifier(),
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                f"HTTP request to Anthropic failed: {exc}",
                provider=self.model_identifier(),
            ) from exc

        if not resp.is_success:
            raise LLMProviderError(
                f"Anthropic API returned HTTP {resp.status_code}",
                provider=self.model_identifier(),
                status_code=resp.status_code,
                upstream_message=resp.text[:500],
            )

        data = resp.json()

        # Locate the tool_use block in the response content list.
        tool_input = self._extract_tool_input(data, tool_name)

        try:
            return response_model.model_validate(tool_input)
        except ValidationError as exc:
            raise LLMValidationError(
                f"Anthropic tool_use response failed Pydantic validation "
                f"for {response_model.__name__}: {exc}",
                provider=self.model_identifier(),
            ) from exc

    def model_identifier(self) -> str:
        return f"anthropic/{self._model}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_tool_input(self, data: dict, tool_name: str) -> dict:
        """Pull the ``input`` dict from the tool_use block in *data*."""
        content_blocks = data.get("content", [])
        for block in content_blocks:
            if block.get("type") == "tool_use" and block.get("name") == tool_name:
                return block["input"]

        # Fallback: model returned stop_reason text instead of tool call.
        stop_reason = data.get("stop_reason")
        raise LLMProviderError(
            f"Anthropic model did not call tool '{tool_name}' "
            f"(stop_reason={stop_reason!r}).  Full response: {str(data)[:300]}",
            provider=self.model_identifier(),
        )
