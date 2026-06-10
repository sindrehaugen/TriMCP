"""
nce/me_app.py

Subject-scoped `/api/me/*` surface (consent-bound read/govern surface).
Requires JWT Bearer tokens to authenticate.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from nce.auth import NamespaceContext
from nce.db_utils import scoped_pg_session
from nce.jwt_auth import JWTAuthMiddleware
from nce.orchestrator import NCEEngine

log = logging.getLogger("nce.me_app")


@asynccontextmanager
async def me_lifespan(app: Starlette):
    """Lifespan context manager for me_app.

    Initializes and manages the lifetime of NCEEngine.
    """
    engine = NCEEngine()
    await engine.connect()
    app.state.engine = engine
    log.info("Me API: NCEEngine connected.")
    try:
        yield
    finally:
        await engine.disconnect()
        app.state.engine = None
        log.info("Me API: NCEEngine disconnected.")


async def get_me_memories(request: Request) -> JSONResponse:
    """GET /api/me/memories

    Retrieve memories scoped to the caller's namespace and agent.
    Optionally filters or checks namespace_id / agent_id parameters.
    """
    ns_ctx: NamespaceContext | None = getattr(request.state, "namespace_ctx", None)
    if not ns_ctx or ns_ctx.namespace_id is None:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32005,
                    "message": "Unauthorized",
                    "data": {"reason": "missing_namespace_context"},
                },
                "id": None,
            },
            status_code=401,
        )

    ns_id: UUID = ns_ctx.namespace_id

    # 1. Enforce that if a namespace_id query param is supplied, it must match the token's namespace
    query_ns = request.query_params.get("namespace_id")
    if query_ns:
        try:
            query_ns_uuid = UUID(str(query_ns).strip())
        except ValueError:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32007,
                        "message": "Invalid namespace_id format",
                        "data": {"reason": "invalid_namespace_format"},
                    },
                    "id": None,
                },
                status_code=400,
            )
        if query_ns_uuid != ns_id:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32005,
                        "message": "Forbidden",
                        "data": {"reason": "cross-namespace request is denied"},
                    },
                    "id": None,
                },
                status_code=403,
            )

    # 2. Enforce that if an agent_id query param is supplied, it must match the token's agent
    query_agent = request.query_params.get("agent_id")
    if query_agent and query_agent.strip() != ns_ctx.agent_id:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32005,
                    "message": "Forbidden",
                    "data": {"reason": "cross-agent request is denied"},
                },
                "id": None,
            },
            status_code=403,
        )

    # 3. Retrieve database connection via scoped_pg_session and execute RLS-scoped query
    engine: NCEEngine = request.app.state.engine
    async with scoped_pg_session(engine.pg_pool, ns_id) as conn:
        rows = await conn.fetch(
            "SELECT id, namespace_id, agent_id, memory_type, assertion_type, payload_ref, valid_from, valid_to "
            "FROM memories WHERE agent_id = $1",
            ns_ctx.agent_id,
        )
        return JSONResponse(
            [
                {
                    "id": str(row["id"]),
                    "namespace_id": str(row["namespace_id"]),
                    "agent_id": row["agent_id"],
                    "memory_type": row["memory_type"],
                    "assertion_type": row["assertion_type"],
                    "payload_ref": row["payload_ref"],
                    "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
                    "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
                }
                for row in rows
            ]
        )


app = Starlette(
    debug=False,
    lifespan=me_lifespan,
    middleware=[
        Middleware(
            JWTAuthMiddleware,
            protected_prefix="/api/me",
            expected_audience=None,
        ),
    ],
    routes=[
        Route("/api/me/memories", endpoint=get_me_memories, methods=["GET"]),
    ],
)
