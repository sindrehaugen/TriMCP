"""
Tri-Stack Information Stacking Logic (The Orchestrator)
Implements the Python Saga Pattern for distributed transactions across Redis, Postgres, and MongoDB.
Rollback guarantee: any PG failure triggers Mongo cleanup to prevent orphaned documents.
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator
from motor.motor_asyncio import AsyncIOMotorClient
import asyncpg
import redis.asyncio as redis
from minio import Minio
from trimcp import embeddings as _embeddings
from trimcp.config import cfg, OrchestratorConfig

log = logging.getLogger("tri-stack-orchestrator")

# --- Constants ---

_SAFE_ID_RE = re.compile(r"^[\w\-]{1,128}$")   # alphanumeric, hyphens, underscores
_ALLOWED_LANGUAGES = frozenset({"python", "javascript", "typescript", "go", "rust"})
_MAX_SUMMARY_LEN = 8_192
_MAX_PAYLOAD_LEN = 10 * 1024 * 1024  # 10 MB hard cap
_MAX_TOP_K = 100
_MAX_DEPTH = 3


# --- Pydantic Models ---

class MemoryPayload(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    namespace_id: Optional[str] = None
    agent_id: str = "default"
    content_type: Literal["chat", "code"]
    summary: str = Field(max_length=_MAX_SUMMARY_LEN)
    heavy_payload: str
    metadata: Optional[dict] = None
    assertion_type: str = "fact"
    check_contradictions: bool = False

    @field_validator("user_id", "session_id")
    @classmethod
    def _safe_id(cls, v: str) -> str:
        if not _SAFE_ID_RE.match(v):
            raise ValueError(
                "user_id/session_id must be 1-128 characters: alphanumeric, hyphens, underscores only"
            )
        return v

    @field_validator("heavy_payload")
    @classmethod
    def _payload_size(cls, v: str) -> str:
        if len(v.encode()) > _MAX_PAYLOAD_LEN:
            raise ValueError(f"heavy_payload exceeds {_MAX_PAYLOAD_LEN // 1024 // 1024} MB limit")
        return v


class MediaPayload(BaseModel):
    user_id: str
    session_id: str
    media_type: Literal["audio", "video", "image"]
    file_path_on_disk: str  # Path to the temporary raw file
    summary: str = Field(max_length=_MAX_SUMMARY_LEN)


class CodeChunk(BaseModel):
    filepath: str
    language: str
    node_type: str = Field(description="'function' or 'class'")
    name: str
    code_string: str
    start_line: int
    end_line: int


class VectorRecord(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    embedding: list[float]
    payload_ref: str


class MongoDocument(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    type: str
    raw_data: str
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


# --- Config ---

# --- Engine ---

class TriStackEngine:
    def __init__(self):
        self.mongo_client = None
        self.pg_pool = None
        self.redis_client = None
        self.redis_sync_client = None
        self.minio_client = None  # New Quad-Stack MinIO property
        self._graph_traverser = None

    async def connect(self):
        cfg.validate()
        self.mongo_client = AsyncIOMotorClient(
            cfg.MONGO_URI,
            serverSelectionTimeoutMS=5_000,
        )
        self.pg_pool = await asyncpg.create_pool(
            cfg.PG_DSN,
            min_size=cfg.PG_MIN_POOL,
            max_size=cfg.PG_MAX_POOL,
            command_timeout=30,
        )
        self.redis_client = redis.from_url(
            cfg.REDIS_URL,
            socket_connect_timeout=5,
            socket_timeout=5,
            max_connections=cfg.REDIS_MAX_CONNECTIONS,
            health_check_interval=30,
        )
        # RQ needs a synchronous connection
        import redis as redis_sync
        self.redis_sync_client = redis_sync.from_url(
            cfg.REDIS_URL,
            socket_connect_timeout=5,
            socket_timeout=5,
            max_connections=cfg.REDIS_MAX_CONNECTIONS,
            health_check_interval=30,
        )

        await self._init_pg_schema()
        await self._init_mongo_indexes()

        # Initialize MinIO
        self.minio_client = Minio(
            cfg.MINIO_ENDPOINT,
            access_key=cfg.MINIO_ACCESS_KEY,
            secret_key=cfg.MINIO_SECRET_KEY,
            secure=cfg.MINIO_SECURE
        )

        # Ensure audio/video buckets exist asynchronously
        await asyncio.to_thread(self._init_minio_buckets)

        from trimcp.graph_query import GraphRAGTraverser
        self._graph_traverser = GraphRAGTraverser(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo_client,
            embedding_fn=self._generate_embedding,
        )
        log.info("TriStackEngine connected (Now Quad-Stack with MinIO).")

    async def disconnect(self):
        if self.mongo_client:
            self.mongo_client.close()
        if self.pg_pool:
            await self.pg_pool.close()
        if self.redis_client:
            await self.redis_client.aclose()
        if self.redis_sync_client:
            self.redis_sync_client.close()
        log.info("TriStackEngine disconnected.")

    def _init_minio_buckets(self):
        """Creates default media buckets if they do not exist."""
        buckets = ["mcp-audio", "mcp-video", "mcp-images"]
        for b in buckets:
            if not self.minio_client.bucket_exists(b):
                self.minio_client.make_bucket(b)
                log.debug(f"[MinIO] Created bucket: {b}")

    def _validate_path(self, filepath: str):
        """Strict OS-agnostic path traversal protection."""
        from pathlib import Path
        try:
            # Normalize and resolve to catch '..' and Unix-style absolute paths
            # Note: Path("/etc/shadow").resolve() on Windows might become C:\etc\shadow 
            # if that directory doesn't exist, so we also check raw strings.
            p = Path(filepath).resolve()
            cwd = Path.cwd().resolve()
            
            # 1. Block '..' in absolute paths
            if Path(filepath).is_absolute():
                if any(part == ".." for part in Path(filepath).parts):
                    raise ValueError(f"Path traversal attempt (..) in absolute path: {filepath!r}")
            
            # 2. Block escaping CWD for relative paths
            elif ".." in filepath:
                if not str(p).startswith(str(cwd)):
                    raise ValueError(f"Path traversal attempt (outside CWD): {filepath!r}")

            # 3. Explicitly block leading slashes that imply Unix root
            if filepath.startswith("/") or filepath.startswith("\\") and not (len(filepath) > 1 and filepath[1] == ":"):
                 # This catches /etc/shadow on Windows too if the intent is root-access
                 raise ValueError(f"Absolute path without drive letter denied: {filepath!r}")
                    
            # 4. Deny specific sensitive system paths (heuristic)
            forbidden = {"/etc", "/proc", "/sys", "/dev", "C:\\Windows", "C:\\Users\\Default"}
            for f in forbidden:
                if str(p).startswith(f) or filepath.startswith(f):
                    raise ValueError(f"Access to system path denied: {filepath!r}")

        except (ValueError, RuntimeError) as e:
            raise ValueError(f"Unsafe filepath rejected: {filepath!r} - {e}")

    async def _init_pg_schema(self):
        """
        Load DDL from the package-bundled schema.sql and execute it as a single
        batch. Idempotent — safe to run on every startup. Keeping the schema in
        a sibling .sql file means it can be reviewed as a schema, diffed across
        versions, and fed to migration tools without touching Python.
        """
        from pathlib import Path
        schema_path = Path(__file__).resolve().parent / "schema.sql"
        ddl = schema_path.read_text(encoding="utf-8")
        async with self.pg_pool.acquire() as conn:
            await conn.execute(ddl)
        log.debug("[PG] schema.sql applied from %s", schema_path)

    async def _init_mongo_indexes(self):
        db = self.mongo_client.memory_archive
        await db.episodes.create_index("user_id")
        await db.code_files.create_index("filepath")
        await db.code_files.create_index("user_id")

    async def _generate_embedding(self, text: str) -> list[float]:
        return await _embeddings.embed(text)

    # --- Core Saga: store_memory ---

    async def store_memory(self, payload: MemoryPayload) -> str:
        """
        Saga Pattern: MongoDB → PostgreSQL → Redis.
        PG failure triggers automatic Mongo rollback.
        """
        db = self.mongo_client.memory_archive
        collection = db.episodes
        inserted_mongo_id: Optional[str] = None
        inserted_result = None

        from trimcp.graph_extractor import extract as graph_extract
        from trimcp.pii import process as pii_process
        from trimcp.models import NamespacePIIConfig

        # Fetch namespace PII config (default to empty config if not found or no namespace)
        pii_config = NamespacePIIConfig()
        if payload.metadata and payload.metadata.get("namespace_id"):
            async with self.pg_pool.acquire() as conn:
                ns_row = await conn.fetchrow(
                    "SELECT metadata FROM namespaces WHERE id = $1",
                    payload.metadata["namespace_id"]
                )
                if ns_row and "pii" in ns_row["metadata"]:
                    pii_config = NamespacePIIConfig(**ns_row["metadata"]["pii"])

        # Phase 0.3: PII Redaction Pipeline
        pii_result = pii_process(payload.summary, pii_config)
        sanitized_summary = pii_result.sanitized_text
        
        # Also sanitize the heavy payload if it's text
        sanitized_heavy = payload.heavy_payload
        if isinstance(sanitized_heavy, str):
            sanitized_heavy = pii_process(sanitized_heavy, pii_config).sanitized_text

        entities, triplets = graph_extract(sanitized_summary)

        try:
            # STEP 1: Episodic Commit (MongoDB)
            inserted_result = await collection.insert_one({
                "user_id": payload.user_id,
                "session_id": payload.session_id,
                "type": payload.content_type,
                "raw_data": sanitized_heavy,
                "metadata": payload.metadata,
                "pii_redacted": pii_result.redacted,
                "pii_entities_found": pii_result.entities_found,
                "ingested_at": datetime.utcnow(),
            })
            inserted_mongo_id = str(inserted_result.inserted_id)
            log.debug("[Mongo] Inserted episode. id=%s", inserted_mongo_id)

            # Pre-compute all embeddings OUTSIDE the PG transaction
            all_texts = [sanitized_summary] + [e.label for e in entities]
            all_vectors = await _embeddings.embed_batch(all_texts)
            vector = all_vectors[0]
            node_vecs = all_vectors[1:]


            # Fetch active and migrating models to insert embeddings
            async with self.pg_pool.acquire() as conn:
                models = await conn.fetch("SELECT id FROM embedding_models WHERE status IN ('active', 'migrating')")
                target_model_ids = [m["id"] for m in models]

            # STEP 2 + 2b: Atomic Semantic + Graph Commit (single PG transaction)

            # Either all three tables (memories, kg_nodes, kg_edges) commit,
            # or PG rolls everything back on exception — no partial Saga state.
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    memory_id = await conn.fetchval(
                        """
                        INSERT INTO memories (user_id, session_id, namespace_id, agent_id, embedding, content_fts, payload_ref, pii_redacted, assertion_type)
                        VALUES ($1, $2, $3::uuid, $4, $5::vector, to_tsvector('english', $6), $7, $8, $9)
                        RETURNING id
                        """,
                        payload.user_id, payload.session_id, 
                        payload.namespace_id, payload.agent_id,
                        json.dumps(vector), sanitized_summary, inserted_mongo_id, pii_result.redacted, payload.assertion_type,
                    )
                    
                    # Insert into memory_embeddings for active/migrating models
                    for model_id in target_model_ids:
                        await conn.execute(
                            "INSERT INTO memory_embeddings (memory_id, model_id, embedding) VALUES ($1, $2, $3::vector) ON CONFLICT DO NOTHING",
                            memory_id, model_id, json.dumps(vector)
                        )

                    # Phase 0.3: Insert PII vault entries if any
                    if pii_result.vault_entries and payload.metadata and payload.metadata.get("namespace_id"):
                        ns_id = payload.metadata["namespace_id"]
                        await conn.executemany(
                            """
                            INSERT INTO pii_redactions (namespace_id, memory_id, token, encrypted_value, entity_type)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            [(ns_id, memory_id, v["token"], v["encrypted_value"], v["entity_type"]) for v in pii_result.vault_entries]
                        )

                    for entity, node_vec in zip(entities, node_vecs):
                        await conn.execute(
                            """
                            INSERT INTO kg_nodes (label, entity_type, embedding, payload_ref)
                            VALUES ($1, $2, $3::vector, $4)
                            ON CONFLICT (label) DO UPDATE
                                SET entity_type  = EXCLUDED.entity_type,
                                    embedding    = EXCLUDED.embedding,
                                    payload_ref = EXCLUDED.payload_ref,
                                    updated_at   = NOW()
                            """,
                            entity.label, entity.entity_type,
                            json.dumps(node_vec), inserted_mongo_id,
                        )
                        
                        # Get node_id to insert into kg_node_embeddings
                        node_id = await conn.fetchval("SELECT id FROM kg_nodes WHERE label = $1", entity.label)
                        if node_id:
                            for model_id in target_model_ids:
                                await conn.execute(
                                    "INSERT INTO kg_node_embeddings (node_id, model_id, embedding) VALUES ($1, $2, $3::vector) ON CONFLICT DO NOTHING",
                                    node_id, model_id, json.dumps(node_vec)
                                )
                    for triplet in triplets:
                        await conn.execute(
                            """
                            INSERT INTO kg_edges (subject_label, predicate, object_label, confidence, payload_ref)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (subject_label, predicate, object_label) DO UPDATE
                                SET confidence   = EXCLUDED.confidence,
                                    payload_ref = EXCLUDED.payload_ref,
                                    updated_at   = NOW()
                            """,
                            triplet.subject_label, triplet.predicate, triplet.object_label,
                            triplet.confidence, inserted_mongo_id,
                        )
                    # Phase 2.2: Append to event log for time travel
                    from trimcp.event_log import append_event
                    import uuid
                    
                    # Serialize entities and triplets
                    serialized_entities = [{"label": e.label, "entity_type": e.entity_type} for e in entities]
                    serialized_triplets = [{"subject_label": t.subject_label, "predicate": t.predicate, "object_label": t.object_label, "confidence": t.confidence} for t in triplets]
                    
                    await append_event(
                        conn=conn,
                        namespace_id=uuid.UUID(payload.namespace_id) if isinstance(payload.namespace_id, str) else payload.namespace_id,
                        agent_id=payload.agent_id,
                        event_type="store_memory",
                        params={
                            "memory_id": str(memory_id),
                            "assertion_type": payload.assertion_type.value if hasattr(payload.assertion_type, "value") else str(payload.assertion_type),
                            "entities": serialized_entities,
                            "triplets": serialized_triplets
                        }
                    )

            log.debug("[PG] Atomic commit: vector + %d nodes + %d edges. mongo_ref=%s",
                      len(entities), len(triplets), inserted_mongo_id)

            # STEP 3: Working Memory (Redis)
            redis_key = f"cache:{payload.user_id}:{payload.session_id}"
            await self.redis_client.setex(redis_key, cfg.REDIS_TTL, sanitized_summary)
            log.debug("[Redis] Summary cached. key=%s", redis_key)

            # STEP 4: Phase 1.3 Contradiction Detection
            contradiction_result = None
            if payload.check_contradictions:
                from trimcp.contradictions import detect_contradictions
                try:
                    async with self.pg_pool.acquire() as conn:
                        namespace_id = payload.metadata.get("namespace_id") if payload.metadata else None
                        if namespace_id:
                            contradiction_result = await detect_contradictions(
                                conn=conn,
                                mongo_client=self.mongo_client,
                                namespace_id=namespace_id,
                                memory_id=str(memory_id),
                                memory_text=sanitized_summary,
                                assertion_type=payload.assertion_type.value,
                                embedding=vector,
                                agent_id=payload.agent_id,
                                triplets=triplets,
                                detection_path="sync"
                            )
                except Exception as e:
                    log.error(f"Contradiction detection failed: {e}")

            return {
                "payload_ref": inserted_mongo_id,
                "contradiction": contradiction_result
            }

        except Exception as e:
            log.error("[SAGA] Transaction failed: %s", e)
            if inserted_mongo_id and inserted_result is not None:
                log.warning("[ROLLBACK] Removing orphaned Mongo doc %s", inserted_mongo_id)
                try:
                    await collection.delete_one({"_id": inserted_result.inserted_id})
                except Exception as mongo_exc:
                    log.error("[ROLLBACK] Mongo cleanup failed: %s", mongo_exc)
                # If Step 2+2b committed but Step 3 (Redis) failed, the PG transaction
                # has already flushed — clean the orphaned rows by payload_ref.
                # kg_nodes are intentionally NOT deleted: labels are shared across
                # memories via upsert, so removing them could orphan other sagas.
                try:
                    async with self.pg_pool.acquire() as conn:
                        await conn.execute(
                            "DELETE FROM memories WHERE payload_ref = $1",
                            inserted_mongo_id,
                        )
                        await conn.execute(
                            "DELETE FROM kg_edges WHERE payload_ref = $1",
                            inserted_mongo_id,
                        )
                except Exception as pg_exc:
                    log.error("[ROLLBACK] PG cleanup failed (GC will reap): %s", pg_exc)
                log.info("[ROLLBACK] Tri-Stack remains pure.")
            raise

    async def store_media(self, payload: MediaPayload) -> str:
        """
        Uploads massive media files to MinIO, saves metadata to MongoDB,
        and processes the summary into the PGVector/Knowledge Graph pipelines.
        """
        import os
        import uuid

        if not os.path.exists(payload.file_path_on_disk):
            raise FileNotFoundError(f"Media file not found: {payload.file_path_on_disk}")

        # 1. Upload to MinIO
        bucket_name = f"mcp-{payload.media_type}"
        file_ext = os.path.splitext(payload.file_path_on_disk)[1]
        object_name = f"{payload.session_id}_{uuid.uuid4().hex}{file_ext}"

        # MinIO fput_object is blocking, so we wrap it in a thread
        await asyncio.to_thread(
            self.minio_client.fput_object,
            bucket_name,
            object_name,
            payload.file_path_on_disk
        )
        log.info(f"[MinIO] Uploaded {payload.media_type} to {bucket_name}/{object_name}")

        # 2. Extract MongoDB Metadata
        media_metadata = {
            "bucket": bucket_name,
            "object_name": object_name,
            "media_type": payload.media_type,
            "original_path": payload.file_path_on_disk
        }

        # 3. Create a standard MemoryPayload using the AI-generated summary 
        # and attach the MinIO metadata. Then pipe it through the existing memory pipeline.
        memory_payload = MemoryPayload(
            user_id=payload.user_id,
            session_id=payload.session_id,
            content_type="chat", # Default for media summaries
            summary=payload.summary,  # The summary gets embedded and graphed
            heavy_payload=payload.summary, # Duplicate for consistency in episodic archive
            metadata=media_metadata
        )

        # Reuse existing graph/vector logic
        return await self.store_memory(memory_payload)

    async def force_gc(self) -> dict:
        """Manually trigger a GC pass."""
        from trimcp.garbage_collector import _collect_orphans
        if not self.mongo_client or not self.pg_pool:
            raise RuntimeError("Engine not connected")
        
        result = await _collect_orphans(self.mongo_client, self.pg_pool)
        
        # Check if we purged an abnormally large amount
        total_deleted = result.get("deleted_docs", 0) + result.get("deleted_nodes", 0)
        if total_deleted > 100:
            from trimcp.notifications import dispatcher
            await dispatcher.dispatch_alert("Large GC Purge", f"Manual GC purged {total_deleted} items.")
            
        return result

    async def check_health(self) -> dict:
        """Live non-blocking health checks for all databases."""
        health = {
            "mongo": "down",
            "postgres": "down",
            "redis": "down",
            "rq_queue": "unknown"
        }
        
        # Mongo
        try:
            if self.mongo_client:
                await self.mongo_client.admin.command("ping")
                health["mongo"] = "up"
        except Exception:
            pass
            
        # Postgres
        try:
            if self.pg_pool:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                health["postgres"] = "up"
        except Exception:
            pass
            
        # Redis
        try:
            if self.redis_client:
                await self.redis_client.ping()
                health["redis"] = "up"
        except Exception:
            pass
            
        # RQ Queue
        try:
            if self.redis_sync_client:
                from rq import Queue
                q = Queue(connection=self.redis_sync_client)
                health["rq_queue"] = f"{len(q)} pending jobs"
        except Exception:
            pass

        return health

    # --- Recall ---

    async def recall_memory(self, user_id: str, session_id: str) -> Optional[str]:
        if not _SAFE_ID_RE.match(user_id) or not _SAFE_ID_RE.match(session_id):
            raise ValueError("Invalid user_id or session_id format")

        redis_key = f"cache:{user_id}:{session_id}"
        cached = await self.redis_client.get(redis_key)
        if cached:
            log.debug("[Redis] Cache hit. key=%s", redis_key)
            return cached.decode()

        log.debug("[Redis] Cache miss — querying PG. user=%s session=%s", user_id, session_id)
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT payload_ref FROM memories
                WHERE user_id=$1 AND session_id=$2 AND memory_type='episodic'
                ORDER BY created_at DESC LIMIT 1
                """,
                user_id, session_id,
            )
        if not row:
            return None

        from bson import ObjectId
        db = self.mongo_client.memory_archive
        doc = await db.episodes.find_one({"_id": ObjectId(row["payload_ref"])})
        return str(doc["raw_data"]) if doc else None

    # --- Semantic Search ---

    async def semantic_search(
        self,
        query: str,
        namespace_id: str,
        agent_id: str,
        top_k: int = 5,
        as_of=None,
    ) -> list[dict]:
        top_k = max(1, min(top_k, _MAX_TOP_K))

        # Fetch namespace cognitive config and temporal retention
        from trimcp.models import NamespaceCognitiveConfig
        cognitive_config = NamespaceCognitiveConfig()
        temporal_retention_days = 90
        
        async with self.pg_pool.acquire() as conn:
            ns_row = await conn.fetchrow("SELECT metadata FROM namespaces WHERE id = $1", namespace_id)
            if ns_row:
                meta = ns_row["metadata"]
                if "cognitive" in meta:
                    cognitive_config = NamespaceCognitiveConfig(**meta["cognitive"])
                if "temporal_retention_days" in meta:
                    temporal_retention_days = meta["temporal_retention_days"]

            vector = await self._generate_embedding(query)
            candidate_k = top_k * 4 
            
            # Build temporal filter
            temporal_clause = ""
            if temporal_retention_days is not None:
                temporal_clause = f"AND m.created_at >= NOW() - INTERVAL '{temporal_retention_days} days'"
            if as_of:
                temporal_clause += f" AND m.created_at <= '{as_of.isoformat()}'"

            # Check for active embedding model
            active_model_id = await conn.fetchval("SELECT id FROM embedding_models WHERE status = 'active' LIMIT 1")
            
            if active_model_id:
                distance_expr = "me.embedding <=> $1::vector"
                join_clause = f"JOIN memory_embeddings me ON m.id = me.memory_id AND me.model_id = '{active_model_id}'"
            else:
                distance_expr = "m.embedding <=> $1::vector"
                join_clause = ""

            rows = await conn.fetch(
                f"""
                WITH vector_candidates AS (
                    SELECT 
                        m.payload_ref, 
                        m.id AS memory_id,
                        {distance_expr} AS distance,
                        COALESCE(s.salience_score, 1.0) AS raw_salience,
                        COALESCE(s.updated_at, m.created_at) AS last_updated
                    FROM memories m
                    {join_clause}
                    LEFT JOIN memory_salience s ON m.id = s.memory_id AND s.agent_id = $3
                    WHERE m.namespace_id = $2 AND m.memory_type = 'episodic' {temporal_clause}
                      AND COALESCE(s.salience_score, 1.0) > 0.0
                    ORDER BY distance ASC
                    LIMIT $4
                ),
                vector_ranked AS (
                    SELECT *, ROW_NUMBER() OVER (ORDER BY distance ASC) as rank
                    FROM vector_candidates
                ),
                fts_candidates AS (
                    SELECT 
                        m.payload_ref, 
                        m.id AS memory_id,
                        ts_rank_cd(m.content_fts, query) AS ts_score,
                        COALESCE(s.salience_score, 1.0) AS raw_salience,
                        COALESCE(s.updated_at, m.created_at) AS last_updated
                    FROM memories m
                    LEFT JOIN memory_salience s ON m.id = s.memory_id AND s.agent_id = $3,
                    LATERAL websearch_to_tsquery('english', $5) AS query
                    WHERE m.namespace_id = $2 AND m.content_fts @@ query AND m.memory_type = 'episodic' {temporal_clause}
                      AND COALESCE(s.salience_score, 1.0) > 0.0
                    ORDER BY ts_score DESC
                    LIMIT $4
                ),
                fts_ranked AS (
                    SELECT *, ROW_NUMBER() OVER (ORDER BY ts_score DESC) as rank
                    FROM fts_candidates
                )
                SELECT 
                    COALESCE(v.payload_ref, f.payload_ref) AS payload_ref,
                    COALESCE(v.memory_id, f.memory_id) AS memory_id,
                    (COALESCE(1.0 / (60 + v.rank), 0.0) +
                     COALESCE(1.0 / (60 + f.rank), 0.0)) AS base_score,
                    COALESCE(v.raw_salience, f.raw_salience) AS raw_salience,
                    COALESCE(v.last_updated, f.last_updated) AS last_updated
                FROM vector_ranked v
                FULL OUTER JOIN fts_ranked f ON v.payload_ref = f.payload_ref
                """
                ,
                json.dumps(vector), namespace_id, agent_id, candidate_k, query
            )

            from trimcp.salience import compute_decayed_score, ranking_score, reinforce
            
            scored_results = []
            memory_ids_to_reinforce = []
            
            for row in rows:
                decayed_salience = compute_decayed_score(
                    s_last=row["raw_salience"],
                    updated_at=row["last_updated"],
                    half_life_days=cognitive_config.half_life_days
                )
                final_score = ranking_score(
                    cosine_sim=row["base_score"], # Using RRF base score as the similarity metric
                    salience=decayed_salience,
                    alpha=cognitive_config.alpha
                )
                scored_results.append({
                    "payload_ref": row["payload_ref"],
                    "memory_id": row["memory_id"],
                    "score": final_score,
                })
            
            # Sort by final score and take top_k
            scored_results.sort(key=lambda x: x["score"], reverse=True)
            top_results = scored_results[:top_k]
            
            # Reinforce retrieved memories
            for res in top_results:
                await reinforce(
                    conn, 
                    str(res["memory_id"]), 
                    agent_id, 
                    namespace_id, 
                    delta=cognitive_config.reinforcement_delta
                )

        from bson import ObjectId
        db = self.mongo_client.memory_archive
        results = []
        for res in top_results:
            doc = await db.episodes.find_one({"_id": ObjectId(res["payload_ref"])})
            if doc:
                results.append({
                    "payload_ref": res["payload_ref"],
                    "score": res["score"],
                    "raw_data": doc.get("raw_data"),
                })
        return results

    async def unredact_memory(self, memory_id: str, namespace_id: str, agent_id: str) -> dict:
        """
        [Phase 0.3] MCP Admin Tool: Reverses pseudonymisation for a given memory.
        Requires elevated permissions (handled externally) and reversible=true in policy.
        """
        from trimcp.signing import decrypt_signing_key, require_master_key
        
        master_key = require_master_key()
        
        async with self.pg_pool.acquire() as conn:
            # Check if namespace allows reversibility
            ns_row = await conn.fetchrow("SELECT metadata FROM namespaces WHERE id = $1", namespace_id)
            if not ns_row or "pii" not in ns_row["metadata"] or not ns_row["metadata"]["pii"].get("reversible"):
                raise ValueError("Namespace PII policy does not allow unredaction (reversible=False).")

            # Fetch the memory
            mem_row = await conn.fetchrow("SELECT payload_ref, pii_redacted FROM memories WHERE id = $1", memory_id)
            if not mem_row:
                raise ValueError("Memory not found.")
            
            if not mem_row["pii_redacted"]:
                return {"status": "not_redacted"}

            # Fetch the vault entries
            vault_rows = await conn.fetch(
                "SELECT token, encrypted_value FROM pii_redactions WHERE memory_id = $1",
                memory_id
            )
            
            if not vault_rows:
                return {"status": "no_vault_entries"}

            from bson import ObjectId
            db = self.mongo_client.memory_archive
            doc = await db.episodes.find_one({"_id": ObjectId(mem_row["payload_ref"])})
            if not doc:
                raise ValueError("MongoDB payload missing.")

            raw_data = doc.get("raw_data", "")
            if not isinstance(raw_data, str):
                return {"status": "raw_data_not_string"}

            # Reconstruct
            for v_row in vault_rows:
                token = v_row["token"]
                encrypted_val = v_row["encrypted_value"]
                try:
                    original_val = decrypt_signing_key(encrypted_val, master_key).decode('utf-8')
                    raw_data = raw_data.replace(token, original_val)
                except Exception as e:
                    log.warning("Failed to decrypt token %s: %s", token, e)

            # Log the unredact event
            from trimcp.event_log import append_event
            await append_event(
                conn=conn,
                namespace_id=namespace_id,
                agent_id=agent_id,
                event_type="unredact",
                params={"memory_id": memory_id},
                result_summary={"status": "success", "tokens_unredacted": len(vault_rows)}
            )

            return {
                "status": "success",
                "unredacted_text": raw_data
            }

    # --- Phase 1.1: Cognitive Layer (Salience) ---

    async def boost_memory(self, memory_id: str, agent_id: str, namespace_id: str, factor: float = 0.2) -> dict:
        """
        [Phase 1.1] MCP Tool: Boosts the salience of a memory for the calling agent.
        """
        factor = max(0.0, min(1.0, factor))
        from trimcp.salience import reinforce
        async with self.pg_pool.acquire() as conn:
            await reinforce(conn, memory_id, agent_id, namespace_id, delta=factor)
            
            from trimcp.event_log import append_event
            await append_event(
                conn=conn,
                namespace_id=namespace_id,
                agent_id=agent_id,
                event_type="boost_memory",
                params={"memory_id": memory_id, "factor": factor},
                result_summary={"status": "success"}
            )
        return {"status": "success", "boosted_by": factor}

    async def forget_memory(self, memory_id: str, agent_id: str, namespace_id: str) -> dict:
        """
        [Phase 1.1] MCP Tool: Sets salience to 0.0 for the calling agent.
        """
        async with self.pg_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_salience (memory_id, agent_id, namespace_id, salience_score, updated_at, access_count)
                VALUES ($1::uuid, $2, $3::uuid, 0.0, NOW(), 1)
                ON CONFLICT (memory_id, agent_id) DO UPDATE
                    SET salience_score = 0.0,
                        updated_at = NOW(),
                        access_count = memory_salience.access_count + 1
                """,
                memory_id, agent_id, namespace_id
            )
            
            from trimcp.event_log import append_event
            await append_event(
                conn=conn,
                namespace_id=namespace_id,
                agent_id=agent_id,
                event_type="forget_memory",
                params={"memory_id": memory_id},
                result_summary={"status": "success"}
            )
        return {"status": "success", "forgotten": True}

    # --- Phase 1.3: Contradictions ---

    async def list_contradictions(self, namespace_id: str, resolution: Optional[str] = None, agent_id: Optional[str] = None) -> list[dict]:
        """
        [Phase 1.3] MCP Tool: List contradictions.
        """
        async with self.pg_pool.acquire() as conn:
            query = "SELECT * FROM contradictions WHERE namespace_id = $1::uuid"
            params = [namespace_id]
            idx = 2
            if resolution:
                query += f" AND resolution = ${idx}"
                params.append(resolution)
                idx += 1
            if agent_id:
                query += f" AND agent_id = ${idx}"
                params.append(agent_id)
                idx += 1
                
            query += " ORDER BY detected_at DESC LIMIT 50"
            rows = await conn.fetch(query, *params)
            
            return [dict(r) for r in rows]

    async def resolve_contradiction(self, contradiction_id: str, resolution: str, resolved_by: str, note: Optional[str] = None) -> dict:
        """
        [Phase 1.3] MCP Tool: Resolve a contradiction.
        resolution values: resolved_a | resolved_b | both_valid
        """
        if resolution not in ("resolved_a", "resolved_b", "both_valid"):
            raise ValueError("Invalid resolution value")
            
        async with self.pg_pool.acquire() as conn:
            # We could append an event to the event log here
            await conn.execute(
                """
                UPDATE contradictions
                SET resolution = $1, resolved_at = NOW(), resolved_by = $2
                WHERE id = $3::uuid
                """,
                resolution, resolved_by, contradiction_id
            )
            
            # Fetch namespace_id to log event
            row = await conn.fetchrow("SELECT namespace_id FROM contradictions WHERE id = $1::uuid", contradiction_id)
            if row:
                from trimcp.event_log import append_event
                await append_event(
                    conn=conn,
                    namespace_id=str(row["namespace_id"]),
                    agent_id=resolved_by,
                    event_type="resolve_contradiction",
                    params={"contradiction_id": contradiction_id, "resolution": resolution, "note": note},
                    result_summary={"status": "success"}
                )
                
        return {"status": "success", "resolution": resolution}

    # --- Code Indexing ---

    async def index_code_file(
        self,
        filepath: str,
        raw_code: str,
        language: str,
        *,
        user_id: Optional[str] = None,
        private: bool = False,
    ) -> dict:
        """
        Offloads indexing to a background worker via RQ.
        Returns a job_id immediately.
        Shared corpus (default): chunks are stored with user_id IS NULL in Postgres.
        private=True: requires user_id; chunks and Mongo docs are scoped to that user.
        """
        # Input validation
        if language not in _ALLOWED_LANGUAGES:
            raise ValueError(f"Unsupported language '{language}'. Allowed: {sorted(_ALLOWED_LANGUAGES)}")

        if private:
            if not user_id:
                raise ValueError("private indexing requires user_id")
            if not _SAFE_ID_RE.match(user_id):
                raise ValueError("Invalid user_id format")
        elif user_id is not None and not _SAFE_ID_RE.match(user_id):
            raise ValueError("Invalid user_id format")

        self._validate_path(filepath)

        if len(raw_code.encode()) > _MAX_PAYLOAD_LEN:
            raise ValueError(f"raw_code exceeds {_MAX_PAYLOAD_LEN // 1024 // 1024} MB limit")

        import hashlib
        file_hash = hashlib.md5(raw_code.encode()).hexdigest()

        scope_user = user_id if private else None
        scope_key = f"private:{scope_user}" if scope_user else "shared"

        # Quick check for skip (sync)
        cached_hash = await self.redis_client.get(f"hash:{scope_key}:{filepath}")
        if cached_hash and cached_hash.decode() == file_hash:
            return {"status": "skipped", "reason": "unchanged", "filepath": filepath}

        # Enqueue the task
        from rq import Queue
        from trimcp.tasks import process_code_indexing
        
        q = Queue(connection=self.redis_sync_client)
        job = q.enqueue(
            process_code_indexing,
            args=(filepath, raw_code, language, scope_user),
            job_timeout='10m'
        )
        
        log.info("[Code] Enqueued indexing job %s for %s", job.id, filepath)
        return {
            "status": "enqueued",
            "job_id": job.id,
            "filepath": filepath
        }

    async def get_job_status(self, job_id: str) -> dict:
        """Checks the status of an RQ job."""
        from rq.job import Job
        try:
            job = await asyncio.to_thread(Job.fetch, job_id, connection=self.redis_sync_client)
            return {
                "job_id": job_id,
                "status": job.get_status(),
                "result": job.result if job.is_finished else None,
                "error": str(job.exc_info) if job.is_failed else None
            }
        except Exception as e:
            return {"job_id": job_id, "status": "not_found", "error": str(e)}

    # --- Graph Search ---

    async def graph_search(
        self,
        query: str,
        namespace_id: str = None,
        max_depth: int = 2,
        top_k_anchors: int = 3,
        restrict_user_id: Optional[str] = None,
        as_of=None,
    ) -> dict:
        if self._graph_traverser is None:
            raise RuntimeError("Engine not connected — call connect() first")
        max_depth = max(1, min(max_depth, _MAX_DEPTH))
        subgraph = await self._graph_traverser.search(
            query,
            namespace_id=namespace_id,
            max_depth=max_depth,
            anchor_top_k=top_k_anchors,
            user_id=restrict_user_id,
            private=bool(restrict_user_id),
            as_of=as_of
        )
        return subgraph.to_dict()

    # --- Codebase Search ---

    async def search_codebase(
        self,
        query: str,
        language_filter: Optional[str] = None,
        top_k: int = 5,
        *,
        user_id: Optional[str] = None,
        private: bool = False,
    ) -> list[dict]:
        top_k = max(1, min(top_k, _MAX_TOP_K))
        if language_filter and language_filter not in _ALLOWED_LANGUAGES:
            raise ValueError(f"Invalid language_filter '{language_filter}'")
        if private:
            if not user_id or not _SAFE_ID_RE.match(user_id):
                raise ValueError("private codebase search requires valid user_id")
        elif user_id is not None and not _SAFE_ID_RE.match(user_id):
            raise ValueError("Invalid user_id format")

        vector = await self._generate_embedding(query)
        candidate_k = top_k * 4
        
        async with self.pg_pool.acquire() as conn:
            # Shared (default): only rows with user_id IS NULL. Private: scoped to user_id.
            if private:
                scope_clause = "AND user_id = $5"
                query_params: list = [json.dumps(vector), candidate_k, query, top_k, user_id]
                next_i = 6
            else:
                scope_clause = "AND user_id IS NULL"
                query_params = [json.dumps(vector), candidate_k, query, top_k]
                next_i = 5

            lang_clause = f"AND language = ${next_i}" if language_filter else ""
            if language_filter:
                query_params.append(language_filter)

            sql = f"""
                WITH vector_candidates AS (
                    SELECT id, embedding <=> $1::vector AS distance
                    FROM memories
                    WHERE memory_type = 'code_chunk' {scope_clause} {lang_clause}
                    ORDER BY distance ASC
                    LIMIT $2
                ),
                vector_ranked AS (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY distance ASC) as rank
                    FROM vector_candidates
                ),
                fts_candidates AS (
                    SELECT id, ts_rank_cd(content_fts, query) AS ts_score
                    FROM memories, 
                    LATERAL websearch_to_tsquery('english', $3) AS query
                    WHERE content_fts @@ query AND memory_type = 'code_chunk' {scope_clause} {lang_clause}
                    ORDER BY ts_score DESC
                    LIMIT $2
                ),
                fts_ranked AS (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY ts_score DESC) as rank
                    FROM fts_candidates
                )
                SELECT 
                    COALESCE(v.id, f.id) AS id,
                    (COALESCE(1.0 / (60 + v.rank), 0.0) +
                     COALESCE(1.0 / (60 + f.rank), 0.0)) AS score
                FROM vector_ranked v
                FULL OUTER JOIN fts_ranked f ON v.id = f.id
                ORDER BY score DESC
                LIMIT $4
            """
            
            fused_rows = await conn.fetch(sql, *query_params)
            
            if not fused_rows:
                return []

            # Fetch full metadata for the winner IDs
            ids = [r["id"] for r in fused_rows]
            rows = await conn.fetch(
                """
                SELECT id, filepath, language, node_type, name, start_line, end_line, payload_ref
                FROM memories
                WHERE id = ANY($1::uuid[])
                """,
                ids,
            )
            # Map back to scores and preserve order
            row_map = {r["id"]: r for r in rows}
            results_ordered = []
            for fr in fused_rows:
                r = row_map.get(fr["id"])
                if r:
                    results_ordered.append({
                        "filepath": r["filepath"],
                        "language": r["language"],
                        "node_type": r["node_type"],
                        "name": r["name"],
                        "start_line": r["start_line"],
                        "end_line": r["end_line"],
                        "score": fr["score"],
                        "payload_ref": r["payload_ref"],
                    })

        from bson import ObjectId
        db = self.mongo_client.memory_archive
        final_results = []
        for res in results_ordered:
            doc = await db.code_files.find_one({"_id": ObjectId(res["payload_ref"])})
            res["raw_code_preview"] = doc["raw_code"][:500] if doc else None
            final_results.append(res)
            
        return final_results


