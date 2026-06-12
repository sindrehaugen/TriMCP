1. **One batch = one branch = one commit.** Branch name `batch-110-outbox-idempotency`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules/deps beyond the dedup table + decorator described here.
4. **Minimal diff.** Reuse the existing `FOR UPDATE SKIP LOCKED` poll loop, the single-transaction handler/mark-published flow, and the DLQ routing. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing outbox/relay tests still pass
6. **Migrations:** NONE. The `processed_outbox_events` table (RLS-enabled) was established by **Batch C0** (already in `main`). Verify it exists; do NOT add a migration or edit `schema.sql`. If absent, STOP — C0 was not merged.
7. **WORM/RLS invariants (never violate):** the dedup insert MUST be in the SAME transaction as the handler's DB effects; tenant-scoped; RLS-enabled on the new table; the no-Redis-I/O-inside-transaction rule for handlers stays enforced.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `event-store-design` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/outbox_relay.py` (poll/deliver/mark loop + handler registry); `nce/tasks.py` (handler signatures); `tests/test_outbox_idempotency.py` (new)
**Goal:** Relay semantics are at-least-once but the module comment claims at-most-once and the handler registry is hardcoded to one event type. Make consumers idempotent and the registry extensible. (1) Fix the docstring to state the at-least-once contract. (2) Add `processed_outbox_events(event_id UUID PK, namespace_id UUID, processed_at TIMESTAMPTZ)` RLS-enabled. (3) Convert the hardcoded handler dict to decorator registration.
**Steps:**
1. Verify the C0 `processed_outbox_events` table exists with FORCE RLS + tenant policy. (No DDL here.)
2. `outbox_relay.py`: in the delivery transaction, INSERT the event_id into `processed_outbox_events` alongside the handler's effects; on crash-redelivery, skip events whose id already exists (idempotent). Pass handlers `(event_id, aggregate_type, aggregate_id, event_type, payload)`.
3. Replace the hardcoded handler map with an `@outbox_handler("memory.stored")`-style decorator registry; the registration wrapper asserts handlers perform no Redis/sync I/O inside the transaction (preserve the existing rule). Re-register the current `memory.stored` handler via the decorator so behavior is unchanged.
4. Correct the module docstring/comment from "at-most-once" to "at-least-once with consumer idempotency."
**Acceptance:** `tests/test_outbox_idempotency.py` (`@pytest.mark.integration`): crash-injection between handler success and mark-published ⇒ event reprocessed exactly once observably (dedup row prevents double effect); registering a second handler type requires zero relay-loop edits. `make lint && make typecheck && pytest -m integration tests/test_outbox_idempotency.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 110 — outbox-idempotency`, paste the gate output, and wait for review.
