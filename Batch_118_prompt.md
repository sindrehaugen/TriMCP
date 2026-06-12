1. **One batch = one branch = one commit.** Branch name `batch-118-secrets-file-convention`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing config env-loader helpers and `require_master_key()`; add a single `*_FILE` resolution helper rather than scattering file reads. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing config/signing tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** never log secret values or file contents; `_FILE` contents are read once at boot and not echoed.
8. **Secrets:** the whole point — support file-based secrets; env still works as fallback.
9. **Tests** are unit-level.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `security-auditor` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/config.py` (`*_FILE` loader); `nce/signing.py` (`require_master_key` honors `NCE_MASTER_KEY_FILE`); `docker-compose.yml` (Docker secrets); `docs/` (note `/proc/<pid>/environ` exposure closed); `tests/test_secrets_file.py` (new)
**Goal:** Master key and other secrets live in env vars, readable via `/proc/<pid>/environ`. Support a `*_FILE` convention (Docker/K8s secrets) so secrets need not be in the environment.
**Steps:**
1. `config.py`: add a helper — for any secret `NCE_X`, if `NCE_X_FILE` is set, read the secret from that file path (strip trailing newline); else fall back to `NCE_X`. Apply to `NCE_MASTER_KEY`, `NCE_API_KEY`, `NCE_ADMIN_API_KEY`, and DB/Redis passwords where they flow through config.
2. `signing.py`: `require_master_key()` resolves via the new helper.
3. `docker-compose.yml`: switch the master key (and at least one other secret) to a Docker secret mounted at a file path, setting `*_FILE`.
4. `docs/`: short note that file-based secrets close the env-exposure vector.
**Acceptance:** `tests/test_secrets_file.py`: `NCE_MASTER_KEY_FILE` pointing at a temp file is honored; env fallback still works when `_FILE` unset; `_FILE` takes precedence over env when both set; secret value never appears in logs. `make lint && make typecheck && pytest tests/test_secrets_file.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 118 — secrets-file-convention`, paste the gate output, and wait for review.
