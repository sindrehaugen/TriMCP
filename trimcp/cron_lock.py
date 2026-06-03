"""
Distributed lock helper for singleton cron jobs.

Uses Redis SET NX EX so only one cron instance runs a given job at a time.
Extracted from cron.py to keep it importable without APScheduler.

Lock primitives (Lua CAS script, token generation) are centralised in
``trimcp.redis_lock`` and imported here — single definition, no duplication.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from trimcp.config import cfg
from trimcp.redis_lock import acquire_lock as _acquire_lock
from trimcp.redis_lock import release_lock as _release_lock

log = logging.getLogger("trimcp.cron")

_CRON_LOCK_PREFIX = "trimcp:cron:lock"
_JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_.:-]{1,128}$")

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


async def acquire_cron_lock(
    job_id: str,
    ttl_seconds: int,
    *,
    redis_client: Any | None = None,
) -> CronLock | None:
    """Try to acquire a Redis distributed lock for a singleton cron job.

    Parameters
    ----------
    job_id:
        Unique cron job name — must match ``[a-zA-Z0-9_.:-]{1,128}``.
    ttl_seconds:
        Lock TTL.  Acts as a safety net if the process dies before
        :func:`release_cron_lock` is called.
    redis_client:
        Optional open ``redis.asyncio.Redis`` instance.  When supplied the
        caller owns its lifetime — this function will not close it.  When
        omitted a temporary client is created and destroyed automatically.
        Pass a shared client from the caller to avoid one TCP round-trip per
        lock acquisition.

    Returns
    -------
    CronLock
        If the lock was acquired — pass to :func:`release_cron_lock`.
    None
        If another instance holds the lock, Redis is unreachable, or locking
        is required but unavailable (production with no REDIS_URL).
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

    owned_client = redis_client is None
    client = redis_client
    try:
        if owned_client:
            from redis.asyncio import Redis as AsyncRedis

            client = AsyncRedis.from_url(cfg.REDIS_URL)

        token = await _acquire_lock(client, key, ttl_seconds)
        if token is None:
            return None

        return CronLock(job_id=job_id, key=key, token=token, ttl_seconds=ttl_seconds)

    except Exception as exc:
        log.error("Cron lock acquisition failed for job=%s: %s", job_id, exc)
        return None

    finally:
        if owned_client and client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                log.warning("Cron lock Redis close failed for job=%s: %s", job_id, exc)


async def release_cron_lock(
    lock: CronLock,
    *,
    redis_client: Any | None = None,
) -> bool:
    """Release a cron lock only if this process still owns it (compare-and-delete).

    Safe to call even if the TTL has expired or another instance has taken
    over — the Lua CAS script returns 0 without deleting another owner's lock.

    Parameters
    ----------
    lock:
        The :class:`CronLock` returned by :func:`acquire_cron_lock`.
    redis_client:
        Optional shared client (same contract as :func:`acquire_cron_lock`).
    """
    if lock.token == _LOCAL_DISABLED:
        return True

    owned_client = redis_client is None
    client = redis_client
    try:
        if owned_client:
            from redis.asyncio import Redis as AsyncRedis

            client = AsyncRedis.from_url(cfg.REDIS_URL)

        return await _release_lock(client, lock.key, lock.token)

    except Exception as exc:
        log.warning("Cron lock release failed for job=%s: %s", lock.job_id, exc)
        return False

    finally:
        if owned_client and client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                log.warning(
                    "Cron lock Redis close after release failed for job=%s: %s",
                    lock.job_id,
                    exc,
                )
