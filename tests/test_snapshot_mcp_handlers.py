"""Unit tests for nce.snapshot_mcp_handlers (streaming export, row serialization)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from nce.orchestrator import NCEEngine
from nce.snapshot_mcp_handlers import (
    _MAX_EXPORT_ROWS,
    _STREAM_PROGRESS_INTERVAL,
    _serialize_memory_row,
    stream_snapshot_export,
)


async def _collect(gen):
    return [line async for line in gen]


def _parse_ndjson_line(line: str) -> dict:
    return json.loads(line.strip())


async def _empty_fetchmany(_size: int) -> list:
    return []


def _memory_row_dict() -> dict:
    return {"memory_id": uuid4(), "metadata": "{}"}


def _fetchmany_from_batches(*batches: list) -> AsyncMock:
    """Return an async fetchmany that yields each batch in order, then []."""
    queue = list(batches)

    async def fetchmany(_size: int) -> list:
        if queue:
            return queue.pop(0)
        return []

    return fetchmany


def _mock_pool_with_conn(
    total: int,
    *,
    fetchmany=None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Pool + conn + cursor mocks for stream_snapshot_export happy paths."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"total": total})

    cursor = MagicMock()
    cursor.fetchmany = fetchmany if fetchmany is not None else _empty_fetchmany
    conn.cursor = MagicMock(return_value=cursor)

    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)

    acq = MagicMock()
    acq.__aenter__ = AsyncMock(return_value=conn)
    acq.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acq)
    return pool, conn, cursor


@pytest.fixture
def mock_engine_with_pool() -> NCEEngine:
    """Minimal engine with pg_pool set (unused on invalid-UUID path)."""
    engine = NCEEngine()
    engine.pg_pool = MagicMock()
    return engine


# ---------------------------------------------------------------------------
# stream_snapshot_export — invalid namespace_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_snapshot_export_invalid_uuid_yields_single_error(
    mock_engine_with_pool: NCEEngine,
) -> None:
    lines = await _collect(stream_snapshot_export(mock_engine_with_pool, "not-a-valid-uuid"))

    assert len(lines) == 1
    payload = _parse_ndjson_line(lines[0])
    assert payload["type"] == "error"
    assert "invalid namespace_id" in payload["message"].lower()
    mock_engine_with_pool.pg_pool.acquire.assert_not_called()


# ---------------------------------------------------------------------------
# stream_snapshot_export — exception sanitization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_snapshot_export_exception_message_sanitized(
    mock_engine_with_pool: NCEEngine,
) -> None:
    mock_engine_with_pool.pg_pool.acquire.side_effect = RuntimeError("secret db failure")

    lines = await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))

    error_lines = [
        _parse_ndjson_line(line)
        for line in lines
        if _parse_ndjson_line(line).get("type") == "error"
    ]
    assert len(error_lines) == 1

    message = error_lines[0]["message"]
    assert message == "Export failed after 0 records"
    assert "secret" not in message
    assert "RuntimeError" not in message
    assert "Error" not in message


# ---------------------------------------------------------------------------
# stream_snapshot_export — BATCH 2 row limits and cursor SQL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_snapshot_export_over_max_rows_yields_error(
    mock_engine_with_pool: NCEEngine,
) -> None:
    pool, conn, _ = _mock_pool_with_conn(_MAX_EXPORT_ROWS + 1)
    mock_engine_with_pool.pg_pool = pool

    lines = await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))
    payloads = [_parse_ndjson_line(line) for line in lines]

    assert payloads[0]["type"] == "metadata"
    assert payloads[-1]["type"] == "error"
    assert "exceeds the maximum" in payloads[-1]["message"].lower()

    conn.cursor.assert_not_called()


@pytest.mark.asyncio
async def test_stream_snapshot_export_at_max_rows_boundary_proceeds(
    mock_engine_with_pool: NCEEngine,
) -> None:
    pool, conn, _ = _mock_pool_with_conn(_MAX_EXPORT_ROWS)
    mock_engine_with_pool.pg_pool = pool

    lines = await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))
    payloads = [_parse_ndjson_line(line) for line in lines]

    assert [p["type"] for p in payloads] == ["metadata", "complete"]
    assert payloads[-1]["total_expected"] == _MAX_EXPORT_ROWS
    assert payloads[-1]["exported"] == 0
    assert not any(p["type"] == "error" for p in payloads)

    conn.cursor.assert_called_once()


@pytest.mark.asyncio
async def test_stream_snapshot_export_zero_rows_metadata_and_complete_only(
    mock_engine_with_pool: NCEEngine,
) -> None:
    pool, _, _ = _mock_pool_with_conn(0)
    mock_engine_with_pool.pg_pool = pool

    lines = await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))
    payloads = [_parse_ndjson_line(line) for line in lines]

    assert [p["type"] for p in payloads] == ["metadata", "complete"]
    assert payloads[-1]["total_expected"] == 0
    assert payloads[-1]["exported"] == 0
    assert not any(p["type"] in ("memory", "progress", "error") for p in payloads)


@pytest.mark.asyncio
async def test_stream_snapshot_export_cursor_sql_stable_order_by(
    mock_engine_with_pool: NCEEngine,
) -> None:
    pool, conn, _ = _mock_pool_with_conn(0)
    mock_engine_with_pool.pg_pool = pool

    await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))

    conn.cursor.assert_called_once()
    sql = conn.cursor.call_args[0][0]
    assert "ORDER BY m.valid_from ASC, m.id ASC" in sql


# ---------------------------------------------------------------------------
# stream_snapshot_export — BATCH 3 fetchmany timeout and progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_snapshot_export_fetchmany_timeout_yields_error(
    mock_engine_with_pool: NCEEngine,
) -> None:
    pool, _, _ = _mock_pool_with_conn(1)
    mock_engine_with_pool.pg_pool = pool

    with patch(
        "nce.snapshot_mcp_handlers.asyncio.wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        lines = await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))

    payloads = [_parse_ndjson_line(line) for line in lines]
    assert payloads[0]["type"] == "metadata"
    assert payloads[-1]["type"] == "error"
    assert payloads[-1]["message"] == "Export timed out"
    assert not any(p["type"] == "complete" for p in payloads)


@pytest.mark.asyncio
async def test_stream_snapshot_export_fetchmany_within_timeout_streams_rows(
    mock_engine_with_pool: NCEEngine,
) -> None:
    row = _memory_row_dict()
    pool, _, _ = _mock_pool_with_conn(1, fetchmany=_fetchmany_from_batches([row], []))
    mock_engine_with_pool.pg_pool = pool

    lines = await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))
    payloads = [_parse_ndjson_line(line) for line in lines]

    assert payloads[0]["type"] == "metadata"
    memory_lines = [p for p in payloads if p["type"] == "memory"]
    assert len(memory_lines) == 1
    assert memory_lines[0]["memory"]["memory_id"] == str(row["memory_id"])
    assert payloads[-1]["type"] == "complete"
    assert payloads[-1]["exported"] == 1
    assert payloads[-1]["total_expected"] == 1


@pytest.mark.asyncio
async def test_stream_snapshot_export_progress_at_every_1000th_row(
    mock_engine_with_pool: NCEEngine,
) -> None:
    assert _STREAM_PROGRESS_INTERVAL == 1000
    rows = [_memory_row_dict() for _ in range(2500)]
    pool, _, _ = _mock_pool_with_conn(2500, fetchmany=_fetchmany_from_batches(rows))
    mock_engine_with_pool.pg_pool = pool

    lines = await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))
    payloads = [_parse_ndjson_line(line) for line in lines]

    progress = [p for p in payloads if p["type"] == "progress"]
    assert [p["exported"] for p in progress] == [1000, 2000]
    assert all(p["total_expected"] == 2500 for p in progress)
    assert payloads[-1]["type"] == "complete"
    assert payloads[-1]["exported"] == 2500


@pytest.mark.asyncio
async def test_stream_snapshot_export_no_progress_when_under_interval(
    mock_engine_with_pool: NCEEngine,
) -> None:
    rows = [_memory_row_dict() for _ in range(500)]
    pool, _, _ = _mock_pool_with_conn(500, fetchmany=_fetchmany_from_batches(rows))
    mock_engine_with_pool.pg_pool = pool

    lines = await _collect(stream_snapshot_export(mock_engine_with_pool, str(uuid4())))
    payloads = [_parse_ndjson_line(line) for line in lines]

    assert not any(p["type"] == "progress" for p in payloads)
    assert sum(1 for p in payloads if p["type"] == "memory") == 500
    assert payloads[-1]["type"] == "complete"
    assert payloads[-1]["exported"] == 500


# ---------------------------------------------------------------------------
# _serialize_memory_row — metadata parsing
# ---------------------------------------------------------------------------


def test_serialize_memory_row_malformed_metadata_returns_empty_dict() -> None:
    row = {"memory_id": str(uuid4()), "metadata": "{not valid json"}
    result = _serialize_memory_row(row)
    assert result["metadata"] == {}


def test_serialize_memory_row_valid_json_metadata_parses() -> None:
    row = {"memory_id": str(uuid4()), "metadata": '{"foo": 1}'}
    result = _serialize_memory_row(row)
    assert result["metadata"] == {"foo": 1}
