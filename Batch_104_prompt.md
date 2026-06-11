1. **One batch = one branch = one commit.** Branch name `batch-104-reembed-vram-guard`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities (`REEMBEDDER_VRAM_ALLOCATED`/`REEMBEDDER_VRAM_RESERVED`/`REEMBEDDER_VRAM_PEAK` in `nce/observability.py`, the `_int_env`/`_float_env` config helpers, `acquire_cron_lock`). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes (`tests/test_reembedding_worker.py`)
   - existing re-embedding tests still pass
6. **Migrations:** none.
7. **WORM/RLS invariants (never violate):** unchanged.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only.
9. **DB-dependent tests** are `@pytest.mark.integration`; the VRAM-gate test is pure-unit with a mocked `torch`/metrics (and may carry the existing `heavy` module marker only if it already loads models — prefer a mock so it runs in the fast lane).
10. **Report format per batch:** files changed, gate output, anything you STOPped on.

**Skill legend:** load the listed skills before coding; first is primary.

**Skills:** `mlops-engineer` (primary), `performance-engineer`, `python-pro`
**Depends on:** none
**Files:** `nce/reembedding_worker.py` (`ReembeddingWorker._embed` ~`:369-408`, `run_once`); `nce/config.py` (typed-env knobs); `tests/test_reembedding_worker.py`
**Goal:** Wire the ALREADY-DEFINED but orphaned VRAM metric (`nce_reembedder_vram_allocated_bytes`, `nce/observability.py` ~`:165`) into an actual back-pressure guard (audit Domain 3, CRITICAL). Today `_embed` calls `embed_batch` with no VRAM check; a large batch OOMs, the job dies, retries, and routes to the DLQ — the metric is never emitted by the live worker. Add a pause-don't-poison guard.
**Steps:**
1. Confirm `_embed` acquires the Redis embed lock then `return await _embeddings.embed_batch(texts)` with no VRAM check, and that `REEMBEDDER_VRAM_ALLOCATED`/`_RESERVED`/`_PEAK` gauges exist but are only recorded in the deprecated `nce/re_embedder.py` stub. If different, STOP.
2. Add config knobs: `NCE_REEMBED_VRAM_HIGH_WATERMARK` (`_float_env`, 0.85, min 0.1, max 0.99) and `NCE_REEMBED_VRAM_MAX_PRESSURE_WAITS` (`_int_env`, 12, min 0).
3. Before each batch in `_embed`, add an `async def _vram_pressure_gate(self)`: if `torch.cuda.is_available()`, read `torch.cuda.memory_allocated()` / `get_device_properties(0).total_memory`, emit the three VRAM gauges (labelled by `worker_id`), and if the ratio ≥ the high-watermark, `torch.cuda.empty_cache()` + `await asyncio.sleep` and retry up to MAX_PRESSURE_WAITS; if still saturated, raise a typed `VRAMPressureError`. No-op cleanly when CUDA is absent.
4. In `run_once`, catch `VRAMPressureError` and exit the tick cleanly (the keyset cursor resumes next cron tick) — pausing, NOT crashing into the DLQ. Log a warning.
**Acceptance:** `tests/test_reembedding_worker.py` (pure-unit, mocked `torch` + gauges): (a) below watermark → embeds normally and emits the allocated gauge; (b) saturated forever → raises `VRAMPressureError` after MAX_PRESSURE_WAITS and `run_once` yields cleanly (no exception escapes, no DLQ); (c) CUDA absent → gate is a no-op. `make lint && make typecheck && pytest tests/test_reembedding_worker.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch 104 — reembed-vram-guard`, paste the gate output, and wait for review.
