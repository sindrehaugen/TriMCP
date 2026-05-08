"""
Snapshot serialization — purely functional data transformation layer.

Extracted from ``snapshot_mcp_handlers.py`` to decouple snapshot data aggregation
and JSON serialization from the MCP transport layer. Every function in this
module is synchronous, stateless, and depends only on Pydantic models — no
engine references, no async I/O, no transport concerns.

Unit-testable without mocks::

    from trimcp.snapshot_serializer import serialize_snapshot_record, SNAPSHOT_ARG_KEYS
    assert SNAPSHOT_ARG_KEYS.NAMESPACE_ID == "namespace_id"
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from trimcp.models import (
    CompareStatesRequest,
    CreateSnapshotRequest,
    SnapshotRecord,
    StateDiffResult,
)

# ── Argument key constants ───────────────────────────────────────────────────
# Replace magic-string lookups in MCP handlers with typed, greppable constants.


@dataclass(frozen=True)
class _SnapshotArgKeys:
    """Dict keys expected in ``arguments`` dicts for snapshot MCP tools.

    Centralising these eliminates magic strings scattered across handler code.
    """

    NAMESPACE_ID: str = "namespace_id"
    NAME: str = "name"
    AGENT_ID: str = "agent_id"
    SNAPSHOT_AT: str = "snapshot_at"
    METADATA: str = "metadata"
    SNAPSHOT_ID: str = "snapshot_id"
    AS_OF_A: str = "as_of_a"
    AS_OF_B: str = "as_of_b"
    QUERY: str = "query"
    TOP_K: str = "top_k"


SNAPSHOT_ARG_KEYS = _SnapshotArgKeys()

# Sentinel for default-agent lookups — avoids repeating "default" as a literal.
_DEFAULT_AGENT_ID: str = "default"
_DEFAULT_TOP_K: int = 10
_DEFAULT_METADATA: dict[str, Any] = {}


# ── Pure serializers ─────────────────────────────────────────────────────────


def serialize_snapshot_record(record: SnapshotRecord) -> str:
    """Serialize a single ``SnapshotRecord`` to a JSON string.

    Args:
        record: A validated snapshot record from the database.

    Returns:
        A JSON string suitable for ``TextContent`` wrapping.
    """
    return json.dumps(record.model_dump(mode="json"))


def serialize_snapshot_list(records: list[SnapshotRecord]) -> str:
    """Serialize a list of ``SnapshotRecord`` to a JSON string."""
    return json.dumps([s.model_dump(mode="json") for s in records])


def serialize_delete_result(result: dict[str, Any]) -> str:
    """Serialize the dict returned by ``delete_snapshot`` to a JSON string.

    The orchestrator returns a plain ``dict`` (not a Pydantic model) for
    delete results, so we serialise directly.
    """
    return json.dumps(result)


def serialize_state_diff(diff: StateDiffResult) -> str:
    """Serialize a ``StateDiffResult`` to a JSON string.

    Args:
        diff: A validated state-diff result from ``compare_states``.

    Returns:
        A JSON string suitable for ``TextContent`` wrapping.
    """
    return json.dumps(diff.model_dump(mode="json"))


# ── Request builders ─────────────────────────────────────────────────────────
# These extract and coerce raw MCP ``arguments`` dict entries into validated
# Pydantic request objects.  Each builder is a pure function — no I/O, no
# engine coupling, trivially unit-testable.


def build_create_snapshot_request(arguments: dict[str, Any]) -> CreateSnapshotRequest:
    """Construct a ``CreateSnapshotRequest`` from a raw MCP arguments dict.

    Args:
        arguments: The raw arguments dict received by ``handle_create_snapshot``.

    Returns:
        A validated ``CreateSnapshotRequest`` instance.
    """
    from trimcp.temporal import parse_as_of

    return CreateSnapshotRequest(
        namespace_id=arguments[SNAPSHOT_ARG_KEYS.NAMESPACE_ID],
        name=arguments[SNAPSHOT_ARG_KEYS.NAME],
        agent_id=arguments.get(SNAPSHOT_ARG_KEYS.AGENT_ID, _DEFAULT_AGENT_ID),
        snapshot_at=parse_as_of(arguments.get(SNAPSHOT_ARG_KEYS.SNAPSHOT_AT)),
        metadata=arguments.get(SNAPSHOT_ARG_KEYS.METADATA, _DEFAULT_METADATA),
    )


def build_compare_states_request(arguments: dict[str, Any]) -> CompareStatesRequest:
    """Construct a ``CompareStatesRequest`` from a raw MCP arguments dict.

    Args:
        arguments: The raw arguments dict received by ``handle_compare_states``.

    Returns:
        A validated ``CompareStatesRequest`` instance.
    """
    from trimcp.temporal import parse_as_of

    as_of_a = parse_as_of(arguments.get(SNAPSHOT_ARG_KEYS.AS_OF_A))
    as_of_b = parse_as_of(arguments.get(SNAPSHOT_ARG_KEYS.AS_OF_B))
    if as_of_a is None or as_of_b is None:
        raise ValueError("compare_states requires both as_of_a and as_of_b timestamps")
    return CompareStatesRequest(
        namespace_id=arguments[SNAPSHOT_ARG_KEYS.NAMESPACE_ID],
        as_of_a=as_of_a,
        as_of_b=as_of_b,
        query=arguments.get(SNAPSHOT_ARG_KEYS.QUERY),
        top_k=int(arguments.get(SNAPSHOT_ARG_KEYS.TOP_K, _DEFAULT_TOP_K)),
    )
