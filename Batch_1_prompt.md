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

**Skills:** `event-sourcing-architect`, `postgresql`, `python-pro`
**Depends on:** none
**Files:** `nce/replay.py` (`_handle_store_memory`, ~`:498-560`); reference `nce/schema.sql` (`memories` `:55-89`, `memory_salience` `:376-385`), `nce/event_types.py` (store_memory params).
**Goal:** Make the handler insert a valid `memories` row.
**Steps:**
1. Remove `summary` and `salience` from the SELECT (`:509-518`) and INSERT (`:529-555`) column lists.
2. Add `payload_ref` to the INSERT, sourced from the event's `params.payload_ref` (24-hex ObjectId). It is `NOT NULL` + CHECK `^[a-f0-9]{24}$`.
3. If a salience value must be carried, write it to `memory_salience(memory_id, agent_id, namespace_id, salience_score)` via a separate INSERT/UPSERT — not onto `memories`.
4. Keep using `uuid.uuid4()` for now (determinism is Phase H — do NOT change ID generation here).
**Acceptance:** `make lint && make typecheck` clean; the handler compiles and a focused unit test constructing a fake store_memory event no longer raises `UndefinedColumnError`/NotNull. (Full integration assertion is Batch 4.)

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch NN — <name>`, paste the gate output, and wait for review.
