"""
Phase 6: Async Background Tasks
Handles heavy processing (AST parsing + Jina vectorization) outside the MCP loop.
Uses RQ (Redis Queue) for reliable task distribution.

Phase 3 hardening: Poison-pill dead-letter-queue (DLQ) for tasks that exhaust
their retry budget.  Each task tracks attempts via Redis; when
``attempt_count > cfg.TASK_MAX_RETRIES``, the payload is persisted to
``dead_letter_queue`` and the job exits cleanly instead of re-raising,
breaking the infinite-retry CPU spin-loop.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from rq import get_current_job

from trimcp import embeddings as _embeddings
from trimcp.ast_parser import parse_file
from trimcp.config import cfg
from trimcp.dead_letter_queue import _clear_attempt, _track_attempt, store_dead_letter
from trimcp.orchestrator import TriStackEngine

log = logging.getLogger("tri-stack-tasks")


def run_async(coro):
    """Helper to run async code in sync RQ worker context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_job_id() -> str:
    """Return the current RQ job ID, or ``"unknown"`` if not in worker context."""
    try:
        job = get_current_job()
        return job.id if job else "unknown"
    except Exception:
        return "unknown"


def _get_redis() -> Redis:
    """Return a Redis client for attempt-tracking counters."""
    return Redis.from_url(cfg.REDIS_URL)


def _check_poison_pill(
    task_name: str,
    job_id: str,
    redis_client: Redis,
    exc: BaseException,
) -> tuple[bool, int, str]:
    """Increment the attempt counter and decide whether to route to DLQ.

    Returns ``(poisoned: bool, attempt_count: int, error_message: str)``.

    - ``poisoned=True``: retries exhausted — caller should persist to DLQ
      and exit cleanly (do NOT re-raise).
    - ``poisoned=False``: still within retry budget — caller should re-raise
      so RQ re-enqueues.
    """
    attempt = _track_attempt(redis_client, job_id)
    max_retries = cfg.TASK_MAX_RETRIES

    if max_retries <= 0:
        # DLQ disabled — always re-raise
        return False, attempt, ""

    if attempt <= max_retries:
        log.warning(
            "[Worker] %s (job %s) attempt %d/%d — retrying. Error: %s",
            task_name,
            job_id,
            attempt,
            max_retries,
            str(exc)[:256],
        )
        return False, attempt, ""

    # Exhausted — route to DLQ
    error_msg = f"{type(exc).__name__}: {exc!s}"[:1024]

    log.critical(
        "[Worker] %s (job %s) exhausted %d retries — routing to dead_letter_queue.",
        task_name,
        job_id,
        attempt,
    )
    return True, attempt, error_msg


async def _store_dlq_async(
    *,
    task_name: str,
    job_id: str,
    kwargs: dict[str, Any],
    error_msg: str,
    attempt: int,
    pg_pool: Any | None = None,
) -> None:
    """Persist a poisoned task to the dead_letter_queue table (async).

    If *pg_pool* is provided (reuse an existing pool), it is used directly.
    Otherwise a lightweight temporary pool is created and torn down.
    """
    if pg_pool is not None:
        await store_dead_letter(pg_pool, task_name, job_id, kwargs, error_msg, attempt)
        return

    # No pool provided — create a short-lived one
    import asyncpg

    pool = await asyncpg.create_pool(cfg.PG_DSN, min_size=1, max_size=2)
    try:
        await store_dead_letter(pool, task_name, job_id, kwargs, error_msg, attempt)
    finally:
        await pool.close()


