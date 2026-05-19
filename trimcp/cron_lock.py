"""
Distributed lock helper for singleton cron jobs.

Uses Redis SET NX EX so only one cron instance runs a given job at a time.
Extracted from cron.py to keep it importable without APScheduler.
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass

from trimcp.config import cfg

log = logging.getLogger("trimcp.cron")

_CRON_LOCK_PREFIX = "trimcp:cron:lock"
_JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_.:-]{1,128}$")

# Lua compare-and-delete: only DEL if value still matches our token.
_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""

# Sentinel for environments where Redis is disabled (non-prod).
_LOCAL_DISABLED = "local-disabled"


@dataclass(frozen=True)
class CronLock:
    """Opaque handle for a distributed cron lock.

    Returned by :func:`acquire_cron_lock` on success.
    Pass to :func:`release_cron_lock` when the job finishes, so the lock is
    released immediately rather than waiting for TTL expiry.
    """

    job_id: str
    key: str
    token: str
    ttl_seconds: int


def _validated_lock_key(job_id: str) -> str:
    if not _JOB_ID_RE.fullmatch(job_id):
        raise ValueError(f"Invalid cron job_id — must match [a-zA-Z0-9_.:-]{{1,128}}: {job_id!r}")
    return f"{_CRON_LOCK_PREFIX}:{job_id}"


async def acquire_cron_lock(job_id: str, ttl_seconds: int) -> CronLock | None:
    """Try to acquire a Redis distributed lock for a singleton cron job.

    Returns:
        CronLock — if the lock was acquired (safe to run this job).
        None — if another instance holds the lock, Redis is unreachable, or
               locking is required but unavailable (production with no REDIS_URL).

    In non-production environments with no ``REDIS_URL`` configured the function
    returns a local-disabled CronLock so dev/CI runs are not blocked.

    In production (``IS_PROD=True``) with no ``REDIS_URL`` this returns None
    (fail-closed) to prevent concurrent singleton jobs.
    """
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be >= 1")

    key = _validated_lock_key(job_id)

    if not cfg.REDIS_URL:
        if cfg.IS_PROD:
            log.error(
                "REDIS_URL not set — refusing cron lock in production for job=%s. "
                "Set REDIS_URL to enable distributed cron locking.",
                job_id,
            )
            return None

        log.warning("REDIS_URL not set — cron distributed lock disabled for %s (non-prod)", job_id)
        return CronLock(
            job_id=job_id,
            key=f"local-disabled:{job_id}",
            token=_LOCAL_DISABLED,
            ttl_seconds=ttl_seconds,
        )

    token = secrets.token_urlsafe(32)
    client = None
    try:
        from redis.asyncio import Redis as AsyncRedis

        client = AsyncRedis.from_url(cfg.REDIS_URL)
        acquired = await client.set(key, token, nx=True, ex=ttl_seconds)

        if not acquired:
            return None

        return CronLock(job_id=job_id, key=key, token=token, ttl_seconds=ttl_seconds)

    except Exception as exc:
        log.error("Cron lock acquisition failed for job=%s: %s", job_id, exc)
        # Fail-closed: abort the job on Redis outage to prevent concurrency bugs.
        return None

    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                log.warning("Cron lock Redis close failed for job=%s: %s", job_id, exc)


async def release_cron_lock(lock: CronLock) -> bool:
    """Release a cron lock only if this process still owns it (compare-and-delete).

    Safe to call even if the TTL has expired or another instance has taken
    over — the Lua script will return 0 without deleting another owner's lock.
    """
    if lock.token == _LOCAL_DISABLED:
        return True

    client = None
    try:
        from redis.asyncio import Redis as AsyncRedis

        client = AsyncRedis.from_url(cfg.REDIS_URL)
        released = await client.eval(_RELEASE_LOCK_LUA, 1, lock.key, lock.token)
        if not released:
            log.warning(
                "Cron lock release for job=%s did not delete key — "
                "lock may have expired or been taken by another instance.",
                lock.job_id,
            )
        return bool(released)

    except Exception as exc:
        log.warning("Cron lock release failed for job=%s: %s", lock.job_id, exc)
        return False

    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                log.warning(
                    "Cron lock Redis close after release failed for job=%s: %s",
                    lock.job_id,
                    exc,
                )
