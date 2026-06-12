1. **One batch = one branch = one commit.** Branch name `batch-109-envelope-read-residual`. Never combine batches.
2. **Verify before you act.** Batch 46 shipped envelope encryption + taught the primary read paths (`orchestrators/memory.py`, `orchestrators/temporal.py`, `semantic_search.py`, `graph_query.py`, `snapshot_mcp_handlers.py`, `me_app.py` all call `maybe_decrypt_raw_data`). **Pre-flight (2026-06-11) found:** `re_embedder.py:~164` and `reembedding_worker.py:~234-245` read `episodes.raw_data`/`code_files.raw_code` RAW (confirmed targets); `contradictions.py` has ZERO raw_data reads (operates on embeddings + PG text — likely OUT of scope); `consolidation.py` only *writes* its abstraction `raw_data` at ~`:260` (verify whether it reads any source raw payload — if not, OUT of scope). Re-grep to confirm before coding; drop any consumer that does not read a raw payload, and report which you dropped.
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
**Files (confirmed):** `nce/re_embedder.py`; `nce/reembedding_worker.py`; `nce/envelope.py` (`maybe_decrypt_raw_data` — read-only reference; note its current signature takes `(raw_data, wrapped_dek)`, so each call site must also fetch the memory's `wrapped_dek`); `nce/observability.py` (new metric); `tests/test_envelope_read_consumers.py` (new). **Files (audit, include only if they actually read a raw payload):** `nce/consolidation.py`, `nce/contradictions.py`.
**Goal:** With envelope encryption enabled, the re-embed consumers read `episodes.raw_data`/`code_files.raw_code` directly and would break on ciphertext — so the flag can never be turned on. Route every raw-payload read through `maybe_decrypt_raw_data()` and add a skip-on-failure path so a zeroed `wrapped_dek` (provable forgetting) degrades gracefully instead of poisoning the pipeline.
**Steps:**
1. In `re_embedder.py` and `reembedding_worker.py`, every site that loads Mongo `raw_data`/`raw_code` must also load that memory's `wrapped_dek` and pass both through `maybe_decrypt_raw_data()`. For `consolidation.py`/`contradictions.py`, first confirm a raw read exists; if none, exclude the file and note it in the report.
2. On decrypt failure for a given memory: set `metadata.dek_unreadable=true` (or equivalent existing marker), skip that memory, continue the batch; increment metric `nce_envelope_decrypt_failures_total` (register in `observability.py`).
3. Do not change write paths or the encryption toggle default.
**Acceptance:** `tests/test_envelope_read_consumers.py` (`@pytest.mark.integration`): with `NCE_ENVELOPE_ENCRYPTION_ENABLED=true`, store → consolidate → contradiction-check → re-embed end-to-end succeeds; a memory with a zeroed `wrapped_dek` is skipped (not raised), flagged, and the failure metric increments. `make lint && make typecheck && NCE_ENVELOPE_ENCRYPTION_ENABLED=true pytest -m integration tests/test_envelope_read_consumers.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 109 — envelope-read-residual`, paste the gate output, and wait for review.
