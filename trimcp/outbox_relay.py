"""Transactional Outbox Relay — ordered, at-most-once delivery of domain events.

The relay polls unpublished rows from ``outbox_events`` using
``FOR UPDATE SKIP LOCKED``, dispatches each event to a registered handler,
marks successful deliveries with ``published_at``, increments ``attempt_count``
on failure, and routes exhausted events to ``dead_letter_queue``.

Handlers must be thin: enqueue worker jobs rather than performing heavy work
(embeddings, graph extraction, contradiction detection) inline inside the
relay transaction.

Entry point: ``run_outbox_relay_once(pool)`` — call from APScheduler or an
asyncio periodic task in the server startup.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg

log = logging.getLogger("trimcp.outbox_relay")

OutboxHandler = Callable[[asyncpg.Connection, dict[str, Any]], Awaitable[None]]

MAX_OUTBOX_ATTEMPTS: int = 5


class OutboxDeliveryError(Exception):
    """Raised when no handler is registered for an outbox event type."""


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_memory_stored(conn: asyncpg.Connection, event: dict[str, Any]) -> None:
    """Dispatch 'memory.stored' to the RQ high-priority worker queue."""
    from trimcp.tasks import enqueue_memory_postprocess

    payload = event.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    enqueue_memory_postprocess(payload)


OUTBOX_HANDLERS: dict[str, OutboxHandler] = {
    "memory.stored": handle_memory_stored,
}


# ---------------------------------------------------------------------------
# Core relay operations
# ---------------------------------------------------------------------------


async def poll_outbox(
    conn: asyncpg.Connection,
    *,
    batch_size: int = 50,
) -> list[dict[str, Any]]:
    """Select unpublished rows within an open transaction (FOR UPDATE SKIP LOCKED)."""
    rows = await conn.fetch(
        """
        SELECT
            id,
            namespace_id,
            aggregate_type,
            aggregate_id,
            event_type,
            payload,
            headers,
            attempt_count,
            created_at
        FROM outbox_events
        WHERE published_at IS NULL
          AND attempt_count < $1
        ORDER BY created_at ASC
        LIMIT $2
        FOR UPDATE SKIP LOCKED
        """,
        MAX_OUTBOX_ATTEMPTS,
        batch_size,
    )
    return [dict(row) for row in rows]


async def mark_published(conn: asyncpg.Connection, event_id: Any) -> None:
    await conn.execute(
        "UPDATE outbox_events SET published_at = now() WHERE id = $1",
        event_id,
    )


async def mark_failed(
    conn: asyncpg.Connection,
    event_id: Any,
    error_message: str,
) -> None:
    await conn.execute(
        """
        UPDATE outbox_events
        SET attempt_count = attempt_count + 1,
            error_message = left($2, 2048)
        WHERE id = $1
        """,
        event_id,
        error_message,
    )


async def move_to_dead_letter_if_exhausted(
    conn: asyncpg.Connection,
    event: dict[str, Any],
    error_message: str,
) -> None:
    """Write a DLQ row when attempt_count has reached MAX_OUTBOX_ATTEMPTS."""
    if int(event["attempt_count"]) + 1 < MAX_OUTBOX_ATTEMPTS:
        return

    payload = event.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)

    await conn.execute(
        """
        INSERT INTO dead_letter_queue (
            namespace_id,
            task_name,
            job_id,
            kwargs,
            error_message,
            attempt_count,
            status
        )
        VALUES ($1, $2, $3, $4::jsonb, left($5, 1024), $6, 'pending')
        """,
        event["namespace_id"],
        f"outbox:{event['event_type']}",
        str(event["id"]),
        json.dumps(
            {
                "outbox_event_id": str(event["id"]),
                "event_type": event["event_type"],
                "aggregate_type": event["aggregate_type"],
                "aggregate_id": str(event["aggregate_id"]),
                "payload": payload,
            },
            default=str,
            sort_keys=True,
        ),
        error_message,
        int(event["attempt_count"]) + 1,
    )
    log.warning(
        "[outbox] event_id=%s event_type=%s exhausted %d attempts — moved to DLQ",
        event["id"],
        event["event_type"],
        MAX_OUTBOX_ATTEMPTS,
    )


async def deliver_one(
    conn: asyncpg.Connection,
    event: dict[str, Any],
) -> None:
    """Dispatch a single outbox event to its registered handler."""
    event_type = event["event_type"]
    handler = OUTBOX_HANDLERS.get(event_type)
    if handler is None:
        raise OutboxDeliveryError(f"No outbox handler registered for event_type={event_type!r}")
    await handler(conn, event)


# ---------------------------------------------------------------------------
# Public relay loop
# ---------------------------------------------------------------------------


async def run_outbox_relay_once(
    pool: asyncpg.Pool,
    *,
    batch_size: int = 50,
) -> int:
    """
    Run one relay pass: poll → deliver → mark_published or mark_failed → DLQ.

    Returns the number of events successfully delivered in this pass.
    All operations run inside a single transaction so locks are released
    atomically on commit.
    """
    delivered = 0

    async with pool.acquire(timeout=10.0) as conn:
        async with conn.transaction():
            events = await poll_outbox(conn, batch_size=batch_size)

            for event in events:
                try:
                    await deliver_one(conn, event)
                except Exception as exc:
                    error_message = f"{type(exc).__name__}: {exc}"
                    log.exception(
                        "[outbox] delivery failed event_id=%s event_type=%s",
                        event["id"],
                        event["event_type"],
                    )
                    try:
                        from trimcp.observability import OUTBOX_DELIVERY_FAILURES_TOTAL

                        OUTBOX_DELIVERY_FAILURES_TOTAL.labels(
                            event_type=str(event["event_type"])
                        ).inc()
                    except Exception:
                        pass
                    await mark_failed(conn, event["id"], error_message)
                    prior_attempts = int(event["attempt_count"])
                    await move_to_dead_letter_if_exhausted(conn, event, error_message)
                    if prior_attempts + 1 >= MAX_OUTBOX_ATTEMPTS:
                        try:
                            from trimcp.observability import OUTBOX_DLQ_TOTAL

                            OUTBOX_DLQ_TOTAL.labels(event_type=str(event["event_type"])).inc()
                        except Exception:
                            pass
                    continue

                await mark_published(conn, event["id"])
                delivered += 1
                try:
                    from trimcp.observability import OUTBOX_DELIVERED_TOTAL

                    OUTBOX_DELIVERED_TOTAL.labels(event_type=str(event["event_type"])).inc()
                except Exception:
                    pass

    log.debug("[outbox] relay pass complete: delivered=%d", delivered)
    return delivered
