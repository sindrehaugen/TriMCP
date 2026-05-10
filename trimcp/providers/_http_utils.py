"""
trimcp.providers._http_utils
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared HTTP client utilities for LLM providers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from trimcp._http_utils import SafeAsyncClient
from trimcp.observability import inject_trace_headers
from trimcp.providers.base import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUpstreamError,
)

log = logging.getLogger(__name__)


async def post_with_error_handling(
    url: str,
    body: dict[str, Any],
    timeout: float,
    model_id: str,
    headers: dict[str, str] | None = None,
    error_prefix: str = "HTTP request failed",
) -> dict[str, Any]:
    """Execute an async HTTP POST request to an LLM provider and handle errors in a unified way.

    Handles timeout, request errors, unsuccessful HTTP status, and non-JSON responses,
    wrapping them in the appropriate TriMCP exceptions (LLMTimeoutError, LLMProviderError).
    """
    # Inject W3C trace context into outbound headers so downstream services
    # (LLM gateways, cognitive sidecars) can continue the distributed trace.
    outbound_headers = inject_trace_headers(dict(headers or {}))
    try:
        async with SafeAsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers=outbound_headers,
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f"{model_id} timed out after {timeout}s",
            provider=model_id,
        ) from exc
    except httpx.RequestError as exc:
        raise LLMProviderError(
            f"{error_prefix}: {exc}",
            provider=model_id,
        ) from exc

    if not resp.is_success:
        status = resp.status_code
        upstream = resp.text[:500]

        # 429 — rate limit (carries optional retry-after header)
        if status == 429:
            retry_after = None
            try:
                retry_after = int(resp.headers.get("retry-after", ""))
            except (ValueError, TypeError):
                pass
            raise LLMRateLimitError(
                f"{model_id} rate-limited (HTTP 429)",
                provider=model_id,
                retry_after=retry_after,
                upstream_message=upstream,
            )

        # 5xx — transient upstream failure
        if 500 <= status < 600:
            raise LLMUpstreamError(
                f"{model_id} upstream error (HTTP {status})",
                provider=model_id,
                status_code=status,
                upstream_message=upstream,
            )

        # All other non-success statuses (400, 401, 403, 404, …)
        raise LLMProviderError(
            f"{model_id} returned HTTP {status}",
            provider=model_id,
            status_code=status,
            upstream_message=upstream,
        )

    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMProviderError(
            f"{model_id} returned non-JSON response: {resp.text[:300]!r}",
            provider=model_id,
        ) from exc
