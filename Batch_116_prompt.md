1. **One batch = one branch = one commit.** Branch name `batch-116-hmac-nonce-mandatory`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing optional Redis nonce store (`nce:nonce:*`), `secrets.compare_digest`, the `_TIMESTAMP_DRIFT_SECONDS` constant, and the `IS_PROD`/fail-closed pattern used by the webhook dedup. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing auth tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** auth changes must not weaken existing scope/RLS checks; in prod, Redis-down on a nonce-required path is fail-closed (reject), matching webhook dedup posture.
8. **Secrets:** `NCE_API_KEY`/`NCE_MASTER_KEY` env-only.
9. **Tests** are unit-level with a fake/real Redis.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `security-auditor` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/auth.py` (HMAC verify path, nonce handling, drift window); `nce/config.py`; `tests/test_hmac_nonce.py` (new or extend `tests/test_auth*.py`)
**Goal:** The HMAC scheme has a ~10-minute replay window and the nonce is optional. Make the nonce mandatory whenever Redis is reachable and shrink the window, closing the replay gap without breaking clock-skew tolerance.
**Steps:**
1. Config: shrink default `NCE_CLOCK_SKEW_TOLERANCE_S` from 300 to 90 (verify current default; if already <300, adjust note). Add `NCE_HMAC_NONCE_REQUIRED` (bool, default true).
2. `auth.py`: when Redis is reachable and `NCE_HMAC_NONCE_REQUIRED`, require a per-request nonce; reject reused nonces (SET NX with TTL = 2× drift). In prod, if Redis is unreachable on a nonce-required path ⇒ reject (fail-closed); in dev, log and allow.
3. Keep constant-time comparison and the canonical message format unchanged.
**Acceptance:** `tests/test_hmac_nonce.py`: replayed request with a reused nonce ⇒ rejected; request outside the ±90s window ⇒ rejected; missing nonce with Redis up + required ⇒ rejected; prod + Redis down ⇒ rejected, dev + Redis down ⇒ allowed with log. `make lint && make typecheck && pytest tests/test_hmac_nonce.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 116 — hmac-nonce-mandatory`, paste the gate output, and wait for review.
