# NCE — Hardening & Innovation Master Plan

> **Status:** Planning only. **Nothing here is built.** All work is deferred until Gemini's 20-batch RL sequence completes; the first action is then a **Wave 0 re-audit** against the final tree (line numbers and gaps will have drifted). This document spans seven parts (I–VII) and ends with a single dependency-ordered **Master Execution Sequence**.

## Executive summary

**Thesis.** NCE's *isolation* is genuinely strong (forced RLS, startup catalog check). Its *auditability/reproducibility* guarantees are architecturally real but **not wired shut**, and ~40% of the advertised *cognitive* layer is orphan code with zero callers. The system's signature failure mode is **"built but never wired"** — a verifier defined but never called, a decay job never registered, an alert dispatcher barely used, a `MERKLE_CHAIN_VALID` gauge never set, an `a2a_shared_query` audit event never written, export without import. The upside of that framing: **NCE is roughly one disciplined integration pass away from being dramatically more trustworthy than it currently looks.** The product north-star this unlocks: *the first LLM memory that is accountable to the person it remembers — it can prove why it believes something, show you everything it believes, forget on demand with a receipt, and admit when it's unsure.*

**The seven parts.**
- **I — Trust hardening:** wire the dormant guarantees (continuous chain verification, sign `prev_chain_hash`, register the decay job), make replay *verifiably* byte-identical, add integration tests that actually prove the storage claims, and activate the orphan cognitive modules (ATMS, do-calculus, spiking search).
- **II — Accountable memory (+ II.6 federation):** Honest Uncertainty, Epistemic Receipts, the Glass Profile, Provable Forgetting, Bi-temporal Accountability, and cross-agent access receipts/provenance.
- **III — Operability:** route failures to alerts, snapshot **import**/DR, close metrics blind-spots, deepen health checks, A2A + ingestion hardening.
- **IV — Retrieval quality (optional):** cross-encoder reranking, multi-vector embeddings.
- **V — Admin control plane:** a runtime `SettingsStore` + auto-generated panel so the whole system is configurable from the page (no `.env` editing), with config changes living on the WORM timeline (config time-travel/rollback).
- **VI — Deployment/infra:** secrets-manager, least-privilege roles, HA, DR, air-gapped profile, supply chain.
- **VII — Content-surface (PII & isolation):** minimize the content leak surface, make Mongo/MinIO isolation structural, and compose II.3+II.4+VII into a real DSAR/right-to-be-forgotten capability.

**Cross-cutting theme.** A memory's content fans out across many stores (Mongo `raw_data`, FTS tsvector, embeddings, KG labels, Redis, MinIO, and WORM entities/triplets). This one fact drives Provable Forgetting (II.4), the replay state-digest (Phase 2.3), and the PII/isolation pass (VII).

## Risk register — the handful of true blockers & gates (verify FIRST)

> **Wave 0 status (audited against the FINAL post-Gemini tree, 20/20 — see "Wave 0 results" below).** R1 **CONFIRMED OPEN** (replay is broken today, not a stale read). R2 **CONFIRMED** (+ new: saga log holds pre-redaction PII). R3 **CONFIRMED safe** (env-only; no SettingsStore exists yet). R4 **NOT confirmed** — `nce_gc` is dormant; workers run as `nce_app`. R5 reconciled.

