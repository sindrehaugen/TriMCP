# NCE — Tech Debt Ledger (implementation review)

> Captured during the post-commit review of Gemini's implementation run (Batches 1–17 committed as `f81f546`; Batch 18 parked). Source of truth for cleanup once the full prompt sequence (`NCE_IMPLEMENTATION_PROMPTS.md`) is finished. Each item is independently actionable.
>
> **Scope note:** the correctness-critical batches were spot-checked against the actual code and are genuinely solid — Batch 3 routes salience to `memory_salience`; replay sets `payload_ref`; Batch 13 implements `prev_chain_hash` v2 signing with a genesis sentinel + version-branched verification. The items below are the gaps.

| ID | Severity | Area | Status |
| :-- | :-- | :-- | :-- |
| TD-1 | HIGH (process) | Git hygiene | open — recurring (out-of-order commits + uncommitted backlog) |
| TD-2 | MED | Batch 18 (saga metrics) | ✅ RESOLVED (re-done as scoped wrapper) |
| TD-3 | MED | Replay robustness | open |
| TD-4 | LOW (gate) | Verification | open |
| TD-5 | LOW | Working-tree entanglement | informational |
| TD-6 | MED | Batch 21 (embedding sidecar resilience) | open — partial |

---

## TD-1 — No per-batch commits (HIGH, process)
**What:** Gemini accumulated Batches ~7–18 (plus older uncommitted D365/NetBox work) into one large uncommitted working-tree blob. It had to be committed as a single 243-file checkpoint (`f81f546`, +11,945/−2,044).
**Why it matters:** Per-batch bisect, review, and rollback are impossible across that range. If a regression surfaces, it can't be isolated to a batch.
**Evidence:** `git log` shows the prior commit was ~Batch 5–6 ("refactor: Batch 1-6 …"); everything after sat uncommitted until `f81f546`.
**Fix / going forward:** Enforce the Global Rule "one batch = one branch = one commit" for Batches 18→64. Each future batch must commit before the next starts. (No remediation possible for the already-bundled 1–17 range — accept and move on.)

**Update (post `f81f546`):** Batches 18 and 19 were subsequently committed individually (`5fc6494` Batch 18, `fad62b2` Batch 19) — good. **But the pattern is still slipping:**
- **Out-of-order history.** The branch advanced to `batch-23-atms-cascade` and **Batch 23 was committed (`2272398`) *before* 18/19**, so the linear log reads `Batch 23 → Batch 18 → Batch 19`. Cosmetic only, but it breaks "read the log to see batch order."
- **Fresh uncommitted backlog.** As of this update, ~6 batches of work sit uncommitted in the working tree, spanning roughly: Batch 20/21 (NetBox client timeouts + `http_resilience` routing — `netbox/*`, `http_resilience.py`, `dynamics365/client.py`), Batch 22 (SSRF/binary pin — `net_safety.py`, `extractors/{libreoffice,project_ext}.py`), Batch 24 (neuromorphic MCP tool — `graph_mcp_handlers.py`, `tool_registry.py`, `mcp_stdio_tools.py`, `test_tool_registry.py`), Batch 25 (do-calculus escalation — `dynamics365/{ingestion,netbox_bridge}.py`, `consolidation.py`).
- **Action:** commit the backlog one batch per commit (verify each + ensure `test_tool_registry.py` counts match the new tools), and have Gemini commit each batch immediately on completion rather than accumulating. Consider committing in dependency order even if executed out of order.

**Update 2 (Batches 18–25 now committed):** `5fc6494` (B18), `fad62b2` (B19), `55e1da3` (B22), `4e10a9e` (B20+21+24+25). **B20/21/24/25 had to be a single commit** — `circuits.py` (B20 timeout + B25 escalation), `netbox_bridge.py` (B21 + B25), and `tool_registry.py`/`mcp_stdio_tools.py`/`test_tool_registry.py` (B24 + B25) are each edited by two batches in one working-tree diff, so per-batch splitting wasn't possible without `git add -p` hunk surgery. Concrete proof that accumulating-then-committing destroys per-batch granularity. Verified before commit: `py_compile` clean; `test_tool_registry.py` 45 passed (registry 59→61, cacheable 6→7).

## TD-2 — Batch 18 `SagaMetrics` global monkeypatch (MED) — ✅ RESOLVED
**Resolution (verified):** Batch 18 was re-done correctly. `nce/observability.py:453-474` defines `SagaMetrics` as a context manager (`__enter__`/`__exit__`) with a `@staticmethod record_failure(stage)`; `nce/orchestrators/memory.py` now uses `with SagaMetrics("store_memory"):` (`:727`) and `with SagaMetrics("store_artifact"):` (`:854`) plus `SagaMetrics.record_failure(...)` on rollback paths. The import-time `__exit__` monkeypatch is gone. `py_compile` clean. (Batch 19 also landed: `EMBEDDING_FALLBACKS.inc()` + `dispatch_alert` on the degraded path, `embeddings.py:301-307` — closes the N-D silent-degradation gap.) Both are uncommitted in the working tree pending a per-batch commit (see TD-1).

<details><summary>Original finding (for history)</summary>

