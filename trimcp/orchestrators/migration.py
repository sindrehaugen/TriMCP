"""
MigrationOrchestrator — domain orchestrator for embedding migration lifecycle and code indexing.

Extracted from TriStackEngine (Prompt 54, Step 5).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

import asyncpg

log = logging.getLogger("tri-stack-orchestrator.migration")


class MigrationOrchestrator:
    """Domain orchestrator for embedding migrations and code indexing."""

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        redis_client,
        redis_sync_client,
    ):
        self.pg_pool = pg_pool
        self.redis_client = redis_client
        self.redis_sync_client = redis_sync_client

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_uuid(self, val: str | UUID | None) -> UUID | None:
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        return UUID(str(val))

    def _validate_path(self, filepath: str) -> None:
        """Validate filepath is within allowed directory using pathlib."""
        try:
            resolved = Path(filepath).resolve()
        except Exception:
            raise ValueError(f"Invalid filepath: {filepath}")
        cwd = Path.cwd().resolve()
        if not str(resolved).startswith(str(cwd)):
            raise ValueError(f"Path traversal detected: {filepath}")

    def _redis_cache_key(
        self, namespace_id: str | UUID | None, user_id: str | None, filepath: str
    ) -> str:
        """Build a deterministic Redis cache key for code indexing."""
        ns = str(namespace_id) if namespace_id else "global"
        user = user_id or "shared"
        safe_path = filepath.replace("\\", "/").rstrip("/")
        return f"code_index:{ns}:{user}:{safe_path}"

    # ------------------------------------------------------------------
    # Code indexing & RQ job status
    # ------------------------------------------------------------------

    async def index_code_file(self, payload, *, priority: int = 0) -> dict:
        """[Phase 3.2] Offloads indexing to a background worker via RQ.

        *priority* routes the job to a queue lane (§5.4):
          - ``> 0`` → ``high_priority`` (user-facing API extractions)
          - ``0``  → ``batch_processing`` (bulk / webhook indexing)
        """
        self._validate_path(payload.filepath)

        import hashlib

        file_hash = hashlib.md5(payload.raw_code.encode()).hexdigest()

        scope_user = payload.user_id if payload.private else None
        cache_key = self._redis_cache_key(payload.namespace_id, scope_user, payload.filepath)

        cached_hash = await self.redis_client.get(cache_key)
        if cached_hash and cached_hash.decode() == file_hash:
            return {"status": "skipped", "reason": "unchanged", "filepath": payload.filepath}

        from trimcp.extractors.dispatch import get_priority_queue
        from trimcp.tasks import process_code_indexing

        q = get_priority_queue(priority, self.redis_sync_client)
        job = q.enqueue(
            process_code_indexing,
            args=(
                payload.filepath,
                payload.raw_code,
                payload.language,
                scope_user,
                str(payload.namespace_id) if payload.namespace_id else None,
            ),
            job_timeout='10m',
        )

        queue_name = q.name
        log.info(
            "[Code] Enqueued indexing job %s for %s (queue=%s)",
            job.id,
            payload.filepath,
            queue_name,
        )
        return {"status": "enqueued", "job_id": job.id, "filepath": payload.filepath}

    async def get_job_status(self, job_id: str) -> dict:
        """Check the status of an RQ job."""
        from rq.job import Job

        try:
            job = await asyncio.to_thread(Job.fetch, job_id, connection=self.redis_sync_client)
            return {
                "job_id": job_id,
                "status": job.get_status(),
                "result": job.result if job.is_finished else None,
                "error": str(job.exc_info) if job.is_failed else None,
            }
        except Exception as e:
            return {"job_id": job_id, "status": "not_found", "error": str(e)}

    # ------------------------------------------------------------------
    # Embedding migration lifecycle
    # ------------------------------------------------------------------

    async def start_migration(self, target_model_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            model = await conn.fetchrow(
                "SELECT id FROM embedding_models WHERE id = $1::uuid", target_model_id
            )
            if not model:
                raise ValueError("Target model not found")

            active = await conn.fetchrow(
                "SELECT id FROM embedding_migrations WHERE status IN ('running', 'validating')"
            )
            if active:
                raise ValueError(f"Migration {active['id']} is already in progress")

            await conn.execute(
                "UPDATE embedding_models SET status = 'migrating' WHERE id = $1::uuid",
                target_model_id,
            )

            mig_id = await conn.fetchval(
                "INSERT INTO embedding_migrations (target_model_id) VALUES ($1::uuid) RETURNING id",
                target_model_id,
            )
            return {"migration_id": str(mig_id), "status": "running"}

    async def migration_status(self, migration_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, target_model_id, status, last_memory_id, last_node_id, "
                "started_at, completed_at FROM embedding_migrations WHERE id = $1::uuid",
                migration_id,
            )
            if not row:
                raise ValueError("Migration not found")
            return dict(row)

    async def validate_migration(self, migration_id: str) -> dict:
        """Quality gate: compare embedded-row counts vs target model.

        Returns ``{"status": "success", "message": ...}`` or
        ``{"status": "failed", "reason": ...}`` — API vocabulary only; the
        ``embedding_migrations.status`` column remains the DB state machine.
        """
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, target_model_id FROM embedding_migrations WHERE id = $1::uuid",
                migration_id,
            )
            if not row or row["status"] != "validating":
                raise ValueError("Migration not found or not in validating state")

            target_model_id = row["target_model_id"]

            # P0 fix: scope mem_count to only memories that possess a
            # corresponding embedding for the target model.  The old unscoped
            # count(*) FROM memories included every namespace on the cluster,
            # guaranteeing emb_count < mem_count and deadlocking every
            # multi-tenant migration at the quality gate.
            mem_count = await conn.fetchval(
                """
                SELECT count(*) FROM memories m
                WHERE EXISTS (
                    SELECT 1 FROM memory_embeddings me
                    WHERE me.memory_id = m.id AND me.model_id = $1::uuid
                )
                """,
                target_model_id,
            )
            emb_count = await conn.fetchval(
                "SELECT count(*) FROM memory_embeddings WHERE model_id = $1::uuid",
                target_model_id,
            )

            if emb_count < mem_count:
                return {
                    "status": "failed",
                    "reason": f"Missing memory embeddings: {mem_count} memories, {emb_count} embeddings",
                }

            return {"status": "success", "message": "All memories and nodes have been embedded"}

    async def commit_migration(self, migration_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT status, target_model_id FROM embedding_migrations WHERE id = $1::uuid",
                    migration_id,
                )
                if not row or row["status"] != "validating":
                    raise ValueError("Migration not ready to commit")

                target_model_id = row["target_model_id"]

                await conn.execute(
                    "UPDATE embedding_models SET status = 'retired', retired_at = now() WHERE status = 'active'"
                )
                await conn.execute(
                    "UPDATE embedding_models SET status = 'active' WHERE id = $1::uuid",
                    target_model_id,
                )
                await conn.execute(
                    "UPDATE embedding_migrations SET status = 'committed', completed_at = now() WHERE id = $1::uuid",
                    migration_id,
                )
                return {"status": "committed", "active_model_id": str(target_model_id)}

    async def abort_migration(self, migration_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT target_model_id FROM embedding_migrations WHERE id = $1::uuid",
                    migration_id,
                )
                if not row:
                    raise ValueError("Migration not found")

                target_model_id = row["target_model_id"]

                await conn.execute(
                    "UPDATE embedding_migrations SET status = 'aborted', completed_at = now() WHERE id = $1::uuid",
                    migration_id,
                )
                await conn.execute(
                    "UPDATE embedding_models SET status = 'retired' WHERE id = $1::uuid",
                    target_model_id,
                )
                return {"status": "aborted"}
