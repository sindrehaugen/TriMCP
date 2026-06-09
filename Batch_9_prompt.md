1. **One batch = one branch = one commit.** Branch name `batch-NN-shortname`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities (`scoped_pg_session`, `unmanaged_pg_connection`, `append_event`, `NotificationDispatcher`, `acquire_cron_lock`, `encrypt_signing_key`/`decrypt_signing_key`, `require_master_key`). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes
   - existing tests you touched still pass
   - if you changed MCP tool counts, update `tests/test_tool_registry.py` exact-count assertions in the SAME batch
6. **Migrations:** new SQL migrations go in `nce/migrations/` with the next free number (current max = `012`). Mirror any schema change into `nce/schema.sql`. Never edit an existing migration.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside `scoped_pg_session`; `append_event` runs inside the same transaction as its data write; never `UPDATE`/`DELETE` `event_log`; never put raw content/PII into `event_log.params`.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only — never read it from, or write it to, a database/settings table/endpoint.
9. **If a test needs live databases**, it is `@pytest.mark.integration`; run it with `pytest -m integration` against `make local-up`. Pure-unit batches must not require Docker.
10. **Report format per batch:** what changed (files), the gate output (lint/typecheck/test green), and anything you had to STOP on.

**Skill legend:** skills are from the Antigravity skills catalogue; load the listed skills for the batch before coding. Pick the first as primary.

**Skills:** `async-python-patterns`, `python-pro`
**Depends on:** none
**Files:** `nce/cron.py` (`async_main`, job registrations ~`:521-606`; `startup_coros` ~`:628-639`); reference `nce/temporal_decay.py` (`register_decay_jobs:370`, `_decay_prune_tick:265`)
**Goal:** Actually schedule `phase_2_2_decay_prune`.
**Steps:**
1. `from nce.temporal_decay import register_decay_jobs` and call `register_decay_jobs(scheduler, pool)` before `scheduler.start()`.
2. Add `_decay_prune_tick(pool)` to `startup_coros`.
**Acceptance:** new integration/boot test asserts a job with id `phase_2_2_decay_prune` is present in the scheduler; lint + typecheck clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch NN — <name>`, paste the gate output, and wait for review.
