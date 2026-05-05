"""
Fake asyncpg connection + pool mocks for Saga / event_log unit tests.

Implements only the SQL shapes exercised by trimcp.event_log.append_event —
no TCP, no Postgres.  Use RecordingFakePool when code expects ``pool.acquire``.

This is deterministic test scaffolding (replacement for unavailable local
PostgreSQL during CI smoke runs).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg


class _FakeTransaction:
    def __init__(self, conn: "RecordingFakeConnection") -> None:
        self._conn = conn

    async def __aenter__(self) -> None:
        self._conn._tx_depth += 1

    async def __aexit__(self, *_exc: object) -> None:
        self._conn._tx_depth -= 1


class RecordingFakeConnection:
    """
    Records INSERT payloads and honours per-namespace MAX(event_seq)+1 sequencing.

    asyncpg Compatibility
    ---------------------
    * ``transaction()`` async context matches Saga coordinator wrapping.
    * ``fetchval`` / ``execute`` / ``fetchrow`` route on SQL substring heuristics.
    """

    def __init__(
        self,
        *,
        db_clock: datetime | None = None,
        simulate_unique_violation_on_insert: bool = False,
    ) -> None:
        utc = timezone.utc
        self._db_clock = (db_clock or datetime(2026, 5, 5, 10, 0, 0, 123456, tzinfo=utc)).astimezone(utc)
        self._seq_max: defaultdict[UUID, int] = defaultdict(int)
        self._tx_depth = 0
        self.event_inserts: list[dict[str, Any]] = []
        self.unique_violation = simulate_unique_violation_on_insert

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    async def fetchval(self, query: str, *args: Any) -> Any:
        if "clock_timestamp()" in query.lower():
            return self._db_clock
        raise AssertionError(f"Unexpected fetchval query: {query!r}")

    async def execute(self, query: str, *args: Any) -> str:
        if "pg_advisory_xact_lock" in query:
            _ = args[0]
            return "SELECT 1"
        raise AssertionError(f"Unexpected execute query: {query!r}")

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        q = "".join(query.split()).lower()

        if "coalesce(max(event_seq)" in q and "fromevent_log" in q.replace(" ", ""):
            namespace_id = args[0]
            assert isinstance(namespace_id, UUID)
            nxt = self._seq_max[namespace_id] + 1
            return {"next_seq": nxt}

        if "insertintoevent_log" in q.replace(" ", ""):
            (
                event_id,
                namespace_id,
                agent_id,
                event_type,
                event_seq,
                occurred_at,
                params_json,
                result_summary_json,
                parent_event_id,
                llm_payload_uri,
                llm_payload_hash,
                signature,
                signature_key_id,
            ) = args

            record = {
                "id": event_id,
                "namespace_id": namespace_id,
                "agent_id": agent_id,
                "event_type": event_type,
                "event_seq": event_seq,
                "occurred_at": occurred_at,
                "params": params_json,
                "signature": signature,
                "signature_key_id": signature_key_id,
            }
            if self.unique_violation:
                raise asyncpg.UniqueViolationError("simulated collision")

            ns = namespace_id if isinstance(namespace_id, UUID) else UUID(str(namespace_id))
            self._seq_max[ns] = max(self._seq_max[ns], int(event_seq))
            self.event_inserts.append(record)

            es = event_seq if isinstance(event_seq, int) else int(event_seq)
            return {"id": event_id, "event_seq": es, "occurred_at": occurred_at}

        raise AssertionError(f"Unexpected fetchrow query: {query!r}")


class RecordingFakePool:
    """
    Minimal pool stand-in: ``await pool.acquire()`` returns a fixed connection.
    """

    def __init__(self, conn: RecordingFakeConnection) -> None:
        self._conn = conn

    async def acquire(self) -> RecordingFakeConnection:
        return self._conn

    async def close(self) -> None:
        return None


def make_fake_pool(**kwargs: Any) -> tuple[RecordingFakePool, RecordingFakeConnection]:
    """Factory: ``pool, conn = make_fake_pool()``."""
    conn = RecordingFakeConnection(**kwargs)
    return RecordingFakePool(conn), conn
