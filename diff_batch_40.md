# Diff Reference for Batch 40

```diff
diff --git a/RL.md b/RL.md
index 3505793..bb69f38 100644
--- a/RL.md
+++ b/RL.md
@@ -47,7 +47,7 @@
 * [DONE] Batch 37 — Honest Uncertainty in search results (II.1) [PASSED TAG]
 * [DONE] Batch 38 — Epistemic Receipts (II.2) [PASSED TAG]
 * [DONE] Batch 39 — Subject-scoped `/api/me/*` surface (cross-cutting enabler) [PASSED TAG]
-* [OPEN] Batch 40 — Glass Profile endpoint + retract→ATMS (II.3) [NO TAG]
+* [RUNNING] Batch 40 — Glass Profile endpoint + retract→ATMS (II.3) [WAITING TAG]
 * [LOCKED] Batch 41 — Accountable Federation: write `a2a_shared_query` + signed provenance (II.6) [NO TAG]
 * [LOCKED] Batch 42 — A2A security hardening (III.5) [NO TAG]
 * [LOCKED] Batch 43 — Bi-temporal "explain my past decision" (II.5) [NO TAG]
diff --git a/nce/me_app.py b/nce/me_app.py
index fe56710..2a9de85 100644
--- a/nce/me_app.py
+++ b/nce/me_app.py
@@ -5,9 +5,10 @@ Subject-scoped `/api/me/*` surface (consent-bound read/govern surface).
 Requires JWT Bearer tokens to authenticate.
 """
 
-from __future__ import annotations
-
+import json
 import logging
+import re
+import uuid
 from contextlib import asynccontextmanager
 from uuid import UUID
 
@@ -17,8 +18,10 @@ from starlette.requests import Request
 from starlette.responses import JSONResponse
 from starlette.routing import Route
 
+from nce.atms import evaluate_atms_intervention, persist_atms_invalidation
 from nce.auth import NamespaceContext
 from nce.db_utils import scoped_pg_session
+from nce.event_log import append_event
 from nce.jwt_auth import JWTAuthMiddleware
 from nce.orchestrator import NCEEngine
 
@@ -139,6 +142,498 @@ async def get_me_memories(request: Request) -> JSONResponse:
         )
 
 
+async def get_me_profile(request: Request) -> JSONResponse:
+    """GET /api/me/profile
+
+    Retrieve a detailed profile of active beliefs (memories) for the caller's namespace and agent,
+    including salience, confidence, last reinforced, source, and associated unresolved contradictions.
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
+        # 1. Fetch active memories with salience information
+        mem_rows = await conn.fetch(
+            """
+            SELECT m.id, m.namespace_id, m.agent_id, m.memory_type, m.assertion_type, m.payload_ref, m.valid_from, m.metadata, m.created_at,
+                   COALESCE(ms.salience_score, 1.0) AS salience,
+                   COALESCE(ms.updated_at, m.created_at) AS last_reinforced
+            FROM memories m
+            LEFT JOIN memory_salience ms ON m.id = ms.memory_id AND ms.agent_id = m.agent_id AND ms.namespace_id = m.namespace_id
+            WHERE m.agent_id = $1 AND m.namespace_id = $2 AND m.valid_to IS NULL
+            """,
+            ns_ctx.agent_id,
+            ns_id,
+        )
+
+        # 2. Fetch active contradictions in the namespace to associate with memories
+        contra_rows = await conn.fetch(
+            """
+            SELECT id, memory_a_id, memory_b_id, confidence, detected_at, detection_path, signals, resolution
+            FROM contradictions
+            WHERE namespace_id = $1 AND resolution IS NULL
+            """,
+            ns_id,
+        )
+
+        # Index contradictions by memory ID
+        contra_map: dict[UUID, list[dict]] = {}
+        for c in contra_rows:
+            signals = c["signals"]
+            if isinstance(signals, str):
+                try:
+                    signals = json.loads(signals)
+                except Exception:
+                    signals = {}
+            contra_data = {
+                "id": str(c["id"]),
+                "memory_a_id": str(c["memory_a_id"]),
+                "memory_b_id": str(c["memory_b_id"]),
+                "confidence": float(c["confidence"]),
+                "detected_at": c["detected_at"].isoformat() if c["detected_at"] else None,
+                "detection_path": c["detection_path"],
+                "signals": signals,
+                "resolution": c["resolution"],
+            }
+            contra_map.setdefault(c["memory_a_id"], []).append(contra_data)
+            contra_map.setdefault(c["memory_b_id"], []).append(contra_data)
+
+        beliefs = []
+        for row in mem_rows:
+            mem_id = row["id"]
+            metadata = row["metadata"] or {}
+            if isinstance(metadata, str):
+                try:
+                    metadata = json.loads(metadata)
+                except Exception:
+                    metadata = {}
+            confidence = metadata.get("confidence", 1.0)
+            try:
+                confidence = float(confidence)
+            except (ValueError, TypeError):
+                confidence = 1.0
+
+            source = metadata.get("source", row["payload_ref"])
+
+            beliefs.append(
+                {
+                    "id": str(mem_id),
+                    "namespace_id": str(row["namespace_id"]),
+                    "agent_id": row["agent_id"],
+                    "memory_type": row["memory_type"],
+                    "assertion_type": row["assertion_type"],
+                    "payload_ref": row["payload_ref"],
+                    "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
+                    "metadata": metadata,
+                    "salience": float(row["salience"]),
+                    "confidence": confidence,
+                    "last_reinforced": row["last_reinforced"].isoformat()
+                    if row["last_reinforced"]
+                    else None,
+                    "source": source,
+                    "contradictions": contra_map.get(mem_id, []),
+                }
+            )
+
+        return JSONResponse(beliefs)
+
+
+async def post_me_govern(request: Request) -> JSONResponse:
+    """POST /api/me/govern
+
+    Govern a memory: edit, downweight, pin, or retract (which triggers the ATMS cascade).
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
+    try:
+        body = await request.json()
+    except Exception:
+        return JSONResponse(
+            {
+                "jsonrpc": "2.0",
+                "error": {
+                    "code": -32700,
+                    "message": "Parse error",
+                    "data": {"reason": "invalid_json_body"},
+                },
+                "id": None,
+            },
+            status_code=400,
+        )
+
+    memory_id_str = body.get("memory_id")
+    action = body.get("action")
+
+    if not memory_id_str or not action:
+        return JSONResponse(
+            {
+                "jsonrpc": "2.0",
+                "error": {
+                    "code": -32602,
+                    "message": "Invalid params",
+                    "data": {"reason": "memory_id and action are required"},
+                },
+                "id": None,
+            },
+            status_code=400,
+        )
+
+    try:
+        memory_id = UUID(str(memory_id_str).strip())
+    except ValueError:
+        return JSONResponse(
+            {
+                "jsonrpc": "2.0",
+                "error": {
+                    "code": -32602,
+                    "message": "Invalid params",
+                    "data": {"reason": "memory_id must be a valid UUID"},
+                },
+                "id": None,
+            },
+            status_code=400,
+        )
+
+    valid_actions = {"edit", "downweight", "pin", "retract"}
+    if action not in valid_actions:
+        return JSONResponse(
+            {
+                "jsonrpc": "2.0",
+                "error": {
+                    "code": -32602,
+                    "message": "Invalid params",
+                    "data": {"reason": f"action must be one of {sorted(valid_actions)}"},
+                },
+                "id": None,
+            },
+            status_code=400,
+        )
+
+    engine: NCEEngine = request.app.state.engine
+    async with scoped_pg_session(engine.pg_pool, ns_id) as conn:
+        async with conn.transaction():
+            # Verify the memory exists, is scoped to RLS, and is not already soft-deleted
+            memory = await conn.fetchrow(
+                "SELECT id, assertion_type, payload_ref, metadata FROM memories WHERE id = $1 AND namespace_id = $2 AND valid_to IS NULL",
+                memory_id,
+                ns_id,
+            )
+            if not memory:
+                return JSONResponse(
+                    {
+                        "jsonrpc": "2.0",
+                        "error": {
+                            "code": -32004,
+                            "message": "Method not found",
+                            "data": {"reason": "memory not found or already deleted"},
+                        },
+                        "id": None,
+                    },
+                    status_code=404,
+                )
+
+            if action == "edit":
+                # Edit metadata / assertion_type / payload_ref
+                new_assertion_type = body.get("assertion_type", memory["assertion_type"])
+                new_payload_ref = body.get("payload_ref", memory["payload_ref"])
+
+                # Check format of new_payload_ref
+                if not re.match(r"^[a-f0-9]{24}$", new_payload_ref):
+                    return JSONResponse(
+                        {
+                            "jsonrpc": "2.0",
+                            "error": {
+                                "code": -32602,
+                                "message": "Invalid params",
+                                "data": {"reason": "payload_ref must be a 24-character hex string"},
+                            },
+                            "id": None,
+                        },
+                        status_code=400,
+                    )
+
+                metadata = memory["metadata"] or {}
+                if isinstance(metadata, str):
+                    try:
+                        metadata = json.loads(metadata)
+                    except Exception:
+                        metadata = {}
+                new_metadata = dict(metadata)
+                if isinstance(body.get("metadata"), dict):
+                    new_metadata.update(body["metadata"])
+
+                await conn.execute(
+                    """
+                    UPDATE memories
+                    SET assertion_type = $1,
+                        payload_ref = $2,
+                        metadata = $3::jsonb
+                    WHERE id = $4 AND namespace_id = $5 AND valid_to IS NULL
+                    """,
+                    new_assertion_type,
+                    new_payload_ref,
+                    json.dumps(new_metadata),
+                    memory_id,
+                    ns_id,
+                )
+
+                await append_event(
+                    conn=conn,
+                    namespace_id=ns_id,
+                    agent_id=ns_ctx.agent_id,
+                    event_type="store_memory",
+                    params={
+                        "saga_id": str(uuid.uuid4()),
+                        "memory_id": str(memory_id),
+                        "payload_ref": new_payload_ref,
+                        "assertion_type": new_assertion_type,
+                        "entities": new_metadata.get("entities", []),
+                        "triplets": new_metadata.get("triplets", []),
+                        "action": "edit",
+                    },
+                    result_summary={"status": "success", "edited": True},
+                )
+                return JSONResponse({"status": "success", "action": "edit"})
+
+            elif action == "downweight":
+                factor = body.get("factor", 0.2)
+                try:
+                    factor = float(factor)
+                except (ValueError, TypeError):
+                    return JSONResponse(
+                        {
+                            "jsonrpc": "2.0",
+                            "error": {
+                                "code": -32602,
+                                "message": "Invalid params",
+                                "data": {"reason": "factor must be a float"},
+                            },
+                            "id": None,
+                        },
+                        status_code=400,
+                    )
+                factor = max(0.0, min(1.0, factor))
+
+                await conn.execute(
+                    """
+                    INSERT INTO memory_salience (memory_id, agent_id, namespace_id, salience_score, updated_at, access_count)
+                    VALUES ($1::uuid, $2, $3::uuid, GREATEST(0.0, 1.0 - $4::real), NOW(), 1)
+                    ON CONFLICT (memory_id, agent_id) DO UPDATE
+                        SET salience_score = GREATEST(0.0, memory_salience.salience_score - $4::real),
+                            updated_at = NOW(),
+                            access_count = memory_salience.access_count + 1
+                    """,
+                    memory_id,
+                    ns_ctx.agent_id,
+                    ns_id,
+                    factor,
+                )
+
+                await append_event(
+                    conn=conn,
+                    namespace_id=ns_id,
+                    agent_id=ns_ctx.agent_id,
+                    event_type="boost_memory",
+                    params={"memory_id": str(memory_id), "factor": -factor},
+                    result_summary={"status": "success", "action": "downweight"},
+                )
+                return JSONResponse({"status": "success", "action": "downweight"})
+
+            elif action == "pin":
+                await conn.execute(
+                    """
+                    INSERT INTO memory_salience (memory_id, agent_id, namespace_id, salience_score, updated_at, access_count)
+                    VALUES ($1::uuid, $2, $3::uuid, 1.0, NOW(), 1)
+                    ON CONFLICT (memory_id, agent_id) DO UPDATE
+                        SET salience_score = 1.0,
+                            updated_at = NOW(),
+                            access_count = memory_salience.access_count + 1
+                    """,
+                    memory_id,
+                    ns_ctx.agent_id,
+                    ns_id,
+                )
+
+                metadata = memory["metadata"] or {}
+                if isinstance(metadata, str):
+                    try:
+                        metadata = json.loads(metadata)
+                    except Exception:
+                        metadata = {}
+                meta = dict(metadata)
+                meta["pinned"] = True
+
+                await conn.execute(
+                    "UPDATE memories SET metadata = $1::jsonb WHERE id = $2 AND namespace_id = $3 AND valid_to IS NULL",
+                    json.dumps(meta),
+                    memory_id,
+                    ns_id,
+                )
+
+                await append_event(
+                    conn=conn,
+                    namespace_id=ns_id,
+                    agent_id=ns_ctx.agent_id,
+                    event_type="boost_memory",
+                    params={"memory_id": str(memory_id), "factor": 1.0},
+                    result_summary={"status": "success", "action": "pin"},
+                )
+                return JSONResponse({"status": "success", "action": "pin"})
+
+            else:  # action == "retract"
+                # 1. Soft-delete the memory itself
+                await conn.execute(
+                    "UPDATE memories SET valid_to = now() WHERE id = $1 AND namespace_id = $2 AND valid_to IS NULL",
+                    memory_id,
+                    ns_id,
+                )
+
+                # 2. Append forget_memory event for WORM traceability
+                await append_event(
+                    conn=conn,
+                    namespace_id=ns_id,
+                    agent_id=ns_ctx.agent_id,
+                    event_type="forget_memory",
+                    params={"memory_id": str(memory_id)},
+                    result_summary={"status": "success", "action": "retract"},
+                )
+
+                # 3. Topology / causal graph cascade
+                cascade_set = {str(memory_id)}
+                topo_cascade = await evaluate_atms_intervention(conn, ns_id, str(memory_id))
+                cascade_set.update(topo_cascade)
+
+                # 4. Transitive derived_from memory dependents cascade
+                max_cascade = 100
+                todo = [str(memory_id)]
+                visited = {str(memory_id)}
+                while todo and len(visited) < max_cascade:
+                    current = todo.pop()
+                    dep_rows = await conn.fetch(
+                        """
+                        SELECT id FROM memories
+                        WHERE namespace_id = $1::uuid
+                          AND (derived_from @> jsonb_build_array($2::text)
+                               OR derived_from @> jsonb_build_array($2::uuid))
+                          AND valid_to IS NULL
+                        """,
+                        ns_id,
+                        current,
+                    )
+                    for r in dep_rows:
+                        dep_id = str(r["id"])
+                        if dep_id not in visited:
+                            visited.add(dep_id)
+                            todo.append(dep_id)
+                            if len(visited) >= max_cascade:
+                                break
+
+                cascade_set.update(visited)
+
+                # 5. Persist soft-deletions of all cascades in the database
+                await persist_atms_invalidation(conn, ns_id, cascade_set)
+
+                # 6. Log the atms_cascade event (using a sentinel contradiction_id)
+                sentinel_contradiction_id = str(UUID(int=0))
+                await append_event(
+                    conn=conn,
+                    namespace_id=ns_id,
+                    agent_id=ns_ctx.agent_id,
+                    event_type="atms_cascade",
+                    params={
+                        "contradiction_id": sentinel_contradiction_id,
+                        "invalidated_memory_id": str(memory_id),
+                        "invalidated_ids": sorted(list(cascade_set)),
+                    },
+                    result_summary={
+                        "status": "success",
+                        "cascade_count": len(cascade_set),
+                        "action": "retract",
+                    },
+                )
+                return JSONResponse(
+                    {"status": "success", "action": "retract", "cascade_count": len(cascade_set)}
+                )
+
+
 app = Starlette(
     debug=False,
     lifespan=me_lifespan,
@@ -151,5 +646,8 @@ app = Starlette(
     ],
     routes=[
         Route("/api/me/memories", endpoint=get_me_memories, methods=["GET"]),
+        Route("/api/me/profile", endpoint=get_me_profile, methods=["GET"]),
+        Route("/api/me/govern", endpoint=post_me_govern, methods=["POST"]),
+        Route("/api/me/profile/govern", endpoint=post_me_govern, methods=["POST"]),
     ],
 )
diff --git a/tests/test_me_app.py b/tests/test_me_app.py
index 97c62ac..61c5518 100644
--- a/tests/test_me_app.py
+++ b/tests/test_me_app.py
@@ -6,11 +6,14 @@ Unit and integration tests for the subject-scoped `/api/me/*` surface.
 
 from __future__ import annotations
 
+import json
 import os
 import time
+import uuid
 from contextlib import asynccontextmanager
 from datetime import datetime, timezone
 from typing import Any
+from unittest.mock import AsyncMock
 from urllib.parse import urlparse, urlunparse
 from uuid import UUID
 
@@ -94,6 +97,19 @@ class TestMeAppUnit:
         async def mock_scoped_pg_session(pool: Any, namespace_id: str | UUID):
             class MockConn:
                 async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
+                    if "contradictions" in query.lower():
+                        return [
+                            {
+                                "id": UUID("22222222-3333-4444-5555-666666666666"),
+                                "memory_a_id": UUID("11111111-2222-3333-4444-555555555555"),
+                                "memory_b_id": UUID("99999999-8888-7777-6666-555555555555"),
+                                "confidence": 0.85,
+                                "detected_at": datetime.now(timezone.utc),
+                                "detection_path": "manual",
+                                "signals": "{}",
+                                "resolution": None,
+                            }
+                        ]
                     return [
                         {
                             "id": UUID("11111111-2222-3333-4444-555555555555"),
@@ -104,12 +120,37 @@ class TestMeAppUnit:
                             "payload_ref": "000000000000000000000001",
                             "valid_from": datetime.now(timezone.utc),
                             "valid_to": None,
+                            "metadata": {"confidence": 0.95, "source": "test_src"},
+                            "created_at": datetime.now(timezone.utc),
+                            "salience": 1.0,
+                            "last_reinforced": datetime.now(timezone.utc),
                         }
                     ]
 
+                async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
+                    if "memories" in query.lower():
+                        return {
+                            "id": args[0],
+                            "assertion_type": "fact",
+                            "payload_ref": "000000000000000000000001",
+                            "metadata": {"confidence": 0.95, "source": "test_src"},
+                        }
+                    return None
+
+                async def execute(self, query: str, *args: Any) -> str:
+                    return "UPDATE 1"
+
+                def transaction(self) -> Any:
+                    @asynccontextmanager
+                    async def mock_tx():
+                        yield
+
+                    return mock_tx()
+
             yield MockConn()
 
         monkeypatch.setattr("nce.me_app.scoped_pg_session", mock_scoped_pg_session)
+        monkeypatch.setattr("nce.me_app.append_event", AsyncMock(return_value=None))
 
     def test_unauthorized_missing_token(self) -> None:
         with TestClient(app) as client:
@@ -170,6 +211,88 @@ class TestMeAppUnit:
         assert resp.status_code == 403
         assert resp.json()["error"]["data"]["reason"] == "cross-agent request is denied"
 
+    def test_get_profile_success(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-abc"))
+        with TestClient(app) as client:
+            resp = client.get(
+                "/api/me/profile",
+                headers={"Authorization": f"Bearer {token}"},
+            )
+        assert resp.status_code == 200
+        data = resp.json()
+        assert len(data) == 1
+        assert data[0]["namespace_id"] == valid_ns_id
+        assert data[0]["agent_id"] == "agent-abc"
+        assert data[0]["salience"] == 1.0
+        assert data[0]["confidence"] == 0.95
+        assert len(data[0]["contradictions"]) == 1
+        assert data[0]["contradictions"][0]["memory_a_id"] == "11111111-2222-3333-4444-555555555555"
+
+    def test_post_govern_edit_success(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-abc"))
+        with TestClient(app) as client:
+            resp = client.post(
+                "/api/me/govern",
+                headers={"Authorization": f"Bearer {token}"},
+                json={
+                    "memory_id": "11111111-2222-3333-4444-555555555555",
+                    "action": "edit",
+                    "assertion_type": "opinion",
+                    "payload_ref": "0000000000000000000000aa",
+                    "metadata": {"info": "edited"},
+                },
+            )
+        assert resp.status_code == 200
+        assert resp.json()["status"] == "success"
+        assert resp.json()["action"] == "edit"
+
+    def test_post_govern_downweight_success(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-abc"))
+        with TestClient(app) as client:
+            resp = client.post(
+                "/api/me/govern",
+                headers={"Authorization": f"Bearer {token}"},
+                json={
+                    "memory_id": "11111111-2222-3333-4444-555555555555",
+                    "action": "downweight",
+                    "factor": 0.3,
+                },
+            )
+        assert resp.status_code == 200
+        assert resp.json()["status"] == "success"
+        assert resp.json()["action"] == "downweight"
+
+    def test_post_govern_pin_success(self) -> None:
+        token = make_token(_base_payload(agent_id="agent-abc"))
+        with TestClient(app) as client:
+            resp = client.post(
+                "/api/me/govern",
+                headers={"Authorization": f"Bearer {token}"},
+                json={"memory_id": "11111111-2222-3333-4444-555555555555", "action": "pin"},
+            )
+        assert resp.status_code == 200
+        assert resp.json()["status"] == "success"
+        assert resp.json()["action"] == "pin"
+
+    def test_post_govern_retract_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
+        # Mock retract specific ATMS helper imports
+        monkeypatch.setattr(
+            "nce.me_app.evaluate_atms_intervention",
+            AsyncMock(return_value={"11111111-2222-3333-4444-555555555555"}),
+        )
+        monkeypatch.setattr("nce.me_app.persist_atms_invalidation", AsyncMock(return_value=1))
+
+        token = make_token(_base_payload(agent_id="agent-abc"))
+        with TestClient(app) as client:
+            resp = client.post(
+                "/api/me/govern",
+                headers={"Authorization": f"Bearer {token}"},
+                json={"memory_id": "11111111-2222-3333-4444-555555555555", "action": "retract"},
+            )
+        assert resp.status_code == 200
+        assert resp.json()["status"] == "success"
+        assert resp.json()["action"] == "retract"
+
 
 # ---------------------------------------------------------------------------
 # Integration Tests (Real Database)
@@ -285,3 +408,144 @@ class TestMeAppIntegration:
         finally:
             await engine.disconnect()
             app.state.engine = None
+
+    @pytest.mark.asyncio
+    async def test_me_app_profile_and_retract_integration(
+        self,
+        setup_jwt_config: None,
+        pg_pool: asyncpg.Pool,
+        monkeypatch: pytest.MonkeyPatch,
+    ) -> None:
+        # We run the application against the real database using HTTPX AsyncClient
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
+                # 1. Create a namespace in the database
+                ns_slug = f"test-ns-profile-{int(time.time())}"
+                async with pg_pool.acquire() as conn:
+                    res = await conn.fetchrow(
+                        "INSERT INTO namespaces (slug) VALUES ($1) RETURNING id", ns_slug
+                    )
+                    ns_id = res["id"]
+
+                    memory_id_a = uuid.uuid4()
+                    memory_id_b = uuid.uuid4()
+
+                    # Insert memory A (independent)
+                    await conn.execute(
+                        "INSERT INTO memories (id, namespace_id, agent_id, payload_ref, metadata) "
+                        "VALUES ($1, $2, 'agent-me', '0000000000000000000000aa', '{}'::jsonb)",
+                        memory_id_a,
+                        ns_id,
+                    )
+
+                    # Insert memory B derived from memory A
+                    await conn.execute(
+                        "INSERT INTO memories (id, namespace_id, agent_id, payload_ref, metadata, derived_from) "
+                        "VALUES ($1, $2, 'agent-me', '0000000000000000000000bb', '{}'::jsonb, $3::jsonb)",
+                        memory_id_b,
+                        ns_id,
+                        json.dumps([str(memory_id_a)]),
+                    )
+
+                token = make_token(_base_payload(ns_id=str(ns_id), agent_id="agent-me"))
+
+                # 2. GET profile and check both memories exist
+                resp = await client.get(
+                    "/api/me/profile",
+                    headers={"Authorization": f"Bearer {token}"},
+                )
+                assert resp.status_code == 200
+                profile = resp.json()
+                assert len(profile) == 2
+
+                # Check IDs are present
+                profile_ids = {p["id"] for p in profile}
+                assert str(memory_id_a) in profile_ids
+                assert str(memory_id_b) in profile_ids
+
+                # 3. Post a govern downweight request
+                resp_down = await client.post(
+                    "/api/me/govern",
+                    headers={"Authorization": f"Bearer {token}"},
+                    json={"memory_id": str(memory_id_a), "action": "downweight", "factor": 0.25},
+                )
+                assert resp_down.status_code == 200
+
+                # 4. Post a govern pin request
+                resp_pin = await client.post(
+                    "/api/me/govern",
+                    headers={"Authorization": f"Bearer {token}"},
+                    json={"memory_id": str(memory_id_a), "action": "pin"},
+                )
+                assert resp_pin.status_code == 200
+
+                # 5. GET profile again to verify pinning
+                resp_prof_2 = await client.get(
+                    "/api/me/profile",
+                    headers={"Authorization": f"Bearer {token}"},
+                )
+                assert resp_prof_2.status_code == 200
+                profile_2 = resp_prof_2.json()
+                mem_a_data = next(p for p in profile_2 if p["id"] == str(memory_id_a))
+                assert mem_a_data["salience"] == 1.0
+                assert mem_a_data["metadata"].get("pinned") is True
+
+                # 6. Retract memory A and ensure memory B (derived) cascades and gets soft-deleted too
+                resp_retract = await client.post(
+                    "/api/me/govern",
+                    headers={"Authorization": f"Bearer {token}"},
+                    json={"memory_id": str(memory_id_a), "action": "retract"},
+                )
+                assert resp_retract.status_code == 200
+                assert resp_retract.json()["status"] == "success"
+
+                # 7. GET profile again and verify it is empty
+                resp_prof_3 = await client.get(
+                    "/api/me/profile",
+                    headers={"Authorization": f"Bearer {token}"},
+                )
+                assert resp_prof_3.status_code == 200
+                assert len(resp_prof_3.json()) == 0
+        finally:
+            await engine.disconnect()
+            app.state.engine = None
```
