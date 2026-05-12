"""
Phase 3: Dead Letter Queue (Poison Pill Handler)
=================================================
Persistent store for background tasks that exhaust their retry budget.

Tasks in ``trimcp.tasks`` (``process_code_indexing``, ``process_bridge_event``)
track attempts via Redis.  When ``attempt_count > cfg.TASK_MAX_RETRIES`` the
payload is written here rather than re-enqueued, preventing infinite-retry
CPU spin-loops that starve worker threads.

Public API
----------
* ``store_dead_letter()``         — persist a poisoned task payload
* ``list_dead_letters()``        — query DLQ (admin / dashboard)
* ``replay_dead_letter()``       — re-enqueue a DLQ entry (admin action)
* ``purge_dead_letter()``        — permanently delete a DLQ entry
* ``_track_attempt()``           — Redis-based attempt counter (used by tasks.py)
* ``_clear_attempt()``           — clear the attempt counter on success
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from redis import Redis

from trimcp.config import cfg
from trimcp.observability import TASK_DLQ_BACKLOG, TASK_DLQ_TOTAL

log = logging.getLogger("trimcp.dead_letter_queue")

# ---------------------------------------------------------------------------
# DLQ payload sanitisation
# ---------------------------------------------------------------------------

_DLQ_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "api_key",
    "private_key",
    "client_secret",
    "raw_code",
    "code",
})
_MAX_DLQ_STRING_LEN: int = 4096
_MAX_DLQ_NESTED_KEYS: int = 50


def _sanitize_dlq_kwargs(value: Any) -> Any:
    """Return a copy of *value* safe for DLQ persistence.

    - Redacts values for known sensitive keys.
    - Truncates strings longer than ``_MAX_DLQ_STRING_LEN``.
    - Limits nested dict/list sizes.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in list(value.items())[:_MAX_DLQ_NESTED_KEYS]:
            if k in _DLQ_SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = _sanitize_dlq_kwargs(v)
        return out
    if isinstance(value, list):
        return [
            _sanitize_dlq_kwargs(i)
            for i in value[:_MAX_DLQ_NESTED_KEYS]
        ]
    if isinstance(value, str):
        if len(value) > _MAX_DLQ_STRING_LEN:
            return value[:_MAX_DLQ_STRING_LEN] + "...[truncated]"
        return value
    return value


# ---------------------------------------------------------------------------
# Redis attempt tracking (used by tasks.py wrappers)
# ---------------------------------------------------------------------------

_ATTEMPT_KEY_PREFIX: str = "task_attempts"


def _attempt_key(job_id: str) -> str:
    """Redis key for a given RQ job's attempt counter."""
    return f"{_ATTEMPT_KEY_PREFIX}:{job_id}"


def _track_attempt(redis_client: Redis, job_id: str) -> int:
    """Increment and return the attempt count for *job_id*.

    Sets a TTL on first write so abandoned counters expire naturally.
    Returns the **new** attempt count (1-based).
    """
    key = _attempt_key(job_id)
    count: int = redis_client.incr(key)  # type: ignore[assignment]
    if count == 1:
        redis_client.expire(key, cfg.TASK_DLQ_REDIS_TTL)
    return count


def _clear_attempt(redis_client: Redis, job_id: str) -> None:
    """Remove the attempt counter after a successful task execution."""
    redis_client.delete(_attempt_key(job_id))


# ---------------------------------------------------------------------------
# DLQ persistence (PostgreSQL — see dead_letter_queue table in schema.sql)
# ---------------------------------------------------------------------------

# Avoid hard import-time dependency on asyncpg; callers pass a pool.
# The table is created by schema.sql on startup.


async def store_dead_letter(
    pg_pool: Any,
    task_name: str,
    job_id: str,
    kwargs: dict[str, Any],
    error_message: str,
    attempt_count: int,
) -> str:
    """Persist a poisoned task to the ``dead_letter_queue`` table.

    Returns the UUID (as str) of the inserted row.

    Emits ``TASK_DLQ_TOTAL`` metric and logs at CRITICAL level so operators
    are alerted to background-job degradation.
    """
    dlq_id = str(UUID(int=0))  # placeholder — real UUID from DB

    try:
        async with pg_pool.acquire(timeout=10.0) as conn:
            dlq_id = str(
                await conn.fetchval(
                    """
                    INSERT INTO dead_letter_queue
                        (task_name, job_id, kwargs, error_message, attempt_count, status)
                    VALUES ($1, $2, $3::jsonb, $4, $5, 'pending')
                    RETURNING id
                    """,
                    task_name,
                    job_id,
                    json.dumps(_sanitize_dlq_kwargs(kwargs)),
                    error_message,
                    attempt_count,
                )
            )

        TASK_DLQ_TOTAL.labels(task_name=task_name).inc()

        # Refresh backlog gauge from DB
        await _refresh_backlog_gauge(pg_pool, task_name)

        log.critical(
            "[DLQ] Task %s (job %s) failed %d times — routed to dead_letter_queue id=%s. Error: %s",
            task_name,
            job_id,
            attempt_count,
            dlq_id,
            error_message[:256],
        )
    except Exception:
        log.exception(
            "[DLQ] CRITICAL — Failed to persist dead_letter_queue row for task %s (job %s). "
            "Payload is lost.",
            task_name,
            job_id,
        )
        raise

    return dlq_id


