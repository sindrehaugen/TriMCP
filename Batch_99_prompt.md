1. **One batch = one branch = one commit.** Branch name `batch-99-chrono-nesting-guard`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities. Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes
   - existing tests you touched still pass
   - if you changed MCP tool counts, update `tests/test_tool_registry.py` exact-count assertions in the SAME batch
6. **Migrations:** new SQL migrations go in `nce/migrations/` with the next free number (current max = `018`). Mirror any schema change into `nce/schema.sql`. Never edit an existing migration.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside `scoped_pg_session`; `append_event` runs inside the same transaction as its data write; never `UPDATE`/`DELETE` `event_log`; never put raw content/PII into `event_log.params`.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only — never read it from, or write it to, a database/settings table/endpoint.
9. **If a test needs live databases**, it is `@pytest.mark.integration`; run it with `pytest -m integration` against `make local-up`. Pure-unit batches must not require Docker.
10. **Report format per batch:** what changed (files), the gate output (lint/typecheck/test green), and anything you had to STOP on.

**Skill legend:** skills are from the Antigravity skills catalogue; load the listed skills for the batch before coding. Pick the first as primary.

**Skills:** `python-pro` (primary), `clean-code`
**Depends on:** none
**Files:** `nce/causal/chrono.py` (`branch_timeline` ~`:28`, `chrono_branch_var` ~`:24`); `tests/unit/test_chrono.py` (`TestChronoContextManager` ~`:50`)
**Goal:** Reject nested `branch_timeline` counterfactual scopes (audit Domain 4). A second `branch_timeline` opened inside an active one silently shadows the outer branch via `ContextVar.set`, then `reset`s back to the *inner* branch on exit — corrupting the outer counterfactual scope. Fail loudly instead.
**Steps:**
1. Confirm `branch_timeline` is a `@contextmanager` that does `token = chrono_branch_var.set({...})` / `chrono_branch_var.reset(token)`, and that `get_active_branch()` returns `chrono_branch_var.get()`. If not, STOP.
2. At the top of `branch_timeline` (before `parse_as_of`), raise `RuntimeError` if `chrono_branch_var.get() is not None`, with a message that names the constraint ("already active … nested … not supported"). Document the rejection in the docstring.
3. Confirm no production caller legitimately nests (grep `branch_timeline` across `nce/`): `nce/causal/correlation.py` only *reads* via `get_active_branch()`; there is no nested `with`. If a nested production usage exists, STOP and report.
**Acceptance:** in `tests/unit/test_chrono.py`, add `test_nested_branch_timeline_is_rejected` (asserts `pytest.raises(RuntimeError)` on the inner `with`, and that the outer branch survives intact) and `test_sequential_branches_after_exit_are_allowed` (proves the guard does NOT break branch→exit→branch). Pure-unit. `make lint && make typecheck && pytest tests/unit/test_chrono.py` clean.

> NOTE: This fix was pre-applied to the working tree during the architectural audit (gate already green: ruff check+format clean, 8/8 `test_chrono.py` pass). This batch exists to route that change through the normal TAG pipeline — verify the working-tree diff matches the Steps above, then run the Closing protocol on a clean branch.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch 99 — chrono-nesting-guard`, paste the gate output, and wait for review.
