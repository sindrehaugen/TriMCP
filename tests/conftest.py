"""Pytest bootstrap — per-test signing cache isolation for parallel-safe execution."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

# `trimcp.config` fails fast on import if unset; tests often import the package
# without a local .env — provide deterministic dev keys for collection only.
for _key, _default in {
    "TRIMCP_MASTER_KEY": "x" * 32,
    "TRIMCP_ADMIN_API_KEY": "test-admin-api-key-for-unit-tests",
    "TRIMCP_MCP_API_KEY": "test-mcp-api-key-for-unit-tests",
    "DROPBOX_APP_SECRET": "test-dropbox-secret",
    "GRAPH_CLIENT_STATE": "test-graph-state",
    "DRIVE_CHANNEL_TOKEN": "test-drive-token",
}.items():
    os.environ.setdefault(_key, _default)

import asyncpg
import pytest
import pytest_asyncio


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run ``test_init_public_api`` last — it purges ``trimcp`` from ``sys.modules``."""
    purge_last: list[pytest.Item] = []
    rest: list[pytest.Item] = []
    for item in items:
        if "test_init_public_api" in item.nodeid:
            purge_last.append(item)
        else:
            rest.append(item)
    items[:] = rest + purge_last


@pytest.fixture(autouse=True)
def _inject_mcp_tenant_api_key_for_tool_calls(monkeypatch):
    """Tenant MCP tools require mcp_api_key in production; tests often omit it."""
    from trimcp.auth import MCP_ADMIN_TOOL_NAMES, enforce_mcp_tool_auth

    _real = enforce_mcp_tool_auth

    def _enforce_with_test_keys(tool_name: str, arguments: dict) -> None:
        args = dict(arguments)
        if tool_name in MCP_ADMIN_TOOL_NAMES:
            args.setdefault("admin_api_key", os.environ.get("TRIMCP_ADMIN_API_KEY", ""))
        elif not args.get("admin_api_key"):
            args.setdefault("mcp_api_key", os.environ.get("TRIMCP_MCP_API_KEY", ""))
        return _real(tool_name, args)

    monkeypatch.setattr("trimcp.auth.enforce_mcp_tool_auth", _enforce_with_test_keys)
    monkeypatch.setattr(
        "trimcp.mcp_stdio_dispatch.enforce_mcp_tool_auth", _enforce_with_test_keys
    )


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def first_recorded_contradiction(out: dict | None) -> dict | None:
    """First row from ``detect_contradictions`` (``{"contradictions": [...]}`` or legacy flat dict)."""
    if out is None:
        return None
    items = out.get("contradictions")
    if items:
        return items[0]
    return out


_TEST_ENV_DEFAULTS: dict[str, str] = {
    "TRIMCP_MASTER_KEY": "x" * 32,
    "TRIMCP_ADMIN_API_KEY": "test-admin-api-key-for-unit-tests",
    "TRIMCP_MCP_API_KEY": "test-mcp-api-key-for-unit-tests",
    "DROPBOX_APP_SECRET": "test-dropbox-secret",
    "GRAPH_CLIENT_STATE": "test-graph-state",
    "DRIVE_CHANNEL_TOKEN": "test-drive-token",
}


def _restore_mcp_env_api_keys() -> None:
    """Some tests clear env keys (e.g. admin hardening); restore blanks for isolation."""
    for key, default in _TEST_ENV_DEFAULTS.items():
        if not os.environ.get(key, "").strip():
            os.environ[key] = default


