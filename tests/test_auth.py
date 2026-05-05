"""
tests/test_auth.py

Unit tests for trimcp/auth.py — HMAC authentication, Phase 0.1 helpers.

Coverage:
  - verify_hmac (correct, wrong key, tampered body, empty key)
  - _compute_signature parity (body vs. no-body)
  - HMACAuthContext Pydantic V2 validation
  - NamespaceContext Pydantic V2 validation
  - resolve_namespace (valid UUID, missing header, malformed UUID)
  - validate_agent_id (normal, empty, whitespace, over-length)
  - HMACAuthMiddleware (via Starlette TestClient):
      - missing headers → 401 JSON-RPC 2.0
      - wrong scheme → 401 JSON-RPC 2.0
      - expired timestamp → 401 JSON-RPC 2.0
      - invalid signature → 401 JSON-RPC 2.0
      - empty api_key on server → 401 JSON-RPC 2.0
      - valid request → 200 pass-through
      - non-protected path → 200 no auth needed
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import time
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from trimcp.auth import (
    HMACAuthContext,
    HMACAuthMiddleware,
    NamespaceContext,
    _compute_signature,
    resolve_namespace,
    set_namespace_context,
    validate_agent_id,
    verify_hmac,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KEY = "test-hmac-secret-key"


def _make_signature(
    key: str,
    method: str,
    path: str,
    timestamp: int,
    body: bytes = b"",
) -> str:
    parts = [method.upper(), path, str(timestamp)]
    if body:
        parts.append(hashlib.sha256(body).hexdigest())
    canonical = "\n".join(parts)
    return _hmac.new(key.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _valid_headers(
    key: str,
    method: str = "GET",
    path: str = "/api/health",
    body: bytes = b"",
    ts: int | None = None,
) -> dict[str, str]:
    ts = ts if ts is not None else int(time.time())
    sig = _make_signature(key, method, path, ts, body)
    return {
        "X-TriMCP-Timestamp": str(ts),
        "Authorization": f"HMAC-SHA256 {sig}",
    }


# ---------------------------------------------------------------------------
# _compute_signature / verify_hmac
# ---------------------------------------------------------------------------

class TestComputeSignature:
    def test_no_body_excludes_hash(self) -> None:
        sig = _compute_signature(_KEY, "GET", "/api/health", 1000, b"")
        expected = _hmac.new(
            _KEY.encode(), b"GET\n/api/health\n1000", hashlib.sha256
        ).hexdigest()
        assert sig == expected

    def test_with_body_includes_sha256(self) -> None:
        body = b'{"x": 1}'
        body_hash = hashlib.sha256(body).hexdigest()
        sig = _compute_signature(_KEY, "POST", "/api/gc/trigger", 2000, body)
        canonical = f"POST\n/api/gc/trigger\n2000\n{body_hash}"
        expected = _hmac.new(_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        assert sig == expected

    def test_method_uppercased(self) -> None:
        sig_lower = _compute_signature(_KEY, "get", "/api/health", 1000, b"")
        sig_upper = _compute_signature(_KEY, "GET", "/api/health", 1000, b"")
        assert sig_lower == sig_upper


class TestVerifyHmac:
    def test_valid_signature_returns_true(self) -> None:
        ts = int(time.time())
        body = b""
        sig = _make_signature(_KEY, "GET", "/api/health", ts, body)
        assert verify_hmac(_KEY, "GET", "/api/health", ts, body, sig) is True

    def test_wrong_key_returns_false(self) -> None:
        ts = int(time.time())
        sig = _make_signature("wrong-key", "GET", "/api/health", ts, b"")
        assert verify_hmac(_KEY, "GET", "/api/health", ts, b"", sig) is False

    def test_tampered_body_returns_false(self) -> None:
        ts = int(time.time())
        original_body = b'{"data": "original"}'
        sig = _make_signature(_KEY, "POST", "/api/x", ts, original_body)
        tampered = b'{"data": "tampered"}'
        assert verify_hmac(_KEY, "POST", "/api/x", ts, tampered, sig) is False

    def test_empty_api_key_returns_false(self) -> None:
        ts = int(time.time())
        sig = _make_signature(_KEY, "GET", "/api/health", ts, b"")
        assert verify_hmac("", "GET", "/api/health", ts, b"", sig) is False

    def test_case_insensitive_signature(self) -> None:
        ts = int(time.time())
        body = b""
        sig = _make_signature(_KEY, "GET", "/api/health", ts, body).upper()
        assert verify_hmac(_KEY, "GET", "/api/health", ts, body, sig) is True

    def test_different_path_returns_false(self) -> None:
        ts = int(time.time())
        sig = _make_signature(_KEY, "GET", "/api/health", ts, b"")
        assert verify_hmac(_KEY, "GET", "/api/other", ts, b"", sig) is False


# ---------------------------------------------------------------------------
# Pydantic V2 models
# ---------------------------------------------------------------------------

class TestHMACAuthContext:
    def test_valid_construction(self) -> None:
        ctx = HMACAuthContext(timestamp=int(time.time()), signature="deadbeef")
        assert ctx.signature == "deadbeef"

    def test_signature_lowercased(self) -> None:
        ctx = HMACAuthContext(timestamp=100, signature="DEADBEEF")
        assert ctx.signature == "deadbeef"

    def test_non_positive_timestamp_raises(self) -> None:
        with pytest.raises(Exception):
            HMACAuthContext(timestamp=0, signature="aa")

    def test_empty_signature_raises(self) -> None:
        with pytest.raises(Exception):
            HMACAuthContext(timestamp=100, signature="")

    def test_non_hex_signature_raises(self) -> None:
        with pytest.raises(Exception):
            HMACAuthContext(timestamp=100, signature="xyz!")

    def test_model_is_frozen(self) -> None:
        ctx = HMACAuthContext(timestamp=100, signature="aa")
        with pytest.raises(Exception):
            ctx.timestamp = 999  # type: ignore[misc]


class TestNamespaceContext:
    def test_valid_uuid_string(self) -> None:
        uid = uuid4()
        ctx = NamespaceContext(namespace_id=uid, agent_id="my-agent")
        assert ctx.namespace_id == uid
        assert ctx.agent_id == "my-agent"

    def test_blank_agent_defaults_to_default(self) -> None:
        ctx = NamespaceContext(namespace_id=uuid4(), agent_id="   ")
        assert ctx.agent_id == "default"

    def test_none_agent_defaults_to_default(self) -> None:
        ctx = NamespaceContext(namespace_id=uuid4(), agent_id=None)  # type: ignore[arg-type]
        assert ctx.agent_id == "default"

    def test_agent_id_truncated_at_128(self) -> None:
        long_id = "a" * 200
        ctx = NamespaceContext(namespace_id=uuid4(), agent_id=long_id)
        assert len(ctx.agent_id) == 128

    def test_agent_id_strips_whitespace(self) -> None:
        ctx = NamespaceContext(namespace_id=uuid4(), agent_id="  agent-1  ")
        assert ctx.agent_id == "agent-1"


# ---------------------------------------------------------------------------
# Phase 0.1 helpers
# ---------------------------------------------------------------------------

class TestResolveNamespace:
    def test_valid_uuid_returns_uuid_object(self) -> None:
        uid = uuid4()
        headers = {"x-trimcp-namespace-id": str(uid)}
        assert resolve_namespace(headers) == uid

    def test_missing_header_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing"):
            resolve_namespace({})

    def test_blank_header_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing"):
            resolve_namespace({"x-trimcp-namespace-id": "  "})

    def test_malformed_uuid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid namespace UUID"):
            resolve_namespace({"x-trimcp-namespace-id": "not-a-uuid"})

    def test_case_insensitive_header_lookup(self) -> None:
        uid = uuid4()
        # Simulate Starlette's lower-cased header dict
        headers = {"x-trimcp-namespace-id": str(uid)}
        assert resolve_namespace(headers) == uid


class TestValidateAgentId:
    def test_normal_id_returned_unchanged(self) -> None:
        assert validate_agent_id("my-agent") == "my-agent"

    def test_whitespace_stripped(self) -> None:
        assert validate_agent_id("  agent-2  ") == "agent-2"

    def test_empty_string_returns_default(self) -> None:
        assert validate_agent_id("") == "default"

    def test_none_returns_default(self) -> None:
        assert validate_agent_id(None) == "default"  # type: ignore[arg-type]

    def test_over_128_chars_truncated(self) -> None:
        assert len(validate_agent_id("x" * 200)) == 128

    def test_whitespace_only_returns_default(self) -> None:
        assert validate_agent_id("    ") == "default"


class TestSetNamespaceContext:
    @pytest.mark.asyncio
    async def test_calls_set_config_with_local_true(self) -> None:
        conn = AsyncMock()
        uid = uuid4()
        await set_namespace_context(conn, uid)
        conn.execute.assert_awaited_once_with(
            "SELECT set_config('trimcp.namespace_id', $1, true)",
            str(uid),
        )


# ---------------------------------------------------------------------------
# HMACAuthMiddleware (via Starlette TestClient)
# ---------------------------------------------------------------------------

def _build_test_app(api_key: str) -> Starlette:
    async def protected_route(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")

    async def public_route(request: Request) -> PlainTextResponse:
        return PlainTextResponse("public")

    return Starlette(
        routes=[
            Route("/api/health", endpoint=protected_route, methods=["GET"]),
            Route("/api/gc/trigger", endpoint=protected_route, methods=["POST"]),
            Route("/public", endpoint=public_route, methods=["GET"]),
        ],
        middleware=[
            Middleware(HMACAuthMiddleware, protected_prefix="/api/", api_key=api_key)
        ],
    )


class TestHMACAuthMiddleware:
    def test_valid_get_passes(self) -> None:
        app = _build_test_app(_KEY)
        headers = _valid_headers(_KEY, "GET", "/api/health")
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/health", headers=headers)
        assert r.status_code == 200
        assert r.text == "OK"

    def test_valid_post_with_body_passes(self) -> None:
        app = _build_test_app(_KEY)
        body = b'{"force": true}'
        ts = int(time.time())
        sig = _make_signature(_KEY, "POST", "/api/gc/trigger", ts, body)
        headers = {
            "X-TriMCP-Timestamp": str(ts),
            "Authorization": f"HMAC-SHA256 {sig}",
            "Content-Type": "application/json",
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.post("/api/gc/trigger", content=body, headers=headers)
        assert r.status_code == 200

    def test_missing_all_auth_headers_returns_401(self) -> None:
        app = _build_test_app(_KEY)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/health")
        assert r.status_code == 401
        body = r.json()
        assert body["jsonrpc"] == "2.0"
        assert body["error"]["code"] == -32001
        assert body["error"]["data"]["reason"] == "missing_auth_headers"

    def test_missing_timestamp_header_returns_401(self) -> None:
        app = _build_test_app(_KEY)
        ts = int(time.time())
        sig = _make_signature(_KEY, "GET", "/api/health", ts)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/health", headers={"Authorization": f"HMAC-SHA256 {sig}"})
        assert r.status_code == 401
        assert r.json()["error"]["data"]["reason"] == "missing_auth_headers"

    def test_missing_authorization_header_returns_401(self) -> None:
        app = _build_test_app(_KEY)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/health", headers={"X-TriMCP-Timestamp": str(int(time.time()))})
        assert r.status_code == 401
        assert r.json()["error"]["data"]["reason"] == "missing_auth_headers"

    def test_wrong_scheme_returns_401(self) -> None:
        app = _build_test_app(_KEY)
        ts = int(time.time())
        sig = _make_signature(_KEY, "GET", "/api/health", ts)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get(
                "/api/health",
                headers={
                    "X-TriMCP-Timestamp": str(ts),
                    "Authorization": f"Bearer {sig}",  # wrong scheme
                },
            )
        assert r.status_code == 401
        assert r.json()["error"]["data"]["reason"] == "invalid_authorization_scheme"

    def test_expired_timestamp_returns_401_with_replay_code(self) -> None:
        app = _build_test_app(_KEY)
        old_ts = int(time.time()) - 600  # 10 minutes ago
        sig = _make_signature(_KEY, "GET", "/api/health", old_ts)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get(
                "/api/health",
                headers={
                    "X-TriMCP-Timestamp": str(old_ts),
                    "Authorization": f"HMAC-SHA256 {sig}",
                },
            )
        assert r.status_code == 401
        body = r.json()
        assert body["error"]["code"] == -32002
        assert body["error"]["data"]["reason"] == "replay_or_clock_skew"

    def test_future_timestamp_too_far_returns_401(self) -> None:
        app = _build_test_app(_KEY)
        future_ts = int(time.time()) + 600  # 10 minutes in future
        sig = _make_signature(_KEY, "GET", "/api/health", future_ts)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get(
                "/api/health",
                headers={
                    "X-TriMCP-Timestamp": str(future_ts),
                    "Authorization": f"HMAC-SHA256 {sig}",
                },
            )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == -32002

    def test_invalid_signature_returns_401(self) -> None:
        app = _build_test_app(_KEY)
        ts = int(time.time())
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get(
                "/api/health",
                headers={
                    "X-TriMCP-Timestamp": str(ts),
                    "Authorization": "HMAC-SHA256 deadbeefdeadbeefdeadbeef",
                },
            )
        assert r.status_code == 401
        assert r.json()["error"]["data"]["reason"] == "invalid_signature"

    def test_non_hex_signature_returns_401(self) -> None:
        app = _build_test_app(_KEY)
        ts = int(time.time())
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get(
                "/api/health",
                headers={
                    "X-TriMCP-Timestamp": str(ts),
                    "Authorization": "HMAC-SHA256 not-hex!",
                },
            )
        assert r.status_code == 401

    def test_empty_server_key_returns_401_server_misconfigured(self) -> None:
        app = _build_test_app("")  # empty key simulates misconfigured server
        headers = _valid_headers(_KEY, "GET", "/api/health")
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/health", headers=headers)
        assert r.status_code == 401
        assert r.json()["error"]["data"]["reason"] == "server_misconfigured"

    def test_public_route_requires_no_auth(self) -> None:
        app = _build_test_app(_KEY)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/public")
        assert r.status_code == 200
        assert r.text == "public"

    def test_jsonrpc_error_structure_is_complete(self) -> None:
        """Every error response must be a complete JSON-RPC 2.0 error object."""
        app = _build_test_app(_KEY)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/health")
        body = r.json()
        assert "jsonrpc" in body
        assert body["jsonrpc"] == "2.0"
        assert "error" in body
        error = body["error"]
        assert "code" in error
        assert "message" in error
        assert "data" in error
        assert "reason" in error["data"]
        assert "id" in body  # may be null but must be present
