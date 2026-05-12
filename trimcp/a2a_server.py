"""
trimcp/a2a_server.py

Phase 3.1 — A2A (Agent-to-Agent) Protocol Surface

Starlette ASGI application exposing the public A2A bridge endpoints:

  GET  /.well-known/agent-card     — public agent capability descriptor
  POST /tasks/send                 — submit a skill task (JWT-protected)
  GET  /tasks/{task_id}            — poll task status (JWT-protected)
  POST /tasks/{task_id}/cancel     — cancel a running task (JWT-protected)

Authentication
--------------
  - /.well-known/agent-card  → unauthenticated (public discovery)
  - /tasks/*                 → JWTAuthMiddleware (Bearer token, NamespaceContext)

Task state is held in an in-memory dict (Phase 3.1).  Tasks are short-lived
(seconds to low-minutes); use the poll endpoint for async clients.

JSON-RPC 2.0 error codes
-------------------------
  -32005  JWT validation failure
  -32006  JWT missing namespace_id claim
  -32007  JWT invalid claim value
  -32010  A2A authorization failure (bad/expired sharing token)
  -32011  A2A scope violation (resource not in granted scopes)
  -32012  Bad skill or missing parameters

Run standalone:
  uvicorn trimcp.a2a_server:app --host 0.0.0.0 --port 8004
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from trimcp.orchestrator import TriStackEngine
from uuid import uuid4

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from trimcp.a2a import (
    A2A_CODE_BAD_REQUEST,
    A2A_CODE_SCOPE_VIOLATION,
    A2A_CODE_UNAUTHORIZED,
    A2AAuthorizationError,
    A2AScopeViolationError,
    enforce_scope,
    verify_token,
)
from trimcp.auth import NamespaceContext
from trimcp.config import cfg
from trimcp.jwt_auth import JWTAuthMiddleware
from trimcp.models import GraphSearchRequest

log = logging.getLogger("trimcp.a2a_server")

# JSON-RPC 2.0 error code for mTLS failures (same range as A2A_UNAUTHORIZED)
A2A_CODE_MTLS = -32013  # mTLS client certificate validation failed


# ---------------------------------------------------------------------------
# mTLS Client Certificate Middleware (imported from shared module)
# ---------------------------------------------------------------------------

from trimcp.mtls import MTLSAuthMiddleware  # noqa: E402

# ---------------------------------------------------------------------------
# Graceful shutdown machinery
# ---------------------------------------------------------------------------
_SHUTDOWN_EVENT: asyncio.Event | None = None
_ACTIVE_REQUESTS: int = 0
_ACTIVE_REQUESTS_LOCK: asyncio.Lock = asyncio.Lock()
_GRACE_PERIOD_S: int = 30  # max seconds to wait for active requests to drain


def _init_shutdown() -> None:
    """Initialise the shutdown event if not already set."""
    global _SHUTDOWN_EVENT
    if _SHUTDOWN_EVENT is None:
        _SHUTDOWN_EVENT = asyncio.Event()


def _is_shutting_down() -> bool:
    """Return True if the server is in graceful-shutdown mode."""
    return _SHUTDOWN_EVENT is not None and _SHUTDOWN_EVENT.is_set()


async def _reject_if_shutting_down(request: Request) -> JSONResponse | None:
    """Return a 503 JSON response if the server is shutting down, else None."""
    if _is_shutting_down():
        return JSONResponse(
            {
                "error": "Server shutting down",
                "detail": "No new requests accepted during graceful shutdown",
            },
            status_code=503,
        )
    return None


@asynccontextmanager
async def _track_active_request():
    """Context manager that tracks the active-request counter for graceful drain."""
    global _ACTIVE_REQUESTS
    async with _ACTIVE_REQUESTS_LOCK:
        _ACTIVE_REQUESTS += 1
    try:
        yield
    finally:
        async with _ACTIVE_REQUESTS_LOCK:
            _ACTIVE_REQUESTS -= 1


async def _drain_active_requests(timeout: int = _GRACE_PERIOD_S) -> int:
    """Wait up to *timeout* seconds for active requests to finish.

    Returns the number of requests still in-flight after the deadline.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        async with _ACTIVE_REQUESTS_LOCK:
            remaining = _ACTIVE_REQUESTS
        if remaining == 0:
            return 0
        wait = deadline - asyncio.get_running_loop().time()
        if wait <= 0:
            return remaining
        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# In-memory task store  (task_id → task dict)
