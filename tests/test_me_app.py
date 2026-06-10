"""
tests/test_me_app.py

Unit and integration tests for the subject-scoped `/api/me/*` surface.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock
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
                    if "contradictions" in query.lower():
                        return [
                            {
                                "id": UUID("22222222-3333-4444-5555-666666666666"),
                                "memory_a_id": UUID("11111111-2222-3333-4444-555555555555"),
                                "memory_b_id": UUID("99999999-8888-7777-6666-555555555555"),
                                "confidence": 0.85,
                                "detected_at": datetime.now(timezone.utc),
                                "detection_path": "manual",
                                "signals": "{}",
                                "resolution": None,
                            }
                        ]
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
                            "metadata": {"confidence": 0.95, "source": "test_src"},
                            "created_at": datetime.now(timezone.utc),
                            "salience": 1.0,
                            "last_reinforced": datetime.now(timezone.utc),
                        }
                    ]

                async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
                    if "memories" in query.lower():
                        return {
                            "id": args[0],
                            "assertion_type": "fact",
                            "payload_ref": "000000000000000000000001",
                            "metadata": {"confidence": 0.95, "source": "test_src"},
                        }
                    return None

                async def execute(self, query: str, *args: Any) -> str:
                    return "UPDATE 1"

                def transaction(self) -> Any:
                    @asynccontextmanager
                    async def mock_tx():
                        yield

                    return mock_tx()

            yield MockConn()

        monkeypatch.setattr("nce.me_app.scoped_pg_session", mock_scoped_pg_session)
        monkeypatch.setattr("nce.me_app.append_event", AsyncMock(return_value=None))

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

    def test_get_profile_success(self) -> None:
        token = make_token(_base_payload(agent_id="agent-abc"))
        with TestClient(app) as client:
            resp = client.get(
                "/api/me/profile",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["namespace_id"] == valid_ns_id
        assert data[0]["agent_id"] == "agent-abc"
        assert data[0]["salience"] == 1.0
        assert data[0]["confidence"] == 0.95
        assert len(data[0]["contradictions"]) == 1
        assert data[0]["contradictions"][0]["memory_a_id"] == "11111111-2222-3333-4444-555555555555"

    def test_post_govern_edit_success(self) -> None:
        token = make_token(_base_payload(agent_id="agent-abc"))
        with TestClient(app) as client:
            resp = client.post(
                "/api/me/govern",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "memory_id": "11111111-2222-3333-4444-555555555555",
                    "action": "edit",
                    "assertion_type": "opinion",
                    "payload_ref": "0000000000000000000000aa",
                    "metadata": {"info": "edited"},
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["action"] == "edit"

    def test_post_govern_downweight_success(self) -> None:
        token = make_token(_base_payload(agent_id="agent-abc"))
        with TestClient(app) as client:
            resp = client.post(
                "/api/me/govern",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "memory_id": "11111111-2222-3333-4444-555555555555",
                    "action": "downweight",
                    "factor": 0.3,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["action"] == "downweight"

    def test_post_govern_pin_success(self) -> None:
        token = make_token(_base_payload(agent_id="agent-abc"))
        with TestClient(app) as client:
            resp = client.post(
                "/api/me/govern",
                headers={"Authorization": f"Bearer {token}"},
                json={"memory_id": "11111111-2222-3333-4444-555555555555", "action": "pin"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["action"] == "pin"

    def test_post_govern_retract_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Mock retract specific ATMS helper imports
        monkeypatch.setattr(
            "nce.me_app.evaluate_atms_intervention",
            AsyncMock(return_value={"11111111-2222-3333-4444-555555555555"}),
        )
        monkeypatch.setattr("nce.me_app.persist_atms_invalidation", AsyncMock(return_value=1))

        token = make_token(_base_payload(agent_id="agent-abc"))
        with TestClient(app) as client:
            resp = client.post(
                "/api/me/govern",
                headers={"Authorization": f"Bearer {token}"},
                json={"memory_id": "11111111-2222-3333-4444-555555555555", "action": "retract"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["action"] == "retract"


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

    @pytest.mark.asyncio
    async def test_me_app_profile_and_retract_integration(
        self,
        setup_jwt_config: None,
        pg_pool: asyncpg.Pool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # We run the application against the real database using HTTPX AsyncClient

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
                # 1. Create a namespace in the database
                ns_slug = f"test-ns-profile-{int(time.time())}"
                async with pg_pool.acquire() as conn:
                    res = await conn.fetchrow(
                        "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id", ns_slug
                    )
                    ns_id = res["id"]

                    memory_id_a = uuid.uuid4()
                    memory_id_b = uuid.uuid4()

                    # Insert memory A (independent)
                    await conn.execute(
                        "INSERT INTO memories (id, namespace_id, agent_id, payload_ref, metadata) "
                        "VALUES ($1, $2, 'agent-me', '0000000000000000000000aa', '{}'::jsonb)",
                        memory_id_a,
                        ns_id,
                    )

                    # Insert memory B derived from memory A
                    await conn.execute(
                        "INSERT INTO memories (id, namespace_id, agent_id, payload_ref, metadata, derived_from) "
                        "VALUES ($1, $2, 'agent-me', '0000000000000000000000bb', '{}'::jsonb, $3::jsonb)",
                        memory_id_b,
                        ns_id,
                        json.dumps([str(memory_id_a)]),
                    )

                token = make_token(_base_payload(ns_id=str(ns_id), agent_id="agent-me"))

                # 2. GET profile and check both memories exist
                resp = await client.get(
                    "/api/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                profile = resp.json()
                assert len(profile) == 2

                # Check IDs are present
                profile_ids = {p["id"] for p in profile}
                assert str(memory_id_a) in profile_ids
                assert str(memory_id_b) in profile_ids

                # 3. Post a govern downweight request
                resp_down = await client.post(
                    "/api/me/govern",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"memory_id": str(memory_id_a), "action": "downweight", "factor": 0.25},
                )
                assert resp_down.status_code == 200

                # 4. Post a govern pin request
                resp_pin = await client.post(
                    "/api/me/govern",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"memory_id": str(memory_id_a), "action": "pin"},
                )
                assert resp_pin.status_code == 200

                # 5. GET profile again to verify pinning
                resp_prof_2 = await client.get(
                    "/api/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp_prof_2.status_code == 200
                profile_2 = resp_prof_2.json()
                mem_a_data = next(p for p in profile_2 if p["id"] == str(memory_id_a))
                assert mem_a_data["salience"] == 1.0
                assert mem_a_data["metadata"].get("pinned") is True

                # 6. Retract memory A and ensure memory B (derived) cascades and gets soft-deleted too
                resp_retract = await client.post(
                    "/api/me/govern",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"memory_id": str(memory_id_a), "action": "retract"},
                )
                assert resp_retract.status_code == 200
                assert resp_retract.json()["status"] == "success"

                # 7. GET profile again and verify it is empty
                resp_prof_3 = await client.get(
                    "/api/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp_prof_3.status_code == 200
                assert len(resp_prof_3.json()) == 0
        finally:
            await engine.disconnect()
            app.state.engine = None
