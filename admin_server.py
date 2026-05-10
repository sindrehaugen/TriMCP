from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from starlette.routing import Route

from trimcp.auth import (
    BasicAuthMiddleware,
    HMACAuthMiddleware,
    optional_hmac_nonce_store,
)
from trimcp.config import cfg
from trimcp.event_log import verify_merkle_chain
from trimcp.mtls import MTLSAuthMiddleware
from trimcp.notifications import dispatcher
from trimcp.observability import MERKLE_CHAIN_VALID, OpenTelemetryTraceMiddleware
from trimcp.orchestrator import TriStackEngine
from trimcp.temporal import parse_as_of

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trimcp-admin")

engine: TriStackEngine | None = None

_hmac_nonce_store = optional_hmac_nonce_store()


@asynccontextmanager
async def lifespan(app):
    global engine
    engine = TriStackEngine()
    await engine.connect()
    await dispatcher.start_worker()
    logger.info("TriMCP Admin: engine connected, dispatcher started.")

    # Startup safety: ensure event_log partitions exist for the current month
    try:
        from trimcp.observability import EVENT_LOG_PARTITION_MONTHS_AHEAD

        async with engine.pg_pool.acquire() as conn:
            await conn.execute("SELECT trimcp_ensure_event_log_monthly_partitions(3)")
            row = await conn.fetchrow(
                """
                SELECT count(*) AS cnt
                FROM pg_inherits i
                JOIN pg_class c ON c.oid = i.inhrelid
                WHERE i.inhparent = 'event_log'::regclass
                  AND c.relname LIKE 'event_log_%'
                  AND c.relname >= 'event_log_' || to_char(now(), 'YYYY_MM')
                """
            )
            months_ahead = row["cnt"] if row else 0
            EVENT_LOG_PARTITION_MONTHS_AHEAD.set(months_ahead)
            if months_ahead < 2:
                logger.warning(
                    "event_log partition runway low: %s months ahead (need >= 2)",
                    months_ahead,
                )
            else:
                logger.info("event_log partition runway: %s months ahead", months_ahead)
    except Exception:
        logger.exception("event_log partition startup check failed")

    yield
    await dispatcher.stop_worker()
    await engine.disconnect()
    logger.info("TriMCP Admin: shutdown complete.")


async def get_health(request):
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    health = await engine.check_health()

    # Check nested database statuses for any "down" components
    db_health = health.get("databases", {})
    if any(status == "down" for status in db_health.values()):
        await dispatcher.dispatch_alert(
            "Database Health Alert", f"Current health: {json.dumps(health)}"
        )

    return JSONResponse(health)


async def get_health_v1(request):
    """GET /api/health/v1 — deprecated alias, returns same data as /api/health."""
    return await get_health(request)


