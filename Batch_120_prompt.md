1. **One batch = one branch = one commit.** Branch name `batch-120-causal-dag-multiparent`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps beyond the table + admin tool described.
4. **Minimal diff.** Reuse `append_event`'s existing transaction, the `parent_event_id` column (kept for the primary parent), and the admin fleet-handler pattern. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing event_log/replay/provenance tests still pass
6. **Migrations:** add `nce/migrations/026_event_parents.sql` (confirm 026 free) + mirror into `nce/schema.sql`.
7. **WORM/RLS invariants (never violate):** `event_parents` is append-only (no UPDATE/DELETE), RLS-enabled + forced; written in the SAME saga transaction as `append_event`; `parent_event_id` column retained for back-compat (signature unchanged where callers don't pass multiples).
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `event-store-design` (primary), `database-architect`
**Depends on:** none (prerequisite for Batch 129 loop breaker)
**Files:** `nce/migrations/026_event_parents.sql` (new); `nce/schema.sql`; `nce/event_log.py` (`append_event` accepts `parent_event_ids`); `nce/consolidation.py` (pass all source events); `nce/replay_mcp_handlers.py` (`get_event_provenance` reads DAG); `nce/admin_handlers/fleet.py` (`detect_causal_cycles`); `nce/tool_registry.py`; `tests/test_causal_dag.py` (new)
**Goal:** `parent_event_id` is single-parent metadata — consolidation (N→1) and merges can't express lineage and there's no loop detection. Add a multi-parent causal DAG without breaking the existing single-parent column or `append_event` signature.
**Steps:**
1. Migration 026 + schema.sql: `event_parents(event_id UUID, parent_event_id UUID, namespace_id UUID, PRIMARY KEY(event_id, parent_event_id))`; append-only (WORM trigger or REVOKE per existing event_log pattern), RLS enabled + forced.
2. `event_log.py`: `append_event(..., parent_event_ids: list[UUID] | None = None)`; when provided, write all rows to `event_parents` in the same transaction; keep populating the scalar `parent_event_id` with the primary parent (first id) for back-compat.
3. `consolidation.py`: pass all source-memory event ids as `parent_event_ids` on the consolidation event.
4. `get_event_provenance`: extend to walk `event_parents` (multi-parent ancestry). Add `detect_causal_cycles` admin tool in `fleet.py` (recursive CTE, depth-capped) + register in `tool_registry.py` (bump tool counts in `tests/test_tool_registry.py`).
**Acceptance:** `tests/test_causal_dag.py` (`@pytest.mark.integration`): a consolidation event records N parents in `event_parents`; `get_event_provenance` returns multi-parent ancestry; `detect_causal_cycles` flags a synthetic cycle and passes a clean DAG; existing single-parent events still resolve via the scalar column. `make lint && make typecheck && pytest -m integration tests/test_causal_dag.py tests/test_tool_registry.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 120 — causal-dag-multiparent`, paste the gate output, and wait for review.
