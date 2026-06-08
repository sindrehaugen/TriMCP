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
import time
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
from nce.temporal_decay import _decay_prune_tick, register_decay_jobs

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
)

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


async def _renewal_tick(pool: asyncpg.Pool) -> None:
    ttl = cfg.BRIDGE_CRON_INTERVAL_MINUTES * 60 + 60
    lock: CronLock | None = await acquire_cron_lock("bridge_subscription_renewal", ttl)
    if lock is None:
        log.debug("Skipping bridge_subscription_renewal — lock held by another instance")
        return
    try:
        stats = await renew_expiring_subscriptions(pool)
        log.info("bridge renewal tick: %s", stats)
    except _CRON_TICK_ERRORS as exc:
        log.exception("bridge renewal tick failed unexpectedly")
        await _dispatch_throttled_alert(
            "cron.bridge_subscription_renewal",
            "Cron Job Failed: bridge_subscription_renewal",
            f"Bridge subscription renewal tick failed: {type(exc).__name__}: {exc}",
        )
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
            except _CRON_TICK_ERRORS as exc:
                log.exception("consolidation tick failed for namespace %s", ns_id)
                await _dispatch_throttled_alert(
                    f"cron.sleep_consolidation.{ns_id}",
                    f"Consolidation Failed: Namespace {ns_id}",
                    f"Consolidation tick failed for namespace {ns_id}: {type(exc).__name__}: {exc}",
                )
    except _CRON_TICK_ERRORS as exc:
        log.exception("consolidation tick failed unexpectedly")
        await _dispatch_throttled_alert(
            "cron.sleep_consolidation.global",
            "Cron Job Failed: sleep_consolidation",
            f"Sleep consolidation tick failed unexpectedly: {type(exc).__name__}: {exc}",
        )
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
            await conn.execute(
                f"SELECT nce_ensure_event_log_monthly_partitions({cfg.NCE_PARTITION_LOOKAHEAD_MONTHS})"
            )
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
    except _CRON_TICK_ERRORS as exc:
        log.exception("event_log partition maintenance tick failed")
        await _dispatch_throttled_alert(
            "cron.event_log_partition_maintenance",
            "Cron Job Failed: event_log_partition_maintenance",
            f"Event log partition maintenance tick failed: {type(exc).__name__}: {exc}",
        )
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

            except _CRON_TICK_ERRORS as exc:
                log.exception("[SAGA-RECOVERY] Failed to recover saga=%s", saga_id)
                await _dispatch_throttled_alert(
                    f"cron.saga_recovery.{saga_id}",
                    f"Saga Recovery Failed: Saga {saga_id}",
                    f"Saga recovery tick failed for saga {saga_id}: {type(exc).__name__}: {exc}",
                )

    except _CRON_TICK_ERRORS as exc:
        log.exception("saga recovery tick failed unexpectedly")
        await _dispatch_throttled_alert(
            "cron.saga_recovery.global",
            "Cron Job Failed: saga_recovery",
            f"Saga recovery tick failed unexpectedly: {type(exc).__name__}: {exc}",
        )
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
    except _CRON_TICK_ERRORS as exc:
        log.exception("outbox relay tick failed unexpectedly")
        await _dispatch_throttled_alert(
            "cron.outbox_relay",
            "Cron Job Failed: outbox_relay",
            f"Outbox relay tick failed: {type(exc).__name__}: {exc}",
        )
    finally:
        await release_cron_lock(lock)


async def _reembedding_tick(pool: asyncpg.Pool, mongo_client: Any) -> None:
    """
    APScheduler job: run one re-embedding sweep.

    Non-fatal — a failure is logged but does not crash the scheduler.
    This tick is coalesced (max_instances=1) so a slow run cannot pile up.
    """
    ttl = _REEMBED_INTERVAL * 60 + 60
    lock: CronLock | None = await acquire_cron_lock("reembedding", ttl)
    if lock is None:
        log.debug("Skipping reembedding — lock held by another instance")
        return
    try:
        worker = ReembeddingWorker()
        stats = await worker.run_once(pool, mongo_client)
        log.info("re-embedding tick: %s", stats)
    except _CRON_TICK_ERRORS as exc:
        log.exception("re-embedding tick failed unexpectedly")
        await _dispatch_throttled_alert(
            "cron.reembedding",
            "Cron Job Failed: reembedding",
            f"Re-embedding tick failed: {type(exc).__name__}: {exc}",
        )
    finally:
        await release_cron_lock(lock)