async def trigger_gc(request):
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        result = await engine.force_gc()
        return JSONResponse({"status": "success", "result": result})
    except Exception as e:
        logger.error("GC failed: %s", e)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def api_search(request):
    """POST /api/search — unified semantic search with optional temporal filter.

    Request body (JSON):
        namespace_id  str   required
        agent_id      str   required
        query         str   required
        top_k         int   optional, default 5
        as_of         str   optional ISO 8601 UTC timestamp for time-travel reads
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Request body must be valid JSON"}, status_code=400
        )

    missing = [f for f in ("namespace_id", "agent_id", "query") if not body.get(f)]
    if missing:
        return JSONResponse(
            {"error": f"Missing required fields: {', '.join(missing)}"},
            status_code=422,
        )

    try:
        as_of_dt = parse_as_of(body.get("as_of"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    from trimcp import quotas as _quotas

    try:
        q_res = await _quotas.consume_for_tool(
            engine.pg_pool, "api_semantic_search", body
        )
    except _quotas.QuotaExceededError as exc:
        return JSONResponse({"error": str(exc)}, status_code=429)

    try:
        results = await engine.semantic_search(
            namespace_id=body["namespace_id"],
            agent_id=body["agent_id"],
            query=body["query"],
            limit=int(body.get("limit", body.get("top_k", 5))),
            offset=int(body.get("offset", 0)),
            as_of=as_of_dt,
        )
        return JSONResponse({"results": results})
    except Exception as exc:
        await q_res.rollback()
        logger.error("api_search failed: %s", exc)
        return JSONResponse(
            {"error": "Search failed", "detail": str(exc)}, status_code=500
        )


async def serve_index(request):
    index_path = os.path.join(os.path.dirname(__file__), "admin", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("Admin UI not found", status_code=404)


# ---------------------------------------------------------------------------
# Phase 2.3 — Replay endpoints
# ---------------------------------------------------------------------------


async def api_replay_observe(request):
    """POST /api/replay/observe

    Stream historical events from a namespace as a JSONL response body.
    Each line is a JSON object with ``type`` in {event, progress, complete, error}.

    Request body (JSON):
        namespace_id     str   required
        start_seq        int   optional, default 1
        end_seq          int   optional, defaults to latest
        agent_id_filter  str   optional
        max_events       int   optional, default 500
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Request body must be valid JSON"}, status_code=400
        )

    if not body.get("namespace_id"):
        return JSONResponse(
            {"error": "Missing required field: namespace_id"}, status_code=422
        )

    try:
        ns_id = uuid.UUID(body["namespace_id"])
    except ValueError:
        return JSONResponse(
            {"error": "namespace_id is not a valid UUID"}, status_code=422
        )

    start_seq = int(body.get("start_seq", 1))
    end_seq = int(body["end_seq"]) if "end_seq" in body else None
    agent_filter = body.get("agent_id_filter")
    max_events = int(body.get("max_events", 500))

    from trimcp.replay import ObservationalReplay

    async def _stream_events() -> AsyncGenerator[str, None]:
        """Inner async generator — never materialises the full list in RAM."""
        replay = ObservationalReplay(pool=engine.pg_pool)
        count = 0
        try:
            async for item in replay.execute(
                source_namespace_id=ns_id,
                start_seq=start_seq,
                end_seq=end_seq,
                agent_id_filter=agent_filter,
            ):
                yield json.dumps(item) + "\n"
                if item.get("type") == "event":
                    count += 1
                    if count >= max_events:
                        yield (
                            json.dumps(
                                {
                                    "type": "truncated",
                                    "reason": "max_events_reached",
                                    "events_returned": count,
                                }
                            )
                            + "\n"
                        )
                        return
        except Exception as exc:
            logger.exception("api_replay_observe stream failed ns=%s", ns_id)
            yield (
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Stream failed after {count} events: {exc}",
                    }
                )
                + "\n"
            )

    return StreamingResponse(
        _stream_events(),
        media_type="application/x-ndjson",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# Phase 3 — Snapshot export (streaming NDJSON)
# ---------------------------------------------------------------------------


async def api_snapshot_export(request):
    """POST /api/snapshot/export

    Stream all memories for a namespace (at a point in time) as NDJSON.
    Uses a server-side asyncpg cursor — orchestrator RAM stays flat
    regardless of export size.  GB-scale exports safe.

    Request body (JSON):
        namespace_id  str   required
        snapshot_id   str   optional — resolve export to a named snapshot
        as_of         str   optional ISO 8601 UTC timestamp (default: now)

    Response: ``application/x-ndjson`` with lines of type:
        metadata — export header (format version, as_of)
        memory   — one per memory record
        progress — periodic progress marker
        complete — final summary
        error    — terminal error
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Request body must be valid JSON"}, status_code=400
        )

    ns_id = body.get("namespace_id")
    if not ns_id:
        return JSONResponse(
            {"error": "Missing required field: namespace_id"}, status_code=422
        )

    try:
        uuid.UUID(ns_id)
    except ValueError:
        return JSONResponse(
            {"error": "namespace_id is not a valid UUID"}, status_code=422
        )

    snapshot_id = body.get("snapshot_id")
    if snapshot_id:
        try:
            uuid.UUID(snapshot_id)
        except ValueError:
            return JSONResponse(
                {"error": "snapshot_id is not a valid UUID"}, status_code=422
            )

    as_of_raw = body.get("as_of")
    from trimcp.temporal import parse_as_of

    as_of_dt = parse_as_of(as_of_raw) if as_of_raw else None

    from trimcp.snapshot_mcp_handlers import stream_snapshot_export

    return StreamingResponse(
        stream_snapshot_export(engine, ns_id, as_of=as_of_dt, snapshot_id=snapshot_id),
        media_type="application/x-ndjson",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-cache",
        },
    )


async def api_replay_fork(request):
    """POST /api/replay/fork

    Start a forked replay as a background task.
    Returns ``{"run_id": "<uuid>", ...}`` immediately; poll ``/api/replay/status/<run_id>``.

    Request body (JSON):
        source_namespace_id  str   required
        target_namespace_id  str   required
        fork_seq             int   required
        start_seq            int   optional, default 1
        replay_mode          str   optional, "deterministic" | "re-execute", default "deterministic"
        config_overrides     obj   optional, used only in re-execute mode
        agent_id_filter      str   optional
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Request body must be valid JSON"}, status_code=400
        )

    required = ("source_namespace_id", "target_namespace_id", "fork_seq")
    missing = [f for f in required if not body.get(f) and body.get(f) != 0]
    if missing:
        return JSONResponse(
            {"error": f"Missing required fields: {', '.join(missing)}"},
            status_code=422,
        )

    from pydantic import ValidationError

    from trimcp.models import ReplayForkRequest

    try:
        fork_req = ReplayForkRequest.model_validate(
            {
                "source_namespace_id": body["source_namespace_id"],
                "target_namespace_id": body["target_namespace_id"],
                "fork_seq": int(body["fork_seq"]),
                "start_seq": int(body.get("start_seq", 1)),
                "replay_mode": body.get("replay_mode", "deterministic"),
                "config_overrides": body.get("config_overrides"),
                "agent_id_filter": body.get("agent_id_filter"),
            }
        )
    except ValidationError as exc:
        return JSONResponse(
            {"error": "Invalid request", "detail": exc.errors(include_url=False)},
            status_code=422,
        )

    # ── Build the frozen execution config (immutable after this point) ──
    from trimcp.models import FrozenForkConfig

    frozen_config = FrozenForkConfig.from_request(fork_req)

    try:
        from trimcp.replay import ForkedReplay, _create_run

        # Pre-create the row so run_id is available before the background task runs.
        async with engine.pg_pool.acquire() as pre_conn:
            fork_run_id = await _create_run(
                pre_conn,
                source_namespace_id=frozen_config.source_namespace_id,
                target_namespace_id=frozen_config.target_namespace_id,
                mode="forked",
                replay_mode=frozen_config.replay_mode,
                start_seq=frozen_config.start_seq,
                end_seq=frozen_config.fork_seq,
                divergence_seq=frozen_config.fork_seq,
                config_overrides=frozen_config.overrides_dict,
            )

        replay = ForkedReplay(pool=engine.pg_pool)

        async def _run_fork() -> None:
            try:
                async for _ in replay.execute(
                    frozen_config=frozen_config,
                    _existing_run_id=fork_run_id,
                ):
                    pass
            except Exception:
                logger.exception(
                    "Background ForkedReplay failed run_id=%s", fork_run_id
                )

        asyncio.create_task(_run_fork(), name=f"fork-{fork_run_id}")
        return JSONResponse(
            {
                "status": "started",
                "run_id": str(fork_run_id),
                "source_namespace": str(frozen_config.source_namespace_id),
                "target_namespace": str(frozen_config.target_namespace_id),
                "fork_seq": frozen_config.fork_seq,
                "replay_mode": frozen_config.replay_mode,
            },
            status_code=202,
        )

    except Exception as exc:
        logger.exception(
            "api_replay_fork failed src=%s tgt=%s",
            frozen_config.source_namespace_id,
            frozen_config.target_namespace_id,
        )
        return JSONResponse(
            {"error": "Fork replay failed to start", "detail": str(exc)},
            status_code=500,
        )


