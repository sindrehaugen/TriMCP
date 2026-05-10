"""
tests/test_jwt_auth.py

Unit tests for ``trimcp/jwt_auth.py`` — JWT authentication with audience validation.

Coverage:
  - ``decode_agent_token`` audience override vs. global config
  - Token with matching audience accepted
  - Token with mismatched audience rejected (InvalidAudienceError)
  - Token without ``aud`` claim rejected
  - A2A-specific audience on ``JWTAuthMiddleware`` prevents replay
  - Global ``TRIMCP_JWT_AUDIENCE`` still works when no per-service override
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import jwt as pyjwt
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from trimcp.config import cfg
from trimcp.jwt_auth import (
    JWTAuthMiddleware,
    JWTDecodeError,
    decode_agent_token,
)

# ---------------------------------------------------------------------------
# Helpers — token factories
# ---------------------------------------------------------------------------

_SECRET = "test-hmac-secret-key-for-jwt-tests-at-least-32-chars!!"
_NS_ID = str(uuid4())


def _make_token(
    *,
    aud: str | None = "trimcp_a2a",
    iss: str | None = "trimcp",
    namespace_id: str | None = None,
    exp_offset: float = 3600.0,
    **extra: Any,
) -> str:
    """Sign a JWT with the test secret.

    Returns an encoded HS256 token.
    """
    now = time.time()
    payload: dict[str, Any] = {
        "sub": "test-agent",
        "iat": int(now),
        "exp": int(now + exp_offset),
    }
    if aud is not None:
        payload["aud"] = aud
    if iss is not None:
        payload["iss"] = iss
    if namespace_id is not None:
        payload["namespace_id"] = namespace_id
    else:
        payload["namespace_id"] = _NS_ID

    payload.update(extra)
    return pyjwt.encode(payload, _SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# decode_agent_token  —  audience override
# ---------------------------------------------------------------------------


class TestDecodeAgentTokenAudience:
    """``decode_agent_token(…, audience=)`` enforces strict audience match."""

    def test_matching_audience_accepted(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "")

        token = _make_token(aud="trimcp_a2a", namespace_id=_NS_ID)
        ctx = decode_agent_token(token, audience="trimcp_a2a")
        assert str(ctx.namespace_id) == _NS_ID

    def test_mismatched_audience_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "")

        token = _make_token(aud="trimcp_web_frontend", namespace_id=_NS_ID)
        with pytest.raises(JWTDecodeError) as excinfo:
            decode_agent_token(token, audience="trimcp_a2a")
        assert excinfo.value.reason == "jwt_audience_mismatch"

    def test_missing_aud_claim_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "")

        token = _make_token(aud=None, namespace_id=_NS_ID)
        with pytest.raises(JWTDecodeError) as excinfo:
            decode_agent_token(token, audience="trimcp_a2a")
        assert "missing" in excinfo.value.reason

    def test_global_audience_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """When ``audience=None``, fall back to ``cfg.TRIMCP_JWT_AUDIENCE``."""
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "trimcp_admin")

        token = _make_token(aud="trimcp_admin", namespace_id=_NS_ID)
        ctx = decode_agent_token(token, audience=None)
        assert str(ctx.namespace_id) == _NS_ID

    def test_audience_none_skips_validation(self, monkeypatch: pytest.MonkeyPatch):
        """When both param and config are empty, aud is not required at all."""
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "")

        # Token without an aud claim — should pass when no audience is configured
        # (only namespace_id is required).
        token = _make_token(aud=None, namespace_id=_NS_ID)
        ctx = decode_agent_token(token, audience=None)
        assert str(ctx.namespace_id) == _NS_ID

    def test_replay_token_rejected_explicit_audience(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Simulates a token issued for the web frontend hitting the A2A server."""
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "")

        # Token intended for web frontend
        frontend_token = _make_token(aud="trimcp_web_frontend", namespace_id=_NS_ID)

        # A2A server requires its own audience
        with pytest.raises(JWTDecodeError, match="audience"):
            decode_agent_token(frontend_token, audience="trimcp_a2a")


# ---------------------------------------------------------------------------
# JWTAuthMiddleware  —  per-service expected_audience
# ---------------------------------------------------------------------------


class TestJWTAuthMiddlewareAudience:
    """End-to-end middleware tests with per-service ``expected_audience``."""

    @staticmethod
    def _make_app(expected_audience: str | None = None) -> Starlette:
        async def _ok(request):
            return JSONResponse(
                {"status": "ok", "ns": str(request.state.namespace_ctx.namespace_id)}
            )

        return Starlette(
            middleware=[
                Middleware(
                    JWTAuthMiddleware,
                    protected_prefix="/api",
                    expected_audience=expected_audience,
                ),
            ],
            routes=[Route("/api/action", endpoint=_ok, methods=["GET"])],
        )

    def test_a2a_audience_accepted(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "")

        app = self._make_app(expected_audience="trimcp_a2a")
        token = _make_token(aud="trimcp_a2a", namespace_id=_NS_ID)

        with TestClient(app) as client:
            resp = client.get(
                "/api/action", headers={"Authorization": f"Bearer {token}"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["ns"] == _NS_ID

    def test_a2a_rejects_frontend_token(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "")

        app = self._make_app(expected_audience="trimcp_a2a")
        token = _make_token(aud="trimcp_web_frontend", namespace_id=_NS_ID)

        with TestClient(app) as client:
            resp = client.get(
                "/api/action", headers={"Authorization": f"Bearer {token}"}
            )
        assert resp.status_code == 401
        error = resp.json()
        assert "error" in error
        assert error["error"]["data"]["reason"] == "jwt_audience_mismatch"

    def test_no_audience_falls_back_to_global(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)
        monkeypatch.setattr(cfg, "TRIMCP_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "TRIMCP_JWT_AUDIENCE", "trimcp_admin")

        app = self._make_app(expected_audience=None)
        token = _make_token(aud="trimcp_admin", namespace_id=_NS_ID)

        with TestClient(app) as client:
            resp = client.get(
                "/api/action", headers={"Authorization": f"Bearer {token}"}
            )
        assert resp.status_code == 200

    def test_protected_prefix_not_matched(self, monkeypatch: pytest.MonkeyPatch):
        """Non-protected routes bypass auth entirely."""
        monkeypatch.setattr(cfg, "TRIMCP_JWT_SECRET", _SECRET)

        app = self._make_app(expected_audience="trimcp_a2a")
        with TestClient(app) as client:
            resp = client.get("/health")
        # No auth required for /health
        assert resp.status_code in (200, 404)
