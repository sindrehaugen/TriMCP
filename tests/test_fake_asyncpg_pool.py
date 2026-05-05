"""Sanity checks for tests/fixtures/fake_asyncpg.py pool shim."""

from __future__ import annotations

import pytest

from tests.fixtures.fake_asyncpg import RecordingFakeConnection, RecordingFakePool, make_fake_pool


@pytest.mark.asyncio
async def test_fake_pool_acquire_returns_same_connection() -> None:
    pool, conn = make_fake_pool()
    got = await pool.acquire()
    assert got is conn
    await pool.close()


@pytest.mark.asyncio
async def test_fake_connection_transaction_depth() -> None:
    conn = RecordingFakeConnection()
    assert conn._tx_depth == 0
    async with conn.transaction():
        assert conn._tx_depth == 1
        async with conn.transaction():
            assert conn._tx_depth == 2
        assert conn._tx_depth == 1
    assert conn._tx_depth == 0
