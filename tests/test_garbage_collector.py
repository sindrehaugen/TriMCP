"""
Tests for GC namespace-aware mode (garbage_collector.py).

Verifies that the GC iterates over all namespaces with set_namespace_context()
before RLS-protected operations, and that helpers return gracefully on error.
"""

from __future__ import annotations

import asyncio
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_namespaces() -> list[UUID]:
    return [uuid4(), uuid4(), uuid4()]


@pytest.fixture
def mock_pg_pool(sample_namespaces):
    """Create a mock pg_pool that returns sample namespaces."""
    pool = MagicMock()
    conn = AsyncMock()
    # fetch returns rows with 'id' field
    conn.fetch = AsyncMock(return_value=[{"id": ns} for ns in sample_namespaces])
    conn.execute = AsyncMock(return_value="DELETE 3")
    tx = AsyncMock()
    tx.__aenter__.return_value = None
    tx.__aexit__.return_value = False
    conn.transaction = MagicMock(return_value=tx)
    acq = AsyncMock()
    acq.__aenter__.return_value = conn
    acq.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=acq)
    return pool


# ---------------------------------------------------------------------------
# _fetch_all_namespaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_all_namespaces_returns_uuids(mock_pg_pool, sample_namespaces):
    from nce.garbage_collector import _fetch_all_namespaces

    result = await _fetch_all_namespaces(mock_pg_pool)
    assert result == sample_namespaces


@pytest.mark.asyncio
async def test_fetch_all_namespaces_empty():
    from nce.garbage_collector import _fetch_all_namespaces

    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    acq = AsyncMock()
    acq.__aenter__.return_value = conn
    acq.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=acq)
    result = await _fetch_all_namespaces(pool)
    assert result == []


# ---------------------------------------------------------------------------
# _clean_orphaned_kg_nodes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_orphaned_cascade_sets_context(mock_pg_pool, sample_namespaces):
    """Verify set_namespace_context is called before the unified CTE cascade."""
    from nce.garbage_collector import _clean_orphaned_cascade

    # Provide a row so the cascade returns counts
    conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow = AsyncMock(
        return_value={
            "salience_count": 0,
            "contradictions_count": 0,
            "event_count": 0,
        }
    )

    with patch(
        "nce.garbage_collector.set_namespace_context", new_callable=AsyncMock
    ) as mock_set_ctx:
        counts = await _clean_orphaned_cascade(mock_pg_pool, sample_namespaces[0])

    mock_set_ctx.assert_awaited_once()
    args, _ = mock_set_ctx.call_args
    assert args[1] == sample_namespaces[0]
    assert isinstance(counts, dict)
    assert "salience" in counts
    assert "contradictions" in counts
    assert "events" not in counts
    assert "nodes" not in counts


@pytest.mark.asyncio
async def test_clean_orphaned_cascade_returns_zero_on_error():
    """If the DB query fails, return all-zero counts (don't crash)."""
    from nce.garbage_collector import _clean_orphaned_cascade

    bad_pool = MagicMock()
    bad_pool.acquire.side_effect = RuntimeError("Connection refused")

    with patch("nce.garbage_collector.set_namespace_context", new_callable=AsyncMock):
        counts = await _clean_orphaned_cascade(bad_pool, uuid4())
    assert counts == {"salience": 0, "contradictions": 0}


@pytest.mark.asyncio
async def test_clean_orphaned_cascade_handles_null_row(mock_pg_pool):
    """If fetchrow returns None, return all-zero counts gracefully."""
    from nce.garbage_collector import _clean_orphaned_cascade

    conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow = AsyncMock(return_value=None)

    counts = await _clean_orphaned_cascade(mock_pg_pool, uuid4())
    assert counts == {"salience": 0, "contradictions": 0}


