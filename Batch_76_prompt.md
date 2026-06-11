Batch 76 — diag-mcp-handlers

> Diagnostic Log Digestion Engine · Phase 2. Master plan: `_internal/work-docs/roadmaps/Diagnostic_Log_Digestion_Engine_Plan_2026-06-10.md`. Ledger: `_internal/Roadmaps/diagnostics_execution_ledger.md`.

## Operating rules (apply to this batch)
1. One batch = one branch = one commit. Branch `batch-76-diag-mcp-handlers`. Never combine batches.
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
- C4 Diff: `git add -A` → write `git diff --cached` to `_internal/diffs/diff_batch_76-diag-mcp-handlers.md`; set this row to `[WAITING TAG]` in the ledger.
- C5 TAG: run the audit yourself per `_internal/templates/tag_audit.md` — read the diff + every modified file end-to-end (no ellipsis/placeholders), apply architect-review/vibe-code-auditor/logic-lens/performance-optimizer/fix-review lenses, enforce WORM/RLS+secrets, emit `### TAG Batch 76 Evaluation Audit Report` matrix.
- C6 Resolve: if REJECTED → write TD+Findings+Kaizen, fix in-scope, re-run C2–C5 (out-of-scope fix → STOP). If PASSED → set ledger row `[PASSED TAG] Done`, commit `batch-76-diag-mcp-handlers`, open PR `Batch 76 — diag-mcp-handlers`.

---

**Skills:** `python-pro` (primary), `mcp-builder`
**Depends on:** 67, 69 · **Parallel:** —
**Files:** **new** `nce/vertical_modules/diagnostics/mcp_handlers.py`. Reference handler shape in `nce/vertical_modules/dynamics365/mcp_handlers.py`.

**Goal:** The async MCP handlers (no registry change yet — that is Batch 77).

**Steps:**
1. `async def handle_diag_ingest_bundle(engine, arguments) -> str` (mutation): validate vendor/device, call `ensure_landing_bucket`, return a tenant-prefixed presigned **PUT** URL, and register a `PENDING` `diag_ingestions` row with deterministic `ingest_id = sha256(landing_uri + etag-or-uuid)`.
2. `handle_diag_commit_bundle` — enqueue `process_diag_bundle` on the `diag_ingest` lane (string path + kwargs, `job_timeout=cfg.NCE_DIAG_JOB_TIMEOUT_MIN*60`).
3. `handle_diag_digest_status`, `handle_diag_device_health`, `handle_diag_list_anomalies` — read-only, namespace-scoped via `scoped_pg_session`; all return JSON strings.
4. Every handler must reject (clean error JSON) when `cfg.NCE_DIAG_ENABLED` is false.

**Acceptance:** `tests/diagnostics/test_mcp_handlers.py` with mocked engine/minio asserting handlers return JSON strings and reject when disabled. Pure-unit. `make lint && make typecheck` clean.

Final (self-orchestrated — do not skip): run the Closing Protocol C1–C6 above — gate (`make lint && make typecheck && pytest tests/diagnostics/test_mcp_handlers.py`) → reviews → write `_internal/diffs/diff_batch_76-diag-mcp-handlers.md` + set ledger row `[WAITING TAG]` → run the TAG audit yourself per `_internal/templates/tag_audit.md` and emit the matrix → if REJECTED fix in-scope and re-run; if PASSED mark ledger Done, commit `batch-76-diag-mcp-handlers`, open PR `Batch 76 — diag-mcp-handlers`.
