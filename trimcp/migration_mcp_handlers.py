"""
MCP tool handlers for embedding model migrations (§11). Extracted from server.py:call_tool().
Follows the same pattern as bridge_mcp_handlers.py — each handler receives the engine
and raw arguments dict, and returns a JSON string that call_tool() wraps in TextContent.

RBAC is enforced by the ``@require_scope("admin")`` decorator on every handler.
The decorator validates ``admin_api_key`` against ``TRIMCP_ADMIN_API_KEY`` (constant-time),
strips auth keys from arguments before they reach ``extra='forbid'`` domain models, and
forwards ``admin_identity`` as a keyword argument to handlers that declare it.

Pre-flight WORM audit logging: every migration mutation handler (start_migration,
commit_migration, abort_migration) writes an irrefutable ``append_event`` audit record
on a **separate** PG connection with its own transaction BEFORE the migration
orchestrator is invoked.  If the audit write fails, the migration is rejected —
the audit gate is the security boundary.  The audit connection is independent of
the migration transaction, guaranteeing the audit record survives even if the
migration transaction rolls back.

On scope violation the decorator raises :class:`trimcp.auth.ScopeError`, which
:func:`call_tool` lets propagate unchanged so the MCP framework produces a JSON-RPC
error response (code ``-32005`` — scope forbidden).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from trimcp.auth import require_scope
from trimcp.event_log import append_event
from trimcp.mcp_errors import mcp_handler
from trimcp.orchestrator import TriStackEngine

log = logging.getLogger("trimcp.migration_mcp_handlers")

# System-level namespace sentinel — used for migration audit events that are
# not tenant-scoped.  The nil UUID is the conventional "no namespace" value.
_SYSTEM_NAMESPACE: UUID = UUID("00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# Pre-flight audit helper — writes before the migration transaction begins
# ---------------------------------------------------------------------------


async def _audit_migration_action(
    pg_pool: asyncpg.Pool,
    *,
    event_type: str,
    admin_identity: str | None,
    migration_id: str | None,
    target_model_id: str | None,
    extra_params: dict[str, Any] | None = None,
) -> None:
    """Write an irrefutable pre-flight audit event on a SEPARATE PG connection.

    This connection and transaction are independent of the migration orchestrator's
    transaction — if the migration transaction rolls back, the audit record survives.

    Raises:
        Exception: Any failure (connection, insert, signing) propagates and
            prevents the migration from proceeding.
    """
    params: dict[str, Any] = {}
    if migration_id is not None:
        params["migration_id"] = migration_id
    if target_model_id is not None:
        params["target_model_id"] = target_model_id
    if extra_params:
        params.update(extra_params)

    async with pg_pool.acquire(timeout=10.0) as audit_conn:
        async with audit_conn.transaction():
            result = await append_event(
                conn=audit_conn,
                namespace_id=_SYSTEM_NAMESPACE,
                agent_id=admin_identity or "system",
                event_type=event_type,
                params=params,
            )
    log.info(
        "[migration-audit] %s recorded — event_id=%s event_seq=%d admin=%s",
        event_type,
        result.event_id,
        result.event_seq,
        admin_identity or "system",
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@require_scope("admin")
@mcp_handler
async def handle_start_migration(
    engine: TriStackEngine,
    arguments: dict[str, Any],
    admin_identity: str | None = None,
) -> str:
    """[ADMIN] Start a re-embedding migration to a new model."""
    target_model_id: str = arguments["target_model_id"]

    # Pre-flight WORM audit — written BEFORE the migration transaction begins.
    # Uses a separate PG connection so the audit survives any migration rollback.
    await _audit_migration_action(
        engine.pg_pool,
        event_type="migration_started",
        admin_identity=admin_identity,
        migration_id=None,  # generated inside the orchestrator
        target_model_id=target_model_id,
    )

    res = await engine.start_migration(target_model_id)
    return json.dumps(res)


@require_scope("admin")
@mcp_handler
async def handle_migration_status(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """[ADMIN] Check the status of a running migration."""
    res = await engine.migration_status(arguments["migration_id"])
    return json.dumps(res)


@require_scope("admin")
@mcp_handler
async def handle_validate_migration(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """[ADMIN] Validate the results of a completed migration."""
    res = await engine.validate_migration(arguments["migration_id"])
    return json.dumps(res)


@require_scope("admin")
@mcp_handler
async def handle_commit_migration(
    engine: TriStackEngine,
    arguments: dict[str, Any],
    admin_identity: str | None = None,
) -> str:
    """[ADMIN] Commit a validated migration, switching the active model."""
    migration_id: str = arguments["migration_id"]

    # Pre-flight WORM audit — written BEFORE the schema-switching transaction.
    await _audit_migration_action(
        engine.pg_pool,
        event_type="migration_committed",
        admin_identity=admin_identity,
        migration_id=migration_id,
        target_model_id=None,
    )

    res = await engine.commit_migration(migration_id)
    return json.dumps(res)


@require_scope("admin")
@mcp_handler
async def handle_abort_migration(
    engine: TriStackEngine,
    arguments: dict[str, Any],
    admin_identity: str | None = None,
) -> str:
    """[ADMIN] Abort an in-progress migration."""
    migration_id: str = arguments["migration_id"]

    # Pre-flight WORM audit — written BEFORE the abort transaction.
    await _audit_migration_action(
        engine.pg_pool,
        event_type="migration_aborted",
        admin_identity=admin_identity,
        migration_id=migration_id,
        target_model_id=None,
    )

    res = await engine.abort_migration(migration_id)
    return json.dumps(res)
