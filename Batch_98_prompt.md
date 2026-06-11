Batch 98 — standalone-guide

> Diagnostic Log Digestion Engine · Docs (Phase 0 deliverable). Master plan: `_internal/work-docs/roadmaps/Diagnostic_Log_Digestion_Engine_Plan_2026-06-10.md`. Ledger: `_internal/Roadmaps/diagnostics_execution_ledger.md`.

## Operating rules (apply to this batch)
1. One batch = one branch = one commit. Branch `batch-98-standalone-guide`. Never combine batches.
2. Verify before you act: confirm the referenced central tools (Batches 65–84) exist before describing them as available; if a described capability is not yet merged, mark it clearly as "planned". On any contradiction, STOP and report.
3. Modify only the file listed below. No code changes. If you think code is needed, STOP and report.
4. Minimal, accurate prose; reuse terminology from the master plan and concept doc. Match the house doc style of `_internal/work-docs/roadmaps/`.
5. Acceptance gate: a prose/readability + technical-accuracy review (NOT pytest — docs-only). No lint/typecheck unless code is touched (it must not be).
6. (Migrations rule — n/a for docs.)
7. WORM/RLS/secrets: do not document secret values; describe the trust model only. Never include real credentials.
8. `NCE_MASTER_KEY` is env-only — reference it only as an environment secret, never with a value.
9. (Integration-test rule — n/a for docs.)
10. Report: file written, the review outcome, the TAG verdict matrix, anything you STOPped on.

## Closing protocol (self-orchestrated — do NOT use Antigravity scripts)
Reproduce `generate_diff.py`/`trigger_tag_audit.py`/`start_rl.py`/`generate_ledger.py` BY HAND. Diff + ledger files are exempt from rule 3.
- C1 Stop when steps done; do not start another batch.
- C2 Gate: run a prose/readability + accuracy review (docs-only; skip pytest).
- C3 Reviews: run `code-reviewer` (as a doc/prose reviewer) + a clarity pass; in-scope fixes only; out-of-scope → one-line Kaizen/TD note.
- C4 Diff: `git add -A` → write `git diff --cached` to `_internal/diffs/diff_batch_98-standalone-guide.md`; set this row to `[WAITING TAG]` in the ledger.
- C5 TAG: run the audit yourself per `_internal/templates/tag_audit.md` on the prose (no source diff) — read the full document, check technical accuracy vs the master plan and the merged central tools, emit `### TAG Batch 98 Evaluation Audit Report` matrix.
- C6 Resolve: if REJECTED → write TD+Findings+Kaizen, fix in-scope, re-run C2–C5. If PASSED → set ledger row `[PASSED TAG] Done`, commit `batch-98-standalone-guide`, open PR `Batch 98 — standalone-guide`.

---

**Skills:** `technical-writing` (primary) *(or `docs-architect`)*, `beautiful-prose`
**Depends on:** 77 (central tools exist) · **Parallel:** group E (93,94,95,98)
**Files:** **new** `_internal/work-docs/diagnostics/Diagnostic_Log_Digestion_Guide.md`.

**Goal:** The standalone user guide (seller/boss intro → technical → operations), per Phase 0 of the plan.

**Steps:** Write the 7 sections from the plan's "Phase 0 / Docs":
1. Executive / seller intro (non-technical): the problem (hundreds of MB of AV/UC logs, slow manual root-cause, truck rolls), the outcome (instant device-linked root cause; fewer site visits; privacy-by-design — raw logs stay on site; works offline), where it runs (cloud core + optional on-site edge appliance); one diagram, benefit bullets, a short "day in the life".
2. How it works (at a glance): Stream-and-Reduce + central-vs-edge split, plain terms.
3. Using it (operators): triggering a bundle from the support frontend/ticketing; reading device health & anomalies; what the NetBox high-level view shows.
4. Technical architecture: pipeline, cognitive layers, vendor profile registry, NetBox enrichment, write-back, security/RLS/zero-copy.
5. Deployment & installers: per-platform install steps (.exe/.dmg/.deb/Proxmox), first-run config, sizing (Ultra i5/16 GB), NPU enablement.
6. Operations: offline/autonomous behavior, sync & spool, retention caps, troubleshooting, upgrades.
7. Security & compliance: data residency, PII posture, credential/signature trust model.

**Acceptance:** prose/accuracy review only; no lint/type/test (docs-only).

Final (self-orchestrated — do not skip): run the Closing Protocol C1–C6 above, treating C2 as a docs review (skip pytest) and C5 as a prose TAG audit (no source diff) → write `_internal/diffs/diff_batch_98-standalone-guide.md` + set ledger row `[WAITING TAG]` → emit the matrix → if REJECTED fix in-scope and re-run; if PASSED mark the ledger row Done, commit `batch-98-standalone-guide`, open PR `Batch 98 — standalone-guide`.