async def _d365_sync_tick(pool: asyncpg.Pool) -> None:
    """
    APScheduler job: run a full Dataverse entity sync for all D365-enabled namespaces.

    Singleton via CronLock — a slow run on one instance prevents other replicas
    from starting a duplicate sync cycle.  Non-fatal: errors are logged and
    do not crash the scheduler.  Only runs when ``NCE_D365_ENABLED=true``.
    """
    if not cfg.NCE_D365_ENABLED:
        return

    ttl = cfg.NCE_D365_SYNC_INTERVAL_MINUTES * 60 + 60
    lock: CronLock | None = await acquire_cron_lock("d365_entity_sync", ttl)
    if lock is None:
        log.debug("Skipping d365_entity_sync — lock held by another instance")
        return

    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(cfg.REDIS_URL)
    try:
        from nce.db_utils import scoped_pg_session
        from nce.vertical_modules.dynamics365.auth import DataverseTokenManager
        from nce.vertical_modules.dynamics365.client import DataverseClient
        from nce.vertical_modules.dynamics365.sync import DataverseSyncEngine

        token_mgr = DataverseTokenManager(redis_client)

        # Scan namespaces that have D365 integration enabled in their metadata.
        async with unmanaged_pg_connection(pool, site="cron.d365_sync.namespace_scan") as conn:
            rows = await conn.fetch(
                """
                SELECT id FROM namespaces
                WHERE COALESCE((metadata->'d365'->>'enabled')::boolean, false) = true
                """
            )

        if not rows:
            log.debug("d365_sync_tick: no namespaces with d365.enabled=true")
            return

        for row in rows:
            ns_id: UUID = row["id"]
            try:
                token = await token_mgr.get_access_token()
                client = DataverseClient(cfg.NCE_D365_ORG_URL, token)
                async with scoped_pg_session(pool, str(ns_id)) as conn:
                    engine = DataverseSyncEngine(conn, ns_id, client)
                    stats = await engine.run_full_sync()
                    log.info("D365 sync tick namespace=%s stats=%s", ns_id, stats)

                # Update last_sync_at in d365_integrations if the row exists
                async with unmanaged_pg_connection(
                    pool, site="cron.d365_sync.update_stats"
                ) as conn:
                    await conn.execute(
                        """
                        UPDATE d365_integrations
                        SET last_sync_at = NOW(), last_sync_stats = $1::jsonb, updated_at = NOW()
                        WHERE namespace_id = $2::uuid AND status = 'ACTIVE'
                        """,
                        json.dumps(stats),
                        ns_id,
                    )
            except _CRON_TICK_ERRORS as exc:
                log.exception("D365 sync tick failed for namespace=%s", ns_id)
                await _dispatch_throttled_alert(
                    f"cron.d365_entity_sync.{ns_id}",
                    f"D365 Sync Failed: Namespace {ns_id}",
                    f"D365 sync tick failed for namespace {ns_id}: {type(exc).__name__}: {exc}",
                )
    except _CRON_TICK_ERRORS as exc:
        log.exception("D365 sync tick failed unexpectedly")
        await _dispatch_throttled_alert(
            "cron.d365_entity_sync.global",
            "Cron Job Failed: d365_entity_sync",
            f"D365 sync tick failed unexpectedly: {type(exc).__name__}: {exc}",
        )
    finally:
        await redis_client.aclose()
        await release_cron_lock(lock)


