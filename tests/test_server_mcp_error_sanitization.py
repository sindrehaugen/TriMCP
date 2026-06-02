"""Production-safe JSON-RPC error payloads from server.call_tool (P0-B)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trimcp.config import cfg
from trimcp.quotas import null_reservation


def _parse_error_payload(result: list) -> dict:
    assert len(result) == 1
    body = json.loads(result[0].text)
    assert "error" in body
    return body["error"]


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.redis_client = AsyncMock()
    engine.redis_client.get.return_value = None
    # Ensure the tool-disabled interceptor always passes (tools are enabled by default)
    engine.redis_client.hexists = AsyncMock(return_value=False)
    engine.pg_pool = MagicMock()
    return engine


@pytest.fixture(autouse=True)
def _server_engine(mock_engine):
    import server

    original = server.engine
    server.engine = mock_engine
    yield
    server.engine = original


@pytest.fixture(autouse=True)
def _disable_quotas(monkeypatch):
    monkeypatch.setattr("trimcp.quotas.cfg.TRIMCP_QUOTAS_ENABLED", False)


@pytest.fixture(autouse=True)
def _prod_safe_errors(monkeypatch):
    """Keep error sanitization active even if another test reloaded trimcp.config."""

    import trimcp.mcp_errors as mcp_errors_mod

    monkeypatch.setattr(cfg, "IS_DEV", False)
    monkeypatch.setattr(mcp_errors_mod.cfg, "IS_DEV", False)


@pytest.mark.asyncio
async def test_call_tool_internal_error_hides_detail_in_prod(monkeypatch, mock_engine):
    monkeypatch.setattr(cfg, "IS_DEV", False)

    import server as srv

    async def _boom(*_a, **_k):
        raise RuntimeError("postgresql://user:secret@db:5432/memory_meta")

    import trimcp.mcp_stdio_dispatch as dispatch

    with patch.object(dispatch.memory_mcp_handlers, "handle_store_memory", _boom):
        err = _parse_error_payload(
            await srv.call_tool(
                "store_memory",
                {
                    "namespace_id": str(uuid.uuid4()),
                    "agent_id": "agent",
                    "content": "hello",
                },
            )
        )
    data = err.get("data") or {}
    assert err["code"] == -32603
    assert "detail" not in data
    assert "postgresql://" not in json.dumps(data)
    assert data.get("request_id")
    assert data.get("type") == "RuntimeError"


@pytest.mark.asyncio
async def test_call_tool_scope_error_hides_detail_in_prod(monkeypatch):
    monkeypatch.setattr(cfg, "IS_DEV", False)

    import server as srv

    from trimcp.auth import ScopeError

    async def _scoped(*_a, **_k):
        raise ScopeError("admin", "invalid admin_api_key")

    import trimcp.mcp_stdio_dispatch as dispatch

    with patch.object(dispatch.admin_mcp_handlers, "handle_manage_namespace", _scoped):
        with patch(
            "trimcp.mcp_stdio_dispatch._consume_quota_for_mcp_tool",
            AsyncMock(return_value=null_reservation()),
        ):
            err = _parse_error_payload(
                await srv.call_tool(
                    "manage_namespace",
                    {"namespace_id": str(uuid.uuid4()), "command": "list"},
                )
            )
    data = err.get("data") or {}
    assert err["code"] == -32005
    assert "detail" not in data
    assert "invalid admin_api_key" not in json.dumps(data)


def test_check_admin_delegates_to_validate_scope(monkeypatch):
    monkeypatch.delenv("TRIMCP_ADMIN_OVERRIDE", raising=False)
    monkeypatch.setenv("TRIMCP_ADMIN_API_KEY", "server-secret-key")

    import server as srv

    with pytest.raises(ValueError) as ei:
        srv._check_admin({"admin_api_key": "wrong"})
    assert "(-32001)" in str(ei.value)

    srv._check_admin({"admin_api_key": "server-secret-key"})
