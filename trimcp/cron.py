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
import json
import logging
import random
from typing import Any
from uuid import UUID

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from trimcp.bridge_renewal import renew_expiring_subscriptions
from trimcp.config import cfg
from trimcp.cron_lock import acquire_cron_lock as _acquire_cron_lock
from trimcp.reembedding_worker import CRON_INTERVAL_MINUTES as _REEMBED_INTERVAL
from trimcp.reembedding_worker import ReembeddingWorker

log = logging.getLogger("trimcp.cron")


async def _renewal_tick(pool: asyncpg.Pool) -> None:
    ttl = cfg.BRIDGE_CRON_INTERVAL_MINUTES * 60 + 60
    if not await _acquire_cron_lock("bridge_subscription_renewal", ttl):
        log.debug("Skipping bridge_subscription_renewal — lock held by another instance")
        return
    try:
        stats = await renew_expiring_subscriptions(pool)
        log.info("bridge renewal tick: %s", stats)
    except Exception:
        log.exception("bridge renewal tick failed unexpectedly")


async def _consolidation_tick(pool: asyncpg.Pool) -> None:
    """
    Run sleep consolidation for each namespace with metadata.consolidation.enabled=true.

    Sequential per-namespace runs; failures are logged and do not stop other namespaces.
    """
    ttl = min(cfg.CONSOLIDATION_CRON_INTERVAL_MINUTES * 60, 7200) + 60
    if not await _acquire_cron_lock("sleep_consolidation", ttl):
        log.debug("Skipping sleep_consolidation — lock held by another instance")
        return
    try:
        from trimcp.consolidation import ConsolidationWorker
        from trimcp.providers import get_provider

        rows = await pool.fetch("""
            SELECT id, metadata FROM namespaces
            WHERE COALESCE((metadata->'consolidation'->>'enabled')::boolean, false) = true
            """)
        for row in rows:
            ns_id: UUID = row["id"]
            raw_meta = row["metadata"]
            if raw_meta is None:
                meta: dict = {}
            elif isinstance(raw_meta, dict):
                meta = raw_meta
            else:
                meta = json.loads(raw_meta)
            try:
                provider = get_provider(meta or {})
                worker = ConsolidationWorker(pool, provider)
                await worker.run_consolidation(ns_id)
                log.info("consolidation tick completed for namespace %s", ns_id)
            except Exception:
                log.exception("consolidation tick failed for namespace %s", ns_id)
    except Exception:
        log.exception("consolidation tick failed unexpectedly")


async def _partition_maintenance_tick(pool: asyncpg.Pool) -> None:
    """
    Ensure event_log monthly partitions exist ahead of time.
    Re-entrant: the PostgreSQL function uses IF NOT EXISTS.
    """
    if not await _acquire_cron_lock("event_log_partition_maintenance", 3600):
        log.debug("Skipping event_log_partition_maintenance — lock held by another instance")
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT trimcp_ensure_event_log_monthly_partitions(3)")
            # Update Prometheus gauge with how many future partitions exist
            row = await conn.fetchrow(
                """
                SELECT count(*) AS cnt
                FROM pg_inherits i
                JOIN pg_class c ON c.oid = i.inhrelid
                WHERE i.inhparent = 'event_log'::regclass
                  AND c.relname LIKE 'event_log_%'
                  AND c.relname > 'event_log_' || to_char(now(), 'YYYY_MM')
                """
            )
            from trimcp.observability import EVENT_LOG_PARTITION_MONTHS_AHEAD

            months_ahead = row["cnt"] if row else 0
            EVENT_LOG_PARTITION_MONTHS_AHEAD.set(months_ahead)
            log.info("event_log partition maintenance complete: %s months ahead", months_ahead)
            if months_ahead < 2:
                log.warning(
                    "event_log partition runway low: only %s months ahead (need >= 2)",
                    months_ahead,
                )
    except Exception:
        log.exception("event_log partition maintenance tick failed")


async def _saga_recovery_tick(pool: asyncpg.Pool) -> None:
    """
    Re-drive rollback for sagas that crashed between PG commit and completion.
    Stale 'pg_committed' rows older than 5 minutes are assumed zombie sagas.
    """
    try:
        from trimcp.auth import set_namespace_context
        from trimcp.event_log import append_event

        rows = await pool.fetch(
            """
            SELECT id, namespace_id, agent_id, payload
            FROM saga_execution_log
            WHERE state = 'pg_committed'
              AND created_at < now() - interval '5 minutes'
            ORDER BY created_at
            LIMIT 100
            """
        )
        for row in rows:
            saga_id: str = str(row["id"])
            ns_id: str = str(row["namespace_id"])
            agent_id: str = row["agent_id"]
            payload: dict = row["payload"] if isinstance(row["payload"], dict) else {}
            memory_id = payload.get("memory_id")

            log.warning(
                "[SAGA-RECOVERY] Re-driving rollback for saga=%s memory_id=%s",
                saga_id,
                memory_id,
            )
            try:
                async with pool.acquire() as conn:
                    await set_namespace_context(conn, UUID(ns_id))
                    await conn.execute(
                        """
                        UPDATE saga_execution_log
                        SET state = 'recovery_needed', updated_at = NOW()
                        WHERE id = $1::uuid
                        """,
                        saga_id,
                    )
                    if memory_id:
                        # Soft-close memory
                        await conn.execute(
                            """
                            UPDATE memories
                            SET valid_to = NOW()
                            WHERE id = $1::uuid AND namespace_id = $2::uuid AND valid_to IS NULL
                            """,
                            memory_id,
                            ns_id,
                        )
                        # Compensating event
                        await append_event(
                            conn=conn,
                            namespace_id=UUID(ns_id),
                            agent_id=agent_id,
                            event_type="store_memory_rolled_back",
                            params={
                                "memory_id": memory_id,
                                "reason": "saga_recovery_cron",
                                "saga_id": saga_id,
                            },
                        )
                    # Mark rolled_back
                    await conn.execute(
                        """
                        UPDATE saga_execution_log
                        SET state = 'rolled_back', updated_at = NOW()
                        WHERE id = $1::uuid
                        """,
                        saga_id,
                    )
                log.info("[SAGA-RECOVERY] Rolled back saga=%s", saga_id)
            except Exception:
                log.exception("[SAGA-RECOVERY] Failed to recover saga=%s", saga_id)
    except Exception:
        log.exception("saga recovery tick failed unexpectedly")


