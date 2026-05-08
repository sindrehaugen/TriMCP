"""
Tests for event_log WORM enforcement startup probe.

Verifies that ``verify_worm_enforcement()`` correctly detects:
- Expected: UPDATE and DELETE denied (InsufficientPrivilegeError)
- Critical: UPDATE or DELETE succeeds → RuntimeError raised
- Edge cases: table missing, unexpected errors
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import asyncpg
import pytest

from trimcp.event_log import verify_worm_enforcement

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conn() -> AsyncMock:
    """Return a mock asyncpg Connection with an AsyncMock execute."""
    c = AsyncMock(spec=asyncpg.Connection)
    c.execute = AsyncMock()
    return c


# ---------------------------------------------------------------------------
# Happy path — UPDATE and DELETE both denied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worm_update_denied_delete_denied():
    """UPDATE and DELETE both raise InsufficientPrivilegeError → probe passes."""
    conn = _conn()
    conn.execute.side_effect = [
        asyncpg.exceptions.InsufficientPrivilegeError("UPDATE denied"),
        asyncpg.exceptions.InsufficientPrivilegeError("DELETE denied"),
    ]

    # Should not raise
    await verify_worm_enforcement(conn)

    assert conn.execute.call_count == 2
    assert "UPDATE" in conn.execute.call_args_list[0][0][0]
    assert "DELETE" in conn.execute.call_args_list[1][0][0]


# ---------------------------------------------------------------------------
# Critical path — UPDATE or DELETE succeeds (WORM broken)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worm_update_succeeds_raises_runtime_error():
    """UPDATE succeeds → RuntimeError halts startup."""
    conn = _conn()
    conn.execute.side_effect = [
        None,  # UPDATE succeeds — DANGER
        asyncpg.exceptions.InsufficientPrivilegeError("DELETE denied"),
    ]

    with pytest.raises(RuntimeError, match="UPDATE on event_log succeeded"):
        await verify_worm_enforcement(conn)


@pytest.mark.asyncio
async def test_worm_delete_succeeds_raises_runtime_error():
    """DELETE succeeds → RuntimeError halts startup."""
    conn = _conn()
    conn.execute.side_effect = [
        asyncpg.exceptions.InsufficientPrivilegeError("UPDATE denied"),
        None,  # DELETE succeeds — DANGER
    ]

    with pytest.raises(RuntimeError, match="DELETE on event_log succeeded"):
        await verify_worm_enforcement(conn)


@pytest.mark.asyncio
async def test_worm_both_succeed_raises_on_update_first():
    """If both UPDATE and DELETE succeed, only UPDATE error is raised."""
    conn = _conn()
    conn.execute.side_effect = [None, None]  # both succeed

    with pytest.raises(RuntimeError, match="UPDATE on event_log succeeded"):
        await verify_worm_enforcement(conn)


# ---------------------------------------------------------------------------
# Edge cases — table missing, unexpected errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_missing_propagates_error():
    """If the table doesn't exist, the error propagates (not caught)."""
    conn = _conn()
    conn.execute.side_effect = asyncpg.exceptions.UndefinedTableError("event_log missing")

    with pytest.raises(asyncpg.exceptions.UndefinedTableError):
        await verify_worm_enforcement(conn)


@pytest.mark.asyncio
async def test_unexpected_postgres_error_propagates():
    """Non-privilege errors propagate unchanged."""
    conn = _conn()
    conn.execute.side_effect = asyncpg.exceptions.ConnectionFailureError("broken")

    with pytest.raises(asyncpg.exceptions.ConnectionFailureError):
        await verify_worm_enforcement(conn)


# ---------------------------------------------------------------------------
# SQL injection safety: WHERE FALSE clause prevents data mutation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_uses_where_false():
    """Both probes use WHERE FALSE so no rows can ever be affected."""
    conn = _conn()
    conn.execute.side_effect = [
        asyncpg.exceptions.InsufficientPrivilegeError("no"),
        asyncpg.exceptions.InsufficientPrivilegeError("no"),
    ]

    await verify_worm_enforcement(conn)

    update_sql = conn.execute.call_args_list[0][0][0]
    delete_sql = conn.execute.call_args_list[1][0][0]
    assert "WHERE FALSE" in update_sql
    assert "WHERE FALSE" in delete_sql


# ---------------------------------------------------------------------------
# Exception class verification — confirm we catch the right exception
# ---------------------------------------------------------------------------


def test_insufficient_privilege_is_expected_exception():
    """Confirm InsufficientPrivilegeError is the specific asyncpg exception."""
    exc = asyncpg.exceptions.InsufficientPrivilegeError("test")
    assert isinstance(exc, asyncpg.exceptions.PostgresError)
    # SQLSTATE 42501 = insufficient_privilege
    assert exc.sqlstate == "42501"
