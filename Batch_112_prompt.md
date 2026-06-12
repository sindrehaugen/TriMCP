1. **One batch = one branch = one commit.** Branch name `batch-112-signal-consequences`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing `confirm_memory`/`reject_memory` flow, `append_event`, the salience upsert helper, and `event_types.py` constants. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing active-learning tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** rejection must record a WORM event carrying the payload HASH only (never raw payload — PII); tenant-scoped; no `event_log` mutation.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary)
**Depends on:** none (Batch 113 builds on the events this emits)
**Files:** `nce/active_learning.py` (`confirm_memory`, `reject_memory`); `nce/event_types.py`; `tests/test_active_learning_signals.py` (new or extend existing)
**Goal:** Human quarantine decisions currently have no downstream consequence — confirmed memories enter at default salience and rejections vanish with no record. Give both a consequence so the signal is usable (and so Batch 113 can aggregate it).
**Steps:**
1. Add event types `quarantine_confirmed` and `quarantine_rejected` to `event_types.py`.
2. `confirm_memory`: after the store saga, set an initial salience prior of `0.65` (constant for now; Batch 113 makes it trust-derived) instead of the default; append `quarantine_confirmed` with `{queue_item_id, agent_id, operator_id}`.
3. `reject_memory`: before discarding, append `quarantine_rejected` with `{queue_item_id, agent_id, operator_id, payload_sha256}` — hash the stashed payload; never log the payload itself.
4. No schema change; reuse the existing `memory_salience` upsert.
**Acceptance:** `tests/test_active_learning_signals.py` (`@pytest.mark.integration`): confirm ⇒ memory persisted with salience ≈0.65 and a `quarantine_confirmed` event; reject ⇒ payload discarded, a `quarantine_rejected` event with a `payload_sha256` (and no raw payload) appended; confirmed memory outranks a default-stored peer in a retrieval check. `make lint && make typecheck && pytest -m integration tests/test_active_learning_signals.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 112 — signal-consequences`, paste the gate output, and wait for review.
