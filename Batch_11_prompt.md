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

**Skills:** `event-store-design`, `observability-engineer`, `async-python-patterns`
**Depends on:** Batch 10
**Files:** `nce/cron.py` (new `_chain_verification_tick`, mirror `_saga_recovery_tick:150`); `nce/db_utils.py` (`UNMANAGED_PG_AUDITED_SITES`); reference `nce/event_log.py` (`verify_merkle_chain:~1168`), `nce/observability.py` (`MERKLE_CHAIN_VALID`).
**Goal:** Run chain verification on a schedule + at startup, set the gauge, alert on failure.
**Steps:**
1. Add site string `cron.chain_verify.namespace_scan` to `UNMANAGED_PG_AUDITED_SITES`.
2. Write `_chain_verification_tick(pool)`: acquire `acquire_cron_lock("chain_verification", …)`; scan namespaces; per namespace call `verify_merkle_chain`; `MERKLE_CHAIN_VALID.set(1/0)`; on invalid → `log.critical`, dispatch an alert (Phase D dispatcher), and `append_event(event_type="chain_verification_failed", …)` (INSERT — allowed).
3. Register the job (IntervalTrigger from Batch 10 config) and add to `startup_coros`.
**Acceptance:** integration test tampers a row via a dev `NCE_BYPASS_WORM` conn, runs the tick, asserts gauge=0 + a `chain_verification_failed` event exists; clean run leaves gauge=1.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch NN — <name>`, paste the gate output, and wait for review.