@pytest.mark.asyncio
async def test_clean_orphaned_cascade_passes_namespace_id_to_cte(mock_pg_pool):
    """Verify namespace_id is passed as a query parameter to the CTE fetchrow call."""
    from nce.garbage_collector import _clean_orphaned_cascade

    ns_id = uuid4()

    conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow = AsyncMock(
        side_effect=[
            {
                "salience_count": 5,
                "contradictions_count": 3,
            },
            {
                "salience_count": 0,
                "contradictions_count": 0,
            },
        ]
    )

    with patch("nce.garbage_collector.set_namespace_context", new_callable=AsyncMock):
        counts = await _clean_orphaned_cascade(mock_pg_pool, ns_id)

    # Verify the namespace_id UUID was passed as the second argument to fetchrow
    call_args, call_kwargs = conn.fetchrow.call_args
    # The SQL text is the first positional arg, namespace_id is the second
    assert len(call_args) >= 2, f"Expected at least 2 positional args, got {len(call_args)}"
    assert call_args[1] == ns_id, f"Expected namespace_id {ns_id} but got {call_args[1]}"

    # Verify the SQL contains the explicit namespace_id filter pattern
    sql = call_args[0]
    assert "$1::uuid" in sql, "Expected parameterised namespace_id filter in CTE SQL"
    assert "namespace_id = $1::uuid" in sql, "Expected explicit namespace_id WHERE clause in CTE"
    # Should appear at least 5 times: existing_memories, 4 orphan sub-selects, 2 DELETEs
    namespace_filter_count = sql.count("namespace_id = $1::uuid")
    assert namespace_filter_count >= 5, (
        f"Expected at least 5 explicit namespace_id filters, found {namespace_filter_count}"
    )

    assert counts == {"salience": 5, "contradictions": 3}


@pytest.mark.asyncio
async def test_fetch_pg_refs_sets_context_per_namespace():
    """Verify _fetch_pg_refs sets namespace context for each namespace."""
    from nce.garbage_collector import _fetch_pg_refs

    ns_list = [uuid4(), uuid4()]

    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])  # empty result — no refs
    tx = AsyncMock()
    tx.__aenter__.return_value = None
    tx.__aexit__.return_value = False
    conn.transaction = MagicMock(return_value=tx)
    acq = AsyncMock()
    acq.__aenter__.return_value = conn
    acq.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=acq)

    with patch(
        "nce.garbage_collector.set_namespace_context", new_callable=AsyncMock
    ) as mock_set_ctx:
        refs = await _fetch_pg_refs(pool, ns_list)

    assert refs == set()
    assert mock_set_ctx.await_count == len(ns_list)
    for i, ns in enumerate(ns_list):
        assert mock_set_ctx.await_args_list[i].args[1] == ns


# ---------------------------------------------------------------------------
# _clean_orphaned_salience — removed (replaced by _clean_orphaned_cascade)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _clean_orphaned_contradictions — removed (replaced by _clean_orphaned_cascade)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _collect_orphans namespace iteration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_orphans_iterates_over_all_namespaces(mock_pg_pool, sample_namespaces):
    """Verify _collect_orphans calls unified cascade for each namespace."""
    from datetime import datetime, timedelta

    from nce.garbage_collector import _collect_orphans

    stale = {
        "_id": "507f1f77bcf86cd799439011",
        "ingested_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }

    async def _async_cursor(docs):
        for d in docs:
            yield d

    def _find_chain(docs):
        cursor = MagicMock()
        cursor.max_time_ms = MagicMock(return_value=_async_cursor(docs))
        return cursor

    # GC uses db[col_name] (subscript), not db.col_name (attribute)
    episodes_col = MagicMock()
    episodes_col.find = MagicMock(return_value=_find_chain([stale]))
    episodes_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    code_col = MagicMock()
    code_col.find = MagicMock(return_value=_find_chain([]))
    code_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))

    mongo_client = MagicMock()
    mongo_client.memory_archive = {"episodes": episodes_col, "code_files": code_col}

    with (
        patch(
            "nce.garbage_collector._clean_orphaned_cascade",
            new_callable=AsyncMock,
            return_value={"salience": 0, "contradictions": 0, "events": 0},
        ) as mock_cascade,
        patch(
            "nce.garbage_collector._fetch_pg_refs",
            new_callable=AsyncMock,
            return_value=set(),
        ),
    ):
        result = await _collect_orphans(mongo_client, mock_pg_pool)

    # Unified cascade should have been called once per namespace
    assert mock_cascade.await_count == len(sample_namespaces)

    # Verify namespace UUIDs were passed correctly
    for i, ns in enumerate(sample_namespaces):
        assert mock_cascade.await_args_list[i].args[1] == ns

    # Verify result shape
    assert "deleted_docs" in result
    assert "deleted_nodes" not in result
    assert "deleted_salience" in result
    assert "deleted_contradictions" in result
    assert result["deleted_docs"] >= 0


