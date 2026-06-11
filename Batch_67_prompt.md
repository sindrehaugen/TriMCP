Batch 67 — diag-schema

> Diagnostic Log Digestion Engine · Phase 1. Master plan: `_internal/work-docs/roadmaps/Diagnostic_Log_Digestion_Engine_Plan_2026-06-10.md`. Ledger: `_internal/Roadmaps/diagnostics_execution_ledger.md`.

## Operating rules (apply to this batch)
1. One batch = one branch = one commit. Branch `batch-67-diag-schema`. Never combine batches.
2. Verify before you act: open each target file and confirm the cited symbol exists. Line numbers are approximate (`~`) — trust the symbol name, not the number. On any mismatch/contradiction, STOP and report — do not invent a fix or create a new file.
3. Modify only the files listed below. No new modules/classes/deps/abstractions unless marked **new**. If you think you need one, STOP and report.
4. Minimal diff; reuse existing utilities (`scoped_pg_session`, `unmanaged_pg_connection`, `append_event`, `consume_resources`, `acquire_cron_lock`, `get_priority_queue`/`enqueue_traced`, `traced_worker_job`, `_check_poison_pill`/`store_dead_letter`, `generate_secure_presigned_url`, `require_master_key`). Match surrounding style.
5. Acceptance gate (all green before commit): `make lint`; `make typecheck`; the named test; any touched tests; if MCP tool counts changed, update `tests/test_tool_registry.py` exact-count asserts in THIS batch.
6. New migrations → `nce/migrations/` next free number (current max 018 → next 019); mirror into `nce/schema.sql`; never edit an existing migration.
7. WORM/RLS: tenant SQL inside `scoped_pg_session`; `append_event` in the same txn as its write; never UPDATE/DELETE `event_log`; no raw content/PII in `event_log.params`.
8. `NCE_MASTER_KEY` is env-only — never read/write it via DB/settings/endpoint.
9. DB-dependent tests are `@pytest.mark.integration` (run via `pytest -m integration` against `make local-up`); pure-unit batches must not need Docker.
10. Report: files changed, gate output, the TAG verdict matrix, anything you STOPped on.

## Closing protocol (self-orchestrated — do NOT use Antigravity scripts)
Reproduce `generate_diff.py`/`trigger_tag_audit.py`/`start_rl.py`/`generate_ledger.py` BY HAND. Diff + ledger files are exempt from rule 3.
- C1 Stop when steps done; do not start another batch.
- C2 Gate: run the rule-5 gate; all green or STOP.
- C3 Reviews: run `code-reviewer` then `fix-review` (+`simplify-code` if logic refactored); in-scope fixes only; out-of-scope → one-line Kaizen/TD note.
- C4 Diff: `git add -A` → write `git diff --cached` to `_internal/diffs/diff_batch_67-diag-schema.md`; set this row to `[WAITING TAG]` in the ledger.
- C5 TAG: run the audit yourself per `_internal/templates/tag_audit.md` — read the diff + every modified file end-to-end (no ellipsis/placeholders), apply architect-review/vibe-code-auditor/logic-lens/performance-optimizer/fix-review lenses, enforce WORM/RLS+secrets, emit `### TAG Batch 67 Evaluation Audit Report` matrix.
- C6 Resolve: if REJECTED → write TD+Findings+Kaizen, fix in-scope, re-run C2–C5 (out-of-scope fix → STOP). If PASSED → set ledger row `[PASSED TAG] Done`, commit `batch-67-diag-schema`, open PR `Batch 67 — diag-schema`.

---

**Skills:** `postgresql` (primary), `database-migration`, `postgres-best-practices`
**Depends on:** none · **Parallel:** group A (65,66,67,68)
**Files:** **new** `nce/migrations/019_diagnostics.sql`; `nce/schema.sql` (table defs + RLS `tenant_tables` array ~`:1153`). Reference `nce/migrations/010_citus_sharding.sql` (`topology_graph` ~`:91`).

**Goal:** Create the three diagnostics tables, fix the `topology_graph` duplicate-edge gap, and apply RLS.

**Steps:**
1. In `019_diagnostics.sql` (mirror into `schema.sql`) create:
   - `diag_ingestions(id uuid pk default gen_random_uuid(), namespace_id uuid not null references namespaces(id) on delete cascade, ingest_id text not null, source text check (source in ('upload','api','ticketing')), vendor_profile text, device_slug text, landing_uri text, status text not null default 'PENDING' check (status in ('PENDING','PROCESSING','DIGESTED','FAILED')), bytes bigint, processed_lines bigint, anomaly_count int, digest_payload_ref text, created_at timestamptz default now(), updated_at timestamptz default now(), unique(namespace_id, ingest_id))`.
   - `diag_anomalies(id uuid pk default gen_random_uuid(), namespace_id uuid not null references namespaces(id) on delete cascade, ingestion_id uuid not null references diag_ingestions(id) on delete cascade, device_slug text, anomaly_type text, severity int, first_line bigint, occurrences int, sample text, window_start timestamptz, window_end timestamptz, created_at timestamptz default now())` — the writer truncates `sample` to ≤200 chars.
   - `device_health_rollup(namespace_id uuid not null references namespaces(id) on delete cascade, device_slug text not null, health_state text check (health_state in ('HEALTHY','DEGRADED','CRITICAL')), top_anomaly_type text, anomaly_score float8, last_ingestion_id uuid, last_seen_at timestamptz, primary key(namespace_id, device_slug))`.
2. Add `CREATE UNIQUE INDEX IF NOT EXISTS uq_topology_edge ON topology_graph(namespace_id, source_node_id, target_node_id, edge_type)`. Verify no duplicate rows would block it; if they might, add a guarded dedup note in the migration comment (do NOT issue a destructive delete without confirming).
3. Add `diag_ingestions`, `diag_anomalies`, `device_health_rollup` to the `tenant_tables` array so `tenant_isolation_policy` is applied; add per-table `namespace_id` indexes.
4. **(Architectural audit — Domain 5 / D1, tenant-bleed, HIGH):** `topology_graph` was created in `010_citus_sharding.sql` with `ENABLE ROW LEVEL SECURITY` but **never `FORCE`** — so the table-owner / `nce_gc` (BYPASSRLS-adjacent) role can read/write every tenant's network topology with `nce.namespace_id` unset. In `019_diagnostics.sql` (mirror into `schema.sql`) add `ALTER TABLE topology_graph FORCE ROW LEVEL SECURITY;` (idempotent; place it next to the existing `topology_graph` policy or fold `topology_graph` into the `tenant_tables` loop if its `namespace_id`/policy shape matches — verify the column and existing `topology_graph_tenant_isolation` policy first; if folding would drop a differently-named policy, keep the standalone `FORCE` instead). Do NOT edit migration `010`.

**Acceptance:** `@pytest.mark.integration` test (run via `make local-up`) that applies the migration then asserts: (a) RLS denies a cross-namespace read of `diag_ingestions`; (b) `topology_graph` reports `relforcerowsecurity = true` in `pg_class` (proving FORCE is on). `make lint && make typecheck` clean.

Final (self-orchestrated — do not skip): run the Closing Protocol C1–C6 above — gate (`make lint && make typecheck && pytest -m integration <the RLS test>`) → reviews → write `_internal/diffs/diff_batch_67-diag-schema.md` + set ledger row `[WAITING TAG]` → run the TAG audit yourself per `_internal/templates/tag_audit.md` and emit the matrix → if REJECTED fix in-scope and re-run; if PASSED mark ledger Done, commit `batch-67-diag-schema`, open PR `Batch 67 — diag-schema`.
