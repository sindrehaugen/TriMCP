"""Semantic search with pgvector cosine + FTS hybrid ranking.

Extracted from ``MemoryOrchestrator`` (Item #22) so the query-building logic
can be tested and maintained independently of the orchestrator's lifecycle.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pypika import Field, Order, Parameter, Query, Table
from pypika.enums import JoinType
from pypika.terms import Term

from trimcp.db_utils import scoped_pg_session
from trimcp.models import _MAX_TOP_K, NamespaceCognitiveConfig

log = logging.getLogger("tri-stack-semantic-search")


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


async def semantic_search(
    *,
    pg_pool: asyncpg.Pool,
    mongo_client: AsyncIOMotorClient,
    embedding_fn,
    query: str,
    namespace_id: str,
    agent_id: str,
    limit: int = 5,
    offset: int = 0,
    as_of=None,
) -> list[dict]:
    """Semantic search with pgvector cosine + FTS hybrid ranking.

    Args:
        pg_pool: PostgreSQL connection pool.
        mongo_client: MongoDB client (used to hydrate episode results).
        embedding_fn: Async callable ``(str) -> list[float]``.
        query: Free-text query string.
        namespace_id: Target namespace UUID (string).
        agent_id: Agent identifier.
        limit: Maximum results to return.
        offset: Pagination offset.
        as_of: Optional time-travel timestamp.

    Returns:
        List of result dicts with ``memory_id``, ``payload_ref``, ``score``, ``raw_data``.
    """
    limit = max(1, min(int(limit), _MAX_TOP_K))
    offset = max(0, int(offset))
    need = offset + limit
    candidate_k = min(max(need * 4, 20), 2000)

    cognitive_config = NamespaceCognitiveConfig()
    temporal_retention_days = 90

    async with scoped_pg_session(pg_pool, namespace_id) as conn:
        ns_row = await conn.fetchrow(
            "SELECT metadata FROM namespaces WHERE id = $1", UUID(namespace_id)
        )
        if ns_row:
            meta = ns_row["metadata"]
            if "cognitive" in meta:
                cognitive_config = NamespaceCognitiveConfig(**meta["cognitive"])
            if "temporal_retention_days" in meta:
                temporal_retention_days = meta["temporal_retention_days"]

        vector = await embedding_fn(query)

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
            v_cand_query.left_join(s)  # type: ignore[arg-type]
            .on((m.id == s.memory_id) & (s.agent_id == p_agent_id))
            .select(
                m.payload_ref,
                m.id.as_("memory_id"),
                distance_expr.as_("distance"),
                RawExpression("COALESCE(s.salience_score, 1.0)").as_(
                    "raw_salience"
                ),
                RawExpression("COALESCE(s.updated_at, m.created_at)").as_(
                    "last_updated"
                ),
            )
            .where(m.namespace_id == p_namespace_id)
            .where(m.memory_type == "episodic")
            .where(RawExpression("COALESCE(s.salience_score, 1.0) > 0.0"))
        )

        fts_cand_query = (
            Query.from_(m)
            .left_join(s)  # type: ignore[arg-type]
            .on((m.id == s.memory_id) & (s.agent_id == p_agent_id))
            .join(
                RawTable(
                    f"LATERAL websearch_to_tsquery('english', {p_query}) AS query"
                )
            )
            .on(RawExpression("true"))  # type: ignore[arg-type]
            .select(
                m.payload_ref,
                m.id.as_("memory_id"),
                RawExpression("ts_rank_cd(m.content_fts, query)").as_("ts_score"),
                RawExpression("COALESCE(s.salience_score, 1.0)").as_(
                    "raw_salience"
                ),
                RawExpression("COALESCE(s.updated_at, m.created_at)").as_(
                    "last_updated"
                ),
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

        v_cand_query = v_cand_query.orderby(Field("distance")).limit(p_candidate_k)  # type: ignore[arg-type]
        fts_cand_query = fts_cand_query.orderby(
            Field("ts_score"), order=Order.desc
        ).limit(p_candidate_k)  # type: ignore[arg-type]

        vector_candidates = v_cand_query.as_("vector_candidates")
        vector_ranked = (
            Query.from_(Table("vector_candidates")).select(
                RawExpression("*"),
                RawExpression("ROW_NUMBER() OVER (ORDER BY distance ASC)").as_(
                    "rank"
                ),
            )
        ).as_("vector_ranked")

        fts_candidates = fts_cand_query.as_("fts_candidates")
        fts_ranked = (
            Query.from_(Table("fts_candidates")).select(
                RawExpression("*"),
                RawExpression("ROW_NUMBER() OVER (ORDER BY ts_score DESC)").as_(
                    "rank"
                ),
            )
        ).as_("fts_ranked")

        v_tbl = Table("vector_ranked").as_("v")
        f_tbl = Table("fts_ranked").as_("f")

        p_alpha = builder.param(float(cognitive_config.alpha))
        p_half_life = builder.param(float(cognitive_config.half_life_days))
        p_need = builder.param(need)

        final_query = (
            Query.with_(vector_candidates, "vector_candidates")
            .with_(vector_ranked, "vector_ranked")
            .with_(fts_candidates, "fts_candidates")
            .with_(fts_ranked, "fts_ranked")
            .from_(v_tbl)
            .join(f_tbl, JoinType.full_outer)
            .on(v_tbl.payload_ref == f_tbl.payload_ref)
            .select(
                RawExpression("COALESCE(v.payload_ref, f.payload_ref)").as_(
                    "payload_ref"
                ),
                RawExpression("COALESCE(v.memory_id, f.memory_id)").as_(
                    "memory_id"
                ),
                RawExpression(
                    f"(COALESCE(1.0 / (60 + v.rank), 0.0) + COALESCE(1.0 / (60 + f.rank), 0.0))"
                    f" * ({p_alpha} + (1.0 - {p_alpha}) "
                    f"* trimcp_decayed_score(COALESCE(v.raw_salience, f.raw_salience), "
                    f"COALESCE(v.last_updated, f.last_updated), {p_half_life}))"
                ).as_("final_score"),
            )
            .orderby(Field("final_score"), order=Order.desc)
            .limit(p_need)  # type: ignore[arg-type]
        )

        rows = await conn.fetch(final_query.get_sql(), *builder.get_params())

        from trimcp.salience import reinforce

        top_results = [
            {
                "payload_ref": row["payload_ref"],
                "memory_id": row["memory_id"],
                "score": row["final_score"],
            }
            for row in rows
        ]

        for res in top_results:
            await reinforce(
                conn,
                str(res["memory_id"]),
                agent_id,
                namespace_id,
                delta=cognitive_config.reinforcement_delta,
            )

    db = mongo_client.memory_archive
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
