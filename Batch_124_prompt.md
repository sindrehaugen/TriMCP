1. **One batch = one branch = one commit.** Branch name `batch-124-external-tamper-anchor`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse `verify_merkle_chain`, the chain-head query, the existing MinIO client, and the `CronLock` pattern. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing event_log/cron tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** anchor blobs are written to an object-locked (WORM) MinIO bucket; per-namespace scoped reads; no `event_log` mutation.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `security-auditor` (primary), `python-pro`
**Depends on:** none (Batch 125 retention builds on the anchor)
**Files:** `nce/cron.py` (anchor tick); `nce/event_log.py` (`verify_merkle_chain` gains `--against-anchor`/param); `nce/admin_handlers/fleet.py` (anchor status); `nce/config.py`; `tests/test_tamper_anchor.py` (new)
**Goal:** WORM is a DB trigger a superuser can disable; the Merkle chain makes tampering detectable but only against the DB itself. Anchor chain heads to an external object-locked store so trigger-disable + history rewrite becomes detectable against an independent root of trust.
**Steps:**
1. `cron.py`: hourly tick (own `CronLock`) writes per-namespace `(namespace_id, max_seq, chain_hash)` to an object-locked MinIO bucket (`cfg.NCE_ANCHOR_BUCKET`). Object lock = WORM at the storage layer.
2. `event_log.py`: `verify_merkle_chain` gains an against-anchor mode comparing the recomputed head to the anchored head; mismatch ⇒ critical + alert.
3. `fleet.py`: anchor-status endpoint (last anchored seq/hash per namespace). Config: `NCE_ANCHOR_BUCKET`, `NCE_ANCHOR_INTERVAL_MINUTES` (default 60). Optional RFC3161 timestamp left as a documented follow-up.
**Acceptance:** `tests/test_tamper_anchor.py` (`@pytest.mark.integration`): anchor tick writes a head; against-anchor verify passes on a pristine chain; simulate history rewrite (trigger-disable + edit via bypass conn) ⇒ against-anchor verify detects the divergence even though the in-DB chain was re-stitched. `make lint && make typecheck && pytest -m integration tests/test_tamper_anchor.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 124 — external-tamper-anchor`, paste the gate output, and wait for review.
