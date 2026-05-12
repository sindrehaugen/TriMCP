"""
TemporalOrchestrator — domain orchestrator for consolidation, snapshots, and state diffing.

Extracted from TriStackEngine (Prompt 54, Step 2).
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient

from trimcp.db_utils import scoped_pg_session

log = logging.getLogger("tri-stack-orchestrator.temporal")


# Mirrored from orchestrator.py for extraction purity
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


def _lineage_source_id(row: Any) -> str | None:
    meta = _metadata_as_dict(
        row.get("metadata") if hasattr(row, "get") else getattr(row, "metadata", None)
    )
    sid = meta.get("source_memory_id")
    if sid:
        return str(sid)
    df = (
        row.get("derived_from")
        if hasattr(row, "get")
        else getattr(row, "derived_from", None)
    )
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


def _build_lineage_modified(old_row: Any, new_row: Any) -> dict[str, Any]:
    keys = ("assertion_type", "memory_type", "pii_redacted", "salience")
    transitions: dict[str, dict[str, Any]] = {}
    for k in keys:
        o = old_row.get(k) if hasattr(old_row, "get") else old_row[k]
        n_val = new_row.get(k) if hasattr(new_row, "get") else new_row[k]
        if k == "salience":
            o = float(o) if o is not None else None
            n_val = float(n_val) if n_val is not None else None
        if o != n_val:
            transitions[k] = {"from": o, "to": n_val}
    return {
        "kind": "lineage_linked",
        "source_memory_id": str(old_row.get("memory_id", "")),
        "old_memory_id": str(old_row.get("memory_id", "")),
        "new_memory_id": str(new_row.get("memory_id", "")),
        "transitions": transitions,
        "metadata_delta": {},
    }


class TemporalOrchestrator:
    """Domain orchestrator for consolidation, snapshots, and state diffing."""

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        mongo_client: AsyncIOMotorClient,
        engine,  # TriStackEngine — needed for semantic_search cross-call
    ):
        self.pg_pool = pg_pool
        self.mongo_client = mongo_client
        self._engine = engine

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_uuid(self, val: str | UUID | None) -> UUID | None:
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        return UUID(str(val))

    @asynccontextmanager
    async def scoped_session(self, namespace_id: str | UUID):
        """Tenant-isolated PostgreSQL session (RLS + transaction-scoped SET LOCAL)."""
        async with scoped_pg_session(self.pg_pool, namespace_id) as conn:
            yield conn

    @property
    def _mongo_db(self):
        return self.mongo_client.memory_archive

    async def _fetch_memories_valid_at(
        self,
        conn: asyncpg.Connection,
        namespace_id: UUID,
        memory_ids: list[UUID],
        as_of: datetime,
    ) -> dict[str, Any]:
        if not memory_ids:
            return {}
        rows = await conn.fetch(
            """
            SELECT m.id AS memory_id, m.namespace_id, m.agent_id, m.payload_ref,
                   m.assertion_type, m.memory_type, m.valid_from, m.pii_redacted,
                   m.derived_from, COALESCE(m.metadata, '{}'::jsonb) AS metadata,
                   (SELECT ms.salience_score FROM memory_salience ms
                    WHERE ms.memory_id = m.id AND ms.namespace_id = m.namespace_id
                    ORDER BY ms.updated_at DESC NULLS LAST LIMIT 1) AS salience
            FROM memories m
            WHERE m.namespace_id = $1
              AND m.id = ANY($2::uuid[])
              AND m.valid_from <= $3
              AND (m.valid_to IS NULL OR m.valid_to > $3)
            """,
            namespace_id,
            memory_ids,
            as_of,
        )
        return {str(r["memory_id"]): r for r in rows}

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    async def trigger_consolidation(
        self, namespace_id: str, since_timestamp: datetime | None = None
    ):
        """[Phase 1.2] Trigger a sleep-consolidation run."""
        from trimcp.consolidation import ConsolidationWorker
        from trimcp.providers import get_provider

        async with self.pg_pool.acquire(timeout=10.0) as conn:
            ns_row = await conn.fetchrow(
                "SELECT metadata FROM namespaces WHERE id = $1", UUID(namespace_id)
            )
            if not ns_row:
                raise ValueError(f"Namespace {namespace_id} not found")

        metadata = json.loads(ns_row["metadata"])
        provider = get_provider(metadata)
        worker = ConsolidationWorker(
            self.pg_pool,
            provider,
            mongo_client=self.mongo_client,
        )

        import asyncio

        asyncio.create_task(
            worker.run_consolidation(
                UUID(namespace_id), since_timestamp=since_timestamp
            )
        )
        return {
            "status": "triggered",
            "namespace_id": namespace_id,
            "since": since_timestamp.isoformat() if since_timestamp else "all",
        }

    async def consolidation_status(self, run_id: str) -> dict:
        """[Phase 1.2] Check status of a consolidation run. Admin bypass by design."""
        async with self.pg_pool.acquire(timeout=10.0) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM consolidation_runs WHERE id = $1", UUID(run_id)
            )
            if not row:
                return {"error": "run_not_found"}

            res = dict(row)
            for k, v in res.items():
                if isinstance(v, datetime):
                    res[k] = v.isoformat()
                elif isinstance(v, UUID):
                    res[k] = str(v)
            return res

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    async def create_snapshot(self, payload) -> Any:
        """[Phase 2.2] Create a named PIT reference."""
        from trimcp.event_log import append_event

        snapshot_at = payload.snapshot_at or datetime.now(timezone.utc)

        async with self.scoped_session(payload.namespace_id) as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO snapshots (namespace_id, agent_id, name, snapshot_at, metadata)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, namespace_id, agent_id, name, snapshot_at, created_at, metadata
                    """,
                    self._ensure_uuid(payload.namespace_id),
                    payload.agent_id,
                    payload.name,
                    snapshot_at,
                    json.dumps(payload.metadata),
                )

                await append_event(
                    conn=conn,
                    namespace_id=self._ensure_uuid(payload.namespace_id),  # type: ignore[arg-type]
                    agent_id=payload.agent_id,
                    event_type="snapshot_created",
                    params={
                        "snapshot_id": str(row["id"]),
                        "name": payload.name,
                        "snapshot_at": snapshot_at.isoformat(),
                    },
                )

        from trimcp.models import SnapshotRecord

        return SnapshotRecord(**row)

    async def list_snapshots(self, namespace_id: str) -> list:
        """[Phase 2.2] List snapshots for a namespace."""
        from trimcp.models import SnapshotRecord

        async with self.scoped_session(namespace_id) as conn:
            rows = await conn.fetch(
                "SELECT * FROM snapshots WHERE namespace_id = $1 ORDER BY created_at DESC",
                UUID(namespace_id),
            )
            return [SnapshotRecord(**r) for r in rows]

    async def delete_snapshot(self, snapshot_id: str, namespace_id: str) -> DeleteSnapshotResult:  # type: ignore[name-defined]  # noqa: F821
        """[Phase 2.2] Delete a point-in-time reference."""
        from trimcp.models import DeleteSnapshotResult

        async with self.scoped_session(namespace_id) as conn:
            res = await conn.execute(
                "DELETE FROM snapshots WHERE id = $1 AND namespace_id = $2",
                UUID(snapshot_id),
                UUID(namespace_id),
            )
            if res == "DELETE 0":
                raise ValueError(
                    f"Snapshot {snapshot_id} not found in namespace {namespace_id}"
                )

        return DeleteSnapshotResult(status="ok", message=f"Snapshot {snapshot_id} deleted")

    # ------------------------------------------------------------------
    # State diffing (compare_states)
    # ------------------------------------------------------------------

    async def compare_states(self, payload) -> Any:
        """[Phase 2.2] Diff two temporal views."""
        from bson import ObjectId

        from trimcp.models import SemanticSearchResult, StateDiffResult

        ns_uuid = self._ensure_uuid(payload.namespace_id)
        if ns_uuid is None:
            raise ValueError("namespace_id is required")

        agent_id = "default"

        def _preview_from_hit(hit: dict[str, Any]) -> str | None:
            rd = hit.get("raw_data")
            if isinstance(rd, str):
                return rd[:200]
            if rd is not None:
                return str(rd)[:200]
            return None

        async def _hydrate(outs: list) -> None:
            db = self._mongo_db
            for res in outs:
                try:
                    doc = await db.episodes.find_one({"_id": ObjectId(res.payload_ref)})
                    if doc:
                        res.content_preview = (
                            doc.get("summary") or str(doc.get("raw_data", ""))
                        )[:200]
                except Exception:
                    pass

        def _row_to_sem(row: Any, *, score: float, hit: dict[str, Any] | None) -> Any:
            meta = _metadata_as_dict(row.get("metadata"))
            pv = _preview_from_hit(hit) if hit else None
            return SemanticSearchResult(
                memory_id=row["memory_id"],
                namespace_id=row["namespace_id"],
                agent_id=row["agent_id"],
                score=score,
                payload_ref=row["payload_ref"],
                assertion_type=row["assertion_type"],
                memory_type=row["memory_type"],
                valid_from=row["valid_from"],
                pii_redacted=row["pii_redacted"],
                content_preview=pv,
                metadata=meta if meta else None,
            )

        if payload.query:
            # Cross-orchestrator call: semantic_search lives on MemoryOrchestrator
            res_a = await self._engine.semantic_search(
                payload.query,
                str(payload.namespace_id),
                agent_id,
                limit=payload.top_k,
                offset=0,
                as_of=payload.as_of_a,
            )
            res_b = await self._engine.semantic_search(
                payload.query,
                str(payload.namespace_id),
                agent_id,
                limit=payload.top_k,
                offset=0,
                as_of=payload.as_of_b,
            )

            def _mid(r: dict[str, Any]) -> str:
                return str(r["memory_id"])

            ids_a = {_mid(r) for r in res_a}
            ids_b = {_mid(r) for r in res_b}
            all_uuid = [UUID(x) for x in sorted(ids_a | ids_b)]

            score_a = {_mid(r): float(r.get("score", 1.0)) for r in res_a}
            score_b = {_mid(r): float(r.get("score", 1.0)) for r in res_b}
            hit_a = {_mid(r): r for r in res_a}
            hit_b = {_mid(r): r for r in res_b}

            async with self.scoped_session(payload.namespace_id) as conn:
                map_a = await self._fetch_memories_valid_at(
                    conn, ns_uuid, all_uuid, payload.as_of_a
                )
                map_b = await self._fetch_memories_valid_at(
                    conn, ns_uuid, all_uuid, payload.as_of_b
                )

            added_ids = ids_b - ids_a
            removed_ids = ids_a - ids_b

            modified: list[dict[str, Any]] = []
            consumed_a: set[str] = set()
            consumed_b: set[str] = set()

            for yid in list(added_ids):
                row_b = map_b.get(yid)
                if row_b is None:
                    continue
                src = _lineage_source_id(row_b)
                if src and src in removed_ids and src in map_a:
                    row_a = map_a[src]
                    modified.append(_build_lineage_modified(row_a, row_b))
                    consumed_b.add(yid)
                    consumed_a.add(src)

            added = [
                _row_to_sem(map_b[i], score=score_b.get(i, 1.0), hit=hit_b.get(i))
                for i in added_ids
                if i not in consumed_b and i in map_b
            ]
            removed = [
                _row_to_sem(map_a[i], score=score_a.get(i, 1.0), hit=hit_a.get(i))
                for i in removed_ids
                if i not in consumed_a and i in map_a
            ]

            await _hydrate(added + removed)

            return StateDiffResult(
                as_of_a=payload.as_of_a,
                as_of_b=payload.as_of_b,
                added=added,
                removed=removed,
                modified=modified,
            )

        # Full namespace diff: UNION ALL query
        async with self.scoped_session(payload.namespace_id) as conn:
            all_rows = await conn.fetch(
                """
                SELECT m.id AS memory_id, m.namespace_id, m.agent_id, m.payload_ref,
                       m.assertion_type, m.memory_type, m.valid_from, m.pii_redacted,
                       m.derived_from, COALESCE(m.metadata, '{}'::jsonb) AS metadata,
                       (SELECT ms.salience_score FROM memory_salience ms
                        WHERE ms.memory_id = m.id AND ms.namespace_id = m.namespace_id
                        ORDER BY ms.updated_at DESC NULLS LAST LIMIT 1) AS salience,
                       'added' AS change_type
                FROM memories m
                WHERE m.namespace_id = $1
                  AND m.valid_from > $2 AND m.valid_from <= $3
                  AND (m.valid_to IS NULL OR m.valid_to > $3)
                UNION ALL
                SELECT m.id AS memory_id, m.namespace_id, m.agent_id, m.payload_ref,
                       m.assertion_type, m.memory_type, m.valid_from, m.pii_redacted,
                       m.derived_from, COALESCE(m.metadata, '{}'::jsonb) AS metadata,
                       (SELECT ms.salience_score FROM memory_salience ms
                        WHERE ms.memory_id = m.id AND ms.namespace_id = m.namespace_id
                        ORDER BY ms.updated_at DESC NULLS LAST LIMIT 1) AS salience,
                       'removed' AS change_type
                FROM memories m
                WHERE m.namespace_id = $1
                  AND m.valid_to > $2 AND m.valid_to <= $3
                """,
                ns_uuid,
                payload.as_of_a,
                payload.as_of_b,
            )

        added_rows = [r for r in all_rows if r["change_type"] == "added"]
        removed_rows = [r for r in all_rows if r["change_type"] == "removed"]

        added_by_id = {str(r["memory_id"]): r for r in added_rows}
        removed_by_id = {str(r["memory_id"]): r for r in removed_rows}

        modified_ns: list[dict[str, Any]] = []
        consumed_added: set[str] = set()
        consumed_removed: set[str] = set()

        for yid, row_b in added_by_id.items():
            src = _lineage_source_id(row_b)
            if src and src in removed_by_id:
                row_a = removed_by_id[src]
                modified_ns.append(_build_lineage_modified(row_a, row_b))
                consumed_added.add(yid)
                consumed_removed.add(src)

        added = [
            _row_to_sem(row, score=1.0, hit=None)
            for mid, row in added_by_id.items()
            if mid not in consumed_added
        ]
        removed = [
            _row_to_sem(row, score=1.0, hit=None)
            for mid, row in removed_by_id.items()
            if mid not in consumed_removed
        ]

        await _hydrate(added + removed)

        return StateDiffResult(
            as_of_a=payload.as_of_a,
            as_of_b=payload.as_of_b,
            added=added,
            removed=removed,
            modified=modified_ns,
        )
