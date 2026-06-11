1. **One batch = one branch = one commit.** Branch name `batch-105-gc-cascade-age-grace`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities (`cfg.GC_ORPHAN_AGE_SECONDS`, the existing chunked-delete CTE, `scoped_pg_session`/namespace context). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes (`tests/test_garbage_collector.py`)
   - existing GC tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside the existing namespace-scoped context; every DELETE keeps its explicit `AND namespace_id = $1::uuid` filter; never `UPDATE`/`DELETE` `event_log` rows themselves (the existing event_log orphan handling is unchanged).
8. **Secrets:** `NCE_MASTER_KEY` is environment-only.
9. **DB-dependent tests** are `@pytest.mark.integration` (this batch's assertions need live Postgres for the cascade).
10. **Report format per batch:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `database-optimizer` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/garbage_collector.py` (Postgres cascade cleanup CTE ~`:225-336`); `tests/test_garbage_collector.py`
**Goal:** Add an age grace period to the Postgres cascade cleanup (audit Domain 2). Mongo/MinIO orphan sweeps filter by `GC_ORPHAN_AGE_SECONDS`, but the PG cascade (`memory_salience`, `contradictions`, event_log refs) deletes orphans the instant a `memory_id` disappears — so an operator-deleted memory can trigger immediate reaping of still-fresh dependents that a concurrent/late writer may still be referencing. Make the cascade respect the same grace window.
**Steps:**
1. Confirm the cascade uses a multi-table CTE that deletes `memory_salience`/`contradictions` rows whose `memory_id` no longer exists in `memories`, with NO temporal filter, and that Mongo/MinIO paths DO use a `cutoff = now() - GC_ORPHAN_AGE_SECONDS`. If different, STOP.
2. Add the same `GC_ORPHAN_AGE_SECONDS` cutoff to the cascade predicates: only reap an orphan whose own timestamp is older than the cutoff (`memory_salience.updated_at < cutoff`, `contradictions.created_at < cutoff`). Verify those columns exist in `nce/schema.sql` before referencing them; if a table lacks a usable timestamp, STOP and report rather than guessing.
3. Keep batch size, chunking, the `asyncio.sleep` yields, and the per-namespace RLS scoping exactly as they are — this is a predicate-only change, not a restructuring.
**Acceptance:** `tests/test_garbage_collector.py` (`@pytest.mark.integration`): seed an orphaned `memory_salience`/`contradictions` row with a FRESH timestamp → assert it SURVIVES a GC pass; backdate it beyond `GC_ORPHAN_AGE_SECONDS` → assert it is reaped. `make lint && make typecheck && pytest -m integration tests/test_garbage_collector.py` clean (against `make local-up`).

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch 105 — gc-cascade-age-grace`, paste the gate output, and wait for review.
