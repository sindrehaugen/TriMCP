"""
Tests for Phase 2.1 Re-embedding Worker (trimcp/reembedding_worker.py).

All async functions are driven via asyncio.run() to sidestep pytest-asyncio.
Embed calls are stubbed so tests run without a GPU / SentenceTransformer.
DB interactions use asyncpg AsyncMock — no live Postgres required.
"""

import asyncio
import json
import uuid
from datetime import datetime

try:
    from datetime import UTC
except ImportError:
    UTC = UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trimcp import reembedding_worker as rw
from trimcp.reembedding_worker import (
    ReembeddingWorker,
    _fallback_text,
    _fetch_kg_nodes_batch,
    _fetch_memories_batch,
    _resolve_texts_from_mongo,
    _update_kg_nodes_batch,
    _update_memories_batch,
    current_model_uuid,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_FAKE_VEC = [0.1] * 768


def _make_pool(conn: AsyncMock) -> MagicMock:
    """Wrap a fake connection in a context-manager pool."""
    pool = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool


def _make_conn() -> AsyncMock:
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.executemany = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=uuid.uuid4())
    conn.fetch = AsyncMock(return_value=[])
    conn.transaction = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction.return_value = ctx
    return conn


def _fake_memory_record(memory_type: str = "episodic") -> MagicMock:
    rec = MagicMock()
    rec.__getitem__ = lambda s, k: {
        "id": uuid.uuid4(),
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "memory_type": memory_type,
        "payload_ref": "a" * 24,
        "name": "test_memory",
        "filepath": None,
    }[k]
    rec.get = lambda k, default=None: {
        "id": rec["id"],
        "created_at": rec["created_at"],
        "memory_type": memory_type,
        "payload_ref": "a" * 24,
        "name": "test_memory",
        "filepath": None,
    }.get(k, default)
    return rec


def _fake_kg_record() -> MagicMock:
    rec = MagicMock()
    _id = uuid.uuid4()
    rec.__getitem__ = lambda s, k: {"id": _id, "label": "TestEntity"}[k]
    rec.get = lambda k, d=None: {"id": _id, "label": "TestEntity"}.get(k, d)
    return rec


# --------------------------------------------------------------------------- #
# Unit: current_model_uuid() is deterministic
# --------------------------------------------------------------------------- #


def test_current_model_uuid_is_deterministic():
    a = current_model_uuid()
    b = current_model_uuid()
    assert a == b
    assert isinstance(a, uuid.UUID)


# --------------------------------------------------------------------------- #
# Unit: _fallback_text
# --------------------------------------------------------------------------- #


def test_fallback_text_uses_name_and_filepath():
    rec = MagicMock()
    rec.get = lambda k, d=None: {"name": "foo", "filepath": "bar/baz.py"}.get(k, d)
    text = _fallback_text(rec, 200)
    assert "foo" in text
    assert "bar/baz.py" in text


def test_fallback_text_clips_to_max_chars():
    rec = MagicMock()
    rec.get = lambda k, d=None: {"name": "x" * 300, "filepath": None}.get(k, d)
    text = _fallback_text(rec, 50)
    assert len(text) <= 50


def test_fallback_text_empty_when_no_fields():
    rec = MagicMock()
    rec.get = lambda k, d=None: None
    assert _fallback_text(rec, 100) == ""


# --------------------------------------------------------------------------- #
# Unit: _fetch_memories_batch — verifies SQL paths without live PG
# --------------------------------------------------------------------------- #


def test_fetch_memories_batch_initial_cursor():
    conn = _make_conn()
    conn.fetch = AsyncMock(return_value=[])

    asyncio.run(_fetch_memories_batch(conn, current_model_uuid(), 32, None, None))

    conn.fetch.assert_awaited_once()
    sql = conn.fetch.await_args.args[0].lower()
    assert "embedding_model_id" in sql
    assert "order" in sql
    # Initial cursor must NOT reference cursor position
    assert "cursor" not in sql


def test_fetch_memories_batch_with_cursor():
    conn = _make_conn()
    conn.fetch = AsyncMock(return_value=[])
    ts = datetime(2024, 6, 1, tzinfo=UTC)
    cid = uuid.uuid4()

    asyncio.run(_fetch_memories_batch(conn, current_model_uuid(), 32, ts, cid))

    conn.fetch.assert_awaited_once()
    sql = conn.fetch.await_args.args[0].lower()
    assert "created_at" in sql  # composite keyset present


