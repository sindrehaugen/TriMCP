"""
Bridge subscription renewal scheduler (§10.7).

Runs an APScheduler interval job that calls ``renew_expiring_subscriptions``:
subscriptions with ``expires_at`` within ``BRIDGE_RENEWAL_LOOKAHEAD_HOURS`` are
renewed via provider APIs; failures mark rows ``DEGRADED``.

Run (from repo root, with env / PG_DSN configured)::

    python -m nce.cron
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

from nce.bridge_renewal import renew_expiring_subscriptions
from nce.config import cfg
from nce.cron_lock import CronLock, acquire_cron_lock, release_cron_lock
from nce.db_utils import scoped_pg_session, unmanaged_pg_connection
from nce.reembedding_worker import CRON_INTERVAL_MINUTES as _REEMBED_INTERVAL
from nce.reembedding_worker import ReembeddingWorker

log = logging.getLogger("nce.cron")

# Cron ticks must never crash the scheduler; catch operational failures only.
_CRON_TICK_ERRORS: tuple[type[BaseException], ...] = (
    asyncpg.PostgresError,
    OSError,
    TimeoutError,
    ValueError,
    TypeError,
    KeyError,
    json.JSONDecodeError,
    RuntimeError,
)


async def _renewal_tick(pool: asyncpg.Pool) -> None:
    ttl = cfg.BRIDGE_CRON_INTERVAL_MINUTES * 60 + 60
    lock: CronLock | None = await acquire_cron_lock("bridge_subscription_renewal", ttl)
    if lock is None:
        log.debug("Skipping bridge_subscription_renewal — lock held by another instance")
        return
    try:
        stats = await renew_expiring_subscriptions(pool)
        log.info("bridge renewal tick: %s", stats)
    except _CRON_TICK_ERRORS:
        log.exception("bridge renewal tick failed unexpectedly")
    finally:
        await release_cron_lock(lock)


async def _consolidation_tick(pool: asyncpg.Pool, mongo_client: Any | None = None) -> None:
    """
    Run sleep consolidation for each namespace with metadata.consolidation.enabled=true.

    Sequential per-namespace runs; failures are logged and do not stop other namespaces.

    Mongo is optional for tests / degraded runs; when set, episodic payloads are hydrated
    in bulk before consolidation LLM calls.
    """
    ttl = min(cfg.CONSOLIDATION_CRON_INTERVAL_MINUTES * 60, 7200) + 60
    lock: CronLock | None = await acquire_cron_lock("sleep_consolidation", ttl)
    if lock is None:
        log.debug("Skipping sleep_consolidation — lock held by another instance")
        return
    try:
        from nce.consolidation import ConsolidationWorker
        from nce.providers import get_provider

        # namespaces is a global admin table — unmanaged connection is correct here.
        async with unmanaged_pg_connection(pool, site="cron.consolidation.namespaces_scan") as conn:
            rows = await conn.fetch("""
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
                worker = ConsolidationWorker(pool, provider, mongo_client=mongo_client)
                await worker.run_consolidation(ns_id)
                log.info("consolidation tick completed for namespace %s", ns_id)
            except _CRON_TICK_ERRORS:
                log.exception("consolidation tick failed for namespace %s", ns_id)
    except _CRON_TICK_ERRORS:
        log.exception("consolidation tick failed unexpectedly")
    finally:
        await release_cron_lock(lock)


async def _partition_maintenance_tick(pool: asyncpg.Pool) -> None:
    """
    Ensure event_log monthly partitions exist ahead of time.
    Re-entrant: the PostgreSQL function uses IF NOT EXISTS.
    """
    lock: CronLock | None = await acquire_cron_lock("event_log_partition_maintenance", 3600)
    if lock is None:
        log.debug("Skipping event_log_partition_maintenance — lock held by another instance")
        return
    try:
        async with unmanaged_pg_connection(pool, site="cron.partition_maintenance") as conn:
            await conn.execute("SELECT nce_ensure_event_log_monthly_partitions(3)")
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
            from nce.observability import EVENT_LOG_PARTITION_MONTHS_AHEAD

            months_ahead = row["cnt"] if row else 0
            EVENT_LOG_PARTITION_MONTHS_AHEAD.set(months_ahead)
            log.info("event_log partition maintenance complete: %s months ahead", months_ahead)
            if months_ahead < 2:
                log.warning(
                    "event_log partition runway low: only %s months ahead (need >= 2)",
                    months_ahead,
                )
    except _CRON_TICK_ERRORS:
        log.exception("event_log partition maintenance tick failed")
    finally:
        await release_cron_lock(lock)


