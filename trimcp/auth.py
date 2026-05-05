"""
trimcp/auth.py

Phase 0.1 — Multi-Tenant Namespacing: HMAC-SHA256 API Authentication.

Public API (imported by admin_server.py and the orchestrator write path):
  - HMACAuthMiddleware       — Starlette middleware; protects HTTP admin endpoints
  - resolve_namespace(...)   — Extract + validate namespace_id UUID from headers
  - validate_agent_id(...)   — Strip / truncate agent_id to safe form
  - set_namespace_context(conn, namespace_id) — SET LOCAL for Postgres RLS

JSON-RPC 2.0 error codes used by this module (server-defined range -32000 to -32099):
  -32001  Authentication failed  (missing / invalid signature)
  -32002  Replay detected        (timestamp outside drift window)
  -32003  Invalid namespace      (missing / malformed UUID)
  -32004  Invalid agent_id       (should never surface; validate_agent_id never raises)

Signature scheme
----------------
Required request headers:
  X-TriMCP-Timestamp:  <unix_epoch_seconds>        integer, UTC
  Authorization:       HMAC-SHA256 <hex_signature>

canonical_message = METHOD\\nPATH\\nTIMESTAMP[\\nSHA256_HEX(raw_body)]
signature         = HMAC-SHA256(TRIMCP_API_KEY, canonical_message)

Notes:
  - Body hash is omitted for requests with an empty body (GET, etc.)
  - Comparison is always constant-time (hmac.compare_digest)
  - Timestamps outside ±5 minutes are rejected (replay protection)
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import logging
import secrets
import time
from base64 import b64decode
from binascii import Error as BinasciiError
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger("trimcp.auth")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIMESTAMP_DRIFT_SECONDS: int = 300  # ±5 minutes replay window

# JSON-RPC 2.0 server-defined error codes
_CODE_AUTH_FAILED: int = -32001
_CODE_REPLAY: int = -32002
_CODE_INVALID_NAMESPACE: int = -32003
_CODE_INVALID_AGENT: int = -32004

_HTTP_UNAUTHORIZED: int = 401
_HTTP_BAD_REQUEST: int = 400


# ---------------------------------------------------------------------------
# Helpers — JSON-RPC 2.0 error responses
# ---------------------------------------------------------------------------

def _jsonrpc_error(
    code: int,
    message: str,
    reason: str,
    request_id: Any = None,
) -> JSONResponse:
    """Build a strict JSON-RPC 2.0 error response.

    HTTP status:
      401 — authentication / replay errors
      400 — malformed namespace / agent_id
    """
    http_status = _HTTP_UNAUTHORIZED if code in (_CODE_AUTH_FAILED, _CODE_REPLAY) else _HTTP_BAD_REQUEST
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
# Pydantic V2 models
# ---------------------------------------------------------------------------

class HMACAuthContext(BaseModel):
    """Validated authentication context extracted from HTTP request headers.

    Immutable after construction (model_config frozen=True).
    """

    model_config = {"frozen": True}

    timestamp: int = Field(..., description="Unix epoch seconds (from X-TriMCP-Timestamp)")
    signature: str = Field(..., description="Lowercase hex HMAC (from Authorization header)")

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("timestamp must be a positive integer")
        return v

    @field_validator("signature", mode="before")
    @classmethod
    def signature_must_be_hex(cls, v: str) -> str:
        stripped = (v or "").strip()
        if not stripped:
            raise ValueError("signature must not be empty")
        try:
            int(stripped, 16)
        except ValueError as exc:
            raise ValueError("signature must be a valid lowercase hex string") from exc
        return stripped.lower()


class NamespaceContext(BaseModel):
    """Validated namespace + agent scoping for multi-tenant RLS.

    Used by the orchestrator write path to carry the resolved identity.
    """

    model_config = {"frozen": True}

    namespace_id: UUID = Field(..., description="Namespace UUID (from X-TriMCP-Namespace-ID)")
    agent_id: str = Field(default="default", description="Agent identifier (from X-TriMCP-Agent-ID)")

    @field_validator("agent_id", mode="before")
    @classmethod
    def clean_agent_id(cls, v: Any) -> str:
        cleaned = (str(v) if v is not None else "").strip()[:128]
        return cleaned if cleaned else "default"


# ---------------------------------------------------------------------------
# Core HMAC helpers
# ---------------------------------------------------------------------------

def _compute_signature(
    api_key: str,
    method: str,
    path: str,
    timestamp: int,
    body_bytes: bytes,
) -> str:
    """Compute the expected HMAC-SHA256 hex signature for a request.

    canonical_message = METHOD\\nPATH\\nTIMESTAMP[\\nSHA256_HEX(body)]
    """
    parts = [method.upper(), path, str(timestamp)]
    if body_bytes:
        parts.append(hashlib.sha256(body_bytes).hexdigest())
    canonical = "\n".join(parts)
    return _hmac.new(
        api_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_hmac(
    api_key: str,
    method: str,
    path: str,
    timestamp: int,
    body_bytes: bytes,
    provided_sig: str,
) -> bool:
    """Constant-time HMAC-SHA256 verification.

    Returns True when the signature is valid, False otherwise.
    An empty api_key always returns False (server misconfigured).
    """
    if not api_key:
        return False
    expected = _compute_signature(api_key, method, path, timestamp, body_bytes)
    return _hmac.compare_digest(expected, provided_sig.strip().lower())


# ---------------------------------------------------------------------------
# Phase 0.1 public helpers (used by orchestrator.py and write path)
# ---------------------------------------------------------------------------

def resolve_namespace(request_headers: dict[str, str]) -> UUID:
    """Extract and validate the namespace_id UUID from request headers.

    Header: X-TriMCP-Namespace-ID: <uuid>

    Raises:
        ValueError — if the header is absent or contains an invalid UUID.
    """
    raw = request_headers.get("x-trimcp-namespace-id", "").strip()
    if not raw:
        raise ValueError("Missing X-TriMCP-Namespace-ID header")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid namespace UUID: {raw!r}") from exc


def validate_agent_id(agent_id: str) -> str:
    """Sanitise agent_id: strip whitespace, truncate to 128 chars.

    Returns 'default' for blank input.  Never raises.
    """
    cleaned = (agent_id or "").strip()[:128]
    return cleaned if cleaned else "default"


async def set_namespace_context(conn: Any, namespace_id: UUID) -> None:
    """Set the Postgres session variable consumed by RLS policies.

    Uses set_config(..., true) which applies only for the current transaction
    (equivalent to SET LOCAL).  Must NOT use bare SET — that would leak across
    pooled connections.

    Args:
        conn:         An asyncpg Connection (or compatible).
        namespace_id: The validated namespace UUID.
    """
    await conn.execute(
        "SELECT set_config('trimcp.namespace_id', $1, true)",
        str(namespace_id),
    )


# ---------------------------------------------------------------------------
# Starlette HMAC middleware
# ---------------------------------------------------------------------------

class HMACAuthMiddleware(BaseHTTPMiddleware):
    """HMAC-SHA256 authentication middleware for Starlette admin endpoints.

    All routes under ``protected_prefix`` (default: ``/api/``) require:
      - ``X-TriMCP-Timestamp`` header (Unix epoch, integer)
      - ``Authorization: HMAC-SHA256 <hex_signature>`` header

    Failed auth attempts always return a strict JSON-RPC 2.0 error body so
    that HTTP and MCP clients can parse failures uniformly.

    Replay protection:
      Requests whose timestamp differs from server time by more than
      ``_TIMESTAMP_DRIFT_SECONDS`` (300 s) are rejected with code -32002.

    Args:
        app:               The ASGI application to wrap.
        protected_prefix:  URL path prefix that requires authentication.
        api_key:           The shared HMAC secret (``TRIMCP_API_KEY``).
    """

    def __init__(
        self,
        app: Any,
        *,
        protected_prefix: str = "/api/",
        api_key: str = "",
    ) -> None:
        super().__init__(app)
        self._protected_prefix = protected_prefix
        self._api_key = api_key
        if not api_key:
            log.warning(
                "HMACAuthMiddleware initialised with empty api_key — "
                "all protected routes will return 401 until TRIMCP_API_KEY is set"
            )

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if not request.url.path.startswith(self._protected_prefix):
            return await call_next(request)

        # Guard: key must be set at middleware construction time
        if not self._api_key:
            log.error(
                "HMAC auth rejected: TRIMCP_API_KEY is empty (server misconfigured)"
            )
            return _jsonrpc_error(
                _CODE_AUTH_FAILED,
                "Authentication failed",
                "server_misconfigured",
            )

        # --- Extract required headers ---
        timestamp_raw = request.headers.get("x-trimcp-timestamp", "").strip()
        auth_header = request.headers.get("authorization", "").strip()

        if not timestamp_raw or not auth_header:
            return _jsonrpc_error(
                _CODE_AUTH_FAILED,
                "Authentication failed",
                "missing_auth_headers",
            )

        # --- Parse "HMAC-SHA256 <hex>" ---
        scheme, _, sig_value = auth_header.partition(" ")
        if scheme.upper() != "HMAC-SHA256" or not sig_value.strip():
            return _jsonrpc_error(
                _CODE_AUTH_FAILED,
                "Authentication failed",
                "invalid_authorization_scheme",
            )

        # --- Validate with Pydantic V2 ---
        try:
            ctx = HMACAuthContext(
                timestamp=int(timestamp_raw),
                signature=sig_value.strip(),
            )
        except (ValueError, Exception) as exc:
            log.warning("HMAC header validation error: %s", exc)
            return _jsonrpc_error(
                _CODE_AUTH_FAILED,
                "Authentication failed",
                "malformed_auth_headers",
            )

        # --- Replay protection ---
        now = int(time.time())
        if abs(now - ctx.timestamp) > _TIMESTAMP_DRIFT_SECONDS:
            log.warning(
                "HMAC replay check failed: request_ts=%d server_ts=%d delta=%d",
                ctx.timestamp,
                now,
                abs(now - ctx.timestamp),
            )
            return _jsonrpc_error(
                _CODE_REPLAY,
                "Request timestamp out of acceptable range",
                "replay_or_clock_skew",
            )

        # --- Read body before passing to next handler ---
        body_bytes = await request.body()

        # --- Verify signature ---
        if not verify_hmac(
            self._api_key,
            request.method,
            request.url.path,
            ctx.timestamp,
            body_bytes,
            ctx.signature,
        ):
            log.warning(
                "HMAC signature mismatch: method=%s path=%s",
                request.method,
                request.url.path,
            )
            return _jsonrpc_error(
                _CODE_AUTH_FAILED,
                "Authentication failed",
                "invalid_signature",
            )

        return await call_next(request)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """HTTP Basic auth for non-API admin UI routes."""

    def __init__(
        self,
        app: Any,
        *,
        protected_prefix: str = "/",
        username: str = "",
        password: str = "",
        excluded_prefixes: tuple[str, ...] = ("/api/",),
        realm: str = "TriMCP Admin",
    ) -> None:
        super().__init__(app)
        self._protected_prefix = protected_prefix
        self._excluded_prefixes = excluded_prefixes
        self._username = username
        self._password = password
        self._realm = realm
        if not username or not password:
            log.warning(
                "BasicAuthMiddleware initialised with empty credentials — "
                "all protected UI routes will return 401 until configured"
            )

    def _challenge(self) -> Response:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{self._realm}"'},
        )

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        path = request.url.path
        if not path.startswith(self._protected_prefix):
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in self._excluded_prefixes):
            return await call_next(request)

        if not self._username or not self._password:
            return self._challenge()

        auth_header = request.headers.get("authorization", "").strip()
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() != "basic" or not token:
            return self._challenge()

        try:
            decoded = b64decode(token).decode("utf-8")
            username, _, password = decoded.partition(":")
        except (ValueError, BinasciiError, UnicodeDecodeError):
            return self._challenge()

        if not (
            secrets.compare_digest(username, self._username)
            and secrets.compare_digest(password, self._password)
        ):
            return self._challenge()

        return await call_next(request)