# --------------------------------------------------------------------------- #
# Unit: _fetch_kg_nodes_batch
# --------------------------------------------------------------------------- #


def test_fetch_kg_nodes_batch_initial():
    conn = _make_conn()
    conn.fetch = AsyncMock(return_value=[])

    asyncio.run(_fetch_kg_nodes_batch(conn, current_model_uuid(), 16, None))

    sql = conn.fetch.await_args.args[0].lower()
    assert "kg_nodes" in sql
    assert "order by id" in sql


def test_fetch_kg_nodes_batch_with_cursor():
    conn = _make_conn()
    conn.fetch = AsyncMock(return_value=[])
    cid = uuid.uuid4()

    asyncio.run(_fetch_kg_nodes_batch(conn, current_model_uuid(), 16, cid))

    sql = conn.fetch.await_args.args[0].lower()
    assert "id > $" in sql


# --------------------------------------------------------------------------- #
# Unit: _update_memories_batch — wraps in transaction, uses correct SQL
# --------------------------------------------------------------------------- #


def test_update_memories_batch_calls_executemany():
    conn = _make_conn()
    model_uuid = current_model_uuid()
    mem_id = uuid.uuid4()
    created_at = datetime(2024, 1, 1, tzinfo=UTC)
    vec = _FAKE_VEC

    asyncio.run(_update_memories_batch(conn, [(mem_id, created_at, vec)], model_uuid))

    conn.executemany.assert_awaited_once()
    sql = conn.executemany.await_args.args[0].lower()
    assert "update memories" in sql
    assert "embedding_model_id" in sql

    rows = conn.executemany.await_args.args[1]
    assert len(rows) == 1
    # payload row: (json_vec, model_str, mem_id, created_at)
    assert rows[0][2] == mem_id
    assert rows[0][3] == created_at
    assert json.loads(rows[0][0]) == _FAKE_VEC


# --------------------------------------------------------------------------- #
# Unit: _update_kg_nodes_batch
# --------------------------------------------------------------------------- #


def test_update_kg_nodes_batch_calls_executemany():
    conn = _make_conn()
    node_id = uuid.uuid4()

    asyncio.run(_update_kg_nodes_batch(conn, [(node_id, _FAKE_VEC)], current_model_uuid()))

    conn.executemany.assert_awaited_once()
    sql = conn.executemany.await_args.args[0].lower()
    assert "update kg_nodes" in sql
    rows = conn.executemany.await_args.args[1]
    assert len(rows) == 1
    # payload row: (json_vec, model_str, node_id)
    assert rows[0][2] == node_id
    assert json.loads(rows[0][0]) == _FAKE_VEC


# --------------------------------------------------------------------------- #
# Unit: _resolve_texts_from_mongo — batch lookup, collection routing
# --------------------------------------------------------------------------- #


def test_resolve_texts_returns_episodic_raw_data():
    ref = "b" * 24

    rec = MagicMock()
    rec.get = lambda k, d=None: {
        "payload_ref": ref,
        "memory_type": "episodic",
    }.get(k, d)

    class _FakeId(str):
        """str subclass so str(doc["_id"]) == ref."""

    async def _fake_find(*_, **__):
        yield {"_id": _FakeId(ref), "raw_data": "hello world"}

    mongo_client = MagicMock()
    mongo_client.memory_archive.episodes.find = _fake_find

    # ObjectId is imported *locally* inside the function; patch it at its
    # source so that ObjectId(ref) just returns the string ref unchanged.
    with patch("bson.ObjectId", side_effect=lambda x: _FakeId(x)):
        result = asyncio.run(_resolve_texts_from_mongo(mongo_client, [rec], max_text_chars=512))

    assert result.get(ref) == "hello world"


# --------------------------------------------------------------------------- #
# Integration: ReembeddingWorker.run_once — happy path, no rows
# --------------------------------------------------------------------------- #


def test_worker_run_once_no_stale_rows():
    """When there are no stale memories, the worker completes with 0 updates."""
    conn = _make_conn()
    run_uuid = uuid.uuid4()
    conn.fetchval = AsyncMock(return_value=run_uuid)
    # First fetch: no rows → terminates immediately
    conn.fetch = AsyncMock(return_value=[])

    pool = _make_pool(conn)

    with patch.object(rw, "_embeddings") as mock_emb:
        mock_emb.embed_batch = AsyncMock(return_value=[])
        result = asyncio.run(ReembeddingWorker(batch_size=8, batches_per_minute=600).run_once(pool))

    assert result["status"] == "completed"
    assert result["memories_done"] == 0
    assert result["kg_nodes_done"] == 0


