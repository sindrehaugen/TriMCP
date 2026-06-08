"""
Phase 3: Dead Letter Queue (Poison Pill Handler)
=================================================
Persistent store for background tasks that exhaust their retry budget.

Tasks in ``nce.tasks`` (``process_code_indexing``, ``process_bridge_event``)
track attempts via Redis.  When ``attempt_count > cfg.TASK_MAX_RETRIES`` the
payload is written here rather than re-enqueued, preventing infinite-retry
CPU spin-loops that starve worker threads.

Public API
----------
* ``store_dead_letter()``         — persist a poisoned task payload
* ``list_dead_letters()``        — query DLQ (admin / dashboard)
* ``count_dead_letters()``       — count DLQ entries (same filters)
* ``replay_dead_letter()``       — mark a DLQ entry for caller-side re-enqueue
* ``purge_dead_letter()``        — soft-delete a DLQ entry (marks 'purged')
* ``_track_attempt()``           — Redis-based attempt counter (used by tasks.py)
* ``_clear_attempt()``           — clear the attempt counter on success

NOTE: list/count/replay/purge operate globally (admin-only paths).
      They do not enforce tenant RLS — callers must ensure authentication.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from redis import Redis

from nce.config import cfg
from nce.observability import TASK_DLQ_BACKLOG, TASK_DLQ_TOTAL

log = logging.getLogger("nce.dead_letter_queue")

# ---------------------------------------------------------------------------
# DLQ payload sanitisation
# ---------------------------------------------------------------------------

# Exact-match set (checked after lowercasing + dash→underscore normalisation).
_DLQ_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "access_token",
        "accesstoken",
        "refresh_token",
        "refreshtoken",
        "token",
        "authorization",
        "auth",
        "bearer",
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "private_key",
        "client_secret",
        "clientsecret",
        "raw_code",
        "code",
        "content",
        "file_content",
    }
)

# Substring markers — any key whose normalised form contains one of these is redacted.
_DLQ_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "private_key",
    "api_key",
    "apikey",
)

_MAX_DLQ_STRING_LEN: int = 4096
_MAX_DLQ_NESTED_KEYS: int = 50
_ERROR_MESSAGE_MAX_LEN: int = 1024

# Validation
_JOB_ID_RE = re.compile(r"^[a-zA-Z0-9:_./-]{1,256}$")
_ALLOWED_DLQ_STATUS: frozenset[str] = frozenset({"pending", "replayed", "purged"})


def _is_sensitive_key(key: str) -> bool:
    """Return True if *key* should be redacted in DLQ payloads.

    Matching is case-insensitive (dash and underscore treated equally).
    Both exact-match and substring checks are applied.
    """
    normalised = key.lower().replace("-", "_")
    if normalised in _DLQ_SENSITIVE_KEYS:
        return True
    return any(marker in normalised for marker in _DLQ_SENSITIVE_SUBSTRINGS)


def _sanitize_dlq_kwargs(value: Any) -> Any:
    """Return a copy of *value* safe for DLQ persistence.

    - Redacts values for known sensitive keys (case-insensitive + substring-based).
    - Recurses into nested dicts with the same rules.
    - Truncates strings longer than ``_MAX_DLQ_STRING_LEN``.
    - Limits nested dict/list sizes.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in list(value.items())[:_MAX_DLQ_NESTED_KEYS]:
            if _is_sensitive_key(str(k)):
                out[str(k)] = "[REDACTED]"
            else:
                out[str(k)] = _sanitize_dlq_kwargs(v)
        return out
    if isinstance(value, list):
        return [_sanitize_dlq_kwargs(i) for i in value[:_MAX_DLQ_NESTED_KEYS]]
    if isinstance(value, str):
        if len(value) > _MAX_DLQ_STRING_LEN:
            return value[:_MAX_DLQ_STRING_LEN] + "...[truncated]"
        return value
    return value


