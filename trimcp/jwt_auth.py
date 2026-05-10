"""
trimcp/jwt_auth.py

Phase 0.2 — JWT Bridge: Bearer-token middleware for agent-scoped API endpoints.

Public API (imported by admin_server.py, a2a_server.py, or any Starlette app):
  JWTAuthMiddleware   — Starlette middleware; validates ``Authorization: Bearer``
                        tokens and attaches a ``NamespaceContext`` to
                        ``request.state.namespace_ctx``.
  decode_agent_token  — Callable helper for non-middleware use (e.g. WebSocket
                        handshake or background task runners).

Integration with the HMAC core
-------------------------------
This module is **additive** to ``trimcp.auth``.  It does not replace the
``HMACAuthMiddleware``; it provides a parallel auth path for *agent-facing*
endpoints that authenticate with short-lived JWT Bearer tokens rather than a
shared HMAC secret.

Both middlewares produce the same ``NamespaceContext`` (from ``trimcp.auth``),
so the orchestrator write path receives identical identity objects regardless
of which auth scheme was used.  Typical stack order::

    app.add_middleware(HMACAuthMiddleware, protected_prefix="/api/admin/", ...)
    app.add_middleware(JWTAuthMiddleware,  protected_prefix="/api/v1/",    ...)

JWT Claims (TriMCP namespace)
------------------------------
Required:
  namespace_id  (str, UUID format)  — maps to ``NamespaceContext.namespace_id``
Optional:
  agent_id      (str, max 128 chars) — maps to ``NamespaceContext.agent_id``;
                                       falls back to ``"default"`` when absent.
Standard claims:
  exp           — token expiry; validated automatically by PyJWT.
  iat           — issued-at; no additional check beyond PyJWT defaults.
  iss           — issuer; validated when ``TRIMCP_JWT_ISSUER`` is configured.
  aud           — audience; validated when ``TRIMCP_JWT_AUDIENCE`` is configured.
  sub           — subject; informational only, not used for auth decisions.
  jti           — JWT ID; available for caller-side replay detection if needed.

Supported algorithms
---------------------
  HS256  — symmetric, HMAC-SHA256.  Set ``TRIMCP_JWT_SECRET``.
           Suitable for development and internal service-to-service use.
  RS256  — asymmetric, RSA + SHA-256.  Set ``TRIMCP_JWT_PUBLIC_KEY`` (PEM).
  ES256  — asymmetric, ECDSA P-256.   Set ``TRIMCP_JWT_PUBLIC_KEY`` (PEM).

``TRIMCP_JWT_PUBLIC_KEY`` may be:
  - A raw PEM string (begins with ``-----BEGIN``), OR
  - A ``file://`` URI pointing to a PEM file on disk.

When both ``TRIMCP_JWT_PUBLIC_KEY`` and ``TRIMCP_JWT_SECRET`` are set, the
public key takes precedence (asymmetric algorithms are preferred in prod).

JSON-RPC 2.0 error codes (server-defined range, extends trimcp.auth)
----------------------------------------------------------------------
  -32005  JWT validation failed  (expired, bad signature, decode error)
  -32006  JWT missing required claim  (``namespace_id`` absent)
  -32007  JWT claim invalid  (``namespace_id`` not a valid UUID)
"""

from __future__ import annotations

import logging
import os
from typing import Any
from uuid import UUID

import jwt  # PyJWT >= 2.8
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
    MissingRequiredClaimError,
)
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from trimcp.auth import NamespaceContext, validate_agent_id
from trimcp.config import cfg

log = logging.getLogger("trimcp.jwt_auth")

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 error codes (JWT-specific, extends trimcp.auth -32001..-32004)
# ---------------------------------------------------------------------------

_CODE_JWT_INVALID: int = -32005  # expired / bad signature / decode error
_CODE_JWT_MISSING_CLAIM: int = -32006  # namespace_id absent
_CODE_JWT_BAD_CLAIM: int = -32007  # namespace_id not a valid UUID

_HTTP_UNAUTHORIZED: int = 401
_HTTP_BAD_REQUEST: int = 400

# Algorithms that require an asymmetric public key
_ASYMMETRIC_ALGORITHMS: frozenset[str] = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"}
)


