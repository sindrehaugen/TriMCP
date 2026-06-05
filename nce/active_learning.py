from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

from nce.models import StoreMemoryRequest
from nce.db_utils import scoped_pg_session
from nce.config import cfg

log = logging.getLogger("nce.active_learning")


class ActiveLearningManager:
    """
    Manages the Active Learning loop (BATCH-P3-005).
    Stashes low-confidence assertions in active_learning_queue, enables operator
    micro-confirmation / rejection, and provides gamified state tracking statistics.
    """

    def __init__(self, pg_pool: asyncpg.Pool):
        self.pg_pool = pg_pool

    async def quarantine_memory(
        self,
        conn: asyncpg.Connection,
        payload: StoreMemoryRequest,
        confidence_score: float,
    ) -> UUID:
        """
        Quarantines a memory request by stashing the serialized payload in active_learning_queue.
        Returns the stashed queue item ID (UUID).
        """
        # Serialize the StoreMemoryRequest payload
        serialized_payload = payload.model_dump_json()

        queue_id = await conn.fetchval(
            """
            INSERT INTO active_learning_queue (namespace_id, agent_id, payload, confidence_score, status, created_at)
            VALUES ($1::uuid, $2, $3::jsonb, $4::real, 'pending', NOW())
            RETURNING id
            """,
            payload.namespace_id,
            payload.agent_id,
            serialized_payload,
            confidence_score,
        )
        log.info(
            "[ACTIVE-LEARNING] Quarantined memory request with confidence %f. queue_id=%s namespace=%s",
            confidence_score,
            queue_id,
            payload.namespace_id,
        )
        return queue_id

    async def confirm_memory(
        self,
        namespace_id: UUID | str,
        queue_item_id: UUID | str,
        operator_id: str,
        memory_orchestrator,
    ) -> dict:
        """
        Promotes a quarantined memory by loading its stashed payload, modifying its metadata
        to bypass quarantine, and calling the memory orchestrator's store_memory method.
        Marks the queue item as confirmed.
        """
        ns_uuid = UUID(str(namespace_id))
        item_uuid = UUID(str(queue_item_id))

        # 1. Fetch stashed payload and mark resolved, then release database connection A
        async with scoped_pg_session(self.pg_pool, ns_uuid) as conn:
            # Check queue item
            row = await conn.fetchrow(
                """
                SELECT payload, status FROM active_learning_queue
                WHERE id = $1::uuid AND namespace_id = $2::uuid
                FOR UPDATE
                """,
                item_uuid,
                ns_uuid,
            )
            if not row:
                raise ValueError(f"Queue item {queue_item_id} not found in namespace {namespace_id}")
            if row["status"] != "pending":
                raise ValueError(f"Queue item {queue_item_id} is already in state: {row['status']}")

            await conn.execute(
                """
                UPDATE active_learning_queue
                SET status = 'confirmed', resolved_at = NOW(), resolved_by = $1
                WHERE id = $2::uuid AND namespace_id = $3::uuid
                """,
                operator_id,
                item_uuid,
                ns_uuid,
            )

        # 2. De-serialize and reconstruct request payload
        payload_data = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        
        # Add bypass flag to metadata
        if "metadata" not in payload_data or payload_data["metadata"] is None:
            payload_data["metadata"] = {}
        payload_data["metadata"]["bypass_quarantine"] = True

        # Reconstruct StoreMemoryRequest
        req = StoreMemoryRequest(**payload_data)

        # 3. Store memory (acquires connection B)
        try:
            store_res = await memory_orchestrator.store_memory(req)
            log.info(
                "[ACTIVE-LEARNING] Confirmed memory in queue_item=%s by operator=%s. Result memory_ref=%s",
                queue_item_id,
                operator_id,
                store_res.get("payload_ref"),
            )
            return store_res
        except Exception as e:
            # Revert queue item back to pending on failure
            async with scoped_pg_session(self.pg_pool, ns_uuid) as conn:
                await conn.execute(
                    """
                    UPDATE active_learning_queue
                    SET status = 'pending', resolved_at = NULL, resolved_by = NULL
                    WHERE id = $1::uuid AND namespace_id = $2::uuid
                    """,
                    item_uuid,
                    ns_uuid,
                )
            raise e

    async def reject_memory(
        self,
        namespace_id: UUID | str,
        queue_item_id: UUID | str,
        operator_id: str,
    ) -> None:
        """
        Discards a quarantined memory by marking it as rejected in the queue.
        """
        ns_uuid = UUID(str(namespace_id))
        item_uuid = UUID(str(queue_item_id))

        async with scoped_pg_session(self.pg_pool, ns_uuid) as conn:
            row = await conn.fetchrow(
                """
                SELECT status FROM active_learning_queue
                WHERE id = $1::uuid AND namespace_id = $2::uuid
                FOR UPDATE
                """,
                item_uuid,
                ns_uuid,
            )
            if not row:
                raise ValueError(f"Queue item {queue_item_id} not found in namespace {namespace_id}")
            if row["status"] != "pending":
                raise ValueError(f"Queue item {queue_item_id} is already in state: {row['status']}")

            await conn.execute(
                """
                UPDATE active_learning_queue
                SET status = 'rejected', resolved_at = NOW(), resolved_by = $1
                WHERE id = $2::uuid AND namespace_id = $3::uuid
                """,
                operator_id,
                item_uuid,
                ns_uuid,
            )
            log.info(
                "[ACTIVE-LEARNING] Rejected memory in queue_item=%s by operator=%s",
                queue_item_id,
                operator_id,
            )

    async def get_pending_queue(self, namespace_id: UUID | str) -> list[dict]:
        """
        Returns a list of all pending items in the confirmation queue for a namespace.
        """
        ns_uuid = UUID(str(namespace_id))
        async with scoped_pg_session(self.pg_pool, ns_uuid) as conn:
            rows = await conn.fetch(
                """
                SELECT id, agent_id, payload, confidence_score, created_at
                FROM active_learning_queue
                WHERE namespace_id = $1::uuid AND status = 'pending'
                ORDER BY created_at ASC
                """,
                ns_uuid,
            )
            results = []
            for r in rows:
                try:
                    payload_parsed = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
                except Exception as err:
                    log.error("[ACTIVE-LEARNING] Failed to parse payload for queue item %s: %s", r["id"], err)
                    payload_parsed = {}

                results.append({
                    "id": str(r["id"]),
                    "agent_id": r["agent_id"],
                    "payload": payload_parsed,
                    "confidence_score": float(r["confidence_score"]),
                    "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                })
            return results

    async def get_gamified_stats(self, namespace_id: UUID | str, operator_id: str) -> dict:
        """
        Provides state tracking payloads suitable for ingestion by gamified frontend components.
        Calculates counts, accuracy rate, XP points, and confirmation streak.
        """
        ns_uuid = UUID(str(namespace_id))
        async with scoped_pg_session(self.pg_pool, ns_uuid) as conn:
            # Counts
            pending_count = await conn.fetchval(
                "SELECT COUNT(*)::int FROM active_learning_queue WHERE namespace_id = $1::uuid AND status = 'pending'",
                ns_uuid,
            )
            confirmed_count = await conn.fetchval(
                "SELECT COUNT(*)::int FROM active_learning_queue WHERE namespace_id = $1::uuid AND status = 'confirmed'",
                ns_uuid,
            )
            rejected_count = await conn.fetchval(
                "SELECT COUNT(*)::int FROM active_learning_queue WHERE namespace_id = $1::uuid AND status = 'rejected'",
                ns_uuid,
            )

            # Streak calculation: count consecutive resolved items sorted by resolved_at desc
            resolved_rows = await conn.fetch(
                """
                SELECT status, resolved_by FROM active_learning_queue
                WHERE namespace_id = $1::uuid AND status IN ('confirmed', 'rejected')
                ORDER BY resolved_at DESC
                LIMIT 50
                """,
                ns_uuid,
            )

            streak = 0
            # Let's count consecutive confirmations/rejections by this operator
            for r in resolved_rows:
                if r["resolved_by"] == operator_id:
                    streak += 1
                else:
                    break

            # Calculate Experience Points (XP)
            # Confirming a memory gives +10 XP, rejecting gives +5 XP
            # We can query specific operator count or total resolved
            op_confirmed = await conn.fetchval(
                "SELECT COUNT(*)::int FROM active_learning_queue WHERE namespace_id = $1::uuid AND status = 'confirmed' AND resolved_by = $2",
                ns_uuid,
                operator_id,
            )
            op_rejected = await conn.fetchval(
                "SELECT COUNT(*)::int FROM active_learning_queue WHERE namespace_id = $1::uuid AND status = 'rejected' AND resolved_by = $2",
                ns_uuid,
                operator_id,
            )
            xp = (op_confirmed * cfg.NCE_ACTIVE_LEARNING_CONFIRM_XP) + (op_rejected * cfg.NCE_ACTIVE_LEARNING_REJECT_XP)

            # Levels: 100 XP per level
            level = 1 + (xp // 100)
            next_level_xp = 100 - (xp % 100)

            accuracy = 0.0
            total_resolved = confirmed_count + rejected_count
            if total_resolved > 0:
                accuracy = round(confirmed_count / total_resolved, 4)

            return {
                "pending_count": pending_count,
                "confirmed_count": confirmed_count,
                "rejected_count": rejected_count,
                "operator_stats": {
                    "operator_id": operator_id,
                    "confirmed_count": op_confirmed,
                    "rejected_count": op_rejected,
                    "xp": xp,
                    "level": level,
                    "xp_to_next_level": next_level_xp,
                    "streak": streak,
                },
                "accuracy_rate": accuracy,
            }
