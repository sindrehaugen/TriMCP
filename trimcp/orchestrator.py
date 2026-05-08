"""
Tri-Stack Information Stacking Logic (The Orchestrator)
Implements the Python Saga Pattern for distributed transactions across Redis, Postgres, and MongoDB.
Rollback guarantee: any PG failure triggers Mongo cleanup to prevent orphaned documents.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
import redis.asyncio as redis
from minio import Minio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from trimcp import embeddings as _embeddings
from trimcp.config import cfg
from trimcp.models import (
    CompareStatesRequest,
    CreateSnapshotRequest,
    GraphSearchRequest,
    IndexCodeFileRequest,
    ManageNamespaceRequest,
    ManageQuotasRequest,
    MediaPayload,
    SnapshotRecord,
    StateDiffResult,
    StoreMemoryRequest,
)

# Backward-compat alias — MemoryPayload was renamed to StoreMemoryRequest
MemoryPayload = StoreMemoryRequest

log = logging.getLogger("tri-stack-orchestrator")

# --- Constants ---

_SAFE_ID_RE = re.compile(r"^[\w\-]{1,128}$")  # alphanumeric, hyphens, underscores
_ALLOWED_LANGUAGES = frozenset({"python", "javascript", "typescript", "go", "rust"})
_MAX_SUMMARY_LEN = 8_192
_MAX_PAYLOAD_LEN = 10 * 1024 * 1024  # 10 MB hard cap
_MAX_TOP_K = 100
_MAX_DEPTH = 3


def _metadata_as_dict(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return dict(raw)


def _shallow_metadata_delta(old: dict[str, Any], new: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Keys added or with changed JSON-serializable values (string compare)."""
    delta: dict[str, dict[str, Any]] = {}
    for k, nv in new.items():
        ov = old.get(k)
        if ov != nv:
            delta[k] = {"from": ov, "to": nv}
    for k, ov in old.items():
        if k not in new:
            delta[k] = {"from": ov, "to": None}
    return delta


def _build_lineage_modified(old_row: Any, new_row: Any) -> dict[str, Any]:
    keys = ("assertion_type", "memory_type", "pii_redacted", "salience")
    transitions: dict[str, dict[str, Any]] = {}
    for k in keys:
        o, n = old_row[k], new_row[k]
        if k == "salience":
            o = float(o) if o is not None else None
            n = float(n) if n is not None else None
        if o != n:
            transitions[k] = {"from": o, "to": n}
    mo = _metadata_as_dict(old_row["metadata"])
    mn = _metadata_as_dict(new_row["metadata"])
    return {
        "kind": "lineage_linked",
        "source_memory_id": str(old_row["memory_id"]),
        "old_memory_id": str(old_row["memory_id"]),
        "new_memory_id": str(new_row["memory_id"]),
        "transitions": transitions,
        "metadata_delta": _shallow_metadata_delta(mo, mn),
    }


def _lineage_source_id(row: Mapping[str, Any]) -> str | None:
    """Primitive linked to a predecessor: replay ``metadata.source_memory_id`` or consolidation ``derived_from[0]``."""
    meta = _metadata_as_dict(row.get("metadata"))
    sid = meta.get("source_memory_id")
    if sid:
        return str(sid)
    df = row.get("derived_from")
    if df is None:
        return None
    if isinstance(df, str):
        try:
            df = json.loads(df)
        except json.JSONDecodeError:
            return None
    if isinstance(df, (list, tuple)) and len(df) > 0:
        return str(df[0])
    return None


# --- Pydantic Models (Internal only) ---


class CodeChunk(BaseModel):
    filepath: str
    language: str
    node_type: str = Field(description="'function' or 'class'")
    name: str
    code_string: str
    start_line: int
    end_line: int


