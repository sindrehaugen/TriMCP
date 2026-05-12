"""Distributed lock helper for singleton cron jobs.

Uses Redis SET NX EX so only one cron instance runs a given job at a time.
Extracted from cron.py to keep it importable without APScheduler.
"""

from __future__ import annotations

import logging

from trimcp.config import cfg

log = logging.getLogger("trimcp.cron")

_CRON_LOCK_PREFIX = "trimcp:cron:lock"


async def acquire_cron_lock(job_id: str, ttl_seconds: int) -> bool:
    """Try to acquire a Redis distributed lock for a singleton cron job.

    Returns True if the lock was acquired (safe to run). Returns True when
    ``REDIS_URL`` is unset (distributed locking disabled). Returns False when
    another instance holds the lock or when Redis cannot be reached
    (fail-closed: skip the run to avoid overlapping singleton jobs).
    """
    if not cfg.REDIS_URL:
        log.warning("REDIS_URL not set — cron distributed lock disabled for %s", job_id)
        return True
    try:
        from redis.asyncio import Redis as AsyncRedis

        client = AsyncRedis.from_url(cfg.REDIS_URL)
        acquired = await client.set(
            f"{_CRON_LOCK_PREFIX}:{job_id}", "1", nx=True, ex=ttl_seconds
        )
        await client.aclose()
        return bool(acquired)
    except Exception as exc:
        log.error("Cron lock acquisition failed for %s: %s", job_id, exc)
        return False  # fail-closed: abort the job on Redis outage to prevent concurrency bugs
