1. **One batch = one branch = one commit.** Branch name `batch-101-atms-iterative-traversal`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities. Match the surrounding code style. This is a behavior-PRESERVING refactor — same inputs must yield identical `set[str]` results.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes
   - existing ATMS/contradiction tests still pass (`tests/test_contradiction_detection.py`, `tests/test_cognitive_orchestrator_rls.py`)
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside `scoped_pg_session`; `append_event` in the same txn as its write; never `UPDATE`/`DELETE` `event_log`; no raw content/PII in `event_log.params`.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only.
9. **DB-dependent tests** are `@pytest.mark.integration`. The new test here is pure-unit (in-memory `ATMSEngine`).
10. **Report format per batch:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `clean-code`, `debugger`
**Depends on:** none
**Files:** `nce/atms.py` (`is_node_provably_valid` ~`:113`, `propagate_deprecation` ~`:199`, `evaluate_belief_states` ~`:235`); **new** `tests/test_atms_recursion.py`
**Goal:** Remove the unbounded Python call-stack recursion in ATMS belief evaluation (audit Domain 4, HIGH). `is_node_provably_valid` recurses over antecedents and `propagate_deprecation` recurses over dependents; a deep justification chain (≳1000 nodes) overflows the C stack and crashes the worker. Convert both to **explicit-stack iterative traversal**, preserving the exact cycle-guard and memoization semantics.
**Steps:**
1. Confirm: `is_node_provably_valid(node_id, active_path, memo)` returns `True` for PREMISE, `node.is_valid` for ASSUMPTION, `False` on cycle (`node_id in active_path`), else `True` iff some justification has all antecedents provable; memo is only consulted/written when `active_path` is empty. `propagate_deprecation` mutates `node.is_valid=False` (non-PREMISE), tracks `visited`, and recurses into DERIVED children that become unprovable. If any of this differs, STOP.
2. Rewrite `is_node_provably_valid` iteratively (explicit work stack / post-order evaluation) so the SAME truth value is returned for every node, including cyclic-justification → `False` and memo reuse for acyclic subgraphs. Do not change the public signature.
3. Rewrite `propagate_deprecation` iteratively (worklist of nodes to deprecate; keep the `visited` cycle guard; keep returning the set of nodes whose `is_valid` flipped from True→False). Preserve the O(dependents) child scan — do NOT change which nodes get invalidated.
4. Add a `sys.setrecursionlimit`-independent guarantee: no Python recursion remains in either function.
**Acceptance:** `tests/test_atms_recursion.py` (pure-unit): (a) a 5,000-node linear justification chain `A←B←…` invalidating the root cascades to all without `RecursionError`; (b) a cyclic justification set is reported invalid (no infinite loop); (c) a small fixed graph yields byte-identical cascade sets vs. the documented contract (regression). `make lint && make typecheck && pytest tests/test_atms_recursion.py tests/test_contradiction_detection.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch 101 — atms-iterative-traversal`, paste the gate output, and wait for review.
