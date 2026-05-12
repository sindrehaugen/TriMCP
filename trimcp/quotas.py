"""
Phase 3.2 — Namespace / agent resource quotas (asyncpg, hot-path friendly).

Only namespaces (and optional per-agent rows) that have rows in ``resource_quotas``
are enforced. One short transaction batches all counter updates for a tool call.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import asyncpg
from asyncpg.exceptions import IntegrityConstraintViolationError

from trimcp.config import cfg

RESOURCE_LLM_TOKENS = "llm_tokens"
RESOURCE_STORAGE_BYTES = "storage_bytes"
RESOURCE_MEMORY_COUNT = "memory_count"


class QuotaExceededError(ValueError):
    """Raised when a quota row would be exceeded (maps to MCP / HTTP client errors)."""


@dataclass
class QuotaReservation:
    """Tracks applied increments for best-effort rollback on downstream failure."""

    pool: asyncpg.Pool | None
    steps: list[tuple[UUID, int]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.steps

    async def rollback(self) -> None:
        if not self.steps or self.pool is None:
            self.steps.clear()
            return
        async with self.pool.acquire(timeout=10.0) as conn:
            async with conn.transaction():
                for qid, delta in self.steps:
                    await conn.execute(
                        """
                        UPDATE resource_quotas
                        SET used_amount = GREATEST(0, used_amount - $1),
                            updated_at = now()
                        WHERE id = $2
                        """,
                        delta,
                        qid,
                    )
        self.steps.clear()


def null_reservation() -> QuotaReservation:
    return QuotaReservation(pool=None, steps=[])


def estimate_llm_tokens(*texts: str | None) -> int:
    div = max(1, int(cfg.TRIMCP_QUOTA_TOKEN_ESTIMATE_DIVISOR))
    total_chars = sum(len(t or "") for t in texts)
    return max(1, total_chars // div)


def estimate_storage_bytes(*texts: str | None) -> int:
    return sum(len((t or "").encode("utf-8")) for t in texts)


async def consume_resources(
    pool: asyncpg.Pool,
    *,
    namespace_id: UUID,
    agent_id: str | None,
    amounts: Mapping[str, int],
) -> QuotaReservation:
    """
    Atomically increment counters for each (resource_type -> delta).

    Skips resource types with delta <= 0. If no quota rows match, returns an empty
    reservation without error (operators opt-in by inserting limits).
    """
    if not cfg.TRIMCP_QUOTAS_ENABLED:
        return null_reservation()

    reservation = QuotaReservation(pool=pool)
    deltas = {k: int(v) for k, v in amounts.items() if int(v) > 0}
    if not deltas:
        return reservation

    async with pool.acquire(timeout=10.0) as conn:
        async with conn.transaction():
            try:
                for resource_type, delta in sorted(deltas.items()):
                    rows = await conn.fetch(
                        """
                        SELECT id, agent_id
                        FROM resource_quotas
                        WHERE namespace_id = $1
                          AND resource_type = $2
                          AND (reset_at IS NULL OR reset_at > now())
                          AND (
                              agent_id IS NULL
                              OR ($3::text IS NOT NULL AND agent_id = $3)
                          )
                        ORDER BY (agent_id IS NULL) DESC
                        FOR UPDATE
                        """,
                        namespace_id,
                        resource_type,
                        agent_id,
                    )
                    if not rows:
                        continue
                    for row in rows:
                        upd = await conn.fetchrow(
                            """
                            UPDATE resource_quotas
                            SET used_amount = used_amount + $1,
                                updated_at = now()
                            WHERE id = $2
                              AND used_amount + $1 <= limit_amount
                            RETURNING id
                            """,
                            delta,
                            row["id"],
                        )
                        if upd is None:
                            scope = "namespace" if row["agent_id"] is None else "agent"
                            raise QuotaExceededError(
                                f"Quota exceeded for namespace={namespace_id} "
                                f"resource={resource_type!r} ({scope} limit)"
                            )
                        reservation.steps.append((row["id"], delta))
            except IntegrityConstraintViolationError as e:
                raise QuotaExceededError(
                    f"Quota integrity constraint violated for namespace={namespace_id}: {e}"
                ) from e

    return reservation


def tool_quota_plan(
    tool_name: str, arguments: dict[str, Any]
) -> tuple[UUID, str | None, dict[str, int]] | None:
    """
    Map MCP / HTTP tool name + arguments to (namespace_id, agent_id, amounts).

    ``agent_id`` may be None to enforce only namespace-wide rows.
    Returns None when the tool should not touch quotas.
    """
    amounts: dict[str, int] = {}

    if tool_name == "store_memory":
        if "namespace_id" not in arguments:
            return None
        ns = UUID(str(arguments["namespace_id"]))
        agent: str | None = str(arguments.get("agent_id") or "default")
        c = arguments.get("content")
        summary = arguments.get("summary")
        heavy = arguments.get("heavy_payload")
        tok = estimate_llm_tokens(c, summary, heavy)
        amounts[RESOURCE_LLM_TOKENS] = max(1, tok * 3)
        amounts[RESOURCE_STORAGE_BYTES] = estimate_storage_bytes(c, summary, heavy)
        amounts[RESOURCE_MEMORY_COUNT] = 1
        return ns, agent, amounts

    if tool_name == "semantic_search":
        if "namespace_id" not in arguments:
            return None
        ns = UUID(str(arguments["namespace_id"]))
        agent = str(arguments.get("agent_id") or "default")
        q = arguments.get("query") or ""
        amounts[RESOURCE_LLM_TOKENS] = estimate_llm_tokens(q) + 50
        return ns, agent, amounts

    if tool_name in ("boost_memory", "forget_memory", "unredact_memory"):
        if "namespace_id" not in arguments:
            return None
        ns = UUID(str(arguments["namespace_id"]))
        agent = str(arguments.get("agent_id") or "default")
        amounts[RESOURCE_LLM_TOKENS] = 64
        return ns, agent, amounts

    if tool_name == "list_contradictions":
        if "namespace_id" not in arguments:
            return None
        ns = UUID(str(arguments["namespace_id"]))
        aid = arguments.get("agent_id")
        agent = str(aid) if aid else None
        amounts[RESOURCE_LLM_TOKENS] = 128
        return ns, agent, amounts

    if tool_name == "a2a_query_shared":
        if "consumer_namespace_id" not in arguments:
            return None
        ns = UUID(str(arguments["consumer_namespace_id"]))
        agent = str(arguments.get("consumer_agent_id") or "default")
        q = arguments.get("query") or ""
        amounts[RESOURCE_LLM_TOKENS] = estimate_llm_tokens(q) + 50
        return ns, agent, amounts

    if tool_name == "api_semantic_search":
        if "namespace_id" not in arguments:
            return None
        ns = UUID(str(arguments["namespace_id"]))
        agent = str(arguments.get("agent_id") or "default")
        q = arguments.get("query") or ""
        amounts[RESOURCE_LLM_TOKENS] = estimate_llm_tokens(q) + 50
        return ns, agent, amounts

    return None


async def consume_for_tool(
    pool: asyncpg.Pool,
    tool_name: str,
    arguments: dict[str, Any],
) -> QuotaReservation:
    if not cfg.TRIMCP_QUOTAS_ENABLED:
        return null_reservation()
    plan = tool_quota_plan(tool_name, arguments)
    if plan is None:
        return null_reservation()
    ns, agent, amounts = plan
    return await consume_resources(
        pool, namespace_id=ns, agent_id=agent, amounts=amounts
    )
