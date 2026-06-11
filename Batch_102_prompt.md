1. **One batch = one branch = one commit.** Branch name `batch-102-health-probe-signature-verify`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities (`verify_event_signature`, `verify_merkle_chain`, the existing health gauges, `scoped_pg_session`/`unmanaged_pg_connection`). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes (`tests/test_health_probes.py`)
   - existing health-probe tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside `scoped_pg_session`; `append_event` in the same txn as its write; never `UPDATE`/`DELETE` `event_log`; no raw content/PII in `event_log.params`. This batch is READ-ONLY against `event_log`.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only.
9. **DB-dependent tests** are `@pytest.mark.integration`; the structural assertions can be pure-unit with mocked verifiers.
10. **Report format per batch:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `security-auditor` (primary), `python-pro`, `observability-engineer`
**Depends on:** none
**Files:** `nce/orchestrator.py` (`check_health` Merkle-sampling block ~`:789-830`); `nce/observability.py` (add a gauge mirroring `MERKLE_CHAIN_VALID`); `tests/test_health_probes.py`
**Goal:** Close the audit Domain-2 gap: the hourly health probe verifies the Merkle **chain** (`verify_merkle_chain`) but never verifies event **signatures** (`verify_event_signature`). An attacker who rewrites the `signature` column directly passes the chain check. Add a bounded signature-sampling pass to the same probe.
**Steps:**
1. Confirm `check_health` samples ~5 active namespaces and calls `verify_merkle_chain(...)`, setting the `MERKLE_CHAIN_VALID` gauge. Confirm `nce/event_log.py` exposes `verify_event_signature(...)` (~`:1120`). If either differs, STOP.
2. In the same sampling loop, for each sampled namespace verify the signatures of a bounded sample of recent events (reuse the existing per-namespace bound — do NOT scan whole partitions). Aggregate into a new gauge `nce_event_signature_valid` (1 = all sampled valid, 0 = any invalid), and downgrade health to `degraded` on failure exactly as the Merkle path does.
3. On a signature failure, log critical and (matching the Merkle path) append the existing failure audit event if one is used there — reuse the same event type/dispatcher; do NOT invent a new event type without confirming `nce/event_types.py`.
4. Keep the probe bounded and cheap: same sample size, no extra full-table reads.
**Acceptance:** `tests/test_health_probes.py` gains a case where signatures are tampered (mock `verify_event_signature` → False or flip a stored signature on an integration namespace) and asserts health degrades + `nce_event_signature_valid == 0`, plus a positive pass. `make lint && make typecheck && pytest tests/test_health_probes.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch 102 — health-probe-signature-verify`, paste the gate output, and wait for review.
