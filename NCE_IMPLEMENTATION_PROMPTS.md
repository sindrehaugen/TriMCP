# NCE — Micro-Batch Implementation Prompts (for Gemini 3.5 Flash / Antigravity IDE)

> **Purpose.** This document splits `NCE_MASTER_PLAN.md` into small, single-focus batches a junior executor can run one at a time and be **guaranteed to succeed**. Each batch is independently committable, cites exact files, names the recommended skills, and ends with a hard acceptance gate. Execute **strictly in order** — later batches assume earlier ones landed.
>
> **Audited base.** Line numbers come from the post-Gemini (20/20) Wave 0 audit. If a cited line/path does not match what you see, **STOP and report** — do not guess.

---

## GLOBAL RULES — apply to EVERY batch (read once, obey always)

1. **One batch = one branch = one commit.** Branch name `batch-NN-shortname`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities (`scoped_pg_session`, `unmanaged_pg_connection`, `append_event`, `NotificationDispatcher`, `acquire_cron_lock`, `encrypt_signing_key`/`decrypt_signing_key`, `require_master_key`). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes
   - existing tests you touched still pass
   - if you changed MCP tool counts, update `tests/test_tool_registry.py` exact-count assertions in the SAME batch
6. **Migrations:** new SQL migrations go in `nce/migrations/` with the next free number (current max = `012`). Mirror any schema change into `nce/schema.sql`. Never edit an existing migration.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside `scoped_pg_session`; `append_event` runs inside the same transaction as its data write; never `UPDATE`/`DELETE` `event_log`; never put raw content/PII into `event_log.params`.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only — never read it from, or write it to, a database/settings table/endpoint.
9. **If a test needs live databases**, it is `@pytest.mark.integration`; run it with `pytest -m integration` against `make local-up`. Pure-unit batches must not require Docker.
10. **Report format per batch:** what changed (files), the gate output (lint/typecheck/test green), and anything you had to STOP on.

**Skill legend:** skills are from the Antigravity skills catalogue; load the listed skills for the batch before coding. Pick the first as primary.

---

# PHASE A — Replay correctness (Wave 0.5, FIRST — fixes a live runtime bug)

> Reconstructive/forked replay fails today: handlers reference `memories.summary`/`memories.salience` (neither column exists) and omit the NOT-NULL `payload_ref`. Salience lives in `memory_salience.salience_score`. Fix the handlers, then prove it with a test. **Correctness only — determinism stays in Phase H.**

## Batch 1 — Fix `_handle_store_memory` schema mismatch
**Skills:** `event-sourcing-architect`, `postgresql`, `python-pro`
**Depends on:** none
**Files:** `nce/replay.py` (`_handle_store_memory`, ~`:498-560`); reference `nce/schema.sql` (`memories` `:55-89`, `memory_salience` `:376-385`), `nce/event_types.py` (store_memory params).
**Goal:** Make the handler insert a valid `memories` row.
**Steps:**
1. Remove `summary` and `salience` from the SELECT (`:509-518`) and INSERT (`:529-555`) column lists.
2. Add `payload_ref` to the INSERT, sourced from the event's `params.payload_ref` (24-hex ObjectId). It is `NOT NULL` + CHECK `^[a-f0-9]{24}$`.
3. If a salience value must be carried, write it to `memory_salience(memory_id, agent_id, namespace_id, salience_score)` via a separate INSERT/UPSERT — not onto `memories`.
4. Keep using `uuid.uuid4()` for now (determinism is Phase H — do NOT change ID generation here).
**Acceptance:** `make lint && make typecheck` clean; the handler compiles and a focused unit test constructing a fake store_memory event no longer raises `UndefinedColumnError`/NotNull. (Full integration assertion is Batch 4.)

## Batch 2 — Fix `_handle_consolidation_run` schema mismatch
**Skills:** `event-sourcing-architect`, `postgresql`, `python-pro`
**Depends on:** Batch 1
**Files:** `nce/replay.py` (`_handle_consolidation_run`, ~`:694-733`)
**Goal:** Same fix as Batch 1 for the consolidation handler.
**Steps:**
1. Remove `summary`/`salience` from the INSERT (`:702-733`); add `payload_ref` from event params.
2. Route any salience into `memory_salience.salience_score`.
3. Preserve the existing `memory_type='consolidated'`, `assertion_type='fact'` literals.
**Acceptance:** lint + typecheck clean; handler no longer references non-existent columns (grep `summary`/`salience` in the function returns nothing on `memories`).

## Batch 3 — Fix `_handle_boost_memory` salience target
**Skills:** `postgresql`, `python-pro`, `code-reviewer`
**Depends on:** Batch 1
**Files:** `nce/replay.py` (`_handle_boost_memory`, ~`:613-626`)
**Goal:** Boost salience in the correct table.
**Steps:**
1. Replace `UPDATE memories SET salience = LEAST(1.0, salience + $1)` with an UPDATE/UPSERT on `memory_salience` (`salience_score = LEAST(1.0, salience_score + $1)`) keyed by `(memory_id, agent_id)`.
2. Confirm `_handle_forget_memory` is untouched (it is already correct).
**Acceptance:** lint + typecheck clean; grep shows no `memories.salience` reference remains anywhere in `nce/replay.py`.

## Batch 4 — Integration test: replay handlers apply real state (R1 regression guard)
**Skills:** `python-testing-patterns`, `test-automator`, `tdd-orchestrator`
**Depends on:** Batches 1–3
**Files:** new `tests/test_replay_handlers_integration.py`
**Goal:** Prove replay runs end-to-end against a live DB and lock R1 closed.
**Steps:**
1. `@pytest.mark.integration`. Seed a source namespace with a `store_memory` + `consolidation_run` + `boost_memory` event stream.
2. Run reconstructive replay into a fresh target namespace.
3. Assert rows land with no `UndefinedColumn`/`NotNull`/CHECK error; assert `memory_salience.salience_score` reflects the boost; assert `memories.payload_ref` is set and matches the 24-hex format.
**Acceptance:** `pytest -m integration tests/test_replay_handlers_integration.py` passes against `make local-up`.

