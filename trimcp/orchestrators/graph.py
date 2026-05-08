"""
GraphOrchestrator — domain orchestrator for GraphRAG traversal and codebase search.

Extracted from TriStackEngine (Prompt 54, Step 1) following the same lazy-init
delegate pattern used by MemoryOrchestrator.
"""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("tri-stack-orchestrator.graph")

# Reusable constants (mirrored from orchestrator.py for extraction purity)
_SAFE_ID_RE = re.compile(r"^[\w\-]{1,128}$")
_ALLOWED_LANGUAGES = frozenset({"python", "javascript", "typescript", "go", "rust"})
_MAX_TOP_K = 100


class GraphOrchestrator:
    """Domain orchestrator for graph search and codebase semantic search."""

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        mongo_client: AsyncIOMotorClient,
        graph_traverser,  # GraphRAGTraverser
        embed_fn,  # async callable: (str) -> list[float]
    ):
        self.pg_pool = pg_pool
        self.mongo_client = mongo_client
        self._graph_traverser = graph_traverser
        self._embed = embed_fn

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_uuid(self, raw: str | UUID | None) -> UUID | None:
        if raw is None:
            return None
        if isinstance(raw, UUID):
            return raw
        return UUID(str(raw))

    async def scoped_session(self, namespace_id: str | UUID):
        """Tenant-isolated PostgreSQL session with RLS context."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _session(ns_id: str | UUID):
            if not ns_id:
                raise ValueError("namespace_id is required")
            ns_uuid = UUID(str(ns_id))
            async with self.pg_pool.acquire() as conn:
                from trimcp.auth import set_namespace_context

                await set_namespace_context(conn, ns_uuid)
                yield conn

        return _session(namespace_id)

    @property
    def _mongo_db(self):
        return self.mongo_client.memory_archive

    # ------------------------------------------------------------------
    # GraphRAG traversal
    # ------------------------------------------------------------------

    async def graph_search(self, payload) -> dict:
        """
        [Phase 2.2] GraphRAG traversal with temporal and user scoping.
        """
        if self._graph_traverser is None:
            raise RuntimeError("Engine not connected — call connect() first")

        subgraph = await self._graph_traverser.search(
            payload.query,
            namespace_id=str(payload.namespace_id),
            max_depth=payload.max_depth,
            anchor_top_k=3,
            user_id=payload.agent_id,
            private=bool(payload.agent_id),
            as_of=payload.as_of,
            max_edges_per_node=payload.max_edges_per_node,
            edge_limit=payload.edge_limit,
            edge_offset=payload.edge_offset,
        )
        return subgraph.to_dict()

    # ------------------------------------------------------------------
    # Codebase search (hybrid vector + FTS with RRF)
    # ------------------------------------------------------------------

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
        top_k = max(1, min(top_k, _MAX_TOP_K))
        if language_filter and language_filter not in _ALLOWED_LANGUAGES:
            raise ValueError(f"Invalid language_filter '{language_filter}'")
        if private:
            if not user_id or not _SAFE_ID_RE.match(user_id):
                raise ValueError("private codebase search requires valid user_id")
        elif user_id is not None and not _SAFE_ID_RE.match(user_id):
            raise ValueError("Invalid user_id format")

        vector = await self._embed(query)
        candidate_k = top_k * 4

        async with self.scoped_session(namespace_id or "default") as conn:
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

            memory_ids = [UUID(str(r["id"])) for r in fused_rows]
            score_map = {str(r["id"]): float(r["score"]) for r in fused_rows}

            rows = await conn.fetch(
                """
                SELECT m.id, m.payload_ref, m.language, m.filepath, m.assertion_type,
                       m.metadata, m.content_fts
                FROM memories m
                WHERE m.id = ANY($1::uuid[])
                """,
                memory_ids,
            )

            results = []
            from bson import ObjectId

            for row in rows:
                mid = str(row["id"])
                meta = {}
                raw = row.get("metadata")
                if raw is not None:
                    if isinstance(raw, str):
                        try:
                            meta = json.loads(raw)
                        except json.JSONDecodeError:
                            pass
                    elif isinstance(raw, dict):
                        meta = dict(raw)

                name = meta.get("name") or row["filepath"]
                node_type = meta.get("node_type") or "chunk"
                start_line = meta.get("start_line", 0)
                end_line = meta.get("end_line", 0)

                # Hydrate code snippet from MongoDB
                excerpt = ""
                try:
                    oid = ObjectId(row["payload_ref"])
                    doc = await self._mongo_db.code_files.find_one({"_id": oid})
                    if doc:
                        excerpt = str(doc.get("raw_code", ""))[:600]
                except Exception:
                    pass

                results.append(
                    {
                        "memory_id": mid,
                        "score": score_map.get(mid, 0.0),
                        "filepath": row["filepath"],
                        "language": row["language"],
                        "node_type": node_type,
                        "name": name,
                        "start_line": start_line,
                        "end_line": end_line,
                        "excerpt": excerpt,
                    }
                )

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