# ---------------------------------------------------------------------------
# Helpers — JSON-RPC 2.0 error responses (same shape as trimcp.auth)
# ---------------------------------------------------------------------------


def _jsonrpc_error(
    code: int,
    message: str,
    reason: str,
    request_id: Any = None,
) -> JSONResponse:
    """Build a strict JSON-RPC 2.0 error response.

    HTTP status:
      401 — authentication / token errors (-32005, -32006, -32007)
      400 — only for malformed claim values outside the UUID check
    """
    http_status = (
        _HTTP_UNAUTHORIZED
        if code in (_CODE_JWT_INVALID, _CODE_JWT_MISSING_CLAIM, _CODE_JWT_BAD_CLAIM)
        else _HTTP_BAD_REQUEST
    )
    return JSONResponse(
        status_code=http_status,
        content={
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message,
                "data": {"reason": reason},
            },
            "id": request_id,
        },
    )


# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------


def _load_public_key(raw: str) -> str:
    """Resolve a public key from an env-var value.

    Accepts:
      - Raw PEM string (starts with ``-----BEGIN``).
      - ``file:///absolute/path/to/key.pem`` URI.

    The file path is validated against an allowed base directory
    (``TRIMCP_JWT_KEY_DIR`` env var, defaults to CWD) to prevent
    path traversal.

    Returns the PEM string.
    Raises ``ValueError`` on unresolvable input.
    """
    from pathlib import Path

    stripped = raw.strip()
    if stripped.startswith("-----"):
        return stripped
    if stripped.startswith("file://"):
        path_str = stripped[len("file://") :]
        key_path = Path(path_str).resolve(strict=False)

        # Validate against allowed base directory
        allowed_dir_raw = os.getenv("TRIMCP_JWT_KEY_DIR", str(Path.cwd()))
        allowed_base = Path(allowed_dir_raw).resolve(strict=True)

        if not key_path.is_relative_to(allowed_base):
            raise ValueError(
                f"TRIMCP_JWT_PUBLIC_KEY path escapes allowed directory: {path_str!r}"
            )

        if not key_path.is_file():
            raise ValueError(f"TRIMCP_JWT_PUBLIC_KEY file not found: {path_str!r}")
        return key_path.read_text(encoding="utf-8").strip()
    raise ValueError(
        f"TRIMCP_JWT_PUBLIC_KEY must be a PEM string or a file:// URI; got: {stripped[:40]!r}…"
    )


def _build_jwt_key(algorithm: str) -> Any:
    """Return the key object / string to pass to ``jwt.decode()``.

    Priority:
      1. Public key  (for asymmetric algorithms, RS256 / ES256 / …)
      2. Shared secret (for HS256)

    Raises ``RuntimeError`` if the algorithm requires a key that is not
    configured (server misconfiguration).
    """
    if cfg.TRIMCP_JWT_PUBLIC_KEY:
        return _load_public_key(cfg.TRIMCP_JWT_PUBLIC_KEY)
    if algorithm in _ASYMMETRIC_ALGORITHMS:
        raise RuntimeError(
            f"Algorithm {algorithm!r} requires TRIMCP_JWT_PUBLIC_KEY to be set but it is empty."
        )
    if cfg.TRIMCP_JWT_SECRET:
        return cfg.TRIMCP_JWT_SECRET
    raise RuntimeError(
        "JWT key not configured: set TRIMCP_JWT_SECRET (HS256) or "
        "TRIMCP_JWT_PUBLIC_KEY (RS256 / ES256)."
    )


# ---------------------------------------------------------------------------
# Core decode + claim extraction
# ---------------------------------------------------------------------------


