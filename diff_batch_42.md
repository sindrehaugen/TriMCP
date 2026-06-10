# Diff Reference for Batch 42

```diff
diff --git a/RL.md b/RL.md
index ad38953..6455d01 100644
--- a/RL.md
+++ b/RL.md
@@ -49,7 +49,7 @@
 * [DONE] Batch 39 — Subject-scoped `/api/me/*` surface (cross-cutting enabler) [PASSED TAG]
 * [DONE] Batch 40 — Glass Profile endpoint + retract→ATMS (II.3) [PASSED TAG]
 * [DONE] Batch 41 — Accountable Federation: write `a2a_shared_query` + signed provenance (II.6) [PASSED TAG]
-* [OPEN] Batch 42 — A2A security hardening (III.5) [NO TAG]
+* [RUNNING] Batch 42 — A2A security hardening (III.5) [NO TAG]
 * [LOCKED] Batch 43 — Bi-temporal "explain my past decision" (II.5) [NO TAG]
 * [LOCKED] Batch 44 — DECISION + content-free WORM log fork (R2 / VII.5) [NO TAG]
 * [LOCKED] Batch 45 — Envelope-encryption subsystem (II.4a) [NO TAG]
diff --git a/nce/a2a.py b/nce/a2a.py
index 0fc946f..7c7a6e3 100644
--- a/nce/a2a.py
+++ b/nce/a2a.py
@@ -41,7 +41,9 @@ async def _append_a2a_event(
     params: dict,
 ) -> None:
     """Helper to set namespace context and append a2a audit event cleanly."""
-    assert owner_ctx.namespace_id is not None, "Namespace ID cannot be None when writing an A2A event"
+    assert owner_ctx.namespace_id is not None, (
+        "Namespace ID cannot be None when writing an A2A event"
+    )
     await set_namespace_context(conn, owner_ctx.namespace_id)
     from nce.event_log import append_event
 
@@ -101,6 +103,7 @@ class A2AGrantRequest(BaseModel):
     can_delegate: bool = Field(
         False, description="Whether the token can be delegated/re-granted downstream"
     )
+    one_time: bool = Field(False, description="Restrict token to a single successful usage")
 
 
 class A2AGrantResponse(BaseModel):
@@ -124,6 +127,7 @@ class VerifiedGrant(BaseModel):
     scopes: list[A2AScope]
     expires_at: datetime
     can_delegate: bool = False
+    one_time: bool = False
 
 
 class A2AAuthorizationError(Exception):
@@ -687,8 +691,9 @@ async def create_grant(
             INSERT INTO a2a_grants (
                 id, owner_namespace_id, owner_agent_id,
                 target_namespace_id, target_agent_id,
-                scopes, token_hash, status, expires_at, can_delegate
-            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'active', $8, $9)
+                scopes, token_hash, status, expires_at, can_delegate,
+                one_time, usage_count
+            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'active', $8, $9, $10, 0)
             """,
             grant_id,
             owner_ctx.namespace_id,
@@ -699,6 +704,7 @@ async def create_grant(
             token_hash,
             expires_at,
             request.can_delegate,
+            request.one_time,
         )
 
         await _append_a2a_event(
@@ -714,6 +720,7 @@ async def create_grant(
                 "scope_count": len(request.scopes),
                 "expires_at": expires_at.isoformat(),
                 "can_delegate": request.can_delegate,
+                "one_time": request.one_time,
             },
         )
 
@@ -749,7 +756,8 @@ async def verify_token(
         """
         SELECT id, owner_namespace_id, owner_agent_id,
                target_namespace_id, target_agent_id,
-               scopes, expires_at, status, can_delegate
+               scopes, expires_at, status, can_delegate,
+               one_time, usage_count
         FROM a2a_grants
         WHERE token_hash = $1 AND status = 'active'
         """,
@@ -773,6 +781,13 @@ async def verify_token(
         log.info("A2A token auto-expired: grant_id=%s", row["id"])
         raise A2AAuthorizationError("Sharing token has expired.")
 
+    # One-time usage check
+    one_time = row["one_time"] if "one_time" in row else False
+    usage_count = row["usage_count"] if "usage_count" in row else 0
+    if one_time and usage_count >= 1:
+        log.warning("A2A token reuse rejected: grant_id=%s", row["id"])
+        raise A2AAuthorizationError("One-time sharing token has already been used.")
+
     # Namespace binding check
     if row["target_namespace_id"] is not None:
         if row["target_namespace_id"] != consumer_ctx.namespace_id:
@@ -795,6 +810,17 @@ async def verify_token(
             )
             raise A2AAuthorizationError("Token is not valid for this agent.")
 
+    # Successful verification - increment usage count and deactivate if one_time
+    await conn.execute(
+        """
+        UPDATE a2a_grants
+        SET usage_count = usage_count + 1,
+            status = CASE WHEN one_time = true THEN 'expired' ELSE status END
+        WHERE id = $1
+        """,
+        row["id"],
+    )
+
     scopes_data = json.loads(row["scopes"])
     scopes = [A2AScope.model_validate(s) for s in scopes_data]
 
@@ -805,6 +831,7 @@ async def verify_token(
         scopes=scopes,
         expires_at=expires_at,
         can_delegate=row["can_delegate"],
+        one_time=row["one_time"] if "one_time" in row else False,
     )
 
 
@@ -871,7 +898,8 @@ async def list_grants(
         rows = await conn.fetch(
             """
             SELECT id, owner_agent_id, target_namespace_id, target_agent_id,
-                   scopes, status, expires_at, created_at, can_delegate
+                   scopes, status, expires_at, created_at, can_delegate,
+                   one_time, usage_count
             FROM a2a_grants
             WHERE owner_namespace_id = $1
             ORDER BY created_at DESC
@@ -883,7 +911,8 @@ async def list_grants(
         rows = await conn.fetch(
             """
             SELECT id, owner_agent_id, target_namespace_id, target_agent_id,
-                   scopes, status, expires_at, created_at, can_delegate
+                   scopes, status, expires_at, created_at, can_delegate,
+                   one_time, usage_count
             FROM a2a_grants
             WHERE owner_namespace_id = $1
               AND status = 'active'
@@ -906,6 +935,8 @@ async def list_grants(
             "status": row["status"],
             "expires_at": row["expires_at"].isoformat(),
             "can_delegate": row["can_delegate"],
+            "one_time": row["one_time"],
+            "usage_count": row["usage_count"],
             "created_at": row["created_at"].isoformat(),
         }
         for row in rows
@@ -985,7 +1016,8 @@ async def verify_grant_status(
             """
             SELECT id, owner_namespace_id, owner_agent_id,
                    target_namespace_id, target_agent_id,
-                   scopes, expires_at, status, created_at, can_delegate
+                   scopes, expires_at, status, created_at, can_delegate,
+                   one_time, usage_count
             FROM a2a_grants
             WHERE token_hash = $1
             """,
@@ -996,7 +1028,8 @@ async def verify_grant_status(
             """
             SELECT id, owner_namespace_id, owner_agent_id,
                    target_namespace_id, target_agent_id,
-                   scopes, expires_at, status, created_at, can_delegate
+                   scopes, expires_at, status, created_at, can_delegate,
+                   one_time, usage_count
             FROM a2a_grants
             WHERE id = $1
             """,
@@ -1055,6 +1088,8 @@ async def verify_grant_status(
         "status": status,
         "expires_at": expires_at.isoformat(),
         "can_delegate": row["can_delegate"],
+        "one_time": row["one_time"],
+        "usage_count": row["usage_count"],
         "created_at": row["created_at"].isoformat(),
     }
 
@@ -1157,7 +1192,8 @@ async def inspect_grant(
         """
         SELECT id, owner_namespace_id, owner_agent_id,
                target_namespace_id, target_agent_id,
-               scopes, status, expires_at, created_at, can_delegate
+               scopes, status, expires_at, created_at, can_delegate,
+               one_time, usage_count
         FROM a2a_grants
         WHERE id = $1 AND owner_namespace_id = $2
         """,
@@ -1185,5 +1221,7 @@ async def inspect_grant(
         "status": row["status"],
         "expires_at": expires_at.isoformat(),
         "can_delegate": row["can_delegate"],
+        "one_time": row["one_time"],
+        "usage_count": row["usage_count"],
         "created_at": row["created_at"].isoformat(),
     }
diff --git a/nce/a2a_server.py b/nce/a2a_server.py
index 3af8c3f..48c2d68 100644
--- a/nce/a2a_server.py
+++ b/nce/a2a_server.py
@@ -198,6 +198,7 @@ async def _get_task(task_id: str) -> dict[str, Any] | None:
             log.warning("Failed to get task from Redis: %s", exc)
     return _tasks.get(task_id)
 
+
 # ---------------------------------------------------------------------------
 # Engine reference (injected via lifespan)
 # ---------------------------------------------------------------------------
@@ -381,13 +382,36 @@ async def tasks_send(request: Request) -> JSONResponse:
     if _engine is None:
         return JSONResponse({"error": "Engine not connected"}, status_code=503)
 
+    # Sliding-window rate limit check
+    client_ip = request.client.host if request.client else "unknown"
+    key = f"nce:ratelimit:a2a:tasks_send:{client_ip}"
+    redis_client = _engine.redis_client if _engine else None
+    from nce.auth import _check_admin_http_rate_limit
+
+    allowed = await _check_admin_http_rate_limit(
+        redis_client,
+        key,
+        cfg.NCE_A2A_HTTP_RATE_LIMIT,
+        cfg.NCE_A2A_HTTP_RATE_PERIOD,
+    )
+    if not allowed:
+        log.warning("A2A tasks/send rate limit exceeded for IP %s", client_ip)
+        return JSONResponse(
+            _jsonrpc_err(-32013, "Rate limit exceeded", "too_many_requests"),
+            status_code=429,
+        )
+
     # Check Uvicorn process memory usage to prevent OOM degradation
     mem_mb = _get_process_memory_mb()
     mem_limit = getattr(cfg, "NCE_A2A_MEMORY_LIMIT_MB", 2048.0)
     if mem_mb is not None and mem_mb > mem_limit:
         log.warning("Uvicorn memory threshold exceeded: %.1f MB > %.1f MB", mem_mb, mem_limit)
         return JSONResponse(
-            _jsonrpc_err(-32017, "Resource exhaustion: memory threshold exceeded", f"Memory usage: {mem_mb:.1f} MB"),
+            _jsonrpc_err(
+                -32017,
+                "Resource exhaustion: memory threshold exceeded",
+                f"Memory usage: {mem_mb:.1f} MB",
+            ),
             status_code=503,
         )
 
@@ -491,7 +515,9 @@ async def tasks_send(request: Request) -> JSONResponse:
             task = _make_task(task_id, "failed", message=str(exc))
             await _store_task(task_id, task)
             return JSONResponse(
-                _jsonrpc_err(-32016, "Service temporarily degraded (circuit breaker open)", str(exc)),
+                _jsonrpc_err(
+                    -32016, "Service temporarily degraded (circuit breaker open)", str(exc)
+                ),
                 status_code=503,
             )
         except ValueError as exc:
@@ -508,8 +534,13 @@ async def tasks_send(request: Request) -> JSONResponse:
             return JSONResponse({"error": "Internal error"}, status_code=500)
         except BaseException as exc:
             import asyncio
+
             state = "canceled" if isinstance(exc, asyncio.CancelledError) else "failed"
-            msg = "Task cancelled (client disconnected or timed out)" if state == "canceled" else f"Task failed: {type(exc).__name__}"
+            msg = (
+                "Task cancelled (client disconnected or timed out)"
+                if state == "canceled"
+                else f"Task failed: {type(exc).__name__}"
+            )
             task = _make_task(task_id, state, message=msg)
             await asyncio.shield(_store_task(task_id, task))
             raise
diff --git a/nce/config.py b/nce/config.py
index fd5d1dc..d1576f1 100644
--- a/nce/config.py
+++ b/nce/config.py
@@ -433,8 +433,10 @@ class _Config:
     # If unset, the default is ``f"nce_{service}"`` per server.
     NCE_A2A_JWT_AUDIENCE: str = os.getenv(
         "NCE_A2A_JWT_AUDIENCE",
-        "nce_a2a",
-    )
+        "nce_a2a"
+        if os.getenv("NCE_ENV", "dev").strip().lower() not in {"prod", "production"}
+        else "",
+    ).strip()
 
     # --- Phase 3.1: A2A mTLS — client certificate enforcement ---
     # When enabled, the A2A server requires a valid client TLS certificate
@@ -469,6 +471,10 @@ class _Config:
     NCE_A2A_MTLS_STRICT: bool = _bool_env("NCE_A2A_MTLS_STRICT", True)
     NCE_A2A_MTLS_TRUSTED_PROXY_HOP: int = int(os.getenv("NCE_A2A_MTLS_TRUSTED_PROXY_HOP", "1"))
 
+    # A2A tasks/send HTTP rate limits
+    NCE_A2A_HTTP_RATE_LIMIT: int = _int_env("NCE_A2A_HTTP_RATE_LIMIT", 60, minimum=1)
+    NCE_A2A_HTTP_RATE_PERIOD: int = _int_env("NCE_A2A_HTTP_RATE_PERIOD", 60, minimum=1)
+
     # --- Admin server mTLS (B6) ---
     # Mirror of the A2A mTLS block but scoped to the admin surface.
     # All vars default to disabled/empty so existing deployments are unaffected.
@@ -737,6 +743,12 @@ class _Config:
                 "Prefer RS256/ES256 with NCE_JWT_PUBLIC_KEY."
             )
 
+        if cls.IS_PROD and not cls.NCE_A2A_JWT_AUDIENCE:
+            raise RuntimeError(
+                "CRITICAL CONFIGURATION FAILURE: NCE_A2A_JWT_AUDIENCE is required "
+                "in production to prevent token replay across system boundaries."
+            )
+
     @classmethod
     def validate(cls) -> None:
         """
diff --git a/nce/schema.sql b/nce/schema.sql
index 6d1b088..0c962d0 100644
--- a/nce/schema.sql
+++ b/nce/schema.sql
@@ -806,6 +806,8 @@ CREATE TABLE IF NOT EXISTS a2a_grants (
                                      CHECK (status IN ('active', 'revoked', 'expired')),
     expires_at           TIMESTAMPTZ NOT NULL,
     can_delegate         BOOLEAN     NOT NULL DEFAULT false,
+    one_time             BOOLEAN     NOT NULL DEFAULT false,
+    usage_count          INTEGER     NOT NULL DEFAULT 0,
     created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
 );
```
