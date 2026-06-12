1. **One batch = one branch = one commit.** Branch name `batch-111-contradiction-cascade-residual`. Never combine batches.
2. **Verify before you act.** Batch 23 already cascades contradiction resolution through derived/consolidated dependents (recursive soft-delete + `atms_cascade` event). **First read Batch 23's actual implementation** in `nce/atms.py`/`contradiction_mcp_handlers.py` and the Batch 23 TAG report. This batch is ONLY the residual it did not do. If Batch 23 already floors edge confidence and re-queues superseded consolidations, STOP and report — scope may be empty.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing cascade traversal, the SAVEPOINT isolation around it, `append_event`, and the change-origin/`origin_event_id` columns from Batch 106. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing ATMS/contradiction tests still pass
6. **Migrations:** none (relies on Batch 106 columns).
7. **WORM/RLS invariants (never violate):** cascade runs in the existing nested SAVEPOINT so ATMS/topology failure cannot abort the resolution record; soft-delete only (`valid_to=now()`), never hard delete; never mutate `event_log`; tenant-scoped.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `database-architect`
**Depends on:** Batch 106 (`origin_event_id` on kg_edges), Batch 107 (derivation graph). Cascade base is Batch 23 (done).
**Files:** `nce/atms.py` (cascade fn); `nce/contradictions.py`; `nce/contradiction_mcp_handlers.py` (`handle_resolve_contradiction`); `nce/consolidation.py` (re-queue hook); `tests/test_cascade_residual.py` (new)
**Goal:** Close the two gaps Batch 23 left: (a) KG edges whose `origin_event_id` traces to a retracted (loser) memory are not touched — floor their confidence to 0.1 (auditable decay, NOT deletion); (b) `superseded`/`merged` resolutions should re-open the affected consolidations for re-derivation rather than leaving stale abstractions.
**Steps:**
1. In the cascade path: after soft-deleting loser memories + dependents, find kg_edges with `origin_event_id` in the retracted set (Batch 106 column) and set `confidence = LEAST(confidence, 0.1)`; append an `edge_confidence_floored` event (or extend the existing `atms_cascade` event payload) — do not delete the edges.
2. For `superseded`/`merged` resolutions: delete the affected consolidated memory row, restore its source memories' salience (reuse the consolidation salience-restore logic if present; if not, STOP and report rather than inventing), and mark those sources eligible for the next consolidation run.
3. Keep `accepted_a`/`accepted_b`/`rejected` behavior from Batch 23 unchanged except for the new edge-flooring step.
**Acceptance:** `tests/test_cascade_residual.py` (`@pytest.mark.integration`): A contradicts B, both feed consolidation C; resolve `accepted_a` ⇒ B + C soft-deleted (Batch 23) AND B's origin-tagged edges floored to ≤0.1 with an event; resolve `superseded` ⇒ C deleted, sources' salience restored and re-queued. `make lint && make typecheck && pytest -m integration tests/test_cascade_residual.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 111 — contradiction-cascade-residual`, paste the gate output, and wait for review.
