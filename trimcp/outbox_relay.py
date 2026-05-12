"""Transactional Outbox Relay — adapter for ordered, at-most-once delivery."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

log = logging.getLogger("trimcp.outbox_relay")


async def poll_outbox(
    pg_pool: asyncpg.Pool,
    *,
    batch_size: int = 100,
    poll_interval_seconds: float = 5.0,
) -> list[dict[str, Any]]:
    """Poll unpublished outbox events.

    Skeleton — returns up to *batch_size* unpublished rows without
    delivering them.  Production wiring will iterate, deliver to
    downstream consumers, and UPDATE published_at.
    """
    async with pg_pool.acquire(timeout=10.0) as conn:
        rows = await conn.fetch(
            """
            SELECT id, aggregate_type, aggregate_id, event_type, payload, headers, created_at
            FROM outbox_events
            WHERE published_at IS NULL
            ORDER BY created_at ASC
            LIMIT $1
            FOR UPDATE SKIP LOCKED
            """,
            batch_size,
        )
        return [dict(r) for r in rows]
