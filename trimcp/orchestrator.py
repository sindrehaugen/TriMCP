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
from trimcp import embeddings as _embeddings
from trimcp.config import cfg, OrchestratorConfig

log = logging.getLogger("tri-stack-orchestrator")

# --- Constants ---

_SAFE_ID_RE = re.compile(r"^[\w\-]{1,128}$")   # alphanumeric, hyphens, underscores
_ALLOWED_LANGUAGES = frozenset({"python", "javascript"})
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
        await self._init_pg_schema()
        await self._init_mongo_indexes()
        from trimcp.graph_query import GraphRAGTraverser
        self._graph_traverser = GraphRAGTraverser(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo_client,
            embedding_fn=self._generate_embedding,
        )
        log.info("TriStackEngine connected (PG pool: %d-%d, Redis max: %d).",
                 cfg.PG_MIN_POOL,
                 cfg.PG_MAX_POOL,
                 cfg.REDIS_MAX_CONNECTIONS)

    async def disconnect(self):
        if self.mongo_client:
            self.mongo_client.close()
        if self.pg_pool:
            await self.pg_pool.close()
        if self.redis_client:
            await self.redis_client.aclose()
        log.info("TriStackEngine disconnected.")

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
                "ingested_at": datetime.utcnow(),
            })
            inserted_mongo_id = str(inserted_result.inserted_id)
            log.debug("[Mongo] Inserted episode. id=%s", inserted_mongo_id)

            # Pre-compute all embeddings OUTSIDE the PG transaction so we don't
            # hold a pooled connection open during CPU-bound inference.
            vector = await self._generate_embedding(payload.summary)
            node_vecs = [await self._generate_embedding(e.label) for e in entities]

            # STEP 2 + 2b: Atomic Semantic + Graph Commit (single PG transaction)
            # Either all three tables (memory_metadata, kg_nodes, kg_edges) commit,
            # or PG rolls everything back on exception — no partial Saga state.
            async with self.pg_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO memory_metadata (user_id, session_id, embedding, mongo_ref_id)
                        VALUES ($1, $2, $3::vector, $4)
                        """,
                        payload.user_id, payload.session_id,
                        json.dumps(vector), inserted_mongo_id,
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
        async with self.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT mongo_ref_id, embedding <=> $1::vector AS distance
                FROM memory_metadata
                WHERE user_id = $2
                ORDER BY distance ASC
                LIMIT $3
                """,
                json.dumps(vector), user_id, top_k,
            )

        from bson import ObjectId
        db = self.mongo_client.memory_archive
        results = []
        for row in rows:
            doc = await db.episodes.find_one({"_id": ObjectId(row["mongo_ref_id"])})
            if doc:
                results.append({
                    "mongo_ref_id": row["mongo_ref_id"],
                    "distance": row["distance"],
                    "raw_data": doc.get("raw_data"),
                })
        return results

    # --- Code Indexing ---

    async def index_code_file(self, filepath: str, raw_code: str, language: str) -> dict:
        """
        Saga: archive full file in MongoDB, embed each AST chunk in PG code_metadata.
        Skips re-indexing if MD5 hash is unchanged.
        """
        # Input validation
        if language not in _ALLOWED_LANGUAGES:
            raise ValueError(f"Unsupported language '{language}'. Allowed: {sorted(_ALLOWED_LANGUAGES)}")
        if ".." in filepath or filepath.startswith("/etc") or filepath.startswith("/proc"):
            raise ValueError(f"Unsafe filepath rejected: {filepath!r}")
        if len(raw_code.encode()) > _MAX_PAYLOAD_LEN:
            raise ValueError(f"raw_code exceeds {_MAX_PAYLOAD_LEN // 1024 // 1024} MB limit")

        import hashlib
        from trimcp.ast_parser import parse_file

        file_hash = hashlib.md5(raw_code.encode()).hexdigest()

        cached_hash = await self.redis_client.get(f"hash:{filepath}")
        if cached_hash and cached_hash.decode() == file_hash:
            return {"status": "skipped", "reason": "unchanged", "filepath": filepath}

        db = self.mongo_client.memory_archive
        collection = db.code_files
        inserted_result = None
        inserted_mongo_id: Optional[str] = None

        try:
            # STEP 1: Episodic Commit
            inserted_result = await collection.insert_one({
                "filepath": filepath,
                "language": language,
                "file_hash": file_hash,
                "raw_code": raw_code,
                "ingested_at": datetime.utcnow(),
            })
            inserted_mongo_id = str(inserted_result.inserted_id)

            # STEP 2: Batch-embed all AST chunks
            chunks = list(parse_file(raw_code, language))
            texts = [f"{c.name}\n{c.code_string}" for c in chunks]
            vectors = await _embeddings.embed_batch(texts)

            async with self.pg_pool.acquire() as conn:
                await conn.execute("DELETE FROM code_metadata WHERE filepath = $1", filepath)
                for chunk, vector in zip(chunks, vectors):
                    await conn.execute(
                        """
                        INSERT INTO code_metadata
                            (filepath, language, node_type, name, start_line, end_line,
                             file_hash, embedding, mongo_ref_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, $9)
                        """,
                        filepath, language, chunk.node_type, chunk.name,
                        chunk.start_line, chunk.end_line,
                        file_hash, json.dumps(vector), inserted_mongo_id,
                    )

            # STEP 3: Cache hash
            await self.redis_client.setex(
                f"hash:{filepath}", cfg.REDIS_TTL, file_hash
            )
            log.info("[Code] Indexed %d chunks from %s", len(chunks), filepath)
            return {
                "status": "indexed",
                "filepath": filepath,
                "chunks": len(chunks),
                "mongo_ref_id": inserted_mongo_id,
            }

        except Exception as e:
            log.error("[SAGA] index_code_file failed: %s", e)
            if inserted_mongo_id and inserted_result is not None:
                await collection.delete_one({"_id": inserted_result.inserted_id})
                log.warning("[ROLLBACK] Orphaned code file removed from MongoDB.")
            raise

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
        async with self.pg_pool.acquire() as conn:
            if language_filter:
                rows = await conn.fetch(
                    """
                    SELECT filepath, language, node_type, name, start_line, end_line, mongo_ref_id,
                           embedding <=> $1::vector AS distance
                    FROM code_metadata
                    WHERE language = $2
                    ORDER BY distance ASC LIMIT $3
                    """,
                    json.dumps(vector), language_filter, top_k,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT filepath, language, node_type, name, start_line, end_line, mongo_ref_id,
                           embedding <=> $1::vector AS distance
                    FROM code_metadata
                    ORDER BY distance ASC LIMIT $2
                    """,
                    json.dumps(vector), top_k,
                )

        from bson import ObjectId
        db = self.mongo_client.memory_archive
        results = []
        for row in rows:
            doc = await db.code_files.find_one({"_id": ObjectId(row["mongo_ref_id"])})
            results.append({
                "filepath": row["filepath"],
                "language": row["language"],
                "node_type": row["node_type"],
                "name": row["name"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "distance": row["distance"],
                "raw_code_preview": doc["raw_code"][:500] if doc else None,
            })
        return results


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