| # | Gate / risk | Where | Why it matters |
| :--- | :--- | :--- | :--- |
| R1 | **CONFIRMED OPEN — replay handlers reference absent columns** (`memories.summary`/`salience` don't exist; salience is `memory_salience.salience_score`) **and omit NOT-NULL `payload_ref`** | Part I Phase 2.0 | `_handle_store_memory` (`replay.py:509-555`), `_handle_consolidation_run` (`:704-733`), `_handle_boost_memory` (`:614`) fail at runtime → reconstructive/forked replay is **broken today**. Hard-blocks Phase 2 / Wave 5 / II.5 until handlers are fixed (join `memory_salience`; set `payload_ref` from event params). `_handle_forget_memory` is OK. |
| R2 | **CONFIRMED — content/PII in the immutable WORM log** | II.4 + VII.1 + VII.5 | `store_memory` `append_event` (`orchestrators/memory.py:325-338`) writes `entities`+`triplets` (content-derived) into immutable `event_log.params`. **NEW:** `saga_execution_log.payload` (`:357-363`) stores the **un-sanitized** plaintext `summary` (written before PII redaction at `:739`) — raw PII in a (deletable, but currently un-purged) table. Decide content-free-log fork **and** sanitize/purge the saga log. |
| R3 | **CONFIRMED safe — `NCE_MASTER_KEY` is secret-manager-only** | Part V.1 / VI.1 | Env-only (`config.py:404`, `signing.py:287`); never DB-stored or endpoint-returned. **No SettingsStore exists yet** — risk is purely forward-looking: V.1 must never persist it. |
| R4 | **NOT confirmed — `nce_gc` least-privilege is aspirational** | VI.4 | `nce_gc` is `BYPASSRLS NOLOGIN` (`schema.sql:24-28`) but **no worker connects as it** — GC/re-embed/cron/app all use `cfg.PG_DSN` (=`nce_app`); no `NCE_GC_DSN`. `unmanaged_pg_connection` is the app role skipping `SET LOCAL`, not a distinct principal. Docs (`database_architecture.md:110`, `enterprise_security.md:158`) are **inaccurate**. VI.4 shifts from "verify" → "implement nce_gc segregation **or** remove the dormant role + fix docs." |
| R5 | **Gemini-overlap reconciled** | All parts | **Closed by Gemini:** `ReplayChecksumError` on `llm_payload_hash` (`replay.py:890`). **Partial:** `MERKLE_CHAIN_VALID` now `.set()` in the manual `api_admin_verify_chain` (`fleet.py:242`), unlabeled — Phase 1.1 narrows to "add the continuous cron tick." **Reference corrections:** `nce/a2a_server.py` & `a2a_mcp_handlers.py` **don't exist** → use `nce/a2a.py` (repoint II.6/III.5/arch-doc refs). Migrations live in `nce/migrations/` (001–012) → Phase 1.2 migration = `013_event_log_sig_version.sql`. |

### Wave 0 results — still OPEN (plan stands), verified against the final tree

- **Phase 1.1** continuous chain-verify: **PARTIAL** — manual admin endpoint only; no `_chain_verification_tick` in `cron.py`. Gauge set once at `fleet.py:242` (unlabeled). *Narrowed:* add the cron tick + alert (gauge wiring already done).
- **Phase 1.2** sign `prev_chain_hash`: **OPEN** — not in `_build_signing_fields` (`event_log.py:539-569`); no `signature_version` column (confirmed absent in schema + all 12 migrations). New migration = `013_…`.
- **Phase 1.3** decay job: **OPEN** — `register_decay_jobs` (`temporal_decay.py:370`) never called from `cron.py`.
- **Phase 2** verified replay: **OPEN** — `uuid.uuid4()` everywhere (no uuid5/remap), no `replay_occurred_at` override on `append_event`, no `nce/state_digest.py`, no digest columns on `replay_runs`. (Phase 2.4 payload-hash check is the one CLOSED piece.)
- **Phase 4** cognitive: **all OPEN** — ATMS zero production callers (`resolve_contradiction` at `cognitive.py:204-217` does not invoke it), do-calculus orphan, `neuromorphic_search` not registered as a tool, `a2a_shared_query` never written (read-side fork handler exists at `replay.py:831`).
- **Re-run note:** this Wave 0 ran against the final 20/20 tree; refresh line numbers once more only if further commits land before implementation begins.

---

# Part I — Trust-Hardening, Verified Replay, Real Tests & Cognitive Wiring

## Context

Audit (file-level, evidence-backed) found that NCE's **isolation** story is genuinely strong and well-tested, but its **auditability/reproducibility** guarantees are architecturally real yet not wired shut, and ~40% of the advertised "cognitive" layer is orphan code with zero callers. The user wants the system made safer, production-ready, and more innovative — all of it, in one coordinated pass, with replay made *truly* byte-identical and verified (not just scoped honestly).

This plan turns the documented guarantees into self-enforcing, test-proven ones, and activates the dormant cognitive modules through real call sites.

**Decisions locked:** replay → make byte-identical *and* verified (heavy); scope → Phase 1+2+3+4 (safety + tests + innovation).

---

## Sequencing & dependencies

1. **Phase 1 (trust hardening)** and **Phase 2 (verified replay)** both edit `nce/event_log.py` `append_event`/`_sign_event`/`_insert_event`. **Do them as one coordinated edit to those functions** to avoid double-churn.
2. **Phase 3 (integration tests)** targets the behavior added in 1+2 → after them.
3. **Phase 4 (cognitive wiring)** is largely independent → can proceed in parallel.
4. **Migrations**: only two new ones — `event_log.signature_version` (1.2) and `replay_runs` digest columns (2.2). Everything else (`derived_from`, `v3_cognitive_ledger`, `contradictions`, `d365_*`) already exists.
5. **Tool-count tests** (`tests/test_tool_registry.py` `_EXPECTED_TOTAL=59`, mutation/cacheable/admin counts) must be bumped whenever Phase 4 adds tools — they assert exact totals.

---

## Phase 1 — Trust hardening (safety / production-ready)

### 1.1 Continuous Merkle-chain verification (currently defined, never auto-run)
- **Config** — add to `nce/config.py` (mirror `NCE_D365_SYNC_INTERVAL_MINUTES` at ~:645):
  `NCE_CHAIN_VERIFY_INTERVAL_MINUTES: int = _int_env("NCE_CHAIN_VERIFY_INTERVAL_MINUTES", 120, minimum=5)`
  `NCE_CHAIN_VERIFY_STARTUP_DEPTH: int = _int_env("NCE_CHAIN_VERIFY_STARTUP_DEPTH", 500, minimum=0)` (0 = full chain at boot).
- **New cron tick** in `nce/cron.py`, mirror `_saga_recovery_tick` (`:150-286`) exactly: `_chain_verification_tick(pool)`:
  - `lock = await acquire_cron_lock("chain_verification", cfg.NCE_CHAIN_VERIFY_INTERVAL_MINUTES*60+60)`; bail if None; `release_cron_lock(lock)` in `finally`.
  - Scan namespaces via `unmanaged_pg_connection(pool, site="cron.chain_verify.namespace_scan")` → **add that site string to `UNMANAGED_PG_AUDITED_SITES`** in `nce/db_utils.py:24-36`.
  - Per namespace, open a read conn and call `verify_merkle_chain(conn, namespace_id=ns)` (`nce/event_log.py:1168`, returns `{valid, checked, first_break, last_verified_seq, reason}`).
  - On `valid is False`: `log.critical(...)`; **set the `MERKLE_CHAIN_VALID` gauge** (already defined in `nce/observability.py:208` but **currently never set by any code** — this tick is its first writer); **dispatch an operator alert** via `NotificationDispatcher.dispatch_alert` (`nce/notifications.py`, see Part III); and `append_event(event_type="chain_verification_failed", params={first_break,...})` (an INSERT — allowed under WORM) so the alert itself is auditable.
- **Register** in `cron.py` `async_main()`: `scheduler.add_job(_chain_verification_tick, IntervalTrigger(minutes=cfg.NCE_CHAIN_VERIFY_INTERVAL_MINUTES), args=[pool], id="chain_verification", coalesce=True, max_instances=1, replace_existing=True)` next to the other `add_job` calls (~:565-590); add `_chain_verification_tick(pool)` to the `startup_coros` list (~:614-625).
- **Bounded startup check** (optional but recommended): in the startup tick, when `NCE_CHAIN_VERIFY_STARTUP_DEPTH>0`, pass `start_seq = max(1, max_seq - depth)` so boot doesn't full-scan huge chains.

### 1.2 Bind `prev_chain_hash` into the HMAC signature (currently the chain linkage is unsigned)
Confirmed safe ordering: `_sign_event` (`:799`) runs *before* `chain_hash` is computed, and `_fetch_previous_chain_hash` (`:651`) is available pre-sign → **no circular dependency** if we sign `prev_chain_hash` (not the current row's own `chain_hash`).
- **Migration** `nce/migrations/0NN_event_log_sig_version.sql` (+ mirror in `nce/schema.sql`): `ALTER TABLE event_log ADD COLUMN IF NOT EXISTS signature_version SMALLINT NOT NULL DEFAULT 1;` (valid on partitioned table). This is the **back-compat hinge**: existing rows stay v1 and keep verifying under the old field set; new rows are v2.
- `_build_signing_fields` (`:534`): add optional `prev_chain_hash_hex: str | None = None`; when set, include `"prev_chain_hash": prev_chain_hash_hex` in the dict.
- `append_event`: move the `_fetch_previous_chain_hash` call to *before* `_sign_event`; pass `prev.hex()` through `_sign_event` → `_build_signing_fields`. `content_hash` then also covers `prev_chain_hash` (fine); `chain_hash` unchanged (`SHA256(content_hash‖prev)`).
- `_sign_event` (`:799`): add `prev_chain_hash_hex` param, thread to `_build_signing_fields`.
- `_insert_event` (`:847`): add `signature_version: int` param, write it in the INSERT (set 2 on new writes).
- `verify_event_signature` (`:1088`): branch on `record["signature_version"]` — v2 rebuilds fields *with* `prev_chain_hash` (fetch the immediately-lower `event_seq` row's `chain_hash` in the same namespace), v1 rebuilds without. **`verify_merkle_chain` already walks predecessors** — have it pass the known prev hash into the per-row signature check to avoid an extra SELECT.

### 1.3 Register the dead decay-prune job (Ebbinghaus math is correct but never scheduled)
- In `cron.py` `async_main()` before `scheduler.start()`: `from nce.temporal_decay import register_decay_jobs; register_decay_jobs(scheduler, pool)` (`nce/temporal_decay.py:370` already builds the `IntervalTrigger` job id `phase_2_2_decay_prune`).
- Add `_decay_prune_tick(pool)` to `startup_coros`. Site `cron.decay_prune` is already in the allowlist — no `db_utils` change needed.

---

## Phase 2 — Verified byte-identical replay (heavy; user-selected)

Core idea: **make the divergence sources deterministic, then prove equality.** Today divergence comes from `uuid.uuid4()` (`replay.py:498,694`; `event_log.py:1019`) and fresh `now()`/`clock_timestamp()` timestamps.

### 2.0 PREREQUISITE — verify the replay handlers actually apply correct state *(blocker check, do first)*
A pressure-test flagged that `_handle_store_memory`/`_handle_consolidation_run` may `SELECT`/`INSERT` columns that **don't exist on the current `memories` schema** (`summary`, `salience` — salience actually lives in the separate `memory_salience` table; there is no `memories.summary`), and may **not preserve `payload_ref`** (which is `NOT NULL`). If true, reconstructive replay is already partially broken today. **Action:** before any determinism work, re-read these handlers against the post-Gemini tree and confirm against `pytest -m integration` replay tests. If the mismatch is real, fixing the handlers (join `memory_salience`, set `payload_ref` from event params) is a **prerequisite** to Phase 2 — do NOT assume; verify. (Don't fully trust this flag — it may reflect a stale read; a green replay integration test would refute it.)

### 2.1 Deterministic identity remap
- Replace random IDs in replay with **UUIDv5** keyed on `(target_namespace_id, source_uuid)` so repeated reconstructions are identical and content-addressable. Introduce a small `ReplayContext` carrying `uuid_remap: dict[UUID, UUID]` and a `remap(source_id) -> uuid5(target_ns, str(source_id))` helper, threaded through `_dispatch_and_apply_event` (`replay.py:~1113`) and the `HandlerFn` protocol (`:455`).
- Update `_handle_store_memory` (`:498`) and `_handle_consolidation_run` (`:694`) to allocate target IDs via `ctx.remap(...)` instead of `uuid.uuid4()`.
- **Deterministic event IDs**: add optional `event_id: UUID | None` param to `append_event`/`_insert_event`; replay passes `uuid5(target_ns, source_event_id)`.

### 2.1b Payload-ref strategy — the share-vs-copy decision *(new, couples to II.4)*
Reconstruction must populate `memories.payload_ref` (Mongo ObjectId, `NOT NULL`). Two options, with a real trade-off the audit surfaced:
- **(A) Reuse the source ObjectId** → source & target share one Mongo doc. Digest equality is trivial, but the two namespaces are *not* isolated — per-namespace forgetting (II.4) on one would affect the other. **Reject** for anything but throwaway analysis forks.
- **(B) Copy the Mongo doc to a fresh deterministic ObjectId** (derive from `uuid5`) → true isolation, but `payload_ref` strings differ between source and target. **Chosen.** Consequence for 2.3: the digest must **not** compare raw `payload_ref` strings — it compares a **content hash** of the payload instead (see 2.3).

### 2.2 Faithful timestamps (guarded override + mandatory re-sign)
- `append_event` binds `occurred_at` from DB `clock_timestamp()`. Add a **replay-only** `replay_occurred_at: datetime | None` that uses the source timestamp; handlers insert source `valid_from` rather than `now()`.
- **Critical (confirmed by audit):** `occurred_at` is part of the **signed fields** and feeds `content_hash`→`chain_hash`. Overriding it therefore **requires re-signing** with the preserved timestamp (the signature is computed over the overridden value), which `append_event` already does since it signs after assembling fields — just ensure the override is applied *before* `_sign_event`. The `event_log` `UNIQUE(namespace_id, event_seq, occurred_at)` does **not** collide because `event_seq` is already unique per namespace.
- Gate: override ignored unless caller is the replay engine in deterministic mode; still passes `_assert_not_future` (past is fine; the D8 guard targets `params.valid_from`).

### 2.3 Namespace state-digest + equality proof *(corrected projection)*
- New `nce/state_digest.py`: `async def compute_namespace_state_digest(conn, namespace_id, *, as_of=None) -> str`. SHA-256 over a canonical, sorted projection of the **durable, deterministic** state. Audit-corrected field rules:
  - **memories:** id (remap-normalized), agent_id, created_at, memory_type, assertion_type, valid_from, valid_to, derived_from, metadata, **content-hash of the payload** (NOT the raw `payload_ref` string — see 2.1b). **Exclude** `signature`, `signature_key_id`, `content_fts`, `embedding` (derived/divergent).
  - **kg_nodes / kg_edges:** labels/predicate/confidence + created_at; **exclude `updated_at`** (mutates on any KG write).
  - **memory_salience:** **EXCLUDE entirely** (or normalize to creation-epoch score) — `salience_score`/`access_count`/`updated_at` change on every retrieval and would break equality by design.
  - **contradictions:** structural fields; exclude human-curation fields (`resolved_by`, `note`) unless determinism is paramount.
- **Gate the claim**: after `ReconstructiveReplay.execute`, compare `digest(source@end_seq)` vs `digest(target)`; store both on `replay_runs` (migration: `source_state_digest TEXT, target_state_digest TEXT, digest_match BOOLEAN`) and surface in `replay_status`. "Byte-identical" wording is only earned when `digest_match` is true — Phase 3 test asserts it.

---

## Phase 3 — Integration tests that actually prove the claims

Today: ~1,687 tests but only ~26 `@pytest.mark.integration`; many units are over-mocked (e.g. `test_batch2_isolation.py:206` asserts a SQL substring; `test_event_log_verification.py:36` asserts a mock was called). Add real DB-backed tests (`@pytest.mark.integration`, run via `pytest -m integration` against the live Quad-Stack):
- `test_saga_compensating_delete_integration` — force PG failure after the Mongo insert in `_run_store_memory_saga` (`nce/orchestrators/memory.py:723`); assert the Mongo doc is gone and no orphan row remains.
- `test_gc_orphan_deletion_integration` — insert an orphan Mongo payload; run `_collect_orphans` (`nce/garbage_collector.py`); assert deletion.
- `test_rls_zero_leak_integration` — extend `test_rls_isolation_integration.py` to `memories` + `kg_edges`: write in ns A, assert ns B sees zero, A sees its own.
- `test_chain_tamper_detection_integration` — append events, mutate one row via a `NCE_BYPASS_WORM` dev connection, assert `verify_merkle_chain` returns `valid=False` with correct `first_break`, and v2 `verify_event_signature` fails on the tampered/reordered row.
- `test_replay_reconstruction_digest_integration` — store events in source ns, run `replay_reconstruct` into target, assert `compute_namespace_state_digest(source) == compute_namespace_state_digest(target)` and `replay_runs.digest_match is True`.

---

## Phase 4 — Activate orphan cognitive modules (innovation)

### 4.1 ATMS cascade on contradiction resolution
- In `resolve_contradiction` (`nce/orchestrators/cognitive.py:161-219`), the `UPDATE ... RETURNING *` already returns `memory_a_id`/`memory_b_id`. After the update + `append_event`, **inside a nested `SAVEPOINT`** (so an ATMS failure can't abort the resolution), map resolution → losing memory:
  - `accepted_a`→deprecate `memory_b_id`; `accepted_b`→deprecate `memory_a_id`; `superseded`/`rejected`→deprecate the rejected side; `false_positive`/`duplicate`→**no cascade**.
  - Call `evaluate_atms_intervention(conn, ns_uuid, str(loser_id))` then `persist_atms_invalidation(conn, ns_uuid, cascade)` (`nce/atms.py`). The justification graph is sourced from `memories.derived_from` (consolidated memories already record parents — `nce/consolidation.py:276`).
  - `append_event(event_type="atms_cascade", params={resolution, invalidated:[...]})` for auditability. ATMS is already cycle-safe; add a `max_cascade` guard.
- Optionally also register the justification graph at consolidation time (`consolidation.py` after the consolidated INSERT) so the cascade has edges to walk.

### 4.2 Do-calculus incident escalation
- Wire the orphan `NetBoxCircuitEscalator.evaluate_and_escalate` (`nce/vertical_modules/netbox/circuits.py:66`, which calls `DoCalculusEngine.evaluate`) into a live path, **guarded on `NCE_NETBOX_URL`/`NCE_NETBOX_TOKEN` presence** (no-op if unset):
  - **Auto-hook**: in the D365 incident/SLA-breach ingestion (`nce/vertical_modules/dynamics365/ingestion.py`), when `sla_breach` + impacted services, build a `degradations` dict and call the escalator inside a `scoped_pg_session`; persist returned tickets as `append_event(event_type="circuit_escalation_generated", params=ticket)`.
  - **Plus an MCP tool** `evaluate_circuit_impact` (handler in a new/again `nce/vertical_modules/netbox` handler module, registered in `nce/tool_registry.py` + declared in `nce/mcp_stdio_tools.py`, gated like the D365 tools) so agents/operators can run do-calculus on demand — more robust than relying on fuzzy telemetry mapping.

### 4.3 Expose spiking activation as a first-class tool
- `GraphRAGTraverser.neuromorphic_search` (`nce/graph_query.py`) is orphaned. Add a `neuromorphic_search` MCP tool (or a `mode:"spiking"` flag on `graph_search`) → handler in `nce/graph_mcp_handlers.py` calling `neuromorphic_search`, registered in `tool_registry.py` (cacheable) and declared in `mcp_stdio_tools.py`. Bump `tests/test_tool_registry.py` counts.

---

## Critical files

- `nce/event_log.py` — chain verify wiring target; signature/versioning edits (`_build_signing_fields:534`, `_sign_event:799`, `_insert_event:847`, `append_event`, `verify_event_signature:1088`, `verify_merkle_chain:1168`).
- `nce/cron.py` — register chain-verify + decay jobs in `async_main()`; new `_chain_verification_tick`.
- `nce/config.py`, `nce/db_utils.py` (`UNMANAGED_PG_AUDITED_SITES`).
- `nce/replay.py` — deterministic remap, timestamp override, digest gating; `nce/state_digest.py` (new); `nce/snapshot_mcp_handlers.py:315` (reuse serializer).
- `nce/orchestrators/cognitive.py` (ATMS hook), `nce/atms.py`, `nce/consolidation.py`.
- `nce/vertical_modules/netbox/circuits.py`, `nce/vertical_modules/dynamics365/ingestion.py`, `nce/graph_query.py`, `nce/graph_mcp_handlers.py`, `nce/tool_registry.py`, `nce/mcp_stdio_tools.py`.
- Migrations: `event_log.signature_version`, `replay_runs` digest columns (+ mirror `nce/schema.sql`).
- Tests: new integration tests above; update `tests/test_tool_registry.py` counts.

## Verification (end-to-end)

1. `make lint && make typecheck` clean.
2. `pytest` (unit) green; then **`pytest -m integration`** against `make local-up` — this is the real gate.
3. **Chain**: tamper a row via a `NCE_BYPASS_WORM` dev conn → confirm the new cron/startup tick logs `critical` and `verify_merkle_chain` reports the right `first_break`; confirm v2 signature verify fails on reorder.
4. **Decay**: confirm `phase_2_2_decay_prune` appears in the scheduler job list and a boot run soft-deletes faded rows.
5. **Replay**: `replay_reconstruct` source→target, then assert `replay_runs.digest_match is True` and the digests match; re-run reconstruction twice and confirm identical target UUIDs (uuid5 determinism).
6. **ATMS**: resolve a contradiction with `accepted_a`; confirm the losing memory + derived dependents are soft-deleted (`valid_to` set) and an `atms_cascade` event exists.
7. **Do-calculus**: with NetBox creds set, trigger an SLA-breach incident; confirm `circuit_escalation_generated` events; confirm `evaluate_circuit_impact` MCP tool returns ranked impacts.
8. **Spiking tool**: call `neuromorphic_search` via MCP; confirm a subgraph returns and tool-registry count tests pass.

---
---

# Part II — Innovation Roadmap: "Accountable Memory"

## Context

Every LLM memory product today (ChatGPT memory, Claude projects, the personalization wave) is the same shape: an **opaque profile the AI keeps *about* the user** — unverifiable, un-inspectable, with "forgetting" you take on faith. That opacity is the root of distrust. NCE's substrate (signed hash-chained event log, time-travel, deterministic replay, ATMS belief revision, reversible PII vault) uniquely lets us **invert** that into memory that is *accountable to the person it remembers*. This roadmap turns those primitives into five human-facing capabilities. Product north-star: **the first LLM memory that can prove why it believes something, show you everything it believes, forget on demand with a receipt, and tell you when it's unsure.**

This is **deferred work** — start after Gemini's 20-batch sequence and after Part I lands (several items depend on Part I's verified replay + ATMS wiring). Re-verify all line numbers against the post-Gemini tree first.

## Cross-cutting product decision (must settle before II.3/II.4 ship)

Today the only human-facing HTTP surface is the **admin** server, gated by HMAC (`nce/auth.py`, `admin/index.html` Alpine+Tailwind panels calling `/api/admin/*` via `signedFetch`). The accountable-memory features are most powerful exposed to the **end user the memory is about**, not just operators. **Net-new:** a *subject-scoped*, consent-bound read/govern surface (its own auth + RLS-pinned-to-self), distinct from admin. Recommend a dedicated `/api/me/*` surface reusing RLS (`scoped_pg_session`) bound to the caller's own namespace/agent. Until that exists, II.3/II.4 can ship admin-only as a v0.

## II.1 — Honest Uncertainty *(LOW effort, high trust-per-line)*
- **Exists:** `nce/semantic_search.py` already computes `raw_salience`, `last_updated`, and an `nce_decayed_score` (decay-aware rank) — but the MCP/result DTO drops them (returns only `memory_id`, `payload_ref`, `score`, `raw_data`).
- **Net-new (small):** surface `salience_score`, `last_reinforced_at`, and a derived `confidence` (decayed salience → 0–1, with an age/staleness flag) in the search result DTO and `handle_semantic_search` serialization. Add a recall convention so the agent can say "~60% sure, last confirmed 3 months ago" instead of bluffing.
- **Mechanism:** project the already-joined salience columns through `semantic_search` → MCP handler; add `confidence`/`stale` computed fields (reuse `nce/temporal_decay.py` retention math).

## II.2 — Epistemic Receipts *(LOW–MED)*
- **Exists:** `get_event_provenance` (`nce/replay.py:1575-1640`) returns the full causal chain for a `memory_id` via `parent_event_id` + `event_log.params->>'memory_id'`; admin route `/api/replay/provenance/{memory_id}`.
- **Net-new:** (a) include `signature` + a `verified` boolean (run `verify_event_signature`) in the provenance response so a receipt is *cryptographically* checkable, not just a list; (b) a **client-facing MCP tool** `explain_memory(memory_id)` / `why_do_you_know` returning the signed receipt (remembered evt# + signer + timestamp); (c) a recall convention that tags each memory-grounded claim with its epistemic status (🔗 remembered / 🧩 inferred-from / 💭 assumed) — the inference/assumed tags come from `memories.derived_from` and `assertion_type`.
- **Composes with:** Part I Phase 1.2 (once `prev_chain_hash` is signed, a receipt also proves chain position).

## II.3 — The Glass Profile *(MED)*
- **Exists:** namespace snapshot export (`nce/admin_handlers/replay.py:95-152`, streaming NDJSON), contradictions list, salience, provenance, and the Alpine/Tailwind panel pattern (`admin/index.html`).
- **Net-new:** (a) a per-subject aggregation endpoint (`/api/me/profile` or admin `/api/admin/subject-profile/{ns}/{agent}`) returning beliefs with salience/confidence/last-reinforced/source/contradictions; (b) a **govern** path — edit / downweight / pin / **retract** — where retract calls ATMS (`evaluate_atms_intervention` + `persist_atms_invalidation`, wired in Part I 4.1) so dependents cascade; (c) a new UI panel mirroring the D365/fleet panel structure.
- **Dependency:** ATMS cascade (Part I Phase 4.1) for correct retraction; the subject-facing surface decision above.

## II.4 — Provable Forgetting *(HIGH — the flagship; bigger than "crypto-shred one key")*

The pressure-test produced the decisive insight: **a memory's content does not live in one place.** It fans out into raw payload + many plaintext *derivatives*. So "destroy the DEK" alone forgets almost nothing. Provable forgetting = **encrypt the one raw copy under a DEK, *delete* every plaintext derivative, and guarantee the immutable log never held content in the first place.** Reframing it honestly is what makes it real.

### The content-artifact inventory (what "forget" must actually cover)
Confirmed write-path locations (`nce/orchestrators/memory.py`):
- **MongoDB `episodes.raw_data`** — the raw content. → **encrypt under the DEK**; destroying the DEK covers this one.
- **`memories.content_fts`** (tsvector from the summary) — **lexemes are reversible** → must be **deleted/zeroed** (DEK does not cover it).
- **`memories.embedding` + `memory_embeddings.embedding`** — derived vectors, inversion risk → **delete/zero**.
- **`kg_nodes.label`, `kg_edges.{subject,predicate,object}_label`** — **plaintext entity strings & triplets extracted from the content.** These are *used as lookup/anchor keys*, so they **cannot be encrypted at rest** without breaking graph search → they must be **deleted** on forget. (This is the inescapable truth: KG labels are content, and forgetting must delete them — ATMS cascade from Part I 4.1 is the mechanism.)
- **`pii_redactions.encrypted_value`** — already AES-256-GCM under master key; delete the rows.
- **Redis** working-memory cache `cache:{ns}:{user}:{session}` — plaintext summary; **explicit delete** (don't wait for TTL).
- **MinIO** `mcp-{media_type}/...` — plaintext media object; **explicit `remove_object`**.

### The WORM-content gate — RESOLVED (with one design fork)
Audited directly (`nce/orchestrators/memory.py`):
- ✅ **Full raw text is NOT in the immutable log.** `store_memory`'s `append_event` params (memory.py:~330) carry `saga_id, memory_id, payload_ref, assertion_type, entities, triplets` — references, not content. The full text/summary lives only in MongoDB `episodes.raw_data` (encryptable) — so the worst case (un-shreddable full content in WORM) is **avoided**.
- ⚠️ **Two residual content copies:**
  1. The WORM params **do include `entities` + `triplets`** — the extracted KG fragments (entity strings + relationship triplets). These are content-derived plaintext sitting in the **immutable** `event_log` → they **cannot be shredded**.
  2. `saga_execution_log.payload` stores the plaintext `summary` (memory.py:~361) — but that table is **deletable**, so the forget op must purge those rows.
- **Design fork (decide before building):**
  - **(a) Honest-scope** the guarantee: "raw content & full text are cryptographically unrecoverable; *extracted entities/relationships* recorded in the immutable audit log at write time persist there by design." Simplest; truthful.
  - **(b) Make the log content-free:** change `store_memory` to write entity/triplet **counts or a hash** (not the strings) into `event_log.params`, so nothing content-bearing enters WORM. Then full forgetting is achievable. Costs a little replay/audit richness. **Recommended if "complete forgetting" is a product promise.**
- Either way, the forget op must also purge `saga_execution_log.payload` rows for the memory.

### Mechanism
- New `nce/envelope.py` (DEK lifecycle), reusing `encrypt_signing_key`/`decrypt_signing_key` (`nce/signing.py` — AES-256-GCM, Argon2id/PBKDF2 envelope, per-row nonce, `SecureKeyBuffer` zeroing already exist and can wrap an arbitrary DEK).
- Per-memory (or per-subject) DEK; `episodes.raw_data` encrypted under it; wrapped DEK stored in a new `memories.wrapped_dek BYTEA` + `dek_key_id` (migration). Read paths that hydrate raw content must learn to decrypt: `semantic_search`, `recall_recent`/`get_recent_context`, `verify_memory`, `unredact_memory`, `search_codebase`, snapshot export, replay (enumerated by the audit).
- **`shred_memory` / `forget_subject` tool** performs the full sequence: destroy DEK → delete content_fts/embeddings → ATMS-cascade-delete kg labels/edges + derived memories → delete pii_redactions → purge Redis key → remove MinIO object → append a signed `memory_shredded` event (refs + key-id only, no content) → return a **deletion receipt** the human can verify.
- **Honest guarantee statement:** "the raw payload is cryptographically unrecoverable (DEK destroyed) and all plaintext derivatives are deleted; the immutable log retains only the *fact* of deletion, never the content." That is a defensible, *provable* claim — unlike "we deleted one key."
- Largest, most invasive item; sequence last. Its completeness test (Phase 3 / II verification) must assert that after shred, **no plaintext fragment of the content remains in any store** (Mongo ciphertext undecryptable, FTS empty, KG labels gone, Redis/MinIO purged, event_log holds only refs).

## II.5 — Bi-temporal Accountability *(MED — depends on Part I verified replay)*
- **Exists:** `as_of` time-travel on `semantic_search`/`graph_search`; `compare_states`; replay/fork.
- **Net-new:** an "explain-my-past-advice" capability — given a timestamp, reconstruct the agent's *belief state then* (as_of read) + the provenance receipts that were valid then, and present "here's what I knew and why I said X." Counterfactual "what if I'd known Y" via Part I's **verified** forked replay (so the reconstruction is provably faithful). Surface as an MCP tool `explain_past_decision(as_of)` + a Glass Profile timeline view.
- **Dependency:** Part I Phase 2 (verified byte-identical replay) — this is what makes the counterfactual trustworthy rather than hand-wavy.

## Recommended build order (cheap-and-proven → heavy-and-novel)
1. **II.1 Honest Uncertainty** — days; pure exposure of existing salience/decay.
2. **II.2 Epistemic Receipts** — small; provenance already exists, add signature/verify + client tool.
3. **Subject-facing `/api/me/*` surface** — the cross-cutting enabler for the next two.
4. **II.3 Glass Profile** — depends on Part I 4.1 (ATMS) for retraction.
5. **II.5 Bi-temporal Accountability** — depends on Part I Phase 2 (verified replay).
6. **II.4 Provable Forgetting** — heaviest; envelope encryption is a real subsystem; ship last.

## Verification (per capability)
- **II.1:** search response includes `salience_score`/`confidence`/`stale`; a 3-month-old unreinforced memory returns low confidence + stale=true.
- **II.2:** `explain_memory` returns a receipt whose `verified` flag flips to false if the underlying event row is tampered (ties into Part I chain tests).
- **II.3:** retract a belief in the Glass Profile → the memory and its `derived_from` dependents are soft-deleted (`valid_to` set) via ATMS; profile reflects it immediately.
- **II.4:** shred a memory → assert **no plaintext fragment survives in ANY store**: Mongo ciphertext is undecryptable (DEK destroyed), `memories.content_fts` empty, `embedding`/`memory_embeddings` gone, `kg_nodes`/`kg_edges` labels derived from it deleted (ATMS cascade), `pii_redactions` rows deleted, Redis cache key purged, MinIO object removed, and `event_log` holds only refs/hashes (no content). A signed `memory_shredded` event + verifiable deletion receipt exist.
- **II.5:** `explain_past_decision(as_of=T)` reconstructs the belief set valid at T; a counterfactual fork returns a `digest_match`-verified alternate state.

### II.6 — Accountable Federation *(MED — extends accountable memory across agents)*
Discovered while auditing A2A: the federation surface has strong crypto/RLS foundations (`nce/a2a.py` — SHA-256 token hashes, `enforce_scope`, expiry, revocation; queries run under the **owner's** RLS namespace at `nce/a2a_server.py:~408`; JWT audience + mTLS). But the *accountability* layer is missing — and it's the cross-agent mirror of II.1–II.4.
- **Access receipts (the federation analog of II.2):** the event type `a2a_shared_query` is **defined (`nce/event_types.py:51`) but never written** — so an owner cannot see *who read which of their memories, when, under which grant*. Net-new (small): append a signed `a2a_shared_query` event on every verified skill call in `nce/a2a_server.py` / `nce/a2a_mcp_handlers.py`, capturing `consumer_namespace_id`, `consumer_agent_id`, `grant_id`, and the query. Surfaces in the Glass Profile (II.3) as "who has accessed what I shared."
- **Signed inter-agent provenance:** when agent B retrieves a memory shared by A, return A's original `event_log` signature + `signature_key_id` alongside it (A's public key is already publishable via the `.well-known/agent-card`). B can then *cryptographically attribute* the memory to A — enabling **federated contradiction detection** ("A asserts X, C asserts ¬X", both signed).
- **Consent receipts + transitive-grant prevention:** chain grant-use events via `parent_event_id` back to the grant-creation event (both already in `event_log`); add a `can_delegate BOOLEAN` column to `a2a_grants` so a consumer can't re-grant someone else's data (closes the token-amplification path).
- **Dependency:** rides on Part I Phase 1.2 (signed `prev_chain_hash`) for receipt strength; pairs with the A2A security hardening in Part III.

---
---

# Part III — Production Operability

## Context

NCE has the *mechanisms* for safe operation but several are **not wired to operators**: failures are logged, not alerted; there's export but no import (no DR); and key paths are un-instrumented. None of these are visible in a demo — they bite the first time something fails at 3am in production. These are the unglamorous items that decide whether the trust story survives contact with real operations.

## III.1 — Wire the alerting pipeline *(HIGH — biggest operability gap)*
- **Exists but unwired:** `NotificationDispatcher` (`nce/notifications.py`, Slack/Teams/email/SNMP) is only called for DB-health degradation + one large-GC event. DLQ exhaustion (`nce/dead_letter_queue.py:236`), cron-tick failures (`nce/cron.py` `_CRON_TICK_ERRORS` handlers), outbox delivery failures (`nce/outbox_relay.py:183`), and quota exhaustion are **logged only**.
- **Net-new (small, high-value):** route those four failure classes through `dispatch_alert(...)`. An operator should learn about a poisoned task / failed sync / chain-verification failure (Part I 1.1) by notification, not by polling the admin dashboard.

## III.2 — Snapshot import / disaster recovery *(HIGH)*
- **Gap:** `stream_snapshot_export` (`nce/snapshot_mcp_handlers.py:88-312`) streams NDJSON out, but there is **no import/restore path** — the export format has no ingest. There is no NCE-native way to rebuild a namespace from a backup.
- **Net-new:** an `import_snapshot` / `restore_namespace` admin+MCP tool that ingests the NDJSON back through the Saga write path (re-using deterministic remap from Part I Phase 2 so a restore is itself verifiable via state-digest). This *completes* the time-travel/replay story into a real backup-and-restore.

## III.3 — Close the metrics blind spots *(MED)*
- **Findings:** `SagaMetrics` exists but is **opt-in** and not wrapped around the `store_memory` saga; `semantic_search`/`graph_search`/`replay` emit no latency spans/metrics; `nce/quotas.py` enforces fail-closed but emits **no consumption/remaining metrics**; the embedding **degraded-fallback** path (`nce/embeddings.py` hash-stub, `degraded_embedding_flag`) silently lowers search quality with no counter/alert.
- **Net-new:** auto-instrument the saga + search + replay paths; add `nce_quota_consumed_total` / `nce_quota_remaining` gauges with a per-namespace threshold alert; increment an `EMBEDDING_FALLBACKS` counter and (in prod) optionally fail-closed rather than silently serving hash vectors.

## III.4 — Deepen health checks *(MED)*
- **Finding:** `check_health` probes the 4 DBs only; it does **not** verify master-key decryption, a sample Merkle-chain segment, or RLS readiness — so signing/replay can be silently broken while `/health` is green.
- **Net-new:** extend the health probe to (a) decrypt the active signing key, (b) verify a bounded chain sample (reuse Part I 1.1), (c) sample an RLS-scoped read. Wire the `MERKLE_CHAIN_VALID` gauge here too.

## III.5 — A2A security hardening *(MED — lands with II.6)*
- **Findings/gaps:** no per-query **rate limiting** on the public A2A endpoints (admin paths have `@admin_rate_limit`, A2A does not); no **one-time / replay protection** on sharing tokens (a leaked token is reusable until expiry); JWT **audience is optional** (should be required so an admin token can't be replayed at the A2A surface).
- **Net-new:** add a sliding-window limiter to `tasks/send`; add an optional `one_time` grant mode (usage counter in `verify_token`); make `NCE_A2A_JWT_AUDIENCE` mandatory in production config validation (`nce/config.py`).

## III.6 — Ingestion sandboxing *(MED — safety)*
- **Findings:** external-process extractors (LibreOffice `soffice`, MPXJ/Java, Tesseract) and URL-fetching extractors carry risk. `nce/net_safety.py:199` self-documents a **TOCTOU DNS-rebinding** hole (validate-then-fetch with the HTTP client re-resolving DNS); MPXJ binary is allowlisted by name but not by hash/path.
- **Net-new:** an IP-pinned httpx resolver (resolve once, connect to that IP) to close the SSRF TOCTOU; pin the MPXJ/soffice binary by absolute path + hash; keep the existing decompression-bomb guards.

## III.7 — Network resilience (timeouts, retry, breaker coverage) *(MED — runtime)*

NCE has the right resilience *primitives* but applies them unevenly. Strong already: `nce/http_resilience.py` (tenacity exponential backoff + **full jitter**, honors `Retry-After`, transient-vs-permanent classification, Prometheus metrics); LLM providers have **both** retry *and* a circuit breaker (`nce/providers/base.py`, `CIRCUIT_BREAKER_STATE`/`FAILURES`); DB clients have bounded timeouts (`command_timeout=30` + 10 s pool-acquire; Mongo `serverSelectionTimeoutMS=5000`; Redis `socket_timeout=5` + `health_check_interval=30`); inbound idempotency (webhook dedup + outbox at-least-once) absorbs upstream retries/jitter. The gaps are coverage, ordered by severity:

| # | Gap (evidence) | Under network loss/jitter/latency | Fix |
| :-- | :-- | :-- | :-- |
| N-A | **Resilience helper coverage is partial** — only bridges + D365 *auth* use `http_resilience`; raw un-retried `httpx` in the **embedding sidecar** (`nce/embeddings.py:528,559`, per-read/write hot path), **D365 client** (`nce/vertical_modules/dynamics365/client.py:161`), **netbox_bridge** (`netbox_bridge.py:100`). | Transient blip → hard error or silent degrade on the busiest path. | Route these through `http_resilience.request_with_retry` — embedding sidecar first. |
| N-B | **NetBox clients have NO timeout** — `httpx.AsyncClient()` with no `timeout=` in `circuits.py:46`, `contacts.py:46/55`, `discovery.py:128/309`, `graphql_activation.py:135`. | A stalled NetBox/network = **unbounded hang**, holding the request + a concurrency slot indefinitely. | Add explicit `timeout=` + retry to every NetBox client (unbounded-hang fix first). |
| N-C | **Circuit breaker wraps LLM only** (`http_resilience.py:189` is explicitly "no circuit breaker"). | A *sustained* sidecar outage = every request retries through a 120 s timeout with no fast-fail → latency amplification / pile-up. | Extend the breaker to the embedding sidecar (and ideally all non-LLM integrations). |
| N-D | **Embedding degraded-fallback is silent** — sidecar failure → hash-stub (`degraded_embedding_flag`), no counter/alert. **⟂ III.3.** | Jitter/latency to the sidecar → **silent search-quality collapse.** | Retry + breaker the sidecar (N-A/N-C) **and** wire the `EMBEDDING_FALLBACKS` counter + alert already planned in **III.3**. |
| N-E | **No DB reconnect/failover** — pools have timeouts but no auto-retry on a dropped primary; Mongo `retryWrites`/`retryReads` not set; no read-replica failover. **⟂ Batch 19.** | A transient PG/Redis blip surfaces as a caller error instead of a transparent retry; replica failover undefined. | Thin DB-retry wrapper for transient `asyncpg`/Redis disconnects; set `retryWrites=true&retryReads=true`; define `DB_READ_URL` failover. **Reconcile with Batch 19 (HA/split-brain).** |
| N-F | **No per-request deadline / egress budget** — the 120 s sidecar timeout sits on the hot path. **⟂ Batch 20.** | One slow upstream call holds a request + a `NCE_MAX_CONCURRENT_TOOLS` slot up to 2 min under latency. | Tighter timeouts + bounded retry instead of one long timeout; consider deadline propagation. **Validate under Batch 20 (chaos/load).** |

**Priorities:** N-B (unbounded NetBox hang) and N-A/N-D (the embedding sidecar — on every read/write — has no retry/breaker and degrades silently). N-E is the Batch-19 overlap. All are runtime-hardening; sequence with the Wave 2 operability window (pairs with III.3's embedding-fallback counter).

---

# Part IV — Retrieval Quality (innovation, optional)

Latent upside in the search stack, independent of the trust work:
- **Hybrid search already exists** — `nce/semantic_search.py` fuses dense (pgvector cosine) + sparse (Postgres FTS `ts_rank_cd`) via RRF-style inverse-rank sum **weighted by salience decay** (`nce_decayed_score`). Good foundation; no learned reranking.
- **IV.1 Cross-encoder reranking (MED):** add an optional rerank pass over the fused top-N (reuse the NLI cross-encoder already loaded for contradiction detection, or a dedicated reranker). Pairs naturally with **II.1 Honest Uncertainty** — the reranker score becomes a real relevance-confidence signal.
- **IV.2 Multi-vector / aspect embeddings (HIGH effort):** one embedding per memory today conflates code-intent vs NL-intent vs entity. An `embedding_aspects` companion (built on the existing shadow-column re-embedding machinery + its Jaccard neighbor-overlap quality gate, `nce/reembedding_migration.py`) enables asymmetric retrieval (query code-intent → match code vectors). Net-new schema + migration; sequence well after the trust work.

---

## How these parts compose

Part I makes the guarantees *real*; Part III makes them *operable and observable*; Part II + II.6 make them *human- and agent-facing* (accountable memory, individual and federated); Part IV lifts raw retrieval quality. The dependency spine: **Part I (chain signing + verified replay + ATMS) → Part III (alerting + DR + health) → Part II/II.6 (receipts, glass profile, forgetting, federation) → Part IV (quality)**. Everything stays deferred until Gemini's sequence completes and the tree is re-audited.

**Cross-cutting theme — the content-derivative leak surface.** A memory's content is duplicated across MongoDB `raw_data`, the FTS tsvector, embeddings, KG node/edge labels, Redis cache, MinIO, *and* (as entities/triplets) the WORM event log. This single fact drives several items: it's why Provable Forgetting (II.4) is a delete-everywhere problem not a one-key problem, why the state-digest (Phase 2.3) must hash content not refs, and it's also a latent **PII/tenant-isolation** concern worth its own pass.

---

# Part V — Admin Control Plane: Full No-Text Configuration

## Context

Goal: an operator should configure and control the **entire** system from the admin web page — never hand-editing `.env`/config files. Today the admin UI (`admin/index.html`, Alpine.js + Tailwind, HMAC `signedFetch`) has panels for **fleet/namespaces, datastores, tools, maintenance, d365**, and the backend exposes runtime toggles for MCP tools/A2A skills (Redis `nce:tools:disabled`, enforced in `mcp_stdio_dispatch.py` / `a2a_server.py`), quota/namespace management, signing-key rotation, replay, DLQ, and bridge ops. But **most configuration is environment variables read once at boot** (`cfg = _Config` from `os.getenv` in `nce/config.py`, ~70 vars / ~20 sections), so "control everything from the UI" requires a **runtime settings layer**, not just more buttons.

> **Overlap warning:** the admin surface is exactly Gemini's **Batch 8 (Admin API & A2A Control Plane)**. This Part must be reconciled against the post-Gemini admin code — Gemini may already restructure routes/panels. Treat line/route references as pre-Gemini; re-audit first.

## V.1 — Runtime `SettingsStore` (the foundation, net-new)
- **DB-backed settings table** (global, admin-only, RLS-exempt or admin-namespace): `settings(key TEXT PK, value JSONB NULL, secret_enc BYTEA NULL, is_secret BOOL, section TEXT, updated_by TEXT, updated_at TIMESTAMPTZ)`. Secrets stored **encrypted** via `encrypt_signing_key` (`nce/signing.py`, the same AES-256-GCM/Argon2id envelope used for d365 `token_enc` and bridge OAuth tokens); plaintext secrets are **never** returned to the UI (write-only, masked display).
- **Precedence accessor** `cfg.get(key, default)` → **env default < settings-store override**. Cache in-process/Redis with short TTL + pub/sub invalidation, reusing the existing `nce:tools:disabled` runtime-toggle pattern so changes propagate to all processes without restart.
- **Settings registry** (`nce/settings_registry.py`): one metadata entry per setting — `key, section, type, reload_class (HOT/WARM/COLD), is_secret, prod_locked, validator`. This single registry drives **both** the API and the auto-generated UI form (no hand-built form per setting).

## V.1a — Settings registry (section-by-section sketch)

Representative inventory to seed `nce/settings_registry.py`. **Legend:** reload class **H**=hot (live) · **W**=warm (apply/reload action) · **C**=cold (restart). **🔒**=secret (encrypted at rest, write-only/masked). **⛔**=prod-locked (never UI-editable; `config.validate()` + API reject). This is a sketch — reconcile each key against `nce/config.py` at build time; not every var is listed.

**1. Datastores & connections** — `MONGO_URI` C🔒 · `PG_DSN` C🔒 · `DB_READ_URL`/`DB_WRITE_URL`/`PG_BOUNCER_URL` C🔒 · `MINIO_ENDPOINT` C · `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` C🔒 · `MINIO_SECURE` C. *(All connection-bound → read-only in UI with "set via secret manager / restart" badge.)*

**2. Pools & concurrency** — `PG_MIN_POOL`/`PG_MAX_POOL` C · `REDIS_MAX_CONNECTIONS` C · `NCE_MAX_CONCURRENT_TOOLS` C *(semaphore built once; could become W if rebuilt on change)*.

**3. Security & signing keys** — `NCE_MASTER_KEY` C🔒⛔ *(secret-manager only; never in store/UI)* · `NCE_API_KEY` W🔒 · `NCE_DISTRIBUTED_REPLAY` W.

**4. Guardrails (display-only, always forbidden in prod)** — `NCE_BYPASS_WORM` ⛔ · `NCE_BYPASS_RLS` ⛔ · `NCE_ADMIN_OVERRIDE` ⛔ · `NCE_LOAD_DOTENV` ⛔ · `NCE_ALLOW_ADMIN_DOTENV_PERSIST` ⛔. *(Render read-only with the reason; API hard-rejects writes.)*

**5. Admin surface** — `NCE_ADMIN_USERNAME` W · `NCE_ADMIN_PASSWORD` W🔒 *(pbkdf2 hash)* · `NCE_ADMIN_API_KEY` W🔒 · `NCE_ADMIN_MTLS_ENABLED` C · `NCE_ADMIN_HTTP_RATE_LIMIT`/`_PERIOD`/`_SENSITIVE_RATE_LIMIT`/`_SENSITIVE_RATE_PERIOD` **H**.

**6. MCP stdio** — `NCE_MCP_API_KEY` W🔒 · `NCE_MCP_NAMESPACE_ID` C *(per-connection pin)* · `NCE_DISABLE_MIGRATION_MCP` / `NCE_ALLOW_MIGRATION_MCP_IN_PROD` W.

**7. A2A / JWT** — `NCE_JWT_SECRET` W🔒 · `NCE_JWT_PUBLIC_KEY` W🔒 · `NCE_JWT_ALGORITHM`/`NCE_JWT_ISSUER`/`NCE_JWT_AUDIENCE`/`NCE_A2A_JWT_AUDIENCE` W · `NCE_A2A_URL` W · `NCE_A2A_MTLS_ENABLED` C · mTLS allowed SANs/fingerprints W · *(planned: A2A rate-limit **H**, one-time-grant default **H** — Part III.5/II.6).*

**8. LLM / Cognitive** — `NCE_LLM_PROVIDER` W · `NCE_COGNITIVE_BASE_URL` W · `NCE_COGNITIVE_EMBEDDING_MODEL` W · `NCE_COGNITIVE_API_KEY` W🔒 · BYO keys `NCE_OPENAI_API_KEY`/`NCE_ANTHROPIC_API_KEY`/… W🔒 · LLM temperature **H**.

**9. Embeddings & edge** — `NCE_EMBEDDING_MODEL_ID` W *(→ triggers re-embedding migration, not instant)* · `NCE_EMBEDDING_MODEL_REVISION` W · `NCE_EMBEDDING_TRUST_REMOTE_CODE` C · `NCE_BACKEND` C · `NCE_OPENVINO_MODEL_DIR`/`_REVISION` C · `EMBED_BATCH_CHUNK` **H** · `NCE_EMBED_MAX_BATCH_TEXTS`/`_MAX_TEXT_CHARS` **H** · `EMBEDDING_MAX_WORKERS` C.

**10. Re-embedding worker** — `REEMBED_BATCH_SIZE` **H** · `REEMBED_BATCHES_PER_MINUTE` **H** · `REEMBED_CRON_INTERVAL_MINUTES` W.

**11. Cron intervals** — `BRIDGE_CRON_INTERVAL_MINUTES` / `BRIDGE_RENEWAL_LOOKAHEAD_HOURS` W · `CONSOLIDATION_CRON_INTERVAL_MINUTES` W · `NCE_CHAIN_VERIFY_INTERVAL_MINUTES` W *(Part I 1.1)* · decay-prune interval W *(Part I 1.3)* · `D365_*`/`netbox_bridge` intervals W. *(W = reschedule the APScheduler job on change.)*

**12. GC / TTL** — `GC_INTERVAL_SECONDS` W · `GC_ORPHAN_AGE_SECONDS` **H** · `REDIS_TTL` **H**.

**13. Quotas** — `NCE_QUOTAS_ENABLED` **H** (global). *Per-namespace limits (llm_tokens/storage_bytes/memory_count) are **tenant-scoped**, not env — they live under the **Tenants** panel via the existing `manage_quotas`, not this global registry.*

**14. Webhooks (receiver hardening)** — `WEBHOOK_MAX_BODY_BYTES` **H** · `WEBHOOK_RATE_LIMIT`/`_RATE_PERIOD_SECONDS` **H** · `WEBHOOK_DEDUP_TTL_SECONDS` **H** · `WEBHOOK_DEDUP_FAIL_OPEN` ⛔ *(forbidden in prod)* · `NCE_WEBHOOK_TRUST_PROXY` W.

**15. Bridges & OAuth** — `BRIDGE_WEBHOOK_BASE_URL` W · `DROPBOX_APP_SECRET`/`GRAPH_CLIENT_STATE`/`DRIVE_CHANNEL_TOKEN` W🔒 · `AZURE_CLIENT_ID`/`_SECRET`/`_TENANT_ID` W🔒 · `BRIDGE_OAUTH_REDIRECT_URI` W · `GDRIVE_OAUTH_*`/`DROPBOX_OAUTH_*` W🔒. *(Bridge connect/disconnect/resync stay on the existing Integrations panel.)*

**16. Observability** — `NCE_OBSERVABILITY_ENABLED` W · `NCE_PROMETHEUS_PORT` C · `NCE_OTEL_SERVICE_NAME` C · `NCE_OTEL_EXPORTER_OTLP_ENDPOINT` W · Jaeger UI ports C.

**17. Temporal** — max `as_of` lookback window **H**.

**18. Cognitive tuning** — salience half-life / decay λ **H** · reinforcement δ **H** · active-learning confidence threshold (R<0.65) **H** · `NCE_ACTIVE_LEARNING_CONFIRM_XP`/`_REJECT_XP` **H** · contradiction NLI thresholds **H**.

**19. NetBox vertical** — `NCE_NETBOX_URL` W · `NCE_NETBOX_TOKEN` W🔒 · `NCE_NETBOX_DEFAULT_INTERFACE_TYPE` **H**.

**20. D365 vertical** — `NCE_D365_ENABLED` W · `NCE_D365_ORG_URL` W · `NCE_D365_WEBHOOK_SECRET` W🔒 · `NCE_D365_SYNC_INTERVAL_MINUTES` W · `NCE_D365_SYNC_PAGE_SIZE` **H** · `NCE_D365_API_VERSION` W · empathic urgency/frustration keyword lists **H** · `NCE_D365_NETBOX_BRIDGE_ENABLED`/`_INTERVAL_MINUTES` W · `NCE_D365_NETBOX_FUZZY_THRESHOLD` **H** · `NCE_D365_NETBOX_TENANT_CF_NAME` W. *(Per-namespace D365 enable stays on the Tenants/d365 panel.)*

**21. Ingestion / extractors** — `NCE_MPXJ_EXTRACTOR` / `NCE_MPXJ_ALLOWED_BINARIES` W · `NCE_SOFFICE` path C · OCR page/pixel caps **H** · decompression-size caps **H** · `net_safety` allow/deny lists **H** *(Part III.6)*.

**22. Tools & Skills toggles** — **H**, already runtime via Redis `nce:tools:disabled`; surface in the **Tools & Skills** panel (not the generic Settings form).

**Routing rule:** *global system* settings → the auto-generated **Settings** panel (this registry). *Tenant-scoped* values (quotas, per-namespace D365/bridge enablement, namespace metadata) → the **Tenants** panel via existing per-namespace endpoints. *Live operational toggles* (tools/skills) → the **Tools & Skills** panel. Keep the three surfaces distinct so "system config" never gets confused with "this tenant's limits."

## V.1b — `/api/admin/settings` API contract (sketch)

REST over the existing Starlette admin app (HMAC `signedFetch`, admin-only; HTTP status codes, not JSON-RPC error codes). Driven entirely by the V.1a registry. Every mutation appends a signed `config_changed` / `config_reload` event to the WORM log (secrets redacted).

| Method · Path | Purpose |
| :--- | :--- |
| `GET /api/admin/settings` | List registry + **effective** values, grouped by section (query `?section=&q=`). Secrets masked. |
| `GET /api/admin/settings/effective` | Flat resolved snapshot (key→value, secrets masked) — for export/diff. |
| `GET /api/admin/settings/{key}` | Single setting detail. |
| `PATCH /api/admin/settings` | Apply a batch of changes (validated, audited, optimistic-locked). |
| `POST /api/admin/settings/{key}/reset` | Remove the store override → revert to env/default. |
| `POST /api/admin/settings/reload` | Run WARM reload handlers for named domains. |
| `GET /api/admin/settings/pending` | Keys changed but `pending_restart` (drives the UI banner). |

**GET list** → `200`:
```jsonc
{ "sections": [ { "section": "Webhooks", "keys": [
  { "key": "WEBHOOK_RATE_LIMIT", "type": "int", "reload_class": "HOT",
    "is_secret": false, "prod_locked": false,
    "effective_value": 120, "source": "store",   // env | store | default
    "store_value_set": true, "validation": {"min": 1},
    "description": "Per-IP webhook rate limit", "updated_by": "admin", "updated_at": "2026-06-07T10:00:00Z" },
  { "key": "DROPBOX_APP_SECRET", "type": "secret", "reload_class": "WARM",
    "is_secret": true, "effective_value": "••••set", "source": "store" }
] } ] }
```

**PATCH** (batch, per-key best-effort) → `207 Multi-Status`:
```jsonc
// request
{ "changes": [
    { "key": "WEBHOOK_RATE_LIMIT", "value": 240, "expected_updated_at": "2026-06-07T10:00:00Z" },
    { "key": "NCE_LLM_PROVIDER", "value": "anthropic" },
    { "key": "PG_MAX_POOL", "value": 20 },
    { "key": "NCE_BYPASS_WORM", "value": true } ],
  "reason": "raise webhook throughput; switch provider" }
// response
{ "results": [
    { "key": "WEBHOOK_RATE_LIMIT", "status": "applied" },        // HOT → live now
    { "key": "NCE_LLM_PROVIDER",   "status": "pending_reload",   // WARM → needs reload
      "reload_domain": "llm" },
    { "key": "PG_MAX_POOL",        "status": "pending_restart" },// COLD → stored, inert until restart
    { "key": "NCE_BYPASS_WORM",    "status": "rejected",
      "code": "prod_locked", "message": "forbidden in production" } ],
  "event_id": "…" }   // the config_changed WORM event
```
Per-key `status` ∈ `applied | pending_reload | pending_restart | rejected`. Rejections: `prod_locked` → 403-class; validation fail → `422`-class with field error; stale `expected_updated_at` → `409` (optimistic-concurrency guard so two admins don't clobber).

**POST `/reload`** → run the WARM handlers and report per domain:
```jsonc
// request
{ "domains": ["cron", "llm", "observability", "a2a"] }
// response
{ "reloaded": { "cron": "rescheduled 7 jobs", "llm": "provider rebuilt (anthropic)",
                "observability": "otel exporter re-init", "a2a": "jwt config refreshed" },
  "event_id": "…" }
```
Each domain maps to a concrete reload action: **cron** → reschedule APScheduler jobs from new intervals; **llm** → rebuild the provider via `nce/providers/factory.py`; **embeddings** → enqueue a re-embedding migration (NOT instant — returns a migration id); **observability** → re-init the OTLP exporter; **a2a** → refresh JWT/mTLS config. WARM changes are inert until their domain is reloaded — the UI shows an "apply" affordance per pending domain.

**Cross-cutting rules:**
- **Secrets are write-only.** PATCH accepts a new plaintext value (stored encrypted via `encrypt_signing_key`); GET never returns it (`"••••set"`); `reset` clears it. "Rotate" = PATCH a new value.
- **Validation reuses `config.validate()`** logic as per-key validators so bad input is rejected at write-time with a clear message — never deferred to a boot crash.
- **Security-section writes** (keys, JWT, mTLS, admin creds) should require an auth **step-up** beyond the standard admin HMAC (note for design — e.g. re-assert admin API key in the request body), since they're the highest-blast-radius changes.
- **Auditability:** the `config_changed` event records key, `old→new` (secrets redacted to `set/unset`), actor, and reason — so configuration drift is reconstructable on the same timeline as memory/replay events.

## V.2 — HOT / WARM / COLD model (what the UI can change live vs. on restart)
- **HOT (apply immediately, read at use):** rate limits, `NCE_QUOTAS_ENABLED`, TTLs, tool/skill toggles, salience/decay params, observability sampling, contradiction/active-learning thresholds. Editing the store takes effect on next `cfg.get`.
- **WARM (re-read on a control action):** cron intervals (reschedule the APScheduler job), LLM provider/model/keys (rebuild the provider), embedding model (does **not** apply instantly — triggers a re-embedding migration, Part I/`reembedding_migration.py`). UI shows an explicit **"apply / reload"** button.
- **COLD (restart required):** DB DSNs, pool sizes, ports, `NCE_MASTER_KEY`, and the security guardrails. UI renders these **read-only** with a "requires restart / set via secret manager" badge; never editable from the UI in production.
- UI badges each field with its class; a **"pending restart"** banner appears when a COLD value is changed via the store.

## V.3 — The Settings panel (auto-generated, mirrors existing panels)
- New Alpine/Tailwind panel built the same way as the d365/fleet panels (`x-data="settingsPanel"` + `signedFetch` to `/api/admin/settings`), **auto-rendered from the registry**, grouped by the ~20 sections (collapsible accordions): Security, Datastores, LLM/Cognitive, Embeddings, Quotas, Cron, Bridges/OAuth, Webhooks, Observability, Admin, A2A, D365, NetBox, GC/TTL, Pools, …
- Each field shows **current effective value + its source badge** (`env` · `default` · `store`), a type-aware input (number/text/bool-toggle/enum-select/secret), inline validation from the registry `validation` block, and a per-field reload-class chip (**H/W/C**).

### V.3a — Interaction design (state-driven from the V.1b responses)
- **Dirty-tracking + batch apply.** Edits accumulate client-side into a pending set (the field shows a "modified" dot and a revert-this-field control). A sticky footer "Review N changes" opens a **confirm-diff modal** listing `key: old → new` (secrets shown as `set → ••••` / `••••→ rotated`), with the optional `reason` text box. Confirm → single `PATCH /api/admin/settings` with all changes + each field's `expected_updated_at`.
- **Render the per-key result honestly** (straight from the 207 response status):
  - `applied` → green "live" check, field value updates in place, source badge flips to `store`.
  - `pending_reload` → amber chip + the field's section grows an **"Apply (reload {domain})"** button; clicking it calls `POST /api/admin/settings/reload {domains:[…]}` and clears the chip on success.
  - `pending_restart` → grey lock chip; contributes to a top-of-page **"Restart required to apply N settings"** banner (fed by `GET /api/admin/settings/pending`).
  - `rejected` → red inline error with `code`/`message` (422 validation text, 403 prod-locked reason, 409 conflict).
- **Optimistic-lock conflict (409):** if another admin changed a key meanwhile, show "changed by {updated_by} at {time} — [reload field] / [overwrite]"; reloading re-fetches the current value so the admin re-decides rather than blind-clobbers.
- **Secret rotation flow:** secret fields render as empty write-only inputs labelled "•••• set (write-only)" with **Rotate** (reveals an input to enter a new value) and **Clear** (`reset`) actions — plaintext is never fetched or shown.
- **Prod-locked fields:** rendered disabled with a lock icon + tooltip ("forbidden in production — set via secret manager / restart"); not submittable. COLD fields are editable but clearly badged "takes effect after restart".
- **Search/filter** across keys + descriptions; a "changed-from-default only" filter to quickly see the deployment's actual overrides; **Export effective config** (calls `/effective`, secrets masked) for support/diffing.

## V.4 — Consolidate existing controls into one coherent IA
Bring today's scattered controls under a consistent information architecture — **Settings · Tenants · Tools & Skills · Integrations · Data & Replay · Security · Observability · Maintenance** — reusing the existing endpoints (tool toggle, quotas, namespaces, signing-key rotation, replay, DLQ, bridges, d365). The only net-new backend is the `SettingsStore`; everything else is re-grouping + filling gaps the registry exposes.

## V.5 — Safety, audit, guardrails (server-enforced, not UI-trusted)
- Every change → a signed `config_changed` event in the WORM `event_log` (key, old→new with **secrets redacted**, actor) — config changes become auditable like everything else.
- **Production guardrails stay forbidden regardless of UI:** `NCE_BYPASS_WORM`, `NCE_BYPASS_RLS`, `NCE_ADMIN_OVERRIDE`, `NCE_LOAD_DOTENV`, dotenv-persist remain rejected by `config.validate()` **and** the settings API rejects writes to `prod_locked` keys (defense in depth — the UI not rendering them is not sufficient).
- This **replaces** the dev-only `.env` dotenv-persist path (`NCE_ALLOW_ADMIN_DOTENV_PERSIST`) with the DB `SettingsStore` as the sanctioned mechanism — so there's **no text-file editing at all**, and it works in production for every non-guardrail setting.
- Reuse `config.validate()` logic as per-field registry validators so bad values are rejected at write time (immediate UI feedback) instead of crashing at next boot.

## V.6 — `config_changed` event schema + config time-travel & rollback

Because every settings mutation is a signed WORM event, **configuration gets the same bi-temporal accountability as memory** (ties directly to Part II.5). "What was the rate limit on March 3rd, and who changed it?" and "revert all settings to last Tuesday" both become queryable operations — config drift stops being a mystery.

### Event schema (`event_type="config_changed"`, params)
```jsonc
{ "actor": "admin",                      // authenticated admin identity
  "reason": "raise webhook throughput",  // optional operator note
  "changes": [                           // one entry per key in the batch
    { "key": "WEBHOOK_RATE_LIMIT", "section": "Webhooks", "reload_class": "HOT",
      "old": 120, "new": 240, "is_secret": false },
    { "key": "DROPBOX_APP_SECRET", "section": "Bridges", "reload_class": "WARM",
      "old": "set", "new": "set", "is_secret": true }   // secrets redacted to set/unset/rotated
  ] }
```
Companion events: `config_reset` (override cleared → key, reverted-to source) and `config_reload` (domain, outcome). Secrets are **never** in params — only the lifecycle token (`set`/`unset`/`rotated`). These events are signed + chained like all others (Part I 1.2), so the config history is itself tamper-evident.

### Reconstruct effective config `as_of T`
Fold the ordered `config_changed`/`config_reset` events for keys up to `T` over the env/default baseline. New read tool/endpoint `GET /api/admin/settings/effective?as_of=T` (and an MCP `explain_config_change(key)` returning a key's full change history) — the config analog of `semantic_search(as_of=)`. Non-secret values reconstruct exactly; secret *values* are not recoverable from the log (by design) — only the fact/time/actor of each change.

### Rollback to a point in time
`POST /api/admin/settings/rollback { as_of: T, sections?: [...], dry_run: true }`:
1. Reconstruct effective config at `T`.
2. Diff against current; compute the inverse change-set.
3. `dry_run` returns the proposed diff for a confirm-modal (same UI as V.3a); on confirm, apply it through the **normal PATCH path** — so every guardrail still holds (prod-locked keys are skipped, COLD keys become `pending_restart`, secrets that were rotated since `T` **cannot** be auto-restored and are flagged for manual re-entry).
4. The rollback itself is recorded as a `config_changed` event with `reason: "rollback to T"` — rolling back is itself on the timeline (and thus re-revertible).

**Guardrails for rollback:** never silently re-enable a forbidden flag; never fabricate a secret it can't recover; always go through validation. Rollback is a *proposed* batch a human confirms, not an automatic time-machine.

## Verification
- Change a HOT setting (e.g. admin rate limit) in the UI → effective immediately, `config_changed` event logged, no restart.
- A secret (e.g. an LLM API key) round-trips: stored encrypted, never displayed, used by the provider after a WARM reload.
- Attempt to toggle `NCE_BYPASS_WORM` in prod → not rendered editable **and** API rejects it.
- Change a COLD value → "pending restart" badge shown, value does not take effect until restart.
- Make several changes over time, then `GET /effective?as_of=T` reconstructs the exact past config; `rollback {as_of:T, dry_run:true}` returns the correct inverse diff; confirming it applies through PATCH (prod-locked skipped, rotated-since-T secrets flagged), and the rollback is itself logged as a `config_changed` event.

---

# Part VI — Deployment, Infrastructure & Environment Boundaries

## Context

The runtime story exists: `docker-compose.yml` (Postgres `pgvector:pg16`, Mongo 7, Redis 7.4, MinIO, a `cognitive` sidecar image, `worker`, `cron`, `admin`, `a2a`, `webhook-receiver`, Jaeger, Caddy), `docker-compose.local.yml` (DBs only), a `Caddyfile` edge, `Makefile` targets, `deploy/` with `bootstrap-compose-secrets.py` + `compose.stack.env`, `verify_v1_launch.py`, `health_probe.py`, and docs for air-gapped + AWS IAM worker isolation. This Part is the production-deployment target state.

> **Heavy overlap with Gemini Batches 15 (Deployment Scripts & Env Boundaries), 17 (Physical Edge & Telemetry), 19 (HA & Split-Brain), 20 (Chaos & Synthetic Load).** Treat the items below as a **checklist to reconcile against the post-Gemini tree** — much may already be done. Re-audit first; implement only the gaps.

- **VI.1 Secrets management (HIGH).** `bootstrap-compose-secrets.py` generates dev secrets into env files. Production must source secrets from a real manager (Vault / AWS Secrets Manager / Azure Key Vault), never committed compose/.env. Define a thin secrets-provider seam; `NCE_MASTER_KEY` is **secret-manager-only** (ties to Part V — never in the SettingsStore). No plaintext secrets in any prod compose file.
- **VI.2 Edge / TLS (MED).** Caddy terminates TLS; confirm HSTS, and that mTLS client-cert passthrough headers (`X-Forwarded-Client-Cert`) match `nce/mtls.py` expectations + the `*_MTLS_TRUSTED_PROXY_HOP` config. Edge-level rate limiting in front of `a2a`/`webhook-receiver`.
- **VI.3 Container hardening (MED).** Non-root users, read-only rootfs where possible, dropped Linux caps, per-service CPU/mem limits, `restart: unless-stopped`, and **compose `healthcheck` + `depends_on: condition: service_healthy`** so the stack starts in dependency order (verify the current compose has these).
- **VI.4 Least-privilege DB/worker roles (HIGH, security).** The `nce_gc` `BYPASSRLS` role must be used **only** by GC/re-embedding workers with its **own credentials**, distinct from the app role (`nce_app`) — confirm the workers actually connect as `nce_gc` and the app never holds BYPASSRLS. Network-segment workers (no public ingress). Aligns with `docs/aws_iam_worker_isolation.md`.
- **VI.5 Scaling & HA (MED).** Stateless `admin`/`a2a`/`webhook-receiver` scale horizontally; **`cron` must stay singleton** (CronLock exists — verify it's the only guard against split-brain; Batch 19 overlaps). RQ workers scale by lane. Document the read-replica (`DB_READ_URL`) + PgBouncer (`PG_BOUNCER_URL`) topology.
  - **VI.5a Multicore utilization (the architecture is multi-core *capable* but not *configured*).** Audit finding: NCE is asyncio (one event loop = ~one core per process, GIL-bound for Python-level CPU work). I/O concurrency is good (84 `asyncio.to_thread`/`run_in_executor` sites; asyncpg + Motor pools), but **nothing ships configured to use multiple cores**. Each gap below is config, not re-architecture:
    - **HTTP servers run single-process** — the `uvicorn` commands in `docker-compose.yml` (`admin_server:app` ~:154, `nce.a2a_server:app` ~:202, `nce.webhook_receiver.main:app` ~:249) carry **no `--workers` flag**, so each pins to one core. Fix: set `--workers N` (or front with gunicorn+uvicorn workers, or compose `deploy.replicas`) behind Caddy. All three are stateless → safe to scale. **Do NOT** add `--workers` to anything that runs background loops in-process (the MCP stdio server co-launches GC/outbox/re-embed tasks — multiple workers would duplicate them).
    - **One RQ worker, one job at a time** — `start_worker.py` is a single forking `Worker(...).work()`; default compose runs **one** `worker` container with no replicas, so background indexing/sync is effectively serial. Fix: run **N `worker` replicas** (or adopt RQ `WorkerPool`); keep lanes (`high_priority` → `batch_processing` → `default`) as-is. Confirm `cron` stays at **1** replica (CronLock is the guard).
    - **Embedding pool size = 1** — `nce/embeddings.py:46` `ThreadPoolExecutor(max_workers=cfg.EMBEDDING_MAX_WORKERS)`, default **1** (`config.py`), serializes concurrent embed calls. Fix: raise `EMBEDDING_MAX_WORKERS` to match CPU, or rely on larger batches; measure GIL contention (torch releases the GIL internally, so a small pool + bigger batches often beats many threads).
    - **No CPU-thread tuning** — no `OMP_NUM_THREADS` / `MKL_NUM_THREADS` / `torch.set_num_threads` / `TOKENIZERS_PARALLELISM` set anywhere; torch/numpy use library defaults that **mis-tune under container CPU limits** (oversubscribe → thrash, or undersubscribe → idle cores). Fix: pin these env vars to each container's CPU quota in the compose/`deploy` env; set `cpus:`/CPU limits so the libraries see the real budget.
    - **No true in-process multicore for CPU-bound Python** — zero `ProcessPoolExecutor`/`multiprocessing`; AST parse, PII/Presidio regex, HDBSCAN, and Python-side graph BFS are GIL-bound (only C-extensions release it). The right escape hatch already exists (push heavy work to **RQ workers**, then scale workers per the bullet above). Consider a `ProcessPoolExecutor` only for the heaviest *synchronous* extractors if profiling shows event-loop starvation.
    - **Verification:** on a multi-core host, confirm (1) each HTTP service spawns N worker processes (or N replicas) and saturates >1 core under load; (2) M `worker` replicas process M jobs concurrently while `cron` stays singleton; (3) `OMP_NUM_THREADS` et al. are visible inside each container and match its CPU quota; (4) an embedding-heavy load uses multiple cores. Cross-check with Batch 19 (HA/split-brain) and Batch 20 (chaos/load) so worker counts are validated under synthetic load, not just asserted.
  - **VI.5b Memory utilization (decent for one instance; one structural issue that couples to scaling).** Audit finding: the heaviest model (embeddings) is already offloaded out-of-process (`deploy/compose.stack.env:15` `NCE_COGNITIVE_BASE_URL=http://cognitive:11435` → `detect_backend()` returns `CognitiveRemoteBackend`, `nce/embeddings.py:646`), and model loaders are `@lru_cache`'d + lazy. Remaining items, in priority order:
    - **M1 — spaCy + NLI still load *in-process* (the structural one). ⟂ VI.5a.** `nce/graph_extractor.py:64` loads spaCy `en_core_web_sm`; `nce/contradictions.py:48` loads the DeBERTa-v3-small NLI `CrossEncoder`. Model-load surface = `admin_server.py` and `nce/tasks.py` (RQ worker), so **each RQ worker holds spaCy + NLI + torch ≈ 0.5–1 GB.** This collides directly with **VI.5a's "scale to N worker replicas"**: cores and RAM pull against each other — N replicas = N × (spaCy + NLI + torch). Fix: route NLI + spaCy through the cognitive sidecar (or a small dedicated NLP sidecar) so they're paid **once** like embeddings; or make contradiction-detection / graph-extraction lazy + opt-in so idle workers don't hold them. **This single change is what makes VI.5a worker-scaling cheap in RAM, not just correct for CPU — do them together.**
    - **M2 — torch thread arenas.** No `OMP_NUM_THREADS`/`MKL_NUM_THREADS`/`torch.set_num_threads` set (same gap as VI.5a); torch sizes per-thread arenas to *visible* cores and over-allocates under a container CPU limit. Fix: pin the thread-count env vars — caps CPU thrash **and** arena memory at once (shared fix with VI.5a).
    - **M3 — `gc.collect()` band-aids** at `nce/extractors/dispatch.py:317,323`, `nce/extractors/pdf_ext.py:114,253`, `nce/re_embedder.py:65` signal real transient-allocation pressure (PDF/OCR/LibreOffice load whole docs+images). Fix: stream/chunk extraction and keep heavy extractors on the RQ worker (already done) so spikes never hit API processes; for fragmentation prefer jemalloc / `malloc_trim` over stop-the-world `gc.collect()`.
    - **M4 — no container memory limits.** Compose sets no `mem_limit`/`deploy.resources.limits`, so a leak/spike OOM-kills the **host** (not one container), and libraries misread available RAM (same failure class as the CPU gap). Fix: set per-service memory limits sized to the model-load surface (`worker`/`admin` need more); pairs with VI.3 container hardening.
    - **M5 — Mongo pool `maxPoolSize=100` per process** (`nce/orchestrator.py`), each service its own client → 100 idle pooled connections × N services of socket buffers + server-side RAM, far above real concurrency. Fix: lower to match concurrency (~10–20); expose as config.
    - **M6 — Argon2id allocates 64 MiB per derivation** (`nce/signing.py:211`, `memory_cost=65536`), spiky under concurrent cold key-decrypts. Steady-state is fine (the `_key_cache`); the *test* pathology is separate (Wave 1.0 T1). Fix: keep the cache warm in prod and **document the spike** so 64 MiB × concurrency is not mistaken for a leak.
    - **Verification:** measure RSS per service before/after M1 (worker should drop ~0.5–1 GB once NLP is offloaded); confirm container memory limits are enforced (M4); confirm Mongo idle-connection RAM falls after M5; confirm scaling workers to N replicas (VI.5a) no longer scales RAM by N once M1 lands.
  - **VI.5c Disk I/O utilization (application discipline is fine; the gap is untuned infra + full-width vectors).** Audit finding: temp files are cleaned up, `store_media` uses `fput_object` on an already-staged file (no bytes→disk→MinIO double-write, `nce/orchestrators/memory.py:879`), and replay uses streamed object I/O. Remaining items, in priority order:
    - **D1 — datastores run stock, no tuning.** `docker-compose.yml`: `postgres` (pgvector:pg16, :26), `mongo:7.0` (:46), `redis:7.4-alpine` (:12) have no `command:`/mounted config. Postgres defaults (`shared_buffers` 128 MB, default WAL/checkpoint, `synchronous_commit=on`) → many small WAL flushes on the write-heavy WORM log + slow HNSW builds; Mongo defaults to snappy. Fix: Postgres `command: postgres -c shared_buffers=… -c maintenance_work_mem=… -c wal_compression=on -c checkpoint_completion_target=0.9 -c max_wal_size=…` (keep `synchronous_commit=on` for the WORM log); Mongo `--wiredTigerCollectionBlockCompressor zstd` (transcripts/code compress well → less disk + read I/O).
    - **D2 — pgvector stores full fp32 vectors. ⟂ Batch 18.** `vector(768)` ≈ 3 KB/row + a large, write-amplifying HNSW index (`nce/schema.sql:63,158,186,265`). Biggest steady-state DB-disk lever as the corpus grows. Fix: migrate to **`halfvec(768)`** (fp16 — halves storage + index size + read I/O, negligible recall loss) or quantize the index; the re-embedding machinery already exists to carry it. **Overlaps Gemini Batch 18 (vector compliance / cryptographic erasure) — reconcile there first** so the storage-format change and erasure work don't conflict.
    - **D3 — Redis persistence on by default** though Part VI.6 treats Redis as rebuildable. RDB snapshots + AOF fsync are disk I/O for declared-disposable data — *except* Redis also holds the RQ queues (losing them drops in-flight jobs). Fix: decide explicitly — `--save "" --appendonly no` to kill Redis disk I/O if queues are acceptably rebuildable, or keep AOF only for the queue.
    - **D4 — extractor temp churn hits real disk.** Write temp → subprocess reads → unlink, per file (`nce/extractors/libreoffice.py:59`, `project_ext.py:69`, `cad_ext.py:121`, etc.) — real disk writes for purely transient data. Fix: point `tempfile`/`NCE_ARTIFACT_STAGING_DIR` at a **tmpfs** (RAM-backed) mount → eliminates extractor disk I/O entirely (also the disk side of the M3 `gc.collect()` band-aids).
    - **D5 — temp files use `delete=False` + manual unlink** (`cad_ext.py:121`→`:163`, `diagrams.py:54`→`:134`, `project_ext.py:69`→`:175`). A crash between create and unlink leaks temp files on disk. Fix: use `TemporaryDirectory`/`try-finally` uniformly (pairs with D4's tmpfs).
    - **D6 — read replica underused.** `DB_READ_URL`/`pg_read_pool` exist and orchestrators use them for SELECTs, but they're optional and absent from default compose, so read I/O contends with WORM writes + index builds on the primary. Fix: document + wire the replica for `semantic_search`/`graph_search` reads (overlaps the VI.5 topology doc).
    - **D7 — unbounded container log volume.** Logs → stdout → Docker `json-file` driver with no rotation; `nce/event_log.py:362` `print('[RLS-DEBUG]…', flush=True)` fires every catalog check. Fix: set compose `logging: { options: { max-size, max-file } }`; demote the RLS-DEBUG `print` to `log.debug`.
    - **Verification:** measure WAL bytes/s + checkpoint frequency before/after D1; confirm on-disk vector+index size roughly halves after D2 (halfvec); confirm extractor runs produce zero real-disk writes once temp is on tmpfs (D4); confirm Redis disk I/O is gone if persistence is disabled (D3); confirm log volume is bounded (D7). Validate under Batch 20 (chaos/load) so I/O ceilings are observed, not assumed.
- **VI.6 Infra backup/DR (HIGH).** Complements Part III.2 (app-level snapshot import). Postgres WAL archiving / `pg_basebackup`, Mongo dumps, MinIO replication, Redis treated as rebuildable. Document RPO/RTO; the WORM `event_log` is the canonical source for replay-based reconstruction (Part I Phase 2 makes that reconstruction *verifiable*).
  - **VI.6a Crash & power-loss recovery (clean power loss is *mostly* survivable; hardware failure is not).** Audit finding: the saga/outbox/GC spine is solid — `_saga_recovery_tick` (`nce/cron.py:150`) sweeps `pg_committed` sagas at startup + every 5 min; `started`-state sagas become Mongo orphans healed by the forward GC; the transactional outbox survives crashes and re-delivers; cron locks are TTL'd; MinIO incomplete multipart uploads are swept; Postgres `synchronous_commit=on` (default) makes committed rows WAL-durable. Six gaps, ordered by severity:
    - **R-A — Mongo default write concern (w:1, j:false). ⟂ D1.** No write concern set on `AsyncIOMotorClient` (`nce/orchestrator.py:129`). The saga writes Mongo → gets ack → commits PG referencing it, but default Mongo acks *before* journaling, so the last ~100 ms window of acked writes can vanish on power loss → **PG durably committed, Mongo payload gone = dangling `payload_ref`.** Fix: set `w="majority", j=True` on the episodes write (or scope `j=True` to the saga payload insert) so an ack means journaled-to-disk before PG commits the reference. **Tie-in: D1's Postgres tuning must NOT turn off `synchronous_commit` for the WORM `event_log`** — keep both stores' durability ON for the saga path.
    - **R-B — No reverse reconciliation. ⟂ forward-GC (`garbage_collector.py:504`).** GC is forward-only (Mongo orphan → delete); nothing scans for PG memories whose Mongo doc is missing. The read path just raises `ValueError("MongoDB payload missing.")` (`nce/orchestrators/memory.py:1089`). So an R-A dangling ref is **permanently unreadable, undetected, unrepaired.** Fix: add a reverse integrity sweep (the mirror of the existing forward GC) — find `memories.payload_ref` with no Mongo doc → soft-retire (`valid_to=now()`) / alert / rebuild from the WORM log via replay.
    - **R-C — In-flight RQ jobs lost on worker death (HIGH).** `start_worker.py` is a bare `Worker(...).work()` — no `StartedJobRegistry` maintenance, no requeue-on-death, no `--with-scheduler`; the app DLQ catches *exceptions*, not power loss. Jobs *running* at crash time silently vanish. Fix: run RQ with the scheduler / a periodic registry cleanup that requeues abandoned jobs; make critical enqueues idempotent + re-derivable (bridge cursors & d365 sync are re-pollable; code-indexing is re-triggerable); document safe-to-lose vs must-requeue job classes. (Pairs with VI.5a's "N worker replicas" — more replicas = more in-flight jobs at risk until this lands.)
    - **R-D — No documented boot-recovery runbook; recovery split across processes.** Saga-recovery + outbox + partition live in `cron`'s `startup_coros` (`nce/cron.py:628`); GC + outbox-loop live in the MCP process (`nce/mcp_stdio_main.py:58`). **If `cron` is down, saga recovery and outbox don't run at all.** Fix: a documented "after unclean shutdown" sequence + health gate; ensure saga-recovery/outbox aren't solely dependent on `cron` being up (or make the dependency explicit + monitored). Overlaps Batch 19.
    - **R-E — Redis state loss partially unaccounted. ⟂ D3.** VI.6 calls Redis "rebuildable," but it also holds **RQ queues** (enqueued-but-not-started jobs) and **quota counters**. If D3 disables persistence (or Redis disk is lost): caches/nonces/locks are fine, but **queued jobs vanish and quota counters reset.** Fix: decide per-key-class — if queues must survive, keep AOF for the queue DB (reconcile with **D3**); document quota-counter reset behaviour.
    - **R-F — Single-node datastores = no hardware-failure tolerance. ⟂ Wave 5.** Clean power loss recovers via WAL + saga; a disk/node failure loses data without VI.6 backups. Fix: the VI.6 backup/DR + VI.5 HA story (WAL archiving, Mongo replica set, MinIO replication). The deep DR path — rebuild a namespace from the WORM log via replay — only becomes trustworthy once **Wave 5 (verified byte-identical replay)** lands.
    - **Verification:** kill -9 a worker mid-saga and confirm recovery converges (no dangling refs after R-A/R-B); pull power (or `docker kill`) mid-ingest and confirm no PG row points at a missing Mongo doc; crash a worker mid-job and confirm the job requeues (R-C); bring the stack up with `cron` absent and confirm the runbook surfaces that saga-recovery didn't run (R-D). Exercise under Batch 19 (HA/split-brain) + Batch 20 (chaos).
- **VI.7 Air-gapped / edge profile (MED).** Promote `docs/airgapped_deployment.md` to a first-class compose **profile**: local cognitive model + OpenVINO NPU, zero telemetry egress, pinned model revisions. Add a profile-specific `verify_v1_launch` smoke check.
- **VI.8 Image supply chain (MED).** Pin all base images **by digest**, pin + ideally **cosign-verify** the `nce-cognitive` image (currently a `:v1` tag), generate an SBOM, scan in CI. Model revision pinning already partly exists (`NCE_OPENVINO_MODEL_REVISION`, `NCE_EMBEDDING_MODEL_REVISION`).
- **VI.9 Deploy gate (MED).** Wire `verify_v1_launch.py` + `health_probe.py` (extended per Part III.4) into a CI/CD post-deploy smoke gate; keep `.github` workflows + pre-commit green as the merge gate.
- **Verification:** a fresh `make up` on a prod-like profile starts in health-ordered sequence; workers connect as `nce_gc`/`nce_app` with correct privileges; no plaintext secret on disk; the air-gapped profile runs with no outbound network; a simulated single-node loss recovers via documented DR.

---

# Part VII — Content-Surface Minimization (PII & Tenant Isolation)

## Context

The cross-cutting "content-derivative leak surface" (raw_data, `content_fts`, embeddings, KG labels/edges, Redis cache, MinIO, and WORM `event_log` entities/triplets) matters beyond forgetting: it's the **PII-compliance and tenant-isolation** surface. PostgreSQL isolation is strong (forced RLS); the other stores are weaker, and PII control depends on *ordering* that must be verified.

> **Overlaps Gemini Batch 4 (Security, PII Vault & A2A) and Batch 18 (Vector Compliance & Cryptographic Erasure).** Reconcile first.

- **VII.1 Verify PII-before-derivation ordering (HIGH — the gating fact).** Content is sanitized (`pii_process`) into `sanitized_summary`/`sanitized_heavy` *before* embedding + KG extraction (`graph_extract_async(sanitized_summary)`), so KG labels/`content_fts`/embeddings should carry **pseudonymized tokens, not raw PII**. **Confirm this ordering holds on every write path** (store_memory, consolidation, code indexing, bridge ingestion). If any path extracts/embeds/ingests *before* sanitizing, raw PII leaks into derivatives — and (via entities/triplets) into the **immutable** event log, which is un-erasable. This is the single most important thing to verify for GDPR posture.
- **VII.2 MongoDB tenant isolation (HIGH).** PG has forced RLS; Mongo `episodes` are isolated **only by an app-supplied `namespace_id` filter** — one missing filter = cross-tenant leak. Introduce a **scoped Mongo accessor** (analogous to `scoped_pg_session`) that injects `namespace_id` on every query/centralizes it, or move to per-namespace collections/DBs. Make isolation structural, not per-call discipline.
- **VII.3 MinIO tenant isolation (MED).** Media buckets `mcp-{media_type}` are shared; isolation is app-enforced via object naming. Add per-namespace key prefixes + bucket policies (or scoped, expiring presigned URLs) so object-store access can't cross tenants.
- **VII.4 Redis isolation (LOW).** Cache keys already include `namespace_id` (`cache:{ns}:{user}:{session}`) — audit for any un-namespaced keys; confirm TTLs; ensure quota/nonce keys are namespace-safe.
- **VII.5 Keep raw PII out of the WORM log (HIGH).** Depends on VII.1: since `event_log.params` for `store_memory` carries `entities`/`triplets`, those must be pseudonymized (or hashed/counted per Part II.4's "content-free log" fork). Raw PII in WORM = a permanent, un-erasable compliance breach.
- **VII.6 PII policy as runtime config (MED).** Per-namespace PII policy (redact / pseudonymize / reject / flag) and recognizer coverage, surfaced as **tenant-scoped settings** (Part V Tenants panel). Document custom recognizers.
- **VII.7 DSAR / right-to-be-forgotten (HIGH — the payoff).** VII + **II.3 Glass Profile** (what we hold about a subject) + **II.4 Provable Forgetting** (erase with a receipt) compose into a genuine GDPR/CCPA **data-subject-access + erasure** capability — export everything about a subject, then cryptographically forget it with proof. This is the compliance story the whole leak-surface analysis was building toward.
- **Verification:** inject a known PII string on every write path → assert it appears **only** pseudonymized in `content_fts`/KG/embeddings/event_log, with the reversible original only in the encrypted `pii_redactions` vault; a deliberately mis-scoped Mongo/MinIO query is blocked by the scoped accessor; a full DSAR export + erasure leaves no plaintext fragment (reuses the II.4 completeness test).

---

# Master Execution Sequence (post-Gemini)

> One ranked backlog, dependency-ordered, cheap-and-proven before heavy-and-novel. **Tests are not a final wave — each item ships with its integration test** (Part I Phase 3 is the test *pattern*, applied throughout). Re-verify line numbers against the post-Gemini tree first.

**Wave 0 — Re-audit (gate). ✅ DONE** (post-Gemini 20/20). Verdicts in the Risk Register above. Net: R1 CONFIRMED OPEN (live bug), R2 CONFIRMED (+ saga-log PII), R3 safe, R4 not-confirmed (nce_gc dormant), R5 reconciled (`a2a.py` not `a2a_server.py`; migrations 001–012; `MERKLE_CHAIN_VALID`/payload-hash partially closed).

**Wave 0.5 — Fix R1 replay handlers (FIRST implementation step — correctness bug).** Promoted to the front because reconstructive/forked replay **fails at runtime today** and it hard-blocks Wave 5 (verified replay), II.5 (bi-temporal), and III.2 (snapshot-restore reuse). Small, self-contained, high value-per-effort. Scope:
- `nce/replay.py` — fix `_handle_store_memory` (`:509-555`), `_handle_consolidation_run` (`:704-733`), `_handle_boost_memory` (`:614`): drop the non-existent `memories.summary`/`memories.salience` references; read/write salience via the `memory_salience` table (`salience_score`); set the NOT-NULL `payload_ref` (24-hex ObjectId) from the event's `params.payload_ref`. Leave `_handle_forget_memory` (already correct).
- **Gate with a real test:** add a `@pytest.mark.integration` test that replays a `store_memory` + `consolidation_run` + `boost_memory` event stream into a target namespace and asserts the rows land (no `UndefinedColumn`/`NotNull`/CHECK errors) — this is also the regression guard that R1 stays closed. (Lands cleanly after Wave 1.0's T1–T3 make the suite fast/bounded; if implementing before that, run the single test directly.)
- *Note:* this is the handler-correctness fix only. The **determinism** layer (uuid5 remap, `replay_occurred_at`, state-digest) remains in **Wave 5** — Wave 0.5 just makes replay *run* so Wave 5 can make it *verifiable*.

**Wave 1.0 — Test-suite performance & reliability (do FIRST, before any other Wave-1 work).** The suite is slow and can appear to "never finish." Root causes are evidence-backed below; fixes are ordered by payoff-per-effort. None change product behaviour — they only make the gate fast and bounded, which every later wave depends on.

| # | Root cause (evidence) | Fix | Payoff |
| :-- | :-- | :-- | :-- |
| T1 | **Signing-key cache is wiped after *every* test.** `tests/conftest.py:252` `_reset_signing_key_cache_after_test` (autouse) calls `signing_mod._key_cache.clear()` on every test. Any test that signs/verifies/encrypts then re-derives the AES wrapping key via **Argon2id** (`time_cost=3`, `memory_cost=64 MiB`, `parallelism=4` — `nce/signing.py:210-212`) or the **PBKDF2 @ 600 000-iteration** fallback (`nce/config.py:415`). That is ~50–150 ms **and** a 64 MiB allocation *per derivation*, defeating the very cache that exists to avoid it. Single biggest unit-suite cost. | Stop clearing the *derivation* cache globally. Either (a) make the autouse reset opt-in via a marker (`@pytest.mark.signing_isolation`) so only the few key-rotation tests pay it, **or** (b) monkeypatch `_derive_aes_key` (Argon2/PBKDF2) to a fast stub in a session fixture, keeping one real KDF round-trip test for correctness. | Largest single win; likely the bulk of unit wall-clock. |
| T2 | **No parallelism** — `pytest-xdist` not installed; ~1 700 tests across 146 files run on one core. | Add `pytest-xdist` to `requirements-dev.txt`; run `pytest -n auto`. Confirm parallel-safety first (conftest already notes per-worker module namespaces; signing cache is per-process, fine under xdist). | Near-linear speedup on multi-core. |
| T3 | **No per-test timeout** — `pytest-timeout` not installed. A single hung async test (real socket/DB/LLM attempt) blocks the whole run → the "never finishes" symptom. | Add `pytest-timeout`; set `addopts += --timeout=60 --timeout-method=thread` in `pytest.ini`. | Converts a hang into one failing test; bounded runs. |
| T4 | **44 real sleeps across 18 test files** (`time.sleep` / `await asyncio.sleep` — TTL/rate-limit/retry tests). Dead wall-clock. | Replace incidental sleeps with monkeypatched clocks or a no-op `asyncio.sleep`; keep real sleeps only where timing *is* the assertion. | Removes seconds of pure idle time. |
| T5 | **Heavy ML model loads** in 4 files (`SentenceTransformer` / `spacy.load` / `CrossEncoder` / `HDBSCAN` / OpenVINO — `test_batch3_hardening.py`, `test_reembedding_worker.py`, `test_sleep_consolidation.py`, `test_openvino_npu_export.py`). If unmocked, each loads real models (100s of MB, multi-second). | Mock the model objects, or mark `@pytest.mark.heavy` and deselect by default (`-m "not heavy"`), running them in a dedicated CI lane only. | Removes the worst per-test outliers. |
| T6 | **`filterwarnings = error`** (`pytest.ini`) turns *any* warning into a failure; with no timeout, flaky teardown/socket noise can abort or stall a run. | Keep `error` for first-party warnings; `ignore` known-benign dependency warnings (file already does this for a few). Pairs with T3 so noisy teardown fails fast instead of hanging. | Fewer false hangs/aborts. |

Sequencing: **T1 → T2 → T3** first (big wins + bounded runs), then T4/T5/T6 opportunistically. All test-infra only; verify with a before/after `pytest` wall-clock and a `pytest -n auto -m "not heavy"` smoke run. Land this before the Wave-1 trust edits so their new integration tests arrive in an already-fast, bounded suite.

**Wave 1 — Wire what's already built (Part I Phase 1).** Highest trust-per-line. ① 1.3 register decay job (≈1 line). ② 1.1 chain-verification tick + set the orphan `MERKLE_CHAIN_VALID` gauge + alert. ③ 1.2 sign `prev_chain_hash` (+ `signature_version` migration). Each with a tamper/behavior integration test.

**Wave 2 — Make failure visible (Part III.1, III.3, III.4).** ① III.1 route DLQ/cron/quota/outbox failures through `NotificationDispatcher` (cheap, high). ② III.4 deepen health checks (master-key decrypt, chain sample, RLS read). ③ III.3 saga/search/quota metrics + embedding-fallback counter.

**Wave 3 — Activate the cognitive layer (Part I Phase 4).** ① 4.1 ATMS cascade on contradiction resolution (also the prerequisite for Glass-Profile retract *and* Forgetting cascade). ② 4.3 expose `neuromorphic_search` tool. ③ 4.2 do-calculus incident escalation (guarded on NetBox creds).

**Wave 4 — DR (Part III.2).** Snapshot **import**/restore through the Saga path — completes backup/restore; reuses Wave-5 determinism for a verifiable restore.

**Wave 5 — Verified replay (Part I Phase 2).** Heavy. Depends on the **Wave 0.5** handler fix (already front-loaded). Deterministic uuid5 remap + payload copy (2.1b) + timestamp re-sign (2.2) + corrected state-digest (2.3). Unlocks II.5.

**Wave 6 — Accountable memory, cheap first (Part II).** ① II.1 Honest Uncertainty (days). ② II.2 Epistemic Receipts (small). ③ the subject-facing `/api/me/*` surface (enabler). ④ II.3 Glass Profile (needs 4.1). ⑤ II.6 Accountable Federation + III.5 A2A hardening. ⑥ II.5 Bi-temporal Accountability (needs Wave 5).

**Wave 7 — Provable Forgetting (Part II.4).** Heaviest; depends on 4.1 (cascade) + the WORM-content fork decision + envelope-encryption subsystem. Ship last; gate on the "no plaintext fragment survives" test.

**Wave 8 — Retrieval quality (Part IV, optional).** IV.1 cross-encoder reranking (pairs with II.1), then IV.2 multi-vector/aspect embeddings.

**Parallelizable / independent:** III.6 ingestion sandboxing (SSRF/subprocess) and III.5 A2A hardening can slot in any time; the content-derivative PII/isolation pass is its own track.

**Part V — Admin Control Plane** (own track; **reconcile against Gemini Batch 8 FIRST** — Gemini may restructure the admin routes/panels this plan references). Three ordered sub-waves:
- **V-a · Config foundation** — slots **right after Wave 2**. Build the `SettingsStore` + settings registry + `/api/admin/settings` API + server-side guardrails & `config_changed` audit (V.1, V.1a, V.1b, V.5). *Depends on:* Wave 0 re-audit only. *Unblocks:* UI-driven Part III alert thresholds/toggles, and it **retires `.env` editing** as the config mechanism. This is the load-bearing piece — almost everything else in Part V is UI on top of it.
- **V-b · Settings panel + IA** — **after V-a**. Auto-generated, state-driven Settings panel + interaction design + consolidation of existing controls into the unified IA (V.3, V.3a, V.4). Pure front-end on the registry/API; no new backend.
- **V-c · Config time-travel & rollback** — **after V-a + Wave 1's signed chain (1.2)**, because config history is only tamper-evident once `config_changed` events are chain-signed. Pairs conceptually with **II.5 bi-temporal accountability** (Wave 6) — ship them together so "rewind my memory" and "rewind my config" land as one accountability story (V.6).

**Part VI — Deployment/Infra** (reconcile against Gemini Batches 15/17/19/20 first; mostly checklist-and-fill-gaps). Compliance/security-critical items ride **with Wave 2 (operability)**: VI.1 secrets-manager seam, VI.4 least-privilege `nce_gc`/`nce_app` roles, VI.6 infra DR (complements III.2). The rest (VI.2 edge/TLS, VI.3 container hardening, VI.5 HA/scaling, VI.7 air-gapped profile, VI.8 supply chain, VI.9 deploy gate) slot opportunistically after.

**Part VII — Content-surface / PII & isolation** (reconcile against Gemini Batches 4/18 first). **VII.1 (PII-before-derivation ordering) and VII.5 (no raw PII in the WORM log) are Wave 0/1 verification gates** — they're compliance-critical *and* a hard prerequisite for Part II.4 (you cannot promise forgetting if raw PII is in the immutable log). VII.2 Mongo scoped-accessor + VII.3 MinIO isolation land in the Wave 2 hardening window. **VII.7 DSAR/erasure is the capstone — it composes II.3 + II.4 + VII and ships last, with Wave 7.**
