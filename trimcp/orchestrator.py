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
    user_id: str
    session_id: str
    content_type: Literal["chat", "code"]
    summary: str = Field(max_length=_MAX_SUMMARY_LEN)
    heavy_payload: str
    metadata: Optional[dict] = None

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
    mongo_ref_id: str


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
        entities, triplets = graph_extract(payload.summary)

        try:
            # STEP 1: Episodic Commit (MongoDB)
            inserted_result = await collection.insert_one({
                "user_id": payload.user_id,
                "session_id": payload.session_id,
                "type": payload.content_type,
                "raw_data": payload.heavy_payload,
                "metadata": payload.metadata,
                "ingested_at": datetime.utcnow(),
            })
            inserted_mongo_id = str(inserted_result.inserted_id)
            log.debug("[Mongo] Inserted episode. id=%s", inserted_mongo_id)

            # Pre-compute all embeddings OUTSIDE the PG transaction
            all_texts = [payload.summary] + [e.label for e in entities]
            all_vectors = await _embeddings.embed_batch(all_texts)
            vector = all_vectors[0]
            node_vecs = all_vectors[1:]

            # STEP 2 + 2b: Atomic Semantic + Graph Commit (single PG transaction)
            # Either all three tables (memory_metadata, kg_nodes, kg_edges) commit,
            # or PG rolls everything back on exception — no partial Saga state.
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO memory_metadata (user_id, session_id, embedding, content_fts, mongo_ref_id)
                        VALUES ($1, $2, $3::vector, to_tsvector('english', $4), $5)
                        """,
                        payload.user_id, payload.session_id,
                        json.dumps(vector), payload.summary, inserted_mongo_id,
                    )
                    for entity, node_vec in zip(entities, node_vecs):
                        await conn.execute(
                            """
                            INSERT INTO kg_nodes (label, entity_type, embedding, mongo_ref_id)
                            VALUES ($1, $2, $3::vector, $4)
                            ON CONFLICT (label) DO UPDATE
                                SET entity_type  = EXCLUDED.entity_type,
                                    embedding    = EXCLUDED.embedding,
                                    mongo_ref_id = EXCLUDED.mongo_ref_id,
                                    updated_at   = NOW()
                            """,
                            entity.label, entity.entity_type,
                            json.dumps(node_vec), inserted_mongo_id,
                        )
                    for triplet in triplets:
                        await conn.execute(
                            """
                            INSERT INTO kg_edges (subject_label, predicate, object_label, confidence, mongo_ref_id)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (subject_label, predicate, object_label) DO UPDATE
                                SET confidence   = EXCLUDED.confidence,
                                    mongo_ref_id = EXCLUDED.mongo_ref_id,
                                    updated_at   = NOW()
                            """,
                            triplet.subject, triplet.predicate, triplet.obj,
                            triplet.confidence, inserted_mongo_id,
                        )
            log.debug("[PG] Atomic commit: vector + %d nodes + %d edges. mongo_ref=%s",
                      len(entities), len(triplets), inserted_mongo_id)

            # STEP 3: Working Memory (Redis)
            redis_key = f"cache:{payload.user_id}:{payload.session_id}"
            await self.redis_client.setex(redis_key, cfg.REDIS_TTL, payload.summary)
            log.debug("[Redis] Summary cached. key=%s", redis_key)

            return inserted_mongo_id

        except Exception as e:
            log.error("[SAGA] Transaction failed: %s", e)
            if inserted_mongo_id and inserted_result is not None:
                log.warning("[ROLLBACK] Removing orphaned Mongo doc %s", inserted_mongo_id)
                try:
                    await collection.delete_one({"_id": inserted_result.inserted_id})
                except Exception as mongo_exc:
                    log.error("[ROLLBACK] Mongo cleanup failed: %s", mongo_exc)
                # If Step 2+2b committed but Step 3 (Redis) failed, the PG transaction
                # has already flushed — clean the orphaned rows by mongo_ref_id.
                # kg_nodes are intentionally NOT deleted: labels are shared across
                # memories via upsert, so removing them could orphan other sagas.
                try:
                    async with self.pg_pool.acquire() as conn:
                        await conn.execute(
                            "DELETE FROM memory_metadata WHERE mongo_ref_id = $1",
                            inserted_mongo_id,
                        )
                        await conn.execute(
                            "DELETE FROM kg_edges WHERE mongo_ref_id = $1",
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
                SELECT mongo_ref_id FROM memory_metadata
                WHERE user_id=$1 AND session_id=$2
                ORDER BY created_at DESC LIMIT 1
                """,
                user_id, session_id,
            )
        if not row:
            return None

        from bson import ObjectId
        db = self.mongo_client.memory_archive
        doc = await db.episodes.find_one({"_id": ObjectId(row["mongo_ref_id"])})
        return str(doc["raw_data"]) if doc else None

    # --- Semantic Search ---

    async def semantic_search(self, user_id: str, query: str, top_k: int = 5) -> list[dict]:
        if not _SAFE_ID_RE.match(user_id):
            raise ValueError("Invalid user_id format")
        top_k = max(1, min(top_k, _MAX_TOP_K))

        vector = await self._generate_embedding(query)
        # Hybrid Search (RRF): Combine pgvector and Full Text Search
        # We fetch more candidates from each and then fuse them.
        candidate_k = top_k * 4 
        async with self.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH vector_candidates AS (
                    SELECT mongo_ref_id, embedding <=> $1::vector AS distance
                    FROM memory_metadata
                    WHERE user_id = $2
                    ORDER BY distance ASC
                    LIMIT $3
                ),
                vector_ranked AS (
                    SELECT mongo_ref_id, ROW_NUMBER() OVER (ORDER BY distance ASC) as rank
                    FROM vector_candidates
                ),
                fts_candidates AS (
                    SELECT mongo_ref_id, ts_rank_cd(content_fts, query) AS ts_score
                    FROM memory_metadata, 
                    LATERAL websearch_to_tsquery('english', $4) AS query
                    WHERE user_id = $2 AND content_fts @@ query
                    ORDER BY ts_score DESC
                    LIMIT $3
                ),
                fts_ranked AS (
                    SELECT mongo_ref_id, ROW_NUMBER() OVER (ORDER BY ts_score DESC) as rank
                    FROM fts_candidates
                )
                SELECT 
                    COALESCE(v.mongo_ref_id, f.mongo_ref_id) AS mongo_ref_id,
                    (COALESCE(1.0 / (60 + v.rank), 0.0) +
                     COALESCE(1.0 / (60 + f.rank), 0.0)) AS score
                FROM vector_ranked v
                FULL OUTER JOIN fts_ranked f ON v.mongo_ref_id = f.mongo_ref_id
                ORDER BY score DESC
                LIMIT $5
                """,
                json.dumps(vector), user_id, candidate_k, query, top_k,
            )

        from bson import ObjectId
        db = self.mongo_client.memory_archive
        results = []
        for row in rows:
            doc = await db.episodes.find_one({"_id": ObjectId(row["mongo_ref_id"])})
            if doc:
                results.append({
                    "mongo_ref_id": row["mongo_ref_id"],
                    "score": row["score"],
                    "raw_data": doc.get("raw_data"),
                })
        return results

    # --- Code Indexing ---

    async def index_code_file(self, filepath: str, raw_code: str, language: str) -> dict:
        """
        Offloads indexing to a background worker via RQ.
        Returns a job_id immediately.
        """
        # Input validation
        if language not in _ALLOWED_LANGUAGES:
            raise ValueError(f"Unsupported language '{language}'. Allowed: {sorted(_ALLOWED_LANGUAGES)}")

        self._validate_path(filepath)

        if len(raw_code.encode()) > _MAX_PAYLOAD_LEN:
            raise ValueError(f"raw_code exceeds {_MAX_PAYLOAD_LEN // 1024 // 1024} MB limit")

        import hashlib
        file_hash = hashlib.md5(raw_code.encode()).hexdigest()

        # Quick check for skip (sync)
        cached_hash = await self.redis_client.get(f"hash:{filepath}")
        if cached_hash and cached_hash.decode() == file_hash:
            return {"status": "skipped", "reason": "unchanged", "filepath": filepath}

        # Enqueue the task
        from rq import Queue
        from trimcp.tasks import process_code_indexing
        
        q = Queue(connection=self.redis_sync_client)
        job = q.enqueue(
            process_code_indexing,
            args=(filepath, raw_code, language),
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

    async def graph_search(self, query: str, max_depth: int = 2) -> dict:
        if self._graph_traverser is None:
            raise RuntimeError("Engine not connected — call connect() first")
        max_depth = max(1, min(max_depth, _MAX_DEPTH))
        subgraph = await self._graph_traverser.search(query, max_depth=max_depth)
        return subgraph.to_dict()

    # --- Codebase Search ---

    async def search_codebase(
        self, query: str, language_filter: Optional[str] = None, top_k: int = 5
    ) -> list[dict]:
        top_k = max(1, min(top_k, _MAX_TOP_K))
        if language_filter and language_filter not in _ALLOWED_LANGUAGES:
            raise ValueError(f"Invalid language_filter '{language_filter}'")

        vector = await self._generate_embedding(query)
        candidate_k = top_k * 4
        
        async with self.pg_pool.acquire() as conn:
            # We handle language_filter by injecting it into both CTEs
            lang_clause = "AND language = $5" if language_filter else ""
            query_params = [json.dumps(vector), candidate_k, query, top_k]
            if language_filter:
                query_params.append(language_filter)

            sql = f"""
                WITH vector_candidates AS (
                    SELECT id, embedding <=> $1::vector AS distance
                    FROM code_metadata
                    WHERE 1=1 {lang_clause}
                    ORDER BY distance ASC
                    LIMIT $2
                ),
                vector_ranked AS (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY distance ASC) as rank
                    FROM vector_candidates
                ),
                fts_candidates AS (
                    SELECT id, ts_rank_cd(content_fts, query) AS ts_score
                    FROM code_metadata, 
                    LATERAL websearch_to_tsquery('english', $3) AS query
                    WHERE content_fts @@ query {lang_clause}
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
                SELECT id, filepath, language, node_type, name, start_line, end_line, mongo_ref_id
                FROM code_metadata
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
                        "mongo_ref_id": r["mongo_ref_id"],
                    })

        from bson import ObjectId
        db = self.mongo_client.memory_archive
        final_results = []
        for res in results_ordered:
            doc = await db.code_files.find_one({"_id": ObjectId(res["mongo_ref_id"])})
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
