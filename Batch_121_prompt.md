1. **One batch = one branch = one commit.** Branch name `batch-121-dlq-auto-triage`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing DLQ storage, the poison-pill attempt counters, the `NotificationDispatcher`, and the admin fleet-handler pattern. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing DLQ/tasks tests still pass
6. **Migrations:** none (reuse existing `dead_letter_queue` columns; fingerprint stored in existing JSONB/metadata or a nullable column only if one already exists — if not, store in metadata, do NOT add a migration).
7. **WORM/RLS invariants (never violate):** tenant-scoped; circuit-open flag is Redis-only; no `event_log` mutation.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `incident-responder` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/dead_letter_queue.py`; `nce/tasks.py` (enqueue guard); `nce/notifications.py`; `nce/admin_handlers/fleet.py` (circuit-close endpoint); `nce/config.py`; `tests/test_dlq_triage.py` (new)
**Goal:** DLQ faults are stored and alerted but never consumed — replay is fully manual, and a deterministically-failing task type retries forever. Add error-fingerprint triage: auto-replay transients, circuit-break repeat deterministic failures.
**Steps:**
1. Fingerprint: `sha256(task_name + exception_class + normalized_top_frame)`. Classify transient (timeouts, connection resets, 429/5xx) vs deterministic.
2. Transient ⇒ auto-replay with exponential backoff (max `cfg.NCE_DLQ_AUTO_REPLAY_MAX`, default 3), then alert and leave for manual handling.
3. Deterministic ⇒ after `k=cfg.NCE_DLQ_CIRCUIT_THRESHOLD` (default 3) same-fingerprint entries, set `nce:dlq:quarantine:{task_name}` in Redis (TTL `cfg.NCE_DLQ_CIRCUIT_TTL_S`, default 3600). `tasks.py` enqueue rejects that task type fast while the flag is set, with an alert.
4. `fleet.py`: admin endpoint to close the circuit (delete the flag). Config knobs registered.
**Acceptance:** `tests/test_dlq_triage.py` (`@pytest.mark.integration`): a transient failure auto-replays up to the cap then alerts; 3 same-fingerprint deterministic failures open the circuit; subsequent enqueue of that task type is rejected; admin close re-enables it. `make lint && make typecheck && pytest -m integration tests/test_dlq_triage.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 121 — dlq-auto-triage`, paste the gate output, and wait for review.