# --- Dev test harness (not executed in production) ---

async def _test():
    logging.basicConfig(level=logging.DEBUG)
    engine = TriStackEngine()
    await engine.connect()
    payload = MemoryPayload(
        user_id="dev_user_1",
        session_id="session_alpha",
        content_type="chat",
        summary="User is setting up a Tri-Stack DB architecture with Docker.",
        heavy_payload="... raw chat transcript placeholder ...",
    )
    try:
        mid = await engine.store_memory(payload)
        log.info("Stored. mongo_id=%s", mid)
    finally:
        await engine.disconnect()


if __name__ == "__main__":
    asyncio.run(_test())

    # --- Phase 2.1: Re-embedding Migrations ---

    async def start_migration(self, target_model_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            # Check if model exists
            model = await conn.fetchrow("SELECT id FROM embedding_models WHERE id = $1::uuid", target_model_id)
            if not model:
                raise ValueError("Target model not found")
            
            # Check if there's already a running migration
            active = await conn.fetchrow("SELECT id FROM embedding_migrations WHERE status IN ('running', 'validating')")
            if active:
                raise ValueError(f"Migration {active['id']} is already in progress")
            
            await conn.execute("UPDATE embedding_models SET status = 'migrating' WHERE id = $1::uuid", target_model_id)
            
            mig_id = await conn.fetchval(
                "INSERT INTO embedding_migrations (target_model_id) VALUES ($1::uuid) RETURNING id",
                target_model_id
            )
            return {"migration_id": str(mig_id), "status": "running"}

    async def migration_status(self, migration_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, target_model_id, status, last_memory_id, last_node_id, started_at, completed_at FROM embedding_migrations WHERE id = $1::uuid",
                migration_id
            )
            if not row:
                raise ValueError("Migration not found")
            return dict(row)

    async def validate_migration(self, migration_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT status, target_model_id FROM embedding_migrations WHERE id = $1::uuid", migration_id)
            if not row or row["status"] != "validating":
                raise ValueError("Migration not found or not in validating state")
                
            # Quality gate: Check if counts match
            mem_count = await conn.fetchval("SELECT count(*) FROM memories")
            emb_count = await conn.fetchval("SELECT count(*) FROM memory_embeddings WHERE model_id = $1::uuid", row["target_model_id"])
            
            if emb_count < mem_count:
                return {"status": "failed", "reason": f"Missing memory embeddings: {mem_count} memories, {emb_count} embeddings"}
                
            return {"status": "passed", "message": "All memories and nodes have been embedded"}

    async def commit_migration(self, migration_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT status, target_model_id FROM embedding_migrations WHERE id = $1::uuid", migration_id)
                if not row or row["status"] != "validating":
                    raise ValueError("Migration not ready to commit")
                    
                target_model_id = row["target_model_id"]
                
                # Retire old active models
                await conn.execute("UPDATE embedding_models SET status = 'retired', retired_at = now() WHERE status = 'active'")
                
                # Set new model to active
                await conn.execute("UPDATE embedding_models SET status = 'active' WHERE id = $1::uuid", target_model_id)
                
                # Mark migration as committed
                await conn.execute("UPDATE embedding_migrations SET status = 'committed', completed_at = now() WHERE id = $1::uuid", migration_id)
                
                return {"status": "committed", "active_model_id": str(target_model_id)}

    async def abort_migration(self, migration_id: str) -> dict:
        async with self.pg_pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT target_model_id FROM embedding_migrations WHERE id = $1::uuid", migration_id)
                if not row:
                    raise ValueError("Migration not found")
                    
                target_model_id = row["target_model_id"]
                
                await conn.execute("UPDATE embedding_migrations SET status = 'aborted', completed_at = now() WHERE id = $1::uuid", migration_id)
                
                # We don't necessarily delete the embeddings, they might be useful, 
                # but we set the model status back to retired or pending
                await conn.execute("UPDATE embedding_models SET status = 'retired' WHERE id = $1::uuid", target_model_id)
                
                return {"status": "aborted"}
