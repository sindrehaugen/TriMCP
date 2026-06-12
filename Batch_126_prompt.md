1. **One batch = one branch = one commit.** Branch name `batch-126-vector-tenancy-assert`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps beyond a small assertion helper.
4. **Minimal diff.** Add one `assert_namespace_filter()` helper and call it at the embedding-query sites; do not restructure the query builders. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing semantic-search/embedding tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** `memory_embeddings` queries must carry an explicit `namespace_id` predicate (defense-in-depth atop RLS); `kg_node_embeddings` is intentionally global — document, don't break it.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **Tests** are unit-level (static/guard assertions) + one integration check.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `vector-database-engineer` (primary), `security-auditor`
**Depends on:** none
**Files:** `nce/semantic_search.py`; `nce/db_utils.py` (`assert_namespace_filter` helper); `tests/test_vector_tenancy.py` (new)
**Goal:** `memory_embeddings` tenant isolation is query-layer discipline, not DB-enforced (the table's RLS posture differs from the transactional tables); a missing WHERE clause could leak cross-tenant vectors. Add a guard helper used at every embedding-query site, and document the intentionally-global `kg_node_embeddings`.
**Steps:**
1. `db_utils.py`: add `assert_namespace_filter(sql, params, namespace_id)` that raises if the query against `memory_embeddings` lacks a namespace predicate / binds no namespace param (a cheap structural check — a real guard, not cosmetic).
2. `semantic_search.py`: call the helper before executing every `memory_embeddings` query.
3. Add a clear comment at the `kg_node_embeddings` usage documenting it is global-by-design and why (cross-namespace vector ops), so the asymmetry is intentional and visible.
**Acceptance:** `tests/test_vector_tenancy.py`: a constructed `memory_embeddings` query missing the namespace predicate trips the assertion; a correct query passes; an integration search returns only the caller namespace's vectors. `make lint && make typecheck && pytest tests/test_vector_tenancy.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 126 — vector-tenancy-assert`, paste the gate output, and wait for review.