def _restore_trimcp_cfg_from_env() -> None:
    """Reset module-level ``cfg`` fields tests often mutate on the shared singleton."""
    from trimcp.config import cfg

    _restore_mcp_env_api_keys()

    env = os.environ.get("TRIMCP_ENV", "dev").strip().lower()
    cfg.ENVIRONMENT = env
    cfg.IS_PROD = env in {"prod", "production"}
    cfg.IS_TEST = env in {"test", "testing", "ci"}
    cfg.IS_DEV = not cfg.IS_PROD and not cfg.IS_TEST
    cfg.REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    cfg.TRIMCP_API_KEY = os.environ.get("TRIMCP_API_KEY", getattr(cfg, "TRIMCP_API_KEY", ""))
    cfg.TRIMCP_MCP_API_KEY = os.environ.get(
        "TRIMCP_MCP_API_KEY", "test-mcp-api-key-for-unit-tests"
    )
    cfg.TRIMCP_MCP_NAMESPACE_ID = os.environ.get("TRIMCP_MCP_NAMESPACE_ID", "")
    cfg.TRIMCP_ADMIN_API_KEY = os.environ.get(
        "TRIMCP_ADMIN_API_KEY", "test-admin-api-key-for-unit-tests"
    )
    cfg.TRIMCP_ADMIN_OVERRIDE = _env_bool("TRIMCP_ADMIN_OVERRIDE", default=False)
    cfg.TRIMCP_QUOTAS_ENABLED = _env_bool("TRIMCP_QUOTAS_ENABLED", default=True)
    cfg.TRIMCP_QUOTA_REDIS_COUNTERS = _env_bool("TRIMCP_QUOTA_REDIS_COUNTERS", default=True)
    cfg.TRIMCP_OBSERVABILITY_ENABLED = _env_bool("TRIMCP_OBSERVABILITY_ENABLED", default=True)
    cfg.TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS = int(
        os.environ.get("TRIMCP_MAX_TEMPORAL_LOOKBACK_DAYS", "90")
    )
    cfg.TRIMCP_JWT_SECRET = os.environ.get("TRIMCP_JWT_SECRET", "")
    cfg.TRIMCP_JWT_PUBLIC_KEY = os.environ.get("TRIMCP_JWT_PUBLIC_KEY", "")
    cfg.TRIMCP_JWT_ALGORITHM = (os.environ.get("TRIMCP_JWT_ALGORITHM") or "HS256").upper().strip()
    cfg.TRIMCP_JWT_ISSUER = os.environ.get("TRIMCP_JWT_ISSUER", "")
    cfg.TRIMCP_JWT_AUDIENCE = os.environ.get("TRIMCP_JWT_AUDIENCE", "")
    cfg.TRIMCP_JWT_LEEWAY_SECONDS = int(os.environ.get("TRIMCP_JWT_LEEWAY_SECONDS", "30"))
    cfg.TRIMCP_DISABLE_MIGRATION_MCP = _env_bool(
        "TRIMCP_DISABLE_MIGRATION_MCP", default=cfg.IS_PROD
    )
    cfg.TRIMCP_MINIO_REQUIRED = _env_bool("TRIMCP_MINIO_REQUIRED", default=True)
    cfg.TRIMCP_EMBEDDING_MODEL_REVISION = os.environ.get("TRIMCP_EMBEDDING_MODEL_REVISION", "")
    cfg.AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
    cfg.AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
    cfg.GDRIVE_OAUTH_CLIENT_ID = os.environ.get("GDRIVE_OAUTH_CLIENT_ID", "")
    cfg.GDRIVE_OAUTH_CLIENT_SECRET = os.environ.get("GDRIVE_OAUTH_CLIENT_SECRET", "")
    cfg.DROPBOX_OAUTH_CLIENT_ID = os.environ.get("DROPBOX_OAUTH_CLIENT_ID", "")
    cfg.WEBHOOK_MAX_BODY_BYTES = max(
        1, int(os.environ.get("WEBHOOK_MAX_BODY_BYTES", str(cfg.WEBHOOK_MAX_BODY_BYTES)))
    )
    cfg.WEBHOOK_RATE_LIMIT = max(
        1, int(os.environ.get("WEBHOOK_RATE_LIMIT", str(cfg.WEBHOOK_RATE_LIMIT)))
    )
    cfg.WEBHOOK_RATE_PERIOD_SECONDS = max(
        1,
        int(os.environ.get("WEBHOOK_RATE_PERIOD_SECONDS", str(cfg.WEBHOOK_RATE_PERIOD_SECONDS))),
    )
    cfg.WEBHOOK_DEDUP_TTL_SECONDS = max(
        60, int(os.environ.get("WEBHOOK_DEDUP_TTL_SECONDS", str(cfg.WEBHOOK_DEDUP_TTL_SECONDS)))
    )
    cfg.WEBHOOK_DEDUP_FAIL_OPEN = _env_bool("WEBHOOK_DEDUP_FAIL_OPEN", default=False)
    cfg.DROPBOX_APP_SECRET = os.environ.get(
        "DROPBOX_APP_SECRET", _TEST_ENV_DEFAULTS["DROPBOX_APP_SECRET"]
    )
    cfg.GRAPH_CLIENT_STATE = os.environ.get(
        "GRAPH_CLIENT_STATE", _TEST_ENV_DEFAULTS["GRAPH_CLIENT_STATE"]
    )
    cfg.DRIVE_CHANNEL_TOKEN = os.environ.get(
        "DRIVE_CHANNEL_TOKEN", _TEST_ENV_DEFAULTS["DRIVE_CHANNEL_TOKEN"]
    )
    cfg.TRIMCP_WEBHOOK_TRUST_PROXY = _env_bool("TRIMCP_WEBHOOK_TRUST_PROXY", default=False)