def process_code_indexing(
    filepath: str,
    raw_code: str,
    language: str,
    user_id: str | None = None,
    namespace_id: str | None = None,
):
    """
    Worker task: Performs the actual heavy lifting of indexing.
    user_id=None: shared corpus (enterprise default). Otherwise private to that user.
    namespace_id: multi-tenant isolation scope.

    Phase 3: Attempts are tracked via Redis.  After ``cfg.TASK_MAX_RETRIES``
    failures the payload is routed to ``dead_letter_queue`` and the job
    exits cleanly (no re-raise → no re-enqueue).
    """
    job_id = _get_job_id()
    redis_client = _get_redis()
    log.info(
        "[Worker] Starting indexing for %s (namespace=%s, job=%s)",
        filepath,
        namespace_id,
        job_id,
    )

    engine = TriStackEngine()

    async def _index():
        await engine.connect()
        inserted_mongo_id = None
        db = engine.mongo_client.memory_archive
        collection = db.code_files
        try:
            file_hash = hashlib.md5(raw_code.encode()).hexdigest()

            # STEP 1: Episodic Commit (MongoDB)
            doc: dict = {
                "filepath": filepath,
                "language": language,
                "file_hash": file_hash,
                "raw_code": raw_code,
                "ingested_at": datetime.now(timezone.utc),
            }
            if user_id:
                doc["user_id"] = user_id
            if namespace_id:
                doc["namespace_id"] = namespace_id
            inserted_result = await collection.insert_one(doc)
            inserted_mongo_id = str(inserted_result.inserted_id)

            # STEP 2: Batch-embed all AST chunks
            chunks = list(parse_file(raw_code, language))
            texts = [f"{c.name}\n{c.code_string}" for c in chunks]
            vectors = await _embeddings.embed_batch(texts)

            # Use scoped session for RLS if namespace_id is provided
            async with (
                engine.scoped_session(namespace_id)
                if namespace_id
                else engine.pg_pool.acquire()
            ) as conn:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE memories SET valid_to = now() "
                        "WHERE filepath = $1 AND (user_id IS NOT DISTINCT FROM $2) AND valid_to IS NULL",
                        filepath,
                        user_id,
                    )
                    from uuid import UUID

                    ns_uuid = UUID(namespace_id) if namespace_id else None
                    metadata = {}
                    if (
                        getattr(_embeddings, "degraded_embedding_flag", None)
                        and _embeddings.degraded_embedding_flag.get()
                    ):
                        metadata["degraded_embedding"] = True

                    for chunk, vector in zip(chunks, vectors):
                        await conn.execute(
                            """
                            INSERT INTO memories
                                (filepath, language, node_type, name, start_line, end_line,
                                 file_hash, embedding, content_fts, payload_ref, user_id, namespace_id, memory_type, metadata)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, 
                                    to_tsvector('english', $9 || ' ' || $10), $11, $12, $13, 'code_chunk', $14)
                            """,
                            filepath,
                            language,
                            chunk.node_type,
                            chunk.name,
                            chunk.start_line,
                            chunk.end_line,
                            file_hash,
                            json.dumps(vector),
                            chunk.name,
                            chunk.code_string,
                            inserted_mongo_id,
                            user_id,
                            ns_uuid,
                            json.dumps(metadata),
                        )

            # STEP 3: Cache hash in Redis
            scope_key = f"private:{user_id}" if user_id else "shared"
            namespace_prefix = f"{namespace_id}:" if namespace_id else ""
            await engine.redis_client.setex(
                f"hash:{namespace_prefix}{scope_key}:{filepath}", 3600, file_hash
            )
            log.info("[Worker] Finished indexing %s (%d chunks)", filepath, len(chunks))

            # Success — clear the attempt counter
            _clear_attempt(redis_client, job_id)
            return {"status": "success", "chunks": len(chunks)}

        except Exception as exc:
            log.exception("[Worker] Indexing failed for %s", filepath)
            if inserted_mongo_id:
                log.warning(
                    "[ROLLBACK] Removing orphaned Mongo doc %s", inserted_mongo_id
                )
                try:
                    await collection.delete_one({"_id": inserted_result.inserted_id})
                except Exception as mongo_exc:
                    log.error("[ROLLBACK] Mongo cleanup failed: %s", mongo_exc)

            # Phase 3: Poison-pill check — route to DLQ if retries exhausted
            poisoned, attempt_count, error_msg = _check_poison_pill(
                task_name="process_code_indexing",
                job_id=job_id,
                redis_client=redis_client,
                exc=exc,
            )
            if poisoned:
                return {
                    "status": "dead_lettered",
                    "job_id": job_id,
                    "_dlq_kwargs": {
                        "filepath": filepath,
                        "language": language,
                        "user_id": user_id,
                        "namespace_id": namespace_id,
                    },
                    "_dlq_error_msg": error_msg,
                    "_dlq_attempt": attempt_count,
                }
            raise  # retry — let RQ re-enqueue
        finally:
            await engine.disconnect()

    result = run_async(_index())

    # Phase 3: If the inner coroutine signalled dead-letter, persist the DLQ record
    # in a SEPARATE event loop to avoid nesting (run_async creates a new loop).
    if isinstance(result, dict) and result.get("status") == "dead_lettered":
        try:
            run_async(
                _store_dlq_async(
                    task_name="process_code_indexing",
                    job_id=result["job_id"],
                    kwargs=result["_dlq_kwargs"],
                    error_msg=result["_dlq_error_msg"],
                    attempt=result["_dlq_attempt"],
                    pg_pool=None,  # engine already disconnected; use short-lived pool
                )
            )
        except Exception as dlq_exc:
            log.critical(
                "[DLQ] CRITICAL — Could not persist DLQ entry for process_code_indexing (job %s): %s",
                result.get("job_id"),
                dlq_exc,
            )
        # Clean up private keys before returning to caller
        return {"status": "dead_lettered", "job_id": result["job_id"]}

    return result


def process_bridge_event(provider: str, payload: dict) -> dict:
    """
    RQ worker: process a validated webhook payload for a document bridge.

    ``provider``: sharepoint | gdrive | dropbox (see §10.3 / Appendix H).

    Phase 3: Attempts are tracked via Redis.  After ``cfg.TASK_MAX_RETRIES``
    failures the payload is routed to ``dead_letter_queue`` and the job
    exits cleanly.
    """
    from trimcp.bridges import dispatch_bridge_event

    job_id = _get_job_id()
    redis_client = _get_redis()
    log.info(
        "[Bridge worker] provider=%s keys=%s job=%s",
        provider,
        list(payload.keys()),
        job_id,
    )

    try:
        result = dispatch_bridge_event(provider, payload)
        # Success — clear attempt counter
        _clear_attempt(redis_client, job_id)
        return result
    except ValueError as e:
        log.error("[Bridge worker] %s", e)
        return {"status": "error", "error": str(e)}
    except Exception as exc:
        log.exception("[Bridge worker] Unhandled failure for provider=%s", provider)
        poisoned, attempt_count, error_msg = _check_poison_pill(
            task_name="process_bridge_event",
            job_id=job_id,
            redis_client=redis_client,
            exc=exc,
        )
        if poisoned:
            try:
                run_async(
                    _store_dlq_async(
                        task_name="process_bridge_event",
                        job_id=job_id,
                        kwargs={"provider": provider, "payload": payload},
                        error_msg=error_msg,
                        attempt=attempt_count,
                        pg_pool=None,
                    )
                )
            except Exception as dlq_exc:
                log.critical(
                    "[DLQ] CRITICAL — Could not persist DLQ entry for process_bridge_event (job %s): %s",
                    job_id,
                    dlq_exc,
                )
            return {"status": "dead_lettered", "job_id": job_id}
        raise  # retry — let RQ re-enqueue
