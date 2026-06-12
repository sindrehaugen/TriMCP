1. **One batch = one branch = one commit.** Branch name `batch-129-d365-mutating-tools`. Never combine batches.
2. **Verify before you act.** This is the highest-blast-radius batch in the plan. Open each target file, confirm Batches 106/114/119/120/128 are merged, and confirm the approval queue + echo helper + causal DAG exist. If any rail is missing, **STOP and report** — do not ship a mutating tool without its safety stack.
3. **Modify only the files listed in the batch.** Two tools only (`d365_update_case`, `d365_create_escalation`). No NetBox writes. No new abstractions beyond the actions module.
4. **Minimal diff.** Reuse the `DataverseClient`, the approval queue (Batch 128), the echo helper (Batch 119), the causal-ancestry walk (Batch 120), the tool-registry `requires_approval` flag, and `append_event`. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes (including the loop test)
   - existing D365/tool-registry tests still pass (bump tool counts)
6. **Migrations:** NONE. The `action_idempotency` table (PK `(namespace_id, idempotency_key)`) and `action_approval_queue` were established by **Batch C0** (already in `main`). Use them directly. If absent, STOP — C0 was not merged.
7. **WORM/RLS invariants (never violate):** every executed action is a WORM event with request+response hashes and `origin_event_id`; the action only executes from an `approved` queue row; tenant-scoped; dry-run is the default.
8. **Secrets:** Azure creds + `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`; Dataverse mocked.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `security-auditor`, `api-design-principles`
**Depends on:** Batch 128 (approval queue), Batch 119 (echo suppression), Batch 120 (causal DAG), Batch 106 (origin) — all merged
**Files:** `nce/vertical_modules/dynamics365/actions.py` (new — execution only); `nce/tool_registry.py` (+ `requires_approval` flag enforcement); `nce/mcp_stdio_dispatch.py` (enforce `requires_approval`); `nce/mcp_stdio_tools.py` (2 tool defs); `nce/config.py`; `tests/test_d365_mutating_tools.py` (new); `tests/test_tool_registry.py` (counts)
**Goal:** Ship the first mutating vertical tools behind the full five-layer safety stack: dry-run default → approval queue → idempotency → loop breakers → provenance. NetBox (physical infra) is deliberately deferred.
**Steps:**
1. `actions.py`: `execute_d365_update_case` and `execute_d365_create_escalation` that run ONLY against an `approved` `action_approval_queue` row. Each carries a client idempotency key sent to D365 in a custom field; dedup so a re-run is a no-op.
2. Loop breakers, in order: per-entity mutation rate limit (Redis, `cfg.NCE_ACTION_RATE_PER_HOUR`, default 3); causal-ancestry check (Batch 120) — if the triggering context's event ancestry already contains a mutation on the same entity within the window, refuse with `loop_detected`; on execution, record an echo (Batch 119) so the resulting webhook is suppressed.
3. Provenance: executed action = WORM event with request/response hashes + `origin_event_id`; propagate `origin_event_id` into the echo set and any resulting kg_edge update (Batch 106 origin = `'agent'`).
4. Registry/dispatch: tools are `mutation=True`, `admin_only=False`, `requires_approval=True`; the dispatcher refuses to execute a `requires_approval` tool except via the approved-row path. Bump `tests/test_tool_registry.py` counts.
**Acceptance:** `tests/test_d365_mutating_tools.py` (`@pytest.mark.integration`, Dataverse mocked): propose → approve → execute → echo recorded → matching webhook suppressed (Batch 119) → deterministic state converges → full chain queryable via `get_event_provenance`; idempotency key replay is a no-op; an induced webhook→agent→mutation cycle trips the ancestry loop breaker within one iteration; rate limit blocks the 4th mutation/hour. `make lint && make typecheck && pytest -m integration tests/test_d365_mutating_tools.py tests/test_tool_registry.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 129 — d365-mutating-tools`, paste the gate output, and wait for review.
