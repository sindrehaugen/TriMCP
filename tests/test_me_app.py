"""
tests/test_me_app.py

Unit and integration tests for the subject-scoped `/api/me/*` surface.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

import asyncpg
import httpx
import jwt
import pytest
from nce.config import cfg
from nce.me_app import app
from nce.orchestrator import NCEEngine
from starlette.testclient import TestClient

hs256_secret = "test-secret-for-unit-tests"
valid_ns_id = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
valid_ns_id_b = "11112222-3333-4444-5555-666666666666"
far_future = int(time.time()) + 3600
past_timestamp = int(time.time()) - 3600

pytestmark = pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")


def make_token(
    payload: dict[str, Any],
    *,
    secret: str = hs256_secret,
    algorithm: str = "HS256",
) -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


def _base_payload(ns_id: str = valid_ns_id, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "namespace_id": ns_id,
        "exp": far_future,
    }
    data.update(overrides)
    return data


@pytest.fixture
def hs256_cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "NCE_JWT_SECRET", hs256_secret)
    monkeypatch.setattr(cfg, "NCE_JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(cfg, "NCE_JWT_ISSUER", "")
    monkeypatch.setattr(cfg, "NCE_JWT_AUDIENCE", "")
    monkeypatch.setattr(cfg, "IS_PROD", False)
    monkeypatch.setattr(cfg, "NCE_JWT_LEEWAY_SECONDS", 0)
    monkeypatch.setattr(cfg, "NCE_JWT_PUBLIC_KEY", "")


@pytest.fixture
def mock_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockEngine:
        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        @property
        def pg_pool(self) -> Any:
            return None

    monkeypatch.setattr("nce.me_app.NCEEngine", MockEngine)


# ---------------------------------------------------------------------------
# Unit Tests (Mocked DB)
# ---------------------------------------------------------------------------


class TestMeAppUnit:
    @pytest.fixture(autouse=True)
    def setup_mocks(
        self,
        hs256_cfg: None,
        mock_engine: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        @asynccontextmanager
        async def mock_scoped_pg_session(pool: Any, namespace_id: str | UUID):
            class MockConn:
                async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
                    return [
                        {
                            "id": UUID("11111111-2222-3333-4444-555555555555"),
                            "namespace_id": UUID(str(namespace_id)),
                            "agent_id": args[0] if args else "default",
                            "memory_type": "episodic",
                            "assertion_type": "fact",
                            "payload_ref": "000000000000000000000001",
                            "valid_from": datetime.now(timezone.utc),
                            "valid_to": None,
                        }
                    ]

            yield MockConn()

        monkeypatch.setattr("nce.me_app.scoped_pg_session", mock_scoped_pg_session)

    def test_unauthorized_missing_token(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/me/memories")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == -32005

    def test_authorized_retrieves_memories(self) -> None:
        token = make_token(_base_payload(agent_id="agent-abc"))
        with TestClient(app) as client:
            resp = client.get(
                "/api/me/memories",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["namespace_id"] == valid_ns_id
        assert data[0]["agent_id"] == "agent-abc"

    def test_cross_namespace_rejected(self) -> None:
        token = make_token(_base_payload(ns_id=valid_ns_id))
        with TestClient(app) as client:
            resp = client.get(
                f"/api/me/memories?namespace_id={valid_ns_id_b}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
        assert resp.json()["error"]["data"]["reason"] == "cross-namespace request is denied"

    def test_matching_namespace_param_accepted(self) -> None:
        token = make_token(_base_payload(ns_id=valid_ns_id))
        with TestClient(app) as client:
            resp = client.get(
                f"/api/me/memories?namespace_id={valid_ns_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json()[0]["namespace_id"] == valid_ns_id

    def test_invalid_namespace_uuid_rejected(self) -> None:
        token = make_token(_base_payload())
        with TestClient(app) as client:
            resp = client.get(
                "/api/me/memories?namespace_id=not-a-valid-uuid",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == -32007

    def test_cross_agent_rejected(self) -> None:
        token = make_token(_base_payload(agent_id="agent-alpha"))
        with TestClient(app) as client:
            resp = client.get(
                "/api/me/memories?agent_id=agent-beta",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
        assert resp.json()["error"]["data"]["reason"] == "cross-agent request is denied"


# ---------------------------------------------------------------------------
# Integration Tests (Real Database)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMeAppIntegration:
    @pytest.fixture
    def setup_jwt_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cfg, "NCE_JWT_SECRET", hs256_secret)
        monkeypatch.setattr(cfg, "NCE_JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(cfg, "NCE_JWT_ISSUER", "")
        monkeypatch.setattr(cfg, "NCE_JWT_AUDIENCE", "")
        monkeypatch.setattr(cfg, "IS_PROD", False)
        monkeypatch.setattr(cfg, "NCE_JWT_LEEWAY_SECONDS", 0)
        monkeypatch.setattr(cfg, "NCE_JWT_PUBLIC_KEY", "")

    @pytest.mark.asyncio
    async def test_scoped_pg_session_isolation_end_to_end(
        self,
        setup_jwt_config: None,
        pg_pool: asyncpg.Pool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # We run the application against the real database using HTTPX AsyncClient
        # to prevent loop mismatch between TestClient and asyncpg.

        # 1. Determine the app_dsn (connecting as nce_app)
        app_dsn = os.getenv("PG_DSN_APP", "").strip()
        primary = (
            os.getenv("NCE_INTEGRATION_PG_DSN")
            or os.getenv("PG_DSN")
            or os.getenv("DATABASE_URL")
            or "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta"
        ).strip()

        if not app_dsn or app_dsn == primary:
            try:
                parsed = urlparse(primary)
                netloc = parsed.hostname or ""
                if parsed.port:
                    netloc = f"{netloc}:{parsed.port}"
                app_pass = cfg.NCE_APP_PASSWORD or "nce_app_secret"
                netloc = f"nce_app:{app_pass}@{netloc}"
                app_dsn = urlunparse(parsed._replace(netloc=netloc))
            except Exception:
                app_dsn = primary

        # 2. Patch cfg.PG_DSN and connect/setup methods of NCEEngine to use nce_app cleanly
        monkeypatch.setattr(cfg, "PG_DSN", app_dsn)

        async def mock_noop(*args, **kwargs):
            pass

        monkeypatch.setattr(NCEEngine, "_init_pg_schema", mock_noop)
        monkeypatch.setattr(NCEEngine, "_apply_pg_migrations", mock_noop)
        monkeypatch.setattr(NCEEngine, "_verify_worm_enforcement", mock_noop)
        monkeypatch.setattr(NCEEngine, "_verify_rls_enforcement", mock_noop)
        monkeypatch.setattr(NCEEngine, "_check_global_legacy_warning", mock_noop)

        engine = NCEEngine()
        await engine.connect()
        app.state.engine = engine

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                # 1. Create two separate namespaces in the database using the privileged pg_pool
                ns_slug_a = f"test-ns-a-{int(time.time())}"
                ns_slug_b = f"test-ns-b-{int(time.time())}"
                async with pg_pool.acquire() as conn:
                    res_a = await conn.fetchrow(
                        "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id", ns_slug_a
                    )
                    res_b = await conn.fetchrow(
                        "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id", ns_slug_b
                    )
                    ns_id_a = res_a["id"]
                    ns_id_b = res_b["id"]

                    # 2. Insert memories for namespace A and namespace B
                    await conn.execute(
                        "INSERT INTO memories (id, namespace_id, agent_id, payload_ref) "
                        "VALUES (gen_random_uuid(), $1, 'agent-me', '0000000000000000000000aa')",
                        ns_id_a,
                    )
                    await conn.execute(
                        "INSERT INTO memories (id, namespace_id, agent_id, payload_ref) "
                        "VALUES (gen_random_uuid(), $1, 'agent-me', '0000000000000000000000bb')",
                        ns_id_b,
                    )

                # 3. Request namespace A memories using token A
                token_a = make_token(_base_payload(ns_id=str(ns_id_a), agent_id="agent-me"))
                resp = await client.get(
                    "/api/me/memories",
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                assert resp.status_code == 200
                memories_a = resp.json()
                assert len(memories_a) == 1
                assert memories_a[0]["namespace_id"] == str(ns_id_a)
                assert memories_a[0]["payload_ref"] == "0000000000000000000000aa"

                # 4. Attempt to query namespace B via namespace_id param using token A (should fail with 403)
                resp_cross = await client.get(
                    f"/api/me/memories?namespace_id={ns_id_b}",
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                assert resp_cross.status_code == 403
        finally:
            await engine.disconnect()
            app.state.engine = None
