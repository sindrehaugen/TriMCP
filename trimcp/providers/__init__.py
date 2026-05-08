"""
trimcp.providers
~~~~~~~~~~~~~~~~
LLM provider abstraction layer (Phase 1.2).

All LLM calls in TriMCP MUST go through ``LLMProvider.complete()``.
No direct SDK or HTTP calls to model APIs are permitted outside this package.

Quick start::

    from trimcp.providers import get_provider, Message
    from trimcp.consolidation import ConsolidatedAbstraction

    provider = get_provider(namespace_metadata)

    result: ConsolidatedAbstraction = await provider.complete(
        messages=[
            Message.system("You are a memory consolidation engine."),
            Message.user(cluster_json),
        ],
        response_model=ConsolidatedAbstraction,
    )
"""

from trimcp.providers.anthropic_provider import AnthropicProvider
from trimcp.providers.base import (
    DEFAULT_CIRCUIT_BREAKER,
    DEFAULT_RETRY_POLICY,
    CircuitBreaker,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUpstreamError,
    LLMValidationError,
    Message,
    MessageRole,
    ResponseModelT,
    RetryPolicy,
)
from trimcp.providers.factory import get_provider
from trimcp.providers.google_gemini import GoogleGeminiProvider
from trimcp.providers.local_cognitive import LocalCognitiveProvider
from trimcp.providers.openai_compat import OpenAICompatProvider

__all__ = [
    # Interface
    "LLMProvider",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMUpstreamError",
    "LLMValidationError",
    "Message",
    "MessageRole",
    "ResponseModelT",
    # Retry & circuit breaker
    "RetryPolicy",
    "DEFAULT_RETRY_POLICY",
    "CircuitBreaker",
    "DEFAULT_CIRCUIT_BREAKER",
    # Factory
    "get_provider",
    # Concrete providers (for direct instantiation in tests / custom wiring)
    "AnthropicProvider",
    "GoogleGeminiProvider",
    "LocalCognitiveProvider",
    "OpenAICompatProvider",
]
