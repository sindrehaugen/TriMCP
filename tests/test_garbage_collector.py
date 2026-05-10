"""
Tests for GC namespace-aware mode (garbage_collector.py).

Verifies that the GC iterates over all namespaces with set_namespace_context()
before RLS-protected operations, and that helpers return gracefully on error.
"""

from __future__ import annotations

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
    # AsyncMock.__aenter__ returns a new mock by default; wire it to return itself
    conn.__aenter__.return_value = conn
    conn.__aexit__.return_value = False
    # fetch returns rows with 'id' field
    conn.fetch = AsyncMock(return_value=[{"id": ns} for ns in sample_namespaces])
    conn.execute = AsyncMock(return_value="DELETE 3")
    pool.acquire = MagicMock(return_value=conn)
    return pool


# ---------------------------------------------------------------------------
# _fetch_all_namespaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_all_namespaces_returns_uuids(mock_pg_pool, sample_namespaces):
    from trimcp.garbage_collector import _fetch_all_namespaces

    result = await _fetch_all_namespaces(mock_pg_pool)
    assert result == sample_namespaces


@pytest.mark.asyncio
async def test_fetch_all_namespaces_empty():
    from trimcp.garbage_collector import _fetch_all_namespaces

    pool = MagicMock()
    conn = AsyncMock()
    conn.__aenter__.return_value = conn
    conn.__aexit__.return_value = False
    conn.fetch = AsyncMock(return_value=[])
    pool.acquire = MagicMock(return_value=conn)
    result = await _fetch_all_namespaces(pool)
    assert result == []


# ---------------------------------------------------------------------------
# _clean_orphaned_kg_nodes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_orphaned_cascade_sets_context(mock_pg_pool, sample_namespaces):
    """Verify set_namespace_context is called before the unified CTE cascade."""
    from trimcp.garbage_collector import _clean_orphaned_cascade

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
        "trimcp.garbage_collector.set_namespace_context", new_callable=AsyncMock
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
    from trimcp.garbage_collector import _clean_orphaned_cascade

    bad_pool = MagicMock()
    bad_pool.acquire.side_effect = RuntimeError("Connection refused")

    with patch(
        "trimcp.garbage_collector.set_namespace_context", new_callable=AsyncMock
    ):
        counts = await _clean_orphaned_cascade(bad_pool, uuid4())
    assert counts == {"salience": 0, "contradictions": 0}


@pytest.mark.asyncio
async def test_clean_orphaned_cascade_handles_null_row(mock_pg_pool):
    """If fetchrow returns None, return all-zero counts gracefully."""
    from trimcp.garbage_collector import _clean_orphaned_cascade

    conn = mock_pg_pool.acquire.return_value.__aenter__.return_value
    conn.fetchrow = AsyncMock(return_value=None)

    counts = await _clean_orphaned_cascade(mock_pg_pool, uuid4())
    assert counts == {"salience": 0, "contradictions": 0}


@pytest.mark.asyncio
async def test_clean_orphaned_cascade_passes_namespace_id_to_cte(mock_pg_pool):
    """Verify namespace_id is passed as a query parameter to the CTE fetchrow call."""
    from trimcp.garbage_collector import _clean_orphaned_cascade

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

    with patch(
        "trimcp.garbage_collector.set_namespace_context", new_callable=AsyncMock
    ):
        counts = await _clean_orphaned_cascade(mock_pg_pool, ns_id)

    # Verify the namespace_id UUID was passed as the second argument to fetchrow
    call_args, call_kwargs = conn.fetchrow.call_args
    # The SQL text is the first positional arg, namespace_id is the second
    assert (
        len(call_args) >= 2
    ), f"Expected at least 2 positional args, got {len(call_args)}"
    assert (
        call_args[1] == ns_id
    ), f"Expected namespace_id {ns_id} but got {call_args[1]}"

    # Verify the SQL contains the explicit namespace_id filter pattern
    sql = call_args[0]
    assert "$1::uuid" in sql, "Expected parameterised namespace_id filter in CTE SQL"
    assert (
        "namespace_id = $1::uuid" in sql
    ), "Expected explicit namespace_id WHERE clause in CTE"
    # Should appear at least 5 times: existing_memories, 4 orphan sub-selects, 2 DELETEs
    namespace_filter_count = sql.count("namespace_id = $1::uuid")
    assert (
        namespace_filter_count >= 5
    ), f"Expected at least 5 explicit namespace_id filters, found {namespace_filter_count}"

    assert counts == {"salience": 5, "contradictions": 3}


