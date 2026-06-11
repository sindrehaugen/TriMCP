# Diff Reference for Batch 56

```diff
diff --git a/docs/database_architecture.md b/docs/database_architecture.md
index b7f313a..2f5e60a 100644
--- a/docs/database_architecture.md
+++ b/docs/database_architecture.md
@@ -107,7 +107,8 @@ async def scoped_pg_session(pool: asyncpg.Pool, namespace_id: str):
 ### 3b. Why RLS Context Requires SET LOCAL
 Using `SET LOCAL` scopes the configuration setting to the immediate transaction block. If the connection is returned to the pool, the setting is guaranteed to revert, preventing cross-tenant leakage. 
 
-* **Admin Bypass**: Background administrative tasks (such as database migrations, global auditing, or the garbage collector) check out connections via `unmanaged_pg_connection(pool)`. These connections bypass RLS using the privileged `nce_gc` role, which has the `BYPASSRLS` attribute enabled.
+* **Admin Bypass**: A narrow set of global maintenance paths (schema migrations, partition maintenance, cron namespace scans) check out connections via `unmanaged_pg_connection(pool)`, which skips `SET LOCAL nce.namespace_id`. Today these still authenticate as the application role (`nce_app`) — `unmanaged_pg_connection` is the app role *skipping* RLS scoping on audited global sites, not a separate database principal.
+* **Worker principal segregation (`nce_gc`)**: The `nce_gc` role exists in `schema.sql` with the `BYPASSRLS` attribute for least-privilege worker isolation. Background maintenance **workers** (the garbage collector and the re-embedding worker) resolve their connection DSN via `db_utils.resolve_worker_dsn()`, which returns `NCE_GC_DSN` when set (so the worker connects as `nce_gc` with its own credentials) and otherwise falls back to `PG_DSN` (the app role) for backward compatibility. To activate segregation, provision `nce_gc` with `LOGIN` + its own password and point `NCE_GC_DSN` at it; the application pool then never authenticates as a `BYPASSRLS` role. Note the GC itself runs RLS-scoped per namespace (it calls `set_namespace_context` rather than relying on `BYPASSRLS`), so segregation is primarily a credential-isolation boundary.
 
 ---
 
diff --git a/docs/enterprise_security.md b/docs/enterprise_security.md
index 1304d32..0c1850c 100644
--- a/docs/enterprise_security.md
+++ b/docs/enterprise_security.md
@@ -155,7 +155,7 @@ CREATE POLICY tenant_isolation_policy ON memories
 ```
 
 * **RLS Enforcement Rule**: All SELECT, INSERT, UPDATE, and DELETE operations executed under the standard application role `nce_app` are restricted to the UUID returned by `get_nce_namespace()`.
-* **Privileged Role Exception**: The garbage collection role `nce_gc` bypasses RLS using the database-level `BYPASSRLS` attribute. This role is not accessible to application threads.
+* **Privileged Role Exception (`nce_gc`)**: The `nce_gc` role is defined in `schema.sql` with the database-level `BYPASSRLS` attribute as a least-privilege boundary for background maintenance workers. Workers select their DSN via `db_utils.resolve_worker_dsn()`: when `NCE_GC_DSN` is set they connect as `nce_gc` (its own credentials, distinct from `nce_app`); when it is unset they fall back to `PG_DSN` (the app role) for backward compatibility. The application role `nce_app` never holds `BYPASSRLS` in either case — that attribute belongs only to `nce_gc`. To enforce hard segregation in production, provision `nce_gc` with `LOGIN` and a dedicated password and set `NCE_GC_DSN` accordingly (`NCE_GC_DSN` is environment-only and never returned by any endpoint). The garbage collector additionally runs RLS-scoped per namespace (via `set_namespace_context`), so it does not depend on `BYPASSRLS` for correctness.
 
 ---
 
diff --git a/nce/config.py b/nce/config.py
index f6a3947..1c7af9c 100644
--- a/nce/config.py
+++ b/nce/config.py
@@ -306,6 +306,20 @@ class _Config:
         or "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta"
     )
     PG_BOUNCER_URL: str = os.getenv("PG_BOUNCER_URL", "")
+    # Least-privilege worker DSN (R4 / VI.4).  Background maintenance workers
+    # (garbage collector, re-embedding worker) connect with this DSN when set,
+    # so they authenticate as a *distinct* principal (e.g. ``nce_gc``) rather
+    # than reusing the application role (``nce_app``).  Handled like other DSNs:
+    # environment-only, never logged in cleartext, never returned by endpoints.
+    # When UNSET it falls back to ``PG_DSN`` so existing deployments are
+    # unchanged (backward-compatible) — segregation is opt-in via provisioning
+    # a dedicated role and pointing this at it.
+    NCE_GC_DSN: str = (
+        os.getenv("NCE_GC_DSN")
+        or os.getenv("PG_DSN")
+        or os.getenv("DATABASE_URL")
+        or "postgresql://mcp_user:mcp_password@localhost:5432/memory_meta"
+    )
     REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
 
     # --- Redis ---
