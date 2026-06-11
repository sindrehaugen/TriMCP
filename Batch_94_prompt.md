Batch 94 — packaging-macos

> Diagnostic Log Digestion Engine · Phase 6 (installers). Master plan: `_internal/work-docs/roadmaps/Diagnostic_Log_Digestion_Engine_Plan_2026-06-10.md`. Ledger: `_internal/Roadmaps/diagnostics_execution_ledger.md`.

## Operating rules (apply to this batch)
1. One batch = one branch = one commit. Branch `batch-94-packaging-macos`. Never combine batches.
2. Verify before you act: open each target file and confirm the cited symbol exists. Line numbers are approximate (`~`) — trust the symbol name, not the number. On any mismatch/contradiction, STOP and report — do not invent a fix or create a new file.
3. Modify only the files listed below. No new modules/classes/deps/abstractions unless marked **new**. If you think you need one, STOP and report.
4. Minimal diff; reuse existing utilities. Match surrounding style. Any added Python obeys lint/typecheck.
5. Acceptance gate (all green before commit): `make lint`; `make typecheck` (for any added Python); the named smoke test (may be manual/CI, not pytest); touched tests still pass.
6. New migrations → `nce/migrations/` next free number (current max 018 → next 019); mirror into `nce/schema.sql`; never edit an existing migration.
7. WORM/RLS: tenant SQL inside `scoped_pg_session`; `append_event` in the same txn as its write; never UPDATE/DELETE `event_log`; no raw content/PII in `event_log.params`.
8. `NCE_MASTER_KEY` is env-only — never read/write it via DB/settings/endpoint. The installer must NOT bake secrets into the image; first-run config supplies them.
9. DB-dependent tests are `@pytest.mark.integration`; pure-unit batches must not need Docker.
10. Report: files changed, gate output, the TAG verdict matrix, anything you STOPped on.

## Closing protocol (self-orchestrated — do NOT use Antigravity scripts)
Reproduce `generate_diff.py`/`trigger_tag_audit.py`/`start_rl.py`/`generate_ledger.py` BY HAND. Diff + ledger files are exempt from rule 3.
- C1 Stop when steps done; do not start another batch.
- C2 Gate: run the rule-5 gate; all green or STOP.
- C3 Reviews: run `code-reviewer` then `fix-review` (+`simplify-code` if logic refactored); in-scope fixes only; out-of-scope → one-line Kaizen/TD note.
- C4 Diff: `git add -A` → write `git diff --cached` to `_internal/diffs/diff_batch_94-packaging-macos.md`; set this row to `[WAITING TAG]` in the ledger.
- C5 TAG: run the audit yourself per `_internal/templates/tag_audit.md` — read the diff + every modified file end-to-end (no ellipsis/placeholders), apply architect-review/vibe-code-auditor/logic-lens/performance-optimizer/fix-review lenses, enforce WORM/RLS+secrets, emit `### TAG Batch 94 Evaluation Audit Report` matrix.
- C6 Resolve: if REJECTED → write TD+Findings+Kaizen, fix in-scope, re-run C2–C5 (out-of-scope fix → STOP). If PASSED → set ledger row `[PASSED TAG] Done`, commit `batch-94-packaging-macos`, open PR `Batch 94 — packaging-macos`.

---

**Skills:** `macos-spm-app-packaging` (primary), `python-packaging`
**Depends on:** 84 · **Parallel:** group E (93,94,95,98)
**Files:** **new** `packaging/macos/` (py2app/PyInstaller bundle + `launchd` plists + signing/notarization notes).

**Goal:** A signed/notarized `.dmg` with launchd-managed edge services.

**Steps:**
1. py2app/PyInstaller app bundle for the edge process set.
2. `launchd` agent plists (auto-start, KeepAlive); code-signing + notarization notes/script.
3. First-run config as in the Windows batch (role=edge, ingest URL, credentials, backend, caps); uninstall purges local raw data.

**Acceptance:** documented clean-host/VM smoke test (install → launchd starts services → sample bundle digests → uninstall purges local raw data). `make lint && make typecheck` clean for any added Python.

Final (self-orchestrated — do not skip): run the Closing Protocol C1–C6 above — gate (lint/typecheck for added Python + the documented smoke test) → reviews → write `_internal/diffs/diff_batch_94-packaging-macos.md` + set ledger row `[WAITING TAG]` → run the TAG audit yourself per `_internal/templates/tag_audit.md` and emit the matrix → if REJECTED fix in-scope and re-run; if PASSED mark ledger Done, commit `batch-94-packaging-macos`, open PR `Batch 94 — packaging-macos`.
