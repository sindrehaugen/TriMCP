"""
Shared database utilities for NCE.

Extracted to break circular imports and centralise security-relevant
session management (scoped_pg_session).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Final
from uuid import UUID

import asyncpg

from nce.observability import SCOPED_SESSION_LATENCY

# Pool checkout timeout — prevents indefinite event-loop stall on exhaustion (FIX-010).
POOL_ACQUIRE_TIMEOUT: Final[float] = 10.0

# Every production use of ``unmanaged_pg_connection`` must register a stable site id
# here after security review (global tables / DDL / legacy non-tenant paths only).
UNMANAGED_PG_AUDITED_SITES: Final[frozenset[str]] = frozenset(
    {
        "cron.consolidation.namespaces_scan",
        "cron.partition_maintenance",
        "cron.saga_recovery.list_stuck",
        "cron.saga_recovery.mark_failed",
        "cron.saga_recovery.mark_completed_no_memory",
        "tasks.code_indexing.legacy_no_namespace",
    }
)


@asynccontextmanager
async def unmanaged_pg_connection(pool: asyncpg.Pool, *, site: str):
    """Acquire a PG connection with bounded wait — no RLS (global/admin paths only).

    WARNING: This does NOT set nce.namespace_id. It bypasses tenant Row Level
    Security entirely. Only use for schema maintenance, global metadata reads, or
    explicitly audited admin operations. Never use for tenant data paths.

    ``site`` must be listed in ``UNMANAGED_PG_AUDITED_SITES`` (enforced at runtime).
    """
    if site not in UNMANAGED_PG_AUDITED_SITES:
        raise ValueError(
            f"unmanaged_pg_connection site {site!r} is not audited. "
            "Add it to UNMANAGED_PG_AUDITED_SITES in nce/db_utils.py after review."
        )
    async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT) as conn:
        yield conn


@asynccontextmanager
async def scoped_pg_session(
    pool: asyncpg.Pool,
    namespace_id: str | UUID,
):
    """
    Context manager for tenant-isolated PostgreSQL sessions.
    Automatically sets 'nce.namespace_id' for RLS enforcement.

    SET LOCAL only persists inside an explicit transaction; this manager wraps
    the entire yielded block in ``conn.transaction()`` so RLS context is
    active for all statements on *conn* (FIX-011).

    The namespace setting is automatically cleared by PostgreSQL when the
    transaction commits or rolls back — no explicit reset is required or
    performed.

    WARNING: Do not perform slow external I/O (Mongo calls, HTTP calls, LLM
    calls, embedding generation) inside this context. The entire yielded
    block runs inside one database transaction; long-held transactions increase
    lock contention and vacuum table bloat.

    Instrumented with SCOPED_SESSION_LATENCY histogram to monitor RLS
    SET LOCAL overhead on the hot path.
    """
    if not namespace_id:
        raise ValueError("namespace_id is required for scoped sessions")

    ns_uuid = UUID(str(namespace_id)) if not isinstance(namespace_id, UUID) else namespace_id
    t0 = time.perf_counter()

    async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT) as conn:
        from nce.auth import set_namespace_context

        async with conn.transaction():
            await set_namespace_context(conn, ns_uuid)
            SCOPED_SESSION_LATENCY.labels(
                namespace_id=str(ns_uuid)[:8],  # truncated for cardinality safety
            ).observe(time.perf_counter() - t0)
            yield conn
            # SET LOCAL is automatically cleared at transaction end.
            # No explicit _reset_rls_context() call: that would run inside the
            # transaction's finally block and can mask the original SQL error if
            # the transaction is already in an aborted state.
