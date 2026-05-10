"""
Shared database utilities for TriMCP.

Extracted to break circular imports and centralise security-relevant
session management (scoped_pg_session).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import UUID

import asyncpg

from trimcp.observability import SCOPED_SESSION_LATENCY


class ConnectionProvider(Protocol):
    """Protocol for anything that can provide an asyncpg connection."""

    async def acquire(self) -> asyncpg.Connection:
        ...


@asynccontextmanager
async def scoped_pg_session(
    pool: asyncpg.Pool,
    namespace_id: str | UUID,
):
    """
    Context manager for tenant-isolated PostgreSQL sessions.
    Automatically sets 'trimcp.namespace_id' for RLS enforcement.

    Instrumented with SCOPED_SESSION_LATENCY histogram (Prompt 28)
    to monitor RLS SET LOCAL overhead on the hot path.
    """
    if not namespace_id:
        raise ValueError("namespace_id is required for scoped sessions")

    ns_uuid = UUID(str(namespace_id)) if not isinstance(namespace_id, UUID) else namespace_id
    t0 = time.perf_counter()

    async with pool.acquire() as conn:
        from trimcp.auth import set_namespace_context

        await set_namespace_context(conn, ns_uuid)
        SCOPED_SESSION_LATENCY.labels(
            namespace_id=str(ns_uuid)[:8],  # truncated for cardinality safety
        ).observe(time.perf_counter() - t0)
        try:
            yield conn
        finally:
            from trimcp.auth import _reset_rls_context

            await _reset_rls_context(conn)