async def _d365_netbox_bridge_tick(pool: asyncpg.Pool) -> None:
    """
    APScheduler job: cross-reference D365 Accounts/FunctionalLocations with NetBox
    Tenants/Sites for all D365-enabled namespaces.

    Requires ``NCE_D365_NETBOX_BRIDGE_ENABLED=true``, ``NCE_NETBOX_URL``, and
    ``NCE_NETBOX_TOKEN``.  Guard: CronLock prevents duplicate runs across replicas.
    """
    if not cfg.NCE_D365_NETBOX_BRIDGE_ENABLED:
        return
    if not cfg.NCE_NETBOX_URL or not cfg.NCE_NETBOX_TOKEN:
        log.warning("d365_netbox_bridge_tick skipped: NCE_NETBOX_URL or NCE_NETBOX_TOKEN not set")
        return

    ttl = cfg.NCE_D365_NETBOX_BRIDGE_INTERVAL_MINUTES * 60 + 60
    lock: CronLock | None = await acquire_cron_lock("d365_netbox_bridge", ttl)
    if lock is None:
        log.debug("Skipping d365_netbox_bridge — lock held by another instance")
        return

    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(cfg.REDIS_URL)
    try:
        from nce.db_utils import scoped_pg_session
        from nce.vertical_modules.dynamics365.auth import DataverseTokenManager
        from nce.vertical_modules.dynamics365.client import DataverseClient
        from nce.vertical_modules.dynamics365.netbox_bridge import (
            D365NetBoxBridge,
            NetBoxBridgeClient,
        )

        token_mgr = DataverseTokenManager(redis_client)

        async with unmanaged_pg_connection(
            pool, site="cron.d365_netbox_bridge.namespace_scan"
        ) as conn:
            rows = await conn.fetch(
                """
                SELECT id FROM namespaces
                WHERE COALESCE((metadata->'d365'->>'enabled')::boolean, false) = true
                """
            )

        if not rows:
            log.debug("d365_netbox_bridge_tick: no namespaces with d365.enabled=true")
            return

        nb_client = NetBoxBridgeClient(
            base_url=cfg.NCE_NETBOX_URL,
            token=cfg.NCE_NETBOX_TOKEN,
        )

        for row in rows:
            ns_id: UUID = row["id"]
            try:
                token = await token_mgr.get_access_token()
                d365_client = DataverseClient(cfg.NCE_D365_ORG_URL, token)
                async with scoped_pg_session(pool, str(ns_id)) as conn:
                    bridge = D365NetBoxBridge(
                        conn=conn,
                        namespace_id=ns_id,
                        d365_client=d365_client,
                        netbox_client=nb_client,
                    )
                    stats = await bridge.run_full_bridge_sync()
                    log.info("D365↔NetBox bridge tick ns=%s stats=%s", ns_id, stats)
            except _CRON_TICK_ERRORS as exc:
                log.exception("D365↔NetBox bridge tick failed for namespace=%s", ns_id)
                await _dispatch_throttled_alert(
                    f"cron.d365_netbox_bridge.{ns_id}",
                    f"D365 NetBox Bridge Failed: Namespace {ns_id}",
                    f"D365 NetBox bridge tick failed for namespace {ns_id}: {type(exc).__name__}: {exc}",
                )
    except _CRON_TICK_ERRORS as exc:
        log.exception("D365↔NetBox bridge tick failed unexpectedly")
        await _dispatch_throttled_alert(
            "cron.d365_netbox_bridge.global",
            "Cron Job Failed: d365_netbox_bridge",
            f"D365 NetBox bridge tick failed unexpectedly: {type(exc).__name__}: {exc}",
        )
    finally:
        await redis_client.aclose()
        await release_cron_lock(lock)


