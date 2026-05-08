"""
CognitiveOrchestrator — domain orchestrator for salience boosts, forgetting, and contradictions.

Extracted from TriStackEngine (Prompt 54, Step 4).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

log = logging.getLogger("tri-stack-orchestrator.cognitive")


class CognitiveOrchestrator:
    """Domain orchestrator for salience management and contradiction resolution."""

    def __init__(self, pg_pool: asyncpg.Pool):
        self.pg_pool = pg_pool

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_uuid(self, val: str | UUID | None) -> UUID | None:
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        return UUID(str(val))

    async def scoped_session(self, namespace_id: str | UUID):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _session(ns_id: str | UUID):
            if not ns_id:
                raise ValueError("namespace_id is required")
            ns_uuid = UUID(str(ns_id))
            async with self.pg_pool.acquire() as conn:
                from trimcp.auth import set_namespace_context

                await set_namespace_context(conn, ns_uuid)
                yield conn

        return _session(namespace_id)

    # ------------------------------------------------------------------
    # Salience — boost_memory
    # ------------------------------------------------------------------

    async def boost_memory(
        self,
        memory_id: str,
        agent_id: str,
        namespace_id: str,
        factor: float = 0.2,
    ) -> dict:
        """[Phase 1.1] Boost the salience of a memory for the calling agent.

        Uses scoped_session to enforce RLS — the caller can only boost
        memories within their own namespace (defense-in-depth on top of
        the namespace_isolation_policy).  Fixes P0 RLS bypass (Item 3,
        Phase 3).
        """
        factor = max(0.0, min(1.0, factor))
        from trimcp.salience import reinforce

        async with self.scoped_session(namespace_id) as conn:
            async with conn.transaction():
                await reinforce(conn, memory_id, agent_id, namespace_id, delta=factor)

                from trimcp.event_log import append_event

                await append_event(
                    conn=conn,
                    namespace_id=namespace_id,
                    agent_id=agent_id,
                    event_type="boost_memory",
                    params={"memory_id": memory_id, "factor": factor},
                    result_summary={"status": "success"},
                )
        return {"status": "success", "boosted_by": factor}

    # ------------------------------------------------------------------
    # Salience — forget_memory
    # ------------------------------------------------------------------

    async def forget_memory(
        self,
        memory_id: str,
        agent_id: str,
        namespace_id: str,
    ) -> dict:
        """[Phase 1.1] Set salience to 0.0 for the calling agent.

        Uses scoped_session to enforce RLS — the caller can only forget
        memories within their own namespace (defense-in-depth on top of
        the namespace_isolation_policy).
        """
        async with self.scoped_session(namespace_id) as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO memory_salience
                        (memory_id, agent_id, namespace_id, salience_score,
                         updated_at, access_count)
                    VALUES ($1::uuid, $2, $3::uuid, 0.0, NOW(), 1)
                    ON CONFLICT (memory_id, agent_id) DO UPDATE
                        SET salience_score = 0.0,
                            updated_at = NOW(),
                            access_count = memory_salience.access_count + 1
                    """,
                    memory_id,
                    agent_id,
                    namespace_id,
                )

                from trimcp.event_log import append_event

                await append_event(
                    conn=conn,
                    namespace_id=namespace_id,
                    agent_id=agent_id,
                    event_type="forget_memory",
                    params={"memory_id": memory_id},
                    result_summary={"status": "success"},
                )
        return {"status": "success", "forgotten": True}

    # ------------------------------------------------------------------
    # Contradictions
    # ------------------------------------------------------------------

    async def list_contradictions(
        self,
        namespace_id: str,
        resolution: str | None = None,
        agent_id: str | None = None,
    ) -> list[dict]:
        """[Phase 1.3] List contradictions."""
        async with self.scoped_session(namespace_id) as conn:
            query = "SELECT * FROM contradictions WHERE namespace_id = $1"
            params: list = [UUID(namespace_id)]
            idx = 2
            if resolution:
                query += f" AND resolution = ${idx}"
                params.append(resolution)
                idx += 1
            if agent_id:
                query += f" AND agent_id = ${idx}"
                params.append(agent_id)
                idx += 1

            query += " ORDER BY detected_at DESC LIMIT 50"
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    async def resolve_contradiction(
        self,
        contradiction_id: str,
        namespace_id: str,
        resolution: str,
        resolved_by: str,
        note: str | None = None,
    ) -> dict:
        """[Phase 1.3] Resolve a contradiction — RLS-enforced via scoped_session.

        Uses a namespace-scoped PG session so the RLS policy on ``contradictions``
        automatically rejects cross-tenant mutations.  The UPDATE includes an
        explicit ``namespace_id = $2::uuid`` filter as defense-in-depth on top
        of RLS.  A caller from namespace A cannot resolve a contradiction in
        namespace B — the UPDATE returns zero rows and ``PermissionError`` is raised.

        The resolution event is cryptographically signed à la WORM contract via
        ``append_event``.
        """
        ns_uuid = self._ensure_uuid(namespace_id)

        async with self.scoped_session(ns_uuid) as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    UPDATE contradictions
                    SET resolution = $3, resolved_at = now(), resolved_by = $4,
                        note = COALESCE($5, note)
                    WHERE id = $1
                      AND namespace_id = $2::uuid
                    RETURNING *
                    """,
                    UUID(contradiction_id),
                    ns_uuid,
                    resolution,
                    resolved_by,
                    note,
                )
                if not row:
                    raise PermissionError(
                        f"Contradiction {contradiction_id} not accessible in your namespace"
                    )

                from trimcp.event_log import append_event

                await append_event(
                    conn=conn,
                    namespace_id=ns_uuid,
                    agent_id=resolved_by,
                    event_type="resolve_contradiction",
                    params={
                        "contradiction_id": contradiction_id,
                        "resolution": resolution,
                        "note": (note or "")[:256],
                    },
                    result_summary={"status": "success"},
                )

                return dict(row)