async def api_replay_status(request):
    """GET /api/replay/status/{run_id}

    Return the current status and progress of a replay run.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    run_id_str = request.path_params.get("run_id", "")
    try:
        run_id = uuid.UUID(run_id_str)
    except ValueError:
        return JSONResponse({"error": "run_id is not a valid UUID"}, status_code=422)

    try:
        from trimcp.replay import ReplayRunNotFoundError, get_run_status

        status = await get_run_status(pool=engine.pg_pool, run_id=run_id)
        return JSONResponse(status)
    except ReplayRunNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        logger.exception("api_replay_status failed run_id=%s", run_id)
        return JSONResponse(
            {"error": "Status check failed", "detail": str(exc)}, status_code=500
        )


async def api_event_provenance(request):
    """GET /api/replay/provenance/{memory_id}

    Trace the full causal chain for a memory via ``parent_event_id`` links.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    memory_id_str = request.path_params.get("memory_id", "")
    try:
        memory_id = uuid.UUID(memory_id_str)
    except ValueError:
        return JSONResponse({"error": "memory_id is not a valid UUID"}, status_code=422)

    try:
        from trimcp.replay import get_event_provenance

        provenance = await get_event_provenance(
            pool=engine.pg_pool, memory_id=memory_id
        )
        return JSONResponse(provenance)
    except Exception as exc:
        logger.exception("api_event_provenance failed memory_id=%s", memory_id)
        return JSONResponse(
            {"error": "Provenance trace failed", "detail": str(exc)}, status_code=500
        )


# ---------------------------------------------------------------------------
# Phase 3.1 — A2A Grant management (HMAC-protected admin endpoints)
# ---------------------------------------------------------------------------


async def api_a2a_create_grant(request):
    """POST /api/a2a/grants/create

    Create an A2A sharing grant. The caller must be authenticated as the owner
    namespace via HMAC. Returns a one-time sharing_token to pass to the recipient.

    Body (JSON):
      namespace_id          (str, UUID, required)
      agent_id              (str, required)
      scopes                (list[{resource_type, resource_id, permissions}], required)
      target_namespace_id   (str, UUID, optional) — restrict to a specific recipient namespace
      target_agent_id       (str, optional)       — restrict to a specific recipient agent
      expires_in_seconds    (int, optional, default 3600)
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    from trimcp.a2a import A2AGrantRequest, A2AScope, create_grant
    from trimcp.auth import NamespaceContext

    try:
        ns_id = uuid.UUID(body["namespace_id"])
        agent_id_val = body.get("agent_id", "default")
        caller_ctx = NamespaceContext(namespace_id=ns_id, agent_id=agent_id_val)
        scopes_raw = body.get("scopes", [])
        scopes = [A2AScope.model_validate(s) for s in scopes_raw]
        req = A2AGrantRequest(
            target_namespace_id=body.get("target_namespace_id"),
            target_agent_id=body.get("target_agent_id"),
            scopes=scopes,
            expires_in_seconds=int(body.get("expires_in_seconds", 3600)),
        )
    except (KeyError, ValueError) as exc:
        return JSONResponse(
            {"error": "Bad request parameters", "detail": str(exc)}, status_code=422
        )

    try:
        async with engine.pg_pool.acquire() as conn:
            resp = await create_grant(conn, caller_ctx, req)
    except Exception as exc:
        logger.exception("api_a2a_create_grant failed ns=%s", ns_id)
        return JSONResponse(
            {"error": "Failed to create grant", "detail": str(exc)}, status_code=500
        )

    return JSONResponse(
        {
            "grant_id": str(resp.grant_id),
            "sharing_token": resp.sharing_token,
            "expires_at": resp.expires_at.isoformat(),
        },
        status_code=201,
    )


async def api_a2a_revoke_grant(request):
    """POST /api/a2a/grants/{grant_id}/revoke

    Revoke an active A2A grant. Only the owning namespace can revoke.

    Body (JSON):
      namespace_id   (str, UUID, required)
      agent_id       (str, optional)
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    grant_id_str = request.path_params.get("grant_id", "")
    try:
        grant_id = uuid.UUID(grant_id_str)
    except ValueError:
        return JSONResponse({"error": "grant_id is not a valid UUID"}, status_code=422)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    from trimcp.a2a import revoke_grant
    from trimcp.auth import NamespaceContext

    try:
        ns_id = uuid.UUID(body["namespace_id"])
        agent_id_val = body.get("agent_id", "default")
        caller_ctx = NamespaceContext(namespace_id=ns_id, agent_id=agent_id_val)
    except (KeyError, ValueError) as exc:
        return JSONResponse(
            {"error": "Bad request parameters", "detail": str(exc)}, status_code=422
        )

    try:
        async with engine.pg_pool.acquire() as conn:
            revoked = await revoke_grant(conn, grant_id, caller_ctx)
    except Exception as exc:
        logger.exception("api_a2a_revoke_grant failed grant=%s", grant_id)
        return JSONResponse(
            {"error": "Revoke failed", "detail": str(exc)}, status_code=500
        )

    if not revoked:
        return JSONResponse(
            {
                "error": "Grant not found or not owned by this namespace",
                "grant_id": str(grant_id),
            },
            status_code=404,
        )

    return JSONResponse({"grant_id": str(grant_id), "revoked": True})