@pytest.mark.asyncio
async def test_collect_orphans_handles_no_namespaces():
    """When no namespaces exist, abort before Mongo/PG deletion to prevent data loss."""
    from datetime import datetime, timedelta

    from nce.garbage_collector import _collect_orphans

    stale = {
        "_id": "507f1f77bcf86cd799439011",
        "ingested_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }

    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])  # empty namespaces table
    acq = AsyncMock()
    acq.__aenter__.return_value = conn
    acq.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=acq)

    async def _async_cursor(docs):
        for d in docs:
            yield d

    find_cursor = MagicMock()
    find_cursor.max_time_ms = MagicMock(return_value=_async_cursor([stale]))

    mongo_client = MagicMock()
    episodes_col = MagicMock()
    episodes_col.find = MagicMock(return_value=find_cursor)
    episodes_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    code_col = MagicMock()
    code_find = MagicMock()
    code_find.max_time_ms = MagicMock(return_value=_async_cursor([]))
    code_col.find = MagicMock(return_value=code_find)
    code_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
    mongo_client.memory_archive = {"episodes": episodes_col, "code_files": code_col}

    with (
        patch(
            "nce.garbage_collector._clean_orphaned_cascade", new_callable=AsyncMock
        ) as mock_cascade,
        patch(
            "nce.garbage_collector._fetch_pg_refs",
            new_callable=AsyncMock,
        ) as mock_pg_refs,
    ):
        result = await _collect_orphans(mongo_client, pool)

    mock_cascade.assert_not_awaited()
    mock_pg_refs.assert_not_awaited()
    episodes_col.delete_one.assert_not_awaited()
    assert result == {
        "deleted_docs": 0,
        "deleted_salience": 0,
        "deleted_contradictions": 0,
    }


# ---------------------------------------------------------------------------
# Batch 6 — hardening regressions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_orphaned_cascade_sql_no_trailing_comma_before_select(
    mock_pg_pool,
):
    """deleted_contradictions CTE must not have a trailing comma before SELECT."""
    from nce.garbage_collector import _clean_orphaned_cascade

    conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow = AsyncMock(return_value={"salience_count": 0, "contradictions_count": 0})

    with patch("nce.garbage_collector.set_namespace_context", new_callable=AsyncMock):
        await _clean_orphaned_cascade(mock_pg_pool, uuid4())

    sql = conn.fetchrow.call_args[0][0]
    assert ")\n                    SELECT" in sql
    assert "),\n                    SELECT" not in sql


@pytest.mark.asyncio
async def test_collect_orphans_empty_namespaces_never_deletes_mongo():
    """Empty namespace list must abort before any Mongo delete_one calls."""
    from datetime import datetime, timedelta

    from nce.garbage_collector import _collect_orphans

    stale_docs = [
        {
            "_id": f"507f1f77bcf86cd79943901{i}",
            "ingested_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        for i in range(3)
    ]

    async def _async_cursor(docs):
        for d in docs:
            yield d

    def _find_chain(docs):
        cursor = MagicMock()
        cursor.max_time_ms = MagicMock(return_value=_async_cursor(docs))
        return cursor

    episodes_col = MagicMock()
    episodes_col.find = MagicMock(return_value=_find_chain(stale_docs))
    episodes_col.delete_one = AsyncMock()
    code_col = MagicMock()
    code_col.find = MagicMock(return_value=_find_chain([]))
    code_col.delete_one = AsyncMock()

    mongo_client = MagicMock()
    mongo_client.memory_archive = {"episodes": episodes_col, "code_files": code_col}

    pool = MagicMock()

    with patch(
        "nce.garbage_collector._fetch_all_namespaces",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await _collect_orphans(mongo_client, pool)

    episodes_col.delete_one.assert_not_awaited()
    code_col.delete_one.assert_not_awaited()
    assert result == {
        "deleted_docs": 0,
        "deleted_salience": 0,
        "deleted_contradictions": 0,
    }


@pytest.mark.asyncio
async def test_connect_with_retry_closes_mongo_when_pg_fails():
    """Mongo client must be closed when PG pool creation fails mid-connect."""
    from nce.garbage_collector import _connect_with_retry

    first_mongo = MagicMock()
    first_mongo.admin.command = AsyncMock(return_value={"ok": 1})
    first_mongo.close = MagicMock()

    second_mongo = MagicMock()
    second_mongo.admin.command = AsyncMock(return_value={"ok": 1})

    mock_pool = MagicMock()

    with (
        patch(
            "nce.garbage_collector.AsyncIOMotorClient",
            side_effect=[first_mongo, second_mongo],
        ),
        patch(
            "nce.garbage_collector.asyncpg.create_pool",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("pg down"), mock_pool],
        ),
        patch("nce.garbage_collector.asyncio.sleep", new_callable=AsyncMock),
    ):
        mongo, pool = await _connect_with_retry()

    first_mongo.close.assert_called_once()
    assert mongo is second_mongo
    assert pool is mock_pool


@pytest.mark.asyncio
async def test_acquire_gc_lock_returns_none_when_not_acquired():
    from nce.garbage_collector import _acquire_gc_lock

    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=False)

    result = await _acquire_gc_lock(mock_client)

    assert result is None


