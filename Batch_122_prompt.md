1. **One batch = one branch = one commit.** Branch name `batch-122-citus-deploy-or-descope`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. This batch has TWO acceptable outcomes (deploy-green OR formally descope) — pick based on test results, do not force a green.
3. **Modify only the files listed in the batch.** No new modules/deps in `nce/` runtime code — this is CI + compose + tests + docs.
4. **Minimal diff.** Reuse migration `010_citus_sharding.sql` as-is and the existing integration-test harness. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the new test matrix runs (green ⇒ keep path; red-after-fix-attempt ⇒ descope path)
   - existing tests still pass
6. **Migrations:** none new (validates existing 010).
7. **WORM/RLS invariants (never violate):** the test matrix MUST assert RLS holds on distributed tables (GUC propagation via `citus.propagate_set_commands='local'`); a failure here is a fail-closed (query errors), never a silent cross-tenant leak.
8. **Secrets:** env-only.
9. **DB-dependent tests** require the Citus profile container.
10. **Report format:** files changed, which outcome (keep/descope), gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `database-architect` (primary), `cloud-architect`
**Depends on:** none
**Files:** `.github/workflows/` (new Citus CI job); `docker-compose.yml` (Citus profile using `citusdata/citus:12-pg16`); `tests/integration/test_citus_rls.py` (new); `docs/` (deployment note OR descope note); possibly move `nce/migrations/010_citus_sharding.sql` → `nce/migrations/optional/` on the descope outcome
**Goal:** Citus is declared (migration 010) but the deployed image is stock pgvector — every distributed-systems claim is untested. Resolve to a known state: deploy-and-test, or formally descope. The losing position is the current untested-claim limbo.
**Steps:**
1. Add a compose `citus` profile using a Citus image that includes pgvector; add a CI job that brings it up and runs the matrix.
2. `test_citus_rls.py`: assert (a) RLS holds on a distributed table with GUC propagation set, (b) cross-shard 2PC works for a saga write, (c) `event_seq` coordinator-local allocation is correct under distribution, (d) `semantic_search` prunes shards.
3. **Green ⇒** keep migration 010, document the deployment + required `citus.propagate_set_commands='local'`. **Red and not fixable within scope ⇒** move 010 to `migrations/optional/`, strike the Citus claim from README/docs, and document why. Either outcome is a PASS for this batch — report which you took.
**Acceptance:** the matrix runs in CI; the chosen outcome is documented; if descoped, README no longer claims live Citus sharding. `make lint && make typecheck` clean; matrix executed.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 122 — citus-deploy-or-descope`, paste the gate output + chosen outcome, and wait for review.