async def api_a2a_list_grants(request):
    """GET /api/a2a/grants?namespace_id=<uuid>[&include_inactive=true]

    List all A2A grants owned by the given namespace.
    Token hashes are never returned.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    ns_id_str = request.query_params.get("namespace_id", "")
    include_inactive = (
        request.query_params.get("include_inactive", "false").lower() == "true"
    )

    try:
        ns_id = uuid.UUID(ns_id_str)
    except ValueError:
        return JSONResponse(
            {"error": "namespace_id is required and must be a valid UUID"},
            status_code=422,
        )

    from trimcp.a2a import list_grants
    from trimcp.auth import NamespaceContext

    agent_id_val = request.query_params.get("agent_id", "default")
    caller_ctx = NamespaceContext(namespace_id=ns_id, agent_id=agent_id_val)

    try:
        async with engine.pg_pool.acquire() as conn:
            grants = await list_grants(
                conn, caller_ctx, include_inactive=include_inactive
            )
    except Exception as exc:
        logger.exception("api_a2a_list_grants failed ns=%s", ns_id)
        return JSONResponse(
            {"error": "List grants failed", "detail": str(exc)}, status_code=500
        )

    return JSONResponse({"grants": grants, "total": len(grants)})


# ---------------------------------------------------------------------------
# Admin dashboard data endpoints (Phase 3.1 UI feed)
# ---------------------------------------------------------------------------


def _parse_uuid_opt(raw: str | None) -> uuid.UUID | None:
    if raw is None or raw == "":
        return None
    return uuid.UUID(raw)


def _parse_int(raw: str | None, default: int, min_value: int, max_value: int) -> int:
    if raw is None or raw == "":
        return default
    value = int(raw)
    return max(min_value, min(max_value, value))


def _serialize_pg_row(row: Any) -> dict:
    d = row if isinstance(row, dict) else dict(row)
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            out[k] = v.astimezone(UTC).isoformat() if v else None
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


async def api_admin_events(request):
    """GET /api/admin/events

    Query params:
      namespace_id?, event_type?, agent_id?, from?, to?, page=1, limit=50
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        namespace_id = _parse_uuid_opt(request.query_params.get("namespace_id"))
        event_type = request.query_params.get("event_type")
        agent_id = request.query_params.get("agent_id")
        from_dt = parse_as_of(request.query_params.get("from"))
        to_dt = parse_as_of(request.query_params.get("to"))
        page = _parse_int(
            request.query_params.get("page"), default=1, min_value=1, max_value=10_000
        )
        limit = _parse_int(
            request.query_params.get("limit"), default=50, min_value=1, max_value=200
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    where = []
    args: list[object] = []
    i = 1
    if namespace_id:
        where.append(f"namespace_id = ${i}")
        args.append(namespace_id)
        i += 1
    if event_type:
        where.append(f"event_type = ${i}")
        args.append(event_type)
        i += 1
    if agent_id:
        where.append(f"agent_id = ${i}")
        args.append(agent_id)
        i += 1
    if from_dt:
        where.append(f"occurred_at >= ${i}")
        args.append(from_dt)
        i += 1
    if to_dt:
        where.append(f"occurred_at <= ${i}")
        args.append(to_dt)
        i += 1

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    offset = (page - 1) * limit
    count_sql = f"SELECT COUNT(*)::bigint AS total FROM event_log {where_sql}"
    items_sql = f"""
        SELECT id, namespace_id, agent_id, event_type, event_seq, occurred_at, parent_event_id
        FROM event_log
        {where_sql}
        ORDER BY occurred_at DESC
        LIMIT ${i} OFFSET ${i + 1}
    """

    try:
        async with engine.pg_pool.acquire() as conn:
            count_row = await conn.fetchrow(count_sql, *args)
            rows = await conn.fetch(items_sql, *args, limit, offset)
    except Exception as exc:
        logger.exception("api_admin_events failed")
        return JSONResponse(
            {"error": "Failed to query events", "detail": str(exc)}, status_code=500
        )

    items = [
        {
            "id": str(r["id"]),
            "namespace_id": str(r["namespace_id"]),
            "agent_id": r["agent_id"],
            "event_type": r["event_type"],
            "event_seq": r["event_seq"],
            "occurred_at": r["occurred_at"].astimezone(UTC).isoformat(),
            "parent_event_id": (
                str(r["parent_event_id"]) if r["parent_event_id"] else None
            ),
        }
        for r in rows
    ]
    return JSONResponse(
        {
            "items": items,
            "page": page,
            "limit": limit,
            "total": int(count_row["total"]) if count_row else 0,
        }
    )


async def api_admin_events_summary(request):
    """GET /api/admin/events/summary

    Query params:
      namespace_id?, from?, to?
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        namespace_id = _parse_uuid_opt(request.query_params.get("namespace_id"))
        from_dt = parse_as_of(request.query_params.get("from"))
        to_dt = parse_as_of(request.query_params.get("to"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    where = []
    args: list[object] = []
    i = 1
    if namespace_id:
        where.append(f"namespace_id = ${i}")
        args.append(namespace_id)
        i += 1
    if from_dt:
        where.append(f"occurred_at >= ${i}")
        args.append(from_dt)
        i += 1
    if to_dt:
        where.append(f"occurred_at <= ${i}")
        args.append(to_dt)
        i += 1
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    try:
        async with engine.pg_pool.acquire() as conn:
            total_row = await conn.fetchrow(
                f"SELECT COUNT(*)::bigint AS total, MAX(occurred_at) AS latest FROM event_log {where_sql}",
                *args,
            )
            by_type_rows = await conn.fetch(
                f"SELECT event_type, COUNT(*)::bigint AS c FROM event_log {where_sql} GROUP BY event_type ORDER BY c DESC",
                *args,
            )
            by_ns_rows = await conn.fetch(
                f"SELECT namespace_id, COUNT(*)::bigint AS c FROM event_log {where_sql} GROUP BY namespace_id ORDER BY c DESC LIMIT 20",
                *args,
            )
            replay_failed = await conn.fetchval(
                "SELECT COUNT(*)::bigint FROM replay_runs WHERE status = 'failed'"
            )
    except Exception as exc:
        logger.exception("api_admin_events_summary failed")
        return JSONResponse(
            {"error": "Failed to summarize events", "detail": str(exc)}, status_code=500
        )

    return JSONResponse(
        {
            "total_events": int(total_row["total"]) if total_row else 0,
            "latest_occurred_at": (
                total_row["latest"].astimezone(UTC).isoformat()
                if total_row and total_row["latest"] is not None
                else None
            ),
            "replay_failed_runs": int(replay_failed or 0),
            "by_event_type": {r["event_type"]: int(r["c"]) for r in by_type_rows},
            "by_namespace": {str(r["namespace_id"]): int(r["c"]) for r in by_ns_rows},
        }
    )


async def api_admin_verify_chain(request):
    """GET /api/admin/verify-chain/{namespace_id}

    Verify the Merkle hash chain for the given namespace.
    Recomputes chain_hash for every event in sequence order and
    reports the first break (if any).
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    raw_ns = request.path_params.get("namespace_id")
    try:
        namespace_id = uuid.UUID(raw_ns) if raw_ns else None
    except ValueError:
        return JSONResponse({"error": "Invalid namespace_id"}, status_code=422)

    if namespace_id is None:
        return JSONResponse({"error": "namespace_id required"}, status_code=422)

    try:
        async with engine.pg_pool.acquire() as conn:
            result = await verify_merkle_chain(conn, namespace_id=namespace_id)
    except Exception as exc:
        logger.exception("api_admin_verify_chain failed")
        return JSONResponse(
            {"error": "Failed to verify chain", "detail": str(exc)},
            status_code=500,
        )

    valid = bool(result.get("valid"))
    MERKLE_CHAIN_VALID.labels(namespace_id=str(namespace_id)).set(1 if valid else 0)

    return JSONResponse(
        {
            "valid": valid,
            "checked": result.get("checked", 0),
            "first_break": result.get("first_break"),
            "last_verified_seq": result.get("last_verified_seq", 0),
        }
    )


async def api_admin_a2a_grants(request):
    """GET /api/admin/a2a/grants

    Query params:
      owner_namespace_id?, status?, target_namespace_id?, page=1, limit=50
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        owner_namespace_id = _parse_uuid_opt(
            request.query_params.get("owner_namespace_id")
        )
        target_namespace_id = _parse_uuid_opt(
            request.query_params.get("target_namespace_id")
        )
        status = request.query_params.get("status")
        if status and status not in ("active", "revoked", "expired"):
            return JSONResponse(
                {"error": "status must be active|revoked|expired"}, status_code=422
            )
        page = _parse_int(
            request.query_params.get("page"), default=1, min_value=1, max_value=10_000
        )
        limit = _parse_int(
            request.query_params.get("limit"), default=50, min_value=1, max_value=200
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    where = []
    args: list[object] = []
    i = 1
    if owner_namespace_id:
        where.append(f"owner_namespace_id = ${i}")
        args.append(owner_namespace_id)
        i += 1
    if status:
        where.append(f"status = ${i}")
        args.append(status)
        i += 1
    if target_namespace_id:
        where.append(f"target_namespace_id = ${i}")
        args.append(target_namespace_id)
        i += 1
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    offset = (page - 1) * limit
    count_sql = f"SELECT COUNT(*)::bigint AS total FROM a2a_grants {where_sql}"
    items_sql = f"""
        SELECT id, owner_namespace_id, owner_agent_id, target_namespace_id,
               target_agent_id, scopes, status, expires_at, created_at
        FROM a2a_grants
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ${i} OFFSET ${i + 1}
    """

    try:
        async with engine.pg_pool.acquire() as conn:
            count_row = await conn.fetchrow(count_sql, *args)
            rows = await conn.fetch(items_sql, *args, limit, offset)
    except Exception as exc:
        logger.exception("api_admin_a2a_grants failed")
        return JSONResponse(
            {"error": "Failed to query A2A grants", "detail": str(exc)}, status_code=500
        )

    items = [
        {
            "grant_id": str(r["id"]),
            "owner_namespace_id": str(r["owner_namespace_id"]),
            "owner_agent_id": r["owner_agent_id"],
            "target_namespace_id": (
                str(r["target_namespace_id"]) if r["target_namespace_id"] else None
            ),
            "target_agent_id": r["target_agent_id"],
            "scopes": (
                json.loads(r["scopes"]) if isinstance(r["scopes"], str) else r["scopes"]
            ),
            "status": r["status"],
            "expires_at": r["expires_at"].astimezone(UTC).isoformat(),
            "created_at": r["created_at"].astimezone(UTC).isoformat(),
        }
        for r in rows
    ]
    return JSONResponse(
        {
            "items": items,
            "page": page,
            "limit": limit,
            "total": int(count_row["total"]) if count_row else 0,
        }
    )


async def api_admin_a2a_grants_summary(request):
    """GET /api/admin/a2a/grants/summary

    Query params:
      owner_namespace_id?
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        owner_namespace_id = _parse_uuid_opt(
            request.query_params.get("owner_namespace_id")
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    where_sql = "WHERE owner_namespace_id = $1" if owner_namespace_id else ""
    args: list[object] = [owner_namespace_id] if owner_namespace_id else []
    expiring_where = (
        "WHERE owner_namespace_id = $1 AND status = 'active' AND expires_at <= now() + interval '24 hours'"
        if owner_namespace_id
        else "WHERE status = 'active' AND expires_at <= now() + interval '24 hours'"
    )

    try:
        async with engine.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT status, COUNT(*)::bigint AS c FROM a2a_grants {where_sql} GROUP BY status",
                *args,
            )
            expiring_24h = await conn.fetchval(
                f"SELECT COUNT(*)::bigint FROM a2a_grants {expiring_where}",
                *args,
            )
    except Exception as exc:
        logger.exception("api_admin_a2a_grants_summary failed")
        return JSONResponse(
            {"error": "Failed to summarize A2A grants", "detail": str(exc)},
            status_code=500,
        )

    status_counts = {r["status"]: int(r["c"]) for r in rows}
    return JSONResponse(
        {
            "active": status_counts.get("active", 0),
            "revoked": status_counts.get("revoked", 0),
            "expired": status_counts.get("expired", 0),
            "expiring_24h": int(expiring_24h or 0),
        }
    )


async def api_admin_a2a_revoke_grant(request):
    """POST /api/admin/a2a/grants/{grant_id}/revoke

    Admin revoke endpoint. Requires owner namespace context in request body.
    """
    return await api_a2a_revoke_grant(request)


async def api_admin_quotas(request):
    """GET /api/admin/quotas

    Query params:
      namespace_id?, window=day
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        namespace_id = _parse_uuid_opt(request.query_params.get("namespace_id"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    window = request.query_params.get("window", "day")
    if window not in ("hour", "day", "month"):
        return JSONResponse({"error": "window must be hour|day|month"}, status_code=422)

    where_sql = "WHERE namespace_id = $1" if namespace_id else ""
    args: list[object] = [namespace_id] if namespace_id else []
    now = datetime.now(UTC)
    if window == "hour":
        cutoff = now.replace(minute=0, second=0, microsecond=0)
    elif window == "day":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        async with engine.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT namespace_id, agent_id, resource_type, limit_amount, used_amount, reset_at, updated_at
                FROM resource_quotas
                {where_sql}
                ORDER BY namespace_id, agent_id NULLS FIRST, resource_type
                """,
                *args,
            )
    except Exception as exc:
        logger.exception("api_admin_quotas failed")
        return JSONResponse(
            {"error": "Failed to query quotas", "detail": str(exc)}, status_code=500
        )

    tools = []
    total_used = 0
    total_limit = 0
    for r in rows:
        used = int(r["used_amount"])
        limit_amount = int(r["limit_amount"])
        total_used += used
        total_limit += limit_amount
        remaining = max(0, limit_amount - used)
        tools.append(
            {
                "namespace_id": str(r["namespace_id"]),
                "agent_id": r["agent_id"],
                "resource_type": r["resource_type"],
                "used": used,
                "limit": limit_amount,
                "remaining": remaining,
                "reset_at": (
                    r["reset_at"].astimezone(UTC).isoformat() if r["reset_at"] else None
                ),
                "updated_at": (
                    r["updated_at"].astimezone(UTC).isoformat()
                    if r["updated_at"]
                    else None
                ),
                "window_start": cutoff.isoformat(),
            }
        )

    return JSONResponse(
        {
            "tools": tools,
            "totals": {
                "used": total_used,
                "limit": total_limit,
                "utilization_pct": (
                    round((total_used / total_limit * 100.0), 2)
                    if total_limit > 0
                    else 0.0
                ),
            },
        }
    )