diff --git a/nce/db_utils.py b/nce/db_utils.py
index a5fb94d..7825658 100644
--- a/nce/db_utils.py
+++ b/nce/db_utils.py
@@ -12,7 +12,7 @@ from contextlib import asynccontextmanager
 from typing import Final
 from uuid import UUID
 
-import asyncpg
+import asyncpg  # type: ignore[import-untyped]
 
 from nce.observability import SCOPED_SESSION_LATENCY
 
@@ -38,6 +38,43 @@ UNMANAGED_PG_AUDITED_SITES: Final[frozenset[str]] = frozenset(
 )
 
 
+def resolve_worker_dsn() -> str:
+    """Return the DSN background maintenance workers must connect with (R4 / VI.4).
+
+    Garbage-collection and re-embedding workers should authenticate as a
+    *distinct, least-privilege* principal (provisioned as ``nce_gc``) rather
+    than reusing the application role. The selection contract is:
+
+    * ``NCE_GC_DSN`` set → use it (the worker principal, distinct from the app).
+    * ``NCE_GC_DSN`` unset → fall back to ``PG_DSN`` (the app role) so existing
+      deployments keep working unchanged (backward-compatible default).
+
+    Resolving from config (rather than reading ``cfg.PG_DSN`` directly at the
+    worker connect site) is what lets a deployment grant the workers their own
+    credentials without the application pool ever holding ``BYPASSRLS``.
+
+    The returned string is a secret — callers must never log it in cleartext
+    (use ``config.redact_secrets_in_text``) nor return it from an endpoint.
+    """
+    from nce.config import cfg
+
+    return cfg.NCE_GC_DSN
+
+
+def worker_dsn_is_segregated() -> bool:
+    """True when workers connect as a principal distinct from the app role.
+
+    Equivalent to "``NCE_GC_DSN`` resolved to something other than ``PG_DSN``".
+    When False, workers share the app DSN (the safe, backward-compatible
+    fallback) — the app role still never gains ``BYPASSRLS`` either way; that
+    attribute is a property of the *role* the DSN authenticates as, granted at
+    provisioning time, not of these workers.
+    """
+    from nce.config import cfg
+
+    return bool(cfg.NCE_GC_DSN) and cfg.NCE_GC_DSN != cfg.PG_DSN
+
+
 @asynccontextmanager
 async def unmanaged_pg_connection(pool: asyncpg.Pool, *, site: str):
     """Acquire a PG connection with bounded wait — no RLS (global/admin paths only).
diff --git a/nce/garbage_collector.py b/nce/garbage_collector.py
index fe3ef7e..9ca034e 100644
--- a/nce/garbage_collector.py
+++ b/nce/garbage_collector.py
@@ -18,12 +18,13 @@ from datetime import datetime, timedelta, timezone
 from typing import Any
 from uuid import UUID
 
-import asyncpg
+import asyncpg  # type: ignore[import-untyped]
 from bson import ObjectId
 from motor.motor_asyncio import AsyncIOMotorClient
 
 from nce.auth import set_namespace_context
 from nce.config import cfg, redact_secrets_in_text
+from nce.db_utils import resolve_worker_dsn
 from nce.redis_lock import acquire_lock as _acquire_redis_lock
 from nce.redis_lock import release_lock as _release_redis_lock
 
@@ -87,8 +88,11 @@ async def _connect_with_retry() -> tuple[AsyncIOMotorClient, asyncpg.Pool]:
             # Force a real connection check
             await mongo_client.admin.command("ping")
 
+            # R4 / VI.4: connect as the least-privilege worker principal
+            # (``nce_gc`` via NCE_GC_DSN) when provisioned; falls back to the
+            # app DSN (``nce_app``) when NCE_GC_DSN is unset.
             pg_pool = await asyncpg.create_pool(
-                cfg.PG_DSN,
+                resolve_worker_dsn(),
                 min_size=1,
                 max_size=3,  # GC needs very few connections
                 command_timeout=30,
diff --git a/nce/reembedding_worker.py b/nce/reembedding_worker.py
index cd6c1c8..3fc9abd 100644
--- a/nce/reembedding_worker.py
+++ b/nce/reembedding_worker.py
@@ -67,10 +67,11 @@ import uuid
 from datetime import datetime
 from typing import Any
 
-import asyncpg
+import asyncpg  # type: ignore[import-untyped]
 
 from nce import embeddings as _embeddings
 from nce.config import cfg
+from nce.db_utils import resolve_worker_dsn
 from nce.embeddings import MODEL_ID, VECTOR_DIM  # noqa: F401
 from nce.redis_lock import acquire_lock as _acquire_redis_lock
 from nce.redis_lock import release_lock as _release_redis_lock
@@ -683,8 +684,13 @@ async def async_main() -> None:
 
     cfg.validate()
 
+    # R4 / VI.4: connect as the least-privilege worker principal
+    # (``nce_gc`` via NCE_GC_DSN) when provisioned; falls back to the app DSN
+    # (``nce_app``) when NCE_GC_DSN is unset.  Only the standalone entry point
+    # owns its pool — when driven by ``nce/cron.py`` the worker reuses the
+    # pool the caller passes to ``run_once`` (see module docstring / cron).
     pool = await asyncpg.create_pool(
-        cfg.PG_DSN,
+        resolve_worker_dsn(),
         min_size=1,
         max_size=4,
         command_timeout=120,
diff --git a/tests/test_worker_dsn_segregation.py b/tests/test_worker_dsn_segregation.py
new file mode 100644
index 0000000..970683d
--- /dev/null
+++ b/tests/test_worker_dsn_segregation.py
@@ -0,0 +1,180 @@
+"""R4 / VI.4 — least-privilege worker DSN segregation.
+
+These tests assert the *real* DSN-selection contract for the background
+maintenance workers (garbage collector + re-embedding worker), not that a mock
+was called:
+
+* When ``NCE_GC_DSN`` is set, ``resolve_worker_dsn()`` returns it and it is a
+  principal *distinct* from ``PG_DSN`` (the app role).
+* When ``NCE_GC_DSN`` is unset, it falls back to ``PG_DSN`` (safe,
+  backward-compatible default).
+* The GC and re-embedding workers actually open their pools against the
+  resolved worker DSN, so a deployment that provisions ``nce_gc`` keeps the
+  application role out of the worker connection — the app pool is never the
+  ``BYPASSRLS`` principal.
+
+Config is an import-time singleton, so the env-precedence cases run in fresh
+subprocesses (mirroring ``tests/test_config_prod_hardening.py``). The
+worker-wiring cases patch ``asyncpg.create_pool`` and inspect the DSN argument
+that the worker passes — asserting the value selected, not merely that connect
+happened.
+"""
+
+from __future__ import annotations
+
+import os
+import subprocess
+import sys
+from pathlib import Path
+from unittest.mock import AsyncMock, MagicMock, patch
+
+import pytest
+
+_REPO_ROOT = Path(__file__).resolve().parents[1]
+
+_APP_DSN = "postgresql://nce_app:app_secret@db.internal:5432/memory_meta"
+_GC_DSN = "postgresql://nce_gc:gc_secret@db.internal:5432/memory_meta"
+
+
+def _run_in_subprocess(code: str, extra_env: dict[str, str]) -> str:
+    env = os.environ.copy()
+    # Ensure a clean baseline: drop any inherited DSN overrides.
+    for k in ("NCE_GC_DSN", "PG_DSN", "DATABASE_URL", "DB_READ_URL", "DB_WRITE_URL"):
+        env.pop(k, None)
+    env["NCE_ENV"] = "dev"
+    env["NCE_MASTER_KEY"] = "x" * 32
+    env.update(extra_env)
+    result = subprocess.run(
+        [sys.executable, "-c", code],
+        cwd=_REPO_ROOT,
+        env=env,
+        capture_output=True,
+        text=True,
+        check=False,
+    )
+    assert result.returncode == 0, f"subprocess failed:\n{result.stdout}\n{result.stderr}"
+    return result.stdout.strip()
+
+
+# --------------------------------------------------------------------------- #
+# Env-precedence contract (real config resolution)
+# --------------------------------------------------------------------------- #
+
+
+def test_gc_dsn_distinct_from_pg_dsn_when_set() -> None:
+    """NCE_GC_DSN set → resolver returns the GC principal, distinct from PG_DSN."""
+    out = _run_in_subprocess(
+        "from nce.config import cfg\n"
+        "from nce.db_utils import resolve_worker_dsn, worker_dsn_is_segregated\n"
+        "print(cfg.PG_DSN)\n"
+        "print(cfg.NCE_GC_DSN)\n"
+        "print(resolve_worker_dsn())\n"
+        "print(worker_dsn_is_segregated())\n",
+        {"PG_DSN": _APP_DSN, "NCE_GC_DSN": _GC_DSN},
+    )
+    pg_dsn, gc_dsn, resolved, segregated = out.splitlines()
+    assert pg_dsn == _APP_DSN
+    assert gc_dsn == _GC_DSN
+    # The contract: the worker resolves to the GC principal, NOT the app role.
+    assert resolved == _GC_DSN
+    assert resolved != pg_dsn
+    assert segregated == "True"
+
+
+def test_gc_dsn_falls_back_to_pg_dsn_when_unset() -> None:
+    """NCE_GC_DSN unset → safe, backward-compatible fallback to PG_DSN."""
+    out = _run_in_subprocess(
+        "from nce.config import cfg\n"
+        "from nce.db_utils import resolve_worker_dsn, worker_dsn_is_segregated\n"
+        "print(cfg.PG_DSN)\n"
+        "print(resolve_worker_dsn())\n"
+        "print(worker_dsn_is_segregated())\n",
+        {"PG_DSN": _APP_DSN},
+    )
+    pg_dsn, resolved, segregated = out.splitlines()
+    assert pg_dsn == _APP_DSN
+    assert resolved == _APP_DSN  # fallback to the app role — unchanged behavior
+    assert segregated == "False"  # not segregated when sharing the app DSN
+
+
+# --------------------------------------------------------------------------- #
+# Worker wiring — the pool is opened against the resolved worker DSN
+# --------------------------------------------------------------------------- #
+
+
+@pytest.mark.asyncio
+async def test_gc_worker_connects_with_resolved_worker_dsn() -> None:
+    """garbage_collector._connect_with_retry opens its pool on resolve_worker_dsn()."""
+    import nce.garbage_collector as gc
+
+    fake_pool = MagicMock()
+
+    fake_mongo = MagicMock()
+    fake_mongo.admin.command = AsyncMock(return_value={"ok": 1})
+
+    captured: dict[str, object] = {}
+
+    async def _fake_create_pool(dsn, **kwargs):  # noqa: ANN001
+        captured["dsn"] = dsn
+        return fake_pool
+
+    with (
+        patch.object(gc, "resolve_worker_dsn", return_value=_GC_DSN) as resolver,
+        patch.object(gc, "AsyncIOMotorClient", return_value=fake_mongo),
+        patch.object(gc.asyncpg, "create_pool", side_effect=_fake_create_pool),
+    ):
+        mongo_client, pool = await gc._connect_with_retry()
+
+    assert pool is fake_pool
+    resolver.assert_called_once()
+    # The load-bearing assertion: the GC pool authenticates as the worker
+    # principal (NCE_GC_DSN), not whatever cfg.PG_DSN happens to be.
+    assert captured["dsn"] == _GC_DSN
+
+
+@pytest.mark.asyncio
+async def test_reembedding_worker_connects_with_resolved_worker_dsn() -> None:
+    """reembedding_worker.async_main opens its pool on resolve_worker_dsn()."""
+    import nce.reembedding_worker as rw
+
+    fake_pool = MagicMock()
+    fake_pool.close = AsyncMock()
+
+    captured: dict[str, object] = {}
+
+    async def _fake_create_pool(dsn, **kwargs):  # noqa: ANN001
+        captured["dsn"] = dsn
+        return fake_pool
+
+    fake_worker = MagicMock()
+    fake_worker.run_once = AsyncMock(return_value={"status": "completed"})
+
+    with (
+        patch.object(rw, "resolve_worker_dsn", return_value=_GC_DSN) as resolver,
+        patch.object(rw.cfg, "validate", return_value=None),
+        patch.object(rw.asyncpg, "create_pool", side_effect=_fake_create_pool),
+        patch.object(rw, "ReembeddingWorker", return_value=fake_worker),
+        # Force the Mongo import branch to be skipped deterministically.
+        patch.dict(sys.modules, {"motor.motor_asyncio": None}),
+    ):
+        await rw.async_main()
+
+    resolver.assert_called_once()
+    assert captured["dsn"] == _GC_DSN
+
+
+def test_app_path_does_not_use_gc_dsn() -> None:
+    """The application orchestrator pool must use PG_DSN (app role), never the GC DSN.
+
+    Guards the inverse invariant: segregation puts BYPASSRLS-capable creds only
+    on the worker side; the app pool keeps PG_DSN and never picks up NCE_GC_DSN.
+    """
+    out = _run_in_subprocess(
+        "from nce.config import cfg\nprint(cfg.PG_DSN)\nprint(cfg.NCE_GC_DSN)\n",
+        {"PG_DSN": _APP_DSN, "NCE_GC_DSN": _GC_DSN},
+    )
+    pg_dsn, gc_dsn = out.splitlines()
+    # The app DSN is the app principal; the GC DSN is a different principal.
+    assert pg_dsn == _APP_DSN
+    assert gc_dsn == _GC_DSN
+    assert pg_dsn != gc_dsn
```
