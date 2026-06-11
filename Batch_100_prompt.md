1. **One batch = one branch = one commit.** Branch name `batch-100-governance-last-known-good`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so (one new module IS authorized below). If you think you need more, STOP and report.
4. **Minimal diff.** Reuse existing utilities (`_jsonrpc_error_response`, `A2AScopeViolationError`, `_safe_counter`, the existing `engine.redis_client`). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes
   - existing tests you touched still pass (`tests/test_tools_administration.py`, `tests/test_dispatch_error_envelopes.py`, `tests/test_a2a_hardening.py`)
   - if you changed MCP tool counts, update `tests/test_tool_registry.py` exact-count assertions in the SAME batch
6. **Migrations:** none in this batch.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside `scoped_pg_session`; `append_event` runs inside the same transaction as its data write; never `UPDATE`/`DELETE` `event_log`; never put raw content/PII into `event_log.params`.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only — never read it from, or write it to, a database/settings table/endpoint.
9. **If a test needs live databases**, it is `@pytest.mark.integration`. Pure-unit batches must not require Docker — mock Redis.
10. **Report format per batch:** what changed (files), the gate output (lint/typecheck/test green), and anything you had to STOP on.

**Skill legend:** skills are from the Antigravity skills catalogue; load the listed skills for the batch before coding. Pick the first as primary.

**Skills:** `backend-architect` (primary), `python-pro`, `security-auditor`
**Depends on:** none
**Files:** **new** `nce/tool_governance.py`; `nce/mcp_stdio_dispatch.py` (the `nce:tools:disabled` `hexists` check ~`:74-83`); `nce/a2a_server.py` (the A2A skill disable check ~`:604-613`); `nce/config.py` (typed-env knobs); `nce/observability.py` (`_safe_counter` ~ near other counters); **new** `tests/test_tool_governance.py`
**Goal:** Replace the fail-OPEN governance check (audit Domain 1, CWE-636/CWE-1188 inversion) with a **last-known-good interceptor**: high availability without ever silently un-revoking an admin-disabled tool/skill on a Redis blip. Today both surfaces do `except Exception: log.warning("defaulting to enabled")` — a revoked skill executes during a Redis outage. The HMAC nonce store already fails *closed* (`nce/auth.py`); align governance with that posture.
**Steps:**
1. Confirm the current code: `mcp_stdio_dispatch.py` calls `await engine.redis_client.hexists("nce:tools:disabled", name)` inside `try/except` that returns nothing on error (fail-open); `a2a_server.py` does the same and raises `A2AScopeViolationError` only on a positive hit. If the shape differs, STOP.
2. Add config knobs in the typed-env block: `NCE_TOOL_GOVERNANCE_STALE_OK_SEC` (`_int_env`, 30, min 1) and `NCE_TOOL_GOVERNANCE_STALE_HARD_SEC` (`_int_env`, 300, min 1).
3. **new** `nce/tool_governance.py`: a process-local `ToolGovernanceCache` holding `frozenset[str]` of disabled names + a monotonic timestamp. `async def is_disabled(redis_client, name) -> bool`: serve the snapshot without a Redis call while age < STALE_OK; otherwise refresh via `hkeys("nce:tools:disabled")`. On Redis error: keep serving the snapshot until age > STALE_HARD, then raise `GovernanceUnavailable` (degraded = fail-closed). No `time.time()` wall-clock for the TTL — use `time.monotonic()`. Increment a `_safe_counter` `nce_tool_governance_degraded_total` when entering hard-stale.
4. Wire both surfaces to `ToolGovernanceCache`: a positive `is_disabled` returns the strict scope error each surface already uses (`-32005` stdio / `A2AScopeViolationError`→`-32011` A2A); a `GovernanceUnavailable` returns `-32005` (stdio) / `A2AScopeViolationError` (A2A) with a "governance registry unavailable" detail — **never** `-32603` and never an internal frame.
5. Keep the cache a module singleton; both surfaces share one instance so a refresh on either warms both.
**Acceptance:** `tests/test_tool_governance.py` (pure-unit, mocked Redis) asserting: (a) disabled name → blocked; (b) Redis raises within STALE_OK → last snapshot still enforced (a previously-disabled tool stays blocked); (c) Redis raises past STALE_HARD → `GovernanceUnavailable` (fail-closed) and the degraded counter increments; (d) re-enable propagates within STALE_OK after recovery. `make lint && make typecheck && pytest tests/test_tool_governance.py` clean.

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\tools\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\tools\trigger_tag_audit.py

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch 100 — governance-last-known-good`, paste the gate output, and wait for review.