async def _reembedding_tick(pool: asyncpg.Pool, mongo_client: Any) -> None:
    """
    APScheduler job: run one re-embedding sweep.

    Non-fatal — a failure is logged but does not crash the scheduler.
    This tick is coalesced (max_instances=1) so a slow run cannot pile up.
    """
    try:
        worker = ReembeddingWorker()
        stats = await worker.run_once(pool, mongo_client)
        log.info("re-embedding tick: %s", stats)
    except Exception:
        log.exception("re-embedding tick failed unexpectedly")


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [trimcp.cron] %(levelname)s %(message)s",
    )
    cfg.validate()

    # Startup jitter — randomized one-time offset to spread database CPU
    # load when multiple TriMCP instances boot simultaneously.  The jitter
    # is applied before the connection pool is created, so it does not hold
    # any database resources while waiting.
    jitter = random.uniform(0.0, cfg.CRON_STARTUP_JITTER_MAX_SECONDS)
    if jitter > 0.0:
        log.info(
            "Applying %.1fs startup jitter to avoid thundering herd "
            "(CRON_STARTUP_JITTER_MAX_SECONDS=%.0f)",
            jitter,
            cfg.CRON_STARTUP_JITTER_MAX_SECONDS,
        )
        await asyncio.sleep(jitter)

    pool = await asyncpg.create_pool(
        cfg.PG_DSN,
        min_size=1,
        max_size=4,  # +1 for the re-embedding worker
        command_timeout=120,
    )

    # Optional Mongo client for re-embedding text resolution.
    mongo_client: Any = None
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        mongo_client = AsyncIOMotorClient(cfg.MONGO_URI, serverSelectionTimeoutMS=5_000)
    except ImportError:
        log.warning("motor not available — re-embedding will use fallback text only.")

    renewal_minutes = max(1, int(cfg.BRIDGE_CRON_INTERVAL_MINUTES))
    reembed_minutes = max(1, int(_REEMBED_INTERVAL))
    consolidation_minutes = max(1, int(cfg.CONSOLIDATION_CRON_INTERVAL_MINUTES))

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        _renewal_tick,
        IntervalTrigger(minutes=renewal_minutes),
        args=[pool],
        id="bridge_subscription_renewal",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        _reembedding_tick,
        IntervalTrigger(minutes=reembed_minutes),
        args=[pool, mongo_client],
        id="phase_2_1_reembedding",
        coalesce=True,
        max_instances=1,  # never overlap runs
        replace_existing=True,
    )

    scheduler.add_job(
        _consolidation_tick,
        IntervalTrigger(minutes=consolidation_minutes),
        args=[pool],
        id="sleep_consolidation",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        _partition_maintenance_tick,
        CronTrigger(day=1, hour=0, minute=0),  # first of every month at 00:00 UTC
        args=[pool],
        id="event_log_partition_maintenance",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        _saga_recovery_tick,
        IntervalTrigger(minutes=5),
        args=[pool],
        id="saga_recovery",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    scheduler.start()
    log.info(
        "Started bridge renewal scheduler: interval=%s min, lookahead=%s h",
        renewal_minutes,
        cfg.BRIDGE_RENEWAL_LOOKAHEAD_HOURS,
    )
    log.info(
        "Started re-embedding scheduler: interval=%s min, model=%s",
        reembed_minutes,
        cfg.TRIMCP_LLM_PROVIDER,
    )
    log.info(
        "Started consolidation scheduler: interval=%s min (namespaces with consolidation.enabled)",
        consolidation_minutes,
    )

    # Fire maintenance jobs immediately on startup so the first interval is not wasted.
    await _renewal_tick(pool)
    await _reembedding_tick(pool, mongo_client)
    await _consolidation_tick(pool)
    await _partition_maintenance_tick(pool)
    await _saga_recovery_tick(pool)

    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=True)
        await pool.close()
        if mongo_client:
            mongo_client.close()
        log.info("Cron shutdown complete.")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
