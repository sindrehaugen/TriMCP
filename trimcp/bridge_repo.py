"""
PostgreSQL access for `bridge_subscriptions` (Appendix H.2 / GAPS audit).
Used by MCP bridge tools and the renewal cron.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

import asyncpg

# asyncpg.Record behaves like Mapping for known keys


async def insert_subscription(
    conn: asyncpg.Connection,
    *,
    user_id: str,
    provider: str,
    resource_id: str,
    status: str = "REQUESTED",
    subscription_id: Optional[str] = None,
    cursor: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    client_state: Optional[str] = None,
    row_id: Optional[uuid.UUID] = None,
) -> uuid.UUID:
    rid = row_id or uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO bridge_subscriptions (
            id, user_id, provider, resource_id, subscription_id,
            cursor, status, expires_at, client_state, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
        """,
        rid,
        user_id,
        provider,
        resource_id,
        subscription_id,
        cursor,
        status,
        expires_at,
        client_state,
    )
    return rid


async def fetch_expiring(
    conn: asyncpg.Connection,
    *,
    within: timedelta,
    limit: int = 100,
) -> List[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT *
        FROM bridge_subscriptions
        WHERE status = 'ACTIVE'
          AND expires_at IS NOT NULL
          AND expires_at < NOW() + $1::interval
        ORDER BY expires_at ASC
        LIMIT $2
        """,
        within,
        limit,
    )


async def get_by_id(conn: asyncpg.Connection, bridge_id: uuid.UUID) -> Optional[asyncpg.Record]:
    return await conn.fetchrow(
        "SELECT * FROM bridge_subscriptions WHERE id = $1",
        bridge_id,
    )


async def list_for_user(
    conn: asyncpg.Connection,
    user_id: str,
    *,
    include_disconnected: bool = False,
) -> List[asyncpg.Record]:
    if include_disconnected:
        return await conn.fetch(
            """
            SELECT * FROM bridge_subscriptions
            WHERE user_id = $1
            ORDER BY updated_at DESC
            """,
            user_id,
        )
    return await conn.fetch(
        """
        SELECT * FROM bridge_subscriptions
        WHERE user_id = $1 AND status <> 'DISCONNECTED'
        ORDER BY updated_at DESC
        """,
        user_id,
    )


async def update_subscription(
    conn: asyncpg.Connection,
    bridge_id: uuid.UUID,
    **fields: Any,
) -> None:
    if not fields:
        return
    keys = list(fields.keys())
    vals = [fields[k] for k in keys]
    set_parts = [f"{k} = ${i + 1}" for i, k in enumerate(keys)]
    vals.append(bridge_id)
    num = len(vals)
    q = (
        f"UPDATE bridge_subscriptions SET {', '.join(set_parts)}, "
        f"updated_at = NOW() WHERE id = ${num}"
    )
    await conn.execute(q, *vals)


async def mark_status(conn: asyncpg.Connection, bridge_id: uuid.UUID, status: str) -> None:
    await conn.execute(
        """
        UPDATE bridge_subscriptions
        SET status = $2, updated_at = NOW()
        WHERE id = $1
        """,
        bridge_id,
        status,
    )


def subscription_to_public_dict(rec: asyncpg.Record) -> dict[str, Any]:
    """JSON-serialisable row for MCP responses (no secrets)."""
    return {
        "id": str(rec["id"]),
        "user_id": rec["user_id"],
        "provider": rec["provider"],
        "resource_id": rec["resource_id"],
        "subscription_id": rec["subscription_id"],
        "cursor": rec["cursor"],
        "status": rec["status"],
        "expires_at": rec["expires_at"].isoformat() if rec["expires_at"] else None,
        "client_state_set": bool(rec["client_state"]),
        "created_at": rec["created_at"].isoformat() if rec["created_at"] else None,
        "updated_at": rec["updated_at"].isoformat() if rec["updated_at"] else None,
    }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