async def api_admin_quotas_summary(request):
    """GET /api/admin/quotas/summary

    Query params:
      namespace_id?
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        namespace_id = _parse_uuid_opt(request.query_params.get("namespace_id"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    where_sql = "WHERE namespace_id = $1" if namespace_id else ""
    args: list[object] = [namespace_id] if namespace_id else []

    try:
        async with engine.pg_pool.acquire() as conn:
            top_rows = await conn.fetch(
                f"""
                SELECT namespace_id, resource_type, used_amount, limit_amount
                FROM resource_quotas
                {where_sql}
                ORDER BY (CASE WHEN limit_amount = 0 THEN 0 ELSE used_amount::float / limit_amount END) DESC
                LIMIT 20
                """,
                *args,
            )
    except Exception as exc:
        logger.exception("api_admin_quotas_summary failed")
        return JSONResponse(
            {"error": "Failed to summarize quotas", "detail": str(exc)}, status_code=500
        )

    near_limit = []
    for r in top_rows:
        limit_amount = int(r["limit_amount"])
        used = int(r["used_amount"])
        utilization = (used / limit_amount * 100.0) if limit_amount > 0 else 0.0
        if utilization >= 80.0:
            near_limit.append(
                {
                    "namespace_id": str(r["namespace_id"]),
                    "resource_type": r["resource_type"],
                    "used": used,
                    "limit": limit_amount,
                    "utilization_pct": round(utilization, 2),
                }
            )

    return JSONResponse({"near_limit": near_limit, "total": len(near_limit)})


async def api_admin_graph_explore(request):
    """POST /api/admin/graph/explore

    Body (JSON):
      namespace_id (required), query (required), max_depth?=2, anchor_top_k?=3, as_of?
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Request body must be valid JSON"}, status_code=400
        )

    missing = [f for f in ("namespace_id", "query") if not body.get(f)]
    if missing:
        return JSONResponse(
            {"error": f"Missing required fields: {', '.join(missing)}"}, status_code=422
        )

    try:
        namespace_id = str(uuid.UUID(body["namespace_id"]))
        as_of_dt = parse_as_of(body.get("as_of"))
        max_depth = int(body.get("max_depth", 2))
        anchor_top_k = int(body.get("anchor_top_k", 3))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    try:
        result = await engine.graph_search(
            query=body["query"],
            namespace_id=namespace_id,
            max_depth=max_depth,
            top_k_anchors=anchor_top_k,
            as_of=as_of_dt,
        )
    except Exception as exc:
        logger.exception("api_admin_graph_explore failed ns=%s", namespace_id)
        return JSONResponse(
            {"error": "Graph exploration failed", "detail": str(exc)}, status_code=500
        )

    return JSONResponse(result)