@pytest.mark.asyncio
async def test_acquire_gc_lock_returns_client_when_acquired():
    from nce.garbage_collector import _acquire_gc_lock

    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=True)

    result = await _acquire_gc_lock(mock_client)

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_release_gc_lock_deletes_key_and_closes():
    from nce.garbage_collector import _release_gc_lock

    mock_client = AsyncMock()
    mock_client.eval = AsyncMock(return_value=1)

    await _release_gc_lock(mock_client, "token")

    mock_client.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_gc_loop_releases_lock_on_collect_error():
    from nce.garbage_collector import run_gc_loop

    mock_mongo = MagicMock()
    mock_mongo.close = MagicMock()
    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()
    mock_lock = AsyncMock()

    sleep_calls = 0

    async def _sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            raise asyncio.CancelledError()

    with (
        patch(
            "nce.garbage_collector._connect_with_retry",
            new_callable=AsyncMock,
            return_value=(mock_mongo, mock_pool),
        ),
        patch(
            "nce.garbage_collector._acquire_gc_lock",
            new_callable=AsyncMock,
            return_value=mock_lock,
        ),
        patch(
            "nce.garbage_collector._collect_orphans",
            new_callable=AsyncMock,
            side_effect=RuntimeError("collect boom"),
        ),
        patch(
            "nce.garbage_collector._release_gc_lock",
            new_callable=AsyncMock,
        ) as mock_release,
        patch("nce.garbage_collector.asyncio.sleep", side_effect=_sleep),
    ):
        with pytest.raises(asyncio.CancelledError):
            await run_gc_loop()

    mock_release.assert_awaited_once()
    assert mock_release.call_args[0][1] == mock_lock


