"""
Shared database utilities for TriMCP.

Extracted to break circular imports and centralise security-relevant
session management (scoped_pg_session).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Final
from uuid import UUID

import asyncpg

from trimcp.observability import SCOPED_SESSION_LATENCY

# Pool checkout timeout — prevents indefinite event-loop stall on exhaustion (FIX-010).
POOL_ACQUIRE_TIMEOUT: Final[float] = 10.0


@asynccontextmanager
async def unmanaged_pg_connection(pool: asyncpg.Pool):
    """Acquire a PG connection with bounded wait — no RLS (global/admin paths only)."""
    async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT) as conn:
        yield conn


@asynccontextmanager
async def scoped_pg_session(
    pool: asyncpg.Pool,
    namespace_id: str | UUID,
):
    """
    Context manager for tenant-isolated PostgreSQL sessions.
    Automatically sets 'trimcp.namespace_id' for RLS enforcement.

    SET LOCAL only persists inside an explicit transaction; this manager wraps
    the entire yielded block in ``conn.transaction()`` so RLS context is
    active for all statements on *conn* (FIX-011).

    Instrumented with SCOPED_SESSION_LATENCY histogram (Prompt 28)
    to monitor RLS SET LOCAL overhead on the hot path.
    """
    if not namespace_id:
        raise ValueError("namespace_id is required for scoped sessions")

    ns_uuid = UUID(str(namespace_id)) if not isinstance(namespace_id, UUID) else namespace_id
    t0 = time.perf_counter()

    async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT) as conn:
        from trimcp.auth import set_namespace_context

        async with conn.transaction():
            await set_namespace_context(conn, ns_uuid)
            SCOPED_SESSION_LATENCY.labels(
                namespace_id=str(ns_uuid)[:8],  # truncated for cardinality safety
            ).observe(time.perf_counter() - t0)
            try:
                yield conn
            finally:
                from trimcp.auth import _reset_rls_context

                await _reset_rls_context(conn)
