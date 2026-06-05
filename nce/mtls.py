"""Reusable mTLS client-certificate middleware for Starlette/ASGI apps.

Extracted from ``a2a_server.py`` (B6) so the same middleware can protect
both the A2A server and the Admin server without duplication.
"""

from __future__ import annotations

import logging
import os

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from nce.a2a import A2AMTLSError, mtls_enforce

log = logging.getLogger("nce.mtls")


class MTLSNotConfiguredError(RuntimeError):
    """Raised when mTLS strict mode is enabled but certificate paths are absent.

    Set ``NCE_MTLS_STRICT=false`` (or the per-service equivalent) to disable
    strict enforcement in local/dev environments — a warning is logged instead.
    """


def assert_bridge_mtls_configured(*, service: str = "bridge") -> None:
    """Assert that mTLS cert paths are set for bridge ingestion adapters.

    Reads ``NCE_MTLS_STRICT`` (default ``true``) and the three cert-path env
    vars.  In strict mode, raises ``MTLSNotConfiguredError`` if any path is
    missing.  In non-strict mode, logs a WARNING and returns.

    Call this from ``BridgeProvider.__init__()`` so every bridge fails fast at
    construction time rather than at runtime when a connection is attempted.
    """
    strict = os.environ.get("NCE_MTLS_STRICT", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }
    cert = os.environ.get("NCE_MTLS_CERT_PATH", "").strip()
    key = os.environ.get("NCE_MTLS_KEY_PATH", "").strip()
    ca = os.environ.get("NCE_MTLS_CA_PATH", "").strip()

    missing = [name for name, val in (
        ("NCE_MTLS_CERT_PATH", cert),
        ("NCE_MTLS_KEY_PATH", key),
        ("NCE_MTLS_CA_PATH", ca),
    ) if not val]

    if not missing:
        return

    msg = (
        f"mTLS cert paths not configured for {service!r} adapter. "
        f"Missing: {', '.join(missing)}. "
        "Set NCE_MTLS_CERT_PATH, NCE_MTLS_KEY_PATH, and NCE_MTLS_CA_PATH, "
        "or set NCE_MTLS_STRICT=false to disable strict enforcement."
    )
    if strict:
        raise MTLSNotConfiguredError(msg)
    log.warning("mTLS not configured (NCE_MTLS_STRICT=false): %s", msg)

# Default JSON-RPC error code for mTLS failures
DEFAULT_MTLS_ERROR_CODE = -32010

_MAX_HEADER_VALUE_BYTES: int = 16_384  # 16 KB — generous for base64-encoded DER certs


class MTLSAuthMiddleware:
    """
    Starlette ASGI middleware that enforces mTLS client certificate validation.

    Parameters
    ----------
    app
        The downstream ASGI application.
    protected_prefix : str
        URL paths starting with this prefix are protected (default ``"/"``).
    enabled : bool
        Whether mTLS enforcement is active.  When ``False`` the middleware
        is a no-op pass-through.
    strict : bool
        If ``True``, missing client certificates raise an error.
        If ``False``, missing certificates are allowed (useful for
        rolling deployments).
    trusted_proxy_hops : int
        Number of trusted reverse-proxy hops in front of the server.
        When > 0, the middleware inspects ``X-Forwarded-*`` headers.
    allowed_sans : list[str]
        Allowed Subject Alternative Names (lower-cased DNS names).
    allowed_fingerprints : list[str]
        Allowed certificate SHA-256 fingerprints (colon-separated hex).
    error_code : int
        JSON-RPC error code returned on mTLS failures (default ``-32010``).
    """

    def __init__(
        self,
        app,
        *,
        protected_prefix: str = "/",
        enabled: bool = False,
        strict: bool = True,
        trusted_proxy_hops: int = 0,
        allowed_sans: list[str] | None = None,
        allowed_fingerprints: list[str] | None = None,
        error_code: int = DEFAULT_MTLS_ERROR_CODE,
    ) -> None:
        self.app = app
        self.protected_prefix = protected_prefix
        self.enabled = enabled
        self.strict = strict
        self.trusted_proxy_hops = trusted_proxy_hops
        self.allowed_sans = [s.lower().strip() for s in (allowed_sans or [])]
        self.allowed_fingerprints = [f.lower().strip() for f in (allowed_fingerprints or [])]
        self.error_code = error_code

        if self.enabled and not self.allowed_sans and not self.allowed_fingerprints:
            raise ValueError(
                "MTLSAuthMiddleware: enabled=True but no trust anchors configured. "
                "Provide at least one allowed_sans or allowed_fingerprints entry."
            )
        if not self.enabled:
            log.warning(
                "MTLSAuthMiddleware: mTLS is DISABLED for prefix %s — "
                "all requests will pass through without certificate validation",
                self.protected_prefix,
            )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        prefix = self.protected_prefix
        if not (path == prefix or path.startswith(prefix.rstrip("/") + "/")):
            await self.app(scope, receive, send)
            return

        headers_obj = Headers(scope=scope)
        headers: dict[str, str] = {}
        for key, value in headers_obj.items():
            if len(value) > _MAX_HEADER_VALUE_BYTES:
                log.warning(
                    "mTLS: oversized header dropped name=%s len=%d path=%s",
                    key[:32],
                    len(value),
                    path,
                )
                continue
            headers[key.lower()] = value

        try:
            mtls_enforce(
                scope=scope,
                headers=headers,
                enabled=True,
                strict=self.strict,
                trusted_proxy_hops=self.trusted_proxy_hops,
                allowed_sans=self.allowed_sans,
                allowed_fingerprints=self.allowed_fingerprints,
            )
        except A2AMTLSError as exc:
            log.warning(
                "mTLS rejection: path=%s reason=%s client_ip=%s",
                path,
                exc,
                scope.get("client", ("unknown", 0))[0],
            )
            request_id = headers.get("x-request-id")
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": self.error_code,
                        "message": "mTLS client certificate validation failed",
                        "data": {"reason": "mtls_validation_failed"},
                    },
                    "id": request_id,
                },
                status_code=401,
                headers={"WWW-Authenticate": "TLS"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
