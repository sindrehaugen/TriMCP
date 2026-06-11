Batch 91 — ingest-digest-endpoint

> Diagnostic Log Digestion Engine · Phase 5 (edge). Master plan: `_internal/work-docs/roadmaps/Diagnostic_Log_Digestion_Engine_Plan_2026-06-10.md`. Ledger: `_internal/Roadmaps/diagnostics_execution_ledger.md`.

## Operating rules (apply to this batch)
1. One batch = one branch = one commit. Branch `batch-91-ingest-digest-endpoint`. Never combine batches.
2. Verify before you act: open each target file and confirm the cited symbol exists. Line numbers are approximate (`~`) — trust the symbol name, not the number. On any mismatch/contradiction, STOP and report — do not invent a fix or create a new file.
3. Modify only the files listed below. No new modules/classes/deps/abstractions unless marked **new**. If you think you need one, STOP and report.
4. Minimal diff; reuse existing utilities (`scoped_pg_session`, `unmanaged_pg_connection`, `append_event`, `consume_resources`, `acquire_cron_lock`, `get_priority_queue`/`enqueue_traced`, `traced_worker_job`, `_check_poison_pill`/`store_dead_letter`, `generate_secure_presigned_url`, `require_master_key`). Match surrounding style.
5. Acceptance gate (all green before commit): `make lint`; `make typecheck`; the named test; any touched tests; if MCP tool counts changed, update `tests/test_tool_registry.py` exact-count asserts in THIS batch.
6. New migrations → `nce/migrations/` next free number (current max 018 → next 019); mirror into `nce/schema.sql`; never edit an existing migration.
7. WORM/RLS: tenant SQL inside `scoped_pg_session`; `append_event` in the same txn as its write; never UPDATE/DELETE `event_log`; no raw content/PII in `event_log.params`.
8. `NCE_MASTER_KEY` is env-only — never read/write it via DB/settings/endpoint.
9. DB-dependent tests are `@pytest.mark.integration` (run via `pytest -m integration` against `make local-up`); pure-unit batches must not need Docker.
10. Report: files changed, gate output, the TAG verdict matrix, anything you STOPped on.

## Closing protocol (self-orchestrated — do NOT use Antigravity scripts)
Reproduce `generate_diff.py`/`trigger_tag_audit.py`/`start_rl.py`/`generate_ledger.py` BY HAND. Diff + ledger files are exempt from rule 3.
- C1 Stop when steps done; do not start another batch.
- C2 Gate: run the rule-5 gate; all green or STOP.
- C3 Reviews: run `code-reviewer` then `fix-review` (+`simplify-code` if logic refactored); in-scope fixes only; out-of-scope → one-line Kaizen/TD note.
- C4 Diff: `git add -A` → write `git diff --cached` to `_internal/diffs/diff_batch_91-ingest-digest-endpoint.md`; set this row to `[WAITING TAG]` in the ledger.
- C5 TAG: run the audit yourself per `_internal/templates/tag_audit.md` — read the diff + every modified file end-to-end (no ellipsis/placeholders), apply architect-review/vibe-code-auditor/logic-lens/performance-optimizer/fix-review lenses, enforce WORM/RLS+secrets, emit `### TAG Batch 91 Evaluation Audit Report` matrix.
- C6 Resolve: if REJECTED → write TD+Findings+Kaizen, fix in-scope, re-run C2–C5 (out-of-scope fix → STOP). If PASSED → set ledger row `[PASSED TAG] Done`, commit `batch-91-ingest-digest-endpoint`, open PR `Batch 91 — ingest-digest-endpoint`.

---

**Skills:** `backend-security-coder` (primary), `api-security-best-practices`, `auth-implementation-patterns`
**Depends on:** 73, 90 · **Parallel:** —
**Files:** `nce/webhook_receiver/main.py` (add the route) — OR `nce/server.py` if that is the correct ASGI ingress (verify which exposes the edge-facing surface). Reuse `nce/mtls.py`, `nce/jwt_auth.py`, `nce/signing.py`, `nce/envelope.py`, and the Batch-73 orchestrator.

**Goal:** The enterprise `POST /ingest/digest` endpoint that merges a signed edge payload under RLS (this is the decided write-back mechanism — NOT an A2A scope change).

**Steps:**
1. Authenticate the edge via mTLS + JWT (audience-checked); verify the payload signature; treat all input as untrusted (validate shapes, clamp anomaly counts, reject raw log lines).
2. Open `scoped_pg_session` for the edge's namespace; dedupe by `ingest_id`; merge edges/rollup via the Batch-73 orchestrator. The edge never writes the core DB directly.
3. Return an ack the spool (Batch 90) can key on; rate-limit consistent with other ingress endpoints.

**Acceptance:** integration test: valid signed payload merges under the right namespace; bad signature/identity → 403; replayed `ingest_id` is a no-op; a cross-namespace write is blocked by RLS. `make lint && make typecheck` clean.

Final (self-orchestrated — do not skip): run the Closing Protocol C1–C6 above — gate (`make lint && make typecheck && pytest -m integration <the endpoint test>`) → reviews → write `_internal/diffs/diff_batch_91-ingest-digest-endpoint.md` + set ledger row `[WAITING TAG]` → run the TAG audit yourself per `_internal/templates/tag_audit.md` and emit the matrix → if REJECTED fix in-scope and re-run; if PASSED mark ledger Done, commit `batch-91-ingest-digest-endpoint`, open PR `Batch 91 — ingest-digest-endpoint`.
