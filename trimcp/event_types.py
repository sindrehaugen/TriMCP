"""
Central definitions for ``event_log.event_type`` values.

Kept free of imports from other ``trimcp`` packages so ``auth``, ``event_log``,
and ``replay`` can share the type set without circular dependencies.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

# Every value must stay in sync with replay handler registry coverage in
# ``trimcp.replay`` (ForkedReplay validates on construction).

EventType = Literal[
    "store_memory",
    "store_memory_rolled_back",
    "forget_memory",
    "boost_memory",
    "resolve_contradiction",
    "consolidation_run",
    "pii_redaction",
    "snapshot_created",
    "unredact",
    "namespace_access_granted",
    "namespace_access_revoked",
    "namespace_created",
    "namespace_metadata_updated",
    "namespace_impersonated",
    "namespace_deleted",
    "migration_started",
    "migration_committed",
    "migration_aborted",
]

VALID_EVENT_TYPES: Final[frozenset[str]] = frozenset(get_args(EventType))

__all__ = ["EventType", "VALID_EVENT_TYPES"]
