1. **One batch = one branch = one commit.** Branch name `batch-103-docalculus-truncation-report`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities (`find_all_causal_paths`, `impacted_by`, `InterventionResult`). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes (`tests/test_correlation_propagation.py`)
   - existing causal tests still pass (`tests/unit/test_chrono.py`, `tests/unit/test_netbox_circuits.py`)
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** unchanged here (pure in-memory graph math).
8. **Secrets:** `NCE_MASTER_KEY` is environment-only.
9. **DB-dependent tests** are `@pytest.mark.integration`; this batch's test is pure-unit (`CausalGraph.from_rows`).
10. **Report format per batch:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `clean-code`
**Depends on:** none
**Files:** `nce/causal/correlation.py` (`DoCalculusEngine.evaluate` ~`:713`, the `paths = …find_all_causal_paths(…, max_depth=10)` / `if not paths: continue` block ~`:786-808`, `InterventionResult` dataclass ~`:203`); `tests/test_correlation_propagation.py`
**Goal:** Stop silent truncation in do-calculus (audit Domain 4). A node reachable per `impacted_by()` but whose every causal path exceeds `max_path_depth` is silently dropped from `probability_matrix`, making a real (but distant) impact look like zero. Report these instead of hiding them.
**Steps:**
1. Confirm `evaluate` computes `impacted_in_mutilated = mutilated.impacted_by(intervention_node_id)`, then per target calls `find_all_causal_paths(..., max_depth=max_path_depth)` and does `if not paths: continue`. Confirm `InterventionResult` is a dataclass. If either differs, STOP.
2. Add a field `truncated_targets: list[str]` (default `field(default_factory=list)`) to `InterventionResult`.
3. In the `if not paths:` branch, append the target to `truncated_targets` (sorted, deduped) instead of silently `continue`-ing past it. Do NOT fabricate a probability — these are "reachable but beyond max_path_depth", explicitly distinct from a computed 0.0.
4. Populate the new field in the `InterventionResult(...)` construction. Verify all consumers still type-check (`nce/vertical_modules/netbox/circuits.py`, any `evaluate_intervention` callers) — the field is additive with a default, so existing consumers are unaffected; if any consumer positionally constructs `InterventionResult`, fix it in-scope.
**Acceptance:** `tests/test_correlation_propagation.py` gains a case with a chain longer than `max_path_depth` proving the distant target lands in `truncated_targets` (and not as a `0.0` in `probability_matrix`), plus a within-depth regression proving normal targets are unaffected. `make lint && make typecheck && pytest tests/test_correlation_propagation.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch 103 — docalculus-truncation-report`, paste the gate output, and wait for review.
