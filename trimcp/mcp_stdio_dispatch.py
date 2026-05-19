"""MCP stdio tool dispatch (handler routing and error envelopes)."""

from __future__ import annotations

import logging
from typing import Any

from mcp.types import TextContent

from trimcp import (
    TriStackEngine,
    a2a_mcp_handlers,
    admin_mcp_handlers,
    bridge_mcp_handlers,
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
    _extract_mcp_code,
    _jsonrpc_error_response,
    _try_cached_mcp_tool_response,
)

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

    from trimcp.observability import instrument_tool_call
    from trimcp.quotas import null_reservation

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

            _base_mutation_tools = {
                "store_memory",
                "store_artifact",
                "store_media",
                "index_code_file",
                "connect_bridge",
                "complete_bridge_auth",
                "disconnect_bridge",
                "force_resync_bridge",
                "create_snapshot",
                "delete_snapshot",
                "manage_namespace",
                "manage_quotas",
                "rotate_signing_key",
                "trigger_consolidation",
                "resolve_contradiction",
                "boost_memory",
                "forget_memory",
                "a2a_create_grant",
                "a2a_revoke_grant",
                "unredact_memory",
                "replay_reconstruct",
            }
            if not cfg.TRIMCP_DISABLE_MIGRATION_MCP:
                _base_mutation_tools |= {
                    "start_migration",
                    "commit_migration",
                    "abort_migration",
                }
            MUTATION_TOOLS = _base_mutation_tools

            if name in MUTATION_TOOLS:
                from trimcp.mcp_args import bump_cache_generation, purge_document_cache

                await bump_cache_generation(engine.redis_client)

                # Document-level cache purge: when a specific memory or snapshot
                # is deleted, evict any cached responses that referenced it.
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

            # --- API response cache (before quota — FIX-020) ---
            cached_payload, cache_key = await _try_cached_mcp_tool_response(engine, name, arguments)
            if cached_payload is not None:
                return cached_payload

            # Quota is incremented only on cache miss, immediately before the tool runs.
            # Never increment on cache hit — see FIX-020.
            q_res = await _consume_quota_for_mcp_tool(
                engine.pg_pool, name, arguments, engine.redis_client
            )

            # --- Tool dispatch ---
            try:
                if name == "store_memory":
                    result_text = await memory_mcp_handlers.handle_store_memory(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "store_artifact":
                    result_text = await memory_mcp_handlers.handle_store_artifact(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "store_media":
                    result_text = await memory_mcp_handlers.handle_store_media(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "semantic_search":
                    result_text = await memory_mcp_handlers.handle_semantic_search(
                        engine, arguments
                    )
                    if cache_key:
                        await engine.redis_client.setex(cache_key, 300, result_text)
                    return [TextContent(type="text", text=result_text)]

                if name == "index_code_file":
                    result_text = await code_mcp_handlers.handle_index_code_file(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "check_indexing_status":
                    result_text = await code_mcp_handlers.handle_check_indexing_status(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "search_codebase":
                    result_text = await code_mcp_handlers.handle_search_codebase(engine, arguments)
                    if cache_key:
                        await engine.redis_client.setex(cache_key, 300, result_text)
                    return [TextContent(type="text", text=result_text)]

                if name == "graph_search":
                    result_text = await graph_mcp_handlers.handle_graph_search(engine, arguments)
                    if cache_key:
                        await engine.redis_client.setex(cache_key, 300, result_text)
                    return [TextContent(type="text", text=result_text)]

                if name == "get_recent_context":
                    result_text = await memory_mcp_handlers.handle_get_recent_context(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "connect_bridge":
                    text = await bridge_mcp_handlers.connect_bridge(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "complete_bridge_auth":
                    text = await bridge_mcp_handlers.complete_bridge_auth(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "list_bridges":
                    text = await bridge_mcp_handlers.list_bridges(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "disconnect_bridge":
                    text = await bridge_mcp_handlers.disconnect_bridge(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "force_resync_bridge":
                    text = await bridge_mcp_handlers.force_resync_bridge(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "bridge_status":
                    text = await bridge_mcp_handlers.bridge_status(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "boost_memory":
                    result_text = await memory_mcp_handlers.handle_boost_memory(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "forget_memory":
                    result_text = await memory_mcp_handlers.handle_forget_memory(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "list_contradictions":
                    result_text = await contradiction_mcp_handlers.handle_list_contradictions(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "resolve_contradiction":
                    result_text = await contradiction_mcp_handlers.handle_resolve_contradiction(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "unredact_memory":
                    _check_admin(arguments)
                    result_text = await memory_mcp_handlers.handle_unredact_memory(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name in (
                    "start_migration",
                    "migration_status",
                    "validate_migration",
                    "commit_migration",
                    "abort_migration",
                ):
                    if cfg.TRIMCP_DISABLE_MIGRATION_MCP:
                        return [
                            TextContent(
                                type="text",
                                text="Migration tools are disabled (TRIMCP_DISABLE_MIGRATION_MCP=true).",
                            )
                        ]
                    if name == "start_migration":
                        result_text = await migration_mcp_handlers.handle_start_migration(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]
                    if name == "migration_status":
                        result_text = await migration_mcp_handlers.handle_migration_status(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]
                    if name == "validate_migration":
                        result_text = await migration_mcp_handlers.handle_validate_migration(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]
                    if name == "commit_migration":
                        result_text = await migration_mcp_handlers.handle_commit_migration(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]
                    if name == "abort_migration":
                        result_text = await migration_mcp_handlers.handle_abort_migration(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]

                if name == "replay_observe":
                    _check_admin(arguments)
                    result_text = await replay_mcp_handlers.handle_replay_observe(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "replay_reconstruct":
                    _check_admin(arguments)
                    result_text = await replay_mcp_handlers.handle_replay_reconstruct(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "replay_fork":
                    _check_admin(arguments)
                    result_text = await replay_mcp_handlers.handle_replay_fork(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "replay_status":
                    _check_admin(arguments)
                    result_text = await replay_mcp_handlers.handle_replay_status(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "get_event_provenance":
                    result_text = await replay_mcp_handlers.handle_get_event_provenance(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "a2a_create_grant":
                    result_text = await a2a_mcp_handlers.handle_a2a_create_grant(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "a2a_revoke_grant":
                    result_text = await a2a_mcp_handlers.handle_a2a_revoke_grant(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "a2a_list_grants":
                    result_text = await a2a_mcp_handlers.handle_a2a_list_grants(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "a2a_query_shared":
                    result_text = await a2a_mcp_handlers.handle_a2a_query_shared(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "manage_namespace":
                    result_text = await admin_mcp_handlers.handle_manage_namespace(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "verify_memory":
                    result_text = await admin_mcp_handlers.handle_verify_memory(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "trigger_consolidation":
                    result_text = await admin_mcp_handlers.handle_trigger_consolidation(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "consolidation_status":
                    result_text = await admin_mcp_handlers.handle_consolidation_status(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "manage_quotas":
                    result_text = await admin_mcp_handlers.handle_manage_quotas(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "rotate_signing_key":
                    result_text = await admin_mcp_handlers.handle_rotate_signing_key(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "get_health":
                    result_text = await admin_mcp_handlers.handle_get_health(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "create_snapshot":
                    result_text = await snapshot_mcp_handlers.handle_create_snapshot(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "list_snapshots":
                    result_text = await snapshot_mcp_handlers.handle_list_snapshots(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "delete_snapshot":
                    result_text = await snapshot_mcp_handlers.handle_delete_snapshot(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "compare_states":
                    result_text = await snapshot_mcp_handlers.handle_compare_states(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "list_dlq":
                    result_text = await admin_mcp_handlers.handle_list_dlq(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "replay_dlq":
                    result_text = await admin_mcp_handlers.handle_replay_dlq(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                if name == "purge_dlq":
                    result_text = await admin_mcp_handlers.handle_purge_dlq(engine, arguments)
                    return [TextContent(type="text", text=result_text)]

                raise UnknownToolError(name)
            except Exception:
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
            # Check for embedded MCP error codes (e.g. (-32001) from _check_admin)
            mcp_code = _extract_mcp_code(msg)
            if mcp_code != -32602:
                return _jsonrpc_error_response(
                    mcp_code,
                    "Request failed",
                    data={"reason": "request_failed"},
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
