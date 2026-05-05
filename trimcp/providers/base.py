"""
trimcp.providers.base
~~~~~~~~~~~~~~~~~~~~~
Abstract base for all LLM provider implementations.

All LLM calls in TriMCP MUST go through this interface.  No direct SDK or
HTTP calls to model APIs are permitted outside of this package.

Design decisions
----------------
* ``complete()`` is generic: callers pass the Pydantic V2 *model class* they
  expect back.  The provider validates the raw JSON from the model and returns
  a typed, fully-validated instance.  This eliminates ``dict`` passing and
  moves validation failures close to the LLM boundary rather than deep in
  business logic.

* ``model_identifier()`` returns ``"provider/model"`` so callers can write
  this string into ``event_log.llm_provider`` without coupling to provider
  internals.

* ``LLMProviderError`` wraps every provider-specific failure so callers handle
  one exception type regardless of which backend is active.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, Optional, Type, TypeVar

from pydantic import BaseModel, ConfigDict, field_validator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TypeVar — used to make complete() generic
# ---------------------------------------------------------------------------

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


# ---------------------------------------------------------------------------
# Message model
# ---------------------------------------------------------------------------

class MessageRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    """A single turn in a multi-turn conversation sent to an LLM."""

    model_config = ConfigDict(frozen=True)

    role: MessageRole
    content: str

    @field_validator("content")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message content must not be blank.")
        return v

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role=MessageRole.system, content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role=MessageRole.user, content=content)

    @classmethod
    def assistant(cls, content: str) -> "Message":
        return cls(role=MessageRole.assistant, content=content)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMProviderError(Exception):
    """Base exception for all LLM provider failures.

    Attributes
    ----------
    provider:
        ``"provider/model"`` string, e.g. ``"anthropic/claude-opus-4-6"``.
    status_code:
        HTTP status code if the failure was an upstream HTTP error; ``None``
        otherwise.
    upstream_message:
        Raw error message from the upstream API, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "unknown",
        status_code: Optional[int] = None,
        upstream_message: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.upstream_message = upstream_message


class LLMValidationError(LLMProviderError):
    """Raised when the model returns valid JSON that fails Pydantic validation.

    This usually means the model hallucinated fields or returned an unexpected
    shape.  Callers that catch ``LLMProviderError`` will also catch this.
    """


class LLMTimeoutError(LLMProviderError):
    """Raised when the upstream API call times out."""


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Abstract interface every LLM provider must implement.

    Usage
    -----
    ::

        provider = get_provider(namespace_metadata)
        result: ConsolidatedAbstraction = await provider.complete(
            messages=[
                Message.system("You are a memory consolidation engine."),
                Message.user(prompt),
            ],
            response_model=ConsolidatedAbstraction,
        )

    Implementors
    ------------
    * ``LocalCognitiveProvider``  — bundled model on port 11435 [D2/D7]
    * ``OpenAICompatProvider``    — OpenAI, Azure OpenAI, DeepSeek, Moonshot
    * ``AnthropicProvider``       — Anthropic Claude (tool_use structured output)
    * ``GoogleGeminiProvider``    — Gemini (schema-in-prompt + JSON parsing)
    """

    @abstractmethod
    async def complete(
        self,
        messages: list,
        response_model: Type[ResponseModelT],
    ) -> ResponseModelT:
        """Send *messages* to the model and return a validated *response_model* instance.

        Parameters
        ----------
        messages:
            Ordered list of :class:`Message` objects.
        response_model:
            A Pydantic V2 ``BaseModel`` *class* (not an instance) that describes
            the expected response shape.  The provider must JSON-serialise the
            model's schema into the request and validate the raw response against
            this class before returning.

        Returns
        -------
        ResponseModelT
            A fully-validated, frozen-safe instance of *response_model*.

        Raises
        ------
        LLMValidationError
            The model returned valid JSON that does not match *response_model*.
        LLMProviderError
            Any upstream API error, connection failure, or unexpected response.
        LLMTimeoutError
            The upstream call exceeded the configured timeout.
        """
        ...

    @abstractmethod
    def model_identifier(self) -> str:
        """Return the ``"provider/model"`` identifier for ``event_log`` rows.

        Examples: ``"anthropic/claude-opus-4-6"``, ``"local/cognitive-model"``.
        """
        ...
