1. **One batch = one branch = one commit.** Branch name `batch-114-d365-incremental-sync`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing `DataverseClient.paginate()`, the `d365_integrations.last_sync_stats` JSONB column, the `CronLock` pattern, and the idempotent kg upsert. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing D365 sync tests still pass
6. **Migrations:** none (cursor lives in existing `last_sync_stats` JSONB).
7. **WORM/RLS invariants (never violate):** per-namespace scoped context; idempotent upserts unchanged; no `event_log` mutation.
8. **Secrets:** Azure creds + `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`; Dataverse is mocked.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `api-design-principles`
**Depends on:** none (prerequisite for Batch 119 echo suppression)
**Files:** `nce/vertical_modules/dynamics365/sync.py`; `nce/vertical_modules/dynamics365/client.py`; `nce/cron.py` (sync tick + new weekly tick); `tests/test_d365_incremental.py` (new)
**Goal:** Every D365 cron tick is currently a full entity refresh (full Dataverse scans). Add `modifiedon` watermark cursors for incremental sync, with a weekly full-refresh pass to reconcile deletes. This is also the prerequisite for distinguishing an agent's own write from a concurrent operator write (Batch 119).
**Steps:**
1. `sync.py`/`client.py`: store a per-entity-set `modifiedon` watermark in `d365_integrations.last_sync_stats` (JSONB cursor map). On each incremental tick, add OData filter `modifiedon gt <cursor>` with a −5min overlap window for clock skew; advance the cursor to the max `modifiedon` seen.
2. `cron.py`: keep the existing tick as the incremental path; add a separate weekly full-refresh tick (own `CronLock`) that fetches all entities and reconciles deletions (entities present in graph but absent from a full pull get soft-handled per existing convention — if no delete path exists, STOP and report rather than inventing destructive logic).
3. Preserve idempotent 4-tuple upserts and confidence semantics exactly.
**Acceptance:** `tests/test_d365_incremental.py` (`@pytest.mark.integration`, Dataverse mocked): first tick seeds cursor; second tick issues `modifiedon gt` and fetches only the delta; weekly tick performs a full pull and reconciles a removed entity. `make lint && make typecheck && pytest -m integration tests/test_d365_incremental.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 114 — d365-incremental-sync`, paste the gate output, and wait for review.
