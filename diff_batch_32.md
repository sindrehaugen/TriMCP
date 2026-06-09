# Diff Reference for Batch 32

```diff
diff --git a/RL.md b/RL.md
index 24b1fbc..a3df018 100644
--- a/RL.md
+++ b/RL.md
@@ -38,8 +38,8 @@
 * [DONE] Batch 28 — Payload copy strategy (Phase 2.1b) [PASSED TAG]
 * [DONE] Batch 29 — Faithful timestamps with mandatory re-sign (Phase 2.2) [PASSED TAG]
 * [DONE] Batch 30 — Namespace state-digest + equality gate (Phase 2.3) [PASSED TAG]
-* [RUNNING] Batch 31 — `settings` table migration (V.1a) [WAITING TAG]
-* [LOCKED] Batch 32 — `SettingsStore` accessor with precedence + cache (V.1b) [NO TAG]
+* [DONE] Batch 31 — `settings` table migration (V.1a) [PASSED TAG]
+* [RUNNING] Batch 32 — `SettingsStore` accessor with precedence + cache (V.1b) [NO TAG]
 * [LOCKED] Batch 33 — Settings registry metadata (V.1a) [NO TAG]
 * [LOCKED] Batch 34 — `GET /api/admin/settings` (+ `/effective`, `/{key}`) (V.1b) [NO TAG]
 * [LOCKED] Batch 35 — `PATCH /api/admin/settings` (207) + `config_changed` WORM event (V.1b/V.5) [NO TAG]
@@ -299,4 +299,12 @@
 * **Identified System Flaws:** None.
 * **Defensive Refactoring Correction Blueprint:** None
 
+### TAG Batch 31 Evaluation Audit Report
+* **Verification Status:** PASSED TAG
+* **Target Scope Verification:** Verified file paths: `nce/schema.sql`, `nce/migrations/015_settings_table.sql`, and `tests/test_schema_bootstrap.py`.
+* **Structural Integrity Scoring:** Creation of a global, RLS-exempt `settings` table with native `JSONB` support and explicit encrypted byte column (`secret_enc`) is structurally clean and correctly keeps system-wide settings separated from tenant-scoped structures. The custom PL/pgSQL DO block correctly revokes PUBLIC permissions and grants least-privilege `SELECT`, `INSERT`, `UPDATE`, `DELETE` access to `nce_app` safely.
+* **Contractual Test Fidelity:** High. The test `test_schema_applies_cleanly_on_fresh_database` successfully boots the entire schema twice to verify idempotence, then queries PG's metadata tables (`information_schema.columns`, `pg_class`, `information_schema.role_table_grants`) directly to assert column types, nullability, RLS-exempt status (`relrowsecurity` is false), and role privileges (`SELECT`, `INSERT`, `UPDATE`, `DELETE` for `nce_app`).
+* **Identified System Flaws:** None.
+* **Defensive Refactoring Correction Blueprint:** None
+
 [EOF: END OF REFACTORING LEDGER]
\ No newline at end of file
```