def _validate_status(status: str | None) -> str | None:
    """Validate optional DLQ status filter against the allowed set."""
    if not status:
        return None
    if status not in _ALLOWED_DLQ_STATUS:
        raise ValueError(f"status must be one of {sorted(_ALLOWED_DLQ_STATUS)}, got {status!r}")
    return status


# ---------------------------------------------------------------------------
# Redis attempt tracking (used by tasks.py wrappers)
# ---------------------------------------------------------------------------

_ATTEMPT_KEY_PREFIX: str = "task_attempts"


def _attempt_key(job_id: str) -> str:
    """Redis key for a given RQ job's attempt counter.

    Validates job_id format to prevent unexpected Redis key shapes.
    """
    if not _JOB_ID_RE.fullmatch(job_id):
        raise ValueError(
            f"Invalid job_id for attempt tracking — must match [a-zA-Z0-9:_./-]{{1,256}}: "
            f"{job_id!r}"
        )
    return f"{_ATTEMPT_KEY_PREFIX}:{job_id}"


def _track_attempt(redis_client: Redis, job_id: str) -> int:
    """Increment and return the attempt count for *job_id*.

    TTL is refreshed on every attempt so the key never becomes permanent,
    even when a connection drop occurs after INCR but before EXPIRE.
    Returns the **new** attempt count (1-based).
    """
    key = _attempt_key(job_id)
    count: int = redis_client.incr(key)  # type: ignore[assignment]
    # Always refresh TTL — prevents permanent keys on partial failure.
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
    namespace_id: str | UUID | None = None,
) -> str:
    """Persist a poisoned task to the ``dead_letter_queue`` table.

    Returns the UUID (as str) of the inserted row.

    Emits ``TASK_DLQ_TOTAL`` metric and logs at CRITICAL level so operators
    are alerted to background-job degradation.

    ``namespace_id`` is stored for tenant attribution, fleet reporting, and
    namespace cleanup. When not passed explicitly, it is derived from
    ``kwargs.get('namespace_id')``. May remain NULL for global tasks.
    """
    # Derive namespace_id from kwargs when not passed explicitly.
    ns: str | UUID | None = namespace_id or kwargs.get("namespace_id")

    sanitized = _sanitize_dlq_kwargs(kwargs)
    # Truncate error_message to match schema comment: truncated to 1024 chars.
    error_message = str(error_message)[:_ERROR_MESSAGE_MAX_LEN]

    dlq_id: str | None = None
    try:
        async with pg_pool.acquire(timeout=10.0) as conn:
            dlq_id = str(
                await conn.fetchval(
                    """
                    INSERT INTO dead_letter_queue (
                        namespace_id, task_name, job_id, kwargs,
                        error_message, attempt_count, status
                    )
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, 'pending')
                    RETURNING id
                    """,
                    ns,
                    task_name,
                    job_id,
                    json.dumps(sanitized, default=str, sort_keys=True),
                    error_message,
                    attempt_count,
                )
            )

        TASK_DLQ_TOTAL.labels(task_name=task_name).inc()

        # Refresh backlog gauge from DB.
        await _refresh_backlog_gauge(pg_pool, task_name)

        # Dispatch alert to operators non-blockingly, caught and logged if failing
        try:
            from nce.notifications import dispatcher

            title = f"Task Dead-Lettered: {task_name}"
            message = f"Task '{task_name}' (job {job_id}) failed: {error_message}"
            await dispatcher.dispatch_alert(title, message)
        except Exception:
            log.exception(
                "[DLQ] Failed to dispatch alert for dead-lettered task %s (job %s)",
                task_name,
                job_id,
            )

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
            "Caller still owns payload but it was not durably stored.",
            task_name,
            job_id,
        )
        raise

    return dlq_id  # type: ignore[return-value]


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
                # Refresh all known task names.
                rows = await conn.fetch(
                    "SELECT task_name, count(*) AS cnt FROM dead_letter_queue "
                    "WHERE status = 'pending' GROUP BY task_name"
                )
                for row in rows:
                    TASK_DLQ_BACKLOG.labels(task_name=row["task_name"]).set(row["cnt"])
    except Exception:
        log.debug("[DLQ] Could not refresh backlog gauge — DB may not be ready.")


