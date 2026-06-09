"""Structural contract tests for nce.tool_registry.

These tests pin the exact shape of TOOL_REGISTRY and its derived sets so that
accidental additions, removals, or mis-classification of tool metadata are
caught before any dispatch refactor goes live.

Run this suite before and after Batch 2.2 (dispatch rewrite) to verify that
the registry exactly mirrors the behaviour encoded in the original if-ladder.
"""

from __future__ import annotations

import inspect

import pytest
from nce.tool_registry import (
    ADMIN_ONLY_TOOLS,
    CACHEABLE_TOOLS,
    MIGRATION_TOOLS,
    MUTATION_TOOLS,
    TOOL_REGISTRY,
)

# ---------------------------------------------------------------------------
# Cardinality
# ---------------------------------------------------------------------------

_EXPECTED_TOTAL = 61


def test_registry_has_61_entries():
    assert len(TOOL_REGISTRY) == _EXPECTED_TOTAL, (
        f"Expected {_EXPECTED_TOTAL} tools, got {len(TOOL_REGISTRY)}. "
        f"Tools: {sorted(TOOL_REGISTRY)}"
    )


# ---------------------------------------------------------------------------
# Handler callability
# ---------------------------------------------------------------------------


def test_all_handlers_are_async_callables():
    """Every registered handler must be an awaitable (async def) callable."""
    bad = [
        name
        for name, spec in TOOL_REGISTRY.items()
        if not (callable(spec.handler) and inspect.iscoroutinefunction(spec.handler))
    ]
    assert not bad, f"Non-async handlers found: {bad}"


# ---------------------------------------------------------------------------
# MUTATION_TOOLS — exact match with the hardcoded set from the old dispatch
# ---------------------------------------------------------------------------

# Ground truth for MUTATION_TOOLS.
# Base set (22) was copied from the original dispatch's _base_mutation_tools.
# replay_dlq and purge_dlq were added (review finding #1) — both write to the
# dead_letter_queue table and were erroneously absent from the original set.
_EXPECTED_MUTATION_TOOLS: frozenset[str] = frozenset(
    {
        # base set (22) — from pre-refactor mcp_stdio_dispatch._base_mutation_tools
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
        "a2a_update_grant_scopes",
        "unredact_memory",
        "replay_reconstruct",
        # DLQ mutations (2) — pre-existing omission corrected in code review
        "replay_dlq",
        "purge_dlq",
        # migration mutations (3) — always present in the registry;
        # the dispatch gate (NCE_DISABLE_MIGRATION_MCP) is applied separately.
        "start_migration",
        "commit_migration",
        "abort_migration",
        # D365 mutations
        "d365_sync_now",
    }
)


def test_mutation_tools_exact_match():
    assert MUTATION_TOOLS == _EXPECTED_MUTATION_TOOLS, (
        f"Extra: {MUTATION_TOOLS - _EXPECTED_MUTATION_TOOLS}  "
        f"Missing: {_EXPECTED_MUTATION_TOOLS - MUTATION_TOOLS}"
    )


def test_mutation_tools_count():
    assert len(MUTATION_TOOLS) == 28


# ---------------------------------------------------------------------------
# CACHEABLE_TOOLS
# ---------------------------------------------------------------------------

_EXPECTED_CACHEABLE: frozenset[str] = frozenset(
    {
        "semantic_search",
        "search_codebase",
        "graph_search",
        "neuromorphic_search",
        "d365_query_case",
        "d365_case_stress_report",
        "d365_netbox_mappings",
    }
)


def test_cacheable_tools_exact_match():
    assert CACHEABLE_TOOLS == _EXPECTED_CACHEABLE, (
        f"Extra: {CACHEABLE_TOOLS - _EXPECTED_CACHEABLE}  "
        f"Missing: {_EXPECTED_CACHEABLE - CACHEABLE_TOOLS}"
    )


def test_cacheable_tools_count():
    assert len(CACHEABLE_TOOLS) == 7


# ---------------------------------------------------------------------------
# ADMIN_ONLY_TOOLS
# ---------------------------------------------------------------------------

_EXPECTED_ADMIN_ONLY: frozenset[str] = frozenset(
    {
        "unredact_memory",
        "replay_observe",
        "replay_reconstruct",
        "replay_fork",
        "replay_status",
        "d365_sync_now",
        "d365_list_sla_breaches",
    }
)


def test_admin_only_tools_exact_match():
    assert ADMIN_ONLY_TOOLS == _EXPECTED_ADMIN_ONLY, (
        f"Extra: {ADMIN_ONLY_TOOLS - _EXPECTED_ADMIN_ONLY}  "
        f"Missing: {_EXPECTED_ADMIN_ONLY - ADMIN_ONLY_TOOLS}"
    )


def test_admin_only_tools_count():
    assert len(ADMIN_ONLY_TOOLS) == 7


# ---------------------------------------------------------------------------
# MIGRATION_TOOLS
# ---------------------------------------------------------------------------

_EXPECTED_MIGRATION: frozenset[str] = frozenset(
    {
        "start_migration",
        "migration_status",
        "validate_migration",
        "commit_migration",
        "abort_migration",
    }
)


def test_migration_tools_exact_match():
    assert MIGRATION_TOOLS == _EXPECTED_MIGRATION, (
        f"Extra: {MIGRATION_TOOLS - _EXPECTED_MIGRATION}  "
        f"Missing: {_EXPECTED_MIGRATION - MIGRATION_TOOLS}"
    )


