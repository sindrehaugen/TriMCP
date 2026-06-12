1. **One batch = one branch = one commit.** Branch name `batch-127-nli-lifecycle`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy**.
3. **Modify only the files listed in the batch.** No new modules/deps.
4. **Minimal diff.** Reuse the existing NLI loader, the observability gauge-registration pattern, and the re_embedder's `torch.cuda.empty_cache()` usage. Match surrounding style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` clean
   - `make typecheck` clean
   - the specific test named in the batch passes
   - existing contradiction/NLI tests still pass (`@pytest.mark.heavy` where model-loading)
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** none specific; do not change contradiction-detection semantics, only the model's memory lifecycle.
8. **Secrets:** `NCE_MASTER_KEY` env-only.
9. **Model-loading tests** carry `@pytest.mark.heavy`.
10. **Report format:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `ml-engineer` (primary), `python-pro`
**Depends on:** none
**Files:** `nce/contradictions.py` (NLI singleton loader ~`_load_nli_model`); `nce/observability.py` (VRAM gauge); `tests/test_nli_lifecycle.py` (new)
**Goal:** The NLI cross-encoder is an `@lru_cache(maxsize=1)` singleton that is never evicted — it pins VRAM/RAM indefinitely. Replace with a TTL + idle-eviction wrapper that frees the model (and CUDA cache) when unused, and expose a VRAM gauge.
**Steps:**
1. Replace the `@lru_cache` singleton with a small TTL/idle-eviction wrapper: load on demand, evict after `cfg.NCE_NLI_IDLE_TTL_S` (default 900) of no use; on eviction drop the reference and call `torch.cuda.empty_cache()` if CUDA.
2. `observability.py`: register a VRAM gauge updated around load/evict (mirror the re_embedder VRAM metric naming).
3. Do not change NLI scoring, thresholds, or the contradiction funnel — lifecycle only.
**Acceptance:** `tests/test_nli_lifecycle.py` (`@pytest.mark.heavy`): model loads on first use; after the idle TTL it is evicted and the reference dropped (CUDA empty_cache invoked when applicable); a subsequent call reloads correctly; the VRAM gauge moves on load/evict. `make lint && make typecheck && pytest -m heavy tests/test_nli_lifecycle.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After this batch: open a PR titled `Batch 127 — nli-lifecycle`, paste the gate output, and wait for review.
