1. **One batch = one branch = one commit.** Branch name `batch-108-reembed-quality-gate-prod`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so.
4. **Minimal diff.** Reuse the existing `neighbor_overlap_fraction()` Jaccard helper and the `_audit_migration_action()` separate-connection WORM audit pattern. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing migration/reembedding tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** the forced-commit escape MUST emit a WORM audit event via the existing separate-connection `_audit_migration_action` path before proceeding; tenant-scoped context for all reads.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `vector-database-engineer` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/migration_mcp_handlers.py` (`handle_commit_migration`, `handle_start_migration`); `nce/reembedding_migration.py` (`neighbor_overlap_fraction` ~`:44-63`); `nce/config.py`; `tests/test_reembed_gate.py` (new)
**Goal:** The neighbor-overlap quality gate currently lives only in the in-memory test store; `handle_commit_migration` can promote v2→v1 ungated. Wire the gate into the real commit path so a bad embedding-model swap cannot silently corrupt retrieval.
**Steps:**
1. Add config: `NCE_REEMBED_GATE_SAMPLE` (int, default 200, min 1), `NCE_REEMBED_GATE_MIN_OVERLAP` (float, default 0.6, 0≤x≤1), `NCE_REEMBED_GATE_K` (int, default 10).
2. In `handle_commit_migration`: before the v2→v1 swap, sample up to `GATE_SAMPLE` memories for the namespace, compute `neighbor_overlap_fraction` (k=`GATE_K`) old-vs-new; if `< GATE_MIN_OVERLAP`, refuse the commit and return the score in the error payload. Accept `force: bool=false`; when `force=true`, proceed BUT emit a WORM audit event (reuse `_audit_migration_action`, event_type e.g. `migration_commit_forced`) carrying the score.
3. In `handle_start_migration`: add a dimension preflight — compare the target model's embedding dim against the column/vector type; mismatch ⇒ STOP with a clear error (do not start).
4. Keep all existing migration-orchestrator behavior otherwise unchanged.
**Acceptance:** `tests/test_reembed_gate.py`: synthetic corpus + perturbed "new model" below threshold ⇒ `handle_commit_migration` refused, score surfaced; identical model ⇒ passes; `force=true` on a failing gate ⇒ proceeds and emits the audit event; dimension mismatch ⇒ `handle_start_migration` STOPs. `make lint && make typecheck && pytest tests/test_reembed_gate.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 108 — reembed-quality-gate-prod`, paste the gate output, and wait for review.
