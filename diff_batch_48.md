# Diff Reference for Batch 48

```diff
diff --git a/RL.md b/RL.md
index 83310b0..0196984 100644
--- a/RL.md
+++ b/RL.md
@@ -55,8 +55,8 @@
 * [DONE] Batch 45 — Envelope-encryption subsystem (II.4a) [PASSED TAG]
 * [DONE] Batch 46 — Encrypt `episodes.raw_data` under the DEK + teach read paths (II.4b) [PASSED TAG]
 * [DONE] Batch 47 — `shred_memory` / `forget_subject` + deletion receipt (II.4c) [PASSED TAG]
-* [LOCKED] Batch 48 — DSAR capstone (VII.7) [NO TAG]
-* [LOCKED] Batch 49 — Verify PII-before-derivation on every write path (VII.1) [NO TAG]
+* [RUNNING] Batch 48 — DSAR capstone (VII.7) [NO TAG]
+* [OPEN] Batch 49 — Verify PII-before-derivation on every write path (VII.1) [NO TAG]
 * [LOCKED] Batch 50 — Scoped MongoDB accessor (VII.2) [NO TAG]
 * [LOCKED] Batch 51 — MinIO per-namespace isolation (VII.3) [NO TAG]
 * [DONE] Batch 52 — Auto-generated Settings panel (V.3) [PASSED TAG]
@@ -68,7 +68,7 @@
 * [DONE] Batch 58 — Reverse-orphan reconciliation sweep (R-B / VI.6a) [PASSED TAG]
 * [DONE] Batch 59 — RQ in-flight job recovery (R-C / VI.6a) [PASSED TAG]
 * [DONE] Batch 60 — Multicore: HTTP workers + RQ replicas + thread pinning (VI.5a) [PASSED TAG]
-* [LOCKED] Batch 61 — RAM: offload spaCy + NLI to a sidecar; container mem limits (VI.5b) [NO TAG]
+* [OPEN] Batch 61 — RAM: offload spaCy + NLI to a sidecar; container mem limits (VI.5b) [NO TAG]
 * [DONE] Batch 62 — Disk: datastore tuning + halfvec + tmpfs temp (VI.5c) [PASSED TAG]
 * [LOCKED] Batch 63 — Cross-encoder reranking (IV.1) [NO TAG]
 * [LOCKED] Batch 64 — Multi-vector / aspect embeddings (IV.2) [NO TAG]
diff --git a/nce/event_log.py b/nce/event_log.py
index 6d87e06..8c04c39 100644
--- a/nce/event_log.py
+++ b/nce/event_log.py
@@ -173,10 +173,7 @@ __all__ = [
 # ---------------------------------------------------------------------------
 
 # Tables expected to be append-only (no UPDATE/DELETE at the application role).
-_WORM_TABLES: tuple[str, ...] = (
-    "event_log",
-    "pii_redactions",
-)
+_WORM_TABLES: tuple[str, ...] = ("event_log",)
 
 
 async def verify_worm_on_table(conn: asyncpg.Connection, table_name: str) -> None:
diff --git a/nce/me_app.py b/nce/me_app.py
index a862451..054bf11 100644
--- a/nce/me_app.py
+++ b/nce/me_app.py
@@ -10,6 +10,7 @@ import logging
 import re
 import uuid
 from contextlib import asynccontextmanager
+from datetime import datetime, timezone
 from uuid import UUID
 
 from starlette.applications import Starlette
@@ -700,6 +701,323 @@ async def post_me_govern(request: Request) -> JSONResponse:
                 )
 
 
+async def get_me_dsar_export(request: Request) -> JSONResponse:
+    """GET /api/me/dsar/export
+
+    Retrieve all data associated with the subject (namespace and agent) including decrypted raw payloads.
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
+    # Enforce namespace matching if passed as query parameter
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
+    # Enforce agent matching if passed as query parameter
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
+    engine: NCEEngine = request.app.state.engine
+    async with scoped_pg_session(engine.pg_pool, ns_id) as conn:
+        # Fetch all memories (active and soft-deleted) for this agent
+        mem_rows = await conn.fetch(
+            """
+            SELECT m.id, m.namespace_id, m.agent_id, m.memory_type, m.assertion_type, m.payload_ref, 
+                   m.valid_from, m.valid_to, m.metadata, m.created_at, m.wrapped_dek,
+                   COALESCE(ms.salience_score, 1.0) AS salience,
+                   COALESCE(ms.updated_at, m.created_at) AS last_reinforced
+            FROM memories m
+            LEFT JOIN memory_salience ms ON m.id = ms.memory_id AND ms.agent_id = m.agent_id AND ms.namespace_id = m.namespace_id
+            WHERE m.agent_id = $1 AND m.namespace_id = $2
+            """,
+            ns_ctx.agent_id,
+            ns_id,
+        )
+
+        # Fetch active contradictions in the namespace
+        contra_rows = await conn.fetch(
+            """
+            SELECT id, memory_a_id, memory_b_id, confidence, detected_at, detection_path, signals, resolution
+            FROM contradictions
+            WHERE namespace_id = $1
+            """,
+            ns_id,
+        )
+
+    # Fetch MongoDB payloads
+    payload_refs = [r["payload_ref"] for r in mem_rows if r["payload_ref"]]
+
+    mongo_payloads = {}
+    if payload_refs and engine.mongo_client is not None:
+        from bson import ObjectId
+
+        db = engine.mongo_client.memory_archive
+        oids = []
+        for ref in payload_refs:
+            try:
+                oids.append(ObjectId(ref))
+            except Exception:
+                pass
+
+        cursor = db.episodes.find({"_id": {"$in": oids}})
+        async for doc in cursor:
+            mongo_payloads[str(doc["_id"])] = doc
+
+    # Map contradictions to memories
+    contra_map: dict[UUID, list[dict]] = {}
+    for c in contra_rows:
+        signals = c["signals"]
+        if isinstance(signals, str):
+            try:
+                signals = json.loads(signals)
+            except Exception:
+                signals = {}
+        contra_data = {
+            "id": str(c["id"]),
+            "memory_a_id": str(c["memory_a_id"]),
+            "memory_b_id": str(c["memory_b_id"]),
+            "confidence": float(c["confidence"]),
+            "detected_at": c["detected_at"].isoformat() if c["detected_at"] else None,
+            "detection_path": c["detection_path"],
+            "signals": signals,
+            "resolution": c["resolution"],
+        }
+        contra_map.setdefault(c["memory_a_id"], []).append(contra_data)
+        contra_map.setdefault(c["memory_b_id"], []).append(contra_data)
+
+    from nce.envelope import maybe_decrypt_raw_data
+
+    beliefs = []
+    for row in mem_rows:
+        mem_id = row["id"]
+        metadata = row["metadata"] or {}
+        if isinstance(metadata, str):
+            try:
+                metadata = json.loads(metadata)
+            except Exception:
+                metadata = {}
+        confidence = metadata.get("confidence", 1.0)
+        try:
+            confidence = float(confidence)
+        except (ValueError, TypeError):
+            confidence = 1.0
+
+        source = metadata.get("source", row["payload_ref"])
+
+        # Fetch and decrypt raw payload if present
+        raw_content = None
+        payload_ref = row["payload_ref"]
+        if payload_ref and payload_ref in mongo_payloads:
+            doc = mongo_payloads[payload_ref]
+            raw_data = doc.get("raw_data")
+            wrapped = row["wrapped_dek"]
+            if raw_data is not None:
+                try:
+                    raw_content = maybe_decrypt_raw_data(
+                        raw_data, bytes(wrapped) if wrapped is not None else None
+                    )
+                except Exception as e:
+                    log.warning("Failed to decrypt raw data for memory %s: %s", mem_id, e)
+                    raw_content = "[Decryption Error]"
+
+        beliefs.append(
+            {
+                "id": str(mem_id),
+                "namespace_id": str(row["namespace_id"]),
+                "agent_id": row["agent_id"],
+                "memory_type": row["memory_type"],
+                "assertion_type": row["assertion_type"],
+                "payload_ref": payload_ref,
+                "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
+                "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
+                "metadata": metadata,
+                "salience": float(row["salience"]),
+                "confidence": confidence,
+                "last_reinforced": row["last_reinforced"].isoformat()
+                if row["last_reinforced"]
+                else None,
+                "source": source,
+                "content": raw_content,
+                "contradictions": contra_map.get(mem_id, []),
+            }
+        )
+
+    return JSONResponse(
+        {
+            "namespace_id": str(ns_id),
+            "agent_id": ns_ctx.agent_id,
+            "exported_at": datetime.now(timezone.utc).isoformat(),
+            "beliefs": beliefs,
+        }
+    )
+
+
+async def post_me_dsar_erase(request: Request) -> JSONResponse:
+    """POST /api/me/dsar/erase
+
+    Provably erase all memories associated with the subject (namespace and agent) and return deletion receipts.
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
+    # Enforce namespace matching if passed as query parameter
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
+    # Enforce agent matching if passed as query parameter
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
+    engine: NCEEngine = request.app.state.engine
+
+    # Fetch all memories that are not yet shredded
+    async with scoped_pg_session(engine.pg_pool, ns_id) as conn:
+        rows = await conn.fetch(
+            """
+            SELECT id FROM memories 
+            WHERE agent_id = $1 AND namespace_id = $2 
+              AND (wrapped_dek IS NOT NULL OR content_fts IS NOT NULL OR embedding IS NOT NULL)
+            """,
+            ns_ctx.agent_id,
+            ns_id,
+        )
+
+    receipts = []
+    errors = []
+
+    for r in rows:
+        mem_id = str(r["id"])
+        try:
+            shred_result = await engine.shred_memory(mem_id, str(ns_id), ns_ctx.agent_id)
+            if shred_result.get("status") == "success":
+                receipts.append(shred_result.get("receipt"))
+            else:
+                errors.append({"memory_id": mem_id, "error": "unknown_shred_failure"})
+        except Exception as e:
+            log.error("Failed to shred memory %s in DSAR erasure: %s", mem_id, e)
+            errors.append({"memory_id": mem_id, "error": str(e)})
+
+    return JSONResponse(
+        {
+            "status": "success",
+            "namespace_id": str(ns_id),
+            "agent_id": ns_ctx.agent_id,
+            "erased_at": datetime.now(timezone.utc).isoformat(),
+            "shredded_count": len(receipts),
+            "receipts": receipts,
+            "errors": errors,
+        }
+    )
+
+
 app = Starlette(
     debug=False,
     lifespan=me_lifespan,
@@ -715,5 +1033,7 @@ app = Starlette(
         Route("/api/me/profile", endpoint=get_me_profile, methods=["GET"]),
         Route("/api/me/govern", endpoint=post_me_govern, methods=["POST"]),
         Route("/api/me/profile/govern", endpoint=post_me_govern, methods=["POST"]),
+        Route("/api/me/dsar/export", endpoint=get_me_dsar_export, methods=["GET"]),
+        Route("/api/me/dsar/erase", endpoint=post_me_dsar_erase, methods=["POST"]),
     ],
 )
diff --git a/nce/schema.sql b/nce/schema.sql
index 9b964bc..a6a2006 100644
--- a/nce/schema.sql
+++ b/nce/schema.sql
@@ -466,6 +466,23 @@ CREATE TABLE IF NOT EXISTS kg_node_embeddings_1 PARTITION OF kg_node_embeddings
 CREATE TABLE IF NOT EXISTS kg_node_embeddings_2 PARTITION OF kg_node_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 2);
 CREATE TABLE IF NOT EXISTS kg_node_embeddings_3 PARTITION OF kg_node_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 3);
 
+DO $$
+BEGIN
+    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
+        GRANT SELECT, INSERT, UPDATE, DELETE ON kg_node_embeddings TO nce_app;
+        GRANT SELECT, INSERT, UPDATE, DELETE ON kg_node_embeddings_0 TO nce_app;
+        GRANT SELECT, INSERT, UPDATE, DELETE ON kg_node_embeddings_1 TO nce_app;
+        GRANT SELECT, INSERT, UPDATE, DELETE ON kg_node_embeddings_2 TO nce_app;
+        GRANT SELECT, INSERT, UPDATE, DELETE ON kg_node_embeddings_3 TO nce_app;
+        
+        GRANT DELETE ON pii_redactions TO nce_app;
+        IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'pii_redactions_default') THEN
+            GRANT DELETE ON pii_redactions_default TO nce_app;
+        END IF;
+    END IF;
+END $$;
+
+
 CREATE TABLE IF NOT EXISTS embedding_migrations (
     id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
     namespace_id     UUID REFERENCES namespaces(id),
@@ -1187,7 +1204,7 @@ BEGIN
             t
         );
         EXECUTE format('REVOKE ALL ON TABLE public.%I FROM nce_app', t);
-        IF t IN ('event_log', 'pii_redactions') THEN
+        IF t IN ('event_log') THEN
             EXECUTE format(
                 'GRANT SELECT, INSERT ON TABLE public.%I TO nce_app',
                 t
diff --git a/tests/test_me_app.py b/tests/test_me_app.py
index 61c5518..e2453f8 100644
--- a/tests/test_me_app.py
+++ b/tests/test_me_app.py
@@ -77,6 +77,20 @@ def mock_engine(monkeypatch: pytest.MonkeyPatch) -> None:
         def pg_pool(self) -> Any:
             return None
 
+        @property
+        def mongo_client(self) -> Any:
+            return None
+
+        async def shred_memory(self, memory_id: str, namespace_id: str, agent_id: str) -> dict:
+            return {
+                "status": "success",
+                "receipt": {
+                    "memory_id": memory_id,
+                    "namespace_id": namespace_id,
+                    "dek_destroyed": True,
+                },
+            }
+
     monkeypatch.setattr("nce.me_app.NCEEngine", MockEngine)
 
 
@@ -293,6 +307,58 @@ class TestMeAppUnit:
         assert resp.json()["status"] == "success"
         assert resp.json()["action"] == "retract"
 
+    def test_get_dsar_export_success(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-abc"))
+        with TestClient(app) as client:
+            resp = client.get(
+                "/api/me/dsar/export",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 200
+        data = resp.json()
+        assert data["namespace_id"] == valid_ns_id
+        assert data["agent_id"] == "agent-abc"
+        assert "beliefs" in data
+        assert len(data["beliefs"]) == 1
+        assert data["beliefs"][0]["id"] == "11111111-2222-3333-4444-555555555555"
+
+    def test_get_dsar_export_unauthorized(self) -> None:
+        with TestClient(app) as client:
+            resp = client.get("/api/me/dsar/export")
+        assert resp.status_code == 401
+
+    def test_get_dsar_export_cross_namespace(self) -> None:
+        token = make_token(_base_payload(ns_id=valid_ns_id))
+        with TestClient(app) as client:
+            resp = client.get(
+                f"/api/me/dsar/export?namespace_id={valid_ns_id_b}",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 403
+
+    def test_get_dsar_export_cross_agent(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-alpha"))
+        with TestClient(app) as client:
+            resp = client.get(
+                "/api/me/dsar/export?agent_id=agent-beta",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 403
+
+    def test_post_dsar_erase_success(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-abc"))
+        with TestClient(app) as client:
+            resp = client.post(
+                "/api/me/dsar/erase",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 200
+        data = resp.json()
+        assert data["status"] == "success"
+        assert data["shredded_count"] == 1
+        assert len(data["receipts"]) == 1
+        assert data["receipts"][0]["dek_destroyed"] is True
+
 
 # ---------------------------------------------------------------------------
 # Integration Tests (Real Database)
@@ -549,3 +615,251 @@ class TestMeAppIntegration:
         finally:
             await engine.disconnect()
             app.state.engine = None
+
+    @pytest.mark.asyncio
+    async def test_me_app_dsar_flow_integration(
+        self,
+        setup_jwt_config: None,
+        pg_pool: asyncpg.Pool,
+        monkeypatch: pytest.MonkeyPatch,
+    ) -> None:
+        from bson import ObjectId
+        from nce import MemoryPayload
+        from nce.db_utils import scoped_pg_session
+        from nce.envelope import _DEK_PAYLOAD_PREFIX, DEKDecryptionError, decrypt_with_dek
+
+        # 1. Enable envelope encryption
+        monkeypatch.setattr(cfg, "NCE_ENVELOPE_ENCRYPTION_ENABLED", True, raising=False)
+
+        # 2. Connect engine as privileged user to store the memory
+        privileged_engine = NCEEngine()
+        await privileged_engine.connect()
+
+        try:
+            # Create a clean namespace and seed an active embedding model if not exists
+            ns_slug = f"test-ns-dsar-{int(time.time())}"
+            async with pg_pool.acquire() as conn:
+                res = await conn.fetchrow(
+                    "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id", ns_slug
+                )
+                ns_id = res["id"]
+
+                # Check active embedding models
+                existing = await conn.fetchval(
+                    "SELECT count(*) FROM embedding_models WHERE status IN ('active', 'migrating')"
+                )
+                if not existing:
+                    from nce import embeddings as _emb
+
+                    await conn.execute(
+                        "INSERT INTO embedding_models (name, dimension, status) "
+                        "VALUES ($1, $2, 'active') ON CONFLICT (name) DO UPDATE SET status = 'active'",
+                        _emb.MODEL_ID,
+                        _emb.VECTOR_DIM,
+                    )
+
+            # Store a memory with a plaintext sentinel
+            sentinel = "DSAR-FLOW-SENTINEL-" + uuid.uuid4().hex
+            content = f"{sentinel}. alice works at globex. email her at dsar@example.com."
+            sid = str(uuid.uuid4())
+            payload = MemoryPayload(
+                namespace_id=ns_id,
+                agent_id="agent-me",
+                content=content,
+                summary=content,
+                heavy_payload=content,
+                metadata={"user_id": sid, "session_id": sid},
+            )
+
+            res = await privileged_engine.store_memory(payload)
+            payload_ref = res["payload_ref"]
+            assert payload_ref
+
+            # Capture pre-shred facts
+            async with scoped_pg_session(pg_pool, str(ns_id)) as conn:
+                mem = await conn.fetchrow(
+                    "SELECT id, wrapped_dek, dek_key_id FROM memories WHERE payload_ref = $1",
+                    payload_ref,
+                )
+                assert mem is not None
+                assert mem["wrapped_dek"] is not None
+                memory_id = str(mem["id"])
+
+                emb_before = await conn.fetchval(
+                    "SELECT count(*) FROM memory_embeddings WHERE memory_id = $1::uuid", memory_id
+                )
+                assert emb_before > 0
+
+            # Capture MongoDB document ciphertext
+            db = privileged_engine.mongo_client.memory_archive
+            doc_before = await db.episodes.find_one({"_id": ObjectId(payload_ref)})
+            ciphertext_before = bytes(doc_before["raw_data"])
+            assert ciphertext_before.startswith(_DEK_PAYLOAD_PREFIX)
+
+            # Prime Redis cache
+            recalled = await privileged_engine.recall_recent(
+                str(ns_id), agent_id="agent-me", limit=1, user_id=sid, session_id=sid
+            )
+            assert recalled
+            redis_key = f"cache:{ns_id}:{sid}:{sid}"
+            assert await privileged_engine.redis_client.get(redis_key) is not None
+
+        finally:
+            await privileged_engine.disconnect()
+
+        # 3. Re-route config to nce_app
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
+        # 4. Connect a second engine as the unprivileged user
+        unprivileged_engine = NCEEngine()
+        await unprivileged_engine.connect()
+        app.state.engine = unprivileged_engine
+
+        try:
+            # 5. Call DSAR Export and verify the sentinel is decrypted
+            token = make_token(_base_payload(ns_id=str(ns_id), agent_id="agent-me"))
+            async with httpx.AsyncClient(
+                transport=httpx.ASGITransport(app=app), base_url="http://test"
+            ) as client:
+                resp_export = await client.get(
+                    "/api/me/dsar/export",
+                    headers={"Authorization": f"Bearer {token}"},
+                )
+                assert resp_export.status_code == 200
+                export_data = resp_export.json()
+                assert export_data["namespace_id"] == str(ns_id)
+                assert export_data["agent_id"] == "agent-me"
+                beliefs = export_data["beliefs"]
+                assert len(beliefs) >= 1
+                sentinel_belief = next(b for b in beliefs if b["id"] == memory_id)
+                assert sentinel_belief["content"] == content
+
+                # 6. Call DSAR Erase and verify success + receipts
+                resp_erase = await client.post(
+                    "/api/me/dsar/erase",
+                    headers={"Authorization": f"Bearer {token}"},
+                )
+                assert resp_erase.status_code == 200
+                erase_data = resp_erase.json()
+                assert erase_data["status"] == "success"
+                assert erase_data["shredded_count"] == 1
+                assert len(erase_data["receipts"]) == 1
+                receipt = erase_data["receipts"][0]
+                assert receipt["dek_destroyed"] is True
+                assert receipt["verified"] is True
+                assert receipt["worm_event"]["event_type"] == "memory_shredded"
+
+            # 7. Assert NO plaintext fragment survives in any store!
+            # PG: DEK destroyed, content_fts / embedding NULL
+            async with scoped_pg_session(pg_pool, str(ns_id)) as conn:
+                post = await conn.fetchrow(
+                    "SELECT wrapped_dek, dek_key_id, content_fts, embedding "
+                    "FROM memories WHERE id = $1::uuid",
+                    memory_id,
+                )
+            assert post["wrapped_dek"] is None
+            assert post["dek_key_id"] is None
+            assert post["content_fts"] is None
+            assert post["embedding"] is None
+
+            # DEK unrecoverable
+            with pytest.raises(DEKDecryptionError):
+                decrypt_with_dek(ciphertext_before, b"\x00" * 32)
+
+            # MongoDB doc tombstoned
+            db_unpriv = unprivileged_engine.mongo_client.memory_archive
+            doc_after = await db_unpriv.episodes.find_one({"_id": ObjectId(payload_ref)})
+            assert doc_after is not None
+            raw_after = doc_after.get("raw_data")
+            raw_after_bytes = (
+                bytes(raw_after) if isinstance(raw_after, (bytes, bytearray, memoryview)) else b""
+            )
+            assert sentinel.encode() not in raw_after_bytes
+            assert sentinel not in json.dumps(doc_after, default=str)
+
+            # memory_embeddings, kg_nodes, kg_edges, pii_redactions are deleted
+            async with scoped_pg_session(pg_pool, str(ns_id)) as conn:
+                emb_after = await conn.fetchval(
+                    "SELECT count(*) FROM memory_embeddings WHERE memory_id = $1::uuid", memory_id
+                )
+                kg_nodes_after = await conn.fetchval(
+                    "SELECT count(*) FROM kg_nodes WHERE payload_ref = $1", payload_ref
+                )
+                kg_edges_after = await conn.fetchval(
+                    "SELECT count(*) FROM kg_edges WHERE payload_ref = $1", payload_ref
+                )
+                pii_after = await conn.fetchval(
+                    "SELECT count(*) FROM pii_redactions WHERE memory_id = $1::uuid", memory_id
+                )
+            assert emb_after == 0
+            assert kg_nodes_after == 0
+            assert kg_edges_after == 0
+            assert pii_after == 0
+
+            # Redis cache key is purged
+            assert await unprivileged_engine.redis_client.get(redis_key) is None
+
+            # WORM event_log holds a signed, content-free memory_shredded event
+            async with scoped_pg_session(pg_pool, str(ns_id)) as conn:
+                ev = await conn.fetchrow(
+                    """
+                    SELECT params, signature, signature_key_id
+                    FROM event_log
+                    WHERE namespace_id = $1::uuid AND event_type = 'memory_shredded'
+                      AND params->>'memory_id' = $2
+                    ORDER BY occurred_at DESC LIMIT 1
+                    """,
+                    ns_id,
+                    memory_id,
+                )
+            assert ev is not None
+            assert ev["signature"] is not None
+            params = ev["params"]
+            if isinstance(params, str):
+                params = json.loads(params)
+            blob = json.dumps(params)
+            assert sentinel not in blob
+            assert params["memory_id"] == memory_id
+            assert "receipt_digest" in params
+            for forbidden in (
+                "raw_data",
+                "content",
+                "summary",
+                "heavy_payload",
+                "entities",
+                "triplets",
+            ):
+                assert forbidden not in params
+
+        finally:
+            await unprivileged_engine.disconnect()
+            app.state.engine = None
```
