# Diff Reference for Batch 41

```diff
diff --git a/NCE_TECH_DEBT.md b/NCE_TECH_DEBT.md
index 6d4d883..d3ea240 100644
--- a/NCE_TECH_DEBT.md
+++ b/NCE_TECH_DEBT.md
@@ -12,6 +12,8 @@
 | TD-4 | LOW (gate) | Verification | open |
 | TD-5 | LOW | Working-tree entanglement | informational |
 | TD-6 | MED | Batch 21 (embedding sidecar resilience) | open — partial |
+| TD-7 | LOW | requirements/Docker optimizations | open (for the new version — not applied) |
+
 
 ---
 
@@ -79,6 +81,90 @@ These were confirmed OPEN in the Wave 0 re-audit and are scheduled in later batc
 - **R-A / Mongo write durability** — saga Mongo write uses default `w:1, j:false`; power-loss window can orphan a committed PG row. (Batch 57.)
 - **R-B / reverse-orphan sweep** — GC is forward-only; no detection of PG memories with a missing Mongo doc. (Batch 58.)
 
+## TD-7 — requirements/Docker optimizations (Drop-in rewrite for the new version — not applied)
+
+### requirements.txt
+Remove torch from here (install it separately for CPU), and move test deps out:
+```diff
+- spacy>=3.7.0
++ spacy>=3.7.0
+  ...
+- # Phase 5: Jina Embeddings
+  sentence-transformers>=2.3.1
+  transformers>=4.36.2,<5.9
+- torch>=2.1.2
++ # torch installed separately from the CPU index in the Dockerfile (no CUDA)
+  ...
+- # Testing
+- pytest>=8.0.0
+- pytest-asyncio>=0.23.0
+- pytest-mock>=3.12.0
+```
+(Add the three pytest* lines to the existing requirements-dev.txt.)
+
+### deploy/multiuser/Dockerfile
+CPU torch + bind-mounted wheels:
+```dockerfile
+# syntax=docker/dockerfile:1.7
+FROM python:3.12-slim-bookworm AS builder
+WORKDIR /build
+RUN apt-get update \
+    && apt-get install -y --no-install-recommends build-essential git \
+    && rm -rf /var/lib/apt/lists/*
+COPY requirements.txt .
+# CPU-only torch (no nvidia/cuda/triton) — saves ~3.6 GB
+RUN pip wheel --no-cache-dir -w /wheels \
+        --index-url https://download.pytorch.org/whl/cpu "torch>=2.1.2" \
+    && pip wheel --no-cache-dir -w /wheels -r requirements.txt
+
+FROM python:3.12-slim-bookworm AS runtime
+WORKDIR /app
+COPY requirements.txt .
+# Bind-mount wheels: install without ever persisting them as a layer (saves ~3 GB)
+RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
+    pip install --no-cache-dir --no-index --find-links=/wheels \
+        "torch>=2.1.2" -r requirements.txt \
+    && python -m spacy download en_core_web_sm \
+    && useradd --system --uid 10001 --create-home trimcp
+
+COPY trimcp ./trimcp
+COPY bravo_hr ./bravo_hr
+COPY bravo_agreement ./bravo_agreement
+COPY start_worker.py health_probe.py ./
+COPY admin_server.py server.py ./
+COPY admin ./admin
+RUN chown -R trimcp:trimcp /app
+USER trimcp
+ENV XDG_CACHE_HOME=/tmp PYTHONUNBUFFERED=1 PYTHONPATH=/app
+HEALTHCHECK --interval=60s --timeout=15s --start-period=90s --retries=3 \
+    CMD python health_probe.py
+CMD ["python", "start_worker.py"]
+```
+
+### docker-compose.yml
+Collapse 7 builds into 1 shared image (use the same Dockerfile+context for all backend services; just build once and override command):
+```yaml
+x-backend: &backend
+  image: backend-app:latest      # one shared image
+  build:
+    context: .
+    dockerfile: deploy/multiuser/Dockerfile
+
+services:
+  bff:     { <<: *backend, command: ["python", "run_steps_bff.py"] }
+  product: { <<: *backend, command: ["python", "-m", "steps_product"] }
+  d365:    { <<: *backend, command: ["python", "-m", "steps_d365"] }
+  cron:    { <<: *backend, command: ["python", "-m", "trimcp.cron"] }
+  # a2a, admin, webhook-receiver likewise
+```
+Only the first service builds; the rest reuse backend-app:latest. 7×15 GB of churn → one ~8 GB image.
+
+### Recommended sequence when you push the new version
+1. Update the three files above; rebuild with BuildKit (DOCKER_BUILDKIT=1, default in your Docker 29.5).
+2. `docker compose up -d` to recreate containers onto the new shared image.
+3. `docker image prune -af` — reclaims the old backend-* images (the 5 in-use 4-day/21h ones + the 2 unused) once nothing references them.
+4. Pin dependencies (generate a lock / freeze to ==) so layers stay cache-stable going forward.
+
 ---
 
-*Last updated: Batches 18–25 committed (`5fc6494` B18, `fad62b2` B19, `2272398` B23, `55e1da3` B22, `4e10a9e` B20+21+24+25) on branch `batch-23-atms-cascade`. Open debt: TD-1 (commit hygiene), TD-3 (replay silent-skip), TD-4 (run cumulative gate), TD-6 (embedding-sidecar retry). Owner: NCE team. Revisit after the full prompt sequence completes.*
+*Last updated: Batches 18–25 committed (`5fc6494` B18, `fad62b2` B19, `2272398` B23, `55e1da3` B22, `4e10a9e` B20+21+24+25) on branch `batch-23-atms-cascade`. Open debt: TD-1 (commit hygiene), TD-3 (replay silent-skip), TD-4 (run cumulative gate), TD-6 (embedding-sidecar retry), TD-7 (requirements/Docker optimizations). Owner: NCE team. Revisit after the full prompt sequence completes.*
diff --git a/RL.md b/RL.md
index 249a306..c3a5055 100644
--- a/RL.md
+++ b/RL.md
@@ -48,7 +48,7 @@
 * [DONE] Batch 38 — Epistemic Receipts (II.2) [PASSED TAG]
 * [DONE] Batch 39 — Subject-scoped `/api/me/*` surface (cross-cutting enabler) [PASSED TAG]
 * [DONE] Batch 40 — Glass Profile endpoint + retract→ATMS (II.3) [PASSED TAG]
-* [OPEN] Batch 41 — Accountable Federation: write `a2a_shared_query` + signed provenance (II.6) [NO TAG]
+* [RUNNING] Batch 41 — Accountable Federation: write `a2a_shared_query` + signed provenance (II.6) [NO TAG]
 * [LOCKED] Batch 42 — A2A security hardening (III.5) [NO TAG]
 * [LOCKED] Batch 43 — Bi-temporal "explain my past decision" (II.5) [NO TAG]
 * [LOCKED] Batch 44 — DECISION + content-free WORM log fork (R2 / VII.5) [NO TAG]
diff --git a/nce/a2a.py b/nce/a2a.py
index 0193e0e..91bbd5d 100644
--- a/nce/a2a.py
+++ b/nce/a2a.py
@@ -26,7 +26,7 @@ try:
 except ImportError:  # pragma: no cover
     _CRYPTOGRAPHY_AVAILABLE = False
 
-import asyncpg
+import asyncpg  # type: ignore[import-untyped]
 from pydantic import BaseModel, ConfigDict, Field
 
 from nce.auth import NamespaceContext, set_namespace_context
@@ -41,6 +41,7 @@ async def _append_a2a_event(
     params: dict,
 ) -> None:
     """Helper to set namespace context and append a2a audit event cleanly."""
+    assert owner_ctx.namespace_id is not None, "Namespace ID cannot be None when writing an A2A event"
     await set_namespace_context(conn, owner_ctx.namespace_id)
     from nce.event_log import append_event
 
@@ -52,6 +53,7 @@ async def _append_a2a_event(
         params=params,
     )
 
+
 # ---------------------------------------------------------------------------
 # JSON-RPC 2.0 error codes
 # ---------------------------------------------------------------------------
@@ -96,6 +98,9 @@ class A2AGrantRequest(BaseModel):
     expires_in_seconds: int = Field(
         3600, ge=60, le=86400 * 30, description="Token validity duration (max 30 days)"
     )
+    can_delegate: bool = Field(
+        False, description="Whether the token can be delegated/re-granted downstream"
+    )
 
 
 class A2AGrantResponse(BaseModel):
@@ -118,6 +123,7 @@ class VerifiedGrant(BaseModel):
     owner_agent_id: str
     scopes: list[A2AScope]
     expires_at: datetime
+    can_delegate: bool
 
 
 class A2AAuthorizationError(Exception):
@@ -576,6 +582,57 @@ def _jsonrpc_error(code: int, message: str, reason: str) -> dict[str, Any]:
     }
 
 
+async def _resolve_scope_namespaces(conn: asyncpg.Connection, scope: A2AScope) -> list[UUID]:
+    """Resolve all potential namespace IDs that the resource in scope might belong to."""
+    if scope.resource_type in ("namespace", "subgraph"):
+        try:
+            return [UUID(scope.resource_id)]
+        except ValueError:
+            raise A2AScopeViolationError(
+                f"Invalid UUID string for namespace/subgraph resource: {scope.resource_id!r}"
+            )
+
+    if scope.resource_type == "memory":
+        try:
+            mem_uuid = UUID(scope.resource_id)
+        except ValueError:
+            raise A2AScopeViolationError(
+                f"Invalid UUID string for memory resource: {scope.resource_id!r}"
+            )
+        ns_val = await conn.fetchval(
+            "SELECT namespace_id FROM memories WHERE id = $1 LIMIT 1",
+            mem_uuid,
+        )
+        if ns_val is None:
+            raise A2AScopeViolationError(f"Memory with ID {scope.resource_id} not found.")
+        return [ns_val]
+
+    if scope.resource_type == "kg_node":
+        # Check if resource_id is a UUID
+        try:
+            node_uuid = UUID(scope.resource_id)
+            ns_val = await conn.fetchval(
+                "SELECT namespace_id FROM kg_nodes WHERE id = $1 LIMIT 1",
+                node_uuid,
+            )
+            if ns_val is None:
+                raise A2AScopeViolationError(f"KG Node with ID {scope.resource_id} not found.")
+            return [ns_val]
+        except ValueError:
+            # It's a label, not a UUID. Find all namespaces where this node label exists.
+            rows = await conn.fetch(
+                "SELECT DISTINCT namespace_id FROM kg_nodes WHERE label = $1",
+                scope.resource_id,
+            )
+            if not rows:
+                return []
+            return [row["namespace_id"] for row in rows]
+
+    raise A2AScopeViolationError(
+        f"Unsupported resource type for delegation: {scope.resource_type!r}"
+    )
+
+
 # ---------------------------------------------------------------------------
 # Core grant lifecycle (raw asyncpg — no ORM)
 # ---------------------------------------------------------------------------
@@ -593,6 +650,31 @@ async def create_grant(
     and returns the raw token to the caller (Agent A) to share out-of-band.
     The raw token is *never* stored — only the hash is persisted.
     """
+    # Scope validation for delegation (transitive re-grant prevention)
+    for scope in request.scopes:
+        ns_ids = await _resolve_scope_namespaces(conn, scope)
+        for ns_id in ns_ids:
+            if ns_id != owner_ctx.namespace_id:
+                has_delegate_grant = await conn.fetchval(
+                    """
+                    SELECT EXISTS (
+                        SELECT 1 FROM a2a_grants
+                        WHERE owner_namespace_id = $1
+                          AND (target_namespace_id = $2 OR target_namespace_id IS NULL)
+                          AND can_delegate = true
+                          AND status = 'active'
+                          AND expires_at > now()
+                    )
+                    """,
+                    ns_id,
+                    owner_ctx.namespace_id,
+                )
+                if not has_delegate_grant:
+                    raise A2AScopeViolationError(
+                        f"Caller namespace {owner_ctx.namespace_id} does not have delegable access "
+                        f"to target namespace {ns_id}."
+                    )
+
     token = f"nce_a2a_{secrets.token_urlsafe(32)}"
     token_hash = _hash_token(token)
     grant_id = uuid4()
@@ -605,8 +687,8 @@ async def create_grant(
             INSERT INTO a2a_grants (
                 id, owner_namespace_id, owner_agent_id,
                 target_namespace_id, target_agent_id,
-                scopes, token_hash, status, expires_at
-            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'active', $8)
+                scopes, token_hash, status, expires_at, can_delegate
+            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'active', $8, $9)
             """,
             grant_id,
             owner_ctx.namespace_id,
@@ -616,6 +698,7 @@ async def create_grant(
             scopes_json,
             token_hash,
             expires_at,
+            request.can_delegate,
         )
 
         await _append_a2a_event(
@@ -630,16 +713,18 @@ async def create_grant(
                 "target_agent_id": request.target_agent_id,
                 "scope_count": len(request.scopes),
                 "expires_at": expires_at.isoformat(),
+                "can_delegate": request.can_delegate,
             },
         )
 
     log.info(
-        "A2A grant created: grant_id=%s owner_ns=%s target_ns=%s scopes=%d expires=%s",
+        "A2A grant created: grant_id=%s owner_ns=%s target_ns=%s scopes=%d expires=%s can_delegate=%s",
         grant_id,
         owner_ctx.namespace_id,
         request.target_namespace_id,
         len(request.scopes),
         expires_at.isoformat(),
+        request.can_delegate,
     )
     return A2AGrantResponse(grant_id=grant_id, sharing_token=token, expires_at=expires_at)
 
@@ -664,7 +749,7 @@ async def verify_token(
         """
         SELECT id, owner_namespace_id, owner_agent_id,
                target_namespace_id, target_agent_id,
-               scopes, expires_at, status
+               scopes, expires_at, status, can_delegate
         FROM a2a_grants
         WHERE token_hash = $1 AND status = 'active'
         """,
@@ -719,6 +804,7 @@ async def verify_token(
         owner_agent_id=row["owner_agent_id"],
         scopes=scopes,
         expires_at=expires_at,
+        can_delegate=row["can_delegate"],
     )
 
 
@@ -785,7 +871,7 @@ async def list_grants(
         rows = await conn.fetch(
             """
             SELECT id, owner_agent_id, target_namespace_id, target_agent_id,
-                   scopes, status, expires_at, created_at
+                   scopes, status, expires_at, created_at, can_delegate
             FROM a2a_grants
             WHERE owner_namespace_id = $1
             ORDER BY created_at DESC
@@ -797,7 +883,7 @@ async def list_grants(
         rows = await conn.fetch(
             """
             SELECT id, owner_agent_id, target_namespace_id, target_agent_id,
-                   scopes, status, expires_at, created_at
+                   scopes, status, expires_at, created_at, can_delegate
             FROM a2a_grants
             WHERE owner_namespace_id = $1
               AND status = 'active'
@@ -819,6 +905,7 @@ async def list_grants(
             "scopes": json.loads(row["scopes"]),
             "status": row["status"],
             "expires_at": row["expires_at"].isoformat(),
+            "can_delegate": row["can_delegate"],
             "created_at": row["created_at"].isoformat(),
         }
         for row in rows
@@ -898,7 +985,7 @@ async def verify_grant_status(
             """
             SELECT id, owner_namespace_id, owner_agent_id,
                    target_namespace_id, target_agent_id,
-                   scopes, expires_at, status, created_at
+                   scopes, expires_at, status, created_at, can_delegate
             FROM a2a_grants
             WHERE token_hash = $1
             """,
@@ -909,7 +996,7 @@ async def verify_grant_status(
             """
             SELECT id, owner_namespace_id, owner_agent_id,
                    target_namespace_id, target_agent_id,
-                   scopes, expires_at, status, created_at
+                   scopes, expires_at, status, created_at, can_delegate
             FROM a2a_grants
             WHERE id = $1
             """,
@@ -967,6 +1054,7 @@ async def verify_grant_status(
         "scopes": json.loads(row["scopes"]),
         "status": status,
         "expires_at": expires_at.isoformat(),
+        "can_delegate": row["can_delegate"],
         "created_at": row["created_at"].isoformat(),
     }
 
@@ -1008,7 +1096,7 @@ async def update_grant_scopes(
     if mode == "append":
         existing_data = json.loads(row["scopes"])
         merged_scopes = [A2AScope.model_validate(s) for s in existing_data]
-        
+
         # Merge input scopes, filtering out exact duplicates
         for ns in scopes:
             if ns not in merged_scopes:
@@ -1069,7 +1157,7 @@ async def inspect_grant(
         """
         SELECT id, owner_namespace_id, owner_agent_id,
                target_namespace_id, target_agent_id,
-               scopes, status, expires_at, created_at
+               scopes, status, expires_at, created_at, can_delegate
         FROM a2a_grants
         WHERE id = $1 AND owner_namespace_id = $2
         """,
@@ -1089,11 +1177,13 @@ async def inspect_grant(
         "grant_id": str(row["id"]),
         "owner_namespace_id": str(row["owner_namespace_id"]),
         "owner_agent_id": row["owner_agent_id"],
-        "target_namespace_id": str(row["target_namespace_id"]) if row["target_namespace_id"] else None,
+        "target_namespace_id": str(row["target_namespace_id"])
+        if row["target_namespace_id"]
+        else None,
         "target_agent_id": row["target_agent_id"],
         "scopes": json.loads(row["scopes"]),
         "status": row["status"],
         "expires_at": expires_at.isoformat(),
+        "can_delegate": row["can_delegate"],
         "created_at": row["created_at"].isoformat(),
     }
-
diff --git a/nce/a2a_mcp_handlers.py b/nce/a2a_mcp_handlers.py
index 8eed8db..c88c441 100644
--- a/nce/a2a_mcp_handlers.py
+++ b/nce/a2a_mcp_handlers.py
@@ -51,6 +51,7 @@ def _build_grant_request(arguments: dict[str, Any]) -> A2AGrantRequest:
         target_agent_id=arguments.get("target_agent_id"),
         scopes=_parse_scopes(arguments.get("scopes", [])),
         expires_in_seconds=int(arguments.get("expires_in_seconds", 3600)),
+        can_delegate=bool(arguments.get("can_delegate", False)),
     )
 
 
@@ -122,16 +123,35 @@ async def handle_a2a_query_shared(engine: NCEEngine, arguments: dict[str, Any])
     async with engine.pg_pool.acquire(timeout=10.0) as conn:
         verified = await verify_token(conn, req.sharing_token, consumer_ctx)
 
-    resource_id = req.resource_id or str(verified.owner_namespace_id)
-    if req.resource_type != "namespace" and not req.resource_id:
-        raise ValueError(f"resource_id is required when resource_type={req.resource_type!r}")
+        resource_id = req.resource_id or str(verified.owner_namespace_id)
+        if req.resource_type != "namespace" and not req.resource_id:
+            raise ValueError(f"resource_id is required when resource_type={req.resource_type!r}")
 
-    enforce_scope(
-        verified.scopes,
-        req.resource_type,
-        resource_id,
-        str(verified.owner_namespace_id),
-    )
+        enforce_scope(
+            verified.scopes,
+            req.resource_type,
+            resource_id,
+            str(verified.owner_namespace_id),
+        )
+
+        # Append signed event on the owner's log
+        owner_ctx = NamespaceContext(
+            namespace_id=verified.owner_namespace_id,
+            agent_id=verified.owner_agent_id,
+        )
+        from nce.a2a import _append_a2a_event
+
+        await _append_a2a_event(
+            conn,
+            owner_ctx=owner_ctx,
+            event_type="a2a_shared_query",
+            params={
+                "consumer_namespace_id": str(consumer_ctx.namespace_id),
+                "consumer_agent_id": consumer_ctx.agent_id,
+                "grant_id": str(verified.grant_id),
+                "query": req.query,
+            },
+        )
 
     if verified.owner_namespace_id == consumer_ctx.namespace_id:
         log.warning(
@@ -149,6 +169,31 @@ async def handle_a2a_query_shared(engine: NCEEngine, arguments: dict[str, Any])
         offset=0,
     )
 
+    # Hydrate owner's original signature + key ID alongside shared memories
+    if results:
+        memory_ids = [res["memory_id"] for res in results]
+        async with engine.pg_pool.acquire(timeout=10.0) as conn:
+            rows = await conn.fetch(
+                """
+                SELECT id, signature, signature_key_id
+                FROM memories
+                WHERE id = ANY($1) AND namespace_id = $2
+                """,
+                memory_ids,
+                verified.owner_namespace_id,
+            )
+            sig_map = {
+                row["id"]: {
+                    "signature": row["signature"].hex() if row["signature"] else None,
+                    "signature_key_id": row["signature_key_id"],
+                }
+                for row in rows
+            }
+            for res in results:
+                info = sig_map.get(res["memory_id"], {})
+                res["signature"] = info.get("signature")
+                res["signature_key_id"] = info.get("signature_key_id")
+
     return json.dumps({"results": results}, default=str)
 
 
diff --git a/nce/models.py b/nce/models.py
index 2b89cc3..2906ac9 100644
--- a/nce/models.py
+++ b/nce/models.py
@@ -1172,6 +1172,7 @@ class A2AGrantRequest(BaseModel):
     target_agent_id: str | None = None
     scopes: list[A2AScope] = Field(..., min_length=1)
     expires_in_seconds: int = Field(3600, ge=60, le=86400 * 30)
+    can_delegate: bool = Field(default=False)
 
     @field_validator("target_agent_id")
     @classmethod
@@ -1197,6 +1198,7 @@ class VerifiedGrant(BaseModel):
     owner_agent_id: str
     scopes: list[A2AScope]
     expires_at: datetime
+    can_delegate: bool
 
 
 class A2AQuerySharedRequest(BaseModel):
diff --git a/nce/schema.sql b/nce/schema.sql
index 7c2e4ce..6d1b088 100644
--- a/nce/schema.sql
+++ b/nce/schema.sql
@@ -805,6 +805,7 @@ CREATE TABLE IF NOT EXISTS a2a_grants (
     status               TEXT        NOT NULL DEFAULT 'active'
                                      CHECK (status IN ('active', 'revoked', 'expired')),
     expires_at           TIMESTAMPTZ NOT NULL,
+    can_delegate         BOOLEAN     NOT NULL DEFAULT false,
     created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
 );
 
diff --git a/tests/test_a2a.py b/tests/test_a2a.py
index 0f6ff67..71b33d9 100644
--- a/tests/test_a2a.py
+++ b/tests/test_a2a.py
@@ -46,6 +46,7 @@ def _grant_row(
     consumer_ns: uuid.UUID | None,
     consumer_agent: str | None,
     scopes: list[dict],
+    can_delegate: bool = False,
 ) -> dict:
     return {
         "id": uuid.uuid4(),
@@ -56,6 +57,7 @@ def _grant_row(
         "scopes": json.dumps(scopes),
         "expires_at": _future_expiry(),
         "status": "active",
+        "can_delegate": can_delegate,
     }
 
 
@@ -248,6 +250,69 @@ class TestCreateGrantSqlShape:
         conn.execute.assert_awaited_once()
 
 
+class TestCreateGrantDelegation:
+    """Tests for the can_delegate validation rules inside create_grant."""
+
+    @pytest.mark.asyncio
+    async def test_create_grant_other_namespace_without_delegable_grant_raises(self) -> None:
+        conn = AsyncMock()
+        # Mock database returning False for EXISTS check (no delegable grant exists)
+        conn.fetchval = AsyncMock(return_value=False)
+        tx = AsyncMock()
+        tx.__aenter__ = AsyncMock(return_value=None)
+        tx.__aexit__ = AsyncMock(return_value=None)
+        conn.transaction = MagicMock(return_value=tx)
+
+        owner = NamespaceContext(namespace_id=uuid.uuid4(), agent_id="owner-agent")
+        other_ns = uuid.uuid4()
+        req = A2AGrantRequest(
+            target_namespace_id=uuid.uuid4(),
+            target_agent_id="visitor",
+            scopes=[
+                A2AScope(
+                    resource_type="namespace",
+                    resource_id=str(other_ns),
+                    permissions=["read"],
+                )
+            ],
+            expires_in_seconds=120,
+        )
+        with pytest.raises(A2AScopeViolationError, match="does not have delegable access"):
+            await create_grant(conn, owner, req)
+
+    @pytest.mark.asyncio
+    async def test_create_grant_other_namespace_with_delegable_grant_succeeds(self) -> None:
+        conn = AsyncMock()
+        # Mock database returning True for EXISTS check (delegable grant exists)
+        conn.fetchval = AsyncMock(return_value=True)
+        tx = AsyncMock()
+        tx.__aenter__ = AsyncMock(return_value=None)
+        tx.__aexit__ = AsyncMock(return_value=None)
+        conn.transaction = MagicMock(return_value=tx)
+
+        owner = NamespaceContext(namespace_id=uuid.uuid4(), agent_id="owner-agent")
+        other_ns = uuid.uuid4()
+        req = A2AGrantRequest(
+            target_namespace_id=uuid.uuid4(),
+            target_agent_id="visitor",
+            scopes=[
+                A2AScope(
+                    resource_type="namespace",
+                    resource_id=str(other_ns),
+                    permissions=["read"],
+                )
+            ],
+            expires_in_seconds=120,
+        )
+        with (
+            patch("nce.a2a.set_namespace_context", new_callable=AsyncMock),
+            patch("nce.event_log.append_event", new_callable=AsyncMock),
+        ):
+            resp = await create_grant(conn, owner, req)
+        assert resp.sharing_token.startswith("nce_a2a_")
+        conn.execute.assert_awaited_once()
+
+
 # ============================================================================
 # mTLS Client Certificate Validation
 # ============================================================================
diff --git a/tests/test_a2a_extensions.py b/tests/test_a2a_extensions.py
index 75d0cd4..b7415af 100644
--- a/tests/test_a2a_extensions.py
+++ b/tests/test_a2a_extensions.py
@@ -51,6 +51,7 @@ def _grant_row_dict(
     status: str = "active",
     expires_at: datetime | None = None,
     created_at: datetime | None = None,
+    can_delegate: bool = False,
 ) -> dict:
     return {
         "id": grant_id or uuid.uuid4(),
@@ -58,10 +59,20 @@ def _grant_row_dict(
         "owner_agent_id": owner_agent,
         "target_namespace_id": consumer_ns,
         "target_agent_id": consumer_agent,
-        "scopes": json.dumps(scopes or [{"resource_type": "namespace", "resource_id": str(uuid.uuid4()), "permissions": ["read"]}]),
+        "scopes": json.dumps(
+            scopes
+            or [
+                {
+                    "resource_type": "namespace",
+                    "resource_id": str(uuid.uuid4()),
+                    "permissions": ["read"],
+                }
+            ]
+        ),
         "status": status,
         "expires_at": expires_at or (datetime.now(timezone.utc) + timedelta(hours=1)),
         "created_at": created_at or datetime.now(timezone.utc),
+        "can_delegate": can_delegate,
     }
 
 
@@ -69,6 +80,7 @@ def _grant_row_dict(
 # 1. Domain Operations Tests (verify_grant_status)
 # ============================================================================
 
+
 @pytest.mark.asyncio
 async def test_verify_grant_status_parameter_bounds() -> None:
     """verify_grant_status must raise ValueError if neither or both parameters are passed."""
@@ -100,7 +112,9 @@ async def test_verify_grant_status_auto_expires() -> None:
     grant_id = uuid.uuid4()
     owner_ns = uuid.uuid4()
     past_expiry = datetime.now(timezone.utc) - timedelta(minutes=5)
-    row = _grant_row_dict(grant_id=grant_id, owner_ns=owner_ns, expires_at=past_expiry, status="active")
+    row = _grant_row_dict(
+        grant_id=grant_id, owner_ns=owner_ns, expires_at=past_expiry, status="active"
+    )
     conn.fetchrow = AsyncMock(return_value=row)
 
     ctx = NamespaceContext(namespace_id=owner_ns, agent_id="agent-caller")
@@ -121,7 +135,9 @@ async def test_verify_grant_status_security_boundaries() -> None:
     owner_ns = uuid.uuid4()
     target_ns = uuid.uuid4()
 
-    row = _grant_row_dict(grant_id=grant_id, owner_ns=owner_ns, consumer_ns=target_ns, consumer_agent="bot-a")
+    row = _grant_row_dict(
+        grant_id=grant_id, owner_ns=owner_ns, consumer_ns=target_ns, consumer_agent="bot-a"
+    )
     conn.fetchrow = AsyncMock(return_value=row)
 
     # 1. Unauthorized caller (different namespace) raises error
@@ -145,7 +161,9 @@ async def test_verify_grant_status_security_boundaries() -> None:
     assert res_target["grant_id"] == str(grant_id)
 
     # 5. Target caller in unrestricted target namespace (target_ns = None) is authorized
-    row_unrestricted = _grant_row_dict(grant_id=grant_id, owner_ns=owner_ns, consumer_ns=None, consumer_agent=None)
+    row_unrestricted = _grant_row_dict(
+        grant_id=grant_id, owner_ns=owner_ns, consumer_ns=None, consumer_agent=None
+    )
     conn.fetchrow = AsyncMock(return_value=row_unrestricted)
     any_ctx = NamespaceContext(namespace_id=uuid.uuid4(), agent_id="any-agent")
     res_any = await verify_grant_status(conn, any_ctx, grant_id=grant_id)
@@ -156,6 +174,7 @@ async def test_verify_grant_status_security_boundaries() -> None:
 # 2. Domain Operations Tests (update_grant_scopes)
 # ============================================================================
 
+
 @pytest.mark.asyncio
 async def test_update_grant_scopes_not_found_or_unauthorized() -> None:
     """update_grant_scopes raises error if grant does not exist or caller is not owner."""
@@ -164,7 +183,16 @@ async def test_update_grant_scopes_not_found_or_unauthorized() -> None:
     owner_ctx = NamespaceContext(namespace_id=uuid.uuid4(), agent_id="owner-agent")
 
     with pytest.raises(A2AAuthorizationError, match="Grant not found or unauthorized."):
-        await update_grant_scopes(conn, owner_ctx, uuid.uuid4(), [A2AScope(resource_type="namespace", resource_id=str(uuid.uuid4()), permissions=["read"])])
+        await update_grant_scopes(
+            conn,
+            owner_ctx,
+            uuid.uuid4(),
+            [
+                A2AScope(
+                    resource_type="namespace", resource_id=str(uuid.uuid4()), permissions=["read"]
+                )
+            ],
+        )
 
 
 @pytest.mark.asyncio
@@ -179,14 +207,34 @@ async def test_update_grant_scopes_inactive_or_expired() -> None:
     row_inactive = _grant_row_dict(grant_id=grant_id, owner_ns=owner_ns, status="revoked")
     conn.fetchrow = AsyncMock(return_value=row_inactive)
     with pytest.raises(A2AAuthorizationError, match="Cannot update scopes of an inactive grant."):
-        await update_grant_scopes(conn, owner_ctx, grant_id, [A2AScope(resource_type="namespace", resource_id=str(uuid.uuid4()), permissions=["read"])])
+        await update_grant_scopes(
+            conn,
+            owner_ctx,
+            grant_id,
+            [
+                A2AScope(
+                    resource_type="namespace", resource_id=str(uuid.uuid4()), permissions=["read"]
+                )
+            ],
+        )
 
     # 2. Expired grant
     past_expiry = datetime.now(timezone.utc) - timedelta(minutes=5)
-    row_expired = _grant_row_dict(grant_id=grant_id, owner_ns=owner_ns, status="active", expires_at=past_expiry)
+    row_expired = _grant_row_dict(
+        grant_id=grant_id, owner_ns=owner_ns, status="active", expires_at=past_expiry
+    )
     conn.fetchrow = AsyncMock(return_value=row_expired)
     with pytest.raises(A2AAuthorizationError, match="Cannot update scopes of an expired grant."):
-        await update_grant_scopes(conn, owner_ctx, grant_id, [A2AScope(resource_type="namespace", resource_id=str(uuid.uuid4()), permissions=["read"])])
+        await update_grant_scopes(
+            conn,
+            owner_ctx,
+            grant_id,
+            [
+                A2AScope(
+                    resource_type="namespace", resource_id=str(uuid.uuid4()), permissions=["read"]
+                )
+            ],
+        )
 
 
 @pytest.mark.asyncio
@@ -203,9 +251,13 @@ async def test_update_grant_scopes_success_strategies() -> None:
     conn.transaction = MagicMock(return_value=tx)
 
     existing_scope_id = str(uuid.uuid4())
-    existing_scopes = [{"resource_type": "namespace", "resource_id": existing_scope_id, "permissions": ["read"]}]
-    row = _grant_row_dict(grant_id=grant_id, owner_ns=owner_ns, scopes=existing_scopes, status="active")
-    
+    existing_scopes = [
+        {"resource_type": "namespace", "resource_id": existing_scope_id, "permissions": ["read"]}
+    ]
+    row = _grant_row_dict(
+        grant_id=grant_id, owner_ns=owner_ns, scopes=existing_scopes, status="active"
+    )
+
     new_scope_id = str(uuid.uuid4())
     new_scopes = [
         A2AScope(resource_type="namespace", resource_id=new_scope_id, permissions=["read"])
@@ -215,12 +267,12 @@ async def test_update_grant_scopes_success_strategies() -> None:
     conn.fetchrow = AsyncMock(return_value=row)
 
     # 1. Replace mode
-    with patch("nce.a2a.set_namespace_context", AsyncMock()) as mock_set_ctx:
+    with patch("nce.a2a.set_namespace_context", AsyncMock()):
         with patch("nce.event_log.append_event", AsyncMock()) as mock_append:
             res = await update_grant_scopes(conn, owner_ctx, grant_id, new_scopes, mode="replace")
             assert len(res["scopes"]) == 1
             assert res["scopes"][0]["resource_id"] == new_scope_id
-            
+
             # Check UPDATE SQL execution
             assert conn.execute.called
             mock_append.assert_called_once()
@@ -238,7 +290,7 @@ async def test_update_grant_scopes_success_strategies() -> None:
             ids = {s["resource_id"] for s in res["scopes"]}
             assert existing_scope_id in ids
             assert new_scope_id in ids
-            
+
             assert conn.execute.called
             mock_append.assert_called_once()
             assert mock_append.call_args[1]["params"]["mode"] == "append"
@@ -256,6 +308,7 @@ async def test_update_grant_scopes_success_strategies() -> None:
 # 3. Domain Operations Tests (inspect_grant)
 # ============================================================================
 
+
 @pytest.mark.asyncio
 async def test_inspect_grant_not_found_or_unauthorized() -> None:
     """inspect_grant raises error if grant does not exist or caller is not owner."""
@@ -288,6 +341,7 @@ async def test_inspect_grant_success() -> None:
 # 4. MCP Handlers Tests
 # ============================================================================
 
+
 @pytest.mark.asyncio
 async def test_handle_a2a_verify_grant_status_mcp() -> None:
     """Verify MCP integration for handle_a2a_verify_grant_status."""
@@ -299,13 +353,11 @@ async def test_handle_a2a_verify_grant_status_mcp() -> None:
         "sharing_token": "bearer-token-abc",
     }
 
-    mock_res = {
-        "grant_id": str(uuid.uuid4()),
-        "status": "active",
-        "scopes": []
-    }
+    mock_res = {"grant_id": str(uuid.uuid4()), "status": "active", "scopes": []}
 
-    with patch("nce.a2a_mcp_handlers.verify_grant_status", AsyncMock(return_value=mock_res)) as mock_domain:
+    with patch(
+        "nce.a2a_mcp_handlers.verify_grant_status", AsyncMock(return_value=mock_res)
+    ) as mock_domain:
         res_str = await a2a_mcp_handlers.handle_a2a_verify_grant_status(engine, args)
         res = json.loads(res_str)
         assert res["status"] == "active"
@@ -327,18 +379,20 @@ async def test_handle_a2a_update_grant_scopes_mcp() -> None:
         "agent_id": "owner-agent",
         "grant_id": str(grant_id),
         "scopes": [
-            {"resource_type": "namespace", "resource_id": str(uuid.uuid4()), "permissions": ["read"]}
+            {
+                "resource_type": "namespace",
+                "resource_id": str(uuid.uuid4()),
+                "permissions": ["read"],
+            }
         ],
         "mode": "append",
     }
 
-    mock_res = {
-        "grant_id": str(grant_id),
-        "status": "updated",
-        "scopes": []
-    }
+    mock_res = {"grant_id": str(grant_id), "status": "updated", "scopes": []}
 
-    with patch("nce.a2a_mcp_handlers.update_grant_scopes", AsyncMock(return_value=mock_res)) as mock_domain:
+    with patch(
+        "nce.a2a_mcp_handlers.update_grant_scopes", AsyncMock(return_value=mock_res)
+    ) as mock_domain:
         res_str = await a2a_mcp_handlers.handle_a2a_update_grant_scopes(engine, args)
         res = json.loads(res_str)
         assert res["status"] == "updated"
@@ -359,13 +413,11 @@ async def test_handle_a2a_inspect_grant_mcp() -> None:
         "grant_id": str(grant_id),
     }
 
-    mock_res = {
-        "grant_id": str(grant_id),
-        "owner_namespace_id": str(owner_ns),
-        "status": "active"
-    }
+    mock_res = {"grant_id": str(grant_id), "owner_namespace_id": str(owner_ns), "status": "active"}
 
-    with patch("nce.a2a_mcp_handlers.inspect_grant", AsyncMock(return_value=mock_res)) as mock_domain:
+    with patch(
+        "nce.a2a_mcp_handlers.inspect_grant", AsyncMock(return_value=mock_res)
+    ) as mock_domain:
         res_str = await a2a_mcp_handlers.handle_a2a_inspect_grant(engine, args)
         res = json.loads(res_str)
         assert res["grant_id"] == str(grant_id)
diff --git a/tests/test_a2a_mcp_handlers.py b/tests/test_a2a_mcp_handlers.py
index 52af5e2..3c9f59d 100644
--- a/tests/test_a2a_mcp_handlers.py
+++ b/tests/test_a2a_mcp_handlers.py
@@ -8,6 +8,7 @@ from __future__ import annotations
 import json
 import logging
 import uuid
+from collections.abc import Generator
 from datetime import datetime, timezone
 from unittest.mock import AsyncMock, MagicMock, patch
 
@@ -73,6 +74,7 @@ def _verified_grant(
     *,
     owner_namespace_id: uuid.UUID | None = None,
     scopes: list[A2AScope] | None = None,
+    can_delegate: bool = False,
 ) -> VerifiedGrant:
     owner_ns = owner_namespace_id or uuid.UUID(OWNER_NS)
     return VerifiedGrant(
@@ -81,6 +83,7 @@ def _verified_grant(
         owner_agent_id="owner-agent",
         scopes=scopes or [_namespace_scope(str(owner_ns))],
         expires_at=datetime.now(timezone.utc),
+        can_delegate=can_delegate,
     )
 
 
@@ -98,6 +101,12 @@ def scopes() -> list[A2AScope]:
     return [_namespace_scope(OWNER_NS)]
 
 
+@pytest.fixture(autouse=True)
+def mock_append_a2a_event() -> Generator[AsyncMock, None, None]:
+    with patch("nce.a2a._append_a2a_event", new_callable=AsyncMock) as m:
+        yield m
+
+
 # ---------------------------------------------------------------------------
 # handle_a2a_revoke_grant — grant_id validation
 # ---------------------------------------------------------------------------
@@ -293,7 +302,7 @@ async def test_query_shared_results_datetime_json_default_str(
 ) -> None:
     verified = _verified_grant(scopes=scopes)
     ts = datetime.now(timezone.utc)
-    engine.semantic_search = AsyncMock(return_value=[{"created_at": ts}])
+    engine.semantic_search = AsyncMock(return_value=[{"memory_id": uuid.uuid4(), "created_at": ts}])
     with (
         patch("nce.a2a_mcp_handlers.verify_token", new_callable=AsyncMock) as verify,
         patch("nce.a2a_mcp_handlers.enforce_scope"),
@@ -404,3 +413,25 @@ async def test_create_grant_returns_json(engine: MagicMock) -> None:
     data = json.loads(out)
     assert data["sharing_token"] == "tok-create"
     assert data["grant_id"]
+
+
+@pytest.mark.asyncio
+async def test_query_shared_writes_a2a_shared_query_event(
+    engine: MagicMock, scopes: list[A2AScope], mock_append_a2a_event: AsyncMock
+) -> None:
+    verified = _verified_grant(scopes=scopes)
+    with (
+        patch("nce.a2a_mcp_handlers.verify_token", new_callable=AsyncMock) as verify,
+        patch("nce.a2a_mcp_handlers.enforce_scope"),
+    ):
+        verify.return_value = verified
+        await a2a_mcp_handlers.handle_a2a_query_shared(engine, _query_shared_base())
+
+    mock_append_a2a_event.assert_called_once()
+    call_args = mock_append_a2a_event.call_args[1]
+    assert call_args["event_type"] == "a2a_shared_query"
+    params = call_args["params"]
+    assert params["consumer_namespace_id"] == CONSUMER_NS
+    assert params["consumer_agent_id"] == "consumer-agent"
+    assert params["grant_id"] == str(verified.grant_id)
+    assert params["query"] == "hello world"
```
