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
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
import redis.asyncio as redis
from bson import ObjectId
from minio import Minio
from motor.motor_asyncio import AsyncIOMotorClient
from pypika import Field, Order, Parameter, Query, Table
from pypika.enums import JoinType
from pypika.terms import Term

from trimcp import embeddings as _embeddings
from trimcp.config import cfg
from trimcp.models import (
    AssertionType,
    MediaPayload,
    MemoryType,
    NamespaceCognitiveConfig,
    NamespacePIIConfig,
    StoreMemoryRequest,
)
from trimcp.observability import SagaMetrics, get_tracer


class RawExpression(Term):
    """Custom term class for injecting raw SQL fragments into PyPika queries."""

    def __init__(self, sql: str):
        super().__init__()
        self.sql = sql

    def get_sql(self, **kwargs) -> str:
        return self.sql


class RawTable(Table):
    """Custom table class for injecting unquoted raw SQL/LATERAL in join clauses."""

    def __init__(self, sql: str):
        super().__init__("")
        self.sql = sql

    def get_table_name(self) -> str:
        return self.sql

    def get_sql(self, **kwargs) -> str:
        return self.sql


class AsyncpgQueryBuilder:
    """Stateful query builder wrapper to manage sequential $N placeholders for asyncpg."""

    def __init__(self):
        self._params = []

    def param(self, value: Any) -> Parameter:
        self._params.append(value)
        return Parameter(f"${len(self._params)}")

    def get_params(self) -> list:
        return self._params


log = logging.getLogger("tri-stack-orchestrator.memory")

