"""Declarative MCP tool registry — single source of truth for dispatch metadata.

Replaces the 54-branch ``if name ==`` ladder in ``mcp_stdio_dispatch.py``
with a ``ToolSpec`` → ``TOOL_REGISTRY`` lookup table.

Each entry records:
  * which handler coroutine to call
  * whether the tool requires admin credentials (``admin_only``)
  * whether successful responses may be cached in Redis (``cacheable``)
  * whether the tool mutates state and should bump the cache generation counter
    (``mutation``)
  * whether the tool is gated by ``NCE_DISABLE_MIGRATION_MCP`` (``migration``)

Derived frozensets (``MUTATION_TOOLS``, ``CACHEABLE_TOOLS``, etc.) are computed
once at import time from the registry — no duplicated inline sets elsewhere.
"""

from __future__ import annotations

import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nce import (
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
from nce.admin_handlers import settings as settings_mcp_handlers
from nce.vertical_modules.dynamics365 import mcp_handlers as d365_mcp_handlers
from nce.vertical_modules.netbox import circuits as netbox_circuits


def _h(module: types.ModuleType, attr: str) -> Callable[..., Any]:
    """Return an async wrapper that resolves ``module.attr`` at **call time**.

    Late-binding preserves ``unittest.mock.patch("pkg.module.handler", ...)``
    compatibility: patching the module attribute after import still affects
    the function actually invoked by the dispatch loop.  Direct references
    stored in a frozen dataclass at registry construction time would silently
    ignore any later patches.
    """

    async def _call(engine: Any, arguments: Any) -> Any:
        return await getattr(module, attr)(engine, arguments)

    # Preserve legible names in tracebacks and for iscoroutinefunction checks.
    _call.__name__ = attr
    _call.__qualname__ = f"{module.__name__}.{attr}"
    return _call


@dataclass(frozen=True)
class ToolSpec:
    """Immutable metadata for a single registered MCP tool.

    Attributes:
        handler:    The async coroutine that implements the tool.
                    Signature: ``async (engine, arguments) -> str``
        admin_only: When *True* the dispatch layer calls ``_check_admin``
                    before invoking the handler.
        cacheable:  When *True* the dispatch layer writes a successful
                    response into Redis with TTL = MCP_CACHE_TTL_S.
        mutation:   When *True* the dispatch layer increments the global
                    cache-generation counter before serving the request
                    (and before any cache lookup).
        migration:  When *True* the tool is gated by
                    ``cfg.NCE_DISABLE_MIGRATION_MCP``; a disabled gate
                    returns a human-readable message without calling the handler.
    """

    handler: Callable[..., Any]
    admin_only: bool = False
    cacheable: bool = False
    mutation: bool = False
    migration: bool = False


# ---------------------------------------------------------------------------
# Registry — one entry per tool, grouped by domain
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, ToolSpec] = {
    # ------------------------------------------------------------------
    # Memory tools
    # ------------------------------------------------------------------
    "store_memory": ToolSpec(
        _h(memory_mcp_handlers, "handle_store_memory"),
        mutation=True,
    ),
    "store_artifact": ToolSpec(
        _h(memory_mcp_handlers, "handle_store_artifact"),
        mutation=True,
    ),
    "store_media": ToolSpec(
        _h(memory_mcp_handlers, "handle_store_media"),
        mutation=True,
    ),
    "semantic_search": ToolSpec(
        _h(memory_mcp_handlers, "handle_semantic_search"),
        cacheable=True,
    ),
    "get_recent_context": ToolSpec(
        _h(memory_mcp_handlers, "handle_get_recent_context"),
    ),
    "boost_memory": ToolSpec(
        _h(memory_mcp_handlers, "handle_boost_memory"),
        mutation=True,
    ),
    "forget_memory": ToolSpec(
        _h(memory_mcp_handlers, "handle_forget_memory"),
        mutation=True,
    ),
    "unredact_memory": ToolSpec(
        _h(memory_mcp_handlers, "handle_unredact_memory"),
        admin_only=True,
        mutation=True,
    ),
    "shred_memory": ToolSpec(
        _h(memory_mcp_handlers, "handle_shred_memory"),
        admin_only=True,
        mutation=True,
    ),
    # ------------------------------------------------------------------
    # Code indexing tools
    # ------------------------------------------------------------------
    "index_code_file": ToolSpec(
        _h(code_mcp_handlers, "handle_index_code_file"),
        mutation=True,
    ),
    "check_indexing_status": ToolSpec(
        _h(code_mcp_handlers, "handle_check_indexing_status"),
    ),
    "search_codebase": ToolSpec(
        _h(code_mcp_handlers, "handle_search_codebase"),
        cacheable=True,
    ),
    # ------------------------------------------------------------------
    # Graph / GraphRAG tools
    # ------------------------------------------------------------------
    "graph_search": ToolSpec(
        _h(graph_mcp_handlers, "handle_graph_search"),
        cacheable=True,
    ),
    "neuromorphic_search": ToolSpec(
        _h(graph_mcp_handlers, "handle_neuromorphic_search"),
        cacheable=True,
    ),
    # ------------------------------------------------------------------
    # Bridge / integration tools
    # ------------------------------------------------------------------
    "connect_bridge": ToolSpec(
        _h(bridge_mcp_handlers, "connect_bridge"),
        mutation=True,
    ),
    "complete_bridge_auth": ToolSpec(
        _h(bridge_mcp_handlers, "complete_bridge_auth"),
        mutation=True,
    ),
    "list_bridges": ToolSpec(
        _h(bridge_mcp_handlers, "list_bridges"),
    ),
    "disconnect_bridge": ToolSpec(
        _h(bridge_mcp_handlers, "disconnect_bridge"),
        mutation=True,
    ),
    "force_resync_bridge": ToolSpec(
        _h(bridge_mcp_handlers, "force_resync_bridge"),
        mutation=True,
    ),
    "bridge_status": ToolSpec(
        _h(bridge_mcp_handlers, "bridge_status"),
    ),
    # ------------------------------------------------------------------
    # Contradiction tools
    # ------------------------------------------------------------------
    "list_contradictions": ToolSpec(
        _h(contradiction_mcp_handlers, "handle_list_contradictions"),
    ),
    "resolve_contradiction": ToolSpec(
        _h(contradiction_mcp_handlers, "handle_resolve_contradiction"),
        mutation=True,
    ),
    # ------------------------------------------------------------------
    # Migration tools  (gated by NCE_DISABLE_MIGRATION_MCP)
    # ------------------------------------------------------------------
    "start_migration": ToolSpec(
        _h(migration_mcp_handlers, "handle_start_migration"),
        mutation=True,
        migration=True,
    ),
    "migration_status": ToolSpec(
        _h(migration_mcp_handlers, "handle_migration_status"),
        migration=True,
    ),
    "validate_migration": ToolSpec(
        _h(migration_mcp_handlers, "handle_validate_migration"),
        migration=True,
    ),
    "commit_migration": ToolSpec(
        _h(migration_mcp_handlers, "handle_commit_migration"),
        mutation=True,
        migration=True,
    ),
    "abort_migration": ToolSpec(
        _h(migration_mcp_handlers, "handle_abort_migration"),
        mutation=True,
        migration=True,
    ),
    # ------------------------------------------------------------------
    # Replay / event-sourcing tools
    # ------------------------------------------------------------------
    "replay_observe": ToolSpec(
        _h(replay_mcp_handlers, "handle_replay_observe"),
        admin_only=True,
    ),
    "replay_reconstruct": ToolSpec(
        _h(replay_mcp_handlers, "handle_replay_reconstruct"),
        admin_only=True,
        mutation=True,
    ),
    "replay_fork": ToolSpec(
        _h(replay_mcp_handlers, "handle_replay_fork"),
        admin_only=True,
    ),
    "replay_status": ToolSpec(
        _h(replay_mcp_handlers, "handle_replay_status"),
        admin_only=True,
    ),
    "get_event_provenance": ToolSpec(
        _h(replay_mcp_handlers, "handle_get_event_provenance"),
    ),
    "explain_memory": ToolSpec(
        _h(replay_mcp_handlers, "handle_explain_memory"),
    ),
    "explain_past_decision": ToolSpec(
        _h(replay_mcp_handlers, "handle_explain_past_decision"),
        admin_only=True,
        mutation=True,
    ),
    "explain_config_change": ToolSpec(
        _h(settings_mcp_handlers, "handle_explain_config_change"),
        admin_only=True,
    ),
    # ------------------------------------------------------------------
    # Agent-to-Agent (A2A) grant tools
    # ------------------------------------------------------------------
    "a2a_create_grant": ToolSpec(
        _h(a2a_mcp_handlers, "handle_a2a_create_grant"),
        mutation=True,
    ),
    "a2a_revoke_grant": ToolSpec(
        _h(a2a_mcp_handlers, "handle_a2a_revoke_grant"),
        mutation=True,
    ),
    "a2a_list_grants": ToolSpec(
        _h(a2a_mcp_handlers, "handle_a2a_list_grants"),
    ),
    "a2a_query_shared": ToolSpec(
        _h(a2a_mcp_handlers, "handle_a2a_query_shared"),
    ),
    "a2a_verify_grant_status": ToolSpec(
        _h(a2a_mcp_handlers, "handle_a2a_verify_grant_status"),
    ),
    "a2a_update_grant_scopes": ToolSpec(
        _h(a2a_mcp_handlers, "handle_a2a_update_grant_scopes"),
        mutation=True,
    ),
    "a2a_inspect_grant": ToolSpec(
        _h(a2a_mcp_handlers, "handle_a2a_inspect_grant"),
    ),
    # ------------------------------------------------------------------
    # Admin / operational tools
    # ------------------------------------------------------------------
    "manage_namespace": ToolSpec(
        _h(admin_mcp_handlers, "handle_manage_namespace"),
        mutation=True,
    ),
    "verify_memory": ToolSpec(
        _h(admin_mcp_handlers, "handle_verify_memory"),
    ),
    "trigger_consolidation": ToolSpec(
        _h(admin_mcp_handlers, "handle_trigger_consolidation"),
        mutation=True,
    ),
    "consolidation_status": ToolSpec(
        _h(admin_mcp_handlers, "handle_consolidation_status"),
    ),
    "manage_quotas": ToolSpec(
        _h(admin_mcp_handlers, "handle_manage_quotas"),
        mutation=True,
    ),
    "rotate_signing_key": ToolSpec(
        _h(admin_mcp_handlers, "handle_rotate_signing_key"),
        mutation=True,
    ),
    "get_health": ToolSpec(
        _h(admin_mcp_handlers, "handle_get_health"),
    ),
    "list_dlq": ToolSpec(
        _h(admin_mcp_handlers, "handle_list_dlq"),
    ),
    "replay_dlq": ToolSpec(
        _h(admin_mcp_handlers, "handle_replay_dlq"),
        mutation=True,  # writes to dead_letter_queue (marks entry as replayed)
    ),
    "purge_dlq": ToolSpec(
        _h(admin_mcp_handlers, "handle_purge_dlq"),
        mutation=True,  # deletes from dead_letter_queue
    ),
    # ------------------------------------------------------------------
    # Snapshot tools
    # ------------------------------------------------------------------
    "create_snapshot": ToolSpec(
        _h(snapshot_mcp_handlers, "handle_create_snapshot"),
        mutation=True,
    ),
    "list_snapshots": ToolSpec(
        _h(snapshot_mcp_handlers, "handle_list_snapshots"),
    ),
    "delete_snapshot": ToolSpec(
        _h(snapshot_mcp_handlers, "handle_delete_snapshot"),
        mutation=True,
    ),
    "compare_states": ToolSpec(
        _h(snapshot_mcp_handlers, "handle_compare_states"),
    ),
    "import_snapshot": ToolSpec(
        _h(snapshot_mcp_handlers, "handle_import_snapshot"),
        mutation=True,
    ),
    # ------------------------------------------------------------------
    # Query catalog tools
    # ------------------------------------------------------------------
    "suggest_queries": ToolSpec(
        _h(catalog_mcp_handlers, "handle_suggest_queries"),
    ),
    "execute_query_template": ToolSpec(
        _h(catalog_mcp_handlers, "handle_execute_query_template"),
    ),
    "describe_schema": ToolSpec(
        _h(catalog_mcp_handlers, "handle_describe_schema"),
    ),
    # ------------------------------------------------------------------
    # Dynamics 365 / Dataverse vertical module tools
    # ------------------------------------------------------------------
    "d365_query_case": ToolSpec(
        _h(d365_mcp_handlers, "handle_d365_query_case"),
        cacheable=True,
    ),
    "d365_sync_now": ToolSpec(
        _h(d365_mcp_handlers, "handle_d365_sync_now"),
        admin_only=True,
        mutation=True,
    ),
    "d365_case_stress_report": ToolSpec(
        _h(d365_mcp_handlers, "handle_d365_case_stress_report"),
        cacheable=True,
    ),
    "d365_list_sla_breaches": ToolSpec(
        _h(d365_mcp_handlers, "handle_d365_list_sla_breaches"),
        admin_only=True,
    ),
    "d365_netbox_mappings": ToolSpec(
        _h(d365_mcp_handlers, "handle_d365_netbox_mappings"),
        cacheable=True,
    ),
    "evaluate_circuit_impact": ToolSpec(
        _h(netbox_circuits, "handle_evaluate_circuit_impact"),
        cacheable=False,
    ),
}

# ---------------------------------------------------------------------------
# Derived sets — computed once at import time
# ---------------------------------------------------------------------------

#: Tools that mutate state — the dispatch layer increments the global cache
#: generation counter before serving these.  Migration-mutation tools
#: (``mutation=True, migration=True``) are included here; the dispatch layer
#: applies the ``NCE_DISABLE_MIGRATION_MCP`` gate separately.
MUTATION_TOOLS: frozenset[str] = frozenset(
    name for name, spec in TOOL_REGISTRY.items() if spec.mutation
)

#: Tools whose successful responses are eligible for Redis caching.
CACHEABLE_TOOLS: frozenset[str] = frozenset(
    name for name, spec in TOOL_REGISTRY.items() if spec.cacheable
)

#: Tools that require admin credentials (``_check_admin`` must pass).
ADMIN_ONLY_TOOLS: frozenset[str] = frozenset(
    name for name, spec in TOOL_REGISTRY.items() if spec.admin_only
)

#: Tools gated by ``cfg.NCE_DISABLE_MIGRATION_MCP``.
MIGRATION_TOOLS: frozenset[str] = frozenset(
    name for name, spec in TOOL_REGISTRY.items() if spec.migration
)