def _ensure_trimcp_package_loaded() -> None:
    """Re-import ``trimcp`` after ``test_init_public_api`` purges ``sys.modules``."""
    import importlib
    import sys

    if "trimcp" in sys.modules:
        return
    importlib.import_module("trimcp")


def _restore_trimcp_temporal_datetime() -> None:
    """Undo tests that monkeypatch ``trimcp.temporal.datetime`` with a fixed clock."""
    import datetime as std_datetime

    import trimcp.temporal as temporal_mod

    temporal_mod.datetime = std_datetime.datetime


@pytest.fixture(autouse=True)
def _reset_trimcp_cfg_singleton_after_test() -> None:
    """Prevent order-dependent failures when tests patch ``trimcp.config.cfg``."""
    _restore_trimcp_cfg_from_env()
    _restore_trimcp_temporal_datetime()
    yield
    _restore_trimcp_cfg_from_env()
    _restore_trimcp_temporal_datetime()


def pytest_runtest_teardown(item: pytest.Item) -> None:
    """``test_init_public_api`` purges ``trimcp`` from ``sys.modules`` — restore for teardown hooks."""
    if "test_init_public_api" in item.nodeid:
        _ensure_trimcp_package_loaded()
        _restore_trimcp_cfg_from_env()
        _restore_trimcp_temporal_datetime()


@pytest.fixture(autouse=True)
def _reset_admin_state_engine_after_test() -> None:
    """Handlers read ``trimcp.admin_state.engine``; do not leak mocks across tests."""
    import trimcp.admin_state as admin_state

    admin_state.engine = None
    try:
        import admin_server as adm

        adm.engine = None
    except Exception:
        pass
    yield
    admin_state.engine = None
    try:
        import admin_server as adm

        adm.engine = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_server_engine_after_test() -> None:
    """``server.call_tool`` uses module-level ``server.engine``."""
    try:
        import server as srv
    except Exception:
        yield
        return

    original = srv.engine
    yield
    srv.engine = original