# --- Constants (mirrored from orchestrator.py) ---
_SAFE_ID_RE = __import__("re").compile(r"^[\w\-]{1,128}$")
_MAX_SUMMARY_LEN = 8_192
_MAX_PAYLOAD_LEN = 10 * 1024 * 1024
_MAX_TOP_K = 100


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
    ):
        self.pg_pool = pg_pool
        self.mongo_client = mongo_client
        self.redis_client = redis_client
        self.minio_client = minio_client

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def scoped_session(self, namespace_id: str | UUID):
        """Tenant-isolated PostgreSQL session with RLS context.

        Instrumented with SCOPED_SESSION_LATENCY (Prompt 28)."""
        import time as _time

        if not namespace_id:
            raise ValueError("namespace_id is required for scoped sessions")
        ns_uuid = UUID(str(namespace_id))
        _t0 = _time.perf_counter()
        async with self.pg_pool.acquire() as conn:
            from trimcp.auth import set_namespace_context

            await set_namespace_context(conn, ns_uuid)
            from trimcp.observability import SCOPED_SESSION_LATENCY

            SCOPED_SESSION_LATENCY.labels(
                namespace_id=str(ns_uuid)[:8],
            ).observe(_time.perf_counter() - _t0)
            yield conn

    async def _generate_embedding(self, text: str) -> list[float]:
        return await _embeddings.embed(text)

    # ------------------------------------------------------------------
    # store_memory — Private helpers
    # ------------------------------------------------------------------

    async def _apply_pii_pipeline(self, payload: StoreMemoryRequest):
        """Phase 0.3: PII Redaction Pipeline + Graph Extraction.

        Returns (pii_result, sanitized_summary, sanitized_heavy, entities, triplets).
        """
        pii_config = NamespacePIIConfig()
        async with self.scoped_session(payload.namespace_id) as conn:
            ns_row = await conn.fetchrow(
                "SELECT metadata FROM namespaces WHERE id = $1", payload.namespace_id
            )
            if ns_row:
                meta = json.loads(ns_row["metadata"])
                if "pii" in meta:
                    pii_config = NamespacePIIConfig(**meta["pii"])

        from trimcp.pii import process as pii_process

        pii_result = pii_process(payload.summary, pii_config)
        sanitized_summary = pii_result.sanitized_text
        sanitized_heavy = pii_process(payload.heavy_payload, pii_config).sanitized_text

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
        """Insert kg_nodes, kg_node_embeddings, kg_edges, and event_log (inside PG tx)."""
        for entity, node_vec in zip(entities, node_vecs):
            await conn.execute(
                """
                INSERT INTO kg_nodes (label, entity_type, embedding, payload_ref, namespace_id)
                VALUES ($1, $2, $3::vector, $4, $5)
                ON CONFLICT (label, namespace_id) DO UPDATE
                    SET entity_type  = EXCLUDED.entity_type,
                        embedding    = EXCLUDED.embedding,
                        payload_ref = EXCLUDED.payload_ref,
                        updated_at   = NOW()
                """,
                entity.label,
                entity.entity_type,
                json.dumps(node_vec),
                inserted_mongo_id,
                payload.namespace_id,
            )

            node_id = await conn.fetchval(
                "SELECT id FROM kg_nodes WHERE label = $1 AND namespace_id = $2",
                entity.label,
                payload.namespace_id,
            )
            if node_id:
                for model_id in target_model_ids:
                    await conn.execute(
                        "INSERT INTO kg_node_embeddings (node_id, model_id, embedding) VALUES ($1, $2, $3::vector) ON CONFLICT DO NOTHING",
                        node_id,
                        model_id,
                        json.dumps(node_vec),
                    )

        for triplet in triplets:
            await conn.execute(
                """
                INSERT INTO kg_edges (subject_label, predicate, object_label, confidence, payload_ref, namespace_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (subject_label, predicate, object_label, namespace_id) DO UPDATE
                    SET confidence   = EXCLUDED.confidence,
                        payload_ref = EXCLUDED.payload_ref,
                        updated_at   = NOW()
                """,
                triplet.subject_label,
                triplet.predicate,
                triplet.object_label,
                triplet.confidence,
                inserted_mongo_id,
                payload.namespace_id,
            )

        # Phase 2.2: Append to event log
        from trimcp.event_log import append_event

        serialized_entities = [{"label": e.label, "entity_type": e.entity_type} for e in entities]
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
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM memory_embeddings WHERE memory_id = $1", memory_id
                    )
                    await conn.execute("DELETE FROM pii_redactions WHERE memory_id = $1", memory_id)
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
                    await conn.execute(
                        "DELETE FROM event_log "
                        "WHERE namespace_id = $1 AND params->>'memory_id' = $2",
                        payload.namespace_id,
                        str(memory_id),
                    )
                    await conn.execute("DELETE FROM memories WHERE id = $1", memory_id)
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
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM kg_edges WHERE payload_ref = $1", inserted_mongo_id
                    )
                    await conn.execute(
                        "DELETE FROM kg_nodes WHERE payload_ref = $1", inserted_mongo_id
                    )
                    await conn.execute(
                        "DELETE FROM memories WHERE payload_ref = $1", inserted_mongo_id
                    )
            except Exception as pg_exc:
                log.error("[ROLLBACK] PG safety cleanup failed (GC will reap): %s", pg_exc)
                SagaMetrics.record_failure("pg_rollback")

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

                # --- Phase 0.3: PII Redaction + Graph Extraction ---
                (
                    pii_result,
                    sanitized_summary,
                    sanitized_heavy,
                    entities,
                    triplets,
                ) = await self._apply_pii_pipeline(payload)

                memory_id = None
                pg_committed = False

                try:
                    # STEP 1: Episodic Commit (MongoDB)
                    user_id = payload.metadata.get("user_id") if payload.metadata else None
                    session_id = payload.metadata.get("session_id") if payload.metadata else None

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
                            "ingested_at": datetime.now(UTC),
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
                    async with self.scoped_session(payload.namespace_id) as conn:
                        models = await conn.fetch(
                            "SELECT id FROM embedding_models WHERE status IN ('active', 'migrating')"
                        )
                        target_model_ids = [m["id"] for m in models]

                    # STEP 2 + 2b: Atomic Semantic + Graph Commit (single PG transaction)
                    async with self.scoped_session(payload.namespace_id) as conn:
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

                    log.debug(
                        "[PG] Atomic commit: vector + %d nodes + %d edges. mongo_ref=%s",
                        len(entities),
                        len(triplets),
                        inserted_mongo_id,
                    )

                    pg_committed = True

                    # STEP 3: Working Memory (Redis)
                    if user_id and session_id:
                        redis_key = f"cache:{payload.namespace_id}:{user_id}:{session_id}"
                        await self.redis_client.setex(redis_key, cfg.REDIS_TTL, sanitized_summary)
                        log.debug("[Redis] Summary cached. key=%s", redis_key)

                    # STEP 4: Contradiction Detection
                    contradiction_result = None
                    if payload.check_contradictions:
                        from trimcp.contradictions import detect_contradictions

                        try:
                            async with self.pg_pool.acquire() as conn:
                                contradiction_result = await detect_contradictions(
                                    conn=conn,
                                    mongo_client=self.mongo_client,
                                    namespace_id=str(payload.namespace_id),
                                    memory_id=str(memory_id),
                                    memory_text=sanitized_summary,
                                    assertion_type=payload.assertion_type.value,
                                    embedding=vector,
                                    agent_id=payload.agent_id,
                                    triplets=triplets,
                                    detection_path="sync",
                                )
                        except Exception as e:
                            log.error("Contradiction detection failed: %s", e)

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
                    )
                    raise

    # ------------------------------------------------------------------
    # store_media
    # ------------------------------------------------------------------

    async def store_media(self, payload: MediaPayload) -> str:
        """Upload media to MinIO, index summary into Tri-Stack."""
        tracer = get_tracer()
        with tracer.start_as_current_span("orchestrator.store_media") as span:
            span.set_attribute("trimcp.media_type", payload.media_type)
            with SagaMetrics("store_media"):
                if not os.path.exists(payload.file_path_on_disk):
                    raise FileNotFoundError(f"Media file not found: {payload.file_path_on_disk}")

                if self.minio_client is None:
                    raise RuntimeError("MinIO client not configured — cannot store media.")

                bucket_name = f"mcp-{payload.media_type}"
                file_ext = os.path.splitext(payload.file_path_on_disk)[1]
                object_name = f"{payload.session_id}_{uuid.uuid4().hex}{file_ext}"

                await asyncio.to_thread(
                    self.minio_client.fput_object,
                    bucket_name,
                    object_name,
                    payload.file_path_on_disk,
                )
                log.info(
                    "[MinIO] Uploaded %s to %s/%s", payload.media_type, bucket_name, object_name
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

                res = await self.store_memory(memory_req)
                return res["payload_ref"]

    # ------------------------------------------------------------------
    # verify_memory
    # ------------------------------------------------------------------

    async def verify_memory(self, memory_id: str, as_of: datetime | None = None) -> dict:
        """[Phase 0.2] Verify integrity and causal provenance of a memory."""
        from trimcp.signing import decrypt_signing_key, require_master_key, verify_fields

        async with self.pg_pool.acquire() as conn:
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
                        await self.redis_client.setex(cache_key, cfg.REDIS_TTL, payload_hash)
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

    async def unredact_memory(self, memory_id: str, namespace_id: str, agent_id: str) -> dict:
        """[Phase 0.3] Reverse pseudonymisation for a given memory (admin-only)."""
        from trimcp.signing import decrypt_signing_key, require_master_key

        async with self.pg_pool.acquire() as conn:
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
                "SELECT payload_ref, pii_redacted FROM memories WHERE id = $1", memory_id
            )
            if not mem_row:
                raise ValueError("Memory not found.")
            if not mem_row["pii_redacted"]:
                return {"status": "not_redacted"}

            vault_rows = await conn.fetch(
                "SELECT token, encrypted_value FROM pii_redactions WHERE memory_id = $1", memory_id
            )
            if not vault_rows:
                return {"status": "no_vault_entries"}

            db = self.mongo_client.memory_archive
            doc = await db.episodes.find_one({"_id": ObjectId(mem_row["payload_ref"])})
            if not doc:
                raise ValueError("MongoDB payload missing.")

            raw_data = doc.get("raw_data", "")
            if not isinstance(raw_data, str):
                return {"status": "raw_data_not_string"}

            with require_master_key() as mk:
                for v_row in vault_rows:
                    token = v_row["token"]
                    encrypted_val = v_row["encrypted_value"]
                    try:
                        original_val = decrypt_signing_key(encrypted_val, mk).decode('utf-8')
                        raw_data = raw_data.replace(token, original_val)
                    except Exception as e:
                        log.warning("Failed to decrypt token %s: %s", token, e)

            from trimcp.event_log import append_event

            await append_event(
                conn=conn,
                namespace_id=namespace_id,
                agent_id=agent_id,
                event_type="unredact",
                params={"memory_id": memory_id},
                result_summary={"status": "success", "tokens_unredacted": len(vault_rows)},
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

        async with self.scoped_session(namespace_id) as conn:
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
        results = []
        for row in rows:
            doc = await db.episodes.find_one({"_id": ObjectId(row["payload_ref"])})
            if doc:
                results.append(str(doc.get("raw_data", "")))

        if not as_of and limit == 1 and offset == 0 and results and not user_id and not session_id:
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
        limit = max(1, min(int(limit), _MAX_TOP_K))
        offset = max(0, int(offset))
        need = offset + limit
        candidate_k = min(max(need * 4, 20), 2000)

        cognitive_config = NamespaceCognitiveConfig()
        temporal_retention_days = 90

        async with self.scoped_session(namespace_id) as conn:
            ns_row = await conn.fetchrow(
                "SELECT metadata FROM namespaces WHERE id = $1", UUID(namespace_id)
            )
            if ns_row:
                meta = ns_row["metadata"]
                if "cognitive" in meta:
                    cognitive_config = NamespaceCognitiveConfig(**meta["cognitive"])
                if "temporal_retention_days" in meta:
                    temporal_retention_days = meta["temporal_retention_days"]

            vector = await self._generate_embedding(query)

            builder = AsyncpgQueryBuilder()
            p_vector = builder.param(json.dumps(vector))
            p_namespace_id = builder.param(UUID(namespace_id))
            p_agent_id = builder.param(agent_id)
            p_candidate_k = builder.param(candidate_k)
            p_query = builder.param(query)

            m = Table("memories").as_("m")
            me = Table("memory_embeddings").as_("me")
            s = Table("memory_salience").as_("s")

            active_model_id = await conn.fetchval(
                "SELECT id FROM embedding_models WHERE status = 'active' LIMIT 1"
            )

            v_cand_query = Query.from_(m)
            if active_model_id:
                distance_expr = RawExpression(f"me.embedding <=> {p_vector}::vector")
                v_cand_query = v_cand_query.join(me).on(
                    (m.id == me.memory_id) & (me.model_id == active_model_id)
                )
            else:
                distance_expr = RawExpression(f"m.embedding <=> {p_vector}::vector")

            v_cand_query = (
                v_cand_query.left_join(s)
                .on((m.id == s.memory_id) & (s.agent_id == p_agent_id))
                .select(
                    m.payload_ref,
                    m.id.as_("memory_id"),
                    distance_expr.as_("distance"),
                    RawExpression("COALESCE(s.salience_score, 1.0)").as_("raw_salience"),
                    RawExpression("COALESCE(s.updated_at, m.created_at)").as_("last_updated"),
                )
                .where(m.namespace_id == p_namespace_id)
                .where(m.memory_type == "episodic")
                .where(RawExpression("COALESCE(s.salience_score, 1.0) > 0.0"))
            )

            fts_cand_query = (
                Query.from_(m)
                .left_join(s)
                .on((m.id == s.memory_id) & (s.agent_id == p_agent_id))
                .join(RawTable(f"LATERAL websearch_to_tsquery('english', {p_query}) AS query"))
                .on(RawExpression("true"))
                .select(
                    m.payload_ref,
                    m.id.as_("memory_id"),
                    RawExpression("ts_rank_cd(m.content_fts, query)").as_("ts_score"),
                    RawExpression("COALESCE(s.salience_score, 1.0)").as_("raw_salience"),
                    RawExpression("COALESCE(s.updated_at, m.created_at)").as_("last_updated"),
                )
                .where(m.namespace_id == p_namespace_id)
                .where(RawExpression("m.content_fts @@ query"))
                .where(m.memory_type == "episodic")
                .where(RawExpression("COALESCE(s.salience_score, 1.0) > 0.0"))
            )

            if temporal_retention_days is not None:
                p_days = builder.param(int(temporal_retention_days))
                retention_expr = RawExpression(
                    f"m.created_at >= NOW() - ({p_days}::int * INTERVAL '1 day')"
                )
                v_cand_query = v_cand_query.where(retention_expr)
                fts_cand_query = fts_cand_query.where(retention_expr)

            if as_of:
                p_as_of = builder.param(as_of)
                as_of_expr = RawExpression(f"m.created_at <= {p_as_of}")
                v_cand_query = v_cand_query.where(as_of_expr)
                fts_cand_query = fts_cand_query.where(as_of_expr)

            v_cand_query = v_cand_query.orderby(Field("distance")).limit(p_candidate_k)
            fts_cand_query = fts_cand_query.orderby(Field("ts_score"), order=Order.desc).limit(
                p_candidate_k
            )

            vector_candidates = v_cand_query.as_("vector_candidates")
            vector_ranked = (
                Query.from_(Table("vector_candidates")).select(
                    RawExpression("*"),
                    RawExpression("ROW_NUMBER() OVER (ORDER BY distance ASC)").as_("rank"),
                )
            ).as_("vector_ranked")

            fts_candidates = fts_cand_query.as_("fts_candidates")
            fts_ranked = (
                Query.from_(Table("fts_candidates")).select(
                    RawExpression("*"),
                    RawExpression("ROW_NUMBER() OVER (ORDER BY ts_score DESC)").as_("rank"),
                )
            ).as_("fts_ranked")

            v_tbl = Table("vector_ranked").as_("v")
            f_tbl = Table("fts_ranked").as_("f")

            final_query = (
                Query.with_(vector_candidates, "vector_candidates")
                .with_(vector_ranked, "vector_ranked")
                .with_(fts_candidates, "fts_candidates")
                .with_(fts_ranked, "fts_ranked")
                .from_(v_tbl)
                .join(f_tbl, JoinType.full_outer)
                .on(v_tbl.payload_ref == f_tbl.payload_ref)
                .select(
                    RawExpression("COALESCE(v.payload_ref, f.payload_ref)").as_("payload_ref"),
                    RawExpression("COALESCE(v.memory_id, f.memory_id)").as_("memory_id"),
                    RawExpression(
                        "(COALESCE(1.0 / (60 + v.rank), 0.0) + COALESCE(1.0 / (60 + f.rank), 0.0))"
                    ).as_("base_score"),
                    RawExpression("COALESCE(v.raw_salience, f.raw_salience)").as_("raw_salience"),
                    RawExpression("COALESCE(v.last_updated, f.last_updated)").as_("last_updated"),
                )
            )

            rows = await conn.fetch(final_query.get_sql(), *builder.get_params())

            from trimcp.salience import compute_decayed_score, ranking_score, reinforce

            scored_results = []
            for row in rows:
                decayed_salience = compute_decayed_score(
                    s_last=row["raw_salience"],
                    updated_at=row["last_updated"],
                    half_life_days=cognitive_config.half_life_days,
                    memory_id=row["memory_id"],
                )
                final_score = ranking_score(
                    cosine_sim=row["base_score"],
                    salience=decayed_salience,
                    alpha=cognitive_config.alpha,
                )
                scored_results.append(
                    {
                        "payload_ref": row["payload_ref"],
                        "memory_id": row["memory_id"],
                        "score": final_score,
                    }
                )

            scored_results.sort(key=lambda x: x["score"], reverse=True)
            top_results = scored_results[offset : offset + limit]

            for res in top_results:
                await reinforce(
                    conn,
                    str(res["memory_id"]),
                    agent_id,
                    UUID(namespace_id),
                    delta=cognitive_config.reinforcement_delta,
                )

        db = self.mongo_client.memory_archive
        results = []
        for res in top_results:
            doc = await db.episodes.find_one({"_id": ObjectId(res["payload_ref"])})
            if doc:
                results.append(
                    {
                        "memory_id": res["memory_id"],
                        "payload_ref": res["payload_ref"],
                        "score": res["score"],
                        "raw_data": doc.get("raw_data"),
                    }
                )
        return results
