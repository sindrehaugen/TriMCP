# Diff Reference for Batch 34

```diff
diff --git a/RL.md b/RL.md
index 214b0c2..f46b57f 100644
--- a/RL.md
+++ b/RL.md
@@ -41,7 +41,7 @@
 * [DONE] Batch 31 — `settings` table migration (V.1a) [PASSED TAG]
 * [DONE] Batch 32 — `SettingsStore` accessor with precedence + cache (V.1b) [PASSED TAG]
 * [DONE] Batch 33 — Settings registry metadata (V.1a) [PASSED TAG]
-* [RUNNING] Batch 34 — `GET /api/admin/settings` (+ `/effective`, `/{key}`) (V.1b) [NO TAG]
+* [RUNNING] Batch 34 — `GET /api/admin/settings` (+ `/effective`, `/{key}`) (V.1b) [WAITING TAG]
 * [LOCKED] Batch 35 — `PATCH /api/admin/settings` (207) + `config_changed` WORM event (V.1b/V.5) [NO TAG]
 * [LOCKED] Batch 36 — `/reset`, `/reload`, `/pending` endpoints (V.1b) [NO TAG]
 * [LOCKED] Batch 37 — Honest Uncertainty in search results (II.1) [NO TAG]
diff --git a/nce/admin_app.py b/nce/admin_app.py
index 5836381..7c65fc4 100644
--- a/nce/admin_app.py
+++ b/nce/admin_app.py
@@ -160,6 +160,17 @@ def build_admin_routes() -> list[Route]:
             methods=["POST"],
         ),
         Route("/api/admin/quotas", endpoint=h.api_admin_quotas, methods=["GET"]),
+        Route("/api/admin/settings", endpoint=h.api_admin_settings_list, methods=["GET"]),
+        Route(
+            "/api/admin/settings/effective",
+            endpoint=h.api_admin_settings_effective,
+            methods=["GET"],
+        ),
+        Route(
+            "/api/admin/settings/{key}",
+            endpoint=h.api_admin_settings_get,
+            methods=["GET"],
+        ),
         Route(
             "/api/admin/signing/status",
             endpoint=h.api_admin_signing_status,
diff --git a/nce/admin_handlers/settings.py b/nce/admin_handlers/settings.py
index 07bde70..e908ca0 100644
--- a/nce/admin_handlers/settings.py
+++ b/nce/admin_handlers/settings.py
@@ -3,19 +3,18 @@ from __future__ import annotations
 import json
 import os
 from typing import Any
+
 from starlette.responses import JSONResponse
 
 from nce import admin_state
-from nce.config import cfg
-from nce.admin_handlers import _shared
 from nce.admin_handlers._shared import UTC, logger
+from nce.config import cfg
 from nce.settings_registry import (
     REGISTRY,
     SettingMetadata,
     validate_bool,
     validate_str_list,
 )
-from nce.settings_store import get
 
 
 def get_validation_metadata(metadata: SettingMetadata) -> dict[str, Any]:
@@ -125,9 +124,7 @@ async def api_admin_settings_list(request: Any) -> JSONResponse:
             sections_list.append(metadata.section)
             section_to_keys[metadata.section] = []
 
-        effective_value, source, store_value_set = get_effective_value(
-            key, metadata, db_overrides
-        )
+        effective_value, source, store_value_set = get_effective_value(key, metadata, db_overrides)
         validation_dict = get_validation_metadata(metadata)
 
         key_detail = {
@@ -214,9 +211,7 @@ async def api_admin_settings_get(request: Any) -> JSONResponse:
             logger.error("Failed to fetch settings key '%s' from Postgres: %s", key, e)
 
     db_overrides = {key: db_row} if db_row else {}
-    effective_value, source, store_value_set = get_effective_value(
-        key, metadata, db_overrides
-    )
+    effective_value, source, store_value_set = get_effective_value(key, metadata, db_overrides)
 
     key_detail = {
         "key": key,
diff --git a/nce/settings_registry.py b/nce/settings_registry.py
index 2a943d2..834b900 100644
--- a/nce/settings_registry.py
+++ b/nce/settings_registry.py
@@ -23,6 +23,7 @@ class SettingMetadata(NamedTuple):
     prod_locked: bool
     validator: Callable[[Any], bool]
     description: str
+    default: Any = None
 
 
 # --- Validator Factories ---
@@ -79,6 +80,81 @@ def validate_str_list(val: Any) -> bool:
     return all(isinstance(item, str) for item in val)
 
 
+# --- Environment Schema Validation & Defaults Auto-Loading ---
+
+
+def _coerce_env_value(val_str: str, target_type: str) -> Any:
+    """Coerce string environment variable value to the registry's target type."""
+    if target_type == "int":
+        try:
+            return int(val_str)
+        except ValueError:
+            raise TypeError(f"Value '{val_str}' is not a valid integer")
+    elif target_type == "float":
+        try:
+            return float(val_str)
+        except ValueError:
+            raise TypeError(f"Value '{val_str}' is not a valid float")
+    elif target_type == "bool":
+        clean = val_str.strip().lower()
+        if clean in {"1", "true", "yes", "on"}:
+            return True
+        elif clean in {"0", "false", "no", "off"}:
+            return False
+        else:
+            raise TypeError(f"Value '{val_str}' is not a valid boolean")
+    elif target_type == "list":
+        clean = val_str.strip()
+        if clean.startswith("[") and clean.endswith("]"):
+            try:
+                import json
+                parsed = json.loads(clean)
+                if isinstance(parsed, list):
+                    return parsed
+            except json.JSONDecodeError:
+                pass
+        return [item.strip() for item in clean.split(",") if item.strip()]
+    return val_str
+
+
+def validate_env(env_dict: dict[str, str] | None = None) -> dict[str, str]:
+    """Validate environment variables against the registry schema.
+
+    Returns a mapping of key to error message for all failed validations.
+    """
+    if env_dict is None:
+        env_dict = os.environ
+
+    errors = {}
+    for key, meta in REGISTRY.items():
+        if key in env_dict:
+            val_str = env_dict[key]
+            try:
+                coerced = _coerce_env_value(val_str, meta.type)
+                if not meta.validator(coerced):
+                    errors[key] = f"Validation failed for key '{key}' with value '{val_str}'"
+            except (TypeError, ValueError) as e:
+                errors[key] = f"Type coercion failed for key '{key}': {e}"
+    return errors
+
+
+def auto_load_defaults(env_dict: dict[str, str] | None = None, overwrite: bool = False) -> None:
+    """Auto-load defaults from registry into the environment mapping if unset."""
+    if env_dict is None:
+        env_dict = os.environ
+
+    for key, meta in REGISTRY.items():
+        if meta.default is not None:
+            if overwrite or key not in env_dict or not env_dict[key].strip():
+                val = meta.default
+                if isinstance(val, bool):
+                    env_dict[key] = "true" if val else "false"
+                elif isinstance(val, list):
+                    env_dict[key] = ",".join(str(item) for item in val)
+                else:
+                    env_dict[key] = str(val)
+
+
 # --- Settings Registry Mapping ---
 
 REGISTRY: dict[str, SettingMetadata] = {
@@ -203,6 +279,7 @@ REGISTRY: dict[str, SettingMetadata] = {
         prod_locked=False,
         validator=validate_int(minimum=1),
         description="Minimum size of PostgreSQL pool.",
+        default=1,
     ),
     "PG_MAX_POOL": SettingMetadata(
         key="PG_MAX_POOL",
@@ -213,6 +290,7 @@ REGISTRY: dict[str, SettingMetadata] = {
         prod_locked=False,
         validator=validate_int(minimum=1),
         description="Maximum size of PostgreSQL pool.",
+        default=10,
     ),
     "REDIS_MAX_CONNECTIONS": SettingMetadata(
         key="REDIS_MAX_CONNECTIONS",
diff --git a/tests/test_settings_registry.py b/tests/test_settings_registry.py
index dee5d20..3a3f86c 100644
--- a/tests/test_settings_registry.py
+++ b/tests/test_settings_registry.py
@@ -74,3 +74,51 @@ def test_validators(key, valid_val, invalid_val):
     assert meta.validator(invalid_val) is False, (
         f"Validator for {key} accepted invalid value: {invalid_val}"
     )
+
+
+def test_validate_env():
+    """Verify validate_env checks and reports malformed environment settings correctly."""
+    from nce.settings_registry import validate_env
+
+    # Valid scenario
+    valid_env = {
+        "PG_MIN_POOL": "5",
+        "MINIO_SECURE": "true",
+        "MONGO_URI": "mongodb://test",
+    }
+    errors = validate_env(valid_env)
+    assert not errors
+
+    # Invalid scenario
+    invalid_env = {
+        "PG_MIN_POOL": "not_an_int",
+        "MINIO_SECURE": "invalid_bool",
+        "MONGO_URI": "",  # Empty is forbidden by allow_empty=False
+    }
+    errors = validate_env(invalid_env)
+    assert "PG_MIN_POOL" in errors
+    assert "MINIO_SECURE" in errors
+    assert "MONGO_URI" in errors
+
+
+def test_auto_load_defaults():
+    """Verify auto_load_defaults populates missing keys in target dictionary."""
+    from nce.settings_registry import auto_load_defaults
+
+    # Empty env dict should receive defaults
+    mock_env = {}
+    auto_load_defaults(mock_env)
+    assert mock_env["PG_MIN_POOL"] == "1"
+    assert mock_env["PG_MAX_POOL"] == "10"
+
+    # Pre-existing values should NOT be overwritten by default
+    mock_env = {"PG_MIN_POOL": "42"}
+    auto_load_defaults(mock_env)
+    assert mock_env["PG_MIN_POOL"] == "42"
+    assert mock_env["PG_MAX_POOL"] == "10"
+
+    # Pre-existing values SHOULD be overwritten if overwrite=True
+    mock_env = {"PG_MIN_POOL": "42"}
+    auto_load_defaults(mock_env, overwrite=True)
+    assert mock_env["PG_MIN_POOL"] == "1"
+
```