class JWTDecodeError(Exception):
    """Wraps PyJWT errors with structured metadata for middleware handling."""

    def __init__(self, code: int, message: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.message = message
        self.reason = reason


def decode_agent_token(
    token: str,
    audience: str | None = None,
) -> NamespaceContext:
    """Validate a JWT Bearer token and extract ``NamespaceContext``.

    This is the canonical extraction function used by both the middleware
    and any non-HTTP callers (WebSocket handshakes, background tasks, etc.).

    Args:
        token: Raw JWT string (without the ``Bearer`` prefix).
        audience:
            Expected ``aud`` claim value.  When provided (non-None, non-empty),
            this value is used instead of ``cfg.TRIMCP_JWT_AUDIENCE`` **and**
            is strictly enforced — a token with a different or missing ``aud``
            is rejected with ``InvalidAudienceError``.

            When ``None`` the function falls back to the global config.
            If the resolved value is still empty the ``aud`` claim is required
            to be present (``require=["aud"]``) but its value is not validated.

    Returns:
        A frozen ``NamespaceContext`` with ``namespace_id`` and ``agent_id``.

    Raises:
        JWTDecodeError: On any validation failure; carries JSON-RPC code +
                        human-readable message + machine-readable reason.
        RuntimeError:   On server misconfiguration (missing key).
    """
    algorithm = cfg.TRIMCP_JWT_ALGORITHM
    try:
        key = _build_jwt_key(algorithm)
    except RuntimeError as exc:
        log.error("JWT key build failed (server misconfiguration): %s", exc)
        raise JWTDecodeError(
            _CODE_JWT_INVALID,
            "Authentication failed",
            "jwt_server_misconfigured",
        ) from exc

    # Resolve audience: explicit param > global config > None (claim required, value unchecked)
    resolved_audience = (
        audience if audience is not None else (cfg.TRIMCP_JWT_AUDIENCE or None)
    )
    # Resolve issuer: coerce empty string to None so PyJWT skips validation
    resolved_issuer = cfg.TRIMCP_JWT_ISSUER or None

    # Only require ``aud`` when we have a specific expected value.
    # PyJWT raises InvalidAudienceError when audience=None but the token
    # carries an aud claim — so we must drop it from ``require`` when
    # intentionally not validating the audience value.
    if resolved_audience:
        decode_options: dict[str, Any] = {"require": ["exp", "iss", "aud"]}
    else:
        decode_options = {"require": ["exp", "iss"]}

    decode_kwargs: dict[str, Any] = {
        "algorithms": [algorithm],
        "options": decode_options,
        "issuer": resolved_issuer,
        "audience": resolved_audience,
    }

    try:
        payload: dict[str, Any] = jwt.decode(token, key, **decode_kwargs)
    except ExpiredSignatureError as exc:
        log.warning("JWT expired: %s", exc)
        raise JWTDecodeError(
            _CODE_JWT_INVALID,
            "Authentication failed",
            "jwt_expired",
        ) from exc
    except MissingRequiredClaimError as exc:
        log.warning("JWT missing standard claim: %s", exc)
        raise JWTDecodeError(
            _CODE_JWT_INVALID,
            "Authentication failed",
            f"jwt_missing_standard_claim:{exc}",
        ) from exc
    except InvalidAudienceError as exc:
        log.warning("JWT audience mismatch: %s", exc)
        raise JWTDecodeError(
            _CODE_JWT_INVALID,
            "Authentication failed",
            "jwt_audience_mismatch",
        ) from exc
    except InvalidIssuerError as exc:
        log.warning("JWT issuer mismatch: %s", exc)
        raise JWTDecodeError(
            _CODE_JWT_INVALID,
            "Authentication failed",
            "jwt_issuer_mismatch",
        ) from exc
    except DecodeError as exc:
        log.warning("JWT decode error: %s", exc)
        raise JWTDecodeError(
            _CODE_JWT_INVALID,
            "Authentication failed",
            "jwt_decode_error",
        ) from exc
    except InvalidTokenError as exc:
        log.warning("JWT invalid: %s", exc)
        raise JWTDecodeError(
            _CODE_JWT_INVALID,
            "Authentication failed",
            "jwt_invalid",
        ) from exc

    # --- Extract TriMCP-specific claims ---
    raw_ns = payload.get("namespace_id")
    if not raw_ns:
        log.warning("JWT missing 'namespace_id' claim; sub=%s", payload.get("sub"))
        raise JWTDecodeError(
            _CODE_JWT_MISSING_CLAIM,
            "Authentication failed",
            "missing_claim:namespace_id",
        )

    try:
        namespace_id = UUID(str(raw_ns).strip())
    except ValueError as exc:
        log.warning("JWT 'namespace_id' claim is not a valid UUID: %r", raw_ns)
        raise JWTDecodeError(
            _CODE_JWT_BAD_CLAIM,
            "Authentication failed",
            f"invalid_claim:namespace_id:{raw_ns!r}",
        ) from exc

    raw_agent = payload.get("agent_id")
    agent_id = validate_agent_id(str(raw_agent) if raw_agent is not None else "")

    try:
        return NamespaceContext(namespace_id=namespace_id, agent_id=agent_id)
    except ValidationError as exc:
        log.error("NamespaceContext construction failed (unexpected): %s", exc)
        raise JWTDecodeError(
            _CODE_JWT_BAD_CLAIM,
            "Authentication failed",
            "invalid_namespace_context",
        ) from exc


# ---------------------------------------------------------------------------
# Starlette middleware
# ---------------------------------------------------------------------------


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """JWT Bearer token authentication middleware for agent-scoped endpoints.

    Validates ``Authorization: Bearer <token>`` for all requests whose path
    starts with ``protected_prefix``.  On success, the resolved
    ``NamespaceContext`` is attached as ``request.state.namespace_ctx`` so
    downstream route handlers and the orchestrator write path can consume it
    without re-parsing the token.

    Error contract (JSON-RPC 2.0):
      -32005  Any JWT validation failure (expired, bad signature, decode error)
      -32006  ``namespace_id`` claim absent
      -32007  ``namespace_id`` claim is not a valid UUID

    Compatibility:
      This middleware is **not** a replacement for ``HMACAuthMiddleware``.
      Both may be mounted simultaneously on different route prefixes::

          app.add_middleware(HMACAuthMiddleware, protected_prefix="/api/admin/", ...)
          app.add_middleware(JWTAuthMiddleware,  protected_prefix="/api/v1/",    ...)

    Args:
        app:               The ASGI application to wrap.
        protected_prefix:  URL path prefix that requires JWT authentication.
                           Defaults to ``cfg.TRIMCP_JWT_PREFIX`` (``/api/v1/``).
        expected_audience:
            Expected ``aud`` claim value for this service.  When set, tokens
            whose ``aud`` does not match are rejected — prevents replay of
            tokens issued for other services (web frontend, admin UI, etc.)
            against this endpoint.

            Falls back to ``cfg.TRIMCP_JWT_AUDIENCE`` when ``None``.
    """

    def __init__(
        self,
        app: Any,
        *,
        protected_prefix: str | None = None,
        expected_audience: str | None = None,
    ) -> None:
        super().__init__(app)
        self._protected_prefix: str = (
            protected_prefix if protected_prefix is not None else cfg.TRIMCP_JWT_PREFIX
        )
        self._expected_audience: str | None = expected_audience
        # Eagerly check key availability; log once at startup rather than per-request.
        try:
            _build_jwt_key(cfg.TRIMCP_JWT_ALGORITHM)
        except RuntimeError as exc:
            log.warning(
                "JWTAuthMiddleware: %s — all protected routes under %r will "
                "return 401 until the key is configured.",
                exc,
                self._protected_prefix,
            )

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not request.url.path.startswith(self._protected_prefix):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "").strip()
        if not auth_header:
            log.debug(
                "JWT auth rejected: no Authorization header for %s %s",
                request.method,
                request.url.path,
            )
            return _jsonrpc_error(
                _CODE_JWT_INVALID,
                "Authentication failed",
                "missing_authorization_header",
            )

        scheme, _, token_value = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not token_value.strip():
            log.debug(
                "JWT auth rejected: expected 'Bearer <token>', got scheme=%r for %s %s",
                scheme,
                request.method,
                request.url.path,
            )
            return _jsonrpc_error(
                _CODE_JWT_INVALID,
                "Authentication failed",
                "invalid_authorization_scheme",
            )

        try:
            namespace_ctx = decode_agent_token(
                token_value.strip(),
                audience=self._expected_audience,
            )
        except JWTDecodeError as exc:
            return _jsonrpc_error(exc.code, exc.message, exc.reason)

        request.state.namespace_ctx = namespace_ctx
        log.debug(
            "JWT auth OK: namespace=%s agent=%s path=%s",
            namespace_ctx.namespace_id,
            namespace_ctx.agent_id,
            request.url.path,
        )
        return await call_next(request)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "JWTAuthMiddleware",
    "JWTDecodeError",
    "decode_agent_token",
]