class VectorRecord(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    embedding: list[float]
    payload_ref: str


class MongoDocument(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    type: str
    raw_data: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
        # Domain orchestrators (created in connect())
        self.memory: object | None = None  # MemoryOrchestrator
        self.graph: object | None = None  # GraphOrchestrator
        self.temporal: object | None = None  # TemporalOrchestrator
        self.namespace: object | None = None  # NamespaceOrchestrator
        self.cognitive: object | None = None  # CognitiveOrchestrator
        self.migration: object | None = None  # MigrationOrchestrator

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
        await self._verify_worm_enforcement()
        await self._verify_rls_enforcement()
        await self._check_global_legacy_warning()
        await self._init_mongo_indexes()

        # Initialize MinIO
        self.minio_client = Minio(
            cfg.MINIO_ENDPOINT,
            access_key=cfg.MINIO_ACCESS_KEY,
            secret_key=cfg.MINIO_SECRET_KEY,
            secure=cfg.MINIO_SECURE,
        )

        # Ensure audio/video buckets exist asynchronously
        await asyncio.to_thread(self._init_minio_buckets)

        from trimcp.graph_query import GraphRAGTraverser

        self._graph_traverser = GraphRAGTraverser(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo_client,
            embedding_fn=self._generate_embedding,
        )

        # --- Domain Orchestrators ---
        from trimcp.orchestrators.memory import MemoryOrchestrator

        self.memory = MemoryOrchestrator(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo_client,
            redis_client=self.redis_client,
            minio_client=self.minio_client,
        )
        from trimcp.orchestrators.graph import GraphOrchestrator

        self.graph = GraphOrchestrator(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo_client,
            graph_traverser=self._graph_traverser,
            embed_fn=self._generate_embedding,
        )
        from trimcp.orchestrators.temporal import TemporalOrchestrator

        self.temporal = TemporalOrchestrator(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo_client,
            engine=self,
        )
        from trimcp.orchestrators.namespace import NamespaceOrchestrator

        self.namespace = NamespaceOrchestrator(
            pg_pool=self.pg_pool,
            redis_client=self.redis_client,
        )
        from trimcp.orchestrators.cognitive import CognitiveOrchestrator

        self.cognitive = CognitiveOrchestrator(
            pg_pool=self.pg_pool,
        )
        from trimcp.orchestrators.migration import MigrationOrchestrator

        self.migration = MigrationOrchestrator(
            pg_pool=self.pg_pool,
            redis_client=self.redis_client,
            redis_sync_client=self.redis_sync_client,
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

    @property
    def _mongo_db(self):
        """Return the memory_archive MongoDB database instance."""
        if not self.mongo_client:
            raise RuntimeError("MongoDB client is not connected")
        return self.mongo_client.memory_archive

    def _ensure_uuid(self, val: str | UUID | None) -> UUID | None:
        """Ensure the value is a UUID object (or None if input is None)."""
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        return UUID(str(val))  # parse str → UUID

    def _warn_connect_not_called(self, method_name: str) -> None:
        """Warn when a lazy-init delegate is created outside of connect()."""
        log.warning(
            "Orchestrator %s called before connect() — creating delegate lazily. "
            "Call connect() before using the engine for production use.",
            method_name,
        )

    def _redis_cache_key(
        self, namespace_id: str | UUID | None, user_id: str | None, filepath: str
    ) -> str:
        """Construct the Redis cache key for code file hashing."""
        scope_key = f"private:{user_id}" if user_id else "shared"
        namespace_prefix = f"{namespace_id}:" if namespace_id else ""
        return f"hash:{namespace_prefix}{scope_key}:{filepath}"

    def _init_minio_buckets(self):
        """Creates default media buckets if they do not exist."""
        buckets = ["mcp-audio", "mcp-video", "mcp-images"]
        for b in buckets:
            if not self.minio_client.bucket_exists(b):
                self.minio_client.make_bucket(b)
                log.debug("[MinIO] Created bucket: %s", b)

    def _validate_path(self, filepath: str):
        """Strict OS-agnostic path traversal protection using pathlib.

        Resolves the supplied path and asserts it lies within the
        current working directory — ``..``, symlinks, and absolute
        paths that escape CWD are all rejected.
        """
        from pathlib import Path

        try:
            allowed_base = Path.cwd().resolve(strict=True)
            candidate = Path(filepath).resolve(strict=False)

            # Reject if the resolved path doesn't start with CWD
            if not candidate.is_relative_to(allowed_base):
                raise ValueError(f"Path escapes allowed base directory: {filepath!r}")

            # Secondary check: reject raw strings that try to escape
            # before resolution (catches non-existent targets that
            # resolve() can't fully normalise).
            if ".." in Path(filepath).parts:
                # Re-resolve to confirm the .. didn't escape
                if not candidate.is_relative_to(allowed_base):
                    raise ValueError(f"Path traversal attempt (..): {filepath!r}")

        except (ValueError, OSError, RuntimeError) as exc:
            raise ValueError(f"Unsafe filepath rejected: {filepath!r} - {exc}") from exc

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

    async def _verify_worm_enforcement(self):
        """
        Runtime assertion that all WORM tables deny UPDATE/DELETE.

        Acquires a connection from the pool and probes each table in
        ``event_log._WORM_TABLES`` via ``verify_worm_on_table()``.
        Halts server startup with a ``RuntimeError`` if any table's WORM
        guarantee is not in effect.
        """
        from trimcp.event_log import _WORM_TABLES, verify_worm_on_table

        async with self.pg_pool.acquire() as conn:
            for table in _WORM_TABLES:
                await verify_worm_on_table(conn, table)

    async def _verify_rls_enforcement(self):
        """
        Validate that all RLS-protected tables are scoped by namespace.

        Acquires a connection from the pool and probes each table in
        ``event_log._RLS_TABLES`` via ``verify_rls_enforcement()``.
        Logs a warning for tables that can't be queried (may not exist
        on first run) and raises ``RuntimeError`` if any table returns
        rows without a namespace context.
        """
        from trimcp.event_log import _RLS_TABLES, verify_rls_enforcement

        async with self.pg_pool.acquire() as conn:
            for table in _RLS_TABLES:
                await verify_rls_enforcement(conn, table)

    async def _check_global_legacy_warning(self):
        """Warn if ``_global_legacy`` namespace still has KG entities.

        The ``_global_legacy`` namespace is a transitional artifact created during
        the KG RLS migration (schema.sql).  If it still contains KG data and is
        older than 30 days, operators should migrate those entities to proper
        namespaces to reduce the cross-tenant attack surface.
        """
        try:
            async with self.pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, created_at FROM namespaces WHERE slug = '_global_legacy'"
                )
        except Exception:
            log.warning(
                "[legacy-warn] Could not query _global_legacy namespace "
                "(table may not exist yet on first run)."
            )
            return

        if row is None:
            log.info("[legacy-warn] No _global_legacy namespace found — clean start.")
            return

        ns_id = row["id"]
        now_dt = datetime.now(UTC)
        created_dt = row["created_at"]
        if created_dt and created_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=None)
        age_days = (now_dt - created_dt).days if created_dt else 0

        try:
            async with self.pg_pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT count(*) FROM kg_nodes WHERE namespace_id = $1::uuid",
                    ns_id,
                )
        except Exception:
            log.warning(
                "[legacy-warn] Could not query kg_nodes for _global_legacy "
                "(table may not exist yet on first run)."
            )
            return

        if count and count > 0:
            msg = f"_global_legacy namespace still has {count} KG entities (age: {age_days} days)"
            if age_days >= 30:
                log.warning(
                    "[legacy-warn] %s — entities should be migrated to proper "
                    "namespaces to reduce cross-tenant attack surface.",
                    msg,
                )
            else:
                log.info("[legacy-warn] %s — will escalate after 30 days.", msg)
        else:
            log.info("[legacy-warn] _global_legacy namespace exists but has no KG entities.")

    async def _init_mongo_indexes(self):
        db = self._mongo_db
        await db.episodes.create_index("user_id")
        await db.code_files.create_index("filepath")
        await db.code_files.create_index("user_id")

    async def _generate_embedding(self, text: str) -> list[float]:
        return await _embeddings.embed(text)

    # --- Database Helpers ---

    @asynccontextmanager
    async def scoped_session(self, namespace_id: str | UUID):
        """
        Context manager for tenant-isolated PostgreSQL sessions.
        Automatically sets 'trimcp.namespace_id' for RLS enforcement.

        Instrumented with SCOPED_SESSION_LATENCY histogram (Prompt 28)
        to monitor RLS SET LOCAL overhead on the hot path.
        """
        import time as _time

        if not namespace_id:
            raise ValueError("namespace_id is required for scoped sessions")

        ns_uuid = self._ensure_uuid(namespace_id)
        _t0 = _time.perf_counter()

        async with self.pg_pool.acquire() as conn:
            from trimcp.auth import set_namespace_context

            await set_namespace_context(conn, ns_uuid)
            from trimcp.observability import SCOPED_SESSION_LATENCY

            SCOPED_SESSION_LATENCY.labels(
                namespace_id=str(ns_uuid)[:8],  # truncated for cardinality safety
            ).observe(_time.perf_counter() - _t0)
            yield conn

    # --- Phase 0.1: Namespace Management ---

    async def manage_namespace(
        self,
        payload: ManageNamespaceRequest,
        admin_identity: str | None = None,
    ) -> dict:
        """[Phase 0.1] Namespace management — delegating to NamespaceOrchestrator."""
        if self.namespace is None:
            self._warn_connect_not_called("manage_namespace")
            from trimcp.orchestrators.namespace import NamespaceOrchestrator

            self.namespace = NamespaceOrchestrator(
                self.pg_pool,
                redis_client=self.redis_client,
            )
        return await self.namespace.manage_namespace(
            payload,
            admin_identity=admin_identity,
        )

    # --- Phase 0.2: Memory Integrity ---

    async def verify_memory(self, memory_id: str, as_of: datetime | None = None) -> dict:
        """[Phase 0.2] Delegate to MemoryOrchestrator."""
        if self.memory is None:
            from trimcp.orchestrators.memory import MemoryOrchestrator

            self.memory = MemoryOrchestrator(
                self.pg_pool, self.mongo_client, self.redis_client, self.minio_client
            )
        return await self.memory.verify_memory(memory_id, as_of)

    # --- Phase 1.2: Consolidation Tools ---

    async def trigger_consolidation(
        self, namespace_id: str, since_timestamp: datetime | None = None
    ):
        """[Phase 1.2] Trigger consolidation — delegating to TemporalOrchestrator."""
        if self.temporal is None:
            self._warn_connect_not_called("trigger_consolidation")
            from trimcp.orchestrators.temporal import TemporalOrchestrator

            self.temporal = TemporalOrchestrator(self.pg_pool, self.mongo_client, self)
        return await self.temporal.trigger_consolidation(namespace_id, since_timestamp)

    async def consolidation_status(self, run_id: str) -> dict:
        """[Phase 1.2] Consolidation status — delegating to TemporalOrchestrator."""
        if self.temporal is None:
            self._warn_connect_not_called("consolidation_status")
            from trimcp.orchestrators.temporal import TemporalOrchestrator

            self.temporal = TemporalOrchestrator(self.pg_pool, self.mongo_client, self)
        return await self.temporal.consolidation_status(run_id)

    # --- Code Indexing ---

    async def index_code_file(self, payload: IndexCodeFileRequest, *, priority: int = 0) -> dict:
        """[Phase 3.2] Code indexing — delegating to MigrationOrchestrator.

        *priority* routes to queue lane: >0 = high_priority, 0 = batch_processing.
        """
        if self.migration is None:
            self._warn_connect_not_called("index_code_file")
            from trimcp.orchestrators.migration import MigrationOrchestrator

            self.migration = MigrationOrchestrator(
                self.pg_pool, self.redis_client, self.redis_sync_client
            )
        return await self.migration.index_code_file(payload, priority=priority)

    async def get_job_status(self, job_id: str) -> dict:
        """RQ job status — delegating to MigrationOrchestrator."""
        if self.migration is None:
            self._warn_connect_not_called("get_job_status")
            from trimcp.orchestrators.migration import MigrationOrchestrator

            self.migration = MigrationOrchestrator(
                self.pg_pool, self.redis_client, self.redis_sync_client
            )
        return await self.migration.get_job_status(job_id)

    # --- Graph Search ---

    async def graph_search(self, payload: GraphSearchRequest) -> dict:
        """[Phase 2.2] GraphRAG traversal — delegating to GraphOrchestrator."""
        if self.graph is None:
            self._warn_connect_not_called("graph_search")
            from trimcp.orchestrators.graph import GraphOrchestrator

            self.graph = GraphOrchestrator(
                self.pg_pool,
                self.mongo_client,
                self._graph_traverser,
                self._generate_embedding,
            )
        return await self.graph.graph_search(payload)

    # --- Codebase Search ---

    async def search_codebase(
        self,
        query: str,
        namespace_id: str | None = None,
        language_filter: str | None = None,
        top_k: int = 5,
        *,
        user_id: str | None = None,
        private: bool = False,
    ) -> list[dict]:
        """Codebase hybrid search — delegating to GraphOrchestrator."""
        if self.graph is None:
            self._warn_connect_not_called("search_codebase")
            from trimcp.orchestrators.graph import GraphOrchestrator

            self.graph = GraphOrchestrator(
                self.pg_pool,
                self.mongo_client,
                self._graph_traverser,
                self._generate_embedding,
            )
        return await self.graph.search_codebase(
            query,
            namespace_id,
            language_filter,
            top_k,
            user_id=user_id,
            private=private,
        )

    async def manage_quotas(self, payload: ManageQuotasRequest) -> dict:
        """[Phase 3.2] Quota management — delegating to NamespaceOrchestrator."""
        if self.namespace is None:
            self._warn_connect_not_called("manage_quotas")
            from trimcp.orchestrators.namespace import NamespaceOrchestrator

            self.namespace = NamespaceOrchestrator(
                self.pg_pool,
                redis_client=self.redis_client,
            )
        return await self.namespace.manage_quotas(payload)

    # --- Core Saga: store_memory ---
    async def store_memory(self, payload: StoreMemoryRequest) -> dict:
        """Delegate to MemoryOrchestrator (lazy-init for test compatibility)."""
        if self.memory is None:
            from trimcp.orchestrators.memory import MemoryOrchestrator

            self.memory = MemoryOrchestrator(
                self.pg_pool, self.mongo_client, self.redis_client, self.minio_client
            )
        return await self.memory.store_memory(payload)

    async def store_media(self, payload: MediaPayload) -> str:
        """Delegate to MemoryOrchestrator."""
        if self.memory is None:
            from trimcp.orchestrators.memory import MemoryOrchestrator

            self.memory = MemoryOrchestrator(
                self.pg_pool, self.mongo_client, self.redis_client, self.minio_client
            )
        return await self.memory.store_media(payload)

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

            await dispatcher.dispatch_alert(
                "Large GC Purge", f"Manual GC purged {total_deleted} items."
            )

        return result

    async def check_health(self) -> dict:
        """Live non-blocking health checks for all databases."""
        health = {"mongo": "down", "postgres": "down", "redis": "down", "rq_queue": "unknown"}

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

    async def check_health_v1(self) -> dict:
        """
        [Phase 3.1] Comprehensive v1.0 health check.
        Verifies databases, local model readiness, and cognitive sidecar connectivity.
        """
        health = {
            "status": "ok",
            "timestamp": datetime.now(UTC).isoformat(),
            "security": {
                "master_key": "valid"
                if (cfg.TRIMCP_MASTER_KEY and len(cfg.TRIMCP_MASTER_KEY) >= 32)
                else "missing/invalid"
            },
            "databases": {
                "mongo": "down",
                "postgres": "up",  # if we are in this method, PG is already up
                "redis": "down",
            },
            "cognitive": {"backend": cfg.TRIMCP_BACKEND or "auto", "engine": "unknown"},
        }

        # 1. Mongo
        try:
            if self.mongo_client:
                await self.mongo_client.admin.command("ping")
                health["databases"]["mongo"] = "up"
        except Exception:
            health["status"] = "degraded"

        # 2. Redis
        try:
            if self.redis_client:
                await self.redis_client.ping()
                health["databases"]["redis"] = "up"
        except Exception:
            health["status"] = "degraded"

        # 3. Cognitive / Embeddings
        from trimcp.embeddings import get_backend

        try:
            backend = get_backend()
            health["cognitive"]["backend_type"] = type(backend).__name__
            # Check if we can route to cognitive sidecar if applicable
            import httpx

            async with httpx.AsyncClient(timeout=2.0) as client:
                url = (
                    f"{cfg.TRIMCP_COGNITIVE_BASE_URL}/health"
                    if cfg.TRIMCP_COGNITIVE_BASE_URL
                    else "http://localhost:11435/health"
                )
                resp = await client.get(url)
                if resp.status_code == 200:
                    health["cognitive"]["engine"] = "up"
                else:
                    health["cognitive"]["engine"] = f"down ({resp.status_code})"
        except Exception as e:
            health["cognitive"]["engine"] = f"unreachable ({type(e).__name__})"
            # If cognitive is the ONLY way we get embeddings, mark degraded
            if not cfg.TRIMCP_BACKEND:
                health["status"] = "degraded"

        return health

    # --- Recall ---

    async def recall_memory(self, namespace_id, user_id, session_id, as_of=None):
        """Legacy single-result recall — delegate to MemoryOrchestrator."""
        if self.memory is None:
            from trimcp.orchestrators.memory import MemoryOrchestrator

            self.memory = MemoryOrchestrator(
                self.pg_pool, self.mongo_client, self.redis_client, self.minio_client
            )
        return await self.memory.recall_memory(namespace_id, user_id, session_id, as_of)

    async def recall_recent(
        self,
        namespace_id,
        agent_id="default",
        limit=10,
        as_of=None,
        user_id=None,
        session_id=None,
        offset=0,
    ):
        """[Phase 2.2] Delegate to MemoryOrchestrator."""
        if self.memory is None:
            from trimcp.orchestrators.memory import MemoryOrchestrator

            self.memory = MemoryOrchestrator(
                self.pg_pool, self.mongo_client, self.redis_client, self.minio_client
            )
        return await self.memory.recall_recent(
            namespace_id, agent_id, limit, as_of, user_id, session_id, offset
        )

    # --- Semantic Search ---

    async def semantic_search(
        self,
        query,
        namespace_id,
        agent_id="default",
        limit=5,
        offset=0,
        as_of=None,
    ):
        """Delegate to MemoryOrchestrator."""
        if self.memory is None:
            from trimcp.orchestrators.memory import MemoryOrchestrator

            self.memory = MemoryOrchestrator(
                self.pg_pool, self.mongo_client, self.redis_client, self.minio_client
            )
        return await self.memory.semantic_search(
            query, namespace_id, agent_id, limit, offset, as_of
        )

    async def unredact_memory(self, memory_id, namespace_id, agent_id):
        """[Phase 0.3] Delegate to MemoryOrchestrator."""
        if self.memory is None:
            from trimcp.orchestrators.memory import MemoryOrchestrator

            self.memory = MemoryOrchestrator(
                self.pg_pool, self.mongo_client, self.redis_client, self.minio_client
            )
        return await self.memory.unredact_memory(memory_id, namespace_id, agent_id)

    # --- Phase 1.1: Cognitive Layer (Salience) ---

    async def boost_memory(
        self, memory_id: str, agent_id: str, namespace_id: str, factor: float = 0.2
    ) -> dict:
        """[Phase 1.1] Boost memory — delegating to CognitiveOrchestrator."""
        if self.cognitive is None:
            self._warn_connect_not_called("boost_memory")
            from trimcp.orchestrators.cognitive import CognitiveOrchestrator

            self.cognitive = CognitiveOrchestrator(self.pg_pool)
        return await self.cognitive.boost_memory(memory_id, agent_id, namespace_id, factor)

    async def forget_memory(self, memory_id: str, agent_id: str, namespace_id: str) -> dict:
        """[Phase 1.1] Forget memory — delegating to CognitiveOrchestrator."""
        if self.cognitive is None:
            self._warn_connect_not_called("forget_memory")
            from trimcp.orchestrators.cognitive import CognitiveOrchestrator

            self.cognitive = CognitiveOrchestrator(self.pg_pool)
        return await self.cognitive.forget_memory(memory_id, agent_id, namespace_id)

    # --- Phase 1.3: Contradictions ---

    async def list_contradictions(
        self, namespace_id: str, resolution: str | None = None, agent_id: str | None = None
    ) -> list[dict]:
        """[Phase 1.3] List contradictions — delegating to CognitiveOrchestrator."""
        if self.cognitive is None:
            self._warn_connect_not_called("list_contradictions")
            from trimcp.orchestrators.cognitive import CognitiveOrchestrator

            self.cognitive = CognitiveOrchestrator(self.pg_pool)
        return await self.cognitive.list_contradictions(namespace_id, resolution, agent_id)

    async def resolve_contradiction(
        self,
        contradiction_id: str,
        namespace_id: str,
        resolution: str,
        resolved_by: str,
        note: str | None = None,
    ) -> dict:
        """[Phase 1.3] Resolve contradiction — RLS-enforced, delegating to CognitiveOrchestrator."""
        if self.cognitive is None:
            self._warn_connect_not_called("resolve_contradiction")
            from trimcp.orchestrators.cognitive import CognitiveOrchestrator

            self.cognitive = CognitiveOrchestrator(self.pg_pool)
        return await self.cognitive.resolve_contradiction(
            contradiction_id, namespace_id, resolution, resolved_by, note
        )

    # --- Phase 2.2: Time Travel Snapshots ---

    async def create_snapshot(self, payload: CreateSnapshotRequest) -> SnapshotRecord:
        """[Phase 2.2] Create snapshot — delegating to TemporalOrchestrator."""
        if self.temporal is None:
            self._warn_connect_not_called("create_snapshot")
            from trimcp.orchestrators.temporal import TemporalOrchestrator

            self.temporal = TemporalOrchestrator(self.pg_pool, self.mongo_client, self)
        return await self.temporal.create_snapshot(payload)

    async def list_snapshots(self, namespace_id: str) -> list[SnapshotRecord]:
        """[Phase 2.2] List snapshots — delegating to TemporalOrchestrator."""
        if self.temporal is None:
            self._warn_connect_not_called("list_snapshots")
            from trimcp.orchestrators.temporal import TemporalOrchestrator

            self.temporal = TemporalOrchestrator(self.pg_pool, self.mongo_client, self)
        return await self.temporal.list_snapshots(namespace_id)

    async def delete_snapshot(self, snapshot_id: str, namespace_id: str) -> dict:
        """[Phase 2.2] Delete snapshot — delegating to TemporalOrchestrator."""
        if self.temporal is None:
            self._warn_connect_not_called("delete_snapshot")
            from trimcp.orchestrators.temporal import TemporalOrchestrator

            self.temporal = TemporalOrchestrator(self.pg_pool, self.mongo_client, self)
        return await self.temporal.delete_snapshot(snapshot_id, namespace_id)

    async def _fetch_memories_valid_at(
        self,
        conn: asyncpg.Connection,
        namespace_id: UUID,
        memory_ids: list[UUID],
        as_of: datetime,
    ) -> dict[str, Any]:
        """[Phase 2.2] Fetch memory rows valid at a point in time — delegating."""
        if self.temporal is None:
            self._warn_connect_not_called("_fetch_memories_valid_at")
            from trimcp.orchestrators.temporal import TemporalOrchestrator

            self.temporal = TemporalOrchestrator(self.pg_pool, self.mongo_client, self)
        return await self.temporal._fetch_memories_valid_at(conn, namespace_id, memory_ids, as_of)

    async def compare_states(self, payload: CompareStatesRequest) -> StateDiffResult:
        """[Phase 2.2] Compare states — delegating to TemporalOrchestrator."""
        if self.temporal is None:
            self._warn_connect_not_called("compare_states")
            from trimcp.orchestrators.temporal import TemporalOrchestrator

            self.temporal = TemporalOrchestrator(self.pg_pool, self.mongo_client, self)
        return await self.temporal.compare_states(payload)

    # --- Phase 2.1: Re-embedding Migrations ---

    async def start_migration(self, target_model_id: str) -> dict:
        """[Phase 2.1] Start migration — delegating to MigrationOrchestrator."""
        if self.migration is None:
            self._warn_connect_not_called("start_migration")
            from trimcp.orchestrators.migration import MigrationOrchestrator

            self.migration = MigrationOrchestrator(
                self.pg_pool, self.redis_client, self.redis_sync_client
            )
        return await self.migration.start_migration(target_model_id)

    async def migration_status(self, migration_id: str) -> dict:
        """[Phase 2.1] Migration status — delegating to MigrationOrchestrator."""
        if self.migration is None:
            self._warn_connect_not_called("migration_status")
            from trimcp.orchestrators.migration import MigrationOrchestrator

            self.migration = MigrationOrchestrator(
                self.pg_pool, self.redis_client, self.redis_sync_client
            )
        return await self.migration.migration_status(migration_id)

    async def validate_migration(self, migration_id: str) -> dict:
        """[Phase 2.1] Validate migration — delegating to MigrationOrchestrator."""
        if self.migration is None:
            self._warn_connect_not_called("validate_migration")
            from trimcp.orchestrators.migration import MigrationOrchestrator

            self.migration = MigrationOrchestrator(
                self.pg_pool, self.redis_client, self.redis_sync_client
            )
        return await self.migration.validate_migration(migration_id)

    async def commit_migration(self, migration_id: str) -> dict:
        """[Phase 2.1] Commit migration — delegating to MigrationOrchestrator."""
        if self.migration is None:
            self._warn_connect_not_called("commit_migration")
            from trimcp.orchestrators.migration import MigrationOrchestrator

            self.migration = MigrationOrchestrator(
                self.pg_pool, self.redis_client, self.redis_sync_client
            )
        return await self.migration.commit_migration(migration_id)

    async def abort_migration(self, migration_id: str) -> dict:
        """[Phase 2.1] Abort migration — delegating to MigrationOrchestrator."""
        if self.migration is None:
            self._warn_connect_not_called("abort_migration")
            from trimcp.orchestrators.migration import MigrationOrchestrator

            self.migration = MigrationOrchestrator(
                self.pg_pool, self.redis_client, self.redis_sync_client
            )
        return await self.migration.abort_migration(migration_id)
