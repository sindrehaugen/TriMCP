"""
Bridge subscription renewal scheduler (§10.7).

Runs an APScheduler interval job that calls ``renew_expiring_subscriptions``:
subscriptions with ``expires_at`` within ``BRIDGE_RENEWAL_LOOKAHEAD_HOURS`` are
renewed via provider APIs; failures mark rows ``DEGRADED``.

Run (from repo root, with env / PG_DSN configured)::

    python -m trimcp.cron
"""
from __future__ import annotations

import asyncio
import logging

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from trimcp.bridge_renewal import renew_expiring_subscriptions
from trimcp.config import cfg

log = logging.getLogger("trimcp.cron")


async def _renewal_tick(pool: asyncpg.Pool) -> None:
    try:
        stats = await renew_expiring_subscriptions(pool)
        log.info("bridge renewal tick: %s", stats)
    except Exception:
        log.exception("bridge renewal tick failed unexpectedly")


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [trimcp.cron] %(levelname)s %(message)s",
    )
    cfg.validate()

    pool = await asyncpg.create_pool(
        cfg.PG_DSN,
        min_size=1,
        max_size=3,
        command_timeout=120,
    )
    minutes = max(1, int(cfg.BRIDGE_CRON_INTERVAL_MINUTES))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _renewal_tick,
        IntervalTrigger(minutes=minutes),
        args=[pool],
        id="bridge_subscription_renewal",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Started bridge renewal scheduler: interval=%s min, lookahead=%s h",
        minutes,
        cfg.BRIDGE_RENEWAL_LOOKAHEAD_HOURS,
    )
    await _renewal_tick(pool)
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=True)
        await pool.close()
        log.info("Bridge cron shutdown complete.")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
