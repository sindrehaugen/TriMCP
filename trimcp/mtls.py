"""Reusable mTLS client-certificate middleware for Starlette/ASGI apps.

Extracted from ``a2a_server.py`` (B6) so the same middleware can protect
both the A2A server and the Admin server without duplication.
"""

from __future__ import annotations

import logging

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from trimcp.a2a import A2AMTLSError, mtls_enforce

log = logging.getLogger("trimcp.mtls")

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