def _integration_pool_dsn() -> str | None:
    """DSN used by ``pg_pool`` (mutations + ``append_event`` integration tests).

    Operators may point CI at an isolated database via ``TRIMCP_INTEGRATION_PG_DSN``.
    Defaults to twelve-factor aliases so ``PG_DSN`` / ``DATABASE_URL`` work.
    """

    raw = (
        os.getenv("TRIMCP_INTEGRATION_PG_DSN")
        or os.getenv("PG_DSN")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    return raw or None


@pytest.fixture(autouse=True)
def _reset_signing_key_cache_after_test() -> None:
    """Reset the signing key module-level cache after each test.

    Prevents test-order dependencies by clearing ``_key_cache`` so each
    test starts with a fresh signing state.  Uses ``yield`` to run after
    the test body (teardown semantics).  Safe under ``pytest-xdist``
    because each worker has its own module namespace.
    """
    yield
    try:
        import trimcp.signing as signing_mod

        # _key_cache is a _SigningKeyCache(TTLCache) — clear() removes all
        # entries and __delitem__ zeros their MutableKeyBuffer.
        signing_mod._key_cache.clear()
    except Exception:
        return


# ---------------------------------------------------------------------------
# Integration Postgres (asyncpg pool + namespaces)
# Used by pytest.mark.integration tests; skips when Postgres is unreachable.
# ---------------------------------------------------------------------------


def _refresh_signing_when_decrypt_fails() -> bool:
    """When true, rotate signing keys if ``TRIMCP_MASTER_KEY`` cannot decrypt the active blob."""

    return os.getenv("TRIMCP_INTEGRATION_REFRESH_SIGNING_ON_DECRYPT_FAIL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _require_append_event_schema(pool: asyncpg.Pool) -> None:
    """``append_event`` / Merkle integration requires current ``event_log`` columns."""

    async with pool.acquire() as conn:
        ok = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM   information_schema.columns
                WHERE  table_schema = 'public'
                  AND  table_name = 'event_log'
                  AND  column_name = 'chain_hash'
            )
            """
        )
    if not ok:
        pytest.skip(
            "Postgres schema is missing public.event_log.chain_hash — "
            "apply the current trimcp/schema.sql before integration tests.",
        )


async def _ensure_active_signing_key(pool: asyncpg.Pool) -> None:
    """Ensure ``get_active_key`` succeeds (rotate when empty / optionally on decrypt mismatch)."""

    from trimcp.signing import (
        NoActiveSigningKeyError,
        SigningKeyDecryptionError,
        get_active_key,
        rotate_key,
    )

    async with pool.acquire() as conn:
        try:
            await get_active_key(conn)
            return
        except NoActiveSigningKeyError:
            await rotate_key(conn)
            return
        except SigningKeyDecryptionError:
            if _refresh_signing_when_decrypt_fails():
                await rotate_key(conn)
                return
            pytest.skip(
                "TRIMCP_MASTER_KEY does not decrypt signing_keys in this database. "
                "Use the deployment master key or set "
                "TRIMCP_INTEGRATION_REFRESH_SIGNING_ON_DECRYPT_FAIL=1 "
                "(rotates active signing keys — use only on disposable databases).",
            )


@pytest_asyncio.fixture
async def pg_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    dsn = _integration_pool_dsn()
    if not dsn:
        pytest.skip(
            "Integration tests need TRIMCP_INTEGRATION_PG_DSN, PG_DSN, or DATABASE_URL",
        )
    try:
        pool = await asyncpg.create_pool(
            dsn,
            min_size=1,
            max_size=6,
            command_timeout=60,
        )
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not reachable for integration tests: {exc}")

    try:
        await _require_append_event_schema(pool)
        await _ensure_active_signing_key(pool)
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def pg_admin_conn(pg_pool: asyncpg.Pool) -> AsyncGenerator[asyncpg.Connection, None]:
    """Single connection with the same role as ``pg_pool`` (compose default: ``mcp_user``)."""

    async with pg_pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture
async def pg_app_conn(
    pg_pool: asyncpg.Pool,
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Connection for catalog / WORM privilege probes.

    When ``PG_DSN_APP`` is set to a different DSN than the integration pool,
    checkout uses that role only. Otherwise reuses ``pg_pool`` — owner roles
    may pass ``UPDATE … WHERE FALSE``; those tests skip.
    """

    app_dsn = os.getenv("PG_DSN_APP", "").strip()
    primary = _integration_pool_dsn() or ""

    if not app_dsn or app_dsn == primary:
        from urllib.parse import urlparse, urlunparse

        from trimcp.config import cfg
        try:
            parsed = urlparse(primary)
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            app_pass = cfg.TRIMCP_APP_PASSWORD or "trimcp_app_secret"
            netloc = f"trimcp_app:{app_pass}@{netloc}"
            app_dsn = urlunparse(parsed._replace(netloc=netloc))
        except Exception:
            async with pg_pool.acquire() as conn:
                yield conn
            return

    try:
        app_pool = await asyncpg.create_pool(
            app_dsn,
            min_size=1,
            max_size=2,
            command_timeout=60,
        )
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"PG_DSN_APP not reachable: {exc}")
    try:
        async with app_pool.acquire() as conn:
            yield conn
    finally:
        await app_pool.close()


@pytest_asyncio.fixture
async def namespace_id(pg_pool: asyncpg.Pool) -> uuid.UUID:
    """Fresh namespace row for integration tests that need RLS / event_log scope."""

    slug = f"pytest-ns-{uuid.uuid4().hex}"
    async with pg_pool.acquire() as conn:
        ns = await conn.fetchval(
            "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id",
            slug,
        )
    assert ns is not None
    return ns


@pytest_asyncio.fixture
async def make_namespace(pg_pool: asyncpg.Pool):
    """Factory that inserts a new namespace and returns its id."""

    async def _make() -> uuid.UUID:
        slug = f"pytest-ns-{uuid.uuid4().hex}"
        async with pg_pool.acquire() as conn:
            ns = await conn.fetchval(
                "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id",
                slug,
            )
        assert ns is not None
        return ns

    return _make