# ---------------------------------------------------------------------------
_tasks: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Engine reference (injected via lifespan)
# ---------------------------------------------------------------------------
_engine: TriStackEngine | None = None


# ---------------------------------------------------------------------------
# Agent card (A2A protocol discovery document)
# ---------------------------------------------------------------------------
_AGENT_CARD: dict[str, Any] = {
    "schema_version": "0.2",
    "name": "TriMCP Memory Engine",
    "description": (
        "Persistent, verifiable, temporal AI memory engine. "
        "Provides cognitive memory services including semantic recall, "
        "knowledge graph traversal, session archival, and memory integrity verification. "
        "Memories decay, consolidate, and strengthen over time via bio-inspired algorithms."
    ),
    "url": os.environ.get("TRIMCP_A2A_URL", "http://localhost:8004"),
    "version": "1.0",
    "capabilities": {
        "streaming": False,
        "stateTransitionHistory": False,
        "pushNotifications": False,
    },
    "skills": [
        {
            "id": "recall_relevant_context",
            "name": "Recall Relevant Context",
            "description": (
                "Semantic search combined with knowledge graph traversal to retrieve "
                "the most relevant memories and associated context."
            ),
            "inputModes": ["text"],
            "outputModes": ["text"],
            "parameters": {
                "query": {"type": "string", "required": True},
                "namespace_id": {"type": "string", "format": "uuid", "required": True},
                "agent_id": {"type": "string", "required": False},
                "user_id": {"type": "string", "required": False},
                "top_k": {"type": "integer", "default": 5, "required": False},
            },
        },
        {
            "id": "archive_session",
            "name": "Archive Session",
            "description": "Batch-store a list of memory payloads from a completed session.",
            "inputModes": ["text"],
            "outputModes": ["text"],
            "parameters": {
                "namespace_id": {"type": "string", "format": "uuid", "required": True},
                "agent_id": {"type": "string", "required": True},
                "user_id": {"type": "string", "required": False},
                "memories": {
                    "type": "array",
                    "required": True,
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "summary": {"type": "string"},
                        },
                    },
                },
            },
        },
        {
            "id": "find_related_decisions",
            "name": "Find Related Decisions",
            "description": "Knowledge graph search to surface related decisions and context nodes.",
            "inputModes": ["text"],
            "outputModes": ["text"],
            "parameters": {
                "query": {"type": "string", "required": True},
                "namespace_id": {"type": "string", "format": "uuid", "required": True},
                "agent_id": {"type": "string", "required": False},
                "user_id": {"type": "string", "required": False},
                "max_depth": {"type": "integer", "default": 2, "required": False},
            },
        },
        {
            "id": "verify_memory_integrity",
            "name": "Verify Memory Integrity",
            "description": "Verify the HMAC signature of a stored memory to confirm it was not tampered with.",
            "inputModes": ["text"],
            "outputModes": ["text"],
            "parameters": {
                "memory_id": {"type": "string", "format": "uuid", "required": True},
                "namespace_id": {"type": "string", "format": "uuid", "required": True},
                "user_id": {"type": "string", "required": False},
            },
        },
        {
            "id": "get_cognitive_state",
            "name": "Get Cognitive State",
            "description": (
                "Retrieve the N most recent memories representing an agent's current "
                "cognitive state (fast Redis-backed recall)."
            ),
            "inputModes": ["text"],
            "outputModes": ["text"],
            "parameters": {
                "namespace_id": {"type": "string", "format": "uuid", "required": True},
                "agent_id": {"type": "string", "required": True},
                "user_id": {"type": "string", "required": False},
                "n": {"type": "integer", "default": 10, "required": False},
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------


def _jsonrpc_err(code: int, message: str, reason: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "error": {
            "code": code,
            "message": message,
            "data": {"reason": reason},
        },
        "id": None,
    }


# ---------------------------------------------------------------------------
# Task state helpers
# ---------------------------------------------------------------------------


def _make_task(
    task_id: str, state: str, artifacts: list | None = None, message: str | None = None
) -> dict[str, Any]:
    task: dict[str, Any] = {
        "id": task_id,
        "status": {
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "artifacts": artifacts or [],
    }
    if message:
        task["status"]["message"] = {
            "role": "agent",
            "parts": [{"type": "text", "text": message}],
        }
    return task


def _require_param(params: dict[str, Any], key: str) -> Any:
    val = params.get(key)
    if val is None:
        raise ValueError(f"Missing required parameter: {key!r}")
    return val


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def get_agent_card(request: Request) -> JSONResponse:
    """GET /.well-known/agent-card — public, unauthenticated."""
    rejected = await _reject_if_shutting_down(request)
    if rejected:
        return rejected
    async with _track_active_request():
        return JSONResponse(_AGENT_CARD)


async def tasks_send(request: Request) -> JSONResponse:
    """POST /tasks/send — Submit a skill invocation task."""
    rejected = await _reject_if_shutting_down(request)
    if rejected:
        return rejected

    if _engine is None:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    caller_ctx: NamespaceContext | None = getattr(request.state, "namespace_ctx", None)
    if caller_ctx is None:
        return JSONResponse(
            _jsonrpc_err(
                A2A_CODE_UNAUTHORIZED,
                "Authentication failed",
                "missing_namespace_context",
            ),
            status_code=401,
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            _jsonrpc_err(A2A_CODE_BAD_REQUEST, "Bad request", "invalid_json"),
            status_code=400,
        )

    task_id: str = str(body.get("id") or uuid4())
    skill: str = str(body.get("skill") or "").strip()
    params: dict[str, Any] = body.get("params") or {}
    sharing_token: str | None = body.get("sharing_token")  # optional cross-agent token

    if not skill:
        return JSONResponse(
            _jsonrpc_err(A2A_CODE_BAD_REQUEST, "Bad request", "missing_skill"),
            status_code=400,
        )

    _tasks[task_id] = _make_task(task_id, "submitted")

    async with _track_active_request():
        try:
            # --- Cross-agent scope validation (A2A sharing token path) ---
            if sharing_token is not None:
                async with _engine.pg_pool.acquire(timeout=10.0) as conn:
                    verified = await verify_token(conn, sharing_token, caller_ctx)

                # Enforce the namespace scope covers the requested namespace_id
                params.get("namespace_id") or ""
                enforce_scope(
                    verified.scopes,
                    "namespace",
                    str(verified.owner_namespace_id),
                    str(verified.owner_namespace_id),
                )

                # Override the params to operate in the owner's namespace
                params = dict(params)
                params["namespace_id"] = str(verified.owner_namespace_id)
                params["_owner_agent_id"] = verified.owner_agent_id

                log.info(
                    "A2A cross-agent access granted: grant=%s consumer_ns=%s owner_ns=%s skill=%s",
                    verified.grant_id,
                    caller_ctx.namespace_id,
                    verified.owner_namespace_id,
                    skill,
                )

            result = await _dispatch_skill(skill, params, caller_ctx)
            task = _make_task(
                task_id,
                "completed",
                artifacts=[{"type": "text", "text": json.dumps(result)}],
            )
            _tasks[task_id] = task
            return JSONResponse(task, status_code=200)

        except A2AAuthorizationError as exc:
            task = _make_task(task_id, "failed", message=str(exc))
            _tasks[task_id] = task
            return JSONResponse(
                _jsonrpc_err(
                    A2A_CODE_UNAUTHORIZED, "A2A authorization failure", str(exc)
                ),
                status_code=403,
            )
        except A2AScopeViolationError as exc:
            task = _make_task(task_id, "failed", message=str(exc))
            _tasks[task_id] = task
            return JSONResponse(
                _jsonrpc_err(A2A_CODE_SCOPE_VIOLATION, "Scope violation", str(exc)),
                status_code=403,
            )
        except ValueError as exc:
            task = _make_task(task_id, "failed", message=str(exc))
            _tasks[task_id] = task
            return JSONResponse(
                _jsonrpc_err(
                    A2A_CODE_BAD_REQUEST, "Invalid skill parameters", str(exc)
                ),
                status_code=400,
            )
        except Exception as exc:
            log.exception("tasks_send failed task_id=%s skill=%s", task_id, skill)
            task = _make_task(
                task_id, "failed", message=f"Internal error: {type(exc).__name__}"
            )
            _tasks[task_id] = task
            return JSONResponse({"error": "Internal error"}, status_code=500)


async def tasks_get(request: Request) -> JSONResponse:
    """GET /tasks/{task_id} — Poll task status."""
    rejected = await _reject_if_shutting_down(request)
    if rejected:
        return rejected
    async with _track_active_request():
        task_id = request.path_params.get("task_id", "")
        task = _tasks.get(task_id)
        if task is None:
            return JSONResponse(
                {"error": "Task not found", "task_id": task_id}, status_code=404
            )
        return JSONResponse(task)


async def tasks_cancel(request: Request) -> JSONResponse:
    """POST /tasks/{task_id}/cancel — Cancel a task."""
    rejected = await _reject_if_shutting_down(request)
    if rejected:
        return rejected
    async with _track_active_request():
        task_id = request.path_params.get("task_id", "")
        task = _tasks.get(task_id)
        if task is None:
            return JSONResponse(
                {"error": "Task not found", "task_id": task_id}, status_code=404
            )

        current_state = task["status"]["state"]
        if current_state in ("completed", "failed", "canceled"):
            return JSONResponse(
                {
                    "error": f"Task already in terminal state: {current_state!r}",
                    "task_id": task_id,
                },
                status_code=409,
            )

        _tasks[task_id] = _make_task(task_id, "canceled")
        return JSONResponse(_tasks[task_id])


# ---------------------------------------------------------------------------
# Skill dispatch
# ---------------------------------------------------------------------------


async def _dispatch_skill(
    skill: str,
    params: dict[str, Any],
    caller_ctx: NamespaceContext,
) -> Any:
    """Route an A2A skill ID to the appropriate TriStackEngine method."""
    assert _engine is not None, "engine not initialized"

    if skill == "recall_relevant_context":
        query = _require_param(params, "query")
        ns_id = _require_param(params, "namespace_id")
        agent_id = params.get("agent_id", caller_ctx.agent_id or "default")
        top_k = max(1, min(int(params.get("limit", params.get("top_k", 5))), 20))
        offset = max(0, int(params.get("offset", 0)))

        semantic = await _engine.semantic_search(
            namespace_id=ns_id,
            agent_id=agent_id,
            query=query,
            limit=top_k,
            offset=offset,
        )
        try:
            graph: dict = await _engine.graph_search(
                GraphSearchRequest(query=query, namespace_id=uuid.UUID(ns_id), max_depth=1)
            )
        except Exception:
            graph = {}

        return {"semantic": semantic, "graph": graph}

    if skill == "archive_session":
        from trimcp.models import MemoryType, StoreMemoryRequest

        memories = _require_param(params, "memories")
        ns_id = _require_param(params, "namespace_id")
        agent_id = _require_param(params, "agent_id")

        if not isinstance(memories, list):
            raise ValueError("'memories' must be a list of memory objects")

        refs: list[str] = []
        for m in memories:
            req = StoreMemoryRequest(
                namespace_id=uuid.UUID(ns_id),
                agent_id=agent_id,
                content=m.get("content", ""),
                summary=m.get("summary") or m.get("content", "")[:200],
                heavy_payload=m.get("content", ""),
                memory_type=MemoryType.episodic,
            )
            result = await _engine.store_memory(req)
            refs.append(str(result.get("payload_ref", "")))

        return {"archived": len(refs), "refs": refs}

    if skill == "find_related_decisions":
        query = _require_param(params, "query")
        ns_id = _require_param(params, "namespace_id")
        max_depth = max(1, min(int(params.get("max_depth", 2)), 3))
        agent_id = params.get("agent_id")

        result = await _engine.graph_search(
            GraphSearchRequest(
                query=query,
                namespace_id=uuid.UUID(ns_id),
                max_depth=max_depth,
                agent_id=agent_id,
            )
        )
        return result

    if skill == "verify_memory_integrity":
        memory_id_str = _require_param(params, "memory_id")
        return await _engine.verify_memory(memory_id=memory_id_str)

    if skill == "get_cognitive_state":
        ns_id = _require_param(params, "namespace_id")
        agent_id = _require_param(params, "agent_id")
        user_id = params.get("user_id", "default")
        n = max(1, min(int(params.get("n", 10)), 50))

        context = await _engine.recall_memory(
            namespace_id=ns_id,
            user_id=user_id,
            session_id=agent_id,
        )
        return {"context": context, "n_requested": n}

    raise ValueError(f"Unknown A2A skill: {skill!r}")


# ---------------------------------------------------------------------------
# Health route
# ---------------------------------------------------------------------------


async def get_health(request: Request) -> JSONResponse:
    rejected = await _reject_if_shutting_down(request)
    if rejected:
        return rejected
    if _engine is None:
        return JSONResponse({"status": "down"}, status_code=503)
    async with _track_active_request():
        res = await _engine.check_health()
        return JSONResponse(res)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: Starlette):
    global _engine
    from trimcp.orchestrator import TriStackEngine

    _init_shutdown()

    _engine = TriStackEngine()
    await _engine.connect()
    log.info("A2A server: TriStackEngine connected.")
    yield
    # --- Graceful shutdown phase ---
    log.info(
        "A2A server: initiating graceful shutdown (draining active requests, max %ds)...",
        _GRACE_PERIOD_S,
    )
    if _SHUTDOWN_EVENT is not None:
        _SHUTDOWN_EVENT.set()

    remaining = await _drain_active_requests()
    if remaining > 0:
        log.warning(
            "A2A server: %d request(s) still in-flight after grace period — disconnecting anyway",
            remaining,
        )
    else:
        log.info("A2A server: all active requests completed.")
    await _engine.disconnect()
    _engine = None
    log.info("A2A server: shutdown complete.")


# ---------------------------------------------------------------------------
# ASGI application
# ---------------------------------------------------------------------------

app = Starlette(
    debug=False,
    lifespan=lifespan,
    middleware=[
        Middleware(
            MTLSAuthMiddleware,
            protected_prefix="/tasks",
            enabled=cfg.TRIMCP_A2A_MTLS_ENABLED,
            strict=cfg.TRIMCP_A2A_MTLS_STRICT,
            trusted_proxy_hops=cfg.TRIMCP_A2A_MTLS_TRUSTED_PROXY_HOP,
            allowed_sans=cfg.TRIMCP_A2A_MTLS_ALLOWED_SANS,
            allowed_fingerprints=cfg.TRIMCP_A2A_MTLS_ALLOWED_FINGERPRINTS,
            error_code=A2A_CODE_MTLS,
        ),
        Middleware(
            JWTAuthMiddleware,
            protected_prefix="/tasks",
            # Require a dedicated audience so tokens issued for other
            # services (web frontend, admin UI) are rejected here.
            expected_audience=cfg.TRIMCP_A2A_JWT_AUDIENCE,
        ),
    ],
    routes=[
        Route("/health", endpoint=get_health, methods=["GET"]),
        Route("/.well-known/agent-card", endpoint=get_agent_card, methods=["GET"]),
        Route("/tasks/send", endpoint=tasks_send, methods=["POST"]),
        Route("/tasks/{task_id}", endpoint=tasks_get, methods=["GET"]),
        Route("/tasks/{task_id}/cancel", endpoint=tasks_cancel, methods=["POST"]),
    ],
)


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)

    _init_shutdown()

    def _handle_sigterm(signum: int, frame: object | None) -> None:
        log.info("Received SIGTERM — initiating graceful shutdown.")
        if _SHUTDOWN_EVENT is not None:
            _SHUTDOWN_EVENT.set()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    log.info(
        "SIGTERM handler registered for graceful shutdown (grace period: %ds).",
        _GRACE_PERIOD_S,
    )

    uvicorn.run(app, host="0.0.0.0", port=8004)
