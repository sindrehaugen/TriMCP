Batch 69 — landing-bucket-ttl

> Diagnostic Log Digestion Engine · Phase 1. Master plan: `_internal/work-docs/roadmaps/Diagnostic_Log_Digestion_Engine_Plan_2026-06-10.md`. Ledger: `_internal/Roadmaps/diagnostics_execution_ledger.md`.

## Operating rules (apply to this batch)
1. One batch = one branch = one commit. Branch `batch-69-landing-bucket-ttl`. Never combine batches.
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
- C4 Diff: `git add -A` → write `git diff --cached` to `_internal/diffs/diff_batch_69-landing-bucket-ttl.md`; set this row to `[WAITING TAG]` in the ledger.
- C5 TAG: run the audit yourself per `_internal/templates/tag_audit.md` — read the diff + every modified file end-to-end (no ellipsis/placeholders), apply architect-review/vibe-code-auditor/logic-lens/performance-optimizer/fix-review lenses, enforce WORM/RLS+secrets, emit `### TAG Batch 69 Evaluation Audit Report` matrix.
- C6 Resolve: if REJECTED → write TD+Findings+Kaizen, fix in-scope, re-run C2–C5 (out-of-scope fix → STOP). If PASSED → set ledger row `[PASSED TAG] Done`, commit `batch-69-landing-bucket-ttl`, open PR `Batch 69 — landing-bucket-ttl`.

---

**Skills:** `python-pro` (primary), `aws-serverless` *(MinIO/S3 lifecycle)*
**Depends on:** 65 · **Parallel:** —
**Files:** `nce/storage.py` (`generate_secure_presigned_url` ~`:21`, `presigned_put_object` usage ~`:102`).

**Goal:** Add an idempotent `ensure_landing_bucket(minio_client)` that creates the landing bucket and sets a 7-day expiry lifecycle.

**Steps:**
1. Add `ensure_landing_bucket(minio_client, bucket: str | None = None, ttl_days: int | None = None) -> None` using `bucket_exists`/`make_bucket` and the `minio` client's `set_bucket_lifecycle` with an expiry rule (days = `cfg.NCE_DIAG_LANDING_TTL_DAYS`) plus an abort-incomplete-multipart rule. Default `bucket = cfg.NCE_DIAG_LANDING_BUCKET`.
2. Make it safe to call repeatedly (swallow "already exists"/"already owned" errors).
3. Do NOT call it at import time; just expose it for later startup wiring.

**Acceptance:** unit test with a mocked `Minio` client asserting `make_bucket` is skipped when `bucket_exists` is true and `set_bucket_lifecycle` is invoked with the configured TTL. Pure-unit. `make lint && make typecheck` clean.

Final (self-orchestrated — do not skip): run the Closing Protocol C1–C6 above — gate (`make lint && make typecheck && pytest <the storage test>`) → reviews → write `_internal/diffs/diff_batch_69-landing-bucket-ttl.md` + set ledger row `[WAITING TAG]` → run the TAG audit yourself per `_internal/templates/tag_audit.md` and emit the matrix → if REJECTED fix in-scope and re-run; if PASSED mark ledger Done, commit `batch-69-landing-bucket-ttl`, open PR `Batch 69 — landing-bucket-ttl`.
