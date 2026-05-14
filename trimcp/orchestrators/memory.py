"""
Memory Orchestrator — extracted from TriStackEngine per Clean Code SRP split.

Handles all memory lifecycle operations: store, search, recall, verify, and PII unredaction.
Receives shared connection pools (PG, Mongo, Redis, MinIO) via constructor injection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
import redis.asyncio as redis
from bson import ObjectId
from minio import Minio
from motor.motor_asyncio import AsyncIOMotorClient

from trimcp import embeddings as _embeddings
from trimcp.auth import set_namespace_context
from trimcp.config import cfg
from trimcp.db_utils import scoped_pg_session
from trimcp.mongo_bulk import fetch_episodes_raw_by_ref, normalize_payload_ref
from trimcp.models import (
    _SAFE_ID_RE,
    AssertionType,
    MediaPayload,
    MemoryType,
    NamespacePIIConfig,
    SagaState,
    StoreMemoryRequest,
)
from trimcp.observability import SagaMetrics, get_tracer

log = logging.getLogger("tri-stack-orchestrator.memory")


def _validate_agent_id(agent_id: str) -> str:
    """Shared validation — mirrors orchestrator._validate_agent_id."""
    from trimcp.auth import validate_agent_id as _v

    return _v(agent_id)


class MemoryOrchestrator:
    """Domain orchestrator for memory storage, search, recall, and integrity."""

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        mongo_client: AsyncIOMotorClient,
        redis_client: redis.Redis,
        minio_client: Minio | None = None,
        pg_read_pool: asyncpg.Pool | None = None,
    ):
        self.pg_pool = pg_pool
        self.pg_read_pool = pg_read_pool
        self.mongo_client = mongo_client
        self.redis_client = redis_client
        self.minio_client = minio_client

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _generate_embedding(self, text: str) -> list[float]:
        return await _embeddings.embed(text)

    async def _enqueue_outbox(
        self,
        conn,
        *,
        namespace_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict,
        headers: dict | None = None,
    ) -> None:
        """Write a domain event to the transactional outbox.

        Called inside an existing PG transaction so the event is
        atomically committed with the business write.
        """
        await conn.execute(
            """
            INSERT INTO outbox_events (
                namespace_id, aggregate_type, aggregate_id, event_type, payload, headers
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            namespace_id,
            aggregate_type,
            aggregate_id,
            event_type,
            json.dumps(payload),
            json.dumps(headers or {}),
        )

    # ------------------------------------------------------------------
    # store_memory — Private helpers
    # ------------------------------------------------------------------

    async def _apply_pii_pipeline(self, payload: StoreMemoryRequest, *, conn=None):
        """Phase 0.3: PII Redaction Pipeline + Graph Extraction.

        Returns (pii_result, sanitized_summary, sanitized_heavy, entities, triplets).
        """
        pii_config = NamespacePIIConfig()

        async def _fetch_ns_config(c):
            ns_row = await c.fetchrow(
                "SELECT metadata FROM namespaces WHERE id = $1", payload.namespace_id
            )
            if ns_row:
                meta = json.loads(ns_row["metadata"])
                if "pii" in meta:
                    return NamespacePIIConfig(**meta["pii"])
            return NamespacePIIConfig()

        if conn is not None:
            pii_config = await _fetch_ns_config(conn)
        else:
            async with scoped_pg_session(self.pg_pool, payload.namespace_id) as c:
                pii_config = await _fetch_ns_config(c)

        from trimcp.pii import process as pii_process

        pii_result = await pii_process(payload.summary, pii_config)
        sanitized_summary = pii_result.sanitized_text
        sanitized_heavy = (await pii_process(payload.heavy_payload, pii_config)).sanitized_text

        from trimcp.graph_extractor import extract as graph_extract

        entities, triplets = graph_extract(sanitized_summary)

        return pii_result, sanitized_summary, sanitized_heavy, entities, triplets

    async def _embed_and_insert_vectors(
        self,
        conn,
        *,
        payload,
        sanitized_summary,
        vector,
        pii_result,
        inserted_mongo_id,
        target_model_ids,
        user_id,
        session_id,
    ):
        """Insert memory row + memory_embeddings + PII vault (inside PG tx).

        Returns the new memory_id (UUID).
        """
        metadata = dict(payload.metadata) if payload.metadata else {}
        if (
            getattr(_embeddings, "degraded_embedding_flag", None)
            and _embeddings.degraded_embedding_flag.get()
        ):
            metadata["degraded_embedding"] = True

        memory_id = await conn.fetchval(
            """
            INSERT INTO memories (user_id, session_id, namespace_id, agent_id, embedding, content_fts, payload_ref, pii_redacted, assertion_type, memory_type, metadata)
            VALUES ($1, $2, $3, $4, $5::vector, to_tsvector('english', $6), $7, $8, $9, $10, $11)
            RETURNING id
            """,
            user_id,
            session_id,
            payload.namespace_id,
            payload.agent_id,
            json.dumps(vector),
            sanitized_summary,
            inserted_mongo_id,
            pii_result.redacted,
            payload.assertion_type.value,
            payload.memory_type.value,
            json.dumps(metadata),
        )

        for model_id in target_model_ids:
            await conn.execute(
                "INSERT INTO memory_embeddings (memory_id, model_id, embedding, namespace_id) VALUES ($1, $2, $3::vector, $4) ON CONFLICT DO NOTHING",
                memory_id,
                model_id,
                json.dumps(vector),
                payload.namespace_id,
            )

        if pii_result.vault_entries:
            await conn.executemany(
                """
                INSERT INTO pii_redactions (namespace_id, memory_id, token, encrypted_value, entity_type)
                VALUES ($1, $2, $3, $4, $5)
                """,
                [
                    (
                        payload.namespace_id,
                        memory_id,
                        v["token"],
                        v["encrypted_value"],
                        v["entity_type"],
                    )
                    for v in pii_result.vault_entries
                ],
            )

        return memory_id

    async def _insert_graph_nodes_and_edges(
        self,
        conn,
        *,
        payload,
        entities,
        node_vecs,
        triplets,
        inserted_mongo_id,
        target_model_ids,
        memory_id,
    ):
        """Insert kg_nodes, kg_node_embeddings, kg_edges, and event_log (inside PG tx).

        Uses UNNEST batching to reduce round-trips from O(N) to O(1).
        """
        # ── Batch-insert kg_nodes ────────────────────────────────────────
        if entities and node_vecs:
            labels = [e.label for e in entities]
            entity_types = [e.entity_type for e in entities]
            embeddings = [json.dumps(v) for v in node_vecs]

            returned_rows = await conn.fetch(
                """
                INSERT INTO kg_nodes (label, entity_type, embedding, payload_ref, namespace_id)
                SELECT unnest($1::text[]), unnest($2::text[]), unnest($3::text[])::vector, $4, $5::uuid
                ON CONFLICT (label, namespace_id) DO UPDATE
                    SET entity_type  = EXCLUDED.entity_type,
                        embedding    = EXCLUDED.embedding,
                        payload_ref = EXCLUDED.payload_ref,
                        updated_at   = NOW()
                RETURNING id, label
                """,
                labels,
                entity_types,
                embeddings,
                inserted_mongo_id,
                payload.namespace_id,
            )
            label_to_id = {row["label"]: row["id"] for row in returned_rows}

            # Safety net: fetch IDs for any labels not returned (should not happen with DO UPDATE)
            missing_labels = [lbl for lbl in labels if lbl not in label_to_id]
            if missing_labels:
                rows = await conn.fetch(
                    "SELECT id, label FROM kg_nodes WHERE namespace_id = $1 AND label = ANY($2::text[])",
                    payload.namespace_id,
                    missing_labels,
                )
                for row in rows:
                    label_to_id[row["label"]] = row["id"]

            # ── Batch-insert kg_node_embeddings ──────────────────────────
            if target_model_ids and label_to_id:
                emb_node_ids: list[str] = []
                emb_model_ids: list[str] = []
                emb_vectors: list[str] = []
                for entity, node_vec in zip(entities, node_vecs):
                    nid = label_to_id.get(entity.label)
                    if nid is None:
                        continue
                    for model_id in target_model_ids:
                        emb_node_ids.append(nid)
                        emb_model_ids.append(model_id)
                        emb_vectors.append(json.dumps(node_vec))
                if emb_node_ids:
                    await conn.execute(
                        """
                        INSERT INTO kg_node_embeddings (node_id, model_id, embedding)
                        SELECT unnest($1::uuid[]), unnest($2::text[]), unnest($3::text[])::vector
                        ON CONFLICT DO NOTHING
                        """,
                        emb_node_ids,
                        emb_model_ids,
                        emb_vectors,
                    )

        # ── Batch-insert kg_edges ────────────────────────────────────────
        if triplets:
            subjs = [t.subject_label for t in triplets]
            preds = [t.predicate for t in triplets]
            objs = [t.object_label for t in triplets]
            confs = [t.confidence for t in triplets]
            await conn.execute(
                """
                INSERT INTO kg_edges (subject_label, predicate, object_label, confidence, payload_ref, namespace_id)
                SELECT unnest($1::text[]), unnest($2::text[]), unnest($3::text[]), unnest($4::float[]), $5, $6::uuid
                ON CONFLICT (subject_label, predicate, object_label, namespace_id) DO UPDATE
                    SET confidence   = EXCLUDED.confidence,
                        payload_ref = EXCLUDED.payload_ref,
                        updated_at   = NOW()
                """,
                subjs,
                preds,
                objs,
                confs,
                inserted_mongo_id,
                payload.namespace_id,
            )

        # Phase 2.2: Append to event log
        from trimcp.event_log import append_event

        serialized_entities = [
            {"label": e.label, "entity_type": e.entity_type} for e in entities
        ]
        serialized_triplets = [
            {
                "subject_label": t.subject_label,
                "predicate": t.predicate,
                "object_label": t.object_label,
                "confidence": t.confidence,
            }
            for t in triplets
        ]

        await append_event(
            conn=conn,
            namespace_id=payload.namespace_id,
            agent_id=payload.agent_id,
            event_type="store_memory",
            params={
                "memory_id": str(memory_id),
                "assertion_type": payload.assertion_type.value,
                "entities": serialized_entities,
                "triplets": serialized_triplets,
            },
        )

    # ------------------------------------------------------------------
    # Saga Execution Log helpers (Item A — crash-recovery)
    # ------------------------------------------------------------------

    async def _saga_log_start(
        self, saga_type: str, payload: StoreMemoryRequest
    ) -> str:
        """Insert a 'started' saga row on an independent connection."""
        async with self.pg_pool.acquire(timeout=10.0) as conn:
            async with conn.transaction():
                await set_namespace_context(conn, payload.namespace_id)
                row = await conn.fetchrow(
                    """
                    INSERT INTO saga_execution_log (saga_type, namespace_id, agent_id, state, payload)
                    VALUES ($1, $2::uuid, $3, 'started', $4)
                    RETURNING id
                    """,
                    saga_type,
                    str(payload.namespace_id),
                    payload.agent_id,
                    {
                        "memory_type": payload.memory_type.value,
                        "assertion_type": payload.assertion_type.value,
                        "summary": payload.summary,
                        "metadata": payload.metadata,
                    },
                )
        return str(row["id"])

    async def _saga_log_transition(
        self, saga_id: str, state: SagaState, payload_patch: dict | None = None
    ) -> None:
        """Update saga state on an independent connection, optionally merging payload."""
        async with self.pg_pool.acquire(timeout=10.0) as conn:
            if payload_patch:
                await conn.execute(
                    """
                    UPDATE saga_execution_log
                    SET state = $1, updated_at = NOW(),
                        payload = payload || $3::jsonb
                    WHERE id = $2::uuid
                    """,
                    state,
                    saga_id,
                    payload_patch,
                )
            else:
                await conn.execute(
                    """
                    UPDATE saga_execution_log
                    SET state = $1, updated_at = NOW()
                    WHERE id = $2::uuid
                    """,
                    state,
                    saga_id,
                )

    async def _apply_rollback_on_failure(
        self,
        *,
        e,
        payload,
        collection,
        inserted_mongo_id,
        inserted_result,
        memory_id,
        pg_committed,
        saga_id=None,
    ):
        """Phase-aware universal rollback — cleans Mongo, PG, and safety-cleanup.

        Each store is rolled back independently; failures in one step are caught,
        logged, and do NOT block remaining steps nor mask the original exception.
        """
        log.error("[SAGA] Transaction failed: %s", e)
        SagaMetrics.record_failure("overall")

        # 1. Mongo rollback
        if inserted_mongo_id and inserted_result is not None:
            log.warning("[ROLLBACK] Removing orphaned Mongo doc %s", inserted_mongo_id)
            try:
                await collection.delete_one({"_id": inserted_result.inserted_id})
                log.info("[ROLLBACK] Mongo doc %s removed.", inserted_mongo_id)
            except Exception as mongo_exc:
                log.error("[ROLLBACK] Mongo cleanup failed: %s", mongo_exc)
                SagaMetrics.record_failure("mongo_rollback")

        # 2. Postgres rollback
        if pg_committed and memory_id:
            log.warning(
                "[ROLLBACK] PG transaction committed; removing all artifacts "
                "for memory_id=%s  payload_ref=%s",
                memory_id,
                inserted_mongo_id,
            )
            try:
                async with self.pg_pool.acquire(timeout=10.0) as conn:
                    async with conn.transaction():
                        await set_namespace_context(conn, payload.namespace_id)
                        await conn.execute(
                            "DELETE FROM memory_embeddings WHERE memory_id = $1", memory_id
                        )
                        await conn.execute(
                            "DELETE FROM pii_redactions WHERE memory_id = $1", memory_id
                        )
                        await conn.execute(
                            "DELETE FROM kg_node_embeddings "
                            "WHERE node_id IN (SELECT id FROM kg_nodes WHERE payload_ref = $1)",
                            inserted_mongo_id,
                        )
                        await conn.execute(
                            "DELETE FROM kg_edges WHERE payload_ref = $1", inserted_mongo_id
                        )
                        await conn.execute(
                            "DELETE FROM kg_nodes WHERE payload_ref = $1", inserted_mongo_id
                        )
                        from trimcp.event_log import append_event

                        await append_event(
                            conn=conn,
                            namespace_id=payload.namespace_id,
                            agent_id=payload.agent_id,
                            event_type="store_memory_rolled_back",
                            params={
                                "memory_id": str(memory_id),
                                "reason": str(e)[:256],
                                "payload_ref": inserted_mongo_id,
                            },
                        )
                        await conn.execute(
                            "UPDATE memories SET valid_to = now() WHERE id = $1 AND valid_to IS NULL",
                            memory_id,
                        )
                log.info("[ROLLBACK] PG artifacts removed for memory_id=%s", memory_id)
            except Exception as pg_exc:
                log.error("[ROLLBACK] PG cleanup failed (GC will reap): %s", pg_exc)
                SagaMetrics.record_failure("pg_rollback")
        elif inserted_mongo_id:
            log.warning(
                "[ROLLBACK] PG transaction did not commit; "
                "attempting safety cleanup by payload_ref=%s",
                inserted_mongo_id,
            )
            try:
                async with self.pg_pool.acquire(timeout=10.0) as conn:
                    async with conn.transaction():
                        await conn.execute(
                            "DELETE FROM kg_edges WHERE payload_ref = $1", inserted_mongo_id
                        )
                        await conn.execute(
                            "DELETE FROM kg_nodes WHERE payload_ref = $1", inserted_mongo_id
                        )
                        await conn.execute(
                            "UPDATE memories SET valid_to = now() WHERE payload_ref = $1 AND valid_to IS NULL",
                            inserted_mongo_id,
                        )
            except Exception as pg_exc:
                log.error(
                    "[ROLLBACK] PG safety cleanup failed (GC will reap): %s", pg_exc
                )
                SagaMetrics.record_failure("pg_rollback")

        if saga_id:
            try:
                await self._saga_log_transition(saga_id, SagaState.ROLLED_BACK)
            except Exception as saga_exc:
                log.error("[SAGA-LOG] Failed to transition to rolled_back: %s", saga_exc)

        log.info("[ROLLBACK] Tri-Stack remains pure.")

    # ------------------------------------------------------------------
    # store_memory (Saga Pattern)
    # ------------------------------------------------------------------

    async def store_memory(self, payload: StoreMemoryRequest) -> dict:
        """
        Saga Pattern: MongoDB → PostgreSQL → Redis.
        PG failure triggers automatic Mongo rollback.
        """
        tracer = get_tracer()
        with tracer.start_as_current_span("orchestrator.store_memory") as span:
            span.set_attribute("trimcp.namespace_id", str(payload.namespace_id))
            with SagaMetrics("store_memory"):
                db = self.mongo_client.memory_archive
                collection = db.episodes
                inserted_mongo_id: str | None = None
                inserted_result = None

                memory_id = None
                pg_committed = False
                saga_id = await self._saga_log_start("store_memory", payload)

                try:
                    # Single PG session for config read + atomic commit
                    async with scoped_pg_session(self.pg_pool, payload.namespace_id) as conn:
                        # --- Phase 0.3: PII Redaction + Graph Extraction ---
                        (
                            pii_result,
                            sanitized_summary,
                            sanitized_heavy,
                            entities,
                            triplets,
                        ) = await self._apply_pii_pipeline(payload, conn=conn)

                        # STEP 1: Episodic Commit (MongoDB)
                        user_id = (
                            payload.metadata.get("user_id") if payload.metadata else None
                        )
                        session_id = (
                            payload.metadata.get("session_id") if payload.metadata else None
                        )

                        inserted_result = await collection.insert_one(
                            {
                                "user_id": user_id,
                                "session_id": session_id,
                                "namespace_id": str(payload.namespace_id),
                                "type": payload.memory_type.value,
                                "raw_data": sanitized_heavy,
                                "metadata": payload.metadata,
                                "pii_redacted": pii_result.redacted,
                                "pii_entities_found": pii_result.entities_found,
                                "ingested_at": datetime.now(timezone.utc),
                            }
                        )
                        inserted_mongo_id = str(inserted_result.inserted_id)
                        log.debug("[Mongo] Inserted episode. id=%s", inserted_mongo_id)

                        # Pre-compute all embeddings OUTSIDE the PG transaction
                        all_texts = [sanitized_summary] + [e.label for e in entities]
                        all_vectors = await _embeddings.embed_batch(all_texts)
                        vector = all_vectors[0]
                        node_vecs = all_vectors[1:]

                        # Fetch active and migrating models
                        models = await conn.fetch(
                            "SELECT id FROM embedding_models WHERE status IN ('active', 'migrating')"
                        )
                        target_model_ids = [m["id"] for m in models]

                        # STEP 2 + 2b: Atomic Semantic + Graph Commit (single PG transaction)
                        async with conn.transaction():
                            memory_id = await self._embed_and_insert_vectors(
                                conn,
                                payload=payload,
                                sanitized_summary=sanitized_summary,
                                vector=vector,
                                pii_result=pii_result,
                                inserted_mongo_id=inserted_mongo_id,
                                target_model_ids=target_model_ids,
                                user_id=user_id,
                                session_id=session_id,
                            )

                            await self._insert_graph_nodes_and_edges(
                                conn,
                                payload=payload,
                                entities=entities,
                                node_vecs=node_vecs,
                                triplets=triplets,
                                inserted_mongo_id=inserted_mongo_id,
                                target_model_ids=target_model_ids,
                                memory_id=memory_id,
                            )

                            # STEP 2c: Transactional Outbox — atomically publish
                            await self._enqueue_outbox(
                                conn,
                                namespace_id=str(payload.namespace_id),
                                aggregate_type="memory",
                                aggregate_id=str(memory_id),
                                event_type="memory.stored",
                                payload={
                                    "memory_id": str(memory_id),
                                    "payload_ref": inserted_mongo_id,
                                    "assertion_type": payload.assertion_type.value,
                                    "memory_type": payload.memory_type.value,
                                    "entities_count": len(entities),
                                    "triplets_count": len(triplets),
                                },
                                headers={"source": "store_memory"},
                            )

                    log.debug(
                        "[PG] Atomic commit: vector + %d nodes + %d edges. mongo_ref=%s",
                        len(entities),
                        len(triplets),
                        inserted_mongo_id,
                    )

                    pg_committed = True
                    await self._saga_log_transition(
                        saga_id, SagaState.PG_COMMITTED, payload_patch={"memory_id": str(memory_id)}
                    )

                    # STEP 3: Working Memory (Redis)
                    if user_id and session_id:
                        redis_key = (
                            f"cache:{payload.namespace_id}:{user_id}:{session_id}"
                        )
                        await self.redis_client.setex(
                            redis_key, cfg.REDIS_TTL, sanitized_summary
                        )
                        log.debug("[Redis] Summary cached. key=%s", redis_key)

                    # STEP 4: Contradiction Detection
                    contradiction_result = None
                    if payload.check_contradictions:
                        from trimcp.contradictions import detect_contradictions

                        try:
                            contradiction_result = await detect_contradictions(
                                self.pg_pool,
                                self.mongo_client,
                                str(payload.namespace_id),
                                str(memory_id),
                                sanitized_summary,
                                payload.assertion_type.value,
                                vector,
                                payload.agent_id,
                                triplets,
                                detection_path="sync",
                            )
                        except Exception as e:
                            log.error("Contradiction detection failed: %s", e)

                    await self._saga_log_transition(saga_id, SagaState.COMPLETED)
                    return {
                        "payload_ref": inserted_mongo_id,
                        "contradiction": contradiction_result,
                    }

                except Exception as e:
                    await self._apply_rollback_on_failure(
                        e=e,
                        payload=payload,
                        collection=collection,
                        inserted_mongo_id=inserted_mongo_id,
                        inserted_result=inserted_result,
                        memory_id=memory_id,
                        pg_committed=pg_committed,
                        saga_id=saga_id,
                    )
                    raise

    # ------------------------------------------------------------------
    # store_artifact (formerly store_media)
    # ------------------------------------------------------------------

    async def store_artifact(self, payload: ArtifactPayload) -> str:
        """Upload artifact to MinIO, index summary into Tri-Stack."""
        tracer = get_tracer()
        with tracer.start_as_current_span("orchestrator.store_artifact") as span:
            span.set_attribute("trimcp.artifact_type", payload.media_type)
            with SagaMetrics("store_artifact"):
                safe_path = os.path.basename(payload.file_path_on_disk)

                if not os.path.exists(safe_path):
                    raise FileNotFoundError(
                        f"Media file not found: {safe_path}"
                    )

                if self.minio_client is None:
                    raise RuntimeError(
                        "MinIO client not configured — cannot store media."
                    )

                bucket_name = f"mcp-{payload.media_type}"
                file_ext = os.path.splitext(safe_path)[1]
                object_name = f"{payload.session_id}_{uuid.uuid4().hex}{file_ext}"

                await asyncio.to_thread(
                    self.minio_client.fput_object,
                    bucket_name,
                    object_name,
                    safe_path,
                )
                    log.info(
                        "[MinIO] Uploaded artifact to %s/%s",
                        bucket_name,
                        object_name,
                    )

                media_metadata = {
                    "bucket": bucket_name,
                    "object_name": object_name,
                    "media_type": payload.media_type,
                    "original_path": payload.file_path_on_disk,
                    "user_id": payload.user_id,
                    "session_id": payload.session_id,
                }

                memory_req = StoreMemoryRequest(
                    namespace_id=payload.namespace_id,
                    agent_id="system",
                    content=payload.summary,
                    summary=payload.summary,
                    heavy_payload=payload.summary,
                    metadata=media_metadata,
                    memory_type=MemoryType.episodic,
                    assertion_type=AssertionType.observation,
                )

                try:
                    res = await self.store_memory(memory_req)
                except Exception:
                    # Saga rollback: remove orphaned MinIO object
                    log.warning(
                        "[MinIO-ROLLBACK] Removing orphaned object %s/%s",
                        bucket_name,
                        object_name,
                    )
                    try:
                        await asyncio.to_thread(
                            self.minio_client.remove_object,
                            bucket_name,
                            object_name,
                        )
                    except Exception as minio_exc:
                        log.error(
                            "[MinIO-ROLLBACK] Failed to remove %s/%s: %s",
                            bucket_name,
                            object_name,
                            minio_exc,
                        )
                        from trimcp.observability import MINIO_ORPHAN_CLEANUP_FAILURES_TOTAL
                        MINIO_ORPHAN_CLEANUP_FAILURES_TOTAL.inc()
                    raise
                return res["payload_ref"]

    async def store_media(self, payload: MediaPayload) -> str:
        """[DEPRECATED] Alias for store_artifact."""
        return await self.store_artifact(payload)

    # ------------------------------------------------------------------
    # verify_memory
    # ------------------------------------------------------------------

    def _db_pool(self, read_only: bool = False) -> asyncpg.Pool:
        """Return read-replica pool for reads when available."""
        if read_only and self.pg_read_pool is not None:
            return self.pg_read_pool
        return self.pg_pool

    async def verify_memory(
        self, memory_id: str, as_of: datetime | None = None
    ) -> dict:
        """[Phase 0.2] Verify integrity and causal provenance of a memory."""
        from trimcp.signing import (
            decrypt_signing_key,
            require_master_key,
            verify_fields,
        )

        async with self._db_pool(read_only=True).acquire(timeout=10.0) as conn:
            if as_of:
                row = await conn.fetchrow(
                    """
                    SELECT m.*, sk.encrypted_key, sk.key_id as signing_key_id
                    FROM memories m
                    JOIN signing_keys sk ON sk.key_id = m.signature_key_id
                    WHERE m.id = $1 AND m.valid_from <= $2
                      AND (m.valid_to IS NULL OR m.valid_to > $2)
                    ORDER BY m.valid_from DESC LIMIT 1
                    """,
                    UUID(memory_id),
                    as_of,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT m.*, sk.encrypted_key, sk.key_id as signing_key_id
                    FROM memories m
                    JOIN signing_keys sk ON sk.key_id = m.signature_key_id
                    WHERE m.id = $1 AND m.valid_to IS NULL
                    """,
                    UUID(memory_id),
                )

            if not row:
                return {"valid": False, "reason": "memory_not_found"}

            with require_master_key() as master_key:
                raw_key = decrypt_signing_key(bytes(row["encrypted_key"]), master_key)

            fields = {
                "namespace_id": str(row["namespace_id"]),
                "agent_id": row["agent_id"],
                "payload_ref": row["payload_ref"],
                "created_at": row["created_at"].isoformat(),
                "assertion_type": row["assertion_type"],
            }

            is_valid = verify_fields(fields, raw_key, bytes(row["signature"]))

            payload_hash = None
            # Cache the payload hash in Redis to avoid recalculating on every call.
            # The cache is invalidated if the memory is updated (payload_ref changes).
            cache_key = f"mem_verify_hash:{memory_id}"
            try:
                cached_hash = await self.redis_client.get(cache_key)
                if cached_hash is not None:
                    payload_hash = cached_hash.decode("utf-8")
            except Exception:
                pass  # Cache miss or Redis down — recalculate below

            if payload_hash is None:
                db = self.mongo_client.memory_archive
                doc = await db.episodes.find_one({"_id": row["payload_ref"]})
                if doc:
                    content = doc.get("raw_data", "")
                    payload_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    try:
                        await self.redis_client.setex(
                            cache_key, cfg.REDIS_TTL, payload_hash
                        )
                    except Exception:
                        pass  # Non-critical cache write

            return {
                "valid": is_valid,
                "reason": "ok" if is_valid else "signature_mismatch",
                "signed_at": row["created_at"].isoformat(),
                "key_id": row["signing_key_id"],
                "payload_hash": payload_hash,
            }

    # ------------------------------------------------------------------
    # unredact_memory
    # ------------------------------------------------------------------

    async def unredact_memory(
        self, memory_id: str, namespace_id: str, agent_id: str
    ) -> dict:
        """[Phase 0.3] Reverse pseudonymisation for a given memory (admin-only)."""
        from trimcp.event_log import append_event
        from trimcp.signing import decrypt_signing_key, require_master_key

        # Phase 1 — RLS-scoped PG read (FIX-025: never raw pool.acquire for tenant paths).
        async with scoped_pg_session(self.pg_pool, namespace_id) as conn:
            ns_row = await conn.fetchrow(
                "SELECT metadata FROM namespaces WHERE id = $1", namespace_id
            )
            if (
                not ns_row
                or "pii" not in ns_row["metadata"]
                or not ns_row["metadata"]["pii"].get("reversible")
            ):
                raise ValueError(
                    "Namespace PII policy does not allow unredaction (reversible=False)."
                )

            mem_row = await conn.fetchrow(
                "SELECT payload_ref, pii_redacted FROM memories WHERE id = $1",
                memory_id,
            )
            if not mem_row:
                raise ValueError("Memory not found.")
            if not mem_row["pii_redacted"]:
                return {"status": "not_redacted"}

            vault_rows = await conn.fetch(
                "SELECT token, encrypted_value FROM pii_redactions WHERE memory_id = $1",
                memory_id,
            )
            if not vault_rows:
                return {"status": "no_vault_entries"}

            payload_ref = mem_row["payload_ref"]
            vault_list = [
                {"token": r["token"], "encrypted_value": r["encrypted_value"]}
                for r in vault_rows
            ]

        # Phase 2 — Mongo + local crypto (no DB connection held).
        db = self.mongo_client.memory_archive
        doc = await db.episodes.find_one({"_id": ObjectId(payload_ref)})
        if not doc:
            raise ValueError("MongoDB payload missing.")

        raw_data = doc.get("raw_data", "")
        if not isinstance(raw_data, str):
            return {"status": "raw_data_not_string"}

        with require_master_key() as mk:
            for v_row in vault_list:
                token = v_row["token"]
                encrypted_val = v_row["encrypted_value"]
                try:
                    original_val = decrypt_signing_key(encrypted_val, mk).decode(
                        "utf-8"
                    )
                    raw_data = raw_data.replace(token, original_val)
                except Exception as e:
                    log.warning("Failed to decrypt token %s: %s", token, e)

        # Phase 3 — append audit event under RLS.
        async with scoped_pg_session(self.pg_pool, namespace_id) as conn:
            await append_event(
                conn=conn,
                namespace_id=UUID(namespace_id),
                agent_id=agent_id,
                event_type="unredact",
                params={"memory_id": memory_id},
                result_summary={
                    "status": "success",
                    "tokens_unredacted": len(vault_list),
                },
            )

        return {"status": "success", "unredacted_text": raw_data}

    # ------------------------------------------------------------------
    # recall_memory / recall_recent
    # ------------------------------------------------------------------

    async def recall_memory(
        self,
        namespace_id: str,
        user_id: str,
        session_id: str,
        as_of: datetime | None = None,
    ) -> str | None:
        """Legacy single-result recall."""
        results = await self.recall_recent(
            namespace_id,
            agent_id=user_id,
            limit=1,
            as_of=as_of,
            user_id=user_id,
            session_id=session_id,
        )
        return results[0] if results else None

    async def recall_recent(
        self,
        namespace_id: str,
        agent_id: str = "default",
        limit: int = 10,
        as_of: datetime | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        offset: int = 0,
    ) -> list[str]:
        """[Phase 2.2] Retrieve N most recent episodic memories for an agent."""
        if not namespace_id:
            raise ValueError("namespace_id is required")

        agent_id = _validate_agent_id(agent_id)
        if offset < 0:
            raise ValueError("offset must be >= 0")
        offset = int(offset)
        if user_id and not _SAFE_ID_RE.match(user_id):
            raise ValueError("Invalid user_id format")
        if session_id and not _SAFE_ID_RE.match(session_id):
            raise ValueError("Invalid session_id format")

        if not as_of and limit == 1 and offset == 0 and not user_id and not session_id:
            redis_key = f"cache:{namespace_id}:{agent_id}"
            cached = await self.redis_client.get(redis_key)
            if cached:
                log.debug("[Redis] Cache hit. key=%s", redis_key)
                return [cached.decode()]

        async with scoped_pg_session(self._db_pool(read_only=True), namespace_id) as conn:
            filters = ["namespace_id = $1", "memory_type = 'episodic'"]
            params: list[Any] = [UUID(str(namespace_id))]
            p_idx = 2

            if user_id:
                filters.append(f"user_id = ${p_idx}")
                params.append(user_id)
                p_idx += 1
            if session_id:
                filters.append(f"session_id = ${p_idx}")
                params.append(session_id)
                p_idx += 1
            if not user_id and not session_id:
                filters.append(f"agent_id = ${p_idx}")
                params.append(agent_id)
                p_idx += 1

            if as_of:
                filters.append(f"valid_from <= ${p_idx}")
                params.append(as_of)
                p_idx += 1
                filters.append(f"(valid_to IS NULL OR valid_to > ${p_idx - 1})")
                order_by = "valid_from DESC"
            else:
                filters.append("valid_to IS NULL")
                order_by = "created_at DESC"

            sql = f"""
                SELECT payload_ref FROM memories
                WHERE {" AND ".join(filters)}
                ORDER BY {order_by} LIMIT ${p_idx} OFFSET ${p_idx + 1}
            """
            params.extend([limit, offset])
            rows = await conn.fetch(sql, *params)

        if not rows:
            return []

        db = self.mongo_client.memory_archive
        keys = [normalize_payload_ref(r["payload_ref"]) for r in rows]
        raw_by_ref = await fetch_episodes_raw_by_ref(db, keys)

        results = []
        for row in rows:
            key = normalize_payload_ref(row["payload_ref"])
            txt = raw_by_ref.get(key, "")
            if txt:
                results.append(str(txt))

        if (
            not as_of
            and limit == 1
            and offset == 0
            and results
            and not user_id
            and not session_id
        ):
            redis_key = f"cache:{namespace_id}:{agent_id}"
            await self.redis_client.setex(redis_key, cfg.REDIS_TTL, results[0])

        return results

    # ------------------------------------------------------------------
    # semantic_search
    # ------------------------------------------------------------------

    async def semantic_search(
        self,
        query: str,
        namespace_id: str,
        agent_id: str,
        limit: int = 5,
        offset: int = 0,
        as_of=None,
    ) -> list[dict]:
        """Semantic search with pgvector cosine + FTS hybrid ranking."""
        from trimcp.semantic_search import semantic_search

        return await semantic_search(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo_client,
            embedding_fn=self._generate_embedding,
            query=query,
            namespace_id=namespace_id,
            agent_id=agent_id,
            limit=limit,
            offset=offset,
            as_of=as_of,
        )

