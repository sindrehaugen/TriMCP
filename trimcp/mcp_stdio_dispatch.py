"""MCP stdio tool dispatch (handler routing and error envelopes)."""

from __future__ import annotations

import logging
from typing import Any

from mcp.types import TextContent

# Handler module imports are kept here so tests can use
# ``patch.object(dispatch.memory_mcp_handlers, "handle_foo", mock)``
# (same module objects that ``_h()`` in tool_registry resolves at call time).
from trimcp import (
    TriStackEngine,
    a2a_mcp_handlers,
    admin_mcp_handlers,
    bridge_mcp_handlers,
    catalog_mcp_handlers,
    code_mcp_handlers,
    contradiction_mcp_handlers,
    graph_mcp_handlers,
    memory_mcp_handlers,
    migration_mcp_handlers,
    replay_mcp_handlers,
    snapshot_mcp_handlers,
)
from trimcp.auth import RateLimitError, ScopeError, enforce_mcp_tool_auth
from trimcp.config import cfg
from trimcp.constants import MCP_CACHE_TTL_S as _MCP_CACHE_TTL_S
from trimcp.mcp_args import bump_cache_generation, purge_document_cache
from trimcp.mcp_errors import (
    McpError,
    UnknownToolError,
    client_visible_detail,
    internal_error_data,
)
from trimcp.mcp_stdio_rpc import (
    MCP_QUOTA_EXCEEDED_PREFIX,
    _check_admin,
    _consume_quota_for_mcp_tool,
    _jsonrpc_error_response,
    _try_cached_mcp_tool_response,
)
from trimcp.observability import instrument_tool_call
from trimcp.quotas import QuotaExceededError, null_reservation
from trimcp.tool_registry import TOOL_REGISTRY

log = logging.getLogger("tri-stack-mcp")


async def execute_call_tool(
    engine: TriStackEngine | None,
    name: str,
    arguments: dict[str, Any],
) -> list[TextContent]:
    if engine is None:
        return _jsonrpc_error_response(
            -32603,
            "Internal error",
            detail="Engine not initialized",
        )

    # Check if tool is disabled in Redis
    try:
        if engine.redis_client and await engine.redis_client.hexists("trimcp:tools:disabled", name):
            return _jsonrpc_error_response(
                -32005,
                "Scope forbidden",
                detail=f"Tool '{name}' has been disabled by the administrator.",
            )
    except Exception as exc:
        log.warning("Redis toggle check failed (defaulting to enabled): %s", exc)

    q_res = null_reservation()

    async with instrument_tool_call(name):
        try:
            try:
                enforce_mcp_tool_auth(name, arguments)
            except ScopeError as exc:
                return _jsonrpc_error_response(
                    -32005,
                    "Scope forbidden",
                    detail=client_visible_detail(exc.reason),
                )

            # --- Registry lookup — unknown tools fail fast before quota is consumed ---
            spec = TOOL_REGISTRY.get(name)
            if spec is None:
                raise UnknownToolError(name)

            # Migration gate: disabled tools return a plain message, no error envelope.
            if spec.migration and cfg.TRIMCP_DISABLE_MIGRATION_MCP:
                return [
                    TextContent(
                        type="text",
                        text="Migration tools are disabled (TRIMCP_DISABLE_MIGRATION_MCP=true).",
                    )
                ]

            # --- API response cache (before quota — FIX-020) ---
            cached_payload, cache_key = await _try_cached_mcp_tool_response(engine, name, arguments)
            if cached_payload is not None:
                return cached_payload

            # Quota is incremented only on cache miss, immediately before the tool runs.
            # Never increment on cache hit — see FIX-020.
            q_res = await _consume_quota_for_mcp_tool(
                engine.pg_pool, name, arguments, engine.redis_client
            )

            # --- Handler call (quota is rolled back on any exception) ---
            try:
                if spec.admin_only:
                    _check_admin(arguments)
                result_text = await spec.handler(engine, arguments)
                # Post-success: bump the generation counter so stale cached reads
                # become unreachable.  Must run AFTER the handler so failed mutations
                # do not cause unnecessary cache invalidation.
                if spec.mutation:
                    await bump_cache_generation(engine.redis_client)

                    doc_id = arguments.get("memory_id") or arguments.get("snapshot_id")
                    if name in ("forget_memory", "delete_snapshot") and doc_id:
                        ns_id = arguments.get("namespace_id")
                        if ns_id:
                            try:
                                await purge_document_cache(
                                    engine.redis_client,
                                    namespace_id=str(ns_id),
                                    memory_id=str(doc_id),
                                )
                            except Exception as exc:
                                log.warning(
                                    "%s: document cache purge failed: %s",
                                    name,
                                    exc,
                                )
                if spec.cacheable and cache_key:
                    await engine.redis_client.setex(cache_key, _MCP_CACHE_TTL_S, result_text)
                return [TextContent(type="text", text=result_text)]
            except BaseException:
                # BaseException catches asyncio.CancelledError (Python ≥ 3.8) so
                # quota is rolled back even when the task is cancelled mid-call.
                await q_res.rollback()
                raise

        except McpError as e:
            return _jsonrpc_error_response(e.code, e.message, data=e.data)
        except ScopeError as e:
            return _jsonrpc_error_response(
                -32005,
                "Scope forbidden",
                data={"reason": "scope_forbidden", "required_scope": e.required_scope},
                detail=client_visible_detail(e.reason or str(e)),
            )
        except RateLimitError as e:
            return _jsonrpc_error_response(
                -32029,
                "Rate limit exceeded",
                data={"reason": "rate_limited"},
                detail=client_visible_detail(str(e)),
            )
        except QuotaExceededError as e:
            return _jsonrpc_error_response(
                -32013,
                "Resource quota exceeded",
                data={"reason": "quota_exceeded"},
                detail=client_visible_detail(str(e)),
            )
        except (ValueError, TypeError) as e:
            msg = str(e)
            if msg.startswith(MCP_QUOTA_EXCEEDED_PREFIX):
                return _jsonrpc_error_response(
                    -32013,
                    "Resource quota exceeded",
                    data={"reason": "quota_exceeded"},
                    detail=client_visible_detail(msg),
                )
            if msg.startswith("Rate limit exceeded"):
                return _jsonrpc_error_response(
                    -32029,
                    "Rate limit exceeded",
                    data={"reason": "rate_limited"},
                    detail=client_visible_detail(msg),
                )
            return _jsonrpc_error_response(
                -32602,
                "Invalid params",
                data={"reason": "invalid_params"},
                detail=client_visible_detail(msg),
            )
        except Exception as e:
            log.exception("Unhandled error in tool '%s'", name)
            return _jsonrpc_error_response(
                -32603,
                "Internal error",
                data=internal_error_data(e),
            )