async def _refresh_backlog_gauge(pg_pool: Any, task_name: str | None = None) -> None:
    """Update the TASK_DLQ_BACKLOG gauge(s) from the current DB state."""
    try:
        async with pg_pool.acquire(timeout=10.0) as conn:
            if task_name:
                count = await conn.fetchval(
                    "SELECT count(*) FROM dead_letter_queue WHERE task_name = $1 AND status = 'pending'",
                    task_name,
                )
                TASK_DLQ_BACKLOG.labels(task_name=task_name).set(count or 0)
            else:
                # Refresh all known task names
                rows = await conn.fetch(
                    "SELECT task_name, count(*) AS cnt FROM dead_letter_queue WHERE status = 'pending' GROUP BY task_name"
                )
                for row in rows:
                    TASK_DLQ_BACKLOG.labels(task_name=row["task_name"]).set(row["cnt"])
    except Exception:
        log.debug("[DLQ] Could not refresh backlog gauge — DB may not be ready.")


async def list_dead_letters(
    pg_pool: Any,
    task_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query dead_letter_queue rows for admin dashboards.

    Args:
        task_name: Optional filter by task function name.
        status: Optional filter (``pending``, ``replayed``, ``purged``).
        limit: Max rows to return (capped at 200).
        offset: Pagination offset.
    """
    limit = min(limit, 200)
    clauses: list[str] = ["1=1"]
    params: list[Any] = []

    if task_name:
        params.append(task_name)
        clauses.append(f"task_name = ${len(params)}")
    if status:
        params.append(status)
        clauses.append(f"status = ${len(params)}")

    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)

    query = f"""
        SELECT id, task_name, job_id, kwargs, error_message, attempt_count,
               status, created_at, replayed_at, purged_at
        FROM dead_letter_queue
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
    """

    async with pg_pool.acquire(timeout=10.0) as conn:
        rows = await conn.fetch(query, *params)

    return [
        {
            "id": str(r["id"]),
            "task_name": r["task_name"],
            "job_id": r["job_id"],
            "kwargs": (
                json.loads(r["kwargs"]) if isinstance(r["kwargs"], str) else r["kwargs"]
            ),
            "error_message": r["error_message"],
            "attempt_count": r["attempt_count"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat(),
            "replayed_at": r["replayed_at"].isoformat() if r["replayed_at"] else None,
            "purged_at": r["purged_at"].isoformat() if r["purged_at"] else None,
        }
        for r in rows
    ]


async def replay_dead_letter(
    pg_pool: Any,
    dlq_id: str,
) -> dict[str, Any]:
    """Mark a DLQ entry as replayed (caller must re-enqueue the job).

    Returns the entry's task_name, job_id, and kwargs so the admin handler
    can push it back onto the RQ queue.

    Raises ValueError if the entry is not in ``pending`` status.
    """
    async with pg_pool.acquire(timeout=10.0) as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE dead_letter_queue
                SET status = 'replayed', replayed_at = now()
                WHERE id = $1::uuid AND status = 'pending'
                RETURNING task_name, job_id, kwargs, attempt_count
                """,
                dlq_id,
            )
            if row is None:
                raise ValueError(
                    f"DLQ entry {dlq_id} not found or not in 'pending' status"
                )

    log.info(
        "[DLQ] Replayed entry %s (task=%s, job=%s)",
        dlq_id,
        row["task_name"],
        row["job_id"],
    )

    return {
        "id": dlq_id,
        "task_name": row["task_name"],
        "job_id": row["job_id"],
        "kwargs": (
            json.loads(row["kwargs"])
            if isinstance(row["kwargs"], str)
            else row["kwargs"]
        ),
        "attempt_count": row["attempt_count"],
        "status": "replayed",
    }


async def purge_dead_letter(
    pg_pool: Any,
    dlq_id: str,
) -> None:
    """Permanently remove a DLQ entry (admin action).

    Raises ValueError if the entry does not exist.
    """
    async with pg_pool.acquire(timeout=10.0) as conn:
        async with conn.transaction():
            result = await conn.execute(
                """
                UPDATE dead_letter_queue
                SET status = 'purged', purged_at = now()
                WHERE id = $1::uuid
                """,
                dlq_id,
            )
            if result == "UPDATE 0":
                raise ValueError(f"DLQ entry {dlq_id} not found")

    log.info("[DLQ] Purged entry %s", dlq_id)
