1. **One batch = one branch = one commit.** Branch name `batch-117-redis-auth-scoped-locks`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing `REDIS_URL` plumbing, `redis_lock.py` SET-NX-EX + compare-and-delete Lua, and `cron_lock.py` key construction. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing lock/cron tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** lock-key changes must not break the compare-and-delete token safety; no `event_log` mutation.
8. **Secrets:** Redis password via `REDIS_URL`/env only; never hardcode.
9. **Tests** are unit/integration with Redis.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `devops-troubleshooter` (primary), `python-pro`
**Depends on:** none
**Files:** `docker-compose.yml` (Redis `requirepass` + `REDIS_URL` with auth); `nce/redis_lock.py`; `nce/cron_lock.py`; `nce/config.py` (doc the residual shared-instance risk); `tests/test_scoped_locks.py` (new or extend)
**Goal:** Redis is an unauthenticated shared store; cron-lock keys aren't tenant-scoped, so one tenant can disrupt another's locks. Add Redis AUTH and namespace-scope the locks where applicable.
**Steps:**
1. `docker-compose.yml`: set Redis `requirepass` (from env, not literal) and update `REDIS_URL` to include credentials; document enabling Redis TLS as a follow-up.
2. `cron_lock.py`/`redis_lock.py`: where a lock guards per-namespace work, include `namespace_id` in the key; keep global system locks global but name them explicitly. Preserve the token compare-and-delete release semantics.
3. Add a config doc comment noting the residual single-instance shared-store risk (per-tenant Redis is out of scope here).
**Acceptance:** `tests/test_scoped_locks.py`: two namespaces acquire same-named per-namespace lock concurrently without mutual exclusion collision; release still uses the token guard (no cross-holder delete). `make lint && make typecheck && pytest tests/test_scoped_locks.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 117 — redis-auth-scoped-locks`, paste the gate output, and wait for review.
