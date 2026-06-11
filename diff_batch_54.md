# Diff Reference for Batch 54

```diff
diff --git a/nce/admin_app.py b/nce/admin_app.py
index bee734f..c57af5d 100644
--- a/nce/admin_app.py
+++ b/nce/admin_app.py
@@ -182,6 +182,11 @@ def build_admin_routes() -> list[Route]:
             endpoint=h.api_admin_settings_reload,
             methods=["POST"],
         ),
+        Route(
+            "/api/admin/settings/rollback",
+            endpoint=h.api_admin_settings_rollback,
+            methods=["POST"],
+        ),
         Route(
             "/api/admin/settings/{key}",
             endpoint=h.api_admin_settings_get,
diff --git a/nce/admin_handlers/settings.py b/nce/admin_handlers/settings.py
index 7962676..1787b75 100644
--- a/nce/admin_handlers/settings.py
+++ b/nce/admin_handlers/settings.py
@@ -162,14 +162,110 @@ async def api_admin_settings_list(request: Any) -> JSONResponse:
     return JSONResponse({"sections": response_sections})
 
 
+def _baseline_effective_value(key: str, metadata: SettingMetadata) -> Any:
+    """Return the env/default effective value for *key*, ignoring any DB override.
+
+    Secrets are masked to ``••••set``/``None`` by ``get_effective_value`` — the raw
+    secret value is never produced here.
+    """
+    value, _, _ = get_effective_value(key, metadata, {})
+    return value
+
+
+def _coerce_event_params(raw: Any) -> dict[str, Any]:
+    """Normalise an ``event_log.params`` column (jsonb may arrive as str) to a dict."""
+    if raw is None:
+        return {}
+    if isinstance(raw, dict):
+        return raw
+    if isinstance(raw, str):
+        try:
+            parsed = json.loads(raw)
+            return parsed if isinstance(parsed, dict) else {}
+        except (json.JSONDecodeError, TypeError):
+            return {}
+    return {}
+
+
+async def _reconstruct_effective_as_of(conn: Any, as_of_dt: Any) -> dict[str, Any]:
+    """Fold ordered ``config_changed``/``config_reset`` WORM events up to *as_of_dt*
+    over the env/default baseline, returning the effective (secrets-masked) config.
+
+    Only the redacted ``new_value`` recorded on each ``config_changed`` event is
+    applied — secret *values* are never reconstructed from the log (they are stored
+    only as ``••••set``/``••••unset`` lifecycle tokens). A ``config_reset`` event
+    reverts the affected keys back to their env/default baseline.
+    """
+    effective: dict[str, Any] = {
+        key: _baseline_effective_value(key, metadata) for key, metadata in REGISTRY.items()
+    }
+
+    rows = await conn.fetch(
+        """
+        SELECT event_type, params, event_seq, occurred_at
+        FROM event_log
+        WHERE event_type IN ('config_changed', 'config_reset')
+          AND occurred_at <= $1
+        ORDER BY occurred_at ASC, event_seq ASC
+        """,
+        as_of_dt,
+    )
+
+    for row in rows:
+        params = _coerce_event_params(row["params"])
+        if row["event_type"] == "config_changed":
+            changes = params.get("changes")
+            if isinstance(changes, dict):
+                for key, change in changes.items():
+                    if key in effective and isinstance(change, dict) and "new_value" in change:
+                        effective[key] = change["new_value"]
+        elif row["event_type"] == "config_reset":
+            resets = params.get("resets")
+            if isinstance(resets, dict):
+                for key in resets:
+                    if key in REGISTRY:
+                        effective[key] = _baseline_effective_value(key, REGISTRY[key])
+
+    return effective
+
+
 async def api_admin_settings_effective(request: Any) -> JSONResponse:
-    """GET /api/admin/settings/effective
+    """GET /api/admin/settings/effective[?as_of=T]
 
     Returns a flat key-value object of all settings with effective values (secrets masked).
+
+    When ``as_of`` (ISO 8601 timestamp) is supplied, the effective config is
+    reconstructed by folding the ordered ``config_changed``/``config_reset`` WORM
+    events up to ``T`` over the env/default baseline — the config analog of
+    ``semantic_search(as_of=)``. Non-secret values reconstruct exactly; secret
+    values are never recovered from the log (only the set/unset lifecycle token).
     """
     if not admin_state.engine:
         return JSONResponse({"error": "Engine not connected"}, status_code=503)
 
+    as_of_raw = request.query_params.get("as_of")
+    if as_of_raw is not None:
+        from nce.temporal import parse_as_of
+
+        try:
+            as_of_dt = parse_as_of(as_of_raw)
+        except ValueError as e:
+            return JSONResponse({"error": str(e)}, status_code=422)
+
+        if not admin_state.engine.pg_pool:
+            return JSONResponse({"error": "Database not available"}, status_code=503)
+
+        try:
+            async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
+                effective_dict = await _reconstruct_effective_as_of(conn, as_of_dt)
+        except Exception as e:
+            logger.exception("Failed to reconstruct effective config as_of: %s", e)
+            return JSONResponse({"error": f"Database query failed: {e}"}, status_code=500)
+
+        return JSONResponse(
+            {"as_of": as_of_dt.isoformat() if as_of_dt else None, "effective": effective_dict}
+        )
+
     db_overrides: dict[str, Any] = {}
     if admin_state.engine.pg_pool:
         try:
@@ -190,6 +286,238 @@ async def api_admin_settings_effective(request: Any) -> JSONResponse:
     return JSONResponse(effective_dict)
 
 
+async def handle_explain_config_change(engine: Any, arguments: dict[str, Any]) -> str:
+    """[MCP] explain_config_change(key) — return a config key's full change history.
+
+    Folds the ordered ``config_changed``/``config_reset`` WORM events that touched
+    *key*, returning one entry per change (timestamp, actor, reason, old→new,
+    reset-to-baseline) — the audit companion to ``effective?as_of=T``. Secret
+    values are never returned: only the recorded ``set``/``unset``/``rotated``
+    redaction tokens already stored on the event.
+    """
+    key = arguments.get("key")
+    if not key or not isinstance(key, str):
+        raise ValueError("explain_config_change requires a string 'key' argument")
+    if key not in REGISTRY:
+        return json.dumps({"key": key, "error": "Setting key not found in registry"})
+
+    metadata = REGISTRY[key]
+    pool = getattr(engine, "pg_pool", None)
+    if pool is None:
+        raise RuntimeError("Database pool not available")
+
+    async with pool.acquire(timeout=10.0) as conn:
+        rows = await conn.fetch(
+            """
+            SELECT event_id, event_type, agent_id, params, event_seq, occurred_at
+            FROM event_log
+            WHERE event_type IN ('config_changed', 'config_reset')
+            ORDER BY occurred_at ASC, event_seq ASC
+            """
+        )
+
+    history: list[dict[str, Any]] = []
+    for row in rows:
+        params = _coerce_event_params(row["params"])
+        occurred_at = row["occurred_at"]
+        occurred_iso = occurred_at.isoformat() if occurred_at is not None else None
+        if row["event_type"] == "config_changed":
+            changes = params.get("changes")
+            if isinstance(changes, dict) and key in changes and isinstance(changes[key], dict):
+                change = changes[key]
+                history.append(
+                    {
+                        "event_id": str(row["event_id"]),
+                        "event_seq": row["event_seq"],
+                        "occurred_at": occurred_iso,
+                        "event_type": "config_changed",
+                        "actor": params.get("actor"),
+                        "reason": params.get("reason"),
+                        "old_value": change.get("old_value"),
+                        "new_value": change.get("new_value"),
+                    }
+                )
+        elif row["event_type"] == "config_reset":
+            resets = params.get("resets")
+            if isinstance(resets, dict) and key in resets:
+                reset = resets[key] if isinstance(resets[key], dict) else {}
+                history.append(
+                    {
+                        "event_id": str(row["event_id"]),
+                        "event_seq": row["event_seq"],
+                        "occurred_at": occurred_iso,
+                        "event_type": "config_reset",
+                        "actor": params.get("actor"),
+                        "reverted_to_source": reset.get("source"),
+                        "new_value": reset.get("new_value"),
+                    }
+                )
+
+    return json.dumps(
+        {
+            "key": key,
+            "is_secret": metadata.is_secret,
+            "section": metadata.section,
+            "change_count": len(history),
+            "history": history,
+        }
+    )
+
+
+class _PatchRequestProxy:
+    """Minimal request shim that delegates to *base* but serves a synthesized JSON body.
+
+    Used so a rollback can apply its inverse change-set through the *normal* PATCH
+    path (``api_admin_settings_patch``) — preserving every guardrail (prod-locked
+    skip, validation, optimistic-lock, COLD→pending_restart, signed config_changed
+    event) rather than re-implementing the write.
+    """
+
+    def __init__(self, base: Any, body: dict[str, Any]) -> None:
+        self._base = base
+        self._body = body
+
+    async def json(self) -> dict[str, Any]:
+        return self._body
+
+    @property
+    def state(self) -> Any:
+        return self._base.state
+
+    @property
+    def headers(self) -> Any:
+        return self._base.headers
+
+
+async def api_admin_settings_rollback(request: Any) -> JSONResponse:
+    """POST /api/admin/settings/rollback { as_of, sections?, dry_run }
+
+    Config time-travel rollback (V.6). Reconstructs the effective config at ``as_of``,
+    diffs it against the current effective config, and computes the inverse change-set
+    that would restore the past state.
+
+    - ``dry_run`` (default True) returns the proposed diff for a confirm-modal.
+    - On apply (``dry_run: false``), the inverse change-set is pushed through the
+      normal PATCH path so every guardrail still holds; the rollback is itself
+      recorded as a ``config_changed`` event (``reason: "rollback to T"``).
+
+    Guardrails: prod-locked keys are never silently re-enabled (skipped); secrets
+    cannot be auto-restored from the WORM log (their values are unrecoverable by
+    design) — keys whose secret changed since ``as_of`` are *flagged* for manual
+    re-entry rather than fabricated.
+    """
+    if not admin_state.engine:
+        return JSONResponse({"error": "Engine not connected"}, status_code=503)
+
+    try:
+        body = await request.json()
+    except Exception:
+        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
+
+    if not isinstance(body, dict) or "as_of" not in body:
+        return JSONResponse({"error": "Payload must contain 'as_of'"}, status_code=422)
+
+    from nce.temporal import parse_as_of
+
+    try:
+        as_of_dt = parse_as_of(body["as_of"])
+    except ValueError as e:
+        return JSONResponse({"error": str(e)}, status_code=422)
+    if as_of_dt is None:
+        return JSONResponse({"error": "'as_of' must be a timestamp"}, status_code=422)
+
+    section_filter = body.get("sections")
+    if section_filter is not None and (
+        not isinstance(section_filter, list) or not all(isinstance(s, str) for s in section_filter)
+    ):
+        return JSONResponse({"error": "'sections' must be a list of strings"}, status_code=422)
+    section_set = set(section_filter) if section_filter else None
+
+    dry_run = body.get("dry_run", True)
+    if not isinstance(dry_run, bool):
+        return JSONResponse({"error": "'dry_run' must be a boolean"}, status_code=422)
+
+    if not admin_state.engine.pg_pool:
+        return JSONResponse({"error": "Database not available"}, status_code=503)
+
+    # Reconstruct past config + read current DB overrides for the live effective view.
+    try:
+        async with admin_state.engine.pg_pool.acquire(timeout=10.0) as conn:
+            past = await _reconstruct_effective_as_of(conn, as_of_dt)
+            db_overrides: dict[str, Any] = {}
+            rows = await conn.fetch(
+                "SELECT key, value, (secret_enc IS NOT NULL) AS has_secret, is_secret FROM settings"
+            )
+            for row in rows:
+                db_overrides[row["key"]] = row
+    except Exception as e:
+        logger.exception("Failed to load config for rollback: %s", e)
+        return JSONResponse({"error": f"Database query failed: {e}"}, status_code=500)
+
+    current = {
+        key: get_effective_value(key, metadata, db_overrides)[0]
+        for key, metadata in REGISTRY.items()
+    }
+
+    applied_diff: dict[str, dict[str, Any]] = {}
+    skipped: dict[str, dict[str, Any]] = {}
+    flagged_secrets: dict[str, dict[str, Any]] = {}
+
+    for key, metadata in REGISTRY.items():
+        if section_set is not None and metadata.section not in section_set:
+            continue
+        target = past[key]
+        cur = current[key]
+        if target == cur:
+            continue  # no inverse change required
+
+        if metadata.prod_locked:
+            skipped[key] = {
+                "reason": "prod_locked",
+                "current_value": cur,
+                "would_restore_to": target,
+            }
+            continue
+
+        if metadata.is_secret:
+            # Secret values are unrecoverable from the WORM log; never fabricate.
+            flagged_secrets[key] = {
+                "reason": "secret_rotated_since_as_of",
+                "current_value": cur,
+                "target_token": target,
+            }
+            continue
+
+        applied_diff[key] = {"old_value": cur, "new_value": target}
+
+    proposal: dict[str, Any] = {
+        "as_of": as_of_dt.isoformat(),
+        "dry_run": dry_run,
+        "diff": applied_diff,
+        "skipped_prod_locked": skipped,
+        "flagged_secrets": flagged_secrets,
+    }
+
+    if dry_run:
+        return JSONResponse(proposal)
+
+    if not applied_diff:
+        return JSONResponse({**proposal, "settings": {}, "note": "No applicable changes"})
+
+    # Apply the inverse (non-secret) change-set through the normal PATCH path so
+    # all guardrails/validation/WORM logging still apply.
+    patch_body = {
+        "settings": {k: {"value": v["new_value"]} for k, v in applied_diff.items()},
+        "reason": f"rollback to {as_of_dt.isoformat()}",
+    }
+    patch_resp = await api_admin_settings_patch(_PatchRequestProxy(request, patch_body))
+    patch_payload = json.loads(bytes(patch_resp.body).decode("utf-8"))
+    return JSONResponse(
+        {**proposal, "settings": patch_payload.get("settings", patch_payload)},
+        status_code=patch_resp.status_code,
+    )
+
+
 async def api_admin_settings_get(request: Any) -> JSONResponse:
     """GET /api/admin/settings/{key}
 
diff --git a/nce/mcp_stdio_tools.py b/nce/mcp_stdio_tools.py
index bfd1a85..ebc1411 100644
--- a/nce/mcp_stdio_tools.py
+++ b/nce/mcp_stdio_tools.py
@@ -979,6 +979,30 @@ TOOLS = [
             "required": ["namespace_id", "admin_api_key"],
         },
     ),
+    Tool(
+        name="explain_config_change",
+        description=(
+            "[Phase V.6] Config time-travel audit — return a configuration key's full "
+            "change history by folding the ordered config_changed/config_reset WORM "
+            "events that touched it (timestamp, actor, reason, old->new for non-secrets). "
+            "Secret values are never returned: only the recorded set/unset/rotated "
+            "lifecycle token. The audit companion to GET /api/admin/settings/effective?as_of=T."
+        ),
+        inputSchema={
+            "type": "object",
+            "properties": {
+                "key": {
+                    "type": "string",
+                    "description": "Registry configuration key whose change history to return.",
+                },
+                "admin_api_key": {
+                    "type": "string",
+                    "description": "Server-side admin API key for elevated access",
+                },
+            },
+            "required": ["key", "admin_api_key"],
+        },
+    ),
     Tool(
         name="a2a_create_grant",
         description=(
diff --git a/nce/tool_registry.py b/nce/tool_registry.py
index d1aeef0..4b5ec7e 100644
--- a/nce/tool_registry.py
+++ b/nce/tool_registry.py
@@ -35,6 +35,7 @@ from nce import (
     replay_mcp_handlers,
     snapshot_mcp_handlers,
 )
+from nce.admin_handlers import settings as settings_mcp_handlers
 from nce.vertical_modules.dynamics365 import mcp_handlers as d365_mcp_handlers
 from nce.vertical_modules.netbox import circuits as netbox_circuits
 
@@ -241,6 +242,10 @@ TOOL_REGISTRY: dict[str, ToolSpec] = {
         admin_only=True,
         mutation=True,
     ),
+    "explain_config_change": ToolSpec(
+        _h(settings_mcp_handlers, "handle_explain_config_change"),
+        admin_only=True,
+    ),
     # ------------------------------------------------------------------
     # Agent-to-Agent (A2A) grant tools
     # ------------------------------------------------------------------
diff --git a/tests/test_settings_time_travel.py b/tests/test_settings_time_travel.py
new file mode 100644
index 0000000..a16487b
--- /dev/null
+++ b/tests/test_settings_time_travel.py
@@ -0,0 +1,299 @@
+"""Batch 54 — config time-travel & rollback (V.6).
+
+Unit tests (no Docker) for:
+  1. GET /api/admin/settings/effective?as_of=T reconstructs the exact past
+     non-secret config by folding ordered ``config_changed`` WORM events over the
+     env/default baseline.
+  2. POST /api/admin/settings/rollback {dry_run:true} returns the correct inverse
+     diff, skips prod-locked keys, and flags secrets (never fabricates them).
+  3. MCP explain_config_change(key) returns a key's full change history.
+
+These exercise the real folding/diff code paths against a mocked asyncpg pool;
+the event rows are crafted to mirror what ``api_admin_settings_patch`` writes.
+"""
+
+from __future__ import annotations
+
+import datetime
+import json
+from types import SimpleNamespace
+from unittest.mock import AsyncMock, MagicMock, patch
+
+import pytest
+from nce.admin_handlers import settings as settings_handlers
+
+UTC = datetime.timezone.utc
+
+
+def _row(event_type: str, params: dict, *, seq: int, occurred_at: datetime.datetime) -> dict:
+    """Build an event_log row as asyncpg would return it (params as a dict)."""
+    return {
+        "event_id": f"00000000-0000-4000-8000-{seq:012d}",
+        "event_type": event_type,
+        "agent_id": params.get("actor", "admin"),
+        "params": params,
+        "event_seq": seq,
+        "occurred_at": occurred_at,
+    }
+
+
+def _make_engine(fetch_results):
+    """Return a mock engine whose pool.acquire() conn.fetch yields the given results.
+
+    *fetch_results* is a list, one entry per expected ``conn.fetch`` call; each entry
+    is itself the list of rows that call should return.
+    """
+    conn = AsyncMock()
+    conn.fetch.side_effect = list(fetch_results)
+
+    ctx = MagicMock()
+    ctx.__aenter__ = AsyncMock(return_value=conn)
+    ctx.__aexit__ = AsyncMock(return_value=False)
+
+    engine = MagicMock()
+    engine.pg_pool.acquire.return_value = ctx
+    engine.redis_client = None
+    return engine, conn
+
+
+def _request(query: dict | None = None, body: dict | None = None):
+    """Minimal request shim exposing the attrs the handlers actually touch."""
+    req = MagicMock()
+    req.query_params = query or {}
+    req.state = SimpleNamespace(namespace_ctx=None)
+    req.headers = {}
+    if body is not None:
+        req.json = AsyncMock(return_value=body)
+    return req
+
+
+# ---------------------------------------------------------------------------
+# 1. effective?as_of=T reconstructs the exact past non-secret config
+# ---------------------------------------------------------------------------
+
+
+@pytest.mark.asyncio
+async def test_effective_as_of_reconstructs_past_config():
+    now = datetime.datetime.now(UTC)
+    t1 = now - datetime.timedelta(days=3)
+    t2 = now - datetime.timedelta(days=2)
+    t3 = now - datetime.timedelta(days=1)  # AFTER the as_of cutoff
+
+    as_of = (now - datetime.timedelta(days=1, hours=12)).isoformat()
+
+    # Sequence of config_changed events. Only events with occurred_at <= as_of
+    # are folded — the SQL cutoff is mimicked by the test fetch below.
+    events = [
+        _row(
+            "config_changed",
+            {
+                "actor": "admin",
+                "reason": "raise limit",
+                "changes": {"NCE_ADMIN_HTTP_RATE_LIMIT": {"old_value": 100, "new_value": 200}},
+            },
+            seq=1,
+            occurred_at=t1,
+        ),
+        _row(
+            "config_changed",
+            {
+                "actor": "admin",
+                "reason": "raise again",
+                "changes": {
+                    "NCE_ADMIN_HTTP_RATE_LIMIT": {"old_value": 200, "new_value": 300},
+                    "WEBHOOK_RATE_LIMIT": {"old_value": 50, "new_value": 75},
+                },
+            },
+            seq=2,
+            occurred_at=t2,
+        ),
+    ]
+    # t3 event would have changed it to 999, but it's after as_of so the handler's
+    # SQL (occurred_at <= $1) excludes it; we simulate that by NOT returning it.
+    _ = t3
+
+    engine, _conn = _make_engine([events])
+
+    with patch("nce.admin_state.engine", engine):
+        resp = await settings_handlers.api_admin_settings_effective(
+            _request(query={"as_of": as_of})
+        )
+
+    assert resp.status_code == 200
+    data = json.loads(bytes(resp.body).decode("utf-8"))
+    eff = data["effective"]
+    # Folded forward to the last value at/just before T:
+    assert eff["NCE_ADMIN_HTTP_RATE_LIMIT"] == 300
+    assert eff["WEBHOOK_RATE_LIMIT"] == 75
+    # A key never touched keeps its env/default baseline (not the rolled value).
+    assert "NCE_QUOTAS_ENABLED" in eff
+
+
+@pytest.mark.asyncio
+async def test_effective_as_of_never_exposes_secret_value():
+    now = datetime.datetime.now(UTC)
+    as_of = now.isoformat()
+    events = [
+        _row(
+            "config_changed",
+            {
+                "actor": "admin",
+                "changes": {
+                    # secrets are redacted to lifecycle tokens in the WORM event
+                    "NCE_GEMINI_API_KEY": {"old_value": "••••unset", "new_value": "••••set"}
+                },
+            },
+            seq=1,
+            occurred_at=now - datetime.timedelta(hours=1),
+        ),
+    ]
+    engine, _conn = _make_engine([events])
+
+    with patch("nce.admin_state.engine", engine):
+        resp = await settings_handlers.api_admin_settings_effective(
+            _request(query={"as_of": as_of})
+        )
+
+    data = json.loads(bytes(resp.body).decode("utf-8"))
+    # The reconstructed secret is ONLY the masked token — never a real value.
+    assert data["effective"]["NCE_GEMINI_API_KEY"] == "••••set"
+
+
+# ---------------------------------------------------------------------------
+# 2. rollback dry_run returns the correct inverse diff (+ guardrails)
+# ---------------------------------------------------------------------------
+
+
+@pytest.mark.asyncio
+async def test_rollback_dry_run_inverse_diff_and_guardrails():
+    now = datetime.datetime.now(UTC)
+    as_of = (now - datetime.timedelta(days=1)).isoformat()
+
+    # Past events (folded for the as_of reconstruction):
+    past_events = [
+        _row(
+            "config_changed",
+            {
+                "actor": "admin",
+                "changes": {"NCE_ADMIN_HTTP_RATE_LIMIT": {"old_value": 100, "new_value": 120}},
+            },
+            seq=1,
+            occurred_at=now - datetime.timedelta(days=2),
+        ),
+    ]
+    # Current DB overrides (second fetch in the rollback handler): the live value
+    # differs from the reconstructed past (200 now vs 120 at T) so the inverse
+    # change-set must restore 120. A prod-locked guardrail and a secret are also
+    # overridden to exercise the skip/flag paths.
+    current_overrides = [
+        {
+            "key": "NCE_ADMIN_HTTP_RATE_LIMIT",
+            "value": "200",
+            "has_secret": False,
+            "is_secret": False,
+        },
+        {
+            "key": "NCE_BYPASS_WORM",
+            "value": "true",
+            "has_secret": False,
+            "is_secret": False,
+        },
+        {
+            "key": "NCE_GEMINI_API_KEY",
+            "value": None,
+            "has_secret": True,
+            "is_secret": True,
+        },
+    ]
+
+    engine, _conn = _make_engine([past_events, current_overrides])
+
+    with patch("nce.admin_state.engine", engine):
+        resp = await settings_handlers.api_admin_settings_rollback(
+            _request(body={"as_of": as_of, "dry_run": True})
+        )
+
+    assert resp.status_code == 200
+    data = json.loads(bytes(resp.body).decode("utf-8"))
+    assert data["dry_run"] is True
+
+    # Inverse diff restores the non-secret HOT key from its current 200 back to 120.
+    assert data["diff"]["NCE_ADMIN_HTTP_RATE_LIMIT"] == {
+        "old_value": 200,
+        "new_value": 120,
+    }
+    # prod-locked guardrail is never silently re-enabled — it is skipped.
+    assert "NCE_BYPASS_WORM" in data["skipped_prod_locked"]
+    assert data["skipped_prod_locked"]["NCE_BYPASS_WORM"]["reason"] == "prod_locked"
+    # secret that changed since T is flagged for manual re-entry, not fabricated.
+    assert "NCE_GEMINI_API_KEY" in data["flagged_secrets"]
+    flagged = data["flagged_secrets"]["NCE_GEMINI_API_KEY"]
+    assert flagged["reason"] == "secret_rotated_since_as_of"
+    # Only the masked lifecycle token is ever present — never a real secret value.
+    assert flagged["current_value"] == "••••set"
+    # The secret is never auto-applied: it must not appear in the apply diff.
+    assert "NCE_GEMINI_API_KEY" not in data["diff"]
+
+
+@pytest.mark.asyncio
+async def test_rollback_requires_as_of():
+    engine, _conn = _make_engine([])
+    with patch("nce.admin_state.engine", engine):
+        resp = await settings_handlers.api_admin_settings_rollback(_request(body={"dry_run": True}))
+    assert resp.status_code == 422
+
+
+# ---------------------------------------------------------------------------
+# 3. explain_config_change(key) returns the change history
+# ---------------------------------------------------------------------------
+
+
+@pytest.mark.asyncio
+async def test_explain_config_change_returns_history():
+    now = datetime.datetime.now(UTC)
+    events = [
+        _row(
+            "config_changed",
+            {
+                "actor": "alice",
+                "reason": "bump",
+                "changes": {
+                    "NCE_ADMIN_HTTP_RATE_LIMIT": {"old_value": 100, "new_value": 150},
+                    "WEBHOOK_RATE_LIMIT": {"old_value": 10, "new_value": 20},
+                },
+            },
+            seq=1,
+            occurred_at=now - datetime.timedelta(days=2),
+        ),
+        _row(
+            "config_changed",
+            {
+                "actor": "bob",
+                "reason": "bump again",
+                "changes": {"NCE_ADMIN_HTTP_RATE_LIMIT": {"old_value": 150, "new_value": 175}},
+            },
+            seq=2,
+            occurred_at=now - datetime.timedelta(days=1),
+        ),
+    ]
+    engine, _conn = _make_engine([events])
+
+    out = await settings_handlers.handle_explain_config_change(
+        engine, {"key": "NCE_ADMIN_HTTP_RATE_LIMIT"}
+    )
+    data = json.loads(out)
+
+    assert data["key"] == "NCE_ADMIN_HTTP_RATE_LIMIT"
+    assert data["change_count"] == 2  # only the two entries touching this key
+    assert [h["new_value"] for h in data["history"]] == [150, 175]
+    assert [h["actor"] for h in data["history"]] == ["alice", "bob"]
+    # The unrelated key's change must NOT appear in this key's history.
+    assert all("WEBHOOK_RATE_LIMIT" not in json.dumps(h) for h in data["history"])
+
+
+@pytest.mark.asyncio
+async def test_explain_config_change_unknown_key():
+    engine, _conn = _make_engine([])
+    out = await settings_handlers.handle_explain_config_change(engine, {"key": "NOPE"})
+    data = json.loads(out)
+    assert "error" in data
diff --git a/tests/test_tool_registry.py b/tests/test_tool_registry.py
index 01fa148..7267199 100644
--- a/tests/test_tool_registry.py
+++ b/tests/test_tool_registry.py
@@ -25,7 +25,7 @@ from nce.tool_registry import (
 # Cardinality
 # ---------------------------------------------------------------------------
 
-_EXPECTED_TOTAL = 64
+_EXPECTED_TOTAL = 65
 
 
 def test_registry_has_expected_entries():
@@ -154,6 +154,9 @@ _EXPECTED_ADMIN_ONLY: frozenset[str] = frozenset(
         "explain_past_decision",
         "d365_sync_now",
         "d365_list_sla_breaches",
+        # Batch 54 — V.6 config time-travel audit; admin-only read of the
+        # config_changed/config_reset WORM history for a key.
+        "explain_config_change",
     }
 )
 
@@ -166,7 +169,7 @@ def test_admin_only_tools_exact_match():
 
 
 def test_admin_only_tools_count():
-    assert len(ADMIN_ONLY_TOOLS) == 8
+    assert len(ADMIN_ONLY_TOOLS) == 9
 
 
 # ---------------------------------------------------------------------------
@@ -323,6 +326,10 @@ def test_toolspec_is_frozen():
             "explain_past_decision",
             {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
         ),
+        (
+            "explain_config_change",
+            {"mutation": False, "cacheable": False, "admin_only": True, "migration": False},
+        ),
         # a2a
         (
             "a2a_create_grant",
```
