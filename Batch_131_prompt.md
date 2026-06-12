1. **One batch = one branch = one commit.** Branch name `batch-131-decay-param-learning`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the `temporal_decay` stability-score table, the soft-delete/prune sweep, the `CronLock`, the settings-registry descriptor pattern, and `append_event` for `config_changed`. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing temporal-decay/cron tests still pass
6. **Migrations:** none (per-class/per-namespace overrides live in the existing settings table; if a stats table is truly required, STOP and report rather than adding a migration here).
7. **WORM/RLS invariants (never violate):** every auto-tune adjustment emits a `config_changed` WORM event (never silently mutate decay params); tenant-scoped; the auto-tune phase is behind a feature flag default-OFF.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `data-scientist` (primary), `python-pro`
**Depends on:** Batch 113 (trust/learning infrastructure pattern)
**Files:** `nce/temporal_decay.py`; `nce/cron.py` (weekly stats + optional tune tick); `nce/admin_handlers/fleet.py` (dashboard panel data); `nce/settings_registry.py`; `nce/config.py`; `tests/test_decay_learning.py` (new)
**Goal:** Decay stability scores are hard-coded with no feedback. Make them learn from data — but never silently. Phase 4a: report-only per-class post-prune miss-rate. Phase 4b: feature-flagged auto-tune, every change WORM-audited.
**Steps:**
1. Phase 4a (always on): a weekly cron computes, per memory class, a "post-prune miss rate" — retrievals (sampled from the query log / soft-deleted matches) that would have matched a pruned memory — plus the recall-reinforcement distribution. Expose via a `fleet.py` dashboard data endpoint. No parameter changes.
2. Phase 4b (behind `cfg.NCE_DECAY_AUTOTUNE_ENABLED`, default false): adjust each class's stability score ±10%/week toward a target miss rate (`cfg.NCE_DECAY_TARGET_MISS_RATE`, default 0.02), bounded to [0.5×, 2×] of the hard-coded defaults. Each adjustment writes a `config_changed` WORM event and goes through the settings store (so it is itself time-travelable/rollbackable via Batch 54).
3. Register config knobs + per-class override descriptors.
**Acceptance:** `tests/test_decay_learning.py` (`@pytest.mark.integration`): the weekly stats tick computes a per-class miss rate and exposes it (no param change while autotune off); with autotune on, a class above target miss-rate has its stability nudged within ±10% and bounds, and a `config_changed` event is emitted; rollback via the settings store restores the prior value. `make lint && make typecheck && pytest -m integration tests/test_decay_learning.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 131 — decay-param-learning`, paste the gate output, and wait for review.