async def _saga_recovery_tick(pool: asyncpg.Pool) -> None:
    """
    Finalize sagas that committed to PG but never advanced to 'completed'.

    A saga in state 'pg_committed' older than 5 minutes means the application
    crashed between the PG commit and the downstream completion signal. Because
    the memory already exists in Postgres (pg_committed = data is durable), the
    correct recovery action is to VERIFY and COMPLETE, NOT to rollback.

    Recovery steps per saga:
      1. Verify the target memory row exists in memories.
      2. If it exists: mark saga 'completed' + append 'saga_recovered' event.
      3. If it is missing: the saga committed but the memory row was lost (rare) —
         mark 'failed' for manual review rather than attempting blind rollback.

    We do NOT soft-delete (valid_to=now()) pg_committed memories.
    'pg_committed' means PG says the memory is there — trust the DB.
    """
    lock: CronLock | None = await acquire_cron_lock("saga_recovery", 600)
    if lock is None:
        log.debug("Skipping saga_recovery — lock held by another instance")
        return
    try:
        from nce.event_log import append_event

        # Read saga candidates without an RLS scope — saga_execution_log is a
        # global admin table, not tenant-partitioned by RLS.
        async with unmanaged_pg_connection(pool, site="cron.saga_recovery.list_stuck") as conn:
            rows = await conn.fetch(
                """
                SELECT id, namespace_id, agent_id, payload
                FROM saga_execution_log
                WHERE state = 'pg_committed'
                  AND COALESCE(updated_at, created_at) < now() - interval '5 minutes'
                ORDER BY COALESCE(updated_at, created_at)
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
                "[SAGA-RECOVERY] Found pg_committed saga=%s memory_id=%s — verifying memory exists",
                saga_id,
                memory_id,
            )
            try:
                if memory_id:
                    # Step 1: verify memory exists via RLS-scoped session.
                    async with scoped_pg_session(pool, ns_id) as conn:
                        memory_row = await conn.fetchrow(
                            """
                            SELECT id FROM memories
                            WHERE id = $1::uuid AND namespace_id = $2::uuid
                            """,
                            memory_id,
                            ns_id,
                        )

                    if memory_row is None:
                        # Memory row is missing despite pg_committed state.
                        # Do NOT rollback blindly — mark failed for human review.
                        log.error(
                            "[SAGA-RECOVERY] saga=%s is pg_committed but memory=%s is "
                            "MISSING from memories table. Marking 'failed' for manual review.",
                            saga_id,
                            memory_id,
                        )
                        async with unmanaged_pg_connection(
                            pool, site="cron.saga_recovery.mark_failed"
                        ) as conn:
                            await conn.execute(
                                """
                                UPDATE saga_execution_log
                                SET state = 'failed', updated_at = NOW()
                                WHERE id = $1::uuid AND state = 'pg_committed'
                                """,
                                saga_id,
                            )
                        continue

                    # Step 2: memory exists — finalize saga + append recovery event.
                    async with scoped_pg_session(pool, ns_id) as conn:
                        await append_event(
                            conn=conn,
                            namespace_id=UUID(ns_id),
                            agent_id=agent_id,
                            event_type="saga_recovered",
                            params={
                                "memory_id": memory_id,
                                "saga_id": saga_id,
                                "recovery_action": "finalized",
                                "reason": "pg_committed_saga_recovery_cron",
                            },
                        )
                        await conn.execute(
                            """
                            UPDATE saga_execution_log
                            SET state = 'completed', updated_at = NOW()
                            WHERE id = $1::uuid AND state = 'pg_committed'
                            """,
                            saga_id,
                        )
                    log.info("[SAGA-RECOVERY] Finalized saga=%s memory=%s", saga_id, memory_id)

                else:
                    # No memory_id in payload — mark completed, nothing to verify.
                    log.warning(
                        "[SAGA-RECOVERY] saga=%s has no memory_id in payload. "
                        "Marking completed (no memory to verify).",
                        saga_id,
                    )
                    async with unmanaged_pg_connection(
                        pool, site="cron.saga_recovery.mark_completed_no_memory"
                    ) as conn:
                        await conn.execute(
                            """
                            UPDATE saga_execution_log
                            SET state = 'completed', updated_at = NOW()
                            WHERE id = $1::uuid AND state = 'pg_committed'
                            """,
                            saga_id,
                        )

            except _CRON_TICK_ERRORS:
                log.exception("[SAGA-RECOVERY] Failed to recover saga=%s", saga_id)

    except _CRON_TICK_ERRORS:
        log.exception("saga recovery tick failed unexpectedly")
    finally:
        await release_cron_lock(lock)


async def _outbox_relay_tick(pool: asyncpg.Pool) -> None:
    """Drain pending outbox events (same relay as MCP stdio background loop)."""
    from nce.outbox_relay import run_outbox_relay_once

    ttl = max(cfg.OUTBOX_RELAY_INTERVAL_SECONDS * 2, 30)
    lock: CronLock | None = await acquire_cron_lock("outbox_relay", ttl)
    if lock is None:
        log.debug("Skipping outbox_relay — lock held by another instance")
        return
    try:
        delivered = await run_outbox_relay_once(pool)
        if delivered:
            log.info("outbox relay tick delivered=%s", delivered)
    except _CRON_TICK_ERRORS:
        log.exception("outbox relay tick failed unexpectedly")
    finally:
        await release_cron_lock(lock)


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
    except _CRON_TICK_ERRORS:
        log.exception("re-embedding tick failed unexpectedly")


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [nce.cron] %(levelname)s %(message)s",
    )
    cfg.validate()

    # Startup jitter — randomized one-time offset to spread database CPU
    # load when multiple NCE instances boot simultaneously.  The jitter
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
        args=[pool, mongo_client],
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

    outbox_seconds = max(1, int(cfg.OUTBOX_RELAY_INTERVAL_SECONDS))
    scheduler.add_job(
        _outbox_relay_tick,
        IntervalTrigger(seconds=outbox_seconds),
        args=[pool],
        id="outbox_relay",
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
        cfg.NCE_LLM_PROVIDER,
    )
    log.info(
        "Started consolidation scheduler: interval=%s min (namespaces with consolidation.enabled)",
        consolidation_minutes,
    )
    log.info("Started outbox relay scheduler: interval=%s s", outbox_seconds)

    # Fire maintenance jobs immediately on startup so the first interval is not wasted.
    # Run concurrently — sequential awaits would delay the event loop by the sum of all
    # tick durations; _reembedding_tick in particular can take minutes.  Each tick already
    # catches and logs its own errors, so we gather with return_exceptions=True as a
    # belt-and-suspenders guard.
    startup_results = await asyncio.gather(
        _renewal_tick(pool),
        _reembedding_tick(pool, mongo_client),
        _consolidation_tick(pool, mongo_client),
        _partition_maintenance_tick(pool),
        _saga_recovery_tick(pool),
        _outbox_relay_tick(pool),
        return_exceptions=True,
    )
    for _result in startup_results:
        if isinstance(_result, BaseException):
            log.error("Startup tick raised uncaught exception: %s", _result)

    try:
        await asyncio.Event().wait()
    finally:
        await asyncio.to_thread(scheduler.shutdown, wait=True)
        await pool.close()
        if mongo_client:
            mongo_client.close()
        log.info("Cron shutdown complete.")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
