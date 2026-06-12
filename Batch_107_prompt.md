1. **One batch = one branch = one commit.** Branch name `batch-107-derivation-depth-guard`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse the existing consolidation cluster flow, `compute_decayed_score` neighbors, the `_int_env`/`_float_env` config helpers, and the settings-registry descriptor pattern. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing consolidation tests still pass
6. **Migrations:** add `nce/migrations/023_derivation_depth.sql` (confirm 023 free) + mirror into `nce/schema.sql`.
7. **WORM/RLS invariants (never violate):** tenant-scoped context for all SQL; no `event_log` mutation. Consolidation already appends events — leave that untouched.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `database-architect`
**Depends on:** none (pairs with Batch 106 but no hard dep)
**Files:** `nce/migrations/023_derivation_depth.sql` (new); `nce/schema.sql` (`memories`); `nce/consolidation.py` (cluster input selection ~`:188-233`, derived-edge insert ~`:321-333`, abstraction row insert); `nce/config.py`; `nce/settings_registry.py`; `tests/test_consolidation_depth.py` (new)
**Goal:** Stop hallucination compounding across consolidation generations. Add `memories.derivation_depth SMALLINT NOT NULL DEFAULT 0`; consolidated rows get `max(parent depth)+1`; exclude memories at/above `cfg.NCE_MAX_DERIVATION_DEPTH` (default 2) from clustering input; attenuate derived KG-edge confidence by generation: `confidence = abstraction.confidence × γ^depth` where γ = `cfg.NCE_DERIVATION_CONFIDENCE_DECAY` (default 0.85).
**Steps:**
1. Migration 023 + schema.sql: add `derivation_depth`; backfill via recursive CTE over `derived_from` (depth from episodic roots). Add partial index `(namespace_id, derivation_depth)`. If `derived_from` is not a queryable JSONB array of parent ids, STOP and report its real shape.
2. Config: add `NCE_MAX_DERIVATION_DEPTH` (int, default 2, min 1) and `NCE_DERIVATION_CONFIDENCE_DECAY` (float, default 0.85, 0<γ≤1) via the existing env helpers; register both as hot-reloadable settings descriptors in the consolidation domain.
3. `consolidation.py`: when selecting cluster input, exclude rows with `derivation_depth >= NCE_MAX_DERIVATION_DEPTH`; when inserting the consolidated memory, set its `derivation_depth = max(source depths)+1`; when inserting derived kg_edges, multiply confidence by `γ^(new depth)`.
4. Do not change the confidence floor (0.3) or supporting-id validation — only add the depth gate and attenuation.
**Acceptance:** `tests/test_consolidation_depth.py` (`@pytest.mark.integration`): build `episodic(d0) → consolidated(d1) → consolidated(d2)`; assert a third-generation cluster that would produce d3 is refused (sources filtered out); assert derived-edge confidence on the d1 abstraction equals `abstraction_conf × 0.85`. `make lint && make typecheck && pytest -m integration tests/test_consolidation_depth.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 107 — derivation-depth-guard`, paste the gate output, and wait for review.
