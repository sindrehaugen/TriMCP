"""Starlette admin application factory (routes, middleware, lifespan)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from nce import admin_http_handlers as h
from nce import admin_state
from nce.auth import (
    AdminHTTPRateLimitMiddleware,
    BasicAuthMiddleware,
    HMACAuthMiddleware,
    optional_hmac_nonce_store,
)
from nce.config import cfg
from nce.mtls import MTLSAuthMiddleware
from nce.notifications import dispatcher
from nce.observability import OpenTelemetryTraceMiddleware
from nce.orchestrator import NCEEngine

logger = logging.getLogger("nce-admin")

_hmac_nonce_store = optional_hmac_nonce_store()


@asynccontextmanager
async def admin_lifespan(app):
    from nce.config import assert_admin_override_not_in_production

    assert_admin_override_not_in_production()

    admin_state.engine = NCEEngine()
    await admin_state.engine.connect()
    app.state.redis_client = admin_state.engine.redis_client
    await dispatcher.start_worker()
    logger.info("NCE Admin: engine connected, dispatcher started.")

    try:
        from nce.observability import EVENT_LOG_PARTITION_MONTHS_AHEAD

        async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
            await conn.execute(
                f"SELECT nce_ensure_event_log_monthly_partitions({cfg.NCE_PARTITION_LOOKAHEAD_MONTHS})"
            )
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
    await admin_state.engine.disconnect()
    logger.info("NCE Admin: shutdown complete.")


async def get_healthz(request):
    """Unauthenticated liveness probe for load balancers / orchestrators."""
    return JSONResponse({"status": "ok"})


def build_admin_middleware() -> list[Middleware]:
    return [
        Middleware(OpenTelemetryTraceMiddleware),
        Middleware(AdminHTTPRateLimitMiddleware),
        Middleware(
            MTLSAuthMiddleware,
            protected_prefix="/api/",
            enabled=cfg.NCE_ADMIN_MTLS_ENABLED,
            strict=cfg.NCE_ADMIN_MTLS_STRICT,
            trusted_proxy_hops=cfg.NCE_ADMIN_MTLS_TRUSTED_PROXY_HOP,
            allowed_sans=cfg.NCE_ADMIN_MTLS_ALLOWED_SANS,
            allowed_fingerprints=cfg.NCE_ADMIN_MTLS_ALLOWED_FINGERPRINTS,
        ),
        Middleware(
            BasicAuthMiddleware,
            protected_prefix="/",
            excluded_prefixes=("/api/", "/healthz"),
            username=cfg.NCE_ADMIN_USERNAME,
            password=cfg.NCE_ADMIN_PASSWORD,
            realm="NCE Admin",
        ),
        Middleware(
            HMACAuthMiddleware,
            protected_prefix="/api/",
            api_key=cfg.NCE_API_KEY,
            nonce_store=_hmac_nonce_store,
        ),
    ]


def build_admin_routes() -> list[Route]:
    return [
        Route("/healthz", endpoint=get_healthz, methods=["GET"]),
        Route("/", endpoint=h.serve_index),
        Route("/styles.css", endpoint=h.serve_styles),
        Route("/api/health", endpoint=h.get_health, methods=["GET"]),
        Route("/api/health/v1", endpoint=h.get_health_v1, methods=["GET"]),
        Route("/api/gc/trigger", endpoint=h.trigger_gc, methods=["POST"]),
        Route("/api/search", endpoint=h.api_search, methods=["POST"]),
        Route("/api/replay/observe", endpoint=h.api_replay_observe, methods=["POST"]),
        Route("/api/replay/fork", endpoint=h.api_replay_fork, methods=["POST"]),
        Route("/api/replay/status/{run_id}", endpoint=h.api_replay_status, methods=["GET"]),
        Route(
            "/api/replay/provenance/{memory_id}",
            endpoint=h.api_event_provenance,
            methods=["GET"],
        ),
        Route("/api/snapshot/export", endpoint=h.api_snapshot_export, methods=["POST"]),
        Route("/api/a2a/grants/create", endpoint=h.api_a2a_create_grant, methods=["POST"]),
        Route(
            "/api/a2a/grants/{grant_id}/revoke",
            endpoint=h.api_a2a_revoke_grant,
            methods=["POST"],
        ),
        Route("/api/a2a/grants", endpoint=h.api_a2a_list_grants, methods=["GET"]),
        Route("/api/admin/events", endpoint=h.api_admin_events, methods=["GET"]),
        Route(
            "/api/admin/events/summary",
            endpoint=h.api_admin_events_summary,
            methods=["GET"],
        ),
        Route("/api/admin/tools", endpoint=h.api_admin_tools, methods=["GET"]),
        Route(
            "/api/admin/tools/toggle",
            endpoint=h.api_admin_tools_toggle,
            methods=["POST"],
        ),
        Route("/api/admin/a2a/grants", endpoint=h.api_admin_a2a_grants, methods=["GET"]),
        Route(
            "/api/admin/a2a/grants/summary",
            endpoint=h.api_admin_a2a_grants_summary,
            methods=["GET"],
        ),
        Route(
            "/api/admin/a2a/grants/{grant_id}/revoke",
            endpoint=h.api_admin_a2a_revoke_grant,
            methods=["POST"],
        ),
        Route("/api/admin/quotas", endpoint=h.api_admin_quotas, methods=["GET"]),
        Route("/api/admin/settings", endpoint=h.api_admin_settings_list, methods=["GET"]),
        Route("/api/admin/settings", endpoint=h.api_admin_settings_patch, methods=["PATCH"]),
        Route(
            "/api/admin/settings/effective",
            endpoint=h.api_admin_settings_effective,
            methods=["GET"],
        ),
        Route(
            "/api/admin/settings/pending",
            endpoint=h.api_admin_settings_pending,
            methods=["GET"],
        ),
        Route(
            "/api/admin/settings/reset",
            endpoint=h.api_admin_settings_reset,
            methods=["POST"],
        ),
        Route(
            "/api/admin/settings/reload",
            endpoint=h.api_admin_settings_reload,
            methods=["POST"],
        ),
        Route(
            "/api/admin/settings/rollback",
            endpoint=h.api_admin_settings_rollback,
            methods=["POST"],
        ),
        Route(
            "/api/admin/settings/{key}",
            endpoint=h.api_admin_settings_get,
            methods=["GET"],
        ),
        Route(
            "/api/admin/signing/status",
            endpoint=h.api_admin_signing_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/pii-redactions",
            endpoint=h.api_admin_pii_redactions_list,
            methods=["GET"],
        ),
        Route(
            "/api/admin/security/event-seq-gaps/{namespace_id}",
            endpoint=h.api_admin_security_event_seq_gaps,
            methods=["GET"],
        ),
        Route(
            "/api/admin/security/verify-memory-sample",
            endpoint=h.api_admin_security_verify_memory_sample,
            methods=["POST"],
        ),
        Route(
            "/api/admin/security/test-rls-isolation",
            endpoint=h.api_admin_security_test_rls_isolation,
            methods=["POST"],
        ),
        Route(
            "/api/admin/quotas/summary",
            endpoint=h.api_admin_quotas_summary,
            methods=["GET"],
        ),
        Route(
            "/api/admin/graph/explore",
            endpoint=h.api_admin_graph_explore,
            methods=["POST"],
        ),
        Route(
            "/api/admin/graph/provenance/{memory_id}",
            endpoint=h.api_event_provenance,
            methods=["GET"],
        ),
        Route(
            "/api/admin/verify-chain/{namespace_id}",
            endpoint=h.api_admin_verify_chain,
            methods=["GET"],
        ),
        Route(
            "/api/admin/embedding-models",
            endpoint=h.api_admin_embedding_models,
            methods=["GET"],
        ),
        Route(
            "/api/admin/embedding-migrations/start",
            endpoint=h.api_admin_embedding_migration_start,
            methods=["POST"],
        ),
        Route(
            "/api/admin/embedding-migrations/{migration_id}/status",
            endpoint=h.api_admin_embedding_migration_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/embedding-migrations/{migration_id}/validate",
            endpoint=h.api_admin_embedding_migration_validate,
            methods=["POST"],
        ),
        Route(
            "/api/admin/embedding-migrations/{migration_id}/commit",
            endpoint=h.api_admin_embedding_migration_commit,
            methods=["POST"],
        ),
        Route(
            "/api/admin/embedding-migrations/{migration_id}/abort",
            endpoint=h.api_admin_embedding_migration_abort,
            methods=["POST"],
        ),
        Route("/api/admin/schema", endpoint=h.api_admin_schema, methods=["GET"]),
        Route("/api/admin/dlq", endpoint=h.api_admin_dlq_list, methods=["GET"]),
        Route(
            "/api/admin/dlq/{dlq_id}/replay",
            endpoint=h.api_admin_dlq_replay,
            methods=["POST"],
        ),
        Route(
            "/api/admin/dlq/{dlq_id}/purge",
            endpoint=h.api_admin_dlq_purge,
            methods=["POST"],
        ),
        Route(
            "/api/admin/db/postgres/status",
            endpoint=h.api_admin_db_postgres_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/db/mongo/status",
            endpoint=h.api_admin_db_mongo_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/db/redis/status",
            endpoint=h.api_admin_db_redis_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/db/minio/status",
            endpoint=h.api_admin_db_minio_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/connectors/status",
            endpoint=h.api_admin_connectors_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/connectors/save",
            endpoint=h.api_admin_connectors_save,
            methods=["POST"],
        ),
        Route(
            "/api/admin/datastores/status",
            endpoint=h.api_admin_datastores_status,
            methods=["GET"],
        ),
        Route(
            "/api/admin/datastores/save",
            endpoint=h.api_admin_datastores_save,
            methods=["POST"],
        ),
        Route(
            "/api/admin/namespaces",
            endpoint=h.api_admin_namespaces_list,
            methods=["GET"],
        ),
        Route(
            "/api/admin/namespaces/{namespace_id}",
            endpoint=h.api_admin_namespaces_get,
            methods=["GET"],
        ),
        Route(
            "/api/admin/namespaces/{namespace_id}/metadata",
            endpoint=h.api_admin_namespaces_update_metadata,
            methods=["POST"],
        ),
        Route(
            "/api/admin/memory/boost",
            endpoint=h.api_admin_memory_boost,
            methods=["POST"],
        ),
        Route(
            "/api/admin/salience-map",
            endpoint=h.api_admin_salience_map,
            methods=["GET"],
        ),
        Route(
            "/api/admin/llm-payload",
            endpoint=h.api_admin_llm_payload,
            methods=["GET"],
        ),
        Route(
            "/api/admin/fleet-overview",
            endpoint=h.api_admin_fleet_overview,
            methods=["GET"],
        ),
        Route(
            "/api/admin/actor-trust",
            endpoint=h.api_admin_actor_trust,
            methods=["GET"],
        ),
        Route(
            "/api/admin/approval-queue",
            endpoint=h.api_admin_approval_queue_list,
            methods=["GET"],
        ),
        Route(
            "/api/admin/approval-queue/{id}",
            endpoint=h.api_admin_approval_queue_get,
            methods=["GET"],
        ),
        Route(
            "/api/admin/contradictions/recent",
            endpoint=h.api_admin_contradictions_recent,
            methods=["GET"],
        ),
        Route(
            "/api/admin/namespaces/{namespace_id}/bridges",
            endpoint=h.api_admin_namespace_bridges,
            methods=["GET"],
        ),
        Route(
            "/api/admin/bridges/{bridge_id}/renew",
            endpoint=h.api_admin_bridge_renew,
            methods=["POST"],
        ),
        # ------------------------------------------------------------------
        # Dynamics 365 / Dataverse admin endpoints
        # ------------------------------------------------------------------
        Route(
            "/api/admin/d365/config",
            endpoint=h.api_admin_d365_config,
            methods=["GET"],
        ),
        Route(
            "/api/admin/d365/integrations",
            endpoint=h.api_admin_d365_integrations,
            methods=["GET"],
        ),
        Route(
            "/api/admin/d365/sync",
            endpoint=h.api_admin_d365_sync_now,
            methods=["POST"],
        ),
        Route(
            "/api/admin/d365/sla-breaches",
            endpoint=h.api_admin_d365_sla_breaches,
            methods=["GET"],
        ),
        Route(
            "/api/admin/d365/namespace/{ns_id}/d365-enabled",
            endpoint=h.api_admin_d365_namespace_update,
            methods=["POST"],
        ),
        Route(
            "/api/admin/d365/netbox-mappings",
            endpoint=h.api_admin_d365_netbox_mappings,
            methods=["GET"],
        ),
        Route(
            "/api/admin/d365/netbox-mappings/{mapping_id}/confirm",
            endpoint=h.api_admin_d365_netbox_mapping_confirm,
            methods=["POST"],
        ),
        Route(
            "/api/admin/d365/netbox-bridge/sync",
            endpoint=h.api_admin_d365_netbox_bridge_sync,
            methods=["POST"],
        ),
    ]


def create_admin_app() -> Starlette:
    return Starlette(
        debug=False,
        lifespan=admin_lifespan,
        middleware=build_admin_middleware(),
        routes=build_admin_routes(),
    )


app = create_admin_app()