## (original) Batch 18 `SagaMetrics` global monkeypatch
**What:** `nce/orchestrators/memory.py:46-66` monkeypatches `SagaMetrics.__exit__` at **module import** to force `store_memory` saga metrics on. This is a global mutation of a shared class (affects every `SagaMetrics` user), not the scoped wrapper the prompt specified. The batch is unfinished and was never TAG-verified.
**Why it matters:** Import-time monkeypatching is fragile and surprising; it couples an unrelated global to the memory orchestrator and can break other saga metrics or tests in non-obvious ways.
**Evidence:** `git status` shows `nce/orchestrators/memory.py` as the sole remaining working-tree change; it contains `_store_memory_saga_metrics_exit` + `SagaMetrics.__exit__ = …` at module level, plus `SagaMetrics.record_failure(...)` calls in the saga.
**Fix:** Re-do Batch 18 as a scoped wrapper around the `store_memory` saga (e.g. an explicit `with SagaMetrics("store_memory"):` context, or a per-call enable flag) — no class-level monkeypatch. Then run the batch's acceptance gate and commit. The current parked diff in `memory.py` should be reverted or rewritten, not committed as-is.
**Note:** `memory.py` also carries older uncommitted saga-log changes (`json.dumps` on `saga_execution_log`); preserve those when reworking Batch 18.

</details>

## TD-3 — Replay handlers silently skip on missing `payload_ref` (MED)
**What:** `nce/replay.py` `_handle_store_memory` (`:525-527`) and `_handle_consolidation_run` (`:726-728`) `return {"skipped": True, "reason": "payload_ref_missing_in_params"}` when the event has no `payload_ref`.
**Why it matters:** During reconstruction/fork, an event missing `payload_ref` is **dropped silently** — no log, metric, or alert. This can mask data loss and will make the Wave 5 state-digest mismatch hard to diagnose (source vs target divergence with no breadcrumb).
**Fix:** Keep the skip (don't crash the whole replay) but emit a `log.warning` + increment a counter (and surface the skip count in `replay_runs` / `replay_status`). Revisit when Wave 5 (verified replay / state-digest) lands — a skipped event should make `digest_match` false with a clear reason.

## TD-4 — Confirm the cumulative committed state is green (LOW, gate)
**What:** TAG verified each batch green individually, and `py_compile` passed on the changed files, but the **cumulative** committed state (`f81f546`) hasn't been gate-checked as a whole.
**Fix:** Run once on the committed tree:
```
make lint && make typecheck && pytest -m "not heavy"
```
Run the integration subset against `make local-up`:
```
pytest -m integration
```
Record the result; if anything fails, it's a cross-batch interaction to fix before continuing.

## TD-5 — Working-tree entanglement of two work streams (LOW, informational)
**What:** The checkpoint commit bundled my implementation Batches 1–17 **together with** older never-committed Gemini RL-sequence work (D365 vertical modules, NetBox modules, etc.). They were interleaved in the same uncommitted tree, so attribution is fuzzy.
**Why it matters:** Only relevant for archaeology — "which change came from which sequence" is no longer cleanly answerable for this checkpoint.
**Fix:** None required. Noted so future reviewers don't assume `f81f546` == "only Batches 1–17."

## TD-6 — Batch 21 embedding-sidecar resilience is incomplete (MED, partial)
**What:** Batch 21 was specified to route the **embedding sidecar** *and* D365/NetBox HTTP through `http_resilience` (retry + backoff + breaker). The committed work (`4e10a9e`) routed **D365 client + netbox_bridge** but **not the embedding sidecar** — `nce/embeddings.py` was not in the diff (last touched in Batch 19, which added the fallback *counter + alert* at `:301-307`, not retry-before-fallback).
**Why it matters:** The embedding sidecar is on **every read/write hot path** (N-A/N-C in the plan). Without retry/breaker in front of it, a transient sidecar blip degrades straight to the deterministic hash-stub (lower-quality vectors) instead of retrying first — and a *sustained* outage keeps paying the full per-call timeout with no fast-fail. The Batch-19 alert will fire, but quality silently drops in the meantime.
**Evidence:** `embeddings.py:528,559` still issue raw `httpx.Client(...)` calls; `git show 4e10a9e --stat` does not include `embeddings.py`.
**Fix:** Wrap the sidecar `httpx` calls (`CognitiveRemoteBackend._sync_embed_batch`) with `http_resilience.request_with_retry`, keeping the hash-stub fallback only as the final resort after retries; add a circuit breaker so a sustained outage fast-fails. Re-run with a transient-503-then-success test.

---

## Carry-overs from the Wave 0 audit still open in code (track alongside the plan)
These were confirmed OPEN in the Wave 0 re-audit and are scheduled in later batches — listed here so they aren't lost:
- **R2 / content-free WORM log** — `event_log.params` still carries `entities`/`triplets`; `saga_execution_log.payload` still stores the **pre-redaction** plaintext `summary`. (Batch 44.)
- **R4 / `nce_gc` least-privilege** — role is `BYPASSRLS NOLOGIN` but no worker connects as it; workers use `nce_app` via `PG_DSN`. Docs (`database_architecture.md:110`, `enterprise_security.md:158`) overstate this. (Batch 56 — implement segregation or remove the dormant role + fix docs.)
- **R-A / Mongo write durability** — saga Mongo write uses default `w:1, j:false`; power-loss window can orphan a committed PG row. (Batch 57.)
- **R-B / reverse-orphan sweep** — GC is forward-only; no detection of PG memories with a missing Mongo doc. (Batch 58.)

---

*Last updated: Batches 18–25 committed (`5fc6494` B18, `fad62b2` B19, `2272398` B23, `55e1da3` B22, `4e10a9e` B20+21+24+25) on branch `batch-23-atms-cascade`. Open debt: TD-1 (commit hygiene), TD-3 (replay silent-skip), TD-4 (run cumulative gate), TD-6 (embedding-sidecar retry). Owner: NCE team. Revisit after the full prompt sequence completes.*
