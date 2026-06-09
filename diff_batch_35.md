# Diff Reference for Batch 35

```diff
diff --git a/RL.md b/RL.md
index 32daa91..99cd82b 100644
--- a/RL.md
+++ b/RL.md
@@ -42,7 +42,7 @@
 * [DONE] Batch 32 — `SettingsStore` accessor with precedence + cache (V.1b) [PASSED TAG]
 * [DONE] Batch 33 — Settings registry metadata (V.1a) [PASSED TAG]
 * [DONE] Batch 34 — `GET /api/admin/settings` (+ `/effective`, `/{key}`) (V.1b) [PASSED TAG]
-* [OPEN] Batch 35 — `PATCH /api/admin/settings` (207) + `config_changed` WORM event (V.1b/V.5) [NO TAG]
+* [RUNNING] Batch 35 — `PATCH /api/admin/settings` (207) + `config_changed` WORM event (V.1b/V.5) [WAITING TAG]
 * [LOCKED] Batch 36 — `/reset`, `/reload`, `/pending` endpoints (V.1b) [NO TAG]
 * [LOCKED] Batch 37 — Honest Uncertainty in search results (II.1) [NO TAG]
 * [LOCKED] Batch 38 — Epistemic Receipts (II.2) [NO TAG]
diff --git a/nce/admin_app.py b/nce/admin_app.py
index 7c65fc4..a439836 100644
--- a/nce/admin_app.py
+++ b/nce/admin_app.py
@@ -161,6 +161,7 @@ def build_admin_routes() -> list[Route]:
         ),
         Route("/api/admin/quotas", endpoint=h.api_admin_quotas, methods=["GET"]),
         Route("/api/admin/settings", endpoint=h.api_admin_settings_list, methods=["GET"]),
+        Route("/api/admin/settings", endpoint=h.api_admin_settings_patch, methods=["PATCH"]),
         Route(
             "/api/admin/settings/effective",
             endpoint=h.api_admin_settings_effective,
diff --git a/nce/admin_handlers/settings.py b/nce/admin_handlers/settings.py
index e908ca0..796f5ad 100644
--- a/nce/admin_handlers/settings.py
+++ b/nce/admin_handlers/settings.py
@@ -59,7 +59,10 @@ def get_effective_value(
         row = db_overrides[key]
         is_secret = row["is_secret"]
         if is_secret:
-            val = "••••set" if row["secret_enc"] else None
+            has_sec = row.get("has_secret")
+            if has_sec is None:
+                has_sec = bool(row.get("secret_enc"))
+            val = "••••set" if has_sec else None
             return val, "store", True
         else:
             val = row["value"]
@@ -102,7 +105,7 @@ async def api_admin_settings_list(request: Any) -> JSONResponse:
         try:
             async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
                 rows = await conn.fetch(
-                    "SELECT key, value, secret_enc, is_secret, updated_by, updated_at FROM settings"
+                    "SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret, updated_by, updated_at FROM settings"
                 )
                 for row in rows:
                     db_overrides[row["key"]] = row
@@ -171,7 +174,7 @@ async def api_admin_settings_effective(request: Any) -> JSONResponse:
     if admin_state.engine.pg_pool:
         try:
             async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
-                rows = await conn.fetch("SELECT key, value, secret_enc, is_secret FROM settings")
+                rows = await conn.fetch("SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret FROM settings")
                 for row in rows:
                     db_overrides[row["key"]] = row
         except Exception as e:
@@ -204,7 +207,7 @@ async def api_admin_settings_get(request: Any) -> JSONResponse:
         try:
             async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
                 db_row = await conn.fetchrow(
-                    "SELECT key, value, secret_enc, is_secret, updated_by, updated_at FROM settings WHERE key = $1",
+                    "SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret, updated_by, updated_at FROM settings WHERE key = $1",
                     key,
                 )
         except Exception as e:
@@ -234,3 +237,299 @@ async def api_admin_settings_get(request: Any) -> JSONResponse:
             key_detail["updated_at"] = db_row["updated_at"].astimezone(UTC).isoformat()
 
     return JSONResponse(key_detail)
+
+
+async def api_admin_settings_patch(request: Any) -> JSONResponse:
+    """PATCH /api/admin/settings
+
+    Batch apply settings updates with per-key status.
+    Enforces optimistic-concurrency guard expected_updated_at (409),
+    production-lock guard prod_locked (403),
+    and server-side metadata validation (422).
+    Appends a signed config_changed WORM event (secrets redacted to set/unset).
+    """
+    if not admin_state.engine:
+        return JSONResponse({"error": "Engine not connected"}, status_code=503)
+
+    try:
+        body = await request.json()
+    except Exception:
+        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
+
+    # Accept both {"settings": { ... }} and direct flat dictionary updates
+    if isinstance(body, dict) and "settings" in body:
+        updates = body["settings"]
+        reason = body.get("reason", "")
+    elif isinstance(body, dict):
+        updates = {k: v for k, v in body.items() if k != "reason"}
+        reason = body.get("reason", "")
+    else:
+        return JSONResponse({"error": "Invalid settings update payload format"}, status_code=422)
+
+    if not isinstance(updates, dict):
+        return JSONResponse({"error": "Settings must be a dictionary"}, status_code=422)
+
+    # Extract actor (agent_id)
+    agent_id = "admin"
+    ns_ctx = getattr(request.state, "namespace_ctx", None)
+    if ns_ctx and ns_ctx.agent_id:
+        agent_id = ns_ctx.agent_id
+    else:
+        agent_id = request.headers.get("x-nce-agent-id") or "admin"
+
+    # Pre-fetch all current DB overrides for the keys in the batch in a single query
+    db_overrides: dict[str, Any] = {}
+    if admin_state.engine.pg_pool:
+        try:
+            async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
+                rows = await conn.fetch(
+                    "SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret, updated_by, updated_at FROM settings WHERE key = ANY($1)",
+                    list(updates.keys()),
+                )
+                for row in rows:
+                    db_overrides[row["key"]] = row
+        except Exception as e:
+            logger.error("Failed to pre-fetch settings overrides: %s", e)
+
+    results: dict[str, dict[str, Any]] = {}
+    has_rejections = False
+    valid_updates: dict[str, dict[str, Any]] = {}
+
+    import uuid
+    from datetime import datetime, timezone
+
+    # First pass: Validate all keys in the batch
+    for key, update_info in updates.items():
+        if key not in REGISTRY:
+            results[key] = {
+                "status": "rejected",
+                "error": f"Setting key '{key}' not found in registry",
+                "status_code": 422,
+            }
+            has_rejections = True
+            continue
+
+        metadata = REGISTRY[key]
+
+        # Extract value and expected_updated_at
+        if isinstance(update_info, dict) and (
+            "value" in update_info or "expected_updated_at" in update_info
+        ):
+            value = update_info.get("value")
+            expected_updated_at = update_info.get("expected_updated_at")
+        else:
+            value = update_info
+            expected_updated_at = None
+
+        # 1. Guardrail check: prod_locked -> 403
+        if metadata.prod_locked:
+            results[key] = {
+                "status": "rejected",
+                "error": f"Setting '{key}' is production locked and cannot be updated dynamically",
+                "status_code": 403,
+            }
+            has_rejections = True
+            continue
+
+        # 2. Optimistic-concurrency guard: stale expected_updated_at -> 409
+        db_row = db_overrides.get(key)
+        db_updated_at = db_row["updated_at"] if db_row else None
+
+        # If expected_updated_at is provided (either as string or None), check it
+        if isinstance(update_info, dict) and "expected_updated_at" in update_info:
+            is_stale = False
+            if expected_updated_at is not None:
+                try:
+                    expected_dt = datetime.fromisoformat(
+                        expected_updated_at.replace("Z", "+00:00")
+                    ).astimezone(timezone.utc)
+                    if db_updated_at is None:
+                        is_stale = True
+                    else:
+                        db_dt = db_updated_at.astimezone(timezone.utc)
+                        if expected_dt != db_dt:
+                            is_stale = True
+                except Exception as e:
+                    results[key] = {
+                        "status": "rejected",
+                        "error": f"Invalid expected_updated_at format: {e}",
+                        "status_code": 422,
+                    }
+                    has_rejections = True
+                    continue
+            else:
+                if db_updated_at is not None:
+                    is_stale = True
+
+            if is_stale:
+                results[key] = {
+                    "status": "rejected",
+                    "error": f"Optimistic lock conflict: Setting '{key}' has been updated since last read",
+                    "status_code": 409,
+                }
+                has_rejections = True
+                continue
+
+        # 3. Secret no-op check: if is_secret is True and value is "••••set", skip validation/update
+        if metadata.is_secret and value == "••••set":
+            valid_updates[key] = {
+                "value": value,
+                "noop": True,
+                "metadata": metadata,
+            }
+            continue
+
+        # 4. Validation check -> 422
+        if not metadata.validator(value):
+            results[key] = {
+                "status": "rejected",
+                "error": f"Validation failed for setting '{key}'",
+                "status_code": 422,
+            }
+            has_rejections = True
+            continue
+
+        valid_updates[key] = {
+            "value": value,
+            "noop": False,
+            "metadata": metadata,
+        }
+
+    # If any key failed validation/concurrency/lock, reject the entire batch
+    if has_rejections:
+        for key in updates.keys():
+            if key not in results:
+                results[key] = {
+                    "status": "rejected",
+                    "error": "Batch aborted due to rejections on other keys",
+                    "status_code": 422,
+                }
+        return JSONResponse({"settings": results}, status_code=207)
+
+    # Second pass: Apply changes transactionally
+    from nce import settings_store
+    from nce.event_log import append_event
+
+    updated_keys: list[str] = []
+    event_changes: dict[str, dict[str, Any]] = {}
+
+    def redact_value(val: Any, is_secret: bool) -> Any:
+        if not is_secret:
+            return val
+        if val is not None and val != "":
+            return "••••set"
+        return "••••unset"
+
+    try:
+        async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
+            async with conn.transaction():
+                for key, info in valid_updates.items():
+                    if info.get("noop"):
+                        metadata = info["metadata"]
+                        if metadata.reload_class == "HOT":
+                            status = "applied"
+                        elif metadata.reload_class == "WARM":
+                            status = "pending_reload"
+                        else:
+                            status = "pending_restart"
+                        results[key] = {"status": status}
+                        continue
+
+                    metadata = info["metadata"]
+                    value = info["value"]
+
+                    db_row = db_overrides.get(key)
+                    if db_row:
+                        old_raw = db_row["value"]
+                        if db_row["is_secret"]:
+                            old_val = "••••set" if db_row["has_secret"] else None
+                        else:
+                            if isinstance(old_raw, str):
+                                try:
+                                    old_val = json.loads(old_raw)
+                                except Exception:
+                                    old_val = old_raw
+                            else:
+                                old_val = old_raw
+                    else:
+                        old_val = getattr(cfg, key, None)
+
+                    await settings_store.set(
+                        key,
+                        value,
+                        is_secret=metadata.is_secret,
+                        section=metadata.section,
+                        updated_by=agent_id,
+                        conn=conn,
+                    )
+                    updated_keys.append(key)
+
+                    old_redacted = redact_value(old_val, metadata.is_secret)
+                    new_redacted = redact_value(value, metadata.is_secret)
+
+                    event_changes[key] = {
+                        "old_value": old_redacted,
+                        "new_value": new_redacted,
+                    }
+
+                    if metadata.reload_class == "HOT":
+                        status = "applied"
+                    elif metadata.reload_class == "WARM":
+                        status = "pending_reload"
+                    else:
+                        status = "pending_restart"
+                    results[key] = {"status": status}
+
+                if updated_keys:
+                    ns_id = None
+                    if ns_ctx and ns_ctx.namespace_id:
+                        ns_id = ns_ctx.namespace_id
+
+                    if not ns_id:
+                        ns_id_raw = await conn.fetchval(
+                            "SELECT id FROM namespaces WHERE slug = '_global_legacy'"
+                        )
+                        if not ns_id_raw:
+                            ns_id_raw = await conn.fetchval(
+                                "SELECT id FROM namespaces ORDER BY created_at ASC LIMIT 1"
+                            )
+                        if ns_id_raw:
+                            ns_id = (
+                                uuid.UUID(str(ns_id_raw))
+                                if not isinstance(ns_id_raw, uuid.UUID)
+                                else ns_id_raw
+                            )
+
+                    if not ns_id:
+                        raise RuntimeError("No namespace found to log config_changed event")
+
+                    await append_event(
+                        conn=conn,
+                        namespace_id=ns_id,
+                        agent_id=agent_id,
+                        event_type="config_changed",
+                        params={
+                            "actor": agent_id,
+                            "reason": reason,
+                            "changes": event_changes,
+                        },
+                    )
+
+    except Exception as exc:
+        logger.exception("Failed to apply settings update transactionally: %s", exc)
+        return JSONResponse({"error": f"Database transaction failed: {exc}"}, status_code=500)
+
+    # Post-commit: Invalidate and populate Redis + local cache
+    active_redis = admin_state.engine.redis_client
+    if active_redis and updated_keys:
+        try:
+            for key in updated_keys:
+                await active_redis.hdel("nce:settings:overrides", key)
+                await active_redis.publish("nce:settings:invalidate", key)
+        except Exception as e:
+            logger.warning("Failed to invalidate Redis cache post-commit: %s", e)
+
+    for key in updated_keys:
+        settings_store._local_cache.pop(key, None)
+
+    return JSONResponse({"settings": results}, status_code=207)
diff --git a/nce/event_types.py b/nce/event_types.py
index b0799e3..ab76811 100644
--- a/nce/event_types.py
+++ b/nce/event_types.py
@@ -55,6 +55,7 @@ EventType = Literal[
     "saga_recovered",  # cron saga recovery: pg_committed saga finalized, not rolled back
     "chain_verification_failed",
     "atms_cascade",
+    "config_changed",
 ]
 
 VALID_EVENT_TYPES: Final[frozenset[str]] = frozenset(get_args(EventType))
@@ -114,6 +115,7 @@ EVENT_REQUIRED_PARAM_KEYS: Final[dict[str, frozenset[str]]] = {
     "saga_recovered": frozenset({"memory_id", "saga_id", "recovery_action", "reason"}),
     "chain_verification_failed": frozenset({"first_break", "reason"}),
     "atms_cascade": frozenset({"contradiction_id", "invalidated_memory_id", "invalidated_ids"}),
+    "config_changed": frozenset({"actor", "changes"}),
 }
 
 EVENT_FORBIDDEN_PARAM_KEYS: Final[dict[str, frozenset[str]]] = {
diff --git a/nce/replay.py b/nce/replay.py
index a663cc7..baf2a7e 100644
--- a/nce/replay.py
+++ b/nce/replay.py
@@ -1057,6 +1057,7 @@ _additional_fork_provenance_types: tuple[str, ...] = (
     "signing_key_rotated",
     "chain_verification_failed",
     "atms_cascade",
+    "config_changed",
 )
 for _fork_et in _additional_fork_provenance_types:
     assert _fork_et not in _HANDLER_REGISTRY, (
diff --git a/nce/settings_store.py b/nce/settings_store.py
index ff12d19..6824b5f 100644
--- a/nce/settings_store.py
+++ b/nce/settings_store.py
@@ -214,6 +214,7 @@ async def set(
     *,
     pool: Any = None,
     redis_client: Any = None,
+    conn: Any = None,
 ) -> None:
     """
     Set a configuration override in the database.
@@ -234,9 +235,29 @@ async def set(
         secret_enc = None
         db_value = json.dumps(value)
 
-    if active_pool:
-        async with active_pool.acquire(timeout=10.0) as conn:
-            await conn.execute(
+    if conn:
+        await conn.execute(
+            """
+            INSERT INTO settings (key, value, secret_enc, is_secret, section, updated_by, updated_at)
+            VALUES ($1, $2::jsonb, $3, $4, $5, $6, NOW())
+            ON CONFLICT (key) DO UPDATE
+            SET value = EXCLUDED.value,
+                secret_enc = EXCLUDED.secret_enc,
+                is_secret = EXCLUDED.is_secret,
+                section = COALESCE(EXCLUDED.section, settings.section),
+                updated_by = EXCLUDED.updated_by,
+                updated_at = NOW()
+            """,
+            key,
+            db_value,
+            secret_enc,
+            is_secret,
+            section,
+            updated_by,
+        )
+    elif active_pool:
+        async with active_pool.acquire(timeout=10.0) as conn_to_use:
+            await conn_to_use.execute(
                 """
                 INSERT INTO settings (key, value, secret_enc, is_secret, section, updated_by, updated_at)
                 VALUES ($1, $2::jsonb, $3, $4, $5, $6, NOW())
@@ -258,21 +279,22 @@ async def set(
     else:
         raise RuntimeError("No database pool available to save setting.")
 
-    # Invalidate and populate Redis
-    if active_redis:
-        try:
-            cache_payload = {
-                "is_secret": is_secret,
-                "secret_enc_hex": secret_enc.hex() if secret_enc else None,
-                "value": value if not is_secret else None,
-            }
-            await active_redis.hset("nce:settings:overrides", key, json.dumps(cache_payload))
-            await active_redis.publish("nce:settings:invalidate", key)
-        except Exception as e:
-            logger.warning("Failed to update Redis cache for setting %s: %s", key, e)
+    # Invalidate and populate Redis if not inside a connection transaction
+    if not conn:
+        if active_redis:
+            try:
+                cache_payload = {
+                    "is_secret": is_secret,
+                    "secret_enc_hex": secret_enc.hex() if secret_enc else None,
+                    "value": value if not is_secret else None,
+                }
+                await active_redis.hset("nce:settings:overrides", key, json.dumps(cache_payload))
+                await active_redis.publish("nce:settings:invalidate", key)
+            except Exception as e:
+                logger.warning("Failed to update Redis cache for setting %s: %s", key, e)
 
-    # Invalidate local cache
-    _local_cache.pop(key, None)
+        # Invalidate local cache
+        _local_cache.pop(key, None)
 
 
 async def reset(key: str, *, pool: Any = None, redis_client: Any = None) -> None:
diff --git a/tests/test_admin_settings.py b/tests/test_admin_settings.py
index 3854b26..96b197a 100644
--- a/tests/test_admin_settings.py
+++ b/tests/test_admin_settings.py
@@ -29,6 +29,10 @@ def bypass_lifespan():
 @pytest.fixture
 def mock_conn():
     c = AsyncMock()
+    tx = MagicMock()
+    tx.__aenter__ = AsyncMock()
+    tx.__aexit__ = AsyncMock()
+    c.transaction = MagicMock(return_value=tx)
     return c
 
 
@@ -228,3 +232,211 @@ def test_get_single_setting_not_found(mock_engine, mock_conn):
             with TestClient(app) as client:
                 resp = client.get("/api/admin/settings/NON_EXISTENT_KEY", headers=headers)
             assert resp.status_code == 404
+
+
+def test_patch_settings_success(mock_engine, mock_conn):
+    """Verify PATCH /api/admin/settings successfully updates HOT settings and logs config_changed event."""
+    mock_conn.fetch.return_value = []
+    mock_conn.fetchrow.return_value = None
+    mock_conn.fetchval.return_value = "00000000-0000-0000-0000-000000000000"  # namespace_id
+    mock_conn.execute.return_value = "UPDATE 1"
+
+    with patch("nce.admin_state.engine", mock_engine):
+        key = cfg.NCE_API_KEY or "test_key"
+        with patch.object(cfg, "NCE_API_KEY", key):
+            ts = int(time.time())
+
+            payload = {
+                "settings": {
+                    "NCE_ADMIN_HTTP_RATE_LIMIT": {"value": 50, "expected_updated_at": None}
+                },
+                "reason": "Test patch",
+            }
+
+            import json
+
+            body_bytes = json.dumps(payload).encode("utf-8")
+            headers = admin_hmac_headers(
+                hex_key_material=key,
+                method="PATCH",
+                path="/api/admin/settings",
+                timestamp=ts,
+                body=body_bytes,
+            )
+
+            with TestClient(app) as client:
+                resp = client.patch("/api/admin/settings", content=body_bytes, headers=headers)
+
+            assert resp.status_code == 207
+            data = resp.json()
+            assert "settings" in data
+            assert "NCE_ADMIN_HTTP_RATE_LIMIT" in data["settings"]
+            assert data["settings"]["NCE_ADMIN_HTTP_RATE_LIMIT"]["status"] == "applied"
+
+
+def test_patch_settings_prod_locked_rejection(mock_engine, mock_conn):
+    """Verify PATCH /api/admin/settings rejects prod_locked settings with 403-class response in Multi-Status."""
+    mock_conn.fetch.return_value = []
+
+    with patch("nce.admin_state.engine", mock_engine):
+        key = cfg.NCE_API_KEY or "test_key"
+        with patch.object(cfg, "NCE_API_KEY", key):
+            ts = int(time.time())
+
+            payload = {"settings": {"NCE_MASTER_KEY": {"value": "new_master_key"}}}
+
+            import json
+
+            body_bytes = json.dumps(payload).encode("utf-8")
+            headers = admin_hmac_headers(
+                hex_key_material=key,
+                method="PATCH",
+                path="/api/admin/settings",
+                timestamp=ts,
+                body=body_bytes,
+            )
+
+            with TestClient(app) as client:
+                resp = client.patch("/api/admin/settings", content=body_bytes, headers=headers)
+
+            assert resp.status_code == 207
+            data = resp.json()
+            assert "settings" in data
+            assert "NCE_MASTER_KEY" in data["settings"]
+            assert data["settings"]["NCE_MASTER_KEY"]["status"] == "rejected"
+            assert data["settings"]["NCE_MASTER_KEY"]["status_code"] == 403
+
+
+def test_patch_settings_optimistic_lock_rejection(mock_engine, mock_conn):
+    """Verify PATCH /api/admin/settings rejects stale expected_updated_at with 409-class response."""
+    import datetime
+
+    db_time = datetime.datetime.now(datetime.timezone.utc)
+
+    # Mock DB to return an existing override with different updated_at
+    mock_conn.fetch.return_value = [
+        {
+            "key": "NCE_ADMIN_HTTP_RATE_LIMIT",
+            "value": "100",
+            "secret_enc": None,
+            "is_secret": False,
+            "updated_by": "someone",
+            "updated_at": db_time,
+        }
+    ]
+
+    with patch("nce.admin_state.engine", mock_engine):
+        key = cfg.NCE_API_KEY or "test_key"
+        with patch.object(cfg, "NCE_API_KEY", key):
+            ts = int(time.time())
+
+            # Client expects updated_at to be db_time minus 1 hour (stale)
+            stale_time = (db_time - datetime.timedelta(hours=1)).isoformat()
+            payload = {
+                "settings": {
+                    "NCE_ADMIN_HTTP_RATE_LIMIT": {"value": 50, "expected_updated_at": stale_time}
+                }
+            }
+
+            import json
+
+            body_bytes = json.dumps(payload).encode("utf-8")
+            headers = admin_hmac_headers(
+                hex_key_material=key,
+                method="PATCH",
+                path="/api/admin/settings",
+                timestamp=ts,
+                body=body_bytes,
+            )
+
+            with TestClient(app) as client:
+                resp = client.patch("/api/admin/settings", content=body_bytes, headers=headers)
+
+            assert resp.status_code == 207
+            data = resp.json()
+            assert data["settings"]["NCE_ADMIN_HTTP_RATE_LIMIT"]["status"] == "rejected"
+            assert data["settings"]["NCE_ADMIN_HTTP_RATE_LIMIT"]["status_code"] == 409
+
+
+def test_patch_settings_validation_failure(mock_engine, mock_conn):
+    """Verify PATCH /api/admin/settings rejects invalid values with 422-class response."""
+    mock_conn.fetch.return_value = []
+
+    with patch("nce.admin_state.engine", mock_engine):
+        key = cfg.NCE_API_KEY or "test_key"
+        with patch.object(cfg, "NCE_API_KEY", key):
+            ts = int(time.time())
+
+            # NCE_ADMIN_HTTP_RATE_LIMIT expects an integer, pass a string
+            payload = {"settings": {"NCE_ADMIN_HTTP_RATE_LIMIT": {"value": "not_an_int"}}}
+
+            import json
+
+            body_bytes = json.dumps(payload).encode("utf-8")
+            headers = admin_hmac_headers(
+                hex_key_material=key,
+                method="PATCH",
+                path="/api/admin/settings",
+                timestamp=ts,
+                body=body_bytes,
+            )
+
+            with TestClient(app) as client:
+                resp = client.patch("/api/admin/settings", content=body_bytes, headers=headers)
+
+            assert resp.status_code == 207
+            data = resp.json()
+            assert data["settings"]["NCE_ADMIN_HTTP_RATE_LIMIT"]["status"] == "rejected"
+            assert data["settings"]["NCE_ADMIN_HTTP_RATE_LIMIT"]["status_code"] == 422
+
+
+def test_patch_settings_secret_redaction(mock_engine, mock_conn):
+    """Verify PATCH /api/admin/settings masks secret inputs to '••••set' in config_changed log."""
+    mock_conn.fetch.return_value = []
+    mock_conn.fetchrow.return_value = None
+    mock_conn.fetchval.return_value = "00000000-0000-0000-0000-000000000000"
+
+    captured_params = None
+    import uuid
+
+    async def mock_append_event(*args, **kwargs):
+        nonlocal captured_params
+        if kwargs.get("event_type") == "config_changed":
+            captured_params = kwargs.get("params")
+        import datetime
+
+        from nce.event_log import AppendResult
+
+        return AppendResult(
+            event_id=uuid.uuid4(),
+            event_seq=1,
+            occurred_at=datetime.datetime.now(datetime.timezone.utc),
+        )
+
+    with (
+        patch("nce.admin_state.engine", mock_engine),
+        patch("nce.event_log.append_event", mock_append_event),
+    ):
+        key = cfg.NCE_API_KEY or "test_key"
+        with patch.object(cfg, "NCE_API_KEY", key):
+            ts = int(time.time())
+
+            payload = {"settings": {"NCE_GEMINI_API_KEY": {"value": "secret_gemini_key"}}}
+
+            import json
+
+            body_bytes = json.dumps(payload).encode("utf-8")
+            headers = admin_hmac_headers(
+                hex_key_material=key,
+                method="PATCH",
+                path="/api/admin/settings",
+                timestamp=ts,
+                body=body_bytes,
+            )
+
+            with TestClient(app) as client:
+                resp = client.patch("/api/admin/settings", content=body_bytes, headers=headers)
+
+            assert resp.status_code == 207
+            assert captured_params is not None
+            assert captured_params["changes"]["NCE_GEMINI_API_KEY"]["new_value"] == "••••set"
```
