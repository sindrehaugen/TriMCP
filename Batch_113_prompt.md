1. **One batch = one branch = one commit.** Branch name `batch-113-actor-trust-scores`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps beyond the table + cron tick described.
4. **Minimal diff.** Reuse the cron `CronLock` pattern, the store-time confidence-prior hook from Batch 112, and the settings-registry descriptor pattern. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing cron + active-learning + memory tests still pass
6. **Migrations:** NONE. The `actor_trust` table (RLS-enabled) was established by **Batch C0** (already in `main`). Verify it exists; do NOT add a migration or edit `schema.sql`. If absent, STOP — C0 was not merged.
7. **WORM/RLS invariants (never violate):** new table is RLS-enabled + forced; cron recompute runs under the per-namespace scoped context; no `event_log` mutation.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `database-architect` (primary), `python-pro`
**Depends on:** Batch 112 (emits the confirm/reject events this aggregates)
**Files:** `nce/cron.py` (new tick); `nce/active_learning.py` (consume trust); `nce/orchestrators/memory.py` (store-time prior); `nce/config.py`; `nce/settings_registry.py`; `tests/test_actor_trust.py` (new)
**Goal:** Aggregate human decisions into a per-actor trust score and feed it back into behavior — so the system learns from accumulated judgment instead of treating every confirmation as one-off.
**Steps:**
1. Verify the C0 `actor_trust` table exists (cols: `confirmations`, `rejections`, `contradictions_sourced`, `trust`, `updated_at`; PK `(namespace_id, actor_id, actor_kind)`) with FORCE RLS. (No DDL here.)
2. `cron.py`: hourly tick under `CronLock` recomputing from the `quarantine_confirmed`/`quarantine_rejected` events (Batch 112) and contradiction-sourced counts: `trust = clamp(0.1, 0.95, (confirms+1)/(confirms+rejections+2) − 0.05·log1p(contradictions_sourced))` (Laplace-smoothed).
3. Consume: in `orchestrators/memory.py`, multiply the store-time confidence prior by source-agent trust; in `active_learning.py`, replace the Batch 112 constant 0.65 with `0.5 + 0.3·operator_trust`, and make the quarantine threshold dynamic (high-trust agents bypass quarantine for mid-confidence; low-trust quarantine more) via config knobs.
4. Config: `NCE_TRUST_QUARANTINE_BYPASS` (float, default 0.8), `NCE_TRUST_DEFAULT` (float, default 0.65); register both.
**Acceptance:** `tests/test_actor_trust.py` (`@pytest.mark.integration`): seed confirm/reject events for two agents ⇒ cron computes diverging trust; high-trust agent's mid-confidence assertion bypasses quarantine, low-trust agent's is quarantined; store-time confidence reflects trust multiplier. `make lint && make typecheck && pytest -m integration tests/test_actor_trust.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 113 — actor-trust-scores`, paste the gate output, and wait for review.
