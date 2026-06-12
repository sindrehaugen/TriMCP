1. **One batch = one branch = one commit.** Branch name `batch-109-envelope-read-residual`. Never combine batches.
2. **Verify before you act.** Batch 46 already shipped envelope encryption + taught the primary read paths and left a kaizen for these four consumers. **First confirm what Batch 46 actually wired** (grep `maybe_decrypt_raw_data` usage). If these consumers already route through it, STOP and report — the batch may be a no-op.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing `maybe_decrypt_raw_data()` (envelope.py) and the established metric-registration pattern in `observability.py`. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - full suite passes with `NCE_ENVELOPE_ENCRYPTION_ENABLED=true`
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** decryption failures must NOT abort a whole batch or corrupt state; flag-and-skip only. Tenant-scoped context preserved.
8. **Secrets:** `NCE_MASTER_KEY` env-only; never log plaintext or DEK material.
9. **DB-dependent tests** are `@pytest.mark.integration`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `python-pro` (primary), `security-auditor`
**Depends on:** none (closes Batch 46 kaizen)
**Files:** `nce/re_embedder.py`; `nce/reembedding_worker.py`; `nce/consolidation.py`; `nce/contradictions.py`; `nce/envelope.py` (`maybe_decrypt_raw_data` — read-only reference unless a skip-helper is needed); `nce/observability.py` (new metric); `tests/test_envelope_read_consumers.py` (new)
**Goal:** With envelope encryption enabled, these four consumers read `episodes.raw_data` directly and would break on ciphertext — so the flag can never be turned on. Route all four through `maybe_decrypt_raw_data()` and add a skip-on-failure path so a zeroed `wrapped_dek` (provable forgetting) degrades gracefully instead of poisoning the pipeline.
**Steps:**
1. Identify every site in the four files that loads Mongo `raw_data`/`raw_code`; wrap each through `maybe_decrypt_raw_data()`.
2. On decrypt failure for a given memory: set `metadata.dek_unreadable=true` (or equivalent existing marker), skip that memory, continue the batch; increment metric `nce_envelope_decrypt_failures_total` (register in `observability.py`).
3. Do not change write paths or the encryption toggle default.
**Acceptance:** `tests/test_envelope_read_consumers.py` (`@pytest.mark.integration`): with `NCE_ENVELOPE_ENCRYPTION_ENABLED=true`, store → consolidate → contradiction-check → re-embed end-to-end succeeds; a memory with a zeroed `wrapped_dek` is skipped (not raised), flagged, and the failure metric increments. `make lint && make typecheck && NCE_ENVELOPE_ENCRYPTION_ENABLED=true pytest -m integration tests/test_envelope_read_consumers.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 109 — envelope-read-residual`, paste the gate output, and wait for review.
