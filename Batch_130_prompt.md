1. **One batch = one branch = one commit.** Branch name `batch-130-epistemic-self-maintenance`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the contradiction resolution path (Batch 23 + 111), the `actor_trust` table (Batch 113), the cascade/retraction hooks, and the `CronLock`. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing contradiction/ATMS/trust tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** auto re-evaluation only acts on already-resolvable states (a side of a contradiction gone) — it must NOT auto-resolve genuinely open human-pending contradictions; tenant-scoped; events appended, never mutated.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `database-architect`
**Depends on:** Batch 111 (cascade residual), Batch 113 (trust)
**Files:** `nce/atms.py`; `nce/contradictions.py`; `nce/cron.py` (re-eval tick); `tests/test_epistemic_self_maintenance.py` (new)
**Goal:** Close the epistemic loop's remaining manual edges: when a memory is retracted/superseded, automatically re-evaluate its still-open contradictions; and feed contradiction-sourcing into the trust table so repeat offenders lose trust.
**Steps:**
1. On retraction/supersession of a memory (cascade path), find open `contradictions` rows referencing it and auto-resolve them as `superseded` when one side no longer exists — but ONLY when a side is genuinely gone; never touch contradictions where both sides remain (those stay human-pending). Append the standard resolution event.
2. Feed `actor_trust.contradictions_sourced` (Batch 113): when a contradiction is confirmed against an agent's asserted memory, increment that agent's counter so the hourly trust recompute penalizes it.
3. Optional safety: a cron tick that scans for stale auto-resolvable contradictions (a side retracted but contradiction left open) and resolves them, under `CronLock`.
**Acceptance:** `tests/test_epistemic_self_maintenance.py` (`@pytest.mark.integration`): retract one side of an open contradiction ⇒ it auto-resolves `superseded` with an event; a contradiction with both sides intact stays `pending`; a confirmed contradiction increments the sourcing agent's `contradictions_sourced` and lowers its next trust recompute. `make lint && make typecheck && pytest -m integration tests/test_epistemic_self_maintenance.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 130 — epistemic-self-maintenance`, paste the gate output, and wait for review.
