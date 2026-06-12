1. **One batch = one branch = one commit.** Branch name `batch-115-mtls-prod-default`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse `assert_bridge_mtls_configured()`/`MTLSNotConfiguredError`, the `IS_PROD` flag, the existing boot-assertion pattern in the app lifespans, and `append_event` for the CRITICAL audit. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing mtls/admin/a2a-server tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** the acknowledged-disabled path emits a CRITICAL log + WORM event; no `event_log` mutation.
8. **Secrets:** cert paths + `NCE_MASTER_KEY` env-only.
9. **DB-dependent tests** may be unit-level (boot-guard logic).
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `security-auditor` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/mtls.py`; `nce/config.py`; `nce/admin_app.py` (lifespan boot guard); `nce/a2a_server.py` (lifespan boot guard); `docker-compose.yml`; `deploy/` (Caddy mTLS example); `tests/test_mtls_prod_default.py` (new)
**Goal:** mTLS middleware exists but defaults off and the default compose ships HTTP. In production this makes "zero-trust transport" aspirational. Make a prod deployment refuse to boot with mTLS disabled unless explicitly acknowledged.
**Steps:**
1. Config: add `NCE_MTLS_ACKNOWLEDGE_DISABLED` (bool, default false).
2. In the admin + a2a server lifespans: if `IS_PROD` and mTLS is not configured/enabled and `NCE_MTLS_ACKNOWLEDGE_DISABLED` is false ⇒ raise at boot (reuse `MTLSNotConfiguredError`). If acknowledged ⇒ log CRITICAL and append a WORM event (e.g. `mtls_disabled_acknowledged`) then continue.
3. `docker-compose.yml` + `deploy/`: add cert mount points and a commented Caddy mTLS termination example; do not enable by default in dev.
4. Do not change the middleware's request-path behavior — boot-time guard only.
**Acceptance:** `tests/test_mtls_prod_default.py`: `IS_PROD=true` + mTLS unconfigured + unacknowledged ⇒ boot raises; acknowledged ⇒ boots with CRITICAL log + audit event; non-prod ⇒ boots silently. `make lint && make typecheck && pytest tests/test_mtls_prod_default.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 115 — mtls-prod-default`, paste the gate output, and wait for review.
