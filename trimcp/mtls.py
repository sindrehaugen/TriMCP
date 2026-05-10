"""Reusable mTLS client-certificate middleware for Starlette/ASGI apps.

Extracted from ``a2a_server.py`` (B6) so the same middleware can protect
both the A2A server and the Admin server without duplication.
"""

from __future__ import annotations

import logging

from starlette.responses import JSONResponse

from trimcp.a2a import A2AMTLSError, mtls_enforce

log = logging.getLogger("trimcp.mtls")

# Default JSON-RPC error code for mTLS failures
DEFAULT_MTLS_ERROR_CODE = -32010


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
        self.allowed_sans = allowed_sans or []
        self.allowed_fingerprints = allowed_fingerprints or []
        self.error_code = error_code

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith(self.protected_prefix):
            await self.app(scope, receive, send)
            return

        headers: dict[str, str] = {}
        for key, value in scope.get("headers", []):
            headers[key.decode("latin-1").lower()] = value.decode("latin-1")

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
            log.warning("mTLS rejection: path=%s reason=%s", path, exc)
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": self.error_code,
                        "message": "mTLS client certificate validation failed",
                        "data": {"reason": str(exc)},
                    },
                    "id": None,
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
