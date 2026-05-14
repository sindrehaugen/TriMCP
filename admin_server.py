from __future__ import annotations

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
    set_namespace_context,
)
from trimcp.background_task_manager import create_tracked_task
from trimcp.config import cfg
from trimcp.event_log import verify_merkle_chain
from trimcp.mtls import MTLSAuthMiddleware
from trimcp.notifications import dispatcher
from trimcp.observability import MERKLE_CHAIN_VALID, OpenTelemetryTraceMiddleware
from trimcp.orchestrator import TriStackEngine
from trimcp.admin_routes import (
    ADMIN_MAX_LIST_LIMIT,
    ADMIN_MAX_ROWS_SKIP,
    ADMIN_NAMESPACES_DEFAULT_LIMIT,
    clamp_bounded_int,
    fetch_event_llm_payload_uri,
    fetch_fleet_overview_page,
    fetch_namespace_bridge_subscriptions,
    fetch_pg_rls_snapshot,
    fetch_recent_open_contradictions,
    fetch_salience_map_points,
    offset_from_page_limit,
    parse_optional_bigint_bounds,
    parse_optional_half_life_days,
    parse_optional_uuid,
    parse_page_limit_common,
    parse_salience_top_k,
    sanitize_event_type_filter,
    sanitize_optional_agent_filter,
    sanitize_resource_type_filter,
    sanitize_slug_prefix_filter,
    sanitize_task_name_filter,
    validate_dlq_status,
)
from trimcp.signing import admin_signing_keys_status
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

        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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
            engine.pg_pool,
            "api_semantic_search",
            body,
            redis_client=engine.redis_client,
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