def test_migration_tools_count():
    assert len(MIGRATION_TOOLS) == 5


# ---------------------------------------------------------------------------
# Derived-set consistency
# ---------------------------------------------------------------------------


def test_mutation_tools_subset_of_registry():
    assert MUTATION_TOOLS <= TOOL_REGISTRY.keys()


def test_cacheable_tools_subset_of_registry():
    assert CACHEABLE_TOOLS <= TOOL_REGISTRY.keys()


def test_admin_only_tools_subset_of_registry():
    assert ADMIN_ONLY_TOOLS <= TOOL_REGISTRY.keys()


def test_migration_tools_subset_of_registry():
    assert MIGRATION_TOOLS <= TOOL_REGISTRY.keys()


def test_migration_mutations_are_in_mutation_tools():
    """All migration tools marked mutation=True must appear in MUTATION_TOOLS."""
    migration_mutations = {
        name for name, spec in TOOL_REGISTRY.items() if spec.migration and spec.mutation
    }
    assert migration_mutations <= MUTATION_TOOLS


def test_no_tool_is_cacheable_and_mutation():
    """Cacheable and mutation are logically exclusive — a write should not be cached."""
    overlap = CACHEABLE_TOOLS & MUTATION_TOOLS
    assert not overlap, f"Tools are both cacheable and mutation: {overlap}"


# ---------------------------------------------------------------------------
# ToolSpec frozen-ness
# ---------------------------------------------------------------------------


def test_toolspec_is_frozen():
    spec = TOOL_REGISTRY["get_health"]
    with pytest.raises((AttributeError, TypeError)):
        spec.admin_only = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Spot-checks for a representative sample of each domain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,expected_flags",
    [
        # memory
        (
            "store_memory",
            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
        ),
        (
            "semantic_search",
            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
        ),
        (
            "unredact_memory",
            {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
        ),
        # code
        (
            "index_code_file",
            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
        ),
        (
            "search_codebase",
            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
        ),
        # graph
        (
            "graph_search",
            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
        ),
        (
            "neuromorphic_search",
            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
        ),
        # bridges
        (
            "connect_bridge",
            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
        ),
        (
            "list_bridges",
            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
        ),
        # migration
        (
            "start_migration",
            {"mutation": True, "cacheable": False, "admin_only": False, "migration": True},
        ),
        (
            "migration_status",
            {"mutation": False, "cacheable": False, "admin_only": False, "migration": True},
        ),
        (
            "commit_migration",
            {"mutation": True, "cacheable": False, "admin_only": False, "migration": True},
        ),
        # replay
        (
            "replay_observe",
            {"mutation": False, "cacheable": False, "admin_only": True, "migration": False},
        ),
        (
            "replay_reconstruct",
            {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
        ),
        (
            "get_event_provenance",
            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
        ),
        # a2a
        (
            "a2a_create_grant",
            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
        ),
        (
            "a2a_list_grants",
            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
        ),
        # admin
        (
            "manage_namespace",
            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
        ),
        (
            "get_health",
            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
        ),
        # snapshots
        (
            "create_snapshot",
            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
        ),
        (
            "compare_states",
            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
        ),
        # catalog
        (
            "suggest_queries",
            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
        ),
        # d365
        (
            "d365_query_case",
            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
        ),
        (
            "d365_sync_now",
            {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
        ),
        (
            "d365_case_stress_report",
            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
        ),
        (
            "d365_list_sla_breaches",
            {"mutation": False, "cacheable": False, "admin_only": True, "migration": False},
        ),
        (
            "evaluate_circuit_impact",
            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
        ),
    ],
)
def test_tool_flags(tool_name: str, expected_flags: dict):
    spec = TOOL_REGISTRY[tool_name]
    for flag, expected in expected_flags.items():
        actual = getattr(spec, flag)
        assert actual == expected, f"{tool_name}.{flag}: expected {expected!r}, got {actual!r}"


@pytest.mark.asyncio
async def test_handle_neuromorphic_search_success():
    import json
    from unittest.mock import AsyncMock, MagicMock

    from nce.graph_mcp_handlers import handle_neuromorphic_search
    from nce.graph_query import Subgraph

    # Mock engine and traverser
    mock_engine = MagicMock()
    mock_traverser = AsyncMock()
    mock_engine._graph_traverser = mock_traverser

    # Mock subgraph result
    dummy_subgraph = Subgraph(anchor="mock_anchor")
    mock_traverser.neuromorphic_search.return_value = dummy_subgraph

    # Valid arguments
    args = {
        "namespace_id": "00000000-0000-4000-8000-000000000001",
        "query": "test query",
        "telemetry_severity": 0.8,
        "theta": 0.6,
        "decay": 0.9,
        "alpha": 1.1,
        "ticks": 3,
        "max_depth": 3,
        "anchor_top_k": 2,
    }

    # Call handler
    resp = await handle_neuromorphic_search(mock_engine, args)
    resp_dict = json.loads(resp)

    assert resp_dict["anchor"] == "mock_anchor"
    mock_traverser.neuromorphic_search.assert_called_once_with(
        query="test query",
        namespace_id="00000000-0000-4000-8000-000000000001",
        max_depth=3,
        anchor_top_k=2,
        user_id=None,
        private=False,
        as_of=None,
        max_edges_per_node=512,
        edge_limit=None,
        edge_offset=0,
        telemetry_severity=0.8,
        theta=0.6,
        decay=0.9,
        alpha=1.1,
        ticks=3,
    )
