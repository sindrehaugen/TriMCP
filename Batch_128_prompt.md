1. **One batch = one branch = one commit.** Branch name `batch-128-action-approval-queue`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps beyond the approval table + handlers described. **No mutating external calls yet** — that is Batch 129. This batch is the safety rail only.
4. **Minimal diff.** Reuse the quarantine queue pattern (`active_learning.py`), the trust score (Batch 113), `append_event`, and the admin handler pattern. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing active-learning/admin tests still pass
6. **Migrations:** NONE. The `action_approval_queue` table (RLS-enabled) was established by **Batch C0** (already in `main`). Verify it exists; do NOT add a migration or edit `schema.sql`. If absent, STOP — C0 was not merged.
7. **WORM/RLS invariants (never violate):** new table RLS-enabled + forced; every confirm/reject emits a WORM event; tenant-scoped; nothing here calls an external system.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `database-architect` (primary), `python-pro`
**Depends on:** Batch 106 (origin), Batch 113 (trust), Batch 116 (nonces) — confirm all merged before starting
**Files:** `nce/active_learning.py` (or a sibling using the same pattern — do NOT create a new module if the pattern fits here); `nce/admin_handlers/` (approve/reject endpoints — note: read-only GET shapes already exist from C0); `nce/event_types.py`; `nce/config.py`; `tests/test_action_approval.py` (new)
**Goal:** Before any agent can mutate an external system (Batch 129), build the human-gated rail: proposed mutations land in an approval queue (dry-run by default), an operator confirms/rejects, and high-trust agents + low-risk action types can be auto-approved per namespace policy. Trust widens this bypass but NEVER bypasses the queue's existence.
**Steps:**
1. Verify the C0 `action_approval_queue` table exists (cols incl. `status` CHECK in pending/approved/rejected/executed/expired, `proposed_payload`, `dry_run_result`, `resolved_*`) with FORCE RLS, and the read-only GET endpoints C0 shipped. (No DDL here.) This batch adds the WRITE/transition behavior + auto-approve policy on top.
2. Enqueue API: a proposed action is stored `pending` with `dry_run=true` semantics; the stored `proposed_payload` is exactly what would be sent (no execution here).
3. Approve/reject admin endpoints: approve ⇒ status `approved` + `action_approved` WORM event (execution is Batch 129); reject ⇒ `rejected` + `action_rejected` event. 
4. Auto-approve policy: read `namespaces.metadata.<system>.auto_approve` + agent trust (Batch 113) ≥ `cfg.NCE_ACTION_AUTOAPPROVE_TRUST` (default 0.85) AND action_type in a low-risk allowlist ⇒ mark `approved` automatically with an `action_auto_approved` event. Everything else stays `pending`.
**Acceptance:** `tests/test_action_approval.py` (`@pytest.mark.integration`): a proposed action lands `pending` with dry-run payload; operator approve/reject transitions + WORM events fire; a high-trust agent + low-risk type + namespace policy ⇒ auto-approved; a low-trust agent or high-risk type ⇒ stays `pending`. `make lint && make typecheck && pytest -m integration tests/test_action_approval.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 128 — action-approval-queue`, paste the gate output, and wait for review.
