Batch 71 — stream-reduce

> Diagnostic Log Digestion Engine · Phase 2. Master plan: `_internal/work-docs/roadmaps/Diagnostic_Log_Digestion_Engine_Plan_2026-06-10.md`. Ledger: `_internal/Roadmaps/diagnostics_execution_ledger.md`.

## Operating rules (apply to this batch)
1. One batch = one branch = one commit. Branch `batch-71-stream-reduce`. Never combine batches.
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
- C4 Diff: `git add -A` → write `git diff --cached` to `_internal/diffs/diff_batch_71-stream-reduce.md`; set this row to `[WAITING TAG]` in the ledger.
- C5 TAG: run the audit yourself per `_internal/templates/tag_audit.md` — read the diff + every modified file end-to-end (no ellipsis/placeholders), apply architect-review/vibe-code-auditor/logic-lens/performance-optimizer/fix-review lenses, enforce WORM/RLS+secrets, emit `### TAG Batch 71 Evaluation Audit Report` matrix.
- C6 Resolve: if REJECTED → write TD+Findings+Kaizen, fix in-scope, re-run C2–C5 (out-of-scope fix → STOP). If PASSED → set ledger row `[PASSED TAG] Done`, commit `batch-71-stream-reduce`, open PR `Batch 71 — stream-reduce`.

---

**Skills:** `python-pro` (primary), `performance-optimizer`, `python-testing-patterns`
**Depends on:** 70 · **Parallel:** —
**Files:** **new** `nce/vertical_modules/diagnostics/streaming.py`.

**Goal:** The flat-memory Stream-and-Reduce core over archives or plain text.

**Steps:**
1. `stream_entries(local_path, *, max_uncompressed_bytes, max_entries) -> Iterator[tuple[str, str]]` (entry_name, line): detect zip/tar/gz by magic bytes; stream members one at a time (`zipfile.ZipFile.open`, `tarfile.open(mode="r|*")`); for plain text use a sliding-window line reader. Enforce a **zip-bomb guard** (cap cumulative uncompressed bytes + entry count; raise `PoisonBundleError` on breach).
2. `digest_stream(profile, lines) -> Digest`: accumulate a **bounded** anomaly list (cap `NCE_DIAG_MAX_ANOMALIES`, keep highest severity + `occurrences` counts) and per-`anomaly_type` 5-minute window aggregates; truncate samples to ≤200 chars. Return a small dataclass (`processed_lines`, `anomalies`, `windows`).
3. Define `class PoisonBundleError(Exception)` here for the worker to classify as non-retryable.

**Acceptance:** `tests/diagnostics/test_streaming.py` — feed a synthetic large temp archive; assert peak RSS stays bounded (`tracemalloc`), anomalies detected, list capped, zip-bomb guard raises. Pure-unit (no Docker). `make lint && make typecheck` clean.

Final (self-orchestrated — do not skip): run the Closing Protocol C1–C6 above — gate (`make lint && make typecheck && pytest tests/diagnostics/test_streaming.py`) → reviews → write `_internal/diffs/diff_batch_71-stream-reduce.md` + set ledger row `[WAITING TAG]` → run the TAG audit yourself per `_internal/templates/tag_audit.md` and emit the matrix → if REJECTED fix in-scope and re-run; if PASSED mark ledger Done, commit `batch-71-stream-reduce`, open PR `Batch 71 — stream-reduce`.