@pytest.mark.asyncio
async def test_run_gc_loop_skips_collect_when_lock_not_acquired():
    from nce.garbage_collector import run_gc_loop

    mock_mongo = MagicMock()
    mock_mongo.close = MagicMock()
    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()

    with (
        patch(
            "nce.garbage_collector._connect_with_retry",
            new_callable=AsyncMock,
            return_value=(mock_mongo, mock_pool),
        ),
        patch(
            "nce.garbage_collector._acquire_gc_lock",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "nce.garbage_collector._collect_orphans",
            new_callable=AsyncMock,
        ) as mock_collect,
        patch(
            "nce.garbage_collector.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await run_gc_loop()

    mock_collect.assert_not_awaited()


@pytest.mark.asyncio
async def test_collect_orphans_find_uses_max_time_ms(mock_pg_pool, sample_namespaces):
    from datetime import datetime, timedelta

    from nce.garbage_collector import _collect_orphans

    stale = {
        "_id": "507f1f77bcf86cd799439011",
        "ingested_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }

    async def _async_cursor(docs):
        for d in docs:
            yield d

    def _find_chain(docs):
        cursor = MagicMock()
        cursor.max_time_ms = MagicMock(return_value=_async_cursor(docs))
        return cursor

    episodes_find = _find_chain([stale])
    code_find = _find_chain([])

    episodes_col = MagicMock()
    episodes_col.find = MagicMock(return_value=episodes_find)
    episodes_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
    code_col = MagicMock()
    code_col.find = MagicMock(return_value=code_find)
    code_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))

    mongo_client = MagicMock()
    mongo_client.memory_archive = {"episodes": episodes_col, "code_files": code_col}

    with (
        patch(
            "nce.garbage_collector._fetch_all_namespaces",
            new_callable=AsyncMock,
            return_value=sample_namespaces,
        ),
        patch(
            "nce.garbage_collector._fetch_pg_refs",
            new_callable=AsyncMock,
            return_value=set(),
        ),
        patch(
            "nce.garbage_collector._clean_orphaned_cascade",
            new_callable=AsyncMock,
            return_value={"salience": 0, "contradictions": 0},
        ),
    ):
        await _collect_orphans(mongo_client, mock_pg_pool)

    episodes_find.max_time_ms.assert_called_once_with(30_000)
    code_find.max_time_ms.assert_called_once_with(30_000)


@pytest.mark.asyncio
async def test_run_gc_loop_cancelled_error_propagates():
    from nce.garbage_collector import run_gc_loop

    mock_mongo = MagicMock()
    mock_mongo.close = MagicMock()
    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()
    mock_lock = AsyncMock()

    sleep_calls = 0

    async def _sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        raise asyncio.CancelledError()

    with (
        patch(
            "nce.garbage_collector._connect_with_retry",
            new_callable=AsyncMock,
            return_value=(mock_mongo, mock_pool),
        ),
        patch(
            "nce.garbage_collector._acquire_gc_lock",
            new_callable=AsyncMock,
            return_value=mock_lock,
        ),
        patch(
            "nce.garbage_collector._collect_orphans",
            new_callable=AsyncMock,
            return_value={"deleted_docs": 0, "deleted_salience": 0, "deleted_contradictions": 0},
        ),
        patch("nce.garbage_collector._release_gc_lock", new_callable=AsyncMock),
        patch("nce.garbage_collector.asyncio.sleep", side_effect=_sleep),
    ):
        with pytest.raises(asyncio.CancelledError):
            await run_gc_loop()


@pytest.mark.asyncio
async def test_fetch_pg_refs_propagates_exception():
    from nce.garbage_collector import _fetch_pg_refs

    pool = MagicMock()
    pool.acquire.side_effect = RuntimeError("PG error")

    with pytest.raises(RuntimeError, match="PG error"):
        await _fetch_pg_refs(pool, [uuid4()])


@pytest.mark.asyncio
async def test_fetch_minio_refs_propagates_exception():
    from nce.garbage_collector import _fetch_minio_refs

    pool = MagicMock()
    pool.acquire.side_effect = RuntimeError("MinIO reference query error")

    with pytest.raises(RuntimeError, match="MinIO reference query error"):
        await _fetch_minio_refs(pool, [uuid4()])


@pytest.mark.asyncio
async def test_collect_minio_orphans_sweeps_incomplete_uploads():
    from datetime import datetime, timedelta, timezone

    from nce.garbage_collector import _collect_minio_orphans

    minio_client = MagicMock()

    bucket = MagicMock()
    bucket.name = "mcp-test-bucket"
    minio_client.list_buckets.return_value = [bucket]

    minio_client.list_objects.return_value = []

    upload_stale = MagicMock()
    upload_stale.object_name = "stale-upload"
    upload_stale.upload_id = "stale-id"
    upload_stale.initiated_time = datetime.now(timezone.utc) - timedelta(days=2)

    upload_fresh = MagicMock()
    upload_fresh.object_name = "fresh-upload"
    upload_fresh.upload_id = "fresh-id"
    upload_fresh.initiated_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    res = MagicMock()
    res.uploads = [upload_stale, upload_fresh]
    res.is_truncated = False

    minio_client._list_multipart_uploads.return_value = res

    count = await _collect_minio_orphans(minio_client, minio_refs=set())

    minio_client._abort_multipart_upload.assert_called_once_with(
        "mcp-test-bucket", "stale-upload", "stale-id"
    )
    assert count == 1


# ---------------------------------------------------------------------------
# Batch 58 — R-B reverse integrity sweep (PG ref → missing Mongo doc)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reverse_sweep_soft_retires_dangling_and_leaves_healthy(
    pg_pool, make_namespace
) -> None:
    """R-B: a memory whose Mongo episodes doc is missing is soft-retired + alerted;
    a memory whose Mongo doc is present is left untouched.

    Exercises real Postgres (RLS-scoped UPDATE valid_to) and real MongoDB, then
    asserts persisted DB state — not just that a function was called.
    """
    import os
    from datetime import datetime, timedelta

    from bson import ObjectId
    from motor.motor_asyncio import AsyncIOMotorClient
    from nce.db_utils import scoped_pg_session
    from nce.garbage_collector import _collect_reverse_orphans

    ns_id = await make_namespace()
    agent_id = "test-reverse-sweep-agent"

    # created_at must be older than the orphan-age cutoff so the sweep considers
    # the rows (mirrors the forward GC's freshly-written-payload guard).
    old_created = datetime.now(timezone.utc) - timedelta(days=365)

    # Healthy memory: Mongo episodes doc exists.
    healthy_oid = ObjectId()
    healthy_ref = str(healthy_oid)
    healthy_memory_id = uuid4()

    # Dangling memory: payload_ref points at an ObjectId never written to Mongo.
    dangling_oid = ObjectId()
    dangling_ref = str(dangling_oid)
    dangling_memory_id = uuid4()

    mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    mongo_client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5_000)
    try:
        try:
            await mongo_client.admin.command("ping")
        except Exception as exc:  # noqa: BLE001 - skip if Mongo unreachable
            pytest.skip(f"MongoDB not reachable for integration test: {exc}")

        db = mongo_client.memory_archive
        # Insert ONLY the healthy doc; the dangling ref is intentionally absent.
        await db.episodes.insert_one(
            {"_id": healthy_oid, "raw_data": "present", "source": "test_reverse_sweep"}
        )

        try:
            async with scoped_pg_session(pg_pool, ns_id) as conn:
                await conn.execute(
                    """
                    INSERT INTO memories (id, namespace_id, agent_id,
                                          assertion_type, memory_type, payload_ref,
                                          metadata, created_at)
                    VALUES
                        ($1, $3, $4, 'fact', 'episodic', $5, '{}'::jsonb, $7),
                        ($2, $3, $4, 'fact', 'episodic', $6, '{}'::jsonb, $7)
                    """,
                    healthy_memory_id,
                    dangling_memory_id,
                    ns_id,
                    agent_id,
                    healthy_ref,
                    dangling_ref,
                    old_created,
                )

            # Patch the operator alert so we can assert it fired without I/O.
            alert_mock = AsyncMock()
            with patch("nce.notifications.dispatcher.dispatch_alert", alert_mock):
                retired = await _collect_reverse_orphans(mongo_client, pg_pool, [ns_id])

            # Exactly the dangling memory was soft-retired.
            assert retired == 1

            async with scoped_pg_session(pg_pool, ns_id) as conn:
                dangling_valid_to = await conn.fetchval(
                    "SELECT valid_to FROM memories WHERE id = $1 AND namespace_id = $2",
                    dangling_memory_id,
                    ns_id,
                )
                healthy_valid_to = await conn.fetchval(
                    "SELECT valid_to FROM memories WHERE id = $1 AND namespace_id = $2",
                    healthy_memory_id,
                    ns_id,
                )

            # Dangling row soft-retired (valid_to set); healthy row untouched.
            assert dangling_valid_to is not None, "dangling memory must be soft-retired"
            assert healthy_valid_to is None, "healthy memory must be left untouched"

            # An operator alert was dispatched naming the dangling memory.
            assert alert_mock.await_count >= 1
            dispatched_text = " ".join(
                str(arg) for call in alert_mock.await_args_list for arg in call.args
            )
            assert str(dangling_memory_id) in dispatched_text
            assert str(healthy_memory_id) not in dispatched_text
        finally:
            # Clean up PG rows (best-effort) and the healthy Mongo doc.
            try:
                async with scoped_pg_session(pg_pool, ns_id) as conn:
                    await conn.execute(
                        "DELETE FROM memories WHERE namespace_id = $1 AND id = ANY($2::uuid[])",
                        ns_id,
                        [healthy_memory_id, dangling_memory_id],
                    )
            except Exception:
                pass
            await db.episodes.delete_one({"_id": healthy_oid})
    finally:
        mongo_client.close()