async def serve_styles(request):
    """GET /styles.css — serve the admin dashboard stylesheet."""
    styles_path = os.path.join(os.path.dirname(__file__), "admin", "styles.css")
    if os.path.exists(styles_path):
        return FileResponse(styles_path, media_type="text/css")
    return HTMLResponse("styles.css not found", status_code=404)


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
        async with engine.pg_pool.acquire(timeout=10.0) as pre_conn:
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

        await create_tracked_task(_run_fork(), name=f"fork-{fork_run_id}")
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
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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
      namespace_id?, event_type?, agent_id?, from?, to?,
      event_seq_gte?, event_seq_lte?,
      include_details=1 (optional: params, result_summary, llm_payload_uri),
      page=1, limit=50
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        qp = request.query_params
        namespace_id = parse_optional_uuid(qp.get("namespace_id"))
        event_type_raw, et_err = sanitize_event_type_filter(qp.get("event_type"))
        if et_err:
            return JSONResponse({"error": et_err}, status_code=422)
        agent_id = qp.get("agent_id")
        from_dt = parse_as_of(qp.get("from"))
        to_dt = parse_as_of(qp.get("to"))
        seq_gte, sg_err = parse_optional_bigint_bounds(
            qp.get("event_seq_gte"), label="event_seq_gte"
        )
        if sg_err:
            return JSONResponse({"error": sg_err}, status_code=422)
        seq_lte, sl_err = parse_optional_bigint_bounds(
            qp.get("event_seq_lte"), label="event_seq_lte"
        )
        if sl_err:
            return JSONResponse({"error": sl_err}, status_code=422)
        page, limit = parse_page_limit_common(qp)
        offset = offset_from_page_limit(page, limit)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    event_type = event_type_raw

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
    if seq_gte is not None:
        where.append(f"event_seq >= ${i}")
        args.append(seq_gte)
        i += 1
    if seq_lte is not None:
        where.append(f"event_seq <= ${i}")
        args.append(seq_lte)
        i += 1

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    count_sql = f"SELECT COUNT(*)::bigint AS total FROM event_log {where_sql}"
    include_details = (qp.get("include_details") or "").lower() in (
        "1",
        "true",
        "yes",
    )
    extra_cols = ""
    if include_details:
        extra_cols = ", params, result_summary, llm_payload_uri"

    items_sql = f"""
        SELECT id, namespace_id, agent_id, event_type, event_seq, occurred_at, parent_event_id
        {extra_cols}
        FROM event_log
        {where_sql}
        ORDER BY occurred_at DESC
        LIMIT ${i} OFFSET ${i + 1}
    """

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            count_row = await conn.fetchrow(count_sql, *args)
            rows = await conn.fetch(items_sql, *args, limit, offset)
    except Exception as exc:
        logger.exception("api_admin_events failed")
        return JSONResponse(
            {"error": "Failed to query events", "detail": str(exc)}, status_code=500
        )

    def _jsonish(val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return val
        return val

    items = []
    for r in rows:
        row_dict: dict[str, Any] = {
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
        if include_details:
            row_dict["params"] = _jsonish(r["params"])
            row_dict["result_summary"] = _jsonish(r["result_summary"])
            uri = r["llm_payload_uri"]
            row_dict["llm_payload_uri"] = str(uri) if uri else None
        items.append(row_dict)
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
        namespace_id = parse_optional_uuid(request.query_params.get("namespace_id"))
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
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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
        owner_namespace_id = parse_optional_uuid(
            request.query_params.get("owner_namespace_id")
        )
        target_namespace_id = parse_optional_uuid(
            request.query_params.get("target_namespace_id")
        )
        status = request.query_params.get("status")
        if status and status not in ("active", "revoked", "expired"):
            return JSONResponse(
                {"error": "status must be active|revoked|expired"}, status_code=422
            )
        qp = request.query_params
        page, limit = parse_page_limit_common(qp)
        offset = offset_from_page_limit(page, limit)
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
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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
        owner_namespace_id = parse_optional_uuid(
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
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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
      namespace_id?, resource_type?, window=day,
      page=1, limit=50
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    qp = request.query_params
    try:
        namespace_id = parse_optional_uuid(qp.get("namespace_id"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    res_type_raw, rt_err = sanitize_resource_type_filter(qp.get("resource_type"))
    if rt_err:
        return JSONResponse({"error": rt_err}, status_code=422)

    try:
        page, limit = parse_page_limit_common(qp)
        offset = offset_from_page_limit(page, limit)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    window = qp.get("window", "day")
    if window not in ("hour", "day", "month"):
        return JSONResponse({"error": "window must be hour|day|month"}, status_code=422)

    where_fragments: list[str] = []
    args: list[object] = []
    idx = 1
    if namespace_id:
        where_fragments.append(f"namespace_id = ${idx}")
        args.append(namespace_id)
        idx += 1
    if res_type_raw:
        where_fragments.append(f"resource_type = ${idx}")
        args.append(res_type_raw)
        idx += 1
    where_sql = f"WHERE {' AND '.join(where_fragments)}" if where_fragments else ""

    now = datetime.now(UTC)
    if window == "hour":
        cutoff = now.replace(minute=0, second=0, microsecond=0)
    elif window == "day":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count_sql = f"SELECT COUNT(*)::bigint AS total FROM resource_quotas {where_sql}"
    sums_sql = f"""
        SELECT COALESCE(SUM(used_amount), 0)::bigint AS used_sum,
               COALESCE(SUM(limit_amount), 0)::bigint AS limit_sum
        FROM resource_quotas
        {where_sql}
    """
    items_sql = f"""
        SELECT namespace_id, agent_id, resource_type, limit_amount, used_amount, reset_at, updated_at
        FROM resource_quotas
        {where_sql}
        ORDER BY namespace_id, agent_id NULLS FIRST, resource_type
        LIMIT ${idx} OFFSET ${idx + 1}
    """

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            count_row = await conn.fetchrow(count_sql, *args)
            sums_row = await conn.fetchrow(sums_sql, *args)
            rows = await conn.fetch(items_sql, *args, limit, offset)
    except Exception as exc:
        logger.exception("api_admin_quotas failed")
        return JSONResponse(
            {"error": "Failed to query quotas", "detail": str(exc)}, status_code=500
        )

    total_used = int(sums_row["used_sum"]) if sums_row else 0
    total_limit = int(sums_row["limit_sum"]) if sums_row else 0

    tools = []
    for r in rows:
        used = int(r["used_amount"])
        limit_amount = int(r["limit_amount"])
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
            "page": page,
            "limit": limit,
            "total": int(count_row["total"]) if count_row else 0,
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
        namespace_id = parse_optional_uuid(request.query_params.get("namespace_id"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    where_sql = "WHERE namespace_id = $1" if namespace_id else ""
    args: list[object] = [namespace_id] if namespace_id else []

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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

    from trimcp.models import GraphSearchRequest

    try:
        payload = GraphSearchRequest(
            namespace_id=namespace_id,
            query=body["query"],
            max_depth=max_depth,
            as_of=as_of_dt,
        )
        result = await engine.graph_search(payload)
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
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
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

    Query params: task_name?, status?, page?, limit?,
    or legacy: limit=50, offset=0 (used when ``page`` is omitted).
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    from trimcp.dead_letter_queue import count_dead_letters, list_dead_letters

    qp = request.query_params
    task_name, tn_err = sanitize_task_name_filter(qp.get("task_name"))
    if tn_err:
        return JSONResponse({"error": tn_err}, status_code=422)
    dlq_status, st_err = validate_dlq_status(qp.get("status"))
    if st_err:
        return JSONResponse({"error": st_err}, status_code=422)

    page: int
    offset: int
    try:
        if qp.get("page") not in (None, ""):
            page, limit = parse_page_limit_common(qp)
            offset = offset_from_page_limit(page, limit)
        else:
            limit = clamp_bounded_int(
                qp.get("limit"),
                default=50,
                min_value=1,
                max_value=ADMIN_MAX_LIST_LIMIT,
            )
            offset = clamp_bounded_int(
                qp.get("offset"),
                default=0,
                min_value=0,
                max_value=ADMIN_MAX_ROWS_SKIP,
            )
            page = (offset // limit) + 1 if limit > 0 else 1
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    try:
        total = await count_dead_letters(
            engine.pg_pool,
            task_name=task_name,
            status=dlq_status,
        )
        entries = await list_dead_letters(
            engine.pg_pool,
            task_name=task_name,
            status=dlq_status,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.exception("api_admin_dlq_list failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(
        {
            "entries": entries,
            "count": len(entries),
            "total": total,
            "page": page,
            "limit": limit,
            "offset": offset,
        }
    )


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


async def api_admin_db_postgres_status(request):
    """GET /api/admin/db/postgres/status"""
    if not engine or not engine.pg_pool:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        async with engine.pg_pool.acquire() as conn:
            # Query sizes and estimate row counts for core tables
            tables_query = """
                SELECT 
                    c.relname AS name,
                    c.reltuples::bigint AS row_count_estimate,
                    pg_total_relation_size(c.oid) AS table_size_bytes,
                    pg_relation_size(c.oid) AS relation_size_bytes
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' 
                  AND c.relkind = 'r'
                  AND c.relname IN ('memories', 'kg_nodes', 'kg_edges', 'event_log', 'outbox_events')
            """
            rows = await conn.fetch(tables_query)
            tables = [dict(r) for r in rows]

            # Estimate partition runway months
            partitions_query = """
                SELECT count(*) AS cnt
                FROM pg_inherits i
                JOIN pg_class c ON c.oid = i.inhrelid
                WHERE i.inhparent = 'event_log'::regclass
                  AND c.relname LIKE 'event_log_%'
                  AND c.relname >= 'event_log_' || to_char(now(), 'YYYY_MM')
            """
            part_row = await conn.fetchrow(partitions_query)
            runway_months = part_row["cnt"] if part_row else 0

        return JSONResponse({
            "tables": tables,
            "partition_status": {
                "runway_months": runway_months
            }
        })
    except Exception as exc:
        logger.exception("api_admin_db_postgres_status failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_db_mongo_status(request):
    """GET /api/admin/db/mongo/status"""
    if not engine or not engine.mongo_client:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        db = engine.mongo_client.get_database("memory_archive")
        collections_list = await db.list_collection_names()
        collections = []
        for col_name in collections_list:
            if col_name.startswith("system."):
                continue
            stats = await db.command("collStats", col_name)
            collections.append({
                "name": col_name,
                "document_count": stats.get("count", 0),
                "storage_size_bytes": stats.get("storageSize", 0),
                "indexes": list(stats.get("indexSizes", {}).keys())
            })
        return JSONResponse({"collections": collections})
    except Exception as exc:
        logger.exception("api_admin_db_mongo_status failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_db_redis_status(request):
    """GET /api/admin/db/redis/status"""
    if not engine or not engine.redis_client:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        info = await engine.redis_client.info()
        db_stats = info.get("db0", {})
        keys_count = db_stats.get("keys", 0)

        keys_cache_count = 0
        keys_lock_count = 0
        try:
            # Safe non-blocking partial keyspace scan
            cursor, keys = await engine.redis_client.scan(cursor=0, match="trimcp:*", count=500)
            for k in keys:
                k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                if ":lock:" in k_str:
                    keys_lock_count += 1
                else:
                    keys_cache_count += 1
        except Exception:
            pass

        return JSONResponse({
            "info": {
                "used_memory_human": info.get("used_memory_human", "0B"),
                "connected_clients": info.get("connected_clients", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0)
            },
            "keyspaces": [
                { "pattern": "trimcp:cache:*", "count": keys_cache_count },
                { "pattern": "trimcp:lock:*", "count": keys_lock_count },
                { "pattern": "all_keys", "count": keys_count }
            ]
        })
    except Exception as exc:
        logger.exception("api_admin_db_redis_status failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_db_minio_status(request):
    """GET /api/admin/db/minio/status"""
    if not engine or not engine.minio_client:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        import asyncio
        def _get_buckets():
            bucket_list = engine.minio_client.list_buckets()
            res = []
            for b in bucket_list:
                obj_count = 0
                total_size = 0
                try:
                    objects = engine.minio_client.list_objects(b.name, recursive=True)
                    for i, o in enumerate(objects):
                        if i >= 100:  # Limit safety scan depth
                            break
                        obj_count += 1
                        total_size += o.size
                except Exception:
                    pass
                res.append({
                    "name": b.name,
                    "object_count": obj_count,
                    "total_size_bytes": total_size
                })
            return res

        buckets = await asyncio.to_thread(_get_buckets)
        return JSONResponse({"buckets": buckets})
    except Exception as exc:
        logger.exception("api_admin_db_minio_status failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_connectors_status(request):
    """GET /api/admin/connectors/status"""
    try:
        bridges = {
            "google_drive": {
                "enabled": bool(cfg.GDRIVE_OAUTH_CLIENT_ID),
                "has_client_id": bool(cfg.GDRIVE_OAUTH_CLIENT_ID),
                "token_status": "active" if cfg.GDRIVE_BRIDGE_TOKEN else "missing",
                "sync_interval_mins": cfg.BRIDGE_CRON_INTERVAL_MINUTES
            },
            "dropbox": {
                "enabled": bool(cfg.DROPBOX_OAUTH_CLIENT_ID),
                "has_client_id": bool(cfg.DROPBOX_OAUTH_CLIENT_ID),
                "token_status": "active" if cfg.DROPBOX_BRIDGE_TOKEN else "missing",
                "sync_interval_mins": cfg.BRIDGE_CRON_INTERVAL_MINUTES
            },
            "onedrive": {
                "enabled": bool(cfg.AZURE_CLIENT_ID),
                "has_client_id": bool(cfg.AZURE_CLIENT_ID),
                "token_status": "active" if cfg.GRAPH_BRIDGE_TOKEN else "missing",
                "sync_interval_mins": cfg.BRIDGE_CRON_INTERVAL_MINUTES
            }
        }

        cognitive_online = False
        if cfg.TRIMCP_COGNITIVE_BASE_URL:
            import httpx
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    resp = await client.get(f"{cfg.TRIMCP_COGNITIVE_BASE_URL}/health")
                    cognitive_online = (resp.status_code == 200)
            except Exception:
                cognitive_online = False

        external_apis = {
            "openai_compatible_cognitive": {
                "endpoint": cfg.TRIMCP_COGNITIVE_BASE_URL or "not_configured",
                "configured": bool(cfg.TRIMCP_COGNITIVE_BASE_URL),
                "online": cognitive_online
            },
            "nli_deberta": {
                "model_id": cfg.NLI_MODEL_ID or "not_configured",
                "loaded": bool(cfg.NLI_MODEL_ID)
            }
        }

        return JSONResponse({
            "bridges": bridges,
            "external_apis": external_apis
        })
    except Exception as exc:
        logger.exception("api_admin_connectors_status failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


def update_dotenv(updates: dict) -> None:
    """Updates key-value pairs in the .env file, creating/replacing lines as needed."""
    dotenv_path = ".env"
    import os
    if not os.path.exists(dotenv_path):
        with open(dotenv_path, "w", encoding="utf-8") as f:
            pass

    with open(dotenv_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    keys_updated = set()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            parts = stripped.split("=", 1)
            k = parts[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                keys_updated.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in keys_updated:
            new_lines.append(f"{k}={v}\n")

    with open(dotenv_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


async def api_admin_connectors_save(request):
    """POST /api/admin/connectors/save"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)

    updates = {}

    def reconstruct_secret(new_val: str, old_val: str) -> str:
        if new_val == "••••••••":
            return old_val
        return new_val

    # Google Drive
    gd = body.get("google_drive", {})
    if "client_id" in gd:
        cfg.GDRIVE_OAUTH_CLIENT_ID = gd["client_id"]
        updates["GDRIVE_OAUTH_CLIENT_ID"] = gd["client_id"]
    if "client_secret" in gd:
        val = reconstruct_secret(gd["client_secret"], cfg.GDRIVE_OAUTH_CLIENT_SECRET)
        cfg.GDRIVE_OAUTH_CLIENT_SECRET = val
        updates["GDRIVE_OAUTH_CLIENT_SECRET"] = val
    if "token" in gd:
        val = reconstruct_secret(gd["token"], cfg.GDRIVE_BRIDGE_TOKEN)
        cfg.GDRIVE_BRIDGE_TOKEN = val
        updates["GDRIVE_BRIDGE_TOKEN"] = val

    # Dropbox
    dbx = body.get("dropbox", {})
    if "client_id" in dbx:
        cfg.DROPBOX_OAUTH_CLIENT_ID = dbx["client_id"]
        updates["DROPBOX_OAUTH_CLIENT_ID"] = dbx["client_id"]
    if "token" in dbx:
        val = reconstruct_secret(dbx["token"], cfg.DROPBOX_BRIDGE_TOKEN)
        cfg.DROPBOX_BRIDGE_TOKEN = val
        updates["DROPBOX_BRIDGE_TOKEN"] = val

    # OneDrive
    od = body.get("onedrive", {})
    if "client_id" in od:
        cfg.AZURE_CLIENT_ID = od["client_id"]
        updates["AZURE_CLIENT_ID"] = od["client_id"]
    if "client_secret" in od:
        val = reconstruct_secret(od["client_secret"], cfg.AZURE_CLIENT_SECRET)
        cfg.AZURE_CLIENT_SECRET = val
        updates["AZURE_CLIENT_SECRET"] = val
    if "tenant_id" in od:
        cfg.AZURE_TENANT_ID = od["tenant_id"]
        updates["AZURE_TENANT_ID"] = od["tenant_id"]
    if "token" in od:
        val = reconstruct_secret(od["token"], cfg.GRAPH_BRIDGE_TOKEN)
        cfg.GRAPH_BRIDGE_TOKEN = val
        updates["GRAPH_BRIDGE_TOKEN"] = val

    # Common
    common = body.get("common", {})
    if "cron_interval_mins" in common:
        try:
            val = int(common["cron_interval_mins"])
            cfg.BRIDGE_CRON_INTERVAL_MINUTES = val
            updates["BRIDGE_CRON_INTERVAL_MINUTES"] = str(val)
        except ValueError:
            pass

    try:
        update_dotenv(updates)
    except Exception as exc:
        logger.exception("Failed to write connectors configuration to .env")
        return JSONResponse({"error": "Failed to persist configurations to .env", "detail": str(exc)}, status_code=500)

    return JSONResponse({"status": "success", "message": "Connector configurations successfully updated."})


def mask_uri_password(uri: str) -> str:
    """Mask the password field of a standard connection URI with dots."""
    if not uri:
        return ""
    from urllib.parse import urlparse, urlunparse
    try:
        parsed = urlparse(uri)
        if parsed.password:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            if parsed.username:
                netloc = f"{parsed.username}:••••••••@{netloc}"
            else:
                netloc = f":••••••••@{netloc}"
            return urlunparse(parsed._replace(netloc=netloc))
        return uri
    except Exception:
        return uri


async def api_admin_datastores_status(request):
    """GET /api/admin/datastores/status
    Retrieves masked connection credentials and pools config for active datastores.
    """
    try:
        postgres = {
            "pg_dsn": mask_uri_password(cfg.PG_DSN),
            "db_read_url": mask_uri_password(cfg.DB_READ_URL),
            "db_write_url": mask_uri_password(cfg.DB_WRITE_URL),
            "pg_min_pool": cfg.PG_MIN_POOL,
            "pg_max_pool": cfg.PG_MAX_POOL,
        }
        mongodb = {
            "mongo_uri": mask_uri_password(cfg.MONGO_URI),
        }
        redis = {
            "redis_url": mask_uri_password(cfg.REDIS_URL),
            "redis_ttl": cfg.REDIS_TTL,
            "redis_max_connections": cfg.REDIS_MAX_CONNECTIONS,
        }
        minio = {
            "minio_endpoint": cfg.MINIO_ENDPOINT,
            "minio_access_key": cfg.MINIO_ACCESS_KEY,
            "has_secret_key": bool(cfg.MINIO_SECRET_KEY),
            "minio_secure": cfg.MINIO_SECURE,
        }
        return JSONResponse({
            "postgres": postgres,
            "mongodb": mongodb,
            "redis": redis,
            "minio": minio,
        })
    except Exception as exc:
        logger.exception("api_admin_datastores_status failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_datastores_save(request):
    """POST /api/admin/datastores/save
    Saves edited connection params back to disk (.env) and applies them dynamically to process config,
    preventing any masked fields from overwriting active production credentials.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)

    from urllib.parse import urlparse, urlunparse

    def reconstruct_uri(new_uri: str, old_uri: str) -> str:
        if not new_uri:
            return ""
        if "••••••••" not in new_uri:
            return new_uri
        try:
            old_parsed = urlparse(old_uri)
            old_password = old_parsed.password or ""
            new_parsed = urlparse(new_uri)
            netloc = new_parsed.hostname or ""
            if new_parsed.port:
                netloc = f"{netloc}:{new_parsed.port}"
            if new_parsed.username:
                netloc = f"{new_parsed.username}:{old_password}@{netloc}"
            else:
                netloc = f":{old_password}@{netloc}"
            return urlunparse(new_parsed._replace(netloc=netloc))
        except Exception:
            return new_uri

    updates = {}

    # 1. PostgreSQL
    pg = body.get("postgres", {})
    if "pg_dsn" in pg and pg["pg_dsn"]:
        reconstructed = reconstruct_uri(pg["pg_dsn"], cfg.PG_DSN)
        cfg.PG_DSN = reconstructed
        updates["PG_DSN"] = reconstructed
    if "db_read_url" in pg and pg["db_read_url"]:
        reconstructed = reconstruct_uri(pg["db_read_url"], cfg.DB_READ_URL)
        cfg.DB_READ_URL = reconstructed
        updates["DB_READ_URL"] = reconstructed
    if "db_write_url" in pg and pg["db_write_url"]:
        reconstructed = reconstruct_uri(pg["db_write_url"], cfg.DB_WRITE_URL)
        cfg.DB_WRITE_URL = reconstructed
        updates["DB_WRITE_URL"] = reconstructed
    if "pg_min_pool" in pg:
        try:
            val = int(pg["pg_min_pool"])
            cfg.PG_MIN_POOL = val
            updates["PG_MIN_POOL"] = str(val)
        except ValueError:
            pass
    if "pg_max_pool" in pg:
        try:
            val = int(pg["pg_max_pool"])
            cfg.PG_MAX_POOL = val
            updates["PG_MAX_POOL"] = str(val)
        except ValueError:
            pass

    # 2. MongoDB
    mongo = body.get("mongodb", {})
    if "mongo_uri" in mongo and mongo["mongo_uri"]:
        reconstructed = reconstruct_uri(mongo["mongo_uri"], cfg.MONGO_URI)
        cfg.MONGO_URI = reconstructed
        updates["MONGO_URI"] = reconstructed

    # 3. Redis
    redis_data = body.get("redis", {})
    if "redis_url" in redis_data and redis_data["redis_url"]:
        reconstructed = reconstruct_uri(redis_data["redis_url"], cfg.REDIS_URL)
        cfg.REDIS_URL = reconstructed
        updates["REDIS_URL"] = reconstructed
    if "redis_ttl" in redis_data:
        try:
            val = int(redis_data["redis_ttl"])
            cfg.REDIS_TTL = val
            updates["REDIS_TTL"] = str(val)
        except ValueError:
            pass
    if "redis_max_connections" in redis_data:
        try:
            val = int(redis_data["redis_max_connections"])
            cfg.REDIS_MAX_CONNECTIONS = val
            updates["REDIS_MAX_CONNECTIONS"] = str(val)
        except ValueError:
            pass

    # 4. MinIO S3
    minio = body.get("minio", {})
    if "minio_endpoint" in minio:
        cfg.MINIO_ENDPOINT = minio["minio_endpoint"]
        updates["MINIO_ENDPOINT"] = minio["minio_endpoint"]
    if "minio_access_key" in minio:
        cfg.MINIO_ACCESS_KEY = minio["minio_access_key"]
        updates["MINIO_ACCESS_KEY"] = minio["minio_access_key"]
    if "minio_secret_key" in minio:
        secret = minio["minio_secret_key"]
        if secret and secret != "••••••••":
            cfg.MINIO_SECRET_KEY = secret
            updates["MINIO_SECRET_KEY"] = secret
    if "minio_secure" in minio:
        secure_val = bool(minio["minio_secure"])
        cfg.MINIO_SECURE = secure_val
        updates["MINIO_SECURE"] = "true" if secure_val else "false"

    # Save updates back to active .env file on disk
    try:
        update_dotenv(updates)
    except Exception as exc:
        logger.exception("Failed to write datastores configuration to .env")
        return JSONResponse({"error": "Failed to persist configurations to .env", "detail": str(exc)}, status_code=500)

    return JSONResponse({"status": "success", "message": "Datastores config successfully updated."})


async def api_admin_signing_status(request):
    """GET /api/admin/signing/status — non-secret signing key rotation summary."""
    if not engine or not engine.pg_pool:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            payload = await admin_signing_keys_status(conn)
    except Exception as exc:
        logger.exception("api_admin_signing_status failed")
        return JSONResponse(
            {"error": "Failed to load signing keys status", "detail": str(exc)},
            status_code=500,
        )
    return JSONResponse(payload)


async def api_admin_pii_redactions_list(request):
    """GET /api/admin/pii-redactions — paginated vault rows (no ciphertext)."""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    qp = request.query_params
    try:
        namespace_id = parse_optional_uuid(qp.get("namespace_id"))
        page, limit = parse_page_limit_common(qp)
        offset = offset_from_page_limit(page, limit)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    where = "WHERE ($1::uuid IS NULL OR namespace_id = $1)"
    args: list[object] = [namespace_id]
    count_sql = f"SELECT COUNT(*)::bigint AS total FROM pii_redactions {where}"
    items_sql = f"""
        SELECT memory_id, namespace_id, entity_type, token, created_at
        FROM pii_redactions
        {where}
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
    """

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            total_row = await conn.fetchrow(count_sql, namespace_id)
            rows = await conn.fetch(items_sql, namespace_id, limit, offset)
    except Exception as exc:
        logger.exception("api_admin_pii_redactions_list failed")
        return JSONResponse(
            {"error": "Failed to list PII redactions", "detail": str(exc)},
            status_code=500,
        )

    items = [
        {
            "memory_id": str(r["memory_id"]),
            "namespace_id": str(r["namespace_id"]),
            "entity_type": r["entity_type"],
            "token": r["token"][:16] + "…" if len(r["token"]) > 16 else r["token"],
            "created_at": r["created_at"].astimezone(UTC).isoformat(),
        }
        for r in rows
    ]
    return JSONResponse(
        {
            "items": items,
            "page": page,
            "limit": limit,
            "total": int(total_row["total"]) if total_row else 0,
        }
    )


async def api_admin_security_event_seq_gaps(request):
    """GET /api/admin/security/event-seq-gaps/{namespace_id}"""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    raw_ns = request.path_params.get("namespace_id")
    try:
        namespace_id = uuid.UUID(raw_ns) if raw_ns else None
    except ValueError:
        return JSONResponse({"error": "Invalid namespace_id"}, status_code=422)
    if namespace_id is None:
        return JSONResponse({"error": "namespace_id required"}, status_code=422)

    gap_sql = """
        WITH s AS (
            SELECT event_seq,
                   LAG(event_seq) OVER (ORDER BY event_seq) AS prev
            FROM event_log
            WHERE namespace_id = $1
        )
        SELECT prev::bigint AS after_seq, event_seq::bigint AS before_seq
        FROM s
        WHERE prev IS NOT NULL AND event_seq > prev + 1
        ORDER BY event_seq
        LIMIT 200
    """

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            min_seq = await conn.fetchval(
                "SELECT MIN(event_seq)::bigint FROM event_log WHERE namespace_id = $1",
                namespace_id,
            )
            max_seq = await conn.fetchval(
                "SELECT MAX(event_seq)::bigint FROM event_log WHERE namespace_id = $1",
                namespace_id,
            )
            gap_rows = await conn.fetch(gap_sql, namespace_id)
    except Exception as exc:
        logger.exception("api_admin_security_event_seq_gaps failed")
        return JSONResponse(
            {"error": "Failed to compute sequence gaps", "detail": str(exc)},
            status_code=500,
        )

    gaps: list[dict[str, int]] = []
    if min_seq is not None and min_seq > 1:
        gaps.append({"after_seq": 0, "before_seq": int(min_seq)})
    for r in gap_rows:
        gaps.append(
            {"after_seq": int(r["after_seq"]), "before_seq": int(r["before_seq"])}
        )

    return JSONResponse(
        {
            "namespace_id": str(namespace_id),
            "min_seq": int(min_seq) if min_seq is not None else None,
            "max_seq": int(max_seq) if max_seq is not None else None,
            "gaps": gaps,
        }
    )


async def api_admin_security_verify_memory_sample(request):
    """POST /api/admin/security/verify-memory-sample

    Body: {"namespace_id"?: uuid, "sample_size"?: int 1–30}
    """
    if not engine or engine.memory is None:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        namespace_id = parse_optional_uuid(body.get("namespace_id"))
        raw_sz = body.get("sample_size")
        sample_size = clamp_bounded_int(
            None if raw_sz is None or raw_sz == "" else str(raw_sz),
            default=10,
            min_value=1,
            max_value=30,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    sample_sql = """
        SELECT id FROM memories
        WHERE valid_to IS NULL
          AND ($1::uuid IS NULL OR namespace_id = $1)
        ORDER BY random()
        LIMIT $2
    """

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            mem_rows = await conn.fetch(sample_sql, namespace_id, sample_size)
    except Exception as exc:
        logger.exception("api_admin_security_verify_memory_sample fetch failed")
        return JSONResponse(
            {"error": "Failed to sample memories", "detail": str(exc)},
            status_code=500,
        )

    results: list[dict[str, object]] = []
    invalid_count = 0
    for r in mem_rows:
        mid = str(r["id"])
        try:
            vr = await engine.memory.verify_memory(mid)
        except Exception as exc:
            results.append(
                {"memory_id": mid, "valid": False, "reason": str(exc), "key_id": None}
            )
            invalid_count += 1
            continue
        ok = bool(vr.get("valid"))
        if not ok:
            invalid_count += 1
        results.append(
            {
                "memory_id": mid,
                "valid": ok,
                "reason": vr.get("reason"),
                "key_id": vr.get("key_id"),
            }
        )

    return JSONResponse(
        {
            "sampled": len(results),
            "invalid_count": invalid_count,
            "namespace_filter": str(namespace_id) if namespace_id else None,
            "results": results,
        }
    )


async def api_admin_security_test_rls_isolation(request):
    """POST /api/admin/security/test-rls-isolation

    Body: {"namespace_id": uuid, "probe_namespace_id": uuid}
    Sets SET LOCAL trimcp.namespace_id to *namespace_id* and counts rows in
    *probe_namespace_id* — should be 0 when RLS enforces tenant isolation.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        ns_a = uuid.UUID(str(body["namespace_id"]))
        ns_b = uuid.UUID(str(body["probe_namespace_id"]))
    except (KeyError, ValueError):
        return JSONResponse(
            {"error": "namespace_id and probe_namespace_id (UUID) required"},
            status_code=422,
        )

    steps: list[str] = [
        "BEGIN;",
        f"SELECT set_config('trimcp.namespace_id', '{ns_a}', true);",
        f"-- COUNT(*) FROM memories WHERE namespace_id = '{ns_b}' (cross-tenant probe)",
        f"-- COUNT(*) FROM memories WHERE namespace_id = '{ns_a}' (same-tenant check)",
        "COMMIT;",
    ]

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            async with conn.transaction():
                await set_namespace_context(conn, ns_a)
                cross_count = await conn.fetchval(
                    "SELECT COUNT(*)::bigint FROM memories WHERE namespace_id = $1",
                    ns_b,
                )
                own_count = await conn.fetchval(
                    "SELECT COUNT(*)::bigint FROM memories WHERE namespace_id = $1",
                    ns_a,
                )
    except Exception as exc:
        logger.exception("api_admin_security_test_rls_isolation failed")
        return JSONResponse(
            {
                "error": "RLS isolation probe failed",
                "detail": str(exc),
                "steps": steps,
            },
            status_code=500,
        )

    isolation_ok = cross_count == 0
    return JSONResponse(
        {
            "scoped_namespace_id": str(ns_a),
            "probe_namespace_id": str(ns_b),
            "cross_tenant_rows_visible": int(cross_count or 0),
            "same_tenant_rows_visible": int(own_count or 0),
            "isolation_ok": isolation_ok,
            "policy_name": "namespace_isolation_policy",
            "steps": steps,
        }
    )


async def api_admin_namespaces_list(request):
    """GET /api/admin/namespaces

    Query params: slug_prefix?, page=1, limit=500

    Always includes ``namespaces`` (compat with admin UI).
    Pagination metadata: ``page``, ``limit``, ``total``, ``items`` (same slice as ``namespaces``).
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    qp = request.query_params
    prefix, pref_err = sanitize_slug_prefix_filter(qp.get("slug_prefix"))
    if pref_err:
        return JSONResponse({"error": pref_err}, status_code=422)

    try:
        page, limit = parse_page_limit_common(
            qp,
            default_limit=ADMIN_NAMESPACES_DEFAULT_LIMIT,
            max_limit=500,
        )
        offset = offset_from_page_limit(page, limit)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    clauses: list[str] = []
    args: list[object] = []
    bind = 1
    if prefix is not None:
        clauses.append(f"slug ILIKE ${bind}")
        args.append(prefix + "%")
        bind += 1
    where_sql = f"WHERE {' AND '.join(clauses)} " if clauses else ""

    count_sql = f"SELECT COUNT(*)::bigint AS total FROM namespaces {where_sql}"
    items_sql = f"""
        SELECT id, slug, parent_id, created_at, metadata
        FROM namespaces
        {where_sql}
        ORDER BY slug
        LIMIT ${bind} OFFSET ${bind + 1}
    """

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            total_row = await conn.fetchrow(count_sql, *args)
            rows = await conn.fetch(items_sql, *args, limit, offset)
        namespaces: list[dict] = []
        for r in rows:
            namespaces.append(
                {
                    "id": str(r["id"]),
                    "slug": r["slug"],
                    "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
                    "created_at": (
                        r["created_at"].astimezone(UTC).isoformat()
                        if r["created_at"]
                        else None
                    ),
                    "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                }
            )
        total = int(total_row["total"]) if total_row else 0
        return JSONResponse(
            {
                "namespaces": namespaces,
                "items": namespaces,
                "page": page,
                "limit": limit,
                "total": total,
            }
        )
    except Exception as exc:
        logger.exception("api_admin_namespaces_list failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_namespaces_get(request):
    """GET /api/admin/namespaces/{namespace_id}
    Retrieves metadata and info for a specific namespace.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        ns_id = uuid.UUID(request.path_params["namespace_id"])
    except ValueError:
        return JSONResponse({"error": "Invalid namespace_id UUID"}, status_code=400)

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            row = await conn.fetchrow(
                "SELECT id, slug, parent_id, created_at, metadata FROM namespaces WHERE id = $1",
                ns_id
            )
        if not row:
            return JSONResponse({"error": "Namespace not found"}, status_code=404)
        return JSONResponse({
            "id": str(row["id"]),
            "slug": row["slug"],
            "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
            "created_at": row["created_at"].astimezone(UTC).isoformat() if row["created_at"] else None,
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
        })
    except Exception as exc:
        logger.exception("api_admin_namespaces_get failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_namespaces_update_metadata(request):
    """POST /api/admin/namespaces/{namespace_id}/metadata
    Saves/updates a namespace's metadata, routing through engine.manage_namespace.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        ns_id = uuid.UUID(request.path_params["namespace_id"])
    except ValueError:
        return JSONResponse({"error": "Invalid namespace_id UUID"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)

    try:
        from pydantic import ValidationError
        from trimcp.models import ManageNamespaceRequest, NamespaceMetadataPatch

        patch = NamespaceMetadataPatch.model_validate(body)
        payload = ManageNamespaceRequest(
            command="update_metadata",
            namespace_id=ns_id,
            metadata_patch=patch
        )

        res = await engine.manage_namespace(payload, admin_identity="admin_webportal")
        return JSONResponse(res)
    except ValidationError as exc:
        return JSONResponse({"error": "Validation failed", "detail": exc.errors()}, status_code=422)
    except Exception as exc:
        logger.exception("api_admin_namespaces_update_metadata failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_admin_memory_boost(request):
    """POST /api/admin/memory/boost — salience reinforce via CognitiveOrchestrator."""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    try:
        ns = parse_optional_uuid(body.get("namespace_id"))
        mem = parse_optional_uuid(body.get("memory_id"))
    except ValueError:
        return JSONResponse({"error": "Invalid UUID"}, status_code=400)

    if ns is None or mem is None:
        return JSONResponse(
            {"error": "namespace_id and memory_id are required"}, status_code=422
        )

    agent_raw = body.get("agent_id")
    agent_id = (str(agent_raw).strip() if agent_raw else "") or "default"

    try:
        factor = float(body.get("factor")) if body.get("factor") is not None else 0.2
    except (TypeError, ValueError):
        return JSONResponse({"error": "factor must be a number"}, status_code=422)

    try:
        res = await engine.boost_memory(
            memory_id=str(mem),
            agent_id=agent_id,
            namespace_id=str(ns),
            factor=factor,
        )
    except Exception as exc:
        logger.exception("api_admin_memory_boost failed")
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse(res)


async def api_admin_salience_map(request):
    """GET /api/admin/salience-map

    Query params: ``namespace_id`` (required), ``agent_id?``, ``top_k?``, ``half_life_days?``
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    qp = request.query_params
    try:
        ns = parse_optional_uuid(qp.get("namespace_id"))
        if ns is None:
            return JSONResponse({"error": "namespace_id is required"}, status_code=422)
    except ValueError:
        return JSONResponse({"error": "Invalid namespace_id UUID"}, status_code=400)

    top_k, tk_err = parse_salience_top_k(qp.get("top_k"))
    if tk_err:
        return JSONResponse({"error": tk_err}, status_code=422)
    agent_filter, ag_err = sanitize_optional_agent_filter(qp.get("agent_id"))
    if ag_err:
        return JSONResponse({"error": ag_err}, status_code=422)

    hl_default = float(cfg.CONSOLIDATION_HALF_LIFE_DAYS)
    half_life, hl_err = parse_optional_half_life_days(
        qp.get("half_life_days"), default=hl_default
    )
    if hl_err:
        return JSONResponse({"error": hl_err}, status_code=422)

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            points = await fetch_salience_map_points(
                conn,
                namespace_id=ns,
                agent_id=agent_filter,
                top_k=top_k,
                half_life_days=half_life,
            )
    except Exception as exc:
        logger.exception("api_admin_salience_map failed ns=%s", ns)
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse(
        {
            "namespace_id": str(ns),
            "half_life_days": half_life,
            "top_k": top_k,
            "points": points,
            "total_returned": len(points),
        }
    )


async def api_admin_llm_payload(request):
    """GET /api/admin/llm-payload

    Query params: ``namespace_id``, ``event_id`` — fetches consolidated LLM artifact JSON from MinIO.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    qp = request.query_params
    try:
        ns = parse_optional_uuid(qp.get("namespace_id"))
        evt_raw = qp.get("event_id")
        evt = uuid.UUID(evt_raw) if evt_raw else None
    except ValueError:
        return JSONResponse({"error": "Invalid UUID in namespace_id/event_id"}, status_code=400)

    if ns is None or evt is None:
        return JSONResponse(
            {"error": "namespace_id and event_id are required"}, status_code=422
        )

    try:
        from trimcp import salience as _salience

        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            uri, uri_err = await fetch_event_llm_payload_uri(
                conn, namespace_id=ns, event_id=evt
            )
        if uri_err:
            return JSONResponse({"error": uri_err}, status_code=404)
        assert uri is not None
        payload = await _salience.fetch_llm_payload(uri)
    except Exception as exc:
        logger.exception("api_admin_llm_payload failed")
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse({"llm_payload_uri": uri, "payload": payload})


async def api_admin_fleet_overview(request):
    """GET /api/admin/fleet-overview — namespace-scoped rollup for fleet monitoring."""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    qp = request.query_params
    prefix, pref_err = sanitize_slug_prefix_filter(qp.get("slug_prefix"))
    if pref_err:
        return JSONResponse({"error": pref_err}, status_code=422)

    try:
        page, limit = parse_page_limit_common(qp)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    hl_default = float(cfg.CONSOLIDATION_HALF_LIFE_DAYS)
    half_life, hl_err = parse_optional_half_life_days(
        qp.get("half_life_days"), default=hl_default
    )
    if hl_err:
        return JSONResponse({"error": hl_err}, status_code=422)

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            rls = await fetch_pg_rls_snapshot(conn)
            items, total = await fetch_fleet_overview_page(
                conn,
                slug_prefix=prefix,
                page=page,
                limit=limit,
                half_life_days=half_life,
            )
    except Exception as exc:
        logger.exception("api_admin_fleet_overview failed")
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse(
        {
            "items": items,
            "page": page,
            "limit": limit,
            "total": total,
            "half_life_days": half_life,
            "rls_tenant_tables": rls,
        }
    )


async def api_admin_contradictions_recent(request):
    """GET /api/admin/contradictions/recent — Fleet contradiction feed."""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        limit = int(request.query_params.get("limit") or "5")
    except ValueError:
        return JSONResponse({"error": "Invalid limit"}, status_code=422)
    limit = max(1, min(limit, 50))
    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            items = await fetch_recent_open_contradictions(conn, limit=limit)
    except Exception as exc:
        logger.exception("api_admin_contradictions_recent failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"items": items, "limit": limit})


async def api_admin_namespace_bridges(request):
    """GET /api/admin/namespaces/{namespace_id}/bridges — integration cards."""
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)
    try:
        ns_uuid = uuid.UUID(request.path_params["namespace_id"])
    except ValueError:
        return JSONResponse({"error": "Invalid namespace_id UUID"}, status_code=400)
    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            items = await fetch_namespace_bridge_subscriptions(conn, ns_uuid)
    except Exception as exc:
        logger.exception("api_admin_namespace_bridges failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"items": items, "namespace_id": str(ns_uuid)})


async def api_admin_bridge_renew(request):
    """POST /api/admin/bridges/{bridge_id}/renew

    Forces a webhook subscription refresh for SharePoint/Google Drive integrations.
    Optional query ``namespace_id`` scopes the call when the caller wants an extra guardrail.
    """
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        bridge_uuid = uuid.UUID(request.path_params["bridge_id"])
    except ValueError:
        return JSONResponse({"error": "Invalid bridge_id UUID"}, status_code=400)

    try:
        ns_guard = parse_optional_uuid(request.query_params.get("namespace_id"))
    except ValueError:
        return JSONResponse({"error": "Invalid namespace_id UUID"}, status_code=400)

    from trimcp.bridge_renewal import renew_dropbox, renew_gdrive, renew_sharepoint

    try:
        async with engine.pg_pool.acquire(timeout=10.0) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM bridge_subscriptions WHERE id = $1",
                bridge_uuid,
            )
        if row is None:
            return JSONResponse({"error": "bridge subscription not found"}, status_code=404)
        if (
            ns_guard is not None
            and row["namespace_id"] is not None
            and row["namespace_id"] != ns_guard
        ):
            return JSONResponse({"error": "namespace_id does not own this bridge"}, status_code=403)
    except Exception as exc:
        logger.exception("api_admin_bridge_renew prefetch failed bridge_id=%s", bridge_uuid)
        return JSONResponse({"error": str(exc)}, status_code=500)

    prov = row["provider"]
    logger.info(
        "audit bridge_admin_renew_requested bridge_id=%s provider=%s namespace_id=%s",
        bridge_uuid,
        prov,
        row["namespace_id"],
    )

    try:
        if prov == "sharepoint":
            await renew_sharepoint(engine.pg_pool, row)
            action = "renewed_sharepoint"
        elif prov == "gdrive":
            await renew_gdrive(engine.pg_pool, row)
            action = "renewed_gdrive"
        elif prov == "dropbox":
            await renew_dropbox(engine.pg_pool, row)
            action = "noop_dropbox"
        else:
            return JSONResponse(
                {"error": f"Unsupported provider for renewal: {prov}"}, status_code=422
            )
    except Exception as exc:
        logger.exception("audit bridge_admin_renew_failed bridge_id=%s", bridge_uuid)
        return JSONResponse({"error": str(exc)}, status_code=500)

    logger.info(
        "audit bridge_admin_renew_succeeded bridge_id=%s provider=%s action=%s",
        bridge_uuid,
        prov,
        action,
    )
    return JSONResponse({"status": "ok", "action": action, "bridge_id": str(bridge_uuid)})




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
        Route("/styles.css", endpoint=serve_styles),
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
            "/api/admin/signing/status",
            endpoint=api_admin_signing_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/pii-redactions",
            endpoint=api_admin_pii_redactions_list,
            methods=["GET"],
        ),
        Route(
            "/api/admin/security/event-seq-gaps/{namespace_id}",
            endpoint=api_admin_security_event_seq_gaps,
            methods=["GET"],
        ),
        Route(
            "/api/admin/security/verify-memory-sample",
            endpoint=api_admin_security_verify_memory_sample,
            methods=["POST"],
        ),
        Route(
            "/api/admin/security/test-rls-isolation",
            endpoint=api_admin_security_test_rls_isolation,
            methods=["POST"],
        ),
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
        Route(
            "/api/admin/db/postgres/status",
            endpoint=api_admin_db_postgres_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/db/mongo/status",
            endpoint=api_admin_db_mongo_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/db/redis/status",
            endpoint=api_admin_db_redis_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/db/minio/status",
            endpoint=api_admin_db_minio_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/connectors/status",
            endpoint=api_admin_connectors_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/connectors/save",
            endpoint=api_admin_connectors_save,
            methods=["POST"],
        ),
        Route(
            "/api/admin/datastores/status",
            endpoint=api_admin_datastores_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/datastores/save",
            endpoint=api_admin_datastores_save,
            methods=["POST"],
        ),
        Route(
            "/api/admin/namespaces",
            endpoint=api_admin_namespaces_list,
            methods=["GET"],
        ),
        Route(
            "/api/admin/namespaces/{namespace_id}",
            endpoint=api_admin_namespaces_get,
            methods=["GET"],
        ),
        Route(
            "/api/admin/namespaces/{namespace_id}/metadata",
            endpoint=api_admin_namespaces_update_metadata,
            methods=["POST"],
        ),
        Route(
            "/api/admin/memory/boost",
            endpoint=api_admin_memory_boost,
            methods=["POST"],
        ),
        Route(
            "/api/admin/salience-map",
            endpoint=api_admin_salience_map,
            methods=["GET"],
        ),
        Route(
            "/api/admin/llm-payload",
            endpoint=api_admin_llm_payload,
            methods=["GET"],
        ),
        Route(
            "/api/admin/fleet-overview",
            endpoint=api_admin_fleet_overview,
            methods=["GET"],
        ),
        Route(
            "/api/admin/contradictions/recent",
            endpoint=api_admin_contradictions_recent,
            methods=["GET"],
        ),
        Route(
            "/api/admin/namespaces/{namespace_id}/bridges",
            endpoint=api_admin_namespace_bridges,
            methods=["GET"],
        ),
        Route(
            "/api/admin/bridges/{bridge_id}/renew",
            endpoint=api_admin_bridge_renew,
            methods=["POST"],
        ),
    ],
)

def _assert_admin_override_not_in_production() -> None:
    """Raise at startup if TRIMCP_ADMIN_OVERRIDE is active in production.

    This guard prevents a development shortcut from silently bypassing
    authentication in production deployments. See FIX-039.
    """
    if os.getenv("TRIMCP_ADMIN_OVERRIDE") and os.getenv("ENVIRONMENT", "dev") == "prod":
        raise RuntimeError(
            "TRIMCP_ADMIN_OVERRIDE must not be set when ENVIRONMENT=prod. "
            "Remove this environment variable from the production configuration."
        )


if __name__ == "__main__":
    import uvicorn

    _assert_admin_override_not_in_production()
    uvicorn.run(app, host="0.0.0.0", port=8003)
