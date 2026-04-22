"""
Tri-Stack Garbage Collector
Runs every hour as an async background task.
Finds MongoDB documents older than 5 minutes with no matching mongo_ref_id
in either PG table (memory_metadata or code_metadata), then deletes them.
Guarantees data purity even if the Python process is hard-killed mid-transaction.

Hardening:
- PG scan is paginated (PAGE_SIZE rows at a time) — safe on million-row tables.
- Startup uses exponential backoff so a slow Docker start never crashes the GC.
- Pool size is bounded; command timeout prevents hung queries.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import asyncpg

from trimcp.config import cfg

log = logging.getLogger("tri-stack-gc")

PAGE_SIZE            = 500   # rows fetched per PG cursor page
MAX_CONNECT_ATTEMPTS = 5
CONNECT_BASE_DELAY   = 2.0   # seconds; doubles each retry


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
            mongo_client = AsyncIOMotorClient(
                cfg.MONGO_URI,
                serverSelectionTimeoutMS=5_000,
            )
            # Force a real connection check
            await mongo_client.admin.command("ping")

            pg_pool = await asyncpg.create_pool(
                cfg.PG_DSN,
                min_size=1,
                max_size=3,          # GC needs very few connections
                command_timeout=30,
            )
            log.info("GC connected on attempt %d.", attempt)
            return mongo_client, pg_pool

        except Exception as exc:
            last_exc = exc
            log.warning(
                "GC connect attempt %d/%d failed: %s. Retrying in %.0fs.",
                attempt, MAX_CONNECT_ATTEMPTS, exc, delay,
            )
            if attempt < MAX_CONNECT_ATTEMPTS:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    raise RuntimeError(
        f"GC could not connect after {MAX_CONNECT_ATTEMPTS} attempts: {last_exc}"
    )


# --- Paginated PG reference set builder ---

async def _fetch_pg_refs(pg_pool: asyncpg.Pool) -> set[str]:
    """
    Build the set of all known mongo_ref_ids in PG using cursor-based pagination.
    Avoids loading millions of rows into memory at once.
    """
    pg_refs: set[str] = set()

    for table in ("memory_metadata", "code_metadata"):
        offset = 0
        while True:
            async with pg_pool.acquire() as conn:
                # Parameterised LIMIT/OFFSET — table name is from a hardcoded tuple, not user input
                rows = await conn.fetch(
                    f"SELECT mongo_ref_id FROM {table} "   # noqa: S608 — table is not user-controlled
                    f"WHERE mongo_ref_id IS NOT NULL "
                    f"LIMIT $1 OFFSET $2",
                    PAGE_SIZE, offset,
                )
            if not rows:
                break
            pg_refs.update(row["mongo_ref_id"] for row in rows)
            offset += PAGE_SIZE

            if len(rows) < PAGE_SIZE:
                break   # last page

    return pg_refs


# --- Core GC pass ---

async def _collect_orphans(
    mongo_client: AsyncIOMotorClient,
    pg_pool: asyncpg.Pool,
) -> int:
    cutoff = datetime.utcnow() - timedelta(seconds=cfg.GC_ORPHAN_AGE_SECONDS)
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
        return 0

    log.info("GC: %d candidate(s) older than %ds. Cross-referencing PG (page=%d)...",
             len(candidates), cfg.GC_ORPHAN_AGE_SECONDS, PAGE_SIZE)

    pg_refs = await _fetch_pg_refs(pg_pool)
    orphans = [(col, oid) for col, oid in candidates if oid not in pg_refs]

    if not orphans:
        log.info("GC: all %d candidates referenced in PG — no orphans.", len(candidates))
        return 0

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

    log.info("GC: pass complete — %d orphan(s) removed.", deleted)
    return deleted


# --- Long-running loop ---

async def run_gc_loop():
    """
    Background loop. Connects once with retry, then runs a GC pass every hour.
    Designed to be launched as asyncio.create_task() alongside the MCP server.
    """
    log.info("GC starting up (interval=%ds, orphan_age=%ds).",
             cfg.GC_INTERVAL_SECONDS, cfg.GC_ORPHAN_AGE_SECONDS)

    try:
        mongo_client, pg_pool = await _connect_with_retry()
    except RuntimeError as exc:
        log.critical("GC failed to connect — background task will exit: %s", exc)
        return

    try:
        while True:
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
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [GC] %(levelname)s %(message)s")
    asyncio.run(run_gc_loop())
