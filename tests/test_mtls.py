"""Unit tests for trimcp/mtls.py — MTLSAuthMiddleware."""

from __future__ import annotations

import os

os.environ.setdefault("TRIMCP_MASTER_KEY", "dev-test-key-32chars-long!!")

from unittest.mock import AsyncMock, patch

import pytest

from trimcp.a2a import A2AMTLSError
from trimcp.mtls import DEFAULT_MTLS_ERROR_CODE, MTLSAuthMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scope(path: str = "/tasks/send") -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
    }


async def _collect_response(middleware: MTLSAuthMiddleware, scope: dict) -> dict:
    """Call the middleware and capture status_code + body from send()."""
    received: dict = {}

    async def receive():
        return {}

    async def send(message):
        if message["type"] == "http.response.start":
            received["status"] = message["status"]
        elif message["type"] == "http.response.body":
            received["body"] = message.get("body", b"")

    await middleware(scope, receive, send)
    return received


# ---------------------------------------------------------------------------
# Pass-through: non-http scope types
# ---------------------------------------------------------------------------


class TestNonHttpScope:
    @pytest.mark.asyncio
    async def test_websocket_scope_passes_through(self):
        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(downstream, enabled=True, protected_prefix="/")

        scope = {"type": "websocket", "path": "/tasks"}
        await mw(scope, AsyncMock(), AsyncMock())

        downstream.assert_awaited_once()


# ---------------------------------------------------------------------------
# Path prefix filtering
# ---------------------------------------------------------------------------


class TestPathPrefixFiltering:
    @pytest.mark.asyncio
    async def test_unprotected_path_bypasses_enforcement(self):
        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(downstream, enabled=True, protected_prefix="/tasks")

        scope = _make_scope(path="/health")
        await mw(scope, AsyncMock(), AsyncMock())

        downstream.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_protected_path_reaches_enforcement(self):
        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(
            downstream,
            enabled=True,
            protected_prefix="/tasks",
            strict=True,
        )

        with patch("trimcp.mtls.mtls_enforce", side_effect=A2AMTLSError("no cert")):
            result = await _collect_response(mw, _make_scope(path="/tasks/send"))

        assert result["status"] == 401
        downstream.assert_not_awaited()


# ---------------------------------------------------------------------------
# Disabled mode: always passes through
# ---------------------------------------------------------------------------


class TestDisabledMode:
    @pytest.mark.asyncio
    async def test_disabled_skips_enforcement_entirely(self):
        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(downstream, enabled=False, protected_prefix="/")

        with patch("trimcp.mtls.mtls_enforce") as mock_enforce:
            await mw(_make_scope("/tasks/send"), AsyncMock(), AsyncMock())

        mock_enforce.assert_not_called()
        downstream.assert_awaited_once()


# ---------------------------------------------------------------------------
# Enabled + valid cert: passes through to downstream
# ---------------------------------------------------------------------------


class TestEnabledValidCert:
    @pytest.mark.asyncio
    async def test_valid_cert_reaches_downstream(self):
        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(
            downstream,
            enabled=True,
            protected_prefix="/tasks",
            allowed_sans=["agent.internal"],
        )

        with patch("trimcp.mtls.mtls_enforce", return_value="agent.internal"):
            await mw(_make_scope("/tasks/send"), AsyncMock(), AsyncMock())

        downstream.assert_awaited_once()


# ---------------------------------------------------------------------------
# Enabled + missing cert (strict): 401 with JSON-RPC error body
# ---------------------------------------------------------------------------


class TestEnabledStrictMissingCert:
    @pytest.mark.asyncio
    async def test_missing_cert_returns_401(self):
        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(downstream, enabled=True, protected_prefix="/tasks")

        with patch("trimcp.mtls.mtls_enforce", side_effect=A2AMTLSError("no cert")):
            result = await _collect_response(mw, _make_scope("/tasks/send"))

        assert result["status"] == 401
        downstream.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_response_body_is_jsonrpc_error(self):
        import json

        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(
            downstream,
            enabled=True,
            protected_prefix="/tasks",
            error_code=-32013,
        )

        with patch("trimcp.mtls.mtls_enforce", side_effect=A2AMTLSError("bad fp")):
            result = await _collect_response(mw, _make_scope("/tasks/send"))

        body = json.loads(result["body"])
        assert body["jsonrpc"] == "2.0"
        assert body["error"]["code"] == -32013
        assert "mTLS" in body["error"]["message"]
        assert body["error"]["data"]["reason"] == "bad fp"
        assert body["id"] is None

    @pytest.mark.asyncio
    async def test_default_error_code_is_minus_32010(self):
        import json

        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(downstream, enabled=True, protected_prefix="/tasks")

        with patch("trimcp.mtls.mtls_enforce", side_effect=A2AMTLSError("x")):
            result = await _collect_response(mw, _make_scope("/tasks/send"))

        body = json.loads(result["body"])
        assert body["error"]["code"] == DEFAULT_MTLS_ERROR_CODE


# ---------------------------------------------------------------------------
# Header extraction: headers are forwarded to mtls_enforce
# ---------------------------------------------------------------------------


class TestHeaderForwarding:
    @pytest.mark.asyncio
    async def test_headers_decoded_and_passed_to_enforce(self):
        downstream = AsyncMock()
        mw = MTLSAuthMiddleware(downstream, enabled=True, protected_prefix="/tasks")

        scope = {
            "type": "http",
            "path": "/tasks/send",
            "headers": [
                (b"x-forwarded-client-cert", b"Hash=abc123"),
                (b"Content-Type", b"application/json"),
            ],
        }

        with patch("trimcp.mtls.mtls_enforce", return_value=None) as mock_enforce:
            await mw(scope, AsyncMock(), AsyncMock())

        call_headers = mock_enforce.call_args.kwargs["headers"]
        assert call_headers["x-forwarded-client-cert"] == "Hash=abc123"
        assert call_headers["content-type"] == "application/json"


# ---------------------------------------------------------------------------
# Constructor defaults
# ---------------------------------------------------------------------------


class TestConstructorDefaults:
    def test_enabled_defaults_to_false(self):
        mw = MTLSAuthMiddleware(AsyncMock())
        assert mw.enabled is False

    def test_strict_defaults_to_true(self):
        mw = MTLSAuthMiddleware(AsyncMock())
        assert mw.strict is True

    def test_allowed_sans_defaults_to_empty_list(self):
        mw = MTLSAuthMiddleware(AsyncMock())
        assert mw.allowed_sans == []

    def test_allowed_fingerprints_defaults_to_empty_list(self):
        mw = MTLSAuthMiddleware(AsyncMock())
        assert mw.allowed_fingerprints == []

    def test_none_sans_coerced_to_empty_list(self):
        mw = MTLSAuthMiddleware(AsyncMock(), allowed_sans=None)
        assert mw.allowed_sans == []
