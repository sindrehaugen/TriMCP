1. **One batch = one branch = one commit.** Branch name `batch-123-worker-confinement`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps in runtime code beyond the rlimit wrapper.
4. **Minimal diff.** Reuse the existing `subprocess_registry.py` launch path and the binary-hash verification already added in Batch 22. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing extractor/subprocess tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** workers that no longer hold admin/master env must still perform their signing/decrypt duties via a SCOPED key (do not break the saga signing path); if a worker genuinely needs the master key, give it via a file-based secret (Batch 118), not broad env.
8. **Secrets:** scope down worker env; no master/admin keys where unused.
9. **Tests** are unit/integration.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `devops-troubleshooter` (primary), `security-auditor`
**Depends on:** Batch 118 (file-based secrets) for any worker that needs scoped key material
**Files:** `docker-compose.yml` (worker services); `deploy/`; `nce/subprocess_registry.py` (rlimit wrapper); `nce/extractors/libreoffice.py`; `nce/extractors/project_ext.py`; `docs/`; `tests/test_subprocess_rlimit.py` (new)
**Goal:** RQ workers share the coordinator image with full env and no resource limits; extraction subprocesses are hash-verified but unbounded on CPU/memory. Confine them.
**Steps:**
1. `docker-compose.yml`: dedicated worker service env that strips `NCE_ADMIN_API_KEY` and `NCE_MASTER_KEY` where not required (use a file-based scoped secret if a worker needs signing); add `deploy.resources.limits` (cpu/mem) and `security_opt: ["no-new-privileges:true"]`. Document an optional seccomp profile.
2. `subprocess_registry.py`: add an rlimit wrapper (CPU seconds, address space) applied when launching LibreOffice/MPXJ; keep the existing binary-hash check and shell-arg guards.
3. Wire the wrapper into `libreoffice.py` and `project_ext.py` launch sites.
**Acceptance:** `tests/test_subprocess_rlimit.py`: a subprocess exceeding the CPU/addr-space limit is killed/contained, not allowed to run unbounded; binary-hash + arg guards still enforced. `make lint && make typecheck && pytest tests/test_subprocess_rlimit.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 123 — worker-confinement`, paste the gate output, and wait for review.