@pytest.mark.asyncio
async def test_fetch_pg_refs_sets_context_per_namespace():
    """Verify _fetch_pg_refs sets namespace context for each namespace."""
    from trimcp.garbage_collector import _fetch_pg_refs

    ns_list = [uuid4(), uuid4()]

    pool = MagicMock()
    conn = AsyncMock()
    conn.__aenter__.return_value = conn
    conn.__aexit__.return_value = False
    conn.fetch = AsyncMock(return_value=[])  # empty result — no refs
    pool.acquire = MagicMock(return_value=conn)

    with patch(
        "trimcp.garbage_collector.set_namespace_context", new_callable=AsyncMock
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
async def test_collect_orphans_iterates_over_all_namespaces(
    mock_pg_pool, sample_namespaces
):
    """Verify _collect_orphans calls unified cascade for each namespace."""
    from datetime import datetime, timedelta

    from trimcp.garbage_collector import _collect_orphans

    stale = {
        "_id": "507f1f77bcf86cd799439011",
        "ingested_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }

    async def _async_cursor(docs):
        for d in docs:
            yield d

    # GC uses db[col_name] (subscript), not db.col_name (attribute)
    episodes_col = MagicMock()
    episodes_col.find = MagicMock(return_value=_async_cursor([stale]))
    episodes_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    code_col = MagicMock()
    code_col.find = MagicMock(return_value=_async_cursor([]))
    code_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))

    mongo_client = MagicMock()
    mongo_client.memory_archive = {"episodes": episodes_col, "code_files": code_col}

    with (
        patch(
            "trimcp.garbage_collector._clean_orphaned_cascade",
            new_callable=AsyncMock,
            return_value={"salience": 0, "contradictions": 0, "events": 0},
        ) as mock_cascade,
        patch(
            "trimcp.garbage_collector._fetch_pg_refs",
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
    """When no namespaces exist, skip PG maintenance passes entirely."""
    from datetime import datetime, timedelta

    from trimcp.garbage_collector import _collect_orphans

    stale = {
        "_id": "507f1f77bcf86cd799439011",
        "ingested_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }

    pool = MagicMock()
    conn = AsyncMock()
    conn.__aenter__.return_value = conn
    conn.__aexit__.return_value = False
    conn.fetch = AsyncMock(return_value=[])  # empty namespaces table
    pool.acquire = MagicMock(return_value=conn)

    async def _async_cursor(docs):
        for d in docs:
            yield d

    mongo_client = MagicMock()
    episodes_col = MagicMock()
    episodes_col.find = MagicMock(return_value=_async_cursor([stale]))
    episodes_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    code_col = MagicMock()
    code_col.find = MagicMock(return_value=_async_cursor([]))
    code_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
    mongo_client.memory_archive = {"episodes": episodes_col, "code_files": code_col}

    with (
        patch(
            "trimcp.garbage_collector._clean_orphaned_cascade", new_callable=AsyncMock
        ) as mock_cascade,
        patch(
            "trimcp.garbage_collector._fetch_pg_refs",
            new_callable=AsyncMock,
            return_value=set(),
        ),
    ):
        result = await _collect_orphans(mongo_client, pool)

    mock_cascade.assert_not_awaited()
    # No namespaces → PG maintenance skipped; doc orphan still cleaned
    assert isinstance(result, dict)
    assert "deleted_nodes" not in result
    assert result["deleted_salience"] == 0
    assert result["deleted_contradictions"] == 0