async def _chain_verification_tick(pool: asyncpg.Pool) -> None:
    """Run Merkle chain verification for all namespaces.

    Sets the MERKLE_CHAIN_VALID gauge (1=valid, 0=corrupted).
    On verification failure, logs critical, dispatches an alert,
    and appends a 'chain_verification_failed' audit event.
    """
    ttl = cfg.NCE_CHAIN_VERIFY_INTERVAL_MINUTES * 60 + 60
    lock: CronLock | None = await acquire_cron_lock("chain_verification", ttl)
    if lock is None:
        log.debug("Skipping chain_verification — lock held by another instance")
        return
    try:
        from nce.event_log import append_event, verify_merkle_chain
        from nce.notifications import dispatcher
        from nce.observability import MERKLE_CHAIN_VALID

        async with unmanaged_pg_connection(pool, site="cron.chain_verify.namespace_scan") as conn:
            rows = await conn.fetch("SELECT id FROM namespaces")

        all_valid = True
        for row in rows:
            ns_id: UUID = row["id"]
            try:
                async with scoped_pg_session(pool, ns_id) as conn:
                    depth = cfg.NCE_CHAIN_VERIFY_STARTUP_DEPTH
                    if depth > 0:
                        max_seq = await conn.fetchval(
                            "SELECT COALESCE(max(event_seq), 0) FROM event_log"
                        )
                        start_seq = max(1, max_seq - depth + 1)
                    else:
                        start_seq = 1

                    res = await verify_merkle_chain(conn, namespace_id=ns_id, start_seq=start_seq)
                    if not res.get("valid", True):
                        all_valid = False
                        first_break = res.get("first_break")
                        reason = res.get("reason") or "Merkle chain signature or hash mismatch"

                        log.critical(
                            "[CHAIN-VERIFICATION] Merkle chain corrupted for namespace=%s. "
                            "First break at event_seq=%s. Reason=%s",
                            ns_id,
                            first_break,
                            reason,
                        )

                        title = f"Merkle Chain Corrupted: Namespace {ns_id}"
                        message = (
                            f"Critical data integrity failure: Merkle chain verification failed "
                            f"for namespace {ns_id}. First break at event_seq {first_break}. "
                            f"Reason: {reason}"
                        )
                        await dispatcher.dispatch_alert(title, message)

                        await append_event(
                            conn=conn,
                            namespace_id=ns_id,
                            agent_id="cron.chain_verify",
                            event_type="chain_verification_failed",
                            params={
                                "first_break": first_break,
                                "reason": reason,
                            },
                        )
            except _CRON_TICK_ERRORS as exc:
                log.exception("Error running Merkle chain verification for namespace %s", ns_id)
                all_valid = False
                await _dispatch_throttled_alert(
                    f"cron.chain_verification.{ns_id}",
                    f"Chain Verification Failed: Namespace {ns_id}",
                    f"Merkle chain verification job failed for namespace {ns_id}: {type(exc).__name__}: {exc}",
                )

        if all_valid:
            MERKLE_CHAIN_VALID.set(1)
        else:
            MERKLE_CHAIN_VALID.set(0)

    except _CRON_TICK_ERRORS as exc:
        log.exception("chain verification tick failed unexpectedly")
        await _dispatch_throttled_alert(
            "cron.chain_verification.global",
            "Cron Job Failed: chain_verification",
            f"Merkle chain verification cron tick failed unexpectedly: {type(exc).__name__}: {exc}",
        )
    finally:
        await release_cron_lock(lock)


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

    if cfg.NCE_D365_ENABLED:
        d365_minutes = max(5, int(cfg.NCE_D365_SYNC_INTERVAL_MINUTES))
        scheduler.add_job(
            _d365_sync_tick,
            IntervalTrigger(minutes=d365_minutes),
            args=[pool],
            id="d365_entity_sync",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )

    if cfg.NCE_D365_NETBOX_BRIDGE_ENABLED:
        bridge_minutes = max(10, int(cfg.NCE_D365_NETBOX_BRIDGE_INTERVAL_MINUTES))
        scheduler.add_job(
            _d365_netbox_bridge_tick,
            IntervalTrigger(minutes=bridge_minutes),
            args=[pool],
            id="d365_netbox_bridge",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )

    register_decay_jobs(scheduler, pool)

    verify_minutes = max(5, int(cfg.NCE_CHAIN_VERIFY_INTERVAL_MINUTES))
    scheduler.add_job(
        _chain_verification_tick,
        IntervalTrigger(minutes=verify_minutes),
        args=[pool],
        id="chain_verification",
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
    startup_coros = [
        _renewal_tick(pool),
        _reembedding_tick(pool, mongo_client),
        _consolidation_tick(pool, mongo_client),
        _partition_maintenance_tick(pool),
        _saga_recovery_tick(pool),
        _outbox_relay_tick(pool),
        _decay_prune_tick(pool),
        _chain_verification_tick(pool),
    ]
    if cfg.NCE_D365_ENABLED:
        startup_coros.append(_d365_sync_tick(pool))
    if cfg.NCE_D365_NETBOX_BRIDGE_ENABLED:
        startup_coros.append(_d365_netbox_bridge_tick(pool))

    startup_results = await asyncio.gather(*startup_coros, return_exceptions=True)
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
