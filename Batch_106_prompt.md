1. **One batch = one branch = one commit.** Branch name `batch-106-change-origin-tags`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities (the kg upsert helpers in `dynamics365/sync.py`, `append_event`, `scoped_pg_session`/namespace context, the caller `NamespaceContext`). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes
   - existing D365/consolidation/replay/memory tests still pass
6. **Migrations:** NONE. `change_origin` + `origin_event_id` on `memories`/`kg_nodes`/`kg_edges` were established by **Batch C0** (already in `main`). Verify they exist; do NOT add a migration or edit `schema.sql`. If absent, STOP — C0 was not merged.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside the existing namespace-scoped context; every write keeps its `namespace_id` filter; never `UPDATE`/`DELETE` `event_log` rows. The new `origin_event_id` references an event id but adds NO FK to `event_log` (partitioned/WORM) — store the UUID only.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `database-architect` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/vertical_modules/dynamics365/sync.py` (kg upserts); `nce/vertical_modules/dynamics365/ingestion.py`; `nce/tasks.py` (`process_d365_event` path); `nce/consolidation.py` (kg insert ~`:321-333`); `nce/replay.py` (fork apply path); `nce/orchestrators/memory.py` (saga kg writes); `tests/test_change_origin.py` (new)
**Goal:** Make change-origin first-class so echo suppression (Batch 119) and loop detection (Batch 129) become possible. This is retrofit-impossible after a mutating tool ships — do it now. Add `change_origin TEXT NOT NULL DEFAULT 'unknown'` with `CHECK (change_origin IN ('sync','webhook','agent','operator','consolidation','replay','unknown'))` and nullable `origin_event_id UUID` to `kg_edges`, `kg_nodes`, and `memories`. Tag every write site with its true origin.
**Steps:**
1. Verify the C0 columns (`change_origin`, `origin_event_id`) exist on all three tables. Backfill of existing rows to `'unknown'` was C0's default — confirm. (No DDL here.)
2. Tag write sites: `dynamics365/sync.py` upserts → `'sync'`; `ingestion.py` / `tasks.process_d365_event` → `'webhook'`; `consolidation.py` derived edges → `'consolidation'`; `replay.py` fork application → `'replay'`; `orchestrators/memory.py` saga → `'agent'` or `'operator'` derived from the caller context (agent_id present ⇒ agent; admin/operator path ⇒ operator).
3. Upsert precedence: in the `ON CONFLICT … DO UPDATE` clauses for `kg_edges`/`kg_nodes`, only overwrite `change_origin` when the incoming origin is higher-authority (`sync` > `webhook` > `consolidation` > `unknown`); never let a webhook downgrade a sync-authored edge. Encode as a CASE in the DO UPDATE.
4. Set `origin_event_id` to the saga/append_event id where one exists at the write site; leave NULL where there is none.
**Acceptance:** `tests/test_change_origin.py` (`@pytest.mark.integration`): assert each ingestion path stamps the expected `change_origin`; assert a webhook upsert does NOT overwrite a pre-existing `'sync'` edge's origin; assert `origin_event_id` is populated on saga-authored memories. `make lint && make typecheck && pytest -m integration tests/test_change_origin.py` clean (against `make local-up`).

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 106 — change-origin-tags`, paste the gate output, and wait for review.
