"""
NamespaceOrchestrator — domain orchestrator for namespace management and quotas.

Extracted from TriStackEngine (Prompt 54, Step 3).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

log = logging.getLogger("tri-stack-orchestrator.namespace")

_NS_DELETE_CHUNK_SIZE = 1_000


async def _delete_namespace_rows_chunked(
    conn: asyncpg.Connection,
    table: str,
    namespace_id: UUID,
) -> None:
    """Delete all rows for namespace_id in 1000-row chunks to limit lock duration."""
    while True:
        result = await conn.execute(
            f"""
            WITH to_delete AS (
                SELECT id FROM {table}
                WHERE namespace_id = $1
                LIMIT $2
            )
            DELETE FROM {table}
            WHERE id IN (SELECT id FROM to_delete)
            """,
            namespace_id,
            _NS_DELETE_CHUNK_SIZE,
        )
        if result == "DELETE 0":
            break
        await asyncio.sleep(0)  # yield event loop between chunks


class NamespaceOrchestrator:
    """Domain orchestrator for namespace CRUD, grants, and quota management."""

    def __init__(self, pg_pool: asyncpg.Pool, redis_client: Any | None = None):
        self.pg_pool = pg_pool
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_uuid(self, val: str | UUID | None) -> UUID | None:
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        return UUID(str(val))

    def scoped_session(self, namespace_id: str | UUID):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _session(ns_id: str | UUID):
            if not ns_id:
                raise ValueError("namespace_id is required")
            ns_uuid = UUID(str(ns_id))
            async with self.pg_pool.acquire() as conn:
                from trimcp.auth import set_namespace_context

                await set_namespace_context(conn, ns_uuid)
                try:
                    yield conn
                finally:
                    from trimcp.auth import _reset_rls_context

                    await _reset_rls_context(conn)

        return _session(namespace_id)

    # ------------------------------------------------------------------
    # Namespace management
    # ------------------------------------------------------------------

    async def manage_namespace(
        self,
        payload,
        admin_identity: str | None = None,
    ) -> dict:
        """
        [Phase 0.1] Admin MCP tool for namespace CRUD and grants.

        *admin_identity* is the authenticated principal identifier (e.g. from JWT
        claims or API-key metadata).  Falls back to ``"admin"`` when not provided
        (legacy / single-user mode).

        Admin bypass note: list / create / grant / revoke operate
        cross-namespace by design and intentionally use raw
        ``pg_pool.acquire()``.  ``update_metadata`` targets a single
        namespace and uses ``scoped_session()`` for RLS consistency.
        """
        from trimcp.models import ManageNamespaceCommand

        _agent_id = admin_identity or "admin"

        if payload.command == ManageNamespaceCommand.create:
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """
                        INSERT INTO namespaces (slug, parent_id, metadata)
                        VALUES ($1, $2, $3)
                        RETURNING id, slug, parent_id, created_at, metadata
                        """,
                        payload.create.slug,
                        payload.create.parent_id,
                        payload.create.metadata.model_dump_json(),
                    )
                    from trimcp.event_log import append_event

                    await append_event(
                        conn=conn,
                        namespace_id=row["id"],
                        agent_id=_agent_id,
                        event_type="namespace_created",
                        params={
                            "slug": payload.create.slug,
                            "parent_id": (
                                str(payload.create.parent_id)
                                if payload.create.parent_id
                                else None
                            ),
                        },
                    )
                return dict(row)

        if payload.command == ManageNamespaceCommand.list:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM namespaces ORDER BY created_at DESC"
                )
                return {"namespaces": [dict(r) for r in rows]}

        if payload.command == ManageNamespaceCommand.update_metadata:
            async with self.scoped_session(payload.namespace_id) as conn:
                old_meta_json = await conn.fetchval(
                    "SELECT metadata FROM namespaces WHERE id = $1",
                    payload.namespace_id,
                )
                if not old_meta_json:
                    raise ValueError(f"Namespace {payload.namespace_id} not found")

                old_meta = json.loads(old_meta_json)
                old_meta.update(payload.metadata_patch.model_dump(exclude_none=True))

                from trimcp.models import NamespaceMetadata

                validated = NamespaceMetadata(**old_meta)

                await conn.execute(
                    "UPDATE namespaces SET metadata = $1 WHERE id = $2",
                    validated.model_dump_json(),
                    payload.namespace_id,
                )

                from trimcp.event_log import append_event

                await append_event(
                    conn=conn,
                    namespace_id=payload.namespace_id,
                    agent_id=_agent_id,
                    event_type="namespace_metadata_updated",
                    params={
                        "old_metadata": old_meta_json,
                        "new_metadata": validated.model_dump_json(),
                    },
                )
                return {"status": "ok", "metadata": validated.model_dump()}

        if payload.command == ManageNamespaceCommand.grant:
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE namespaces SET parent_id = $1 WHERE id = $2",
                        payload.namespace_id,
                        payload.grantee_namespace_id,
                    )
                    from trimcp.event_log import append_event

                    await append_event(
                        conn=conn,
                        namespace_id=payload.grantee_namespace_id,
                        agent_id=_agent_id,
                        event_type="namespace_access_granted",
                        params={
                            "granting_namespace_id": str(payload.namespace_id),
                            "grantee_namespace_id": str(payload.grantee_namespace_id),
                        },
                    )
                return {
                    "status": "ok",
                    "message": f"Namespace {payload.grantee_namespace_id} granted access to {payload.namespace_id}",
                }

        if payload.command == ManageNamespaceCommand.revoke:
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE namespaces SET parent_id = NULL WHERE id = $1 AND parent_id = $2",
                        payload.grantee_namespace_id,
                        payload.namespace_id,
                    )
                    from trimcp.event_log import append_event

                    await append_event(
                        conn=conn,
                        namespace_id=payload.grantee_namespace_id,
                        agent_id=_agent_id,
                        event_type="namespace_access_revoked",
                        params={
                            "revoking_namespace_id": str(payload.namespace_id),
                            "revokee_namespace_id": str(payload.grantee_namespace_id),
                        },
                    )
                return {
                    "status": "ok",
                    "message": f"Access revoked for {payload.grantee_namespace_id}",
                }

        if payload.command == ManageNamespaceCommand.delete:
            if not payload.namespace_id:
                raise ValueError("namespace_id required for delete")

            # Purge MCP cache entries for this namespace BEFORE deletion.
            if self._redis is not None:
                from trimcp.mcp_args import purge_namespace_cache

                try:
                    await purge_namespace_cache(self._redis, str(payload.namespace_id))
                except Exception as exc:
                    log.warning(
                        "Namespace delete: cache purge failed for %s: %s",
                        payload.namespace_id,
                        exc,
                    )

            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    # Large tables — chunked to limit per-statement lock duration.
                    for table in ("event_log", "memories", "memory_salience", "kg_nodes"):
                        await _delete_namespace_rows_chunked(conn, table, payload.namespace_id)

                    # KG edges span two namespace columns; use a direct DELETE.
                    while True:
                        result = await conn.execute(
                            """
                            WITH to_delete AS (
                                SELECT id FROM kg_edges
                                WHERE source_namespace_id = $1 OR target_namespace_id = $1
                                LIMIT $2
                            )
                            DELETE FROM kg_edges WHERE id IN (SELECT id FROM to_delete)
                            """,
                            payload.namespace_id,
                            _NS_DELETE_CHUNK_SIZE,
                        )
                        if result == "DELETE 0":
                            break
                        await asyncio.sleep(0)

                    # Small tables — single-shot deletes are safe.
                    for table in ("contradictions", "resource_quotas", "embedding_migrations"):
                        await conn.execute(
                            f"DELETE FROM {table} WHERE namespace_id = $1",
                            payload.namespace_id,
                        )
                    # Finally delete the namespace record itself.
                    result = await conn.execute(
                        "DELETE FROM namespaces WHERE id = $1",
                        payload.namespace_id,
                    )

                    from trimcp.event_log import append_event

                    await append_event(
                        conn=conn,
                        namespace_id=payload.namespace_id,
                        agent_id=_agent_id,
                        event_type="namespace_deleted",
                        params={"namespace_id": str(payload.namespace_id)},
                    )

            if result == "DELETE 0":
                raise ValueError(f"Namespace {payload.namespace_id} not found")

            # Bump global cache generation as a secondary invalidation signal.
            if self._redis is not None:
                from trimcp.mcp_args import bump_cache_generation

                try:
                    await bump_cache_generation(self._redis)
                except Exception as exc:
                    log.warning("Namespace delete: global cache bump failed: %s", exc)

            return {
                "status": "ok",
                "message": f"Namespace {payload.namespace_id} deleted",
            }

        raise ValueError(f"Unsupported command: {payload.command}")

    # ------------------------------------------------------------------
    # Quota management
    # ------------------------------------------------------------------

    async def manage_quotas(self, payload) -> dict:
        """
        [Phase 3.2] Admin MCP tool for resource quota management.
        Uses scoped_session so RLS on resource_quotas filters correctly.
        """
        from trimcp.models import ManageQuotasCommand

        async with self.scoped_session(payload.namespace_id) as conn:
            if payload.command == ManageQuotasCommand.set:
                row = await conn.fetchrow(
                    """
                    INSERT INTO resource_quotas (namespace_id, agent_id, resource_type, limit_amount)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (namespace_id, resource_type) WHERE agent_id IS NULL DO UPDATE
                        SET limit_amount = EXCLUDED.limit_amount,
                            updated_at = now()
                    ON CONFLICT (namespace_id, agent_id, resource_type) WHERE agent_id IS NOT NULL DO UPDATE
                        SET limit_amount = EXCLUDED.limit_amount,
                            updated_at = now()
                    RETURNING *
                    """,
                    payload.namespace_id,
                    payload.agent_id,
                    payload.resource_type,
                    payload.limit,
                )
                return dict(row)

            if payload.command == ManageQuotasCommand.list:
                rows = await conn.fetch(
                    "SELECT * FROM resource_quotas WHERE namespace_id = $1 ORDER BY created_at DESC",
                    payload.namespace_id,
                )
                return {"quotas": [dict(r) for r in rows]}

            if payload.command == ManageQuotasCommand.delete:
                await conn.execute(
                    """
                    DELETE FROM resource_quotas 
                    WHERE namespace_id = $1 AND resource_type = $2 
                      AND (agent_id IS NOT DISTINCT FROM $3)
                    """,
                    payload.namespace_id,
                    payload.resource_type,
                    payload.agent_id,
                )
                return {
                    "status": "ok",
                    "message": f"Quota for {payload.resource_type} deleted",
                }

            if payload.command == ManageQuotasCommand.reset:
                await conn.execute(
                    """
                    UPDATE resource_quotas 
                    SET used_amount = 0, updated_at = now()
                    WHERE namespace_id = $1 AND resource_type = $2 
                      AND (agent_id IS NOT DISTINCT FROM $3)
                    """,
                    payload.namespace_id,
                    payload.resource_type,
                    payload.agent_id,
                )
                return {
                    "status": "ok",
                    "message": f"Usage reset for {payload.resource_type}",
                }

        raise ValueError(f"Unsupported quota command: {payload.command}")
