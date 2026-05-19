"""JSON-RPC helpers and admin/quota utilities for MCP stdio."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from trimcp.mcp_errors import merge_client_error_data

log = logging.getLogger("tri-stack-mcp")

if TYPE_CHECKING:
    from trimcp.orchestrator import TriStackEngine

# MCP / JSON-RPC client-visible prefix when ``consume_for_tool`` hits a hard limit.
MCP_QUOTA_EXCEEDED_PREFIX = "Resource quota exceeded (-32013)"

# Tools whose JSON-RPC payloads are keyed in Redis — quota must NOT run on cache hit (FIX-020).
_MCP_TOOL_RESPONSE_CACHE_TOOLS = frozenset({"semantic_search", "search_codebase", "graph_search"})


async def _try_cached_mcp_tool_response(
    eng: TriStackEngine,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[list[TextContent] | None, str | None]:
    """Return cached MCP tool payloads before quota runs; misses return (None, redis_key).

    Naming note: callers treat a non-empty first element as cache hit."""
    from trimcp.mcp_args import build_cache_key

    if tool_name not in _MCP_TOOL_RESPONSE_CACHE_TOOLS:
        return None, None

    gen_raw = await eng.redis_client.get("mcp_cache_generation")
    gen_val = int(gen_raw.decode()) if gen_raw else 0
    ns_id = arguments.get("namespace_id")
    cache_key = build_cache_key(
        tool_name=tool_name,
        arguments=arguments,
        generation=gen_val,
        namespace_id=ns_id,
    )
    cached_raw = await eng.redis_client.get(cache_key)
    if not cached_raw:
        return None, cache_key

    ns_for_log = str(ns_id)[:8] if ns_id is not None else "global"
    log.info("API Cache hit for tool %s (ns=%s)", tool_name, ns_for_log)
    return (
        [TextContent(type="text", text=cached_raw.decode())],
        cache_key,
    )


async def _consume_quota_for_mcp_tool(
    pg_pool,
    tool_name: str,
    arguments: dict[str, Any],
    redis_client,
) -> Any:
    from trimcp import quotas as _quotas

    try:
        return await _quotas.consume_for_tool(
            pg_pool, tool_name, arguments, redis_client=redis_client
        )
    except _quotas.QuotaExceededError as exc:
        raise ValueError(f"{MCP_QUOTA_EXCEEDED_PREFIX}: {exc}") from exc


def _check_admin(arguments: dict[str, Any]) -> None:
    """Validate admin privileges via :func:`trimcp.auth._validate_scope`.

    .. deprecated::
        Prefer ``@require_scope("admin")`` on new handlers.  Legacy replay/unredact
        paths still call this helper; it delegates to the same scope logic as the
        decorator and maps failures to ``(-32001)`` for backward-compatible clients.

    Raises:
        ValueError: When the caller is not authorised (embeds ``(-32001)``).
    """
    from trimcp.auth import ScopeError, _validate_scope

    try:
        _validate_scope("admin", arguments)
    except ScopeError as exc:
        raise ValueError(f"Unauthorized: {exc.reason} (-32001)") from exc


def _model_kwargs(arguments: dict[str, Any]) -> dict[str, Any]:
    """Strip MCP auth-only keys before ``**`` into ``extra='forbid'`` domain models."""
    from trimcp.mcp_args import model_kwargs

    return model_kwargs(arguments)


# ── JSON-RPC 2.0 Error Response Helper ─────────────────────────────────────
# Standard error codes per JSON-RPC 2.0:
#   -32600  Invalid Request
#   -32601  Method not found
#   -32602  Invalid params
#   -32603  Internal error
# MCP extended codes (server-errors -32000..-32099):
#   -32001  Admin authentication required
#   -32005  Scope forbidden
#   -32013  Resource quota exceeded
#   -32029  Rate limit exceeded

# Regex to extract embedded MCP error codes from exception messages:
# e.g. "Unauthorized administrative attempt: missing admin_api_key (-32001)"
_MCP_ERROR_CODE_RE = re.compile(r"\((-32\d{3})\)")


def _extract_mcp_code(msg: str, default: int = -32602) -> int:
    """Extract an MCP extended error code embedded in an exception message.

    Some callers (e.g. ``_check_admin``) embed codes like ``(-32001)`` in
    their ``ValueError`` message strings.  This function extracts them so
    the JSON-RPC response preserves the intended error code.
    """
    m = _MCP_ERROR_CODE_RE.search(msg)
    if m:
        return int(m.group(1))
    return default


def _jsonrpc_error_response(
    code: int,
    message: str,
    *,
    detail: str | None = None,
    data: dict[str, Any] | None = None,
) -> list[TextContent]:
    """Return a JSON-RPC 2.0 error response as ``TextContent``.

    Args:
        code: Standard JSON-RPC 2.0 or MCP extended error code.
        message: Short human-readable error summary.
        detail: Optional detail string included under ``error.data.detail``.
        data: Optional extra fields merged into ``error.data``.

    Returns:
        A single-element ``TextContent`` list containing the serialized
        JSON-RPC error object.  The MCP SDK treats this as a *successful*
        tool result; the error payload is for the *client* to interpret.
    """
    error: dict[str, Any] = {"code": code, "message": message}
    error_data = merge_client_error_data(data, detail=detail)
    if error_data:
        error["data"] = error_data
    return [
        TextContent(
            type="text",
            text=json.dumps({"jsonrpc": "2.0", "error": error}),
        )
    ]
