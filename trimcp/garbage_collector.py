"""
Tri-Stack Garbage Collector
Runs every hour as an async background task.
Finds MongoDB documents older than GC_ORPHAN_AGE_SECONDS with no matching payload_ref
in either PG table (memories or memories), then deletes them.
Guarantees data purity even if the Python process is hard-killed mid-transaction.

Hardening:
- PG scan is paginated (PAGE_SIZE rows at a time) — safe on million-row tables.
- Startup uses exponential backoff so a slow Docker start never crashes the GC.
- Pool size is bounded; command timeout prevents hung queries.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from trimcp.auth import set_namespace_context
from trimcp.config import cfg, redact_secrets_in_text

_GC_LOCK_KEY: str = "trimcp:gc:lock"
_GC_LOCK_TTL_SECONDS: int = cfg.GC_INTERVAL_SECONDS + 60


async def _acquire_gc_lock() -> bool:
    """Try to acquire a Redis distributed lock for the GC singleton.

    Returns ``True`` if the lock was acquired, ``False`` if another
    instance is already running.
    """
    if not cfg.REDIS_URL:
        log.warning("REDIS_URL not set — GC distributed lock disabled; "
                    "multiple instances may race.")
        return True
    try:
        from redis.asyncio import Redis as AsyncRedis
        client = AsyncRedis.from_url(cfg.REDIS_URL)
        acquired = await client.set(_GC_LOCK_KEY, "1", nx=True, ex=_GC_LOCK_TTL_SECONDS)
        await client.aclose()
        return bool(acquired)
    except Exception as exc:
        log.error("GC lock acquisition failed: %s", exc)
        return False  # fail-closed: abort the job on Redis outage to prevent concurrency bugs

log = logging.getLogger("tri-stack-gc")

PAGE_SIZE = cfg.GC_PAGE_SIZE  # rows fetched per PG cursor page
MAX_CONNECT_ATTEMPTS = cfg.GC_MAX_CONNECT_ATTEMPTS
CONNECT_BASE_DELAY = cfg.GC_CONNECT_BASE_DELAY  # seconds; doubles each retry
CHUNK_DELETE_SIZE = 1000  # rows deleted per chunk to prevent table locks


# --- Connection helpers with retry ---


async def _connect_with_retry() -> tuple[AsyncIOMotorClient, asyncpg.Pool]:
    """
    Attempt to connect to Mongo and PG with exponential backoff.
    Raises RuntimeError after MAX_CONNECT_ATTEMPTS failures.
    """
    delay = CONNECT_BASE_DELAY
    last_exc: Exception | None = None

    for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
        try:
            mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(
                cfg.MONGO_URI,
                serverSelectionTimeoutMS=5_000,
            )
            # Force a real connection check
            await mongo_client.admin.command("ping")

            pg_pool = await asyncpg.create_pool(
                cfg.PG_DSN,
                min_size=1,
                max_size=3,  # GC needs very few connections
                command_timeout=30,
            )
            log.info("GC connected on attempt %d.", attempt)
            return mongo_client, pg_pool

        except Exception as exc:
            last_exc = exc
            log.warning(
                "GC connect attempt %d/%d failed: %s. Retrying in %.0fs.",
                attempt,
                MAX_CONNECT_ATTEMPTS,
                exc,
                delay,
            )
            if attempt < MAX_CONNECT_ATTEMPTS:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    raise RuntimeError(
        f"GC could not connect after {MAX_CONNECT_ATTEMPTS} attempts: {last_exc}"
    )


# --- Paginated PG reference set builder ---


async def _fetch_pg_ref_batch(conn: asyncpg.Connection, table: str, last_seen_id: UUID, limit: int) -> list[asyncpg.Record]:
    """Fetch a batch of payload_refs using keyset pagination."""
    # Keyset pagination — table name is from a hardcoded tuple, not user input
    return await conn.fetch(
        f"SELECT id, payload_ref FROM {table} "  # noqa: S608 — table is not user-controlled
        f"WHERE payload_ref IS NOT NULL AND id > $1 "
        f"ORDER BY id LIMIT $2",
        last_seen_id,
        limit,
    )


async def _fetch_pg_refs(pg_pool: asyncpg.Pool, namespaces: list[UUID]) -> set[str]:
    """
    Build the set of all known mongo_ref_ids in PG using keyset-based pagination.
    Iterates over all namespaces and sets RLS context for each so FORCE ROW LEVEL
    SECURITY does not silently return zero rows.
    """
    pg_refs: set[str] = set()
    ZERO_UUID = UUID(int=0)

    for ns_id in namespaces:
        async with pg_pool.acquire(timeout=10.0) as conn:
            async with conn.transaction():
                await set_namespace_context(conn, ns_id)
                for table in ("memories",):
                    last_seen_id = ZERO_UUID
                    while True:
                        rows = await _fetch_pg_ref_batch(conn, table, last_seen_id, PAGE_SIZE)
                        if not rows:
                            break
                        pg_refs.update(row["payload_ref"] for row in rows)
                        last_seen_id = rows[-1]["id"]

                        if len(rows) < PAGE_SIZE:
                            break  # last page

    return pg_refs


# --- Namespace-aware maintenance helpers ---
# These helpers must set namespace context so RLS policies allow the
# cross-table orphan detection queries to see each namespace's data.


async def _fetch_all_namespaces(pg_pool: asyncpg.Pool) -> list[UUID]:
    """Fetch all namespace UUIDs from the namespaces table."""
    async with pg_pool.acquire(timeout=10.0) as conn:
        rows = await conn.fetch("SELECT id FROM namespaces")
        return [row["id"] for row in rows]


async def _clean_orphaned_cascade(
    pg_pool: asyncpg.Pool,
    namespace_id: UUID,
) -> dict[str, int]:
    """
    Chunked cascade that identifies orphaned memory_ids and deletes them in
    batches of CHUNK_DELETE_SIZE to prevent long-held table locks.

    Every subquery and DELETE includes an explicit ``namespace_id = $1::uuid``
    filter as defense-in-depth.  RLS policies provide the primary isolation;
    the explicit clause guarantees tenant boundaries even if RLS is misconfigured
    or bypassed (e.g. a role with ``row_security = off``).

    Iterates with ``await asyncio.sleep(0.1)`` between chunks to yield the
    event loop so other connections can process during a large GC sweep.

    Returns cumulative counts for ``salience``, ``contradictions``, ``events``
    across all chunks.
    """
    totals: dict[str, int] = {
        "salience": 0,
        "contradictions": 0,
    }

    while True:
        try:
            async with pg_pool.acquire(timeout=10.0) as conn:
                async with conn.transaction():
                    await set_namespace_context(conn, namespace_id)
                    row = await conn.fetchrow(
                        """
                    WITH existing_memories AS (
                        SELECT id FROM memories
                        WHERE namespace_id = $1::uuid
                    ),
                    orphan_memory_ids AS (
                        SELECT memory_id FROM (
                            SELECT ms.memory_id
                            FROM memory_salience ms
                            LEFT JOIN existing_memories em ON ms.memory_id = em.id
                            WHERE em.id IS NULL
                              AND ms.namespace_id = $1::uuid
                            UNION
                            SELECT c.memory_a_id
                            FROM contradictions c
                            LEFT JOIN existing_memories em ON c.memory_a_id = em.id
                            WHERE em.id IS NULL
                              AND c.namespace_id = $1::uuid
                            UNION
                            SELECT c.memory_b_id
                            FROM contradictions c
                            LEFT JOIN existing_memories em ON c.memory_b_id = em.id
                            WHERE em.id IS NULL
                              AND c.namespace_id = $1::uuid
                            UNION
                            SELECT (el.params->>'memory_id')::uuid
                            FROM event_log el
                            LEFT JOIN existing_memories em
                                   ON (el.params->>'memory_id')::uuid = em.id
                            WHERE el.params->>'memory_id' IS NOT NULL
                              AND em.id IS NULL
                              AND el.namespace_id = $1::uuid
                        ) sub
                        LIMIT $2
                    ),
                    deleted_salience AS (
                        DELETE FROM memory_salience
                        WHERE memory_id IN (SELECT memory_id FROM orphan_memory_ids)
                          AND namespace_id = $1::uuid
                        RETURNING 1 AS dummy
                    ),
                    deleted_contradictions AS (
                        DELETE FROM contradictions
                        WHERE (   memory_a_id IN (SELECT memory_id FROM orphan_memory_ids)
                               OR memory_b_id IN (SELECT memory_id FROM orphan_memory_ids))
                          AND namespace_id = $1::uuid
                        RETURNING 1 AS dummy
                    ),
                    SELECT
                        (SELECT count(*) FROM deleted_salience)      AS salience_count,
                        (SELECT count(*) FROM deleted_contradictions) AS contradictions_count
                    """,
                        namespace_id,
                        CHUNK_DELETE_SIZE,
                    )
                    if row is None:
                        break
                    chunk_salience = int(row["salience_count"])
                    chunk_contradictions = int(row["contradictions_count"])
                    if (
                        chunk_salience == 0
                        and chunk_contradictions == 0
                    ):
                        break
                    totals["salience"] += chunk_salience
                    totals["contradictions"] += chunk_contradictions
        except Exception as exc:
            log.error("GC: cascade cleanup failed for ns=%s: %s", namespace_id, exc)
            break

        await asyncio.sleep(0.1)

    return totals


# --- Core GC pass ---


async def _collect_orphans(
    mongo_client: AsyncIOMotorClient,
    pg_pool: asyncpg.Pool,
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cfg.GC_ORPHAN_AGE_SECONDS)
    db = mongo_client.memory_archive

    candidates: list[tuple[str, str]] = []

    for col_name in ("episodes", "code_files"):
        cursor = db[col_name].find(
            {"ingested_at": {"$lt": cutoff}},
            {"_id": 1},
        )
        async for doc in cursor:
            candidates.append((col_name, str(doc["_id"])))

    if not candidates:
        log.info("GC: no candidates — Tri-Stack is clean.")
        return {
            "deleted_docs": 0,
            "deleted_salience": 0,
            "deleted_contradictions": 0,
        }

    log.info(
        "GC: %d candidate(s) older than %ds. Cross-referencing PG (page=%d)...",
        len(candidates),
        cfg.GC_ORPHAN_AGE_SECONDS,
        PAGE_SIZE,
    )

    # Fetch all namespaces once — used by both _fetch_pg_refs (for RLS-scoped
    # reference collection) and the per-namespace cascade loop below.
    namespaces = await _fetch_all_namespaces(pg_pool)

    pg_refs = await _fetch_pg_refs(pg_pool, namespaces)
    orphans = [(col, oid) for col, oid in candidates if oid not in pg_refs]

    if not orphans:
        log.info(
            "GC: all %d candidates referenced in PG — no orphans.", len(candidates)
        )
        return {
            "deleted_docs": 0,
            "deleted_nodes": 0,
            "deleted_salience": 0,
            "deleted_contradictions": 0,
        }

    log.warning("GC: %d orphan(s) detected. Purging...", len(orphans))
    deleted = 0
    for col_name, str_id in orphans:
        try:
            result = await db[col_name].delete_one({"_id": ObjectId(str_id)})
            if result.deleted_count:
                log.info("GC: deleted orphan [%s] %s", col_name, str_id)
                deleted += 1
        except Exception as exc:
            log.error("GC: failed to delete %s from [%s]: %s", str_id, col_name, exc)

    # --- Namespace-aware PG maintenance passes ---
    # These operations hit RLS-protected tables (memory_salience,
    # contradictions).  We iterate over all namespaces and set the
    # session variable so RLS allows the cross-table orphan detection to work.
    #
    # Unified single-pass CTE: one query identifies orphaned memory_ids via
    # LEFT JOIN against memories, then cascades DELETEs to all dependent
    # tables in a single round-trip.  Every subquery and DELETE includes an
    # explicit namespace_id filter (defense-in-depth on top of RLS).

    if not namespaces:
        log.info("GC: no namespaces found — skipping PG maintenance passes.")
        return {
            "deleted_docs": deleted,
            "deleted_salience": 0,
            "deleted_contradictions": 0,
        }

    log.info(
        "GC: running per-namespace cascade maintenance across %d namespace(s).",
        len(namespaces),
    )

    total_salience = 0
    total_contradictions = 0

    for ns_id in namespaces:
        counts = await _clean_orphaned_cascade(pg_pool, ns_id)
        total_salience += counts["salience"]
        total_contradictions += counts["contradictions"]

    if total_salience > 0:
        log.info(
            "GC: purged %d orphaned memory_salience rows across all namespaces.",
            total_salience,
        )
    if total_contradictions > 0:
        log.info(
            "GC: purged %d orphaned contradictions across all namespaces.",
            total_contradictions,
        )

    log.info("GC: pass complete — %d orphan(s) removed.", deleted)
    return {
        "deleted_docs": deleted,
        "deleted_salience": total_salience,
        "deleted_contradictions": total_contradictions,
    }


# --- Long-running loop ---


async def run_gc_loop():
    """
    Background loop. Connects once with retry, then runs a GC pass every hour.
    Designed to be launched as asyncio.create_task() alongside the MCP server.
    """
    log.info(
        "GC starting up (interval=%ds, orphan_age=%ds).",
        cfg.GC_INTERVAL_SECONDS,
        cfg.GC_ORPHAN_AGE_SECONDS,
    )

    try:
        mongo_client, pg_pool = await _connect_with_retry()
    except RuntimeError as exc:
        log.critical(
            "GC failed to connect — background task will exit: %s",
            redact_secrets_in_text(str(exc)),
        )
        return

    try:
        while True:
            if not await _acquire_gc_lock():
                log.info("GC lock held by another instance — skipping this pass.")
                await asyncio.sleep(cfg.GC_INTERVAL_SECONDS)
                continue
            try:
                await _collect_orphans(mongo_client, pg_pool)
            except Exception as exc:
                log.error("GC pass raised unexpected error: %s", exc)
            await asyncio.sleep(cfg.GC_INTERVAL_SECONDS)
    finally:
        mongo_client.close()
        await pg_pool.close()
        log.info("GC connections closed.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [GC] %(levelname)s %(message)s"
    )
    asyncio.run(run_gc_loop())
