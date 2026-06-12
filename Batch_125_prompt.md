1. **One batch = one branch = one commit.** Branch name `batch-125-event-retention`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the monthly partition scheme, the GC chunked-delete CTE, the `CronLock`, and the Batch 106 `change_origin` column. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing gc/cron/event_log tests still pass
6. **Migrations:** none (operates on existing partitions/tables).
7. **WORM/RLS invariants (never violate):** an event_log partition may only be archived+dropped AFTER it is anchored (Batch 124); never delete individual `event_log` rows — drop whole aged partitions only; tenant-scoped purges for contradictions/edges.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `database-optimizer` (primary), `python-pro`
**Depends on:** Batch 124 (anchor must exist before a partition is droppable), Batch 106 (origin tags for edge purge)
**Files:** `nce/garbage_collector.py` (or `nce/database/pruning.py` — use whichever owns retention); `nce/cron.py`; `nce/config.py`; `tests/test_event_retention.py` (new)
**Goal:** Event log, contradictions, and low-confidence edges grow unbounded — no retention anywhere. Add bounded retention that respects WORM (drop only anchored, aged partitions) and origin tags.
**Steps:**
1. Partition retention: a tick that archives event_log partitions older than `cfg.NCE_EVENT_RETENTION_MONTHS` (default keep generous, e.g. 24) to MinIO, then drops the partition — ONLY if that partition's range is fully anchored (Batch 124). Never row-level delete.
2. Resolved-contradiction purge: delete `contradictions` rows with non-null resolution older than `cfg.NCE_CONTRADICTION_RETENTION_DAYS` (default 180), tenant-scoped.
3. Low-confidence-edge prune: GC reaps kg_edges with `confidence < 0.15` AND age > `cfg.NCE_EDGE_PRUNE_AGE_DAYS` (default 90), but NEVER edges whose `change_origin='sync'` (deterministic ground truth) — use the Batch 106 column.
4. Register config knobs.
**Acceptance:** `tests/test_event_retention.py` (`@pytest.mark.integration`): an aged+anchored partition is archived then dropped; an aged-but-unanchored partition is kept; a resolved contradiction past TTL is purged; a low-confidence non-sync edge is reaped while a low-confidence `sync` edge survives. `make lint && make typecheck && pytest -m integration tests/test_event_retention.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 125 — event-retention`, paste the gate output, and wait for review.