async def api_admin_embedding_models(request):
    """GET /api/admin/embedding-models — list embedding model registry rows."""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        async with engine.pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, dimension, status, created_at, retired_at
                FROM embedding_models
                ORDER BY created_at DESC
                """)
    except Exception as exc:
        logger.exception("api_admin_embedding_models failed")
        return JSONResponse(
            {"error": "Failed to list models", "detail": str(exc)}, status_code=500
        )
    return JSONResponse({"models": [_serialize_pg_row(r) for r in rows]})


async def api_admin_embedding_migration_start(request):
    """POST /api/admin/embedding-migrations/start — body { \"target_model_id\": uuid }."""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Request body must be valid JSON"}, status_code=400
        )
    tid = body.get("target_model_id")
    if not tid:
        return JSONResponse({"error": "target_model_id is required"}, status_code=422)
    try:
        out = await engine.start_migration(str(tid))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    except Exception as exc:
        logger.exception("start_migration failed")
        return JSONResponse(
            {"error": "start_migration failed", "detail": str(exc)}, status_code=500
        )
    return JSONResponse(out)


async def api_admin_embedding_migration_status(request):
    """GET /api/admin/embedding-migrations/{migration_id}/status"""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    mid = request.path_params.get("migration_id")
    try:
        out = await engine.migration_status(mid)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        logger.exception("migration_status failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(_serialize_pg_row(out))


async def api_admin_embedding_migration_validate(request):
    """POST /api/admin/embedding-migrations/{migration_id}/validate"""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    mid = request.path_params.get("migration_id")
    try:
        out = await engine.validate_migration(mid)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("validate_migration failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(out)


async def api_admin_embedding_migration_commit(request):
    """POST /api/admin/embedding-migrations/{migration_id}/commit"""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    mid = request.path_params.get("migration_id")
    try:
        out = await engine.commit_migration(mid)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("commit_migration failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(out)


async def api_admin_embedding_migration_abort(request):
    """POST /api/admin/embedding-migrations/{migration_id}/abort"""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    mid = request.path_params.get("migration_id")
    try:
        out = await engine.abort_migration(mid)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        logger.exception("abort_migration failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(out)


async def api_admin_schema(request):
    """GET /api/admin/schema — JSON Schema for all public TriMCP Pydantic models."""
    from pydantic.json_schema import models_json_schema

    from trimcp.models import (
        ForgetMemoryRequest,
        GetRecentContextRequest,
        GraphSearchRequest,
        IndexCodeFileRequest,
        KGEdge,
        KGNode,
        ManageQuotasRequest,
        MediaPayload,
        MemoryRecord,
        NamespaceCognitiveConfig,
        NamespaceCreate,
        NamespaceMetadata,
        NamespaceMetadataPatch,
        NamespacePIIConfig,
        NamespaceRecord,
        SemanticSearchRequest,
        SemanticSearchResult,
        StoreMemoryRequest,
        UnredactMemoryRequest,
    )

    _models = [
        NamespaceCreate, NamespaceRecord, NamespaceMetadata, NamespaceMetadataPatch,
        NamespaceCognitiveConfig, NamespacePIIConfig, ManageQuotasRequest,
        StoreMemoryRequest, MemoryRecord, ForgetMemoryRequest, UnredactMemoryRequest,
        GetRecentContextRequest, SemanticSearchRequest, SemanticSearchResult,
        GraphSearchRequest, IndexCodeFileRequest, KGNode, KGEdge, MediaPayload,
    ]
    _, schema = models_json_schema(
        [(m, "validation") for m in _models],
        title="TriMCP API Schema",
    )
    return JSONResponse(schema)


async def api_admin_dlq_list(request):
    """GET /api/admin/dlq

    Query params: task_name?, status?, limit=50, offset=0
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    from trimcp.dead_letter_queue import list_dead_letters

    task_name = request.query_params.get("task_name") or None
    status = request.query_params.get("status") or None
    try:
        limit = int(request.query_params.get("limit", "50"))
        offset = int(request.query_params.get("offset", "0"))
    except ValueError:
        return JSONResponse({"error": "limit and offset must be integers"}, status_code=422)

    try:
        entries = await list_dead_letters(
            engine.pg_pool, task_name=task_name, status=status, limit=limit, offset=offset
        )
    except Exception as exc:
        logger.exception("api_admin_dlq_list failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"entries": entries, "count": len(entries)})


async def api_admin_dlq_replay(request):
    """POST /api/admin/dlq/{dlq_id}/replay"""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    from trimcp.dead_letter_queue import replay_dead_letter

    dlq_id = request.path_params["dlq_id"]
    try:
        result = await replay_dead_letter(engine.pg_pool, dlq_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        logger.exception("api_admin_dlq_replay failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(result)


async def api_admin_dlq_purge(request):
    """POST /api/admin/dlq/{dlq_id}/purge"""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    from trimcp.dead_letter_queue import purge_dead_letter

    dlq_id = request.path_params["dlq_id"]
    try:
        await purge_dead_letter(engine.pg_pool, dlq_id)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        logger.exception("api_admin_dlq_purge failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"status": "ok", "id": dlq_id})


app = Starlette(
    debug=False,
    lifespan=lifespan,
    middleware=[
        # OTel middleware must come first so trace context is established
        # before any auth or handler logic runs.
        Middleware(OpenTelemetryTraceMiddleware),
        Middleware(
            MTLSAuthMiddleware,
            protected_prefix="/api/",
            enabled=cfg.TRIMCP_ADMIN_MTLS_ENABLED,
            strict=cfg.TRIMCP_ADMIN_MTLS_STRICT,
            trusted_proxy_hops=cfg.TRIMCP_ADMIN_MTLS_TRUSTED_PROXY_HOP,
            allowed_sans=cfg.TRIMCP_ADMIN_MTLS_ALLOWED_SANS,
            allowed_fingerprints=cfg.TRIMCP_ADMIN_MTLS_ALLOWED_FINGERPRINTS,
        ),
        Middleware(
            BasicAuthMiddleware,
            protected_prefix="/",
            excluded_prefixes=("/api/",),
            username=cfg.TRIMCP_ADMIN_USERNAME,
            password=cfg.TRIMCP_ADMIN_PASSWORD,
            realm="TriMCP Admin",
        ),
        Middleware(
            HMACAuthMiddleware,
            protected_prefix="/api/",
            api_key=cfg.TRIMCP_API_KEY,
            nonce_store=_hmac_nonce_store,
        ),
    ],
    routes=[
        Route("/", endpoint=serve_index),
        Route("/api/health", endpoint=get_health, methods=["GET"]),
        Route("/api/health/v1", endpoint=get_health_v1, methods=["GET"]),
        Route("/api/gc/trigger", endpoint=trigger_gc, methods=["POST"]),
        Route("/api/search", endpoint=api_search, methods=["POST"]),
        # Phase 2.3 — Replay
        Route("/api/replay/observe", endpoint=api_replay_observe, methods=["POST"]),
        Route("/api/replay/fork", endpoint=api_replay_fork, methods=["POST"]),
        Route(
            "/api/replay/status/{run_id}", endpoint=api_replay_status, methods=["GET"]
        ),
        Route(
            "/api/replay/provenance/{memory_id}",
            endpoint=api_event_provenance,
            methods=["GET"],
        ),
        # Phase 3 — Snapshot export (streaming NDJSON)
        Route("/api/snapshot/export", endpoint=api_snapshot_export, methods=["POST"]),
        # Phase 3.1 — A2A Grant Management
        Route(
            "/api/a2a/grants/create", endpoint=api_a2a_create_grant, methods=["POST"]
        ),
        Route(
            "/api/a2a/grants/{grant_id}/revoke",
            endpoint=api_a2a_revoke_grant,
            methods=["POST"],
        ),
        Route("/api/a2a/grants", endpoint=api_a2a_list_grants, methods=["GET"]),
        # Admin UI feed endpoints
        Route("/api/admin/events", endpoint=api_admin_events, methods=["GET"]),
        Route(
            "/api/admin/events/summary",
            endpoint=api_admin_events_summary,
            methods=["GET"],
        ),
        Route("/api/admin/a2a/grants", endpoint=api_admin_a2a_grants, methods=["GET"]),
        Route(
            "/api/admin/a2a/grants/summary",
            endpoint=api_admin_a2a_grants_summary,
            methods=["GET"],
        ),
        Route(
            "/api/admin/a2a/grants/{grant_id}/revoke",
            endpoint=api_admin_a2a_revoke_grant,
            methods=["POST"],
        ),
        Route("/api/admin/quotas", endpoint=api_admin_quotas, methods=["GET"]),
        Route(
            "/api/admin/quotas/summary",
            endpoint=api_admin_quotas_summary,
            methods=["GET"],
        ),
        Route(
            "/api/admin/graph/explore",
            endpoint=api_admin_graph_explore,
            methods=["POST"],
        ),
        Route(
            "/api/admin/graph/provenance/{memory_id}",
            endpoint=api_event_provenance,
            methods=["GET"],
        ),
        Route(
            "/api/admin/verify-chain/{namespace_id}",
            endpoint=api_admin_verify_chain,
            methods=["GET"],
        ),
        Route(
            "/api/admin/embedding-models",
            endpoint=api_admin_embedding_models,
            methods=["GET"],
        ),
        Route(
            "/api/admin/embedding-migrations/start",
            endpoint=api_admin_embedding_migration_start,
            methods=["POST"],
        ),
        Route(
            "/api/admin/embedding-migrations/{migration_id}/status",
            endpoint=api_admin_embedding_migration_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/embedding-migrations/{migration_id}/validate",
            endpoint=api_admin_embedding_migration_validate,
            methods=["POST"],
        ),
        Route(
            "/api/admin/embedding-migrations/{migration_id}/commit",
            endpoint=api_admin_embedding_migration_commit,
            methods=["POST"],
        ),
        Route(
            "/api/admin/embedding-migrations/{migration_id}/abort",
            endpoint=api_admin_embedding_migration_abort,
            methods=["POST"],
        ),
        # Schema endpoint
        Route("/api/admin/schema", endpoint=api_admin_schema, methods=["GET"]),
        # DLQ management
        Route("/api/admin/dlq", endpoint=api_admin_dlq_list, methods=["GET"]),
        Route(
            "/api/admin/dlq/{dlq_id}/replay",
            endpoint=api_admin_dlq_replay,
            methods=["POST"],
        ),
        Route(
            "/api/admin/dlq/{dlq_id}/purge",
            endpoint=api_admin_dlq_purge,
            methods=["POST"],
        ),
    ],
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
