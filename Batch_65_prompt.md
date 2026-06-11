Batch 65 — diag-config

> Diagnostic Log Digestion Engine · Phase 1. Master plan: `_internal/work-docs/roadmaps/Diagnostic_Log_Digestion_Engine_Plan_2026-06-10.md`. Ledger: `_internal/Roadmaps/diagnostics_execution_ledger.md`.

## Operating rules (apply to this batch)
1. One batch = one branch = one commit. Branch `batch-65-diag-config`. Never combine batches.
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
- C4 Diff: `git add -A` → write `git diff --cached` to `_internal/diffs/diff_batch_65-diag-config.md`; set this row to `[WAITING TAG]` in the ledger.
- C5 TAG: run the audit yourself per `_internal/templates/tag_audit.md` — read the diff + every modified file end-to-end (no ellipsis/placeholders), apply architect-review/vibe-code-auditor/logic-lens/performance-optimizer/fix-review lenses, enforce WORM/RLS+secrets, emit `### TAG Batch 65 Evaluation Audit Report` matrix.
- C6 Resolve: if REJECTED → write TD+Findings+Kaizen, fix in-scope, re-run C2–C5 (out-of-scope fix → STOP). If PASSED → set ledger row `[PASSED TAG] Done`, commit `batch-65-diag-config`, open PR `Batch 65 — diag-config`.

---

**Skills:** `python-pro` (primary), `clean-code`
**Depends on:** none · **Parallel:** group A (65,66,67,68)
**Files:** `nce/config.py` (the `NCE_D365_*` block ~`:741`; helpers `_int_env`/`_float_env` at top of file); `.env.example` (only if it documents config — verify first).

**Goal:** Add the `NCE_DIAG_*` configuration surface, matching the existing typed-env pattern exactly.

**Steps:**
1. Confirm `_int_env(key, default, minimum=…)` and the bool idiom `os.getenv(...).strip().lower() in ("1","true","yes")` exist. If not, STOP.
2. Add, in the same style and block:
   - `NCE_DIAG_ENABLED` (bool, default false)
   - `NCE_DIAG_LANDING_BUCKET` (str, default `"nce-diag-landing"`)
   - `NCE_DIAG_LANDING_TTL_DAYS` (`_int_env`, 7, minimum 1)
   - `NCE_DIAG_MAX_BUNDLE_MB` (`_int_env`, 700, minimum 1)
   - `NCE_DIAG_MAX_ANOMALIES` (`_int_env`, 50, minimum 1)
   - `NCE_DIAG_JOB_TIMEOUT_MIN` (`_int_env`, 45, minimum 1)
   - `NCE_DIAG_CRASH_STORM_THRESHOLD` (`_int_env`, 10, minimum 1)
   - `NCE_DIAG_CRASH_STORM_WINDOW_SEC` (`_int_env`, 300, minimum 1)
   - `NCE_DIAG_TMPDIR` (str, default `""` = system temp)
3. Add matching documented entries to `.env.example` if that file exists and documents config.

**Acceptance:** new `tests/test_config_diag.py` asserting defaults and that `NCE_DIAG_ENABLED` parses `"true"/"1"/"yes"` truthy and other values falsy. Pure-unit. `make lint && make typecheck` clean.

Final (self-orchestrated — do not skip): run the Closing Protocol C1–C6 above — gate (`make lint && make typecheck && pytest tests/test_config_diag.py`) → reviews → write `_internal/diffs/diff_batch_65-diag-config.md` + set ledger row `[WAITING TAG]` → run the TAG audit yourself per `_internal/templates/tag_audit.md` and emit the matrix → if REJECTED fix TD/Findings/Kaizen in-scope and re-run; if PASSED mark the ledger row Done, commit `batch-65-diag-config`, open PR `Batch 65 — diag-config`.
