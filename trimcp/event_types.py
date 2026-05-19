"""
Central definitions for ``event_log.event_type`` values.

Kept free of imports from other ``trimcp`` packages so ``auth``, ``event_log``,
and ``replay`` can share the type set without circular dependencies.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

# Every value must stay in sync with replay handler registry coverage in
# ``trimcp.replay`` (ForkedReplay validates on construction).

# Logical groupings guide ``EventType`` below (single flat ``Literal`` keeps
# ``get_args(EventType)`` correct for runtime validation).

EventType = Literal[
    # MEMORY_EVENTS
    "store_memory",
    "store_memory_rolled_back",
    "forget_memory",
    "boost_memory",
    # COGNITIVE_EVENTS
    "resolve_contradiction",
    "consolidation_run",
    # SECURITY_EVENTS — PII / snapshot / cryptographic redaction probes
    "pii_redaction",
    "snapshot_created",
    "unredact",
    # NAMESPACE_EVENTS
    "namespace_access_granted",
    "namespace_access_revoked",
    "namespace_created",
    "namespace_metadata_updated",
    "namespace_impersonated",
    # Soft-delete / lifecycle (``namespace_deleted`` removed — WORM FK blocks emit-then-hard-delete).
    "namespace_deletion_requested",
    "namespace_disabled",
    # MIGRATION_EVENTS (pre-flight audit — engine not yet invoked)
    "migration_start_requested",
    "migration_commit_requested",
    "migration_abort_requested",
    # MIGRATION_EVENTS (legacy names — retained for historical event_log rows)
    "migration_started",
    "migration_committed",
    "migration_aborted",
    # A2A_EVENTS
    "a2a_grant_created",
    "a2a_grant_revoked",
    "a2a_shared_query",
    # SECURITY_EVENTS — key rotation audit
    "signing_key_rotated",
    # SAGA_EVENTS
    "saga_recovered",  # cron saga recovery: pg_committed saga finalized, not rolled back
]

VALID_EVENT_TYPES: Final[frozenset[str]] = frozenset(get_args(EventType))

# -----------------------------------------------------------------------------
# Payload contracts for ``append_event(..., params=...)``.
# Only event types listed here are validated beyond JSON-serialisability /
# `_validate_params_no_backdated_timestamp`. Omit a type entirely to impose
# no required/forbidden constraints (replay may add fork metadata keys freely).
# -----------------------------------------------------------------------------

EVENT_REQUIRED_PARAM_KEYS: Final[dict[str, frozenset[str]]] = {
    "store_memory": frozenset(
        {
            "saga_id",
            "memory_id",
            "payload_ref",
            "assertion_type",
            "entities",
            "triplets",
        }
    ),
    "store_memory_rolled_back": frozenset({"saga_id", "memory_id", "reason", "payload_ref"}),
    "forget_memory": frozenset({"memory_id"}),
    "boost_memory": frozenset({"memory_id", "factor"}),
    "resolve_contradiction": frozenset({"contradiction_id", "resolution"}),
    "consolidation_run": frozenset(
        {
            "abstraction",
            "key_entities",
            "key_relations",
            "supporting_memory_ids",
            "contradicting_memory_ids",
            "confidence",
            "source_memories",
            "consolidated_memory_id",
            "payload_ref",
        }
    ),
    "pii_redaction": frozenset({"memory_id"}),
    "snapshot_created": frozenset({"snapshot_id", "name", "snapshot_at"}),
    "unredact": frozenset({"memory_id"}),
    "namespace_created": frozenset({"slug"}),
    "namespace_metadata_updated": frozenset({"old_metadata", "new_metadata"}),
    "namespace_disabled": frozenset({"was_disabled"}),
    "namespace_access_granted": frozenset({"granting_namespace_id", "grantee_namespace_id"}),
    "namespace_access_revoked": frozenset({"revoking_namespace_id", "revokee_namespace_id"}),
    "namespace_impersonated": frozenset({"impersonated_namespace_id", "impersonating_agent"}),
    "migration_start_requested": frozenset({"target_model_id"}),
    "migration_commit_requested": frozenset({"migration_id"}),
    "migration_abort_requested": frozenset({"migration_id"}),
    "migration_started": frozenset({"target_model_id"}),
    "migration_committed": frozenset({"migration_id"}),
    "migration_aborted": frozenset({"migration_id"}),
    "a2a_grant_created": frozenset({"grant_id", "target_agent_id", "scope_count", "expires_at"}),
    "a2a_grant_revoked": frozenset({"grant_id"}),
    "saga_recovered": frozenset({"memory_id", "saga_id", "recovery_action", "reason"}),
}

EVENT_FORBIDDEN_PARAM_KEYS: Final[dict[str, frozenset[str]]] = {
    # Prevent accidentally mixing audit vocabulary into the wrong event shape.
    "unredact": frozenset({"pii_redaction"}),
    "pii_redaction": frozenset({"unredact"}),
    # Never persist raw bearer material or hashed secrets in provenance payloads.
    "a2a_grant_created": frozenset({"sharing_token", "token_hash", "scopes"}),
    "a2a_grant_revoked": frozenset({"sharing_token", "token_hash"}),
}


__all__ = [
    "EventType",
    "VALID_EVENT_TYPES",
    "EVENT_REQUIRED_PARAM_KEYS",
    "EVENT_FORBIDDEN_PARAM_KEYS",
]
