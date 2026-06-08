"""Transactional Outbox Relay — ordered, at-most-once delivery of domain events.

The relay polls unpublished rows from ``outbox_events`` using
``FOR UPDATE SKIP LOCKED``, dispatches each event to a registered handler,
marks successful deliveries with ``published_at``, increments ``attempt_count``
on failure, and routes exhausted events to ``dead_letter_queue``.

Handler contract
----------------
Handlers run **inside** the open transaction, which gives them MVCC-consistent
reads and lets ``mark_published`` be atomic with the delivery.  Handlers must
NOT perform external I/O (Redis, HTTP) inside the transaction — that holds the
DB connection while waiting on external services and starves the pool.

To fire external work after the commit, return a zero-argument callable from
the handler.  The relay collects these "post-commit actions" and calls them
after the transaction closes.  The canonical example is
``handle_memory_stored`` returning ``lambda: enqueue_memory_postprocess(payload)``
so the RQ enqueue runs after the DB row is already committed.

Entry point: ``run_outbox_relay_once(pool)`` — call from APScheduler or an
asyncio periodic task in the server startup.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg

log = logging.getLogger("nce.outbox_relay")

_ALERT_THROTTLE_CACHE: dict[str, float] = {}
_THROTTLE_WINDOW_SECONDS = 300.0


async def _dispatch_throttled_alert(key: str, title: str, message: str) -> None:
    now = time.time()
    last_sent = _ALERT_THROTTLE_CACHE.get(key, 0.0)
    if now - last_sent >= _THROTTLE_WINDOW_SECONDS:
        _ALERT_THROTTLE_CACHE[key] = now
        try:
            from nce.notifications import dispatcher

            await dispatcher.dispatch_alert(title, message)
        except Exception:
            log.exception("Failed to dispatch throttled alert for key %s", key)


# Handlers may return an optional zero-arg callable to run after the
# transaction commits (e.g. Redis enqueue, HTTP notification).
# Return None if no post-commit work is needed.
PostCommitAction = Callable[[], None]
OutboxHandler = Callable[[asyncpg.Connection, dict[str, Any]], Awaitable[PostCommitAction | None]]

MAX_OUTBOX_ATTEMPTS: int = 5


class OutboxDeliveryError(Exception):
    """Raised when no handler is registered for an outbox event type."""


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_memory_stored(
    conn: asyncpg.Connection,
    event: dict[str, Any],
) -> PostCommitAction:
    """Prepare the RQ enqueue action for 'memory.stored'.

    Returns a post-commit callable instead of enqueuing inside the transaction.
    This keeps Redis I/O out of the open DB transaction and prevents pool
    starvation when Redis is slow or briefly unreachable.
    """
    from nce.tasks import enqueue_memory_postprocess

    payload = event.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)

    # Capture payload in closure — enqueue runs after transaction commits.
    captured = dict(payload)
    return lambda: enqueue_memory_postprocess(captured)


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
    await _dispatch_throttled_alert(
        f"outbox.dlq.{event['event_type']}",
        f"Outbox Event Dead-Lettered: outbox:{event['event_type']}",
        f"Outbox event '{event['event_type']}' (id {event['id']}) failed: {error_message}",
    )


async def deliver_one(
    conn: asyncpg.Connection,
    event: dict[str, Any],
) -> PostCommitAction | None:
    """Dispatch a single outbox event to its registered handler.

    Returns the handler's post-commit action (or None) for the caller to fire
    after the surrounding transaction commits.
    """
    event_type = event["event_type"]
    handler = OUTBOX_HANDLERS.get(event_type)
    if handler is None:
        raise OutboxDeliveryError(f"No outbox handler registered for event_type={event_type!r}")
    return await handler(conn, event)


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

    The transaction covers only DB operations (poll, mark_published/failed,
    DLQ insert).  Any post-commit actions returned by handlers (e.g. Redis
    enqueues) are collected during the transaction and fired **after** the
    transaction commits so external I/O never holds the DB connection open.
    """
    delivered = 0
    post_commit_actions: list[PostCommitAction] = []

    async with pool.acquire(timeout=10.0) as conn:
        async with conn.transaction():
            events = await poll_outbox(conn, batch_size=batch_size)

            for event in events:
                try:
                    action = await deliver_one(conn, event)
                except Exception as exc:
                    error_message = f"{type(exc).__name__}: {exc}"
                    log.exception(
                        "[outbox] delivery failed event_id=%s event_type=%s",
                        event["id"],
                        event["event_type"],
                    )
                    await _dispatch_throttled_alert(
                        f"outbox.delivery_failed.{event['event_type']}",
                        f"Outbox Delivery Failed: {event['event_type']}",
                        f"Outbox event delivery failed for event_id {event['id']}: {error_message}",
                    )
                    try:
                        from nce.observability import OUTBOX_DELIVERY_FAILURES_TOTAL

                        OUTBOX_DELIVERY_FAILURES_TOTAL.labels(
                            event_type=str(event["event_type"])
                        ).inc()
                    except Exception:
                        pass
                    if isinstance(exc, OutboxDeliveryError):
                        await conn.execute(
                            """
                            UPDATE outbox_events
                            SET attempt_count = $1,
                                error_message = left($2, 2048)
                            WHERE id = $3
                            """,
                            MAX_OUTBOX_ATTEMPTS,
                            error_message,
                            event["id"],
                        )
                        event_copy = dict(event)
                        event_copy["attempt_count"] = MAX_OUTBOX_ATTEMPTS - 1
                        await move_to_dead_letter_if_exhausted(conn, event_copy, error_message)
                        try:
                            from nce.observability import OUTBOX_DLQ_TOTAL

                            OUTBOX_DLQ_TOTAL.labels(event_type=str(event["event_type"])).inc()
                        except Exception:
                            pass
                    else:
                        await mark_failed(conn, event["id"], error_message)
                        prior_attempts = int(event["attempt_count"])
                        await move_to_dead_letter_if_exhausted(conn, event, error_message)
                        if prior_attempts + 1 >= MAX_OUTBOX_ATTEMPTS:
                            try:
                                from nce.observability import OUTBOX_DLQ_TOTAL

                                OUTBOX_DLQ_TOTAL.labels(event_type=str(event["event_type"])).inc()
                            except Exception:
                                pass
                    continue

                await mark_published(conn, event["id"])
                delivered += 1
                if action is not None:
                    post_commit_actions.append(action)
                try:
                    from nce.observability import OUTBOX_DELIVERED_TOTAL

                    OUTBOX_DELIVERED_TOTAL.labels(event_type=str(event["event_type"])).inc()
                except Exception:
                    pass
        # Transaction committed.  Fire external work outside the DB connection.

    for action in post_commit_actions:
        try:
            action()
        except Exception as exc:
            log.warning("[outbox] post-commit action failed: %s", exc)

    log.debug("[outbox] relay pass complete: delivered=%d", delivered)
    return delivered
