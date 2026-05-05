"""Unit tests for Phase 3.2 resource quotas (async consume + rollback)."""

from __future__ import annotations

import hashlib
import hmac as _hmac
import importlib.util
import json
import sys
import time
import types
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Route
from starlette.testclient import TestClient

import trimcp.quotas as quotas
from trimcp.auth import HMACAuthMiddleware
from trimcp.quotas import QuotaExceededError


def _register_mcp_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow ``import server`` in environments without the MCP SDK wheel."""

    def _passthrough_decorator(fn):
        return fn

    class _FakeServer:
        def __init__(self, _name: str) -> None:
            pass

        def list_tools(self):
            return _passthrough_decorator

        def call_tool(self):
            return _passthrough_decorator

    @asynccontextmanager
    async def _fake_stdio():
        yield (MagicMock(), MagicMock())

    mcp = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_server_stdio = types.ModuleType("mcp.server.stdio")
    mcp_types = types.ModuleType("mcp.types")

    mcp_server.Server = _FakeServer
    mcp_server_stdio.stdio_server = _fake_stdio
    mcp_types.Tool = MagicMock()
    mcp_types.TextContent = MagicMock()

    monkeypatch.setitem(sys.modules, "mcp", mcp)
    monkeypatch.setitem(sys.modules, "mcp.server", mcp_server)
    monkeypatch.setitem(sys.modules, "mcp.server.stdio", mcp_server_stdio)
    monkeypatch.setitem(sys.modules, "mcp.types", mcp_types)


@pytest.mark.asyncio
async def test_consume_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("trimcp.quotas.cfg.TRIMCP_QUOTAS_ENABLED", False)
    pool = MagicMock()
    ns = uuid.uuid4()
    res = await quotas.consume_resources(
        pool,
        namespace_id=ns,
        agent_id="a1",
        amounts={quotas.RESOURCE_LLM_TOKENS: 100},
    )
    assert res.is_empty
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_consume_updates_matching_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("trimcp.quotas.cfg.TRIMCP_QUOTAS_ENABLED", True)

    ns_id = uuid.uuid4()
    qrow_ns = uuid.uuid4()

    conn = AsyncMock()
    conn.fetch.return_value = [{"id": qrow_ns, "agent_id": None}]
    conn.fetchrow.return_value = {"id": qrow_ns}

    tx = AsyncMock()
    conn.transaction = MagicMock(return_value=tx)
    tx.__aenter__.return_value = None
    tx.__aexit__.return_value = None

    pool = MagicMock()
    acq = AsyncMock()
    acq.__aenter__.return_value = conn
    acq.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=acq)

    res = await quotas.consume_resources(
        pool,
        namespace_id=ns_id,
        agent_id="agent-x",
        amounts={quotas.RESOURCE_LLM_TOKENS: 10},
    )
    assert len(res.steps) == 1
    assert res.steps[0] == (qrow_ns, 10)
    conn.fetch.assert_called()
    conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_consume_raises_when_limit_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("trimcp.quotas.cfg.TRIMCP_QUOTAS_ENABLED", True)

    ns_id = uuid.uuid4()
    qrow_ns = uuid.uuid4()

    conn = AsyncMock()
    conn.fetch.return_value = [{"id": qrow_ns, "agent_id": None}]
    conn.fetchrow.return_value = None

    tx = AsyncMock()
    conn.transaction = MagicMock(return_value=tx)
    tx.__aenter__.return_value = None
    tx.__aexit__.return_value = None

    pool = MagicMock()
    acq = AsyncMock()
    acq.__aenter__.return_value = conn
    acq.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=acq)

    with pytest.raises(QuotaExceededError):
        await quotas.consume_resources(
            pool,
            namespace_id=ns_id,
            agent_id="a",
            amounts={quotas.RESOURCE_LLM_TOKENS: 999},
        )


def test_tool_quota_plan_store_memory_shapes() -> None:
    ns = str(uuid.uuid4())
    plan = quotas.tool_quota_plan(
        "store_memory",
        {
            "namespace_id": ns,
            "agent_id": "bot",
            "content": "hello",
            "summary": "hi",
            "heavy_payload": "x" * 40,
        },
    )
    assert plan is not None
    n, agent, amounts = plan
    assert str(n) == ns
    assert agent == "bot"
    assert quotas.RESOURCE_LLM_TOKENS in amounts
    assert quotas.RESOURCE_STORAGE_BYTES in amounts
    assert amounts[quotas.RESOURCE_MEMORY_COUNT] == 1


def test_tool_quota_plan_unknown_returns_none() -> None:
    assert quotas.tool_quota_plan("graph_search", {}) is None


@pytest.mark.asyncio
async def test_reservation_rollback_skips_when_no_pool() -> None:
    r = quotas.null_reservation()
    await r.rollback()


@pytest.mark.asyncio
async def test_reservation_rollback_executes_decrements() -> None:
    conn = AsyncMock()
    tx = AsyncMock()
    conn.transaction = MagicMock(return_value=tx)
    tx.__aenter__.return_value = None
    tx.__aexit__.return_value = None

    pool = MagicMock()
    acq = AsyncMock()
    acq.__aenter__.return_value = conn
    acq.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=acq)

    qid = uuid.uuid4()
    r = quotas.QuotaReservation(pool=pool, steps=[(qid, 5)])
    await r.rollback()
    assert r.is_empty
    conn.execute.assert_called_once()


# ---------------------------------------------------------------------------
# HTTP 429 (admin API) + MCP tool path (-32013) — no real Postgres / Redis
# ---------------------------------------------------------------------------

_HMAC_KEY = "pytest-quota-hmac-secret-not-for-prod"


def _signed_post(path: str, body: dict) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body).encode("utf-8")
    ts = int(time.time())
    parts = ["POST", path, str(ts), hashlib.sha256(raw).hexdigest()]
    canonical = "\n".join(parts)
    sig = _hmac.new(_HMAC_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-TriMCP-Timestamp": str(ts),
        "Authorization": f"HMAC-SHA256 {sig}",
        "Content-Type": "application/json",
    }
    return raw, headers


def test_tool_quota_plan_a2a_query_shared() -> None:
    consumer_ns = str(uuid.uuid4())
    plan = quotas.tool_quota_plan(
        "a2a_query_shared",
        {
            "consumer_namespace_id": consumer_ns,
            "consumer_agent_id": "agent-b",
            "query": "what did we decide?",
        },
    )
    assert plan is not None
    ns, agent, amounts = plan
    assert str(ns) == consumer_ns
    assert agent == "agent-b"
    assert quotas.RESOURCE_LLM_TOKENS in amounts


def test_admin_api_search_returns_429_when_quota_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    import admin_server as adm

    async def _boom(*_a, **_k):
        raise QuotaExceededError("namespace cap reached")

    monkeypatch.setattr("trimcp.quotas.consume_for_tool", _boom)
    monkeypatch.setattr(adm, "engine", MagicMock())

    app = Starlette(
        middleware=[
            Middleware(
                HMACAuthMiddleware,
                protected_prefix="/api/",
                api_key=_HMAC_KEY,
            )
        ],
        routes=[Route("/api/search", endpoint=adm.api_search, methods=["POST"])],
    )

    body = {
        "namespace_id": str(uuid.uuid4()),
        "agent_id": "alpha",
        "query": "hello",
    }
    raw, hdrs = _signed_post("/api/search", body)
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post("/api/search", content=raw, headers=hdrs)
    assert r.status_code == 429
    payload = r.json()
    assert "error" in payload
    assert "cap" in payload["error"].lower() or "quota" in payload["error"].lower()


@pytest.mark.asyncio
async def test_mcp_call_tool_surfaces_quota_as_32013(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP stdio path: quota exhaustion maps to ValueError with -32013 (rate limit / quota)."""

    monkeypatch.delitem(sys.modules, "server", raising=False)
    if importlib.util.find_spec("mcp") is None:
        _register_mcp_stubs(monkeypatch)
    import server as srv

    eng = MagicMock()
    eng.pg_pool = MagicMock()
    eng.redis_client = MagicMock()
    eng.redis_client.get = AsyncMock(return_value=None)
    eng.redis_client.incr = AsyncMock(return_value=1)
    eng.redis_client.setex = AsyncMock()
    eng.semantic_search = AsyncMock(return_value=[])
    monkeypatch.setattr(srv, "engine", eng)

    async def _boom(pool, tool, args):
        raise QuotaExceededError("no capacity")

    monkeypatch.setattr("trimcp.quotas.consume_for_tool", _boom)

    with pytest.raises(ValueError, match=r"-32013"):
        await srv.call_tool(
            "semantic_search",
            {
                "namespace_id": str(uuid.uuid4()),
                "agent_id": "agent-a",
                "query": "find the spec",
            },
        )
