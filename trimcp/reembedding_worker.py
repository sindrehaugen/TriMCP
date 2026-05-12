"""
Phase 2.1 — Re-embedding Worker
=================================
Finds ``memories`` rows whose ``embedding_model_id`` differs from the current
embedding model version (or is NULL) and re-embeds them in bounded,
rate-limited batches.  Optionally re-embeds ``kg_nodes`` (which have no model
version column).

Design
------
Model versioning
    The running model is identified by a deterministic UUIDv5 derived from
    ``trimcp.embeddings.MODEL_ID``.  Each updated memory row gets that UUID
    stamped into ``embedding_model_id``, so the next run can skip it cheaply
    via a single index scan.

Keyset pagination
    Memories are fetched via ``(created_at ASC, id ASC)`` cursor so the query
    planner can use the partitioned index and the cursor stays stable even if
    new rows are inserted during a run.

Rate limiting
    A configurable ``REEMBED_BATCHES_PER_MINUTE`` cap (default: 20 → one batch
    every 3 s) is implemented as a post-batch ``asyncio.sleep``.  A single
    ``asyncio.Semaphore`` guards the embedding call to prevent concurrent embed
    fan-out.

Text source
    - ``episodic`` memories  → Mongo ``episodes.raw_data`` (the heavy payload;
      best available approximation of the original summary text).
    - ``code_chunk`` memories → Mongo ``code_files.raw_code`` (truncated).
    - Fallback                → ``name + filepath`` columns on the memories row.
    - ``kg_nodes``            → ``label`` column (no Mongo lookup needed).

Resumability
    Each run is recorded in the ``reembedding_runs`` audit table (created by the
    worker on first run — no schema.sql changes required).  The cursor position
    is checkpointed after every batch.  If the process is killed mid-run, the
    next invocation continues from where the cursor left off because rows already
    updated are excluded by the ``embedding_model_id != current`` WHERE clause.

Entry points
------------
``ReembeddingWorker.run_once(pool, mongo_client)``
    One full sweep; callable from APScheduler (see ``trimcp/cron.py``).
``async_main()``
    Connects, runs one sweep, disconnects — suitable for ``python -m trimcp.reembedding_worker``.
``main()``
    Sync wrapper for ``__main__``.

Env vars
--------
REEMBED_BATCH_SIZE            Rows per embed batch (default: 32).
REEMBED_BATCHES_PER_MINUTE    Rate cap (default: 20 → 3 s sleep between batches).
REEMBED_MAX_ROWS_PER_RUN      0 = unlimited; positive = stop after N memories (default: 0).
REEMBED_INCLUDE_KG_NODES      "true" to also refresh kg_nodes embeddings (default: false).
REEMBED_MAX_TEXT_CHARS        Clip text before embedding (default: 4096).
REEMBED_CRON_INTERVAL_MINUTES APScheduler interval when running via cron (default: 60).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

import asyncpg

from trimcp import embeddings as _embeddings
from trimcp.embeddings import MODEL_ID, VECTOR_DIM  # noqa: F401

log = logging.getLogger("trimcp.reembedding")

# --------------------------------------------------------------------------- #
# Model version — deterministic UUIDv5 keyed on the embedding model name.
# --------------------------------------------------------------------------- #

_UUID_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def current_model_uuid() -> uuid.UUID:
    """Return a stable UUID that uniquely identifies the active embedding model."""
    return uuid.uuid5(_UUID_NS, MODEL_ID)


# --------------------------------------------------------------------------- #
# Env-driven config (isolated from _Config to avoid touching the shared class)
# --------------------------------------------------------------------------- #


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "false").lower() in ("1", "true", "yes")


BATCH_SIZE: int = _env_int("REEMBED_BATCH_SIZE", 32)
BATCHES_PER_MINUTE: int = _env_int("REEMBED_BATCHES_PER_MINUTE", 20)
MAX_ROWS_PER_RUN: int = _env_int("REEMBED_MAX_ROWS_PER_RUN", 0)  # 0 = unlimited
INCLUDE_KG_NODES: bool = _env_bool("REEMBED_INCLUDE_KG_NODES", False)
MAX_TEXT_CHARS: int = _env_int("REEMBED_MAX_TEXT_CHARS", 4096)
CRON_INTERVAL_MINUTES: int = _env_int("REEMBED_CRON_INTERVAL_MINUTES", 60)


# --------------------------------------------------------------------------- #
# Audit table DDL — created by the worker on first run (idempotent).
# --------------------------------------------------------------------------- #

_DDL_REEMBEDDING_RUNS = """
CREATE TABLE IF NOT EXISTS reembedding_runs (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version     UUID        NOT NULL,
    model_name        TEXT        NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ,
    status            TEXT        NOT NULL DEFAULT 'running'
                                  CHECK (status IN ('running','completed','failed')),
    memories_done     BIGINT      NOT NULL DEFAULT 0,
    kg_nodes_done     BIGINT      NOT NULL DEFAULT 0,
    error_message     TEXT,
    -- Keyset cursor checkpointed after each batch for resumability.
    cursor_created_at TIMESTAMPTZ,
    cursor_id         UUID
);
"""


async def _ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(_DDL_REEMBEDDING_RUNS)


# --------------------------------------------------------------------------- #
# Pagination helpers — pure SQL, raw asyncpg
# --------------------------------------------------------------------------- #


async def _fetch_memories_batch(
    conn: asyncpg.Connection,
    model_uuid: uuid.UUID,
    batch_size: int,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
) -> list[asyncpg.Record]:
    """
    Keyset-paginated SELECT of memories that need re-embedding.

    Includes rows where:
    - ``embedding IS NOT NULL``  (skip blanks that were never embedded)
    - ``embedding_model_id``  is NULL or does not match the current model UUID
    """
    model_str = str(model_uuid)

    if cursor_created_at is None:
        return await conn.fetch(
            """
            SELECT id, created_at, memory_type, payload_ref, name, filepath
            FROM   memories
            WHERE  embedding IS NOT NULL
              AND  (embedding_model_id IS NULL
                    OR embedding_model_id::text <> $1)
            ORDER  BY created_at ASC, id ASC
            LIMIT  $2
            FOR UPDATE SKIP LOCKED
            """,
            model_str,
            batch_size,
        )

    # Composite keyset: advance past (created_at, id) of the last processed row.
    return await conn.fetch(
        """
        SELECT id, created_at, memory_type, payload_ref, name, filepath
        FROM   memories
        WHERE  embedding IS NOT NULL
          AND  (embedding_model_id IS NULL
                OR embedding_model_id::text <> $1)
          AND  (created_at, id) > ($2, $3)
        ORDER  BY created_at ASC, id ASC
        LIMIT  $4
        FOR UPDATE SKIP LOCKED
        """,
        model_str,
        cursor_created_at,
        cursor_id,
        batch_size,
    )


async def _fetch_kg_nodes_batch(
    conn: asyncpg.Connection,
    model_uuid: uuid.UUID,
    batch_size: int,
    cursor_id: uuid.UUID | None,
) -> list[asyncpg.Record]:
    """Ordered by id ASC; works across HASH partitions."""
    model_str = str(model_uuid)
    if cursor_id is None:
        return await conn.fetch(
            """
            SELECT id, label FROM kg_nodes
            WHERE embedding IS NOT NULL
              AND (embedding_model_id IS NULL OR embedding_model_id::text <> $1)
            ORDER BY id ASC LIMIT $2
            FOR UPDATE SKIP LOCKED
            """,
            model_str,
            batch_size,
        )
    return await conn.fetch(
        """
        SELECT id, label FROM kg_nodes
        WHERE embedding IS NOT NULL
          AND (embedding_model_id IS NULL OR embedding_model_id::text <> $1)
          AND id > $2
        ORDER BY id ASC LIMIT $3
        FOR UPDATE SKIP LOCKED
        """,
        model_str,
        cursor_id,
        batch_size,
    )


# --------------------------------------------------------------------------- #
# Mongo text resolution — batch by collection
# --------------------------------------------------------------------------- #


async def _resolve_texts_from_mongo(
    mongo_client: Any,
    rows: list[asyncpg.Record],
    max_text_chars: int,
) -> dict[str, str]:
    """
    Returns ``{payload_ref: text_to_embed}`` for rows that have a valid MongoDB
    payload_ref.

    Episodic memories → ``episodes.raw_data``.
    Code chunks       → ``code_files.raw_code`` (truncated to max_text_chars).
    """
    from bson import ObjectId  # defer so tests that mock Mongo don't need bson

    episodic_refs: list[str] = []
    code_refs: list[str] = []

    for row in rows:
        ref = row.get("payload_ref") or ""
        if len(ref) != 24:  # MongoDB ObjectId hex is always 24 chars
            continue
        if row.get("memory_type") == "code_chunk":
            code_refs.append(ref)
        else:
            episodic_refs.append(ref)

    result: dict[str, str] = {}
    db = mongo_client.memory_archive

    if episodic_refs:
        try:
            oids = [ObjectId(r) for r in episodic_refs]
            async for doc in db.episodes.find({"_id": {"$in": oids}}, {"raw_data": 1}):
                ref = str(doc["_id"])
                result[ref] = str(doc.get("raw_data", ""))[:max_text_chars]
        except Exception as exc:
            log.warning("Re-embed: Mongo episodic fetch error: %s", exc)

    if code_refs:
        try:
            oids = [ObjectId(r) for r in code_refs]
            async for doc in db.code_files.find(
                {"_id": {"$in": oids}}, {"raw_code": 1}
            ):
                ref = str(doc["_id"])
                result[ref] = str(doc.get("raw_code", ""))[:max_text_chars]
        except Exception as exc:
            log.warning("Re-embed: Mongo code fetch error: %s", exc)

    return result


def _fallback_text(row: asyncpg.Record, max_chars: int) -> str:
    """Best-effort text from the memories row itself when Mongo is unavailable."""
    parts = [p for p in (row.get("name"), row.get("filepath")) if p]
    return (" ".join(parts))[:max_chars]


# --------------------------------------------------------------------------- #
# Batch update helpers
# --------------------------------------------------------------------------- #


async def _update_memories_batch(
    conn: asyncpg.Connection,
    batch: list[tuple[uuid.UUID, datetime, list[float]]],
    model_uuid: uuid.UUID,
) -> None:
    """
    Stamps updated embedding + embedding_model_id for a batch of memories.
    Includes ``created_at`` in the WHERE clause so Postgres can prune to the
    correct range partition without a full-table scan.
    """
    model_str = str(model_uuid)
    async with conn.transaction():
        await conn.executemany(
            """
            UPDATE memories
            SET    embedding          = $1::vector,
                   embedding_model_id = $2::uuid
            WHERE  id         = $3
              AND  created_at = $4
            """,
            [
                (json.dumps(vec), model_str, mem_id, created_at)
                for mem_id, created_at, vec in batch
            ],
        )


async def _update_kg_nodes_batch(
    conn: asyncpg.Connection,
    batch: list[tuple[uuid.UUID, list[float]]],
    model_uuid: uuid.UUID,
) -> None:
    model_str = str(model_uuid)
    async with conn.transaction():
        await conn.executemany(
            "UPDATE kg_nodes SET embedding = $1::vector, embedding_model_id = $2::uuid, updated_at = now() WHERE id = $3",
            [(json.dumps(vec), model_str, node_id) for node_id, vec in batch],
        )


# --------------------------------------------------------------------------- #
# Progress checkpoint
# --------------------------------------------------------------------------- #


async def _checkpoint(
    conn: asyncpg.Connection,
    run_id: uuid.UUID,
    memories_done: int,
    kg_nodes_done: int,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
) -> None:
    await conn.execute(
        """
        UPDATE reembedding_runs
        SET    memories_done     = $1,
               kg_nodes_done    = $2,
               cursor_created_at = $3,
               cursor_id         = $4
        WHERE  id = $5
        """,
        memories_done,
        kg_nodes_done,
        cursor_created_at,
        cursor_id,
        run_id,
    )


# --------------------------------------------------------------------------- #
# Worker class
# --------------------------------------------------------------------------- #


class ReembeddingWorker:
    """
    Stateless background worker — instantiate once per process; call
    ``run_once`` as many times as needed (APScheduler or manual).
    """

    def __init__(
        self,
        *,
        batch_size: int = BATCH_SIZE,
        batches_per_minute: int = BATCHES_PER_MINUTE,
        max_rows_per_run: int = MAX_ROWS_PER_RUN,
        include_kg_nodes: bool = INCLUDE_KG_NODES,
        max_text_chars: int = MAX_TEXT_CHARS,
    ) -> None:
        self.batch_size = max(1, batch_size)
        # Inter-batch sleep enforces the token-rate cap.
        self._sleep = 60.0 / max(1, batches_per_minute)
        self.max_rows_per_run = max_rows_per_run  # 0 = unlimited
        self.include_kg_nodes = include_kg_nodes
        self.max_text_chars = max_text_chars

    # ---------------------------------------------------------------------- #
    # Internal helpers
    # ---------------------------------------------------------------------- #

    async def _embed(self, pool: asyncpg.Pool, texts: list[str]) -> list[list[float]]:
        # Use Postgres advisory lock to prevent concurrent embedding fan-out across workers
        lock_key = 0x7265656D626564  # 'reembed' in hex
        async with pool.acquire(timeout=10.0) as conn:
            await conn.execute("SELECT pg_advisory_lock($1)", lock_key)
            try:
                return await _embeddings.embed_batch(texts)
            finally:
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_key)

    async def _create_run(
        self,
        pool: asyncpg.Pool,
        model_uuid: uuid.UUID,
    ) -> uuid.UUID:
        async with pool.acquire(timeout=10.0) as conn:
            await _ensure_schema(conn)
            run_id: uuid.UUID = await conn.fetchval(
                """
                INSERT INTO reembedding_runs (model_version, model_name)
                VALUES ($1, $2)
                RETURNING id
                """,
                model_uuid,
                MODEL_ID,
            )
        return run_id

    async def _close_run(
        self,
        pool: asyncpg.Pool,
        run_id: uuid.UUID,
        status: str,
        memories_done: int,
        kg_nodes_done: int,
        error: str | None = None,
    ) -> None:
        async with pool.acquire(timeout=10.0) as conn:
            await conn.execute(
                """
                UPDATE reembedding_runs
                SET    status        = $1,
                       completed_at  = now(),
                       memories_done = $2,
                       kg_nodes_done = $3,
                       error_message = $4
                WHERE  id = $5
                """,
                status,
                memories_done,
                kg_nodes_done,
                error,
                run_id,
            )

    # ---------------------------------------------------------------------- #
    # Phase A — memories
    # ---------------------------------------------------------------------- #

    async def _run_memories_phase(
        self,
        pool: asyncpg.Pool,
        mongo_client: Any,
        model_uuid: uuid.UUID,
        run_id: uuid.UUID,
    ) -> int:
        """Returns total memories re-embedded during this phase."""
        cursor_created_at: datetime | None = None
        cursor_id: uuid.UUID | None = None
        memories_done = 0

        while True:
            # Stop early if the operator set a per-run ceiling.
            if self.max_rows_per_run and memories_done >= self.max_rows_per_run:
                log.info(
                    "Re-embed: max_rows_per_run=%d reached, stopping memories phase.",
                    self.max_rows_per_run,
                )
                break

            async with pool.acquire(timeout=10.0) as conn:
                async with conn.transaction():
                    rows = await _fetch_memories_batch(
                        conn,
                        model_uuid,
                        self.batch_size,
                        cursor_created_at,
                        cursor_id,
                    )

            if not rows:
                log.debug("Re-embed: no more stale memories found.")
                break

            # Resolve text for each row —————————————————————————————————————
            mongo_texts: dict[str, str] = {}
            if mongo_client is not None:
                mongo_texts = await _resolve_texts_from_mongo(
                    mongo_client, rows, self.max_text_chars
                )

            texts: list[str] = []
            selected: list[tuple[uuid.UUID, datetime]] = []

            for row in rows:
                ref = row.get("payload_ref") or ""
                text = mongo_texts.get(ref) or _fallback_text(row, self.max_text_chars)
                if not text:
                    log.debug(
                        "Re-embed: skipping memory %s — no text available.", row["id"]
                    )
                    continue
                texts.append(text)
                selected.append((row["id"], row["created_at"]))

            if texts:
                vectors = await self._embed(pool, texts)

                update_batch = [
                    (mem_id, created_at, vec)
                    for (mem_id, created_at), vec in zip(selected, vectors)
                ]

                async with pool.acquire(timeout=10.0) as conn:
                    await _update_memories_batch(conn, update_batch, model_uuid)

                memories_done += len(update_batch)

            # Advance cursor ————————————————————————————————————————————————
            last = rows[-1]
            cursor_created_at = last["created_at"]
            cursor_id = last["id"]

            async with pool.acquire(timeout=10.0) as conn:
                await _checkpoint(
                    conn,
                    run_id,
                    memories_done,
                    0,
                    cursor_created_at,
                    cursor_id,
                )

            log.info(
                "Re-embed: %d memories updated this run (batch=%d).",
                memories_done,
                len(texts),
            )

            # Rate-limit: honour REEMBED_BATCHES_PER_MINUTE ————————————————
            await asyncio.sleep(self._sleep)

        return memories_done

    # ---------------------------------------------------------------------- #
    # Phase B — kg_nodes (optional)
    # ---------------------------------------------------------------------- #

    async def _run_kg_nodes_phase(
        self,
        pool: asyncpg.Pool,
        run_id: uuid.UUID,
        memories_done: int,
        model_uuid: uuid.UUID,
    ) -> int:
        kg_cursor_id: uuid.UUID | None = None
        kg_nodes_done = 0

        while True:
            async with pool.acquire(timeout=10.0) as conn:
                async with conn.transaction():
                    rows = await _fetch_kg_nodes_batch(
                        conn, model_uuid, self.batch_size, kg_cursor_id
                    )

            if not rows:
                break

            texts = [row["label"][: self.max_text_chars] for row in rows]
            vectors = await self._embed(pool, texts)

            batch = [(row["id"], vec) for row, vec in zip(rows, vectors)]

            async with pool.acquire(timeout=10.0) as conn:
                await _update_kg_nodes_batch(conn, batch, model_uuid)

            kg_nodes_done += len(batch)
            kg_cursor_id = rows[-1]["id"]

            async with pool.acquire(timeout=10.0) as conn:
                await _checkpoint(
                    conn,
                    run_id,
                    memories_done,
                    kg_nodes_done,
                    None,
                    None,
                )

            log.info("Re-embed: %d kg_nodes updated this run.", kg_nodes_done)
            await asyncio.sleep(self._sleep)

        return kg_nodes_done

    # ---------------------------------------------------------------------- #
    # Public entry point
    # ---------------------------------------------------------------------- #

    async def run_once(
        self,
        pool: asyncpg.Pool,
        mongo_client: Any = None,
    ) -> dict[str, Any]:
        """
        Run one full re-embedding sweep.

        Parameters
        ----------
        pool:
            asyncpg connection pool (already connected).
        mongo_client:
            Motor ``AsyncIOMotorClient`` (or compatible).  Pass ``None`` in
            tests; the worker falls back to ``name + filepath`` text.

        Returns
        -------
        dict with keys: run_id, status, memories_done, kg_nodes_done.
        """
        model_uuid = current_model_uuid()
        run_id = await self._create_run(pool, model_uuid)

        log.info(
            "Re-embedding run %s started | model=%s | batch=%d | rate=%d/min",
            run_id,
            MODEL_ID,
            self.batch_size,
            int(60.0 / self._sleep),
        )

        memories_done = 0
        kg_nodes_done = 0

        try:
            memories_done = await self._run_memories_phase(
                pool, mongo_client, model_uuid, run_id
            )

            if self.include_kg_nodes:
                kg_nodes_done = await self._run_kg_nodes_phase(
                    pool, run_id, memories_done, model_uuid
                )

            await self._close_run(
                pool, run_id, "completed", memories_done, kg_nodes_done
            )
            log.info(
                "Re-embedding run %s completed | memories=%d kg_nodes=%d",
                run_id,
                memories_done,
                kg_nodes_done,
            )
            return {
                "run_id": str(run_id),
                "status": "completed",
                "memories_done": memories_done,
                "kg_nodes_done": kg_nodes_done,
            }

        except Exception as exc:
            await self._close_run(
                pool,
                run_id,
                "failed",
                memories_done,
                kg_nodes_done,
                error=str(exc)[:2048],
            )
            log.exception("Re-embedding run %s failed", run_id)
            raise


# --------------------------------------------------------------------------- #
# Standalone entry point (``python -m trimcp.reembedding_worker``)
# --------------------------------------------------------------------------- #


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [trimcp.reembedding] %(levelname)s %(message)s",
    )
    from trimcp.config import cfg

    cfg.validate()

    pool = await asyncpg.create_pool(
        cfg.PG_DSN,
        min_size=1,
        max_size=4,
        command_timeout=120,
    )

    mongo_client: Any = None
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        mongo_client = AsyncIOMotorClient(cfg.MONGO_URI, serverSelectionTimeoutMS=5_000)
    except ImportError:
        log.warning("motor not available — re-embedding will use fallback text only.")

    worker = ReembeddingWorker()
    try:
        stats = await worker.run_once(pool, mongo_client)
        log.info("Done: %s", stats)
    finally:
        await pool.close()
        if mongo_client:
            mongo_client.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
