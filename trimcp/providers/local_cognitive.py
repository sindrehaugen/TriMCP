"""
trimcp.providers.local_cognitive
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
LLM provider for the bundled local cognitive model [D2 / D7].

The bundled image is ``ghcr.io/sindrehaugen/trimcp-cognitive:v1`` and exposes
an OpenAI-compatible HTTP API on ``localhost:11435``.  Detection happens via a
``GET /health`` probe at startup; if the endpoint is unavailable the factory
logs a warning and the caller is responsible for graceful skip.

Structured output uses ``response_format={"type": "json_object"}`` with the
Pydantic schema embedded in the system prompt.  The raw content string is
validated with Pydantic V2 before return.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, List, Optional, Type

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

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MODEL   = "local-cognitive-model"


class LocalCognitiveProvider(LLMProvider):
    """Calls the bundled cognitive model over OpenAI-compatible HTTP.

    Parameters
    ----------
    base_url:
        HTTP base URL of the cognitive container, e.g.
        ``"http://localhost:11435"``.  Trailing slashes are stripped.
    model:
        Model name sent in the request body.  Defaults to
        ``"local-cognitive-model"``.
    timeout:
        Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model    = model
        self._timeout  = timeout

    # ------------------------------------------------------------------
    # Health probe (optional, called by factory)
    # ------------------------------------------------------------------

    async def is_healthy(self) -> bool:
        """Return True if ``GET /health`` responds with 2xx."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._base_url}/health")
                return r.is_success
        except Exception:
            return False

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: List[Message],
        response_model: Type[ResponseModelT],
    ) -> ResponseModelT:
        schema_hint = json.dumps(response_model.model_json_schema(), indent=2)
        payload = {
            "model": self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Local cognitive model timed out after {self._timeout}s",
                provider=self.model_identifier(),
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                f"HTTP request to local cognitive model failed: {exc}",
                provider=self.model_identifier(),
            ) from exc

        if not resp.is_success:
            raise LLMProviderError(
                f"Local cognitive model returned HTTP {resp.status_code}",
                provider=self.model_identifier(),
                status_code=resp.status_code,
                upstream_message=resp.text[:500],
            )

        data    = resp.json()
        content = data["choices"][0]["message"]["content"]
        return _parse_and_validate(content, response_model, self.model_identifier())

    def model_identifier(self) -> str:
        return f"local/{self._model}"


# ---------------------------------------------------------------------------
# Shared validation helper (used by multiple providers)
# ---------------------------------------------------------------------------

def _parse_and_validate(
    raw_content: str,
    response_model: Type[ResponseModelT],
    provider_id: str,
) -> ResponseModelT:
    """Parse *raw_content* as JSON and validate against *response_model*.

    Raises
    ------
    LLMValidationError
        When the JSON parses but fails Pydantic validation.
    LLMProviderError
        When the JSON itself is malformed.
    """
    try:
        return response_model.model_validate_json(raw_content)
    except ValidationError as exc:
        raise LLMValidationError(
            f"Model response failed Pydantic validation for {response_model.__name__}: {exc}",
            provider=provider_id,
        ) from exc
    except json.JSONDecodeError as exc:
        raise LLMProviderError(
            f"Model returned non-JSON content: {raw_content[:200]!r}",
            provider=provider_id,
        ) from exc
