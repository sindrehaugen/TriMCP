# Diff Reference for Batch 39

```diff
diff --git a/RL.md b/RL.md
index 08dcacc..fe082ac 100644
--- a/RL.md
+++ b/RL.md
@@ -46,7 +46,7 @@
 * [DONE] Batch 36 — `/reset`, `/reload`, `/pending` endpoints (V.1b) [PASSED TAG]
 * [DONE] Batch 37 — Honest Uncertainty in search results (II.1) [PASSED TAG]
 * [DONE] Batch 38 — Epistemic Receipts (II.2) [PASSED TAG]
-* [OPEN] Batch 39 — Subject-scoped `/api/me/*` surface (cross-cutting enabler) [NO TAG]
+* [RUNNING] Batch 39 — Subject-scoped `/api/me/*` surface (cross-cutting enabler) [RUNNING TAG]
 * [LOCKED] Batch 40 — Glass Profile endpoint + retract→ATMS (II.3) [NO TAG]
 * [LOCKED] Batch 41 — Accountable Federation: write `a2a_shared_query` + signed provenance (II.6) [NO TAG]
 * [LOCKED] Batch 42 — A2A security hardening (III.5) [NO TAG]
diff --git a/nce/me_app.py b/nce/me_app.py
new file mode 100644
index 0000000..fe56710
--- /dev/null
+++ b/nce/me_app.py
@@ -0,0 +1,155 @@
+"""
+nce/me_app.py
+
+Subject-scoped `/api/me/*` surface (consent-bound read/govern surface).
+Requires JWT Bearer tokens to authenticate.
+"""
+
+from __future__ import annotations
+
+import logging
+from contextlib import asynccontextmanager
+from uuid import UUID
+
+from starlette.applications import Starlette
+from starlette.middleware import Middleware
+from starlette.requests import Request
+from starlette.responses import JSONResponse
+from starlette.routing import Route
+
+from nce.auth import NamespaceContext
+from nce.db_utils import scoped_pg_session
+from nce.jwt_auth import JWTAuthMiddleware
+from nce.orchestrator import NCEEngine
+
+log = logging.getLogger("nce.me_app")
+
+
+@asynccontextmanager
+async def me_lifespan(app: Starlette):
+    """Lifespan context manager for me_app.
+
+    Initializes and manages the lifetime of NCEEngine.
+    """
+    engine = NCEEngine()
+    await engine.connect()
+    app.state.engine = engine
+    log.info("Me API: NCEEngine connected.")
+    try:
+        yield
+    finally:
+        await engine.disconnect()
+        app.state.engine = None
+        log.info("Me API: NCEEngine disconnected.")
+
+
+async def get_me_memories(request: Request) -> JSONResponse:
+    """GET /api/me/memories
+
+    Retrieve memories scoped to the caller's namespace and agent.
+    Optionally filters or checks namespace_id / agent_id parameters.
+    """
+    ns_ctx: NamespaceContext | None = getattr(request.state, "namespace_ctx", None)
+    if not ns_ctx or ns_ctx.namespace_id is None:
+        return JSONResponse(
+            {
+                "jsonrpc": "2.0",
+                "error": {
+                    "code": -32005,
+                    "message": "Unauthorized",
+                    "data": {"reason": "missing_namespace_context"},
+                },
+                "id": None,
+            },
+            status_code=401,
+        )
+
+    ns_id: UUID = ns_ctx.namespace_id
+
+    # 1. Enforce that if a namespace_id query param is supplied, it must match the token's namespace
+    query_ns = request.query_params.get("namespace_id")
+    if query_ns:
+        try:
+            query_ns_uuid = UUID(str(query_ns).strip())
+        except ValueError:
+            return JSONResponse(
+                {
+                    "jsonrpc": "2.0",
+                    "error": {
+                        "code": -32007,
+                        "message": "Invalid namespace_id format",
+                        "data": {"reason": "invalid_namespace_format"},
+                    },
+                    "id": None,
+                },
+                status_code=400,
+            )
+        if query_ns_uuid != ns_id:
+            return JSONResponse(
+                {
+                    "jsonrpc": "2.0",
+                    "error": {
+                        "code": -32005,
+                        "message": "Forbidden",
+                        "data": {"reason": "cross-namespace request is denied"},
+                    },
+                    "id": None,
+                },
+                status_code=403,
+            )
+
+    # 2. Enforce that if an agent_id query param is supplied, it must match the token's agent
+    query_agent = request.query_params.get("agent_id")
+    if query_agent and query_agent.strip() != ns_ctx.agent_id:
+        return JSONResponse(
+            {
+                "jsonrpc": "2.0",
+                "error": {
+                    "code": -32005,
+                    "message": "Forbidden",
+                    "data": {"reason": "cross-agent request is denied"},
+                },
+                "id": None,
+            },
+            status_code=403,
+        )
+
+    # 3. Retrieve database connection via scoped_pg_session and execute RLS-scoped query
+    engine: NCEEngine = request.app.state.engine
+    async with scoped_pg_session(engine.pg_pool, ns_id) as conn:
+        rows = await conn.fetch(
+            "SELECT id, namespace_id, agent_id, memory_type, assertion_type, payload_ref, valid_from, valid_to "
+            "FROM memories WHERE agent_id = $1",
+            ns_ctx.agent_id,
+        )
+        return JSONResponse(
+            [
+                {
+                    "id": str(row["id"]),
+                    "namespace_id": str(row["namespace_id"]),
+                    "agent_id": row["agent_id"],
+                    "memory_type": row["memory_type"],
+                    "assertion_type": row["assertion_type"],
+                    "payload_ref": row["payload_ref"],
+                    "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
+                    "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
+                }
+                for row in rows
+            ]
+        )
+
+
+app = Starlette(
+    debug=False,
+    lifespan=me_lifespan,
+    middleware=[
+        Middleware(
+            JWTAuthMiddleware,
+            protected_prefix="/api/me",
+            expected_audience=None,
+        ),
+    ],
+    routes=[
+        Route("/api/me/memories", endpoint=get_me_memories, methods=["GET"]),
+    ],
+)
diff --git a/tests/test_me_app.py b/tests/test_me_app.py
new file mode 100644
index 0000000..97c62ac
--- /dev/null
+++ b/tests/test_me_app.py
@@ -0,0 +1,287 @@
+"""
+tests/test_me_app.py
+
+Unit and integration tests for the subject-scoped `/api/me/*` surface.
+"""
+
+from __future__ import annotations
+
+import os
+import time
+from contextlib import asynccontextmanager
+from datetime import datetime, timezone
+from typing import Any
+from urllib.parse import urlparse, urlunparse
+from uuid import UUID
+
+import asyncpg
+import httpx
+import jwt
+import pytest
+from nce.config import cfg
+from nce.me_app import app
+from nce.orchestrator import NCEEngine
+from starlette.testclient import TestClient
+
+hs256_secret = "test-secret-for-unit-tests"
+valid_ns_id = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
+valid_ns_id_b = "11112222-3333-4444-5555-666666666666"
+far_future = int(time.time()) + 3600
+past_timestamp = int(time.time()) - 3600
+
+pytestmark = pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
+
+
+def make_token(
+    payload: dict[str, Any],
+    *,
+    secret: str = hs256_secret,
+    algorithm: str = "HS256",
+) -> str:
+    return jwt.encode(payload, secret, algorithm=algorithm)
+
+
+def _base_payload(ns_id: str = valid_ns_id, **overrides: Any) -> dict[str, Any]:
+    data: dict[str, Any] = {
+        "namespace_id": ns_id,
+        "exp": far_future,
+    }
+    data.update(overrides)
+    return data
+
+
+@pytest.fixture
+def hs256_cfg(monkeypatch: pytest.MonkeyPatch) -> None:
+    monkeypatch.setattr(cfg, "NCE_JWT_SECRET", hs256_secret)
+    monkeypatch.setattr(cfg, "NCE_JWT_ALGORITHM", "HS256")
+    monkeypatch.setattr(cfg, "NCE_JWT_ISSUER", "")
+    monkeypatch.setattr(cfg, "NCE_JWT_AUDIENCE", "")
+    monkeypatch.setattr(cfg, "IS_PROD", False)
+    monkeypatch.setattr(cfg, "NCE_JWT_LEEWAY_SECONDS", 0)
+    monkeypatch.setattr(cfg, "NCE_JWT_PUBLIC_KEY", "")
+
+
+@pytest.fixture
+def mock_engine(monkeypatch: pytest.MonkeyPatch) -> None:
+    class MockEngine:
+        async def connect(self) -> None:
+            pass
+
+        async def disconnect(self) -> None:
+            pass
+
+        @property
+        def pg_pool(self) -> Any:
+            return None
+
+    monkeypatch.setattr("nce.me_app.NCEEngine", MockEngine)
+
+
+# ---------------------------------------------------------------------------
+# Unit Tests (Mocked DB)
+# ---------------------------------------------------------------------------
+
+
+class TestMeAppUnit:
+    @pytest.fixture(autouse=True)
+    def setup_mocks(
+        self,
+        hs256_cfg: None,
+        mock_engine: None,
+        monkeypatch: pytest.MonkeyPatch,
+    ) -> None:
+        @asynccontextmanager
+        async def mock_scoped_pg_session(pool: Any, namespace_id: str | UUID):
+            class MockConn:
+                async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
+                    return [
+                        {
+                            "id": UUID("11111111-2222-3333-4444-555555555555"),
+                            "namespace_id": UUID(str(namespace_id)),
+                            "agent_id": args[0] if args else "default",
+                            "memory_type": "episodic",
+                            "assertion_type": "fact",
+                            "payload_ref": "000000000000000000000001",
+                            "valid_from": datetime.now(timezone.utc),
+                            "valid_to": None,
+                        }
+                    ]
+
+            yield MockConn()
+
+        monkeypatch.setattr("nce.me_app.scoped_pg_session", mock_scoped_pg_session)
+
+    def test_unauthorized_missing_token(self) -> None:
+        with TestClient(app) as client:
+            resp = client.get("/api/me/memories")
+        assert resp.status_code == 401
+        assert resp.json()["error"]["code"] == -32005
+
+    def test_authorized_retrieves_memories(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-abc"))
+        with TestClient(app) as client:
+            resp = client.get(
+                "/api/me/memories",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 200
+        data = resp.json()
+        assert len(data) == 1
+        assert data[0]["namespace_id"] == valid_ns_id
+        assert data[0]["agent_id"] == "agent-abc"
+
+    def test_cross_namespace_rejected(self) -> None:
+        token = make_token(_base_payload(ns_id=valid_ns_id))
+        with TestClient(app) as client:
+            resp = client.get(
+                f"/api/me/memories?namespace_id={valid_ns_id_b}",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 403
+        assert resp.json()["error"]["data"]["reason"] == "cross-namespace request is denied"
+
+    def test_matching_namespace_param_accepted(self) -> None:
+        token = make_token(_base_payload(ns_id=valid_ns_id))
+        with TestClient(app) as client:
+            resp = client.get(
+                f"/api/me/memories?namespace_id={valid_ns_id}",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 200
+        assert resp.json()[0]["namespace_id"] == valid_ns_id
+
+    def test_invalid_namespace_uuid_rejected(self) -> None:
+        token = make_token(_base_payload())
+        with TestClient(app) as client:
+            resp = client.get(
+                "/api/me/memories?namespace_id=not-a-valid-uuid",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 400
+        assert resp.json()["error"]["code"] == -32007
+
+    def test_cross_agent_rejected(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-alpha"))
+        with TestClient(app) as client:
+            resp = client.get(
+                "/api/me/memories?agent_id=agent-beta",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 403
+        assert resp.json()["error"]["data"]["reason"] == "cross-agent request is denied"
+
+
+# ---------------------------------------------------------------------------
+# Integration Tests (Real Database)
+# ---------------------------------------------------------------------------
+
+
+@pytest.mark.integration
+class TestMeAppIntegration:
+    @pytest.fixture
+    def setup_jwt_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
+        monkeypatch.setattr(cfg, "NCE_JWT_SECRET", hs256_secret)
+        monkeypatch.setattr(cfg, "NCE_JWT_ALGORITHM", "HS256")
+        monkeypatch.setattr(cfg, "NCE_JWT_ISSUER", "")
+        monkeypatch.setattr(cfg, "NCE_JWT_AUDIENCE", "")
+        monkeypatch.setattr(cfg, "IS_PROD", False)
+        monkeypatch.setattr(cfg, "NCE_JWT_LEEWAY_SECONDS", 0)
+        monkeypatch.setattr(cfg, "NCE_JWT_PUBLIC_KEY", "")
+
+    @pytest.mark.asyncio
+    async def test_scoped_pg_session_isolation_end_to_end(
+        self,
+        setup_jwt_config: None,
+        pg_pool: asyncpg.Pool,
+        monkeypatch: pytest.MonkeyPatch,
+    ) -> None:
+        # We run the application against the real database using HTTPX AsyncClient
+        # to prevent loop mismatch between TestClient and asyncpg.
+
+        # 1. Determine the app_dsn (connecting as nce_app)
+        app_dsn = os.getenv("PG_DSN_APP", "").strip()
+        primary = (
+            os.getenv("NCE_INTEGRATION_PG_DSN")
+            or os.getenv("PG_DSN")
+            or os.getenv("DATABASE_URL")
+            or "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta"
+        ).strip()
+
+        if not app_dsn or app_dsn == primary:
+            try:
+                parsed = urlparse(primary)
+                netloc = parsed.hostname or ""
+                if parsed.port:
+                    netloc = f"{netloc}:{parsed.port}"
+                app_pass = cfg.NCE_APP_PASSWORD or "nce_app_secret"
+                netloc = f"nce_app:{app_pass}@{netloc}"
+                app_dsn = urlunparse(parsed._replace(netloc=netloc))
+            except Exception:
+                app_dsn = primary
+
+        # 2. Patch cfg.PG_DSN and connect/setup methods of NCEEngine to use nce_app cleanly
+        monkeypatch.setattr(cfg, "PG_DSN", app_dsn)
+
+        async def mock_noop(*args, **kwargs):
+            pass
+
+        monkeypatch.setattr(NCEEngine, "_init_pg_schema", mock_noop)
+        monkeypatch.setattr(NCEEngine, "_apply_pg_migrations", mock_noop)
+        monkeypatch.setattr(NCEEngine, "_verify_worm_enforcement", mock_noop)
+        monkeypatch.setattr(NCEEngine, "_verify_rls_enforcement", mock_noop)
+        monkeypatch.setattr(NCEEngine, "_check_global_legacy_warning", mock_noop)
+
+        engine = NCEEngine()
+        await engine.connect()
+        app.state.engine = engine
+
+        try:
+            async with httpx.AsyncClient(
+                transport=httpx.ASGITransport(app=app), base_url="http://test"
+            ) as client:
+                # 1. Create two separate namespaces in the database using the privileged pg_pool
+                ns_slug_a = f"test-ns-a-{int(time.time())}"
+                ns_slug_b = f"test-ns-b-{int(time.time())}"
+                async with pg_pool.acquire() as conn:
+                    res_a = await conn.fetchrow(
+                        "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id", ns_slug_a
+                    )
+                    res_b = await conn.fetchrow(
+                        "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id", ns_slug_b
+                    )
+                    ns_id_a = res_a["id"]
+                    ns_id_b = res_b["id"]
+
+                    # 2. Insert memories for namespace A and namespace B
+                    await conn.execute(
+                        "INSERT INTO memories (id, namespace_id, agent_id, payload_ref) "
+                        "VALUES (gen_random_uuid(), $1, 'agent-me', '0000000000000000000000aa')",
+                        ns_id_a,
+                    )
+                    await conn.execute(
+                        "INSERT INTO memories (id, namespace_id, agent_id, payload_ref) "
+                        "VALUES (gen_random_uuid(), $1, 'agent-me', '0000000000000000000000bb')",
+                        ns_id_b,
+                    )
+
+                # 3. Request namespace A memories using token A
+                token_a = make_token(_base_payload(ns_id=str(ns_id_a), agent_id="agent-me"))
+                resp = await client.get(
+                    "/api/me/memories",
+                    headers={"Authorization": f"Bearer {token_a}"},
+                )
+                assert resp.status_code == 200
+                memories_a = resp.json()
+                assert len(memories_a) == 1
+                assert memories_a[0]["namespace_id"] == str(ns_id_a)
+                assert memories_a[0]["payload_ref"] == "0000000000000000000000aa"
+
+                # 4. Attempt to query namespace B via namespace_id param using token A (should fail with 403)
+                resp_cross = await client.get(
+                    f"/api/me/memories?namespace_id={ns_id_b}",
+                    headers={"Authorization": f"Bearer {token_a}"},
+                )
+                assert resp_cross.status_code == 403
+        finally:
+            await engine.disconnect()
+            app.state.engine = None
```