---

# PHASE B — Test-suite speed & reliability (Wave 1.0 — do before adding more tests)

## Batch 5 — Add `pytest-xdist` for parallel test runs (T2)
**Skills:** `python-testing-patterns`, `test-automator`
**Depends on:** none (can run anytime)
**Files:** `requirements-dev.txt`; `docs/developer_onboarding.md` (test section)
**Goal:** Enable `pytest -n auto`.
**Steps:**
1. Add `pytest-xdist` to `requirements-dev.txt` (pinned).
2. Document `pytest -n auto` as the default fast run.
**Acceptance:** `pip install -r requirements-dev.txt` succeeds; `pytest -n auto` collects and runs (green or pre-existing failures only — no new failures from parallelism).

## Batch 6 — Add per-test timeout (T3)
**Skills:** `python-testing-patterns`, `test-automator`
**Depends on:** none
**Files:** `requirements-dev.txt`, `pytest.ini`
**Goal:** Convert hangs into one failing test.
**Steps:**
1. Add `pytest-timeout` to `requirements-dev.txt`.
2. In `pytest.ini` `addopts`, append `--timeout=60 --timeout-method=thread`.
**Acceptance:** a deliberately-sleeping throwaway test fails at ~60s instead of hanging; full suite still green.

## Batch 7 — Scope the signing-cache reset so unit tests stop re-deriving the KDF (T1)
**Skills:** `python-testing-patterns`, `security-auditor`, `python-patterns`
**Depends on:** none
**Files:** `tests/conftest.py` (`_reset_signing_key_cache_after_test`, `:252-269`)
**Goal:** Stop wiping `signing._key_cache` after every test (Argon2id/PBKDF2-600k re-derivation is the suite's biggest cost).
**Steps:**
1. Make the autouse reset opt-in: only clear the cache for tests marked `@pytest.mark.signing_isolation` (register the marker in `pytest.ini`).
2. OR (if simpler) add a session fixture that monkeypatches the KDF to a fast stub for unit tests, keeping ONE real round-trip test for correctness.
3. Do not change production signing behaviour.
**Acceptance:** unit-suite wall-clock drops materially; signing correctness tests still pass; `make typecheck` clean.

## Batch 8 — Mark heavy ML-model tests so they can be deselected (T5)
**Skills:** `python-testing-patterns`, `test-automator`
**Depends on:** none
**Files:** `pytest.ini`; `tests/test_batch3_hardening.py`, `tests/test_reembedding_worker.py`, `tests/test_sleep_consolidation.py`, `tests/test_openvino_npu_export.py`
**Goal:** Let `pytest -m "not heavy"` skip real model loads.
**Steps:**
1. Register a `heavy` marker in `pytest.ini`.
2. Tag the model-loading tests with `@pytest.mark.heavy` (or mock the model objects if trivial).
**Acceptance:** `pytest -m "not heavy"` runs without loading SentenceTransformer/spaCy/CrossEncoder/OpenVINO; full run still includes them.

---

# PHASE C — Wire what's already built (Wave 1, trust hardening)

## Batch 9 — Register the dormant decay-prune job (Phase 1.3)
**Skills:** `async-python-patterns`, `python-pro`
**Depends on:** none
**Files:** `nce/cron.py` (`async_main`, job registrations ~`:521-606`; `startup_coros` ~`:628-639`); reference `nce/temporal_decay.py` (`register_decay_jobs:370`, `_decay_prune_tick:265`)
**Goal:** Actually schedule `phase_2_2_decay_prune`.
**Steps:**
1. `from nce.temporal_decay import register_decay_jobs` and call `register_decay_jobs(scheduler, pool)` before `scheduler.start()`.
2. Add `_decay_prune_tick(pool)` to `startup_coros`.
**Acceptance:** new integration/boot test asserts a job with id `phase_2_2_decay_prune` is present in the scheduler; lint + typecheck clean.

## Batch 10 — Config knobs for continuous chain verification (Phase 1.1a)
**Skills:** `python-pro`, `observability-engineer`
**Depends on:** none
**Files:** `nce/config.py`
**Goal:** Add the interval/depth knobs the cron tick will use.
**Steps:**
1. Add `NCE_CHAIN_VERIFY_INTERVAL_MINUTES` (default 120, min 5) and `NCE_CHAIN_VERIFY_STARTUP_DEPTH` (default 500, min 0) using the existing `_int_env` helper.
**Acceptance:** `from nce.config import cfg; cfg.NCE_CHAIN_VERIFY_INTERVAL_MINUTES` resolves; typecheck clean.

## Batch 11 — Add the continuous Merkle-chain-verification cron tick (Phase 1.1b)
**Skills:** `event-store-design`, `observability-engineer`, `async-python-patterns`
**Depends on:** Batch 10
**Files:** `nce/cron.py` (new `_chain_verification_tick`, mirror `_saga_recovery_tick:150`); `nce/db_utils.py` (`UNMANAGED_PG_AUDITED_SITES`); reference `nce/event_log.py` (`verify_merkle_chain:~1168`), `nce/observability.py` (`MERKLE_CHAIN_VALID`).
**Goal:** Run chain verification on a schedule + at startup, set the gauge, alert on failure.
**Steps:**
1. Add site string `cron.chain_verify.namespace_scan` to `UNMANAGED_PG_AUDITED_SITES`.
2. Write `_chain_verification_tick(pool)`: acquire `acquire_cron_lock("chain_verification", …)`; scan namespaces; per namespace call `verify_merkle_chain`; `MERKLE_CHAIN_VALID.set(1/0)`; on invalid → `log.critical`, dispatch an alert (Phase D dispatcher), and `append_event(event_type="chain_verification_failed", …)` (INSERT — allowed).
3. Register the job (IntervalTrigger from Batch 10 config) and add to `startup_coros`.
**Acceptance:** integration test tampers a row via a dev `NCE_BYPASS_WORM` conn, runs the tick, asserts gauge=0 + a `chain_verification_failed` event exists; clean run leaves gauge=1.

## Batch 12 — Migration: `event_log.signature_version` (Phase 1.2a)
**Skills:** `database-migration`, `postgresql`, `sql-pro`
**Depends on:** none
**Files:** new `nce/migrations/013_event_log_sig_version.sql`; mirror in `nce/schema.sql` (`event_log` DDL ~`:557-574`)
**Goal:** Back-compat hinge for binding `prev_chain_hash` into the signature.
**Steps:**
1. `ALTER TABLE event_log ADD COLUMN IF NOT EXISTS signature_version SMALLINT NOT NULL DEFAULT 1;` (valid on the partitioned table).
2. Mirror the column into `schema.sql`.
**Acceptance:** `trace_migrations.py` (or fresh `make local-up`) applies cleanly; column present; existing rows default to 1.

## Batch 13 — Sign `prev_chain_hash` in the event signature (Phase 1.2b)
**Skills:** `event-store-design`, `security-auditor`, `python-pro`
**Depends on:** Batch 12
**Files:** `nce/event_log.py` (`_build_signing_fields:539-569`, `_sign_event:804-849`, `append_event`, `_insert_event:882-914`, `verify_event_signature:1093-1170`)
**Goal:** Bind chain position into the HMAC for new (v2) rows without breaking old (v1) rows.
**Steps:**
1. `_build_signing_fields`: add optional `prev_chain_hash_hex: str | None = None`; when set, include `"prev_chain_hash"` in the dict.
2. `append_event`: move the `_fetch_previous_chain_hash` call to BEFORE `_sign_event`; pass `prev.hex()` through `_sign_event` → `_build_signing_fields`.
3. `_sign_event`: add the param and thread it.
4. `_insert_event`: write `signature_version = 2` for new rows.
5. `verify_event_signature`: branch on `record["signature_version"]` — v2 rebuilds fields WITH `prev_chain_hash` (fetch the immediately-lower `event_seq` row's `chain_hash`), v1 rebuilds WITHOUT.
**Acceptance:** integration test: append events (now v2), verify they pass; reorder/tamper a row and confirm v2 `verify_event_signature` fails; pre-existing v1 rows still verify.

## Batch 14 — Integration tests for chain + decay wiring (Phase 3 slice)
**Skills:** `python-testing-patterns`, `test-automator`, `event-store-design`
**Depends on:** Batches 9, 11, 13
**Files:** new `tests/test_chain_and_decay_integration.py`
**Goal:** Lock the Wave-1 wiring.
**Steps:**
1. `test_chain_tamper_detection_integration` (tamper → `verify_merkle_chain` valid=False, correct `first_break`).
2. `test_decay_job_scheduled` (job id present; a boot run soft-deletes a faded row).
**Acceptance:** `pytest -m integration tests/test_chain_and_decay_integration.py` green.

---

# PHASE D — Make failure visible (Wave 2: III.1 alerting, III.4 health, III.3 metrics)

## Batch 15 — Route DLQ exhaustion to the alert dispatcher (III.1a)
**Skills:** `incident-responder`, `observability-engineer`, `python-pro`
**Depends on:** none
**Files:** `nce/dead_letter_queue.py` (~`:236`); reference `nce/notifications.py` (`NotificationDispatcher.dispatch_alert`)
**Goal:** Operators learn about poisoned tasks by notification, not polling.
**Steps:** On DLQ write, call `dispatch_alert(...)` with task name, job id, error. Fail-safe: alert failure must not raise into the caller.
**Acceptance:** unit test asserts `dispatch_alert` is invoked when a task is dead-lettered.

## Batch 16 — Route cron-tick + outbox failures to alerts (III.1b)
**Skills:** `incident-responder`, `observability-engineer`
**Depends on:** Batch 15
**Files:** `nce/cron.py` (`_CRON_TICK_ERRORS` handlers), `nce/outbox_relay.py` (~`:183`)
**Goal:** Failed syncs/relays alert.
**Steps:** In the existing exception handlers, add a throttled `dispatch_alert`. Do not change control flow.
**Acceptance:** unit test simulates a tick failure and asserts an alert is dispatched.

## Batch 17 — Deepen health checks (III.4)
**Skills:** `observability-engineer`, `slo-implementation`, `security-auditor`
**Depends on:** Batch 11
**Files:** locate `check_health` (health probe / admin health); `nce/signing.py` (`require_master_key`), `nce/event_log.py` (`verify_merkle_chain`)
**Goal:** `/health` reflects signing + chain + RLS readiness, not just DB up.
**Steps:** Add three probes — (a) decrypt the active signing key, (b) verify a bounded chain sample, (c) a sample RLS-scoped read. Set `MERKLE_CHAIN_VALID` here too.
**Acceptance:** test: with a broken master key, health reports unhealthy even though DBs are up.

## Batch 18 — Instrument the saga write path (III.3a)
**Skills:** `distributed-tracing`, `observability-engineer`, `saga-orchestration`
**Depends on:** none
**Files:** `nce/orchestrators/memory.py` (`_run_store_memory_saga`); reference `SagaMetrics`
**Goal:** Saga latency/success metrics emitted by default.
**Steps:** Wrap the store_memory saga with the existing `SagaMetrics` (make it non-opt-in for this path).
**Acceptance:** test asserts saga metric increments on success and failure.

## Batch 19 — Quota + embedding-fallback metrics & alert (III.3b, closes N-D)
**Skills:** `observability-engineer`, `prometheus-configuration`
**Depends on:** Batch 15
**Files:** `nce/quotas.py`; `nce/embeddings.py` (degraded fallback path)
**Goal:** No silent quota/quality degradation.
**Steps:** Add `nce_quota_consumed_total` / `nce_quota_remaining` gauges; increment an `EMBEDDING_FALLBACKS` counter and `dispatch_alert` when the sidecar fallback (hash-stub) triggers.
**Acceptance:** test: forcing the embedding fallback increments the counter and alerts.

---

# PHASE E — Network & ingestion resilience (III.7, III.6) — small, high-value

## Batch 20 — Add timeouts to all NetBox clients (N-B, unbounded-hang fix)
**Skills:** `network-engineer`, `backend-security-coder`, `async-python-patterns`
**Depends on:** none
**Files:** `nce/vertical_modules/netbox/circuits.py:46`, `contacts.py:46,55`, `discovery.py:128,309`, `graphql_activation.py:135`
**Goal:** No `httpx.AsyncClient()` without a timeout.
**Steps:** Add an explicit `timeout=httpx.Timeout(30.0)` (or config) to every NetBox `httpx.AsyncClient(...)`.
**Acceptance:** grep shows no timeout-less `httpx.AsyncClient(` in `vertical_modules/netbox/`; unit test asserts a slow endpoint raises a timeout, not a hang.

## Batch 21 — Route the embedding sidecar + D365/NetBox HTTP through the resilience helper (N-A/N-C)
**Skills:** `microservices-patterns`, `error-handling-patterns`, `async-python-patterns`
**Depends on:** Batch 20
**Files:** `nce/embeddings.py` (`:528,559`), `nce/vertical_modules/dynamics365/client.py:161`, `netbox_bridge.py:100`; reuse `nce/http_resilience.py` (`request_with_retry`)
**Goal:** Retry + backoff (and breaker where available) on the hot embedding path and D365/NetBox calls.
**Steps:** Wrap these raw `httpx` calls with `http_resilience.request_with_retry`. Keep the existing degraded fallback as the final resort after retries.
**Acceptance:** test: a transient 503 from the sidecar is retried then succeeds; a sustained outage fast-fails without piling up.

## Batch 22 — Close the SSRF TOCTOU + pin extractor binaries (III.6)
**Skills:** `backend-security-coder`, `security-auditor`
**Depends on:** none
**Files:** `nce/net_safety.py` (~`:199`, `validate_extractor_url`/`validate_webhook_payload_url`); `nce/extractors/project_ext.py` (MPXJ), `nce/extractors/libreoffice.py` (soffice)
**Goal:** Resolve-once-connect-to-that-IP; pin binaries by path+hash.
**Steps:** Add an IP-pinned httpx resolver (resolve once, connect to the pinned IP); pin MPXJ/soffice by absolute path + hash.
**Acceptance:** test: a DNS-rebinding mock cannot redirect the fetch to a private IP after validation.

---

# PHASE F — Activate the cognitive layer (Wave 3)

## Batch 23 — ATMS cascade on contradiction resolution (Phase 4.1)
**Skills:** `event-sourcing-architect`, `postgresql`, `architect-review`
**Depends on:** Batch 4 (replay sane), Batch 13 (signed chain)
**Files:** `nce/orchestrators/cognitive.py` (`resolve_contradiction:161-219`); reuse `nce/atms.py` (`evaluate_atms_intervention`, `persist_atms_invalidation`), `nce/consolidation.py` (`derived_from`)
**Goal:** Resolving a contradiction deprecates the losing memory + dependents.
**Steps:**
1. After the existing `UPDATE … RETURNING` + `append_event`, inside a nested `SAVEPOINT` (so ATMS failure can't abort resolution), map resolution → loser (`accepted_a`→b, `accepted_b`→a, `superseded`/`rejected`→rejected side, `false_positive`/`duplicate`→no cascade).
2. Call `evaluate_atms_intervention` then `persist_atms_invalidation`; `append_event(event_type="atms_cascade", …)`. Add a `max_cascade` guard.
**Acceptance:** integration test: resolve `accepted_a` → losing memory + `derived_from` dependents get `valid_to` set; an `atms_cascade` event exists.

## Batch 24 — Expose `neuromorphic_search` as an MCP tool (Phase 4.3)
**Skills:** `rag-engineer`, `api-endpoint-builder`, `python-pro`
**Depends on:** none
**Files:** `nce/graph_mcp_handlers.py` (new handler), `nce/tool_registry.py`, `nce/mcp_stdio_tools.py`; reuse `GraphRAGTraverser.neuromorphic_search` (`nce/graph_query.py`); update `tests/test_tool_registry.py` counts.
**Goal:** Make spiking-activation search callable.
**Steps:** Add a `neuromorphic_search` tool (cacheable) → handler calls `neuromorphic_search`; register in `tool_registry.py`; declare schema in `mcp_stdio_tools.py`; bump `_EXPECTED_TOTAL` + cacheable count.
**Acceptance:** `tests/test_tool_registry.py` passes with new counts; an MCP call returns a subgraph.

## Batch 25 — Wire do-calculus circuit escalation (Phase 4.2)
**Skills:** `architect-review`, `python-pro`, `api-endpoint-builder`
**Depends on:** Batch 24 pattern
**Files:** `nce/vertical_modules/netbox/circuits.py` (`evaluate_and_escalate`), `nce/vertical_modules/dynamics365/ingestion.py` (SLA-breach path); new MCP tool `evaluate_circuit_impact` (registry + stdio decl); update tool counts.
**Goal:** Give the orphan escalator a live path, guarded on NetBox creds.
**Steps:** On D365 `sla_breach` + impacted services, build `degradations` and call the escalator inside a `scoped_pg_session`; persist tickets as `append_event(event_type="circuit_escalation_generated", …)`. Add the on-demand MCP tool. No-op when `NCE_NETBOX_URL`/`TOKEN` unset.
**Acceptance:** integration test with NetBox creds set: an SLA breach yields `circuit_escalation_generated` events; the tool returns ranked impacts.

---

# PHASE G — Disaster recovery (Wave 4)

## Batch 26 — Snapshot import / restore (III.2)
**Skills:** `saga-orchestration`, `database-architect`, `python-pro`
**Depends on:** Batch 4
**Files:** new logic in `nce/snapshot_mcp_handlers.py` (mirror `stream_snapshot_export:88-312`); registry + stdio decl; update tool counts.
**Goal:** Rebuild a namespace from an exported NDJSON snapshot via the Saga path.
**Steps:** Add `import_snapshot` / `restore_namespace` that ingests the NDJSON back through the Saga write path. Reuse deterministic remap once Phase H lands (until then, document non-verifiable restore).
**Acceptance:** integration test: export ns A → import into ns B → row counts/types match.

---

# PHASE H — Verified byte-identical replay (Wave 5, heavy)

## Batch 27 — Deterministic identity remap (uuid5) in replay (Phase 2.1)
**Skills:** `event-sourcing-architect`, `python-pro`, `architect-review`
**Depends on:** Batch 4
**Files:** `nce/replay.py` (`_dispatch_and_apply_event:~1113`, `HandlerFn` protocol `:455`, `_handle_store_memory`, `_handle_consolidation_run`)
**Goal:** Repeatable target IDs.
**Steps:** Introduce a `ReplayContext` carrying `uuid_remap: dict[UUID, UUID]` + `remap(src)->uuid5(target_ns, str(src))`; replace `uuid.uuid4()` in the handlers with `ctx.remap(...)`. Add deterministic `event_id` (`uuid5(target_ns, source_event_id)`) param to `append_event`/`_insert_event`.
**Acceptance:** test: reconstruct twice → identical target UUIDs.

## Batch 28 — Payload copy strategy (Phase 2.1b)
**Skills:** `nosql-expert`, `python-pro`
**Depends on:** Batch 27
**Files:** `nce/replay.py` (payload handling)
**Goal:** True isolation between source/target Mongo docs.
**Steps:** Copy the Mongo doc to a fresh deterministic ObjectId (derived from uuid5); set target `payload_ref` to the copy. Digest (Batch 30) compares a content hash, not the ref string.
**Acceptance:** test: source and target have distinct `payload_ref`s pointing at equal content.

## Batch 29 — Faithful timestamps with mandatory re-sign (Phase 2.2)
**Skills:** `event-store-design`, `security-auditor`
**Depends on:** Batch 13, Batch 27
**Files:** `nce/event_log.py` (`append_event`), `nce/replay.py` (handlers)
**Goal:** Preserve source `occurred_at`/`valid_from` deterministically.
**Steps:** Add a replay-only `replay_occurred_at: datetime | None` to `append_event`, applied BEFORE `_sign_event` (so the signature covers the overridden value). Gate: ignored unless caller is the replay engine in deterministic mode. Handlers insert source `valid_from`.
**Acceptance:** test: replayed event carries source timestamp AND verifies (signature recomputed over it).

## Batch 30 — Namespace state-digest + equality gate (Phase 2.3)
**Skills:** `event-sourcing-architect`, `data-quality-frameworks`, `database-migration`
**Depends on:** Batches 28–29
**Files:** new `nce/state_digest.py`; migration `0NN_replay_runs_digest.sql` + schema mirror (`replay_runs` add `source_state_digest TEXT, target_state_digest TEXT, digest_match BOOLEAN`); `nce/replay.py` (`ReconstructiveReplay.execute`, `replay_status`)
**Goal:** Earn the "byte-identical" claim.
**Steps:** `compute_namespace_state_digest(conn, ns, *, as_of=None)` = SHA-256 over a canonical sorted projection of durable, deterministic state (memories: remap-normalized id, agent_id, created_at, types, valid_*, derived_from, metadata, **content-hash of payload** — exclude signature/fts/embedding; kg labels/predicate/confidence — exclude updated_at; EXCLUDE memory_salience). Compare source@end vs target; store both + `digest_match`.
**Acceptance:** integration test: `compute_namespace_state_digest(source) == (target)` and `replay_runs.digest_match is True`.

---

# PHASE I — Admin control plane foundation (V-a) — unblocks UI-driven config

## Batch 31 — `settings` table migration (V.1a)
**Skills:** `database-migration`, `postgresql`, `secrets-management`
**Depends on:** none
**Files:** new migration + `schema.sql`
**Goal:** DB-backed runtime settings.
**Steps:** `settings(key TEXT PK, value JSONB NULL, secret_enc BYTEA NULL, is_secret BOOL, section TEXT, updated_by TEXT, updated_at TIMESTAMPTZ)`. Admin-namespace / RLS-exempt as designed.
**Acceptance:** migration applies; table present.

## Batch 32 — `SettingsStore` accessor with precedence + cache (V.1b)
**Skills:** `backend-architect`, `python-pro`, `secrets-management`
**Depends on:** Batch 31
**Files:** new `nce/settings_store.py`
**Goal:** `cfg.get(key)` → env default < store override; secrets encrypted via `encrypt_signing_key`; short-TTL cache + Redis pub/sub invalidation (reuse the `nce:tools:disabled` pattern).
**Steps:** Implement get/set/reset; secrets write-only (never returned). **Never store `NCE_MASTER_KEY`.**
**Acceptance:** unit test: env default returned when unset; store override wins; secret round-trips encrypted and is never returned in plaintext.

## Batch 33 — Settings registry metadata (V.1a)
**Skills:** `backend-architect`, `api-design-principles`
**Depends on:** Batch 32
**Files:** new `nce/settings_registry.py`
**Goal:** One metadata entry per setting (`key, section, type, reload_class HOT/WARM/COLD, is_secret, prod_locked, validator`) driving both API and UI.
**Steps:** Seed the ~22 sections from plan V.1a; mark guardrail keys `prod_locked` (`NCE_BYPASS_WORM`, `NCE_BYPASS_RLS`, `NCE_ADMIN_OVERRIDE`, `NCE_LOAD_DOTENV`, dotenv-persist) and `NCE_MASTER_KEY` as never-UI-editable.
**Acceptance:** unit test: every registry entry has a validator; prod_locked keys flagged.

## Batch 34 — `GET /api/admin/settings` (+ `/effective`, `/{key}`) (V.1b)
**Skills:** `fastapi-pro`, `api-endpoint-builder`, `api-documentation`
**Depends on:** Batch 33
**Files:** `nce/admin_app.py` (routes), `nce/admin_handlers/` (new settings handler)
**Goal:** Read settings grouped by section, secrets masked.
**Steps:** Implement the three GET endpoints from plan V.1b, secrets shown as `"••••set"`.
**Acceptance:** HMAC-signed GET returns sections; secrets masked; test passes.

## Batch 35 — `PATCH /api/admin/settings` (207) + `config_changed` WORM event (V.1b/V.5)
**Skills:** `fastapi-pro`, `security-auditor`, `event-store-design`
**Depends on:** Batch 34
**Files:** settings handler; reuse `append_event`
**Goal:** Batch apply with per-key status; audited; guardrails enforced server-side.
**Steps:** Implement per-key `applied | pending_reload | pending_restart | rejected` (prod_locked→403-class, validation→422, stale `expected_updated_at`→409). Append a signed `config_changed` event (secrets redacted to set/unset).
**Acceptance:** test: HOT key applies live; prod_locked key rejected; a `config_changed` event is written with secrets redacted.

## Batch 36 — `/reset`, `/reload`, `/pending` endpoints (V.1b)
**Skills:** `fastapi-pro`, `api-endpoint-builder`
**Depends on:** Batch 35
**Files:** settings handler; `nce/cron.py` (reschedule on cron-domain reload), `nce/providers/factory.py` (llm rebuild)
**Goal:** WARM reloads + restart-pending visibility.
**Steps:** Implement reset (clear override), reload (run WARM domain handlers: cron reschedule, llm rebuild, observability re-init, a2a refresh), pending (keys needing restart).
**Acceptance:** test: a WARM cron-interval change + `/reload {domains:["cron"]}` reschedules jobs.

---

# PHASE J — Accountable memory (Wave 6)

## Batch 37 — Honest Uncertainty in search results (II.1)
**Skills:** `rag-engineer`, `python-pro`
**Depends on:** none
**Files:** `nce/semantic_search.py` (project existing `raw_salience`/`last_updated`), `handle_semantic_search` serialization; reuse `nce/temporal_decay.py` retention math.
**Goal:** Return `salience_score`, `last_reinforced_at`, derived `confidence` + `stale` flag.
**Acceptance:** test: a 3-month-unreinforced memory returns low confidence + `stale=true`.

## Batch 38 — Epistemic Receipts (II.2)
**Skills:** `event-sourcing-architect`, `api-endpoint-builder`, `security-auditor`
**Depends on:** Batch 13
**Files:** `nce/replay.py` (`get_event_provenance:~1575-1640`), admin route; new MCP tool `explain_memory` (registry + stdio decl + counts)
**Goal:** Cryptographically checkable provenance.
**Steps:** Include `signature` + a `verified` boolean (run `verify_event_signature`) in the provenance response; add the client-facing `explain_memory(memory_id)` tool returning the signed receipt.
**Acceptance:** test: `verified` flips to false when the underlying event row is tampered.

## Batch 39 — Subject-scoped `/api/me/*` surface (cross-cutting enabler)
**Skills:** `fastapi-pro`, `backend-security-coder`, `saas-multi-tenant`
**Depends on:** none
**Files:** new `/api/me` app/routes; reuse `scoped_pg_session` pinned to caller's own namespace/agent
**Goal:** A consent-bound read/govern surface distinct from admin.
**Acceptance:** test: caller can only read their own namespace; cross-namespace request is denied.

## Batch 40 — Glass Profile endpoint + retract→ATMS (II.3)
**Skills:** `rag-engineer`, `fastapi-pro`, `event-sourcing-architect`
**Depends on:** Batch 23 (ATMS), Batch 39
**Files:** `/api/me/profile` (or admin subject-profile); govern path
**Goal:** Show all beliefs + edit/downweight/pin/retract (retract → ATMS cascade).
**Acceptance:** test: retract → memory + `derived_from` dependents soft-deleted; profile reflects it.

## Batch 41 — Accountable Federation: write `a2a_shared_query` + signed provenance (II.6)
**Skills:** `event-sourcing-architect`, `security-auditor`, `api-design-principles`
**Depends on:** Batch 13
**Files:** `nce/a2a.py` (NOTE: real module — NOT `a2a_server.py`); `nce/a2a_mcp_handlers` if present; `a2a_grants` (add `can_delegate BOOLEAN` via migration)
**Goal:** Owner can see who read what; consumer can attribute; no transitive re-grant.
**Steps:** Append a signed `a2a_shared_query` event on every verified skill call (consumer ns/agent, grant_id, query); return owner's original signature + key id alongside shared memories; add `can_delegate` column + enforcement.
**Acceptance:** test: a shared query writes one `a2a_shared_query` event; a non-delegable grant can't re-grant.

## Batch 42 — A2A security hardening (III.5)
**Skills:** `backend-security-coder`, `security-auditor`, `api-security-best-practices`
**Depends on:** none
**Files:** `nce/a2a.py` / A2A request path; `nce/config.py`
**Goal:** Rate-limit, one-time grants, mandatory audience.
**Steps:** Sliding-window limiter on `tasks/send`; optional `one_time` grant mode (usage counter in `verify_token`); make `NCE_A2A_JWT_AUDIENCE` mandatory in prod `config.validate()`.
**Acceptance:** tests for each: limiter trips; one-time grant rejects 2nd use; prod boot fails without audience.

## Batch 43 — Bi-temporal "explain my past decision" (II.5)
**Skills:** `event-sourcing-architect`, `rag-engineer`
**Depends on:** Phase H (verified replay)
**Files:** new MCP tool `explain_past_decision(as_of)` (registry + stdio + counts); Glass Profile timeline view
**Goal:** Reconstruct belief state + valid receipts at time T via verified forked replay.
**Acceptance:** test: `explain_past_decision(as_of=T)` returns the belief set valid at T; counterfactual fork is `digest_match`-verified.

---

# PHASE K — Provable Forgetting (Wave 7, flagship; ship last of the memory work)

## Batch 44 — DECISION + content-free WORM log fork (R2 / VII.5)
**Skills:** `gdpr-data-handling`, `privacy-by-design`, `architect-review`
**Depends on:** none (do FIRST in this phase)
**Files:** `nce/orchestrators/memory.py` (`append_event` params `:325-338`; `saga_execution_log` payload `:357-363`)
**Goal:** Stop new content/PII entering immutable logs.
**Steps:** Change `store_memory` to log entity/triplet **counts or hashes** (not strings) in `event_log.params`; sanitize the summary in `saga_execution_log.payload` (or store a ref) so pre-redaction PII is not persisted. (If product opts for honest-scope instead, document the scope precisely.)
**Acceptance:** test: injecting a known PII string yields no plaintext fragment in `event_log.params` or `saga_execution_log.payload`.

## Batch 45 — Envelope-encryption subsystem (II.4a)
**Skills:** `security-auditor`, `secrets-management`, `python-pro`
**Depends on:** none
**Files:** new `nce/envelope.py`; reuse `nce/signing.py` (`encrypt_signing_key`/`decrypt_signing_key`, `SecureKeyBuffer`); migration: `memories.wrapped_dek BYTEA`, `dek_key_id`
**Goal:** Per-memory (or per-subject) DEK lifecycle.
**Acceptance:** unit test: DEK wrap/unwrap round-trips; destroying the DEK makes ciphertext undecryptable.

## Batch 46 — Encrypt `episodes.raw_data` under the DEK + teach read paths (II.4b)
**Skills:** `nosql-expert`, `security-auditor`, `python-pro`
**Depends on:** Batch 45
**Files:** `nce/orchestrators/memory.py` (write); read paths: `semantic_search`, `recall_recent`, `verify_memory`, `unredact_memory`, `search_codebase`, snapshot export, replay
**Goal:** Raw content encrypted at rest; hydration decrypts.
**Acceptance:** integration test: stored raw_data is ciphertext at rest; reads transparently decrypt.

## Batch 47 — `shred_memory` / `forget_subject` + deletion receipt (II.4c)
**Skills:** `gdpr-data-handling`, `security-auditor`, `event-sourcing-architect`
**Depends on:** Batches 23, 44, 46
**Files:** new tool (registry + stdio + counts); orchestrates DEK destroy → delete content_fts/embeddings → ATMS-cascade KG labels/edges + derived → delete pii_redactions → purge Redis key → MinIO `remove_object` → append signed `memory_shredded` (refs only) → return receipt.
**Acceptance:** completeness integration test: after shred, **no plaintext fragment survives in ANY store** (Mongo undecryptable, FTS empty, embeddings gone, KG labels gone, Redis/MinIO purged, event_log holds only refs); signed `memory_shredded` + verifiable receipt exist.

## Batch 48 — DSAR capstone (VII.7)
**Skills:** `gdpr-data-handling`, `privacy-by-design`, `api-endpoint-builder`
**Depends on:** Batches 40, 47
**Files:** compose Glass Profile (export) + shred (erase) into a `/api/me` DSAR flow
**Goal:** Export-everything-then-forget-with-proof.
**Acceptance:** test: DSAR export then erase leaves no plaintext fragment (reuses Batch 47 test).

---

# PHASE L — Content-surface isolation (Part VII)

## Batch 49 — Verify PII-before-derivation on every write path (VII.1)
**Skills:** `privacy-by-design`, `security-auditor`, `gdpr-data-handling`
**Depends on:** none
**Files:** audit `store_memory`, consolidation, code indexing, bridge ingestion
**Goal:** Confirm sanitize precedes embed + KG extract everywhere.
**Acceptance:** test on each write path: a known PII string appears only pseudonymized in fts/KG/embeddings/event_log; reversible original only in `pii_redactions`.

## Batch 50 — Scoped MongoDB accessor (VII.2)
**Skills:** `nosql-expert`, `saas-multi-tenant`, `backend-security-coder`
**Depends on:** none
**Files:** new scoped Mongo accessor (analogous to `scoped_pg_session`); refactor episode reads/writes to use it
**Goal:** Structural namespace injection, not per-call discipline.
**Acceptance:** test: a query missing the namespace filter is rejected/auto-scoped.

## Batch 51 — MinIO per-namespace isolation (VII.3)
**Skills:** `backend-security-coder`, `cloud-architect`
**Depends on:** none
**Files:** MinIO object naming/policies in `nce/orchestrators/memory.py` / `nce/storage.py`
**Goal:** Per-namespace key prefixes + scoped/expiring presigned URLs.
**Acceptance:** test: object names carry the namespace prefix; cross-tenant fetch denied.

---

# PHASE M — Admin panel UI + config time-travel (V-b, V-c)

## Batch 52 — Auto-generated Settings panel (V.3)
**Skills:** `frontend-developer`, `tailwind-patterns`, `ui-ux-designer`
**Depends on:** Batch 36
**Files:** `admin/index.html` (new `settingsPanel` Alpine component, mirror d365 panel pattern, `signedFetch`)
**Goal:** Render the registry by section with type-aware inputs + source/reload-class badges.
**Acceptance:** panel loads from `/api/admin/settings`; secrets masked; manual smoke check documented.

## Batch 53 — Settings interaction design (V.3a)
**Skills:** `frontend-developer`, `ui-ux-designer`
**Depends on:** Batch 52
**Files:** `admin/index.html` settings component
**Goal:** Dirty-tracking + batch apply + confirm-diff modal; render 207 per-key statuses; 409 conflict flow; secret rotate/clear; prod-locked disabled.
**Acceptance:** manual smoke: edit → review-diff → apply shows correct per-key states.

## Batch 54 — `config_changed` time-travel + rollback (V.6)
**Skills:** `event-sourcing-architect`, `fastapi-pro`, `api-endpoint-builder`
**Depends on:** Batches 35, 13
**Files:** `GET /api/admin/settings/effective?as_of=T`; `POST /api/admin/settings/rollback`; MCP `explain_config_change(key)`
**Goal:** Reconstruct effective config at T; rollback as a confirmed PATCH batch.
**Acceptance:** test: `effective?as_of=T` reconstructs past config; `rollback {dry_run:true}` returns correct inverse diff; prod-locked skipped; rotated-since-T secrets flagged.

---

# PHASE N — Deployment, infra, resource utilization (Part VI)

## Batch 55 — Secrets-manager seam + remove dev dotenv-persist in prod (VI.1)
**Skills:** `secrets-management`, `deployment-engineer`, `security-auditor`
**Depends on:** none
**Files:** `scripts/bootstrap-compose-secrets.py`, deploy docs, `nce/config.py`
**Goal:** Prod secrets from a real manager; `NCE_MASTER_KEY` manager-only.
**Acceptance:** doc + seam; no plaintext secret in any prod compose file; test/boot-guard for prod.

## Batch 56 — Resolve `nce_gc` least-privilege (R4 / VI.4)
**Skills:** `database-architect`, `security-auditor`, `postgresql`
**Depends on:** none
**Files:** `nce/garbage_collector.py`, `nce/reembedding_worker.py`, `nce/config.py` (add `NCE_GC_DSN`), `nce/db_utils.py`; docs `database_architecture.md:110`, `enterprise_security.md:158`
**Goal:** Either make workers connect as `nce_gc` (separate creds, LOGIN) OR remove the dormant role and correct the docs. (Pick per architect note; default: implement segregation.)
**Acceptance:** test: GC/re-embed connect with the GC DSN; app pool never holds BYPASSRLS; docs match reality.

## Batch 57 — Mongo write durability for the saga (R-A / VI.6a)
**Skills:** `nosql-expert`, `saga-orchestration`, `database-architect`
**Depends on:** none
**Files:** `nce/orchestrator.py` (`AsyncIOMotorClient` ~`:129`) or the episodes write in `nce/orchestrators/memory.py`
**Goal:** A Mongo ack means journaled-to-disk before PG commits the reference.
**Steps:** Set `w="majority", j=True` on the saga episodes write (scope to that write to limit latency cost).
**Acceptance:** test/doc: power-loss window can't leave a committed PG row pointing at an unjournaled Mongo doc.

## Batch 58 — Reverse-orphan reconciliation sweep (R-B / VI.6a)
**Skills:** `database-architect`, `incident-runbook-templates`, `python-pro`
**Depends on:** Batch 15
**Files:** `nce/garbage_collector.py` (add a reverse pass)
**Goal:** Detect PG memories whose Mongo doc is missing.
**Steps:** Sweep `memories.payload_ref` with no Mongo doc → soft-retire (`valid_to=now()`) + alert (and optionally flag for replay rebuild).
**Acceptance:** integration test: a deliberately-missing Mongo doc → its PG memory is flagged/soft-retired + alert dispatched.

## Batch 59 — RQ in-flight job recovery (R-C / VI.6a)
**Skills:** `incident-responder`, `async-python-patterns`, `deployment-engineer`
**Depends on:** none
**Files:** `start_worker.py`
**Goal:** Jobs running at crash time get requeued.
**Steps:** Run RQ with the scheduler / a periodic `StartedJobRegistry` cleanup that requeues abandoned jobs; set `failure_ttl`/`result_ttl`. Document safe-to-lose vs must-requeue classes.
**Acceptance:** test/doc: a killed worker's in-flight job is requeued, not lost.

## Batch 60 — Multicore: HTTP workers + RQ replicas + thread pinning (VI.5a)
**Skills:** `deployment-engineer`, `docker-expert`, `performance-engineer`
**Depends on:** none
**Files:** `docker-compose.yml` (admin/a2a/webhook commands; worker replicas; env)
**Goal:** Use more than one core.
**Steps:** Add `--workers N` (or replicas behind Caddy) to admin/a2a/webhook (NOT the MCP stdio process); run N `worker` replicas (cron stays 1); pin `OMP_NUM_THREADS`/`MKL_NUM_THREADS`/`TOKENIZERS_PARALLELISM` to CPU quota.
**Acceptance:** on a multi-core host, services saturate >1 core; cron stays singleton.

## Batch 61 — RAM: offload spaCy + NLI to a sidecar; container mem limits (VI.5b)
**Skills:** `performance-engineer`, `deployment-engineer`, `ml-engineer`
**Depends on:** Batch 60
**Files:** embedding/NLP load paths; `docker-compose.yml`
**Goal:** Stop every worker holding ~0.5–1 GB of NLP models; set mem limits.
**Acceptance:** worker RSS drops materially after offload; per-service mem limits enforced.

## Batch 62 — Disk: datastore tuning + halfvec + tmpfs temp (VI.5c)
**Skills:** `postgresql-optimization`, `vector-index-tuning`, `database-optimizer`
**Depends on:** none; **reconcile with Batch 18-equivalent vector-compliance work first**
**Files:** `docker-compose.yml` (PG/Mongo/Redis commands), `nce/schema.sql` (vector → `halfvec(768)`), tempfile dir → tmpfs
**Goal:** Tune WAL/compression; halve vector+index size; remove extractor disk I/O.
**Acceptance:** vector+index on-disk size ~halves; WAL/checkpoint metrics improve; extractor runs produce no real-disk writes.

---

# PHASE O — Retrieval quality (Wave 8, optional, last)

## Batch 63 — Cross-encoder reranking (IV.1)
**Skills:** `rag-engineer`, `hybrid-search-implementation`, `embedding-strategies`
**Depends on:** Batch 37
**Files:** `nce/semantic_search.py` (optional rerank pass over fused top-N; reuse the NLI cross-encoder)
**Goal:** Learned relevance over the RRF-fused candidates.
**Acceptance:** test: rerank changes ordering sensibly; reranker score surfaced as a confidence signal.

## Batch 64 — Multi-vector / aspect embeddings (IV.2)
**Skills:** `vector-database-engineer`, `embedding-strategies`, `database-migration`
**Depends on:** Batch 62
**Files:** `embedding_aspects` companion + migration; reuse `nce/reembedding_migration.py` machinery
**Goal:** Asymmetric retrieval (code-intent vs NL-intent).
**Acceptance:** test: query code-intent matches code vectors; quality gate (Jaccard neighbor-overlap) passes.

---

## Final note for the executor
- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch NN — <name>`, paste the gate output, and wait for review.
- Batches within the same phase that say **Depends on: none** may be parallelized across people, but still merge in numeric order.
