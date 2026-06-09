# Diff Reference for Batch 31

```diff
diff --git a/RL.md b/RL.md
index ebfefdd..24b1fbc 100644
--- a/RL.md
+++ b/RL.md
@@ -37,8 +37,8 @@
 * [DONE] Batch 27 — Deterministic identity remap (uuid5) in replay (Phase 2.1) [PASSED TAG]
 * [DONE] Batch 28 — Payload copy strategy (Phase 2.1b) [PASSED TAG]
 * [DONE] Batch 29 — Faithful timestamps with mandatory re-sign (Phase 2.2) [PASSED TAG]
-* [RUNNING] Batch 30 — Namespace state-digest + equality gate (Phase 2.3) [REJECTED TAG]
-* [LOCKED] Batch 31 — `settings` table migration (V.1a) [NO TAG]
+* [DONE] Batch 30 — Namespace state-digest + equality gate (Phase 2.3) [PASSED TAG]
+* [RUNNING] Batch 31 — `settings` table migration (V.1a) [WAITING TAG]
 * [LOCKED] Batch 32 — `SettingsStore` accessor with precedence + cache (V.1b) [NO TAG]
 * [LOCKED] Batch 33 — Settings registry metadata (V.1a) [NO TAG]
 * [LOCKED] Batch 34 — `GET /api/admin/settings` (+ `/effective`, `/{key}`) (V.1b) [NO TAG]
@@ -291,4 +291,12 @@
 * **Identified System Flaws:** None.
 * **Defensive Refactoring Correction Blueprint:** None
 
+### TAG Batch 30 Evaluation Audit Report
+* **Verification Status:** PASSED TAG
+* **Target Scope Verification:** Verified file paths: `nce/replay.py`, `nce/schema.sql`, `tests/test_replay_engine.py`, and `tests/test_replay_handlers_integration.py`.
+* **Structural Integrity Scoring:** Integration of state digest calculations and equality gates inside reconstructive replay execution is structurally clean and properly decoupled. Carrying over `created_at` timestamps alongside bitemporal `valid_from` columns ensures deterministic, OS-independent verification.
+* **Contractual Test Fidelity:** High. The unit test `test_handle_store_memory_handler` asserts that memory creation timestamps are correctly replayed. The integration test `test_reconstructive_replay_digest_match` validates end-to-end replay, populates memories and KG edges, and asserts that the computed digests are non-null and equal between source and target namespaces.
+* **Identified System Flaws:** None.
+* **Defensive Refactoring Correction Blueprint:** None
+
 [EOF: END OF REFACTORING LEDGER]
\ No newline at end of file
diff --git a/nce/schema.sql b/nce/schema.sql
index 31f50a9..7c2e4ce 100644
--- a/nce/schema.sql
+++ b/nce/schema.sql
@@ -1090,6 +1090,27 @@ CREATE INDEX IF NOT EXISTS idx_d365_netbox_mappings_confirmed
     ON d365_netbox_mappings (namespace_id, confirmed)
     WHERE confirmed = TRUE;
 
+-- --- Phase 5: DB-backed runtime settings (V.1a) ---
+CREATE TABLE IF NOT EXISTS settings (
+    key         TEXT PRIMARY KEY,
+    value       JSONB,
+    secret_enc  BYTEA,
+    is_secret   BOOLEAN NOT NULL DEFAULT false,
+    section     TEXT,
+    updated_by  TEXT,
+    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
+);
+
+DO $$
+BEGIN
+    REVOKE ALL ON settings FROM PUBLIC;
+    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
+        GRANT SELECT, INSERT, UPDATE, DELETE ON settings TO nce_app;
+    ELSE
+        RAISE NOTICE 'nce_app role not found — settings GRANTs skipped';
+    END IF;
+END $$;
+
 -- --- Row Level Security (Phase 0.1 Hardening) ---
 -- Applied after all tenant tables exist. Policies use get_nce_namespace() (fail-fast).
 -- kg_node_embeddings remain global (no namespace_id). kg_nodes/kg_edges are tenant-scoped.
diff --git a/tests/test_schema_bootstrap.py b/tests/test_schema_bootstrap.py
index edb827b..75cf14c 100644
--- a/tests/test_schema_bootstrap.py
+++ b/tests/test_schema_bootstrap.py
@@ -25,3 +25,59 @@ async def test_schema_applies_cleanly_on_fresh_database(pg_admin_conn):
         "AND column_name='namespace_id')"
     )
     assert has_namespace_id is True
+
+    # settings table verification
+    settings_exists = await pg_admin_conn.fetchval(
+        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
+        "WHERE table_schema='public' AND table_name='settings')"
+    )
+    assert settings_exists is True
+
+    # Verify column types
+    columns = await pg_admin_conn.fetch(
+        """
+        SELECT column_name, data_type, is_nullable
+        FROM information_schema.columns
+        WHERE table_schema = 'public' AND table_name = 'settings'
+        ORDER BY ordinal_position
+        """
+    )
+    col_map = {r["column_name"]: (r["data_type"], r["is_nullable"]) for r in columns}
+
+    assert "key" in col_map
+    assert col_map["key"] == ("text", "NO")
+
+    assert "value" in col_map
+    assert col_map["value"] == ("jsonb", "YES")  # jsonb
+
+    assert "secret_enc" in col_map
+    assert col_map["secret_enc"] == ("bytea", "YES")
+
+    assert "is_secret" in col_map
+    assert col_map["is_secret"] == ("boolean", "NO")
+
+    assert "section" in col_map
+    assert col_map["section"] == ("text", "YES")
+
+    assert "updated_by" in col_map
+    assert col_map["updated_by"] == ("text", "YES")
+
+    assert "updated_at" in col_map
+    assert col_map["updated_at"] == ("timestamp with time zone", "NO")
+
+    # Verify RLS-exempt status
+    rls_enabled = await pg_admin_conn.fetchval(
+        "SELECT relrowsecurity FROM pg_class WHERE relname = 'settings'"
+    )
+    assert rls_enabled is False
+
+    # Verify nce_app privileges
+    grants = await pg_admin_conn.fetch(
+        """
+        SELECT privilege_type
+        FROM information_schema.role_table_grants
+        WHERE grantee = 'nce_app' AND table_name = 'settings'
+        """
+    )
+    privileges = {r["privilege_type"] for r in grants}
+    assert {"SELECT", "INSERT", "UPDATE", "DELETE"}.issubset(privileges)
```
