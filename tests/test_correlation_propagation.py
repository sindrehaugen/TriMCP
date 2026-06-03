"""
tests/test_correlation_propagation.py

Unit coverage for trimcp.correlation ContextVar isolation.

Exercises:
  - get_correlation_id() returns None outside a request context
  - require_correlation_id() raises RuntimeError outside a request context
  - set/get round-trip returns the correct UUID
  - reset() restores None after the request boundary
  - Concurrent async tasks each see their own independent correlation ID
  - append_event auto-picks up the ContextVar value when not explicitly passed
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from uuid import UUID, uuid4

import pytest

from tests.fixtures.event_log_params import minimal_store_memory_params
from tests.fixtures.fake_asyncpg import RecordingFakeConnection
from trimcp import event_log as event_log_mod
from trimcp.correlation import (
    correlation_id_var,
    get_correlation_id,
    require_correlation_id,
)
from trimcp.event_log import append_event

_RAW_SIGNING_SECRET = hashlib.sha256(b"pytest-correlation-hmac-secret").digest()


@pytest.fixture(autouse=True)
def _patch_active_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_active_key(_conn: object) -> tuple[str, bytes]:
        return ("pytest-key-id", _RAW_SIGNING_SECRET)

    monkeypatch.setattr(event_log_mod, "get_active_key", _fake_active_key)


@pytest.fixture
def namespace_id() -> UUID:
    return uuid4()


# ── get_correlation_id ──────────────────────────────────────────────────────


def test_get_correlation_id_returns_none_when_unset() -> None:
    assert get_correlation_id() is None


def test_get_correlation_id_returns_uuid_when_set() -> None:
    cid = uuid4()
    token = correlation_id_var.set(cid)
    try:
        assert get_correlation_id() == cid
    finally:
        correlation_id_var.reset(token)


# ── require_correlation_id ──────────────────────────────────────────────────


def test_require_correlation_id_raises_when_unset() -> None:
    with pytest.raises(RuntimeError, match="correlation_id_var is not set"):
        require_correlation_id()


def test_require_correlation_id_returns_uuid_when_set() -> None:
    cid = uuid4()
    token = correlation_id_var.set(cid)
    try:
        assert require_correlation_id() == cid
    finally:
        correlation_id_var.reset(token)


# ── reset restores None ─────────────────────────────────────────────────────


def test_reset_restores_none_after_request_boundary() -> None:
    assert get_correlation_id() is None
    cid = uuid4()
    token = correlation_id_var.set(cid)
    assert get_correlation_id() == cid
    correlation_id_var.reset(token)
    assert get_correlation_id() is None


# ── concurrent async isolation ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_tasks_see_independent_correlation_ids() -> None:
    """Two concurrent coroutines that each set correlation_id_var see different values.

    This is the core ContextVar guarantee: each asyncio.Task has its own copy
    of the context. Setting the var in one task does not bleed into another.
    """
    results: dict[int, uuid.UUID | None] = {}

    async def worker(slot: int, cid: uuid.UUID) -> None:
        token = correlation_id_var.set(cid)
        try:
            await asyncio.sleep(0)  # yield to allow interleaving
            results[slot] = get_correlation_id()
        finally:
            correlation_id_var.reset(token)

    cid_a = uuid4()
    cid_b = uuid4()
    assert cid_a != cid_b

    await asyncio.gather(worker(0, cid_a), worker(1, cid_b))

    assert results[0] == cid_a
    assert results[1] == cid_b


@pytest.mark.asyncio
async def test_nested_task_inherits_then_isolates_parent_context() -> None:
    """A child task spawned from within a set context inherits the value at
    creation time but resetting inside the child does not affect the parent."""
    parent_cid = uuid4()
    child_saw: list[uuid.UUID | None] = []
    parent_after_child: list[uuid.UUID | None] = []

    async def child_worker() -> None:
        child_saw.append(get_correlation_id())
        # Override in child — must not propagate to parent.
        child_token = correlation_id_var.set(uuid4())
        await asyncio.sleep(0)
        correlation_id_var.reset(child_token)

    token = correlation_id_var.set(parent_cid)
    try:
        await asyncio.create_task(child_worker())
        parent_after_child.append(get_correlation_id())
    finally:
        correlation_id_var.reset(token)

    # Child inherited parent value at spawn time.
    assert child_saw[0] == parent_cid
    # Parent's correlation_id is unchanged after child ran.
    assert parent_after_child[0] == parent_cid


# ── append_event auto-pulls from ContextVar ─────────────────────────────────


@pytest.mark.asyncio
async def test_append_event_captures_correlation_id_from_context(
    namespace_id: UUID,
) -> None:
    """append_event reads correlation_id from the ContextVar when not supplied."""
    cid = uuid4()
    conn = RecordingFakeConnection()

    token = correlation_id_var.set(cid)
    try:
        async with conn.transaction():
            await append_event(
                conn=conn,
                namespace_id=namespace_id,
                agent_id="test-agent",
                event_type="store_memory",
                params=minimal_store_memory_params(),
            )
    finally:
        correlation_id_var.reset(token)

    assert len(conn.event_inserts) == 1
    assert conn.event_inserts[0]["correlation_id"] == cid


@pytest.mark.asyncio
async def test_append_event_stores_none_correlation_id_when_context_unset(
    namespace_id: UUID,
) -> None:
    """When no ContextVar is active and no explicit cid is passed, correlation_id is None."""
    assert get_correlation_id() is None
    conn = RecordingFakeConnection()

    async with conn.transaction():
        await append_event(
            conn=conn,
            namespace_id=namespace_id,
            agent_id="test-agent",
            event_type="store_memory",
            params=minimal_store_memory_params(),
        )

    assert conn.event_inserts[0]["correlation_id"] is None


@pytest.mark.asyncio
async def test_append_event_explicit_cid_overrides_context(
    namespace_id: UUID,
) -> None:
    """An explicitly passed correlation_id takes precedence over the ContextVar."""
    context_cid = uuid4()
    explicit_cid = uuid4()
    assert context_cid != explicit_cid

    conn = RecordingFakeConnection()
    token = correlation_id_var.set(context_cid)
    try:
        async with conn.transaction():
            await append_event(
                conn=conn,
                namespace_id=namespace_id,
                agent_id="test-agent",
                event_type="store_memory",
                params=minimal_store_memory_params(),
                correlation_id=explicit_cid,
            )
    finally:
        correlation_id_var.reset(token)

    assert conn.event_inserts[0]["correlation_id"] == explicit_cid