async def count_dead_letters(
    pg_pool: Any,
    task_name: str | None = None,
    status: str | None = None,
) -> int:
    """Return matching DLQ row count (same filters as ``list_dead_letters``)."""
    status = _validate_status(status)

    clauses: list[str] = ["1=1"]
    params: list[Any] = []

    if task_name:
        params.append(task_name)
        clauses.append(f"task_name = ${len(params)}")
    if status:
        params.append(status)
        clauses.append(f"status = ${len(params)}")

    query = f"""
        SELECT COUNT(*)::bigint AS cnt
        FROM dead_letter_queue
        WHERE {' AND '.join(clauses)}
    """

    async with pg_pool.acquire(timeout=10.0) as conn:
        cnt = await conn.fetchval(query, *params)

    return int(cnt or 0)


async def list_dead_letters(
    pg_pool: Any,
    task_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query dead_letter_queue rows for admin dashboards.

    NOTE: This is a global (non-namespace-scoped) query. Only call from
    admin-authenticated control-plane code.

    Args:
        task_name: Optional filter by task function name.
        status: Optional filter — must be one of: ``pending``, ``replayed``, ``purged``.
        limit: Max rows to return (clamped to 1–200).
        offset: Pagination offset (clamped to >= 0).
    """
    status = _validate_status(status)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

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
        SELECT id, namespace_id, task_name, job_id, kwargs, error_message,
               attempt_count, status, created_at, replayed_at, purged_at
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
            "namespace_id": str(r["namespace_id"]) if r["namespace_id"] else None,
            "task_name": r["task_name"],
            "job_id": r["job_id"],
            "kwargs": (json.loads(r["kwargs"]) if isinstance(r["kwargs"], str) else r["kwargs"]),
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
    """Mark a DLQ entry as replayed and return its payload for caller-side re-enqueue.

    Transitions the row ``pending → replayed``. The caller is responsible for
    pushing the returned task_name/kwargs back onto the RQ queue. If the caller
    crashes between this call and the actual enqueue, the entry remains 'replayed'
    (not re-processable automatically).

    Returns the entry's task_name, job_id, and kwargs for the admin handler.
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
                raise ValueError(f"DLQ entry {dlq_id} not found or not in 'pending' status")

    log.info(
        "[DLQ] Replayed entry %s (task=%s, job=%s)",
        dlq_id,
        row["task_name"],
        row["job_id"],
    )

    # Refresh backlog gauge — one pending row removed.
    await _refresh_backlog_gauge(pg_pool, row["task_name"])

    return {
        "id": dlq_id,
        "task_name": row["task_name"],
        "job_id": row["job_id"],
        "kwargs": (json.loads(row["kwargs"]) if isinstance(row["kwargs"], str) else row["kwargs"]),
        "attempt_count": row["attempt_count"],
        "status": "replayed",
    }


async def purge_dead_letter(
    pg_pool: Any,
    dlq_id: str,
) -> None:
    """Mark a DLQ entry as purged (soft-delete — row is retained for audit).

    Sets ``status = 'purged'`` and ``purged_at = now()``. The row remains in
    the table for audit log integrity. Use a DB-level archival/cleanup job for
    physical removal after the retention window.

    Raises ValueError if the entry does not exist.
    """
    async with pg_pool.acquire(timeout=10.0) as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE dead_letter_queue
                SET status = 'purged', purged_at = now()
                WHERE id = $1::uuid
                RETURNING task_name
                """,
                dlq_id,
            )
            if row is None:
                raise ValueError(f"DLQ entry {dlq_id} not found")

    log.info("[DLQ] Purged entry %s (task=%s)", dlq_id, row["task_name"])

    # Refresh backlog gauge — entry is no longer pending.
    await _refresh_backlog_gauge(pg_pool, row["task_name"])