# --------------------------------------------------------------------------- #
# Integration: ReembeddingWorker.run_once — processes one batch of memories
# --------------------------------------------------------------------------- #


def test_worker_processes_one_memory_batch():
    """Worker fetches one page of rows, embeds them, and marks run completed."""
    conn = _make_conn()
    run_uuid = uuid.uuid4()
    conn.fetchval = AsyncMock(return_value=run_uuid)

    fake_row = _fake_memory_record("episodic")
    # First fetch returns one row; second fetch returns nothing (end of cursor).
    conn.fetch = AsyncMock(side_effect=[[fake_row], [], []])

    pool = _make_pool(conn)

    with patch.object(rw, "_embeddings") as mock_emb:
        mock_emb.embed_batch = AsyncMock(return_value=[_FAKE_VEC])
        result = asyncio.run(
            ReembeddingWorker(
                batch_size=32,
                batches_per_minute=600,  # sleep ≈ 0.1 s
            ).run_once(pool, mongo_client=None)
        )

    assert result["status"] == "completed"
    # embed_batch called once (the batch with one row)
    mock_emb.embed_batch.assert_awaited_once()
    # executemany called once for the UPDATE
    conn.executemany.assert_awaited()


# --------------------------------------------------------------------------- #
# Integration: max_rows_per_run stops early
# --------------------------------------------------------------------------- #


def test_worker_respects_max_rows_per_run():
    conn = _make_conn()
    conn.fetchval = AsyncMock(return_value=uuid.uuid4())

    row = _fake_memory_record()
    # Return rows indefinitely — worker must stop at max_rows_per_run.
    conn.fetch = AsyncMock(return_value=[row])

    pool = _make_pool(conn)

    with patch.object(rw, "_embeddings") as mock_emb:
        mock_emb.embed_batch = AsyncMock(return_value=[_FAKE_VEC])
        result = asyncio.run(
            ReembeddingWorker(
                batch_size=1,
                batches_per_minute=600,
                max_rows_per_run=1,
            ).run_once(pool, mongo_client=None)
        )

    assert result["status"] == "completed"
    assert result["memories_done"] == 1
    # embed_batch must have been called exactly once
    mock_emb.embed_batch.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Integration: embed failure propagates and run is marked 'failed'
# --------------------------------------------------------------------------- #


def test_worker_marks_run_failed_on_embed_error():
    conn = _make_conn()
    conn.fetchval = AsyncMock(return_value=uuid.uuid4())

    row = _fake_memory_record()
    conn.fetch = AsyncMock(return_value=[row])

    pool = _make_pool(conn)

    with patch.object(rw, "_embeddings") as mock_emb:
        mock_emb.embed_batch = AsyncMock(side_effect=RuntimeError("GPU OOM"))
        with pytest.raises(RuntimeError, match="GPU OOM"):
            asyncio.run(
                ReembeddingWorker(batch_size=1, batches_per_minute=600).run_once(
                    pool, mongo_client=None
                )
            )

    # The final UPDATE must set status='failed'
    final_execute_calls = conn.execute.await_args_list
    assert any("failed" in str(call) for call in final_execute_calls), (
        "Expected status='failed' in final UPDATE"
    )


# --------------------------------------------------------------------------- #
# Integration: kg_nodes phase runs when include_kg_nodes=True
# --------------------------------------------------------------------------- #


def test_worker_processes_kg_nodes_when_enabled():
    conn = _make_conn()
    conn.fetchval = AsyncMock(return_value=uuid.uuid4())

    kg_row = _fake_kg_record()
    # memories fetch: no rows → skip Phase A
    # kg_nodes fetch: one row, then empty
    conn.fetch = AsyncMock(side_effect=[[], [kg_row], []])

    pool = _make_pool(conn)

    with patch.object(rw, "_embeddings") as mock_emb:
        mock_emb.embed_batch = AsyncMock(return_value=[_FAKE_VEC])
        result = asyncio.run(
            ReembeddingWorker(
                batch_size=32,
                batches_per_minute=600,
                include_kg_nodes=True,
            ).run_once(pool, mongo_client=None)
        )

    assert result["status"] == "completed"
    assert result["kg_nodes_done"] == 1
    mock_emb.embed_batch.assert_awaited_once()
