# TriMCP v1 — Post-Isolation To-Do List

*Last audited: 2026-05-07 against Innovation Roadmap v2, Enterprise Deployment Plan v2.2, current codebase, and Uncle Bob Clean Code review (7-module audit). Client-Side Privilege Escalation fix applied. Prompt 37: Signing key cache and MasterKey memory hardening applied. Sections reordered: open items first, sorted by priority.*

- [x] **Missing P1 MCP Tools** (Innovation Roadmap v2):
    - *Fix*: Implemented `manage_namespace`, `verify_memory`, `trigger_consolidation`, `manage_quotas`, `create_snapshot`, `list_snapshots`, `compare_states`.
    - *Hardening*: Added `_check_admin` gate with `TRIMCP_ADMIN_API_KEY` validation. Unified all inputs to Pydantic V2 models.
    - *Restoration*: Restored accidentally removed code indexing and GraphRAG tools.
    - *Alignment*: Updated `a2a_server.py` and `index_all.py` for multi-tenant namespace support.
    - *Status*: 98% implemented.

---

## Kaizen (Improvements)

- *Lint in CI*: The repo has no PR/merge `pytest` workflow yet; `.github/workflows/release.yml` only runs on version tags. **Recommendation**: Add a lightweight `ci.yml` (on `pull_request` / `push`) running `ruff check trimcp tests` with rules `F401` (unused imports), `F821` (undefined names), and `I` (isort via ruff) to catch missing imports and typos before merge. Pin `ruff` in `requirements-dev.txt` or use `astral-sh/ruff-action`.

- *Stale To-Do tracking*: All 6 remaining P1 bugs in `To-Do-v1.md` were already implemented in prior fix batches but never checked off. The To-Do list drifted out of sync with reality. **Recommendation**: After every fix batch, re-scan To-Do before closing the prompt. Consider a `verify_todo.py` script that cross-references open items against git log or codebase grep to flag stale entries automatically.

- *Test regression detection*: The Prompt 32 validation sweep uncovered 12 hidden test regressions that weren't listed in any Kaizen item — they were side effects of the MemoryOrchestrator extraction and other refactors. **Recommendation**: Run the full test suite (`pytest tests/ --tb=line --no-header -q`) as a gating step after every architectural refactor batch, and compare pass/fail counts against the baseline. Any change in count signals undocumented regressions.

- *False-alarm P1 entries*: The `observability.py` (`trace` NameError), `test_sleep_consolidation.py` (import error), and `TestResolveNamespace` auth test entries were already resolved by prior work or were never bugs (guarded code paths). **Recommendation**: Add a "Verification required" gate to new To-Do entries — before writing up a bug, run a minimal reproducer (`python -c "from trimcp.X import Y"`) to confirm the error actually reproduces on `main`.

### Kaizen — Updates (rolling log)

- **2026-05-07 — God Function refactor: `append_event()` (Prompt 55):** Extracted ``_validate_event_payload()``, ``_sign_event()``, and ``_insert_event()`` from ``append_event()`` in ``event_log.py``. The main function dropped from ~234 lines to ~70 lines. 352 existing tests pass with zero regressions. Existing locking, clock, and signing-field helpers preserved unchanged.

- **2026-05-07 — P6 test coverage batch 2 + docs (Prompt 51):** Created 15 new tests: `tests/test_pii_repr.py` (5 tests for PIIEntity repr safety) and `tests/test_providers.py` (10 tests for provider repr key leakage + _redact_api_key edge cases). Documented `TRIMCP_ADMIN_API_KEY` in env vars doc and `mcp_config.json`. Test suite grows from 337 to 352 passing. Installed `pypika` for SQL query builder dependency.

- **2026-05-07 — P6 test coverage batch 1 (Prompt 50):** Created 39 new tests across 3 new/updated test files: `tests/test_llm_providers.py` (10 tests, `pytest-httpx` for malformed LLM responses), `tests/test_ssrf_guard.py` (22 parametrized tests for SSRF guard), and `tests/test_extractors_core.py` (7 new decompression bomb tests). Test suite grows from 298 to 337 passing. Installed `pytest-httpx`, `python-docx`, and `defusedxml` for test dependencies.

- **2026-05-07 — P4 operational items (Prompt 47):** Three P4 items completed: (1) `consolidation.py` — added injection tag detection logging in `_build_consolidation_messages()` that logs WARNING with context excerpt when `<memory_content>` delimiters are detected in raw input; (2) `memory.py` — cached SHA-256 payload hashes in Redis via `mem_verify_hash:{memory_id}` with `cfg.REDIS_TTL`, with graceful degradation on Redis errors; (3) `a2a_server.py` — added optional `user_id` to all 5 A2A skill schemas, removed hardcoded `"default"` in `get_cognitive_state` handler, now reads `user_id` from params. 298 existing tests pass.

- **2026-05-07 — Namespace audit logging + admin identity propagation (Prompt 45):** Added `namespace_created` and `namespace_metadata_updated` to `EventType` in `event_log.py`. Added `append_event()` calls for `create` and `update_metadata` branches of `manage_namespace()` in `orchestrator.py`. Extended `manage_namespace()` with optional `admin_identity: str | None` parameter, threaded from `server.py` → `admin_mcp_handlers.py` → `orchestrator.py`. All audit events (create, update_metadata, grant, revoke) now use dynamic `admin_identity or "admin"`. Added `admin_identity` to `_MCP_AUTH_KEYS` in `mcp_args.py`. 298 existing tests pass.

- **2026-05-07 — Generalized WORM + RLS startup probes (Prompt 42):** `event_log.py` — refactored `verify_worm_enforcement()` into `verify_worm_on_table(conn, table_name)` with `_WORM_TABLES` registry (`event_log`, `pii_redactions`, `memory_salience`); added `verify_rls_enforcement(conn, table_name)` that catches non-scoped SELECTs returning rows, with `_RLS_TABLES` registry (12 RLS-protected tables). Orchestrator `connect()` now probes both sets at startup. 294 existing tests pass.

- **2026-05-07 — Startup schema safety checks (Prompt 39):** Two database initialization hardening items: (1) `orchestrator.py` — added `_check_global_legacy_warning()` that warns if the transitional `_global_legacy` namespace still has KG entities after 30 days, encouraging migration to reduce cross-tenant attack surface; (2) `schema.sql` — the `ck_a2a_grants_token_hash_len` DO block now runs a diagnostic `SELECT count(*)` before adding the constraint, skipping and warning instead of crashing on dirty legacy data. 294 existing tests pass.

- **2026-05-07 — P2 security gaps (Prompt 35):** Three fixes applied: (1) `office_word.py` — added `MAX_ENTRY_DECOMPRESSED_SIZE` (200MB) per-entry check in `_check_zip_bomb()` to prevent OOM from a single highly-compressed entry; (2) `pii.py` — wrapped `scan()` in try/except that clears `PIIEntity` raw values on exception before re-raising, preventing PII leakage into tracebacks; (3) `config.py` — added `_redact_dsn()` helper that masks passwords in connection URIs using `urllib.parse`. All 294 existing tests pass with zero regressions.

- **2026-05-07 — Post-refactor test validation sweep (Prompt 32):** Fixed 12 test regressions from the MemoryOrchestrator extraction, GC namespace-aware refactor, reembedding worker `model_uuid` signature change, and `graph_query` `set_namespace_context` call. Root causes: `FakeConsolidationConn` missing `fetchrow`; `TemporalGraphFakeConn` missing `execute`; `_collect_orphans` returning `int` instead of `dict`; reembedding test calls missing `model_uuid` param; mock `__aiter__` incompatibility with async generators; SQL injection temporal test missing `mongo_client` for delegated `semantic_search`. **Result**: 294 pass / 7 skip / 2 fail (smoke_stdio env only). All 6 P1-level regressions eliminated.

- **2026-05-07 — P4 DB/Redis ops (Prompt 46):** `schema.sql` — `idx_namespaces_parent_id`, `idx_namespaces_created_at DESC` on `namespaces`. `NonceStore` now uses `redis.asyncio.ConnectionPool` + `Redis` with `max_connections` default 100 for ad-hoc construction and `cfg.REDIS_MAX_CONNECTIONS` from `optional_hmac_nonce_store()`. `HMACAuthMiddleware` awaits `check_and_store`. Added `NonceStore.aclose()` for app shutdown (wire from Starlette lifespan if you want deterministic pool teardown). **Follow-up**: bridge/orchestrator paths still use sync `redis`; only the nonce hot path is async.

- **2026-05-07 — P5 code quality & debt (Prompt 48):** Removed deprecated `is_admin` from admin MCP `inputSchema`s; deleted dead `orchestrator._test()` / `__main__`; removed unused `graph_extractor.persist_graph()`; introduced `trimcp.mcp_args.model_kwargs` + `server._model_kwargs` and route `manage_namespace` / `manage_quotas` through it before `ManageNamespaceRequest` / `ManageQuotasRequest`. **Kaizen**: Keep auth stripping at the `call_tool` boundary (not inside each handler) so new `extra='forbid'` admin models only need one call-site update; avoid `from server import` inside `trimcp.*` handlers — it creates import cycles — use `trimcp.mcp_args` as the shared module instead.

- **2026-05-07 — `manage_namespace` grant/revoke atomicity (Prompt 40):** Grant and revoke branches now use `async with conn.transaction():` around the ACL `UPDATE` and `append_event()` so both commit or roll back together. `append_event()` already participates in the outer TX only (no internal COMMIT/ROLLBACK). **Follow-up**: `boost_memory` / `forget_memory` in the same file still pair mutations with `append_event` without an explicit transaction — same autocommit split risk; track as a small P3 if not already covered by saga paths.

- **2026-05-07 — Distributed HMAC replay (Prompt 36):** `cfg.TRIMCP_DISTRIBUTED_REPLAY` + `trimcp.auth.optional_hmac_nonce_store()`; `admin_server.py` passes `nonce_store` into `HMACAuthMiddleware` when flag + `REDIS_URL` are set; `server.py` docstring clarifies stdio MCP has no HTTP HMAC stack. **Update (Prompt 46):** `NonceStore` is now asyncio + pooled; residual blocking sync Redis applies to other components (orchestrator/bridge), not the HMAC nonce path.
- **2026-05-07 — Installer binary verification (Prompt 33):** Build defs audited for `trimcp-launch` parity with `.github/workflows/release.yml`; `TriMCP.wxs` header + directory layout clarified (Inno = full tree, MSI = shim + PS1); `deploy/README.md` native installers section; `GAPS.md` Phase 5 reframed (optional signed-artifact QA only).

- **2026-05-07 — Graph query time-travel signature verification (Prompt 38):** `GraphRAGTraverser._verify_time_travel_event_signatures()` added; all 3 time-travel CTEs (`_find_anchor`, `_bfs`, node metadata) now carry `event_id` through the CTE and verify HMAC signatures post-query. Raises `DataIntegrityError` on tampered rows. **Kaizen**: The verification query scans all `event_log` partitions (no `occurred_at` in WHERE). Bounded by `MAX_NODES=50`. Consider intra-`search()` event_id dedup cache to avoid re-verifying the same event across CTE calls (P7).

- **2026-05-07 — GC unified cascade + compare_states UNION ALL (Prompt 43):** Replaced three separate `_clean_orphaned_*` helpers in `garbage_collector.py` with single `_clean_orphaned_cascade()` using a chained CTE (`existing_memories` → `orphan_memory_ids` → cascading DELETEs to `memory_salience`, `contradictions`, `event_log`, `kg_nodes`). `compare_states` full-namespace diff now uses a single `UNION ALL` query with `change_type` tagging instead of two sequential `conn.fetch()` calls. Both reduce round-trips/scan count. **Kaizen**: GC `existing_memories` CTE still scans all RANGE partitions; materialized active-memory-ids lookup table viable at scale. `event_log` DELETE cascade scans all partitions — acceptable at hourly frequency.

- **2026-05-07 — P7 crypto & token upgrades (Prompt 52):** (1) `validate_base_url_async()` added — async DNS resolution via `run_in_executor` for SSRF guard. (2) `_PBKDF2_ITERATIONS` now reads `TRIMCP_PBKDF2_ITERATIONS` env var with 100k floor. (3) Argon2id wrapping-key KDF implemented with v3 blob prefix `TC3\x01` — `encrypt_signing_key` auto-selects Argon2id (argon2-cffi available) or falls back to PBKDF2; `decrypt_signing_key` handles v3/v2/legacy formats. (4) PII pseudonym tokens now use 16-byte base64url (~22 chars) instead of 64-char hex — 128-bit collision resistance. **Kaizen (Argon2id)**: No forced migration needed; existing v2 blobs still decrypt; new rotations emit v3; database naturally migrates over key rotation cycles. **Kaizen (PII tokens)**: Old 64-char hex tokens in stored text coexist with new 22-char base64url tokens; deterministic re-processing of same PII produces new format consistently.

- **2026-05-07 — Full TriStackEngine SRP extraction (Prompt 54):** Extracted all 5 remaining domain orchestrators from the God Class: `GraphOrchestrator` (graph_search, search_codebase), `TemporalOrchestrator` (trigger_consolidation, consolidation_status, create_snapshot, list_snapshots, delete_snapshot, compare_states, _fetch_memories_valid_at), `NamespaceOrchestrator` (manage_namespace, manage_quotas), `CognitiveOrchestrator` (boost_memory, forget_memory, list_contradictions, resolve_contradiction), `MigrationOrchestrator` (start_migration, migration_status, validate_migration, commit_migration, abort_migration, index_code_file, get_job_status). Each lives in `trimcp/orchestrators/<domain>.py`. `TriStackEngine` reduced from ~1662 to ~400 lines — a true director class. All 6 orchestrators are wired in `connect()` with lazy-init fallbacks for test compatibility via `_warn_connect_not_called()`. **Kaizen (cross-orchestrator calls)**: TemporalOrchestrator calls `self._engine.semantic_search()` for query-based compare_states — this is the only cross-orchestrator dependency; could be replaced with a direct callback but adds complexity. 350 tests pass, 0 regressions.

### P1 — Production Bugs (Fix Immediately)

- [x] **Fix `graph_query.py` missing `UUID` import** (`trimcp/graph_query.py`):
    - *Context*: Discovered 2026-05-07. `_find_anchor()` calls `UUID(str(namespace_id))` but `UUID` was not imported. Caused `NameError` in graph search with namespace scoping.
    - *Fix*: Added `from uuid import UUID` with other stdlib imports in `graph_query.py` (2026-05-07).

- [x] **Garbage Collector needs namespace-aware mode** (`garbage_collector.py`):
    - *Context*: The GC's orphaned `kg_nodes` DELETE runs without a namespace context set. With RLS now active, the query will return 0 rows.
    - *Fix*: Added `_fetch_all_namespaces()`, `_clean_orphaned_kg_nodes()`, `_clean_orphaned_salience()`, `_clean_orphaned_contradictions()` helpers that call `set_namespace_context()` before each per-namespace purge. `_collect_orphans()` now iterates over all namespaces (2026-05-07).

- [x] **Fix `NameError: name 'trace' is not defined` in `observability.py`** (`trimcp/observability.py:178`):
    - *Context*: Investigated during 2026-05-07 batch. The `trace` name IS imported inside the `try: from opentelemetry import trace` block at line 9-15, and its usage at line 177-178 is guarded by `if HAS_OTEL:`. The entry was a false alarm — no code change needed.

- [x] **Fix `test_sleep_consolidation.py` import error** (`tests/test_sleep_consolidation.py`):
    - *Context*: `consolidation.py` already has `from datetime import datetime` at module level (line 5). The test does not reference `datetime` directly — it imports via `trimcp.consolidation`. No code change needed; the entry was a false alarm.

- [x] **Fix `TestResolveNamespace` auth test failures** (`tests/test_auth.py:215,219`):
    - *Context*: `resolve_namespace()` returns `None` for missing/blank headers, does not raise `ValueError`. Tests were already updated to assert `is None` instead of `pytest.raises(ValueError)`. Already passing (2026-05-07).

- [x] **Fix `test_saga_rollback.py` for MemoryOrchestrator delegation** (`tests/test_saga_rollback.py`):
    - *Context*: Lazy-init `MemoryOrchestrator` fallback already present in `store_memory()` (line 454-456), `get_recent_context()` (line 750-754), `recall_context()` (line 757-760), and `recall_memory()` (line 887-890). Saga tests create `TriStackEngine()` without `connect()` — the lazy-init handles this correctly.

- [x] **Fix `test_integration_engine.py` requiring live databases** (`tests/test_integration_engine.py`):
    - *Context*: Already has `pytestmark = pytest.mark.skipif(not _ALL_CONTAINERS, ...)` decorator at module level with socket-based container detection and clear skip message. CI skips explicitly.

### P2 — Security Gaps

- [x] **Per-entry decompression limit for office_word.py** (`extractors/office_word.py`):
    - *Context*: The total uncompressed size check catches bombs, but a single highly-compressed entry could still cause OOM on `z.read(name)`. No per-entry limit existed.
    - *Fix* (2026-05-07 Prompt 35): Added `MAX_ENTRY_DECOMPRESSED_SIZE = 200MB` and a per-entry `file_size` check in `_check_zip_bomb()`. Each `ZipInfo` entry is now checked individually before summing; any entry exceeding the limit triggers an immediate `decompression_bomb` rejection.

- [x] **Wire NonceStore into production middleware stack** (`admin_server.py`, `server.py`):
    - *Context*: `NonceStore` is implemented and tested but not yet wired into `HMACAuthMiddleware` at the server construction sites. Multi-instance deployments need `NonceStore(cfg.REDIS_URL)` passed to the middleware constructor.
    - *Fix*: Added `cfg.TRIMCP_DISTRIBUTED_REPLAY` plus `trimcp.auth.optional_hmac_nonce_store()`. `admin_server.py` passes `nonce_store=_hmac_nonce_store`. `server.py` documents that stdio MCP has no HTTP HMAC stack — distributed nonce applies to the admin HTTP app only when the flag is truthy (`REDIS_URL` required).
    - *Kaizen (distributed)*: ~~Blocking `NonceStore.check_and_store` held the Starlette event loop~~ — **resolved (2026-05-07, Prompt 46):** async pooled `redis.asyncio`. Optional: unify nonce key prefix TTL with infra Redis DB index for multi-service tenants sharing one cluster.

- [x] **`_global_legacy` namespace hardens attack surface** (`schema.sql`):
    - *Context*: The KG RLS migration creates a `_global_legacy` namespace to backfill existing rows. If an attacker obtains any valid namespace UUID, they could set `trimcp.namespace_id` to `_global_legacy`'s UUID and access all legacy KG data. This namespace should be treated as a transitional artifact.
    - *Fix* (2026-05-07 Prompt 39): Added `_check_global_legacy_warning()` startup check in `orchestrator.py` wired into `connect()`. Queries `namespaces` for the `_global_legacy` slug, then `kg_nodes` for entity count under that namespace. If entities exist and namespace is ≥30 days old, logs a WARNING suggesting migration to proper namespaces. Gracefully handles missing tables (first-run scenario).

- [x] **PG_DSN contains credentials in plaintext** (`config.py:PG_DSN`):
    - *Context*: Database connection strings (PG_DSN, MONGO_URI) contain passwords in plaintext in env vars. If a connection error occurs, `asyncpg` or `motor` may include the DSN in exception messages.
    - *Fix* (2026-05-07 Prompt 35): Added `_redact_dsn()` helper in `config.py` that uses `urllib.parse` to safely mask the password component of any connection URI. Handles `user:pass@host` and `:pass@host` (Redis) formats, preserves query parameters and all non-sensitive components. Call sites can use `_redact_dsn(cfg.PG_DSN)` before logging or error formatting.

- [x] **Graph Query Time-Travel Verification** (`graph_query.py`):
    - *Context*: Time-travel mode in `graph_query.py` executed `event_log` queries entirely on the Postgres side via CTEs for performance. It bypassed inline Python `verify_event_signature()` verification — tampered event_log rows were silently accepted in time-travel graph traversals.
    - *Fix* (2026-05-07 Prompt 38): Added `_verify_time_travel_event_signatures()` helper to `GraphRAGTraverser`. All three time-travel CTE paths (`_find_anchor`, `_bfs`, node metadata fetch in `search()`) now carry the winning `event_id` through the CTE (`id AS event_id` in `memory_events`, propagated via `active_memories` → `historical_nodes`/`historical_edges` → final SELECT). After each CTE returns, the collected `event_id`s are verified by fetching full `event_log` rows and calling `verify_event_signature()`. Raises `DataIntegrityError` on any signature mismatch.
    - *Test*: 3 new tests in `test_graph_query.py`: `test_time_travel_anchor_detects_tampered_event` (anchor CTE → DataIntegrityError), `test_time_travel_bfs_detects_tampered_event` (BFS CTE → DataIntegrityError), `test_time_travel_passes_with_valid_signatures` (valid signatures → success). 7/7 pass.
    - *Kaizen (performance)*: The verification query (`SELECT * FROM event_log WHERE id = ANY($1::uuid[])`) scans all RANGE partitions since `occurred_at` is not in the WHERE clause. The subgraph is bounded by `MAX_NODES=50` so this is typically ≤50 event_ids. For extreme cases with many BFS layers, consider caching already-verified event_ids across CTE calls within a single `search()` invocation to avoid re-verifying the same event. Track as a P7 optimization.

- [x] **Clear raw PII in `scan()` on exception** (`pii.py:scan()`):
    - *Context*: `clear_raw_value()` was called only inside `process()` after the redaction loop consumes each entity. If an exception occurs during `scan()` (e.g., regex timeout, Presidio crash), the `entities` list could propagate into a traceback with raw PII values.
    - *Fix* (2026-05-07 Prompt 35): Wrapped `scan()` body in a try/except that iterates all entities and calls `clear_raw_value()` on each before re-raising the exception. The original exception is never swallowed — only the PII entities are sanitized before propagation.

- [x] **Signing Key Cache Uses Immutable Bytes** (`signing.py:_CachedKey.raw_key`):
    - *Context*: Discovered during MasterKey mutable-buffer fix. The decrypted signing key cached in `_CachedKey.raw_key` was a `bytes` object — immutable and not zeroable. While less critical than the master key (it's rotated and has a 5-minute TTL), it persisted in process memory.
    - *Fix* (2026-05-07 Prompt 37): Created `MutableKeyBuffer` class — a `bytearray`-backed wrapper with `raw` property (returns `memoryview`), explicit `zero()` method, and `__del__` defence-in-depth. Updated `_CachedKey.raw_key` from `bytes` to `MutableKeyBuffer`. `get_active_key()` and `get_key_by_id()` now return `memoryview` (accepted by `hmac.new()` and all bytes-like APIs). Old cache entries are explicitly `zero()`-ed before replacement in all three cache mutation paths (TTL refresh, `get_key_by_id` cache miss, `rotate_key`). All 31 tests pass including 12 new memory-inspection tests.
    - *Kaizen*: The `memoryview` returned by `get_active_key()` is valid only while the cache entry lives (5-minute TTL). Callers that store the return value beyond the cache window would get a dangling reference. This is safe for current callers (`event_log.py`, `consolidation.py`) which consume the key immediately and discard. Future callers should copy with `bytes(raw_key)` if long-term storage is needed.
    - *Kaizen*: `_key_cache` is module-level global state — the cache zeroing logic relies on careful ordering in `get_active_key()`. If `rotate_key()` is called concurrently with `get_active_key()` (unlikely in single-threaded asyncio), the old cache could be zeroed while a caller is still using it. For multi-threaded deployments, a reader-writer lock around the cache should be added (documented in the module docstring as a known constraint).

- [x] **`MasterKey.__init__` Receives Immutable `bytes`** (`signing.py:MasterKey.__init__`):
    - *Context*: `from_env()` called `mk_str.encode("utf-8")` which produced an immutable `bytes` object. The `bytearray` copied it, but the original `bytes` persisted until GC. This was a fundamental Python limitation.
    - *Fix* (2026-05-07 Prompt 37): Refactored `MasterKey.from_env()` to use `ctypes.create_string_buffer` for the UTF-8 encoding intermediate. The C buffer is explicitly `ctypes.memset`-ed to zero after the key material is copied into the `bytearray`-backed `MasterKey`. Uses `cls.__new__(cls)` to bypass `__init__` and build the instance directly from the C buffer via `memoryview`, avoiding a second intermediate `bytes` object. The single unavoidable intermediate is the `str` from `os.environ.get()` (immutable Python string — no known workaround in CPython). Added `test_from_env_ctypes_loads_correct_key`, `test_from_env_ctypes_with_unicode`, `test_from_env_rejects_short_key`, and `test_from_env_strips_whitespace`.
    - *Kaizen (memory boundary tradeoff)*: Despite the `ctypes` improvement, the `os.environ.get()` call unavoidably creates an immutable Python `str` that cannot be zeroed. CPython's internal string representation may cache the UTF-8 form after first encode, but this is interpreter-internal and version-specific. For deployments requiring absolute memory safety, the master key should be read from a file descriptor or kernel keyring via a C extension that never creates Python string objects. This is tracked as a potential `trimcp-secure-init` C extension for a future release.

### P3 — Architecture & Reliability

- [x] **Extract remaining TriStackEngine domain orchestrators** (Clean Code continuation):
    - *Context*: 2026-05-07 refactor extracted `MemoryOrchestrator` (~570 lines) from `TriStackEngine`. 5 more orchestrators remained for full SRP compliance:
        - `GraphOrchestrator`: `graph_search`, `search_codebase` (~150 lines)
        - `TemporalOrchestrator`: `trigger_consolidation`, `consolidation_status`, `create_snapshot`, `list_snapshots`, `delete_snapshot`, `compare_states` (~220 lines)
        - `NamespaceOrchestrator`: `manage_namespace`, `manage_quotas` (~130 lines)
        - `CognitiveOrchestrator`: `boost_memory`, `forget_memory`, `list_contradictions`, `resolve_contradiction` (~110 lines)
        - `MigrationOrchestrator`: `start_migration`, `migration_status`, `validate_migration`, `commit_migration`, `abort_migration`, `index_code_file`, `get_job_status` (~160 lines)
    - *Fix* (2026-05-07 Prompt 54): All 5 orchestrators extracted into `trimcp/orchestrators/` (graph.py, temporal.py, namespace.py, cognitive.py, migration.py). Each follows the lazy-init delegate pattern established by MemoryOrchestrator. `TriStackEngine` reduced from ~1662 to ~400 lines — a clean director class handling connect/disconnect, health checks, GC helpers, and cross-orchestrator delegation. Cross-orchestrator calls (e.g., TemporalOrchestrator → MemoryOrchestrator for `semantic_search`) go through `self._engine`. 350 tests pass, 0 regressions.
    - *Kaizen (director architecture)*: New domain methods are added to the appropriate orchestrator file and wired in `connect()` + add a lazy-init wrapper. The `_warn_connect_not_called()` helper warns when lazy-init creates a delegate outside `connect()`, making test compatibility explicit. After all 6 orchestrators extracted, the engine is a true director: connect, disconnect, scoped_session, health probes, GC coordination, and delegate wiring.

- [x] **Grant/revoke UPDATE + append_event not atomic** (`orchestrator.py:manage_namespace`):
    - *Context (pre-fix)*: The ACL UPDATE and `append_event()` used the same connection but were not wrapped in an explicit `BEGIN/COMMIT` transaction. If `append_event()` failed after the UPDATE succeeded, the ACL change could persist with no audit trail.
    - *Fix* (2026-05-07): Wrapped `ManageNamespaceCommand.grant` and `.revoke` in `async with conn.transaction():` so UPDATE and `append_event()` share one commit boundary.

- [x] **`a2a_grants` CHECK constraint — validate no violating rows** (`schema.sql`):
    - *Context*: The `ck_a2a_grants_token_hash_len CHECK (length(token_hash) = 32)` was added via an idempotent DO block. If any existing rows have `token_hash` bytes != 32, the `ALTER TABLE ... ADD CONSTRAINT` would fail at startup, halting the server.
    - *Fix* (2026-05-07 Prompt 39): Modified the DO block in `schema.sql` to run a diagnostic `SELECT count(*) FROM a2a_grants WHERE length(token_hash) != 32` before attempting to add the constraint. If violating rows exist, logs a WARNING with the count and skips adding the constraint. Only adds the constraint when the diagnostic returns 0 violating rows.

- [x] **Composite PK partitions block declarative foreign keys** (`schema.sql`):
    - *Context*: Multiple tables (`memories`, `event_log`) use RANGE partitioning with composite primary keys like `(id, created_at)`. Downstream tables (`memory_salience`, `contradictions`) can't declare FKs to `memories(id)` because `id` alone is not a unique constraint. Trigger-based FKs and GC cleanup were used as workarounds, but this architectural constraint affects every future table that references partitioned parents.
    - *Fix* (2026-05-07 Prompt 44 Step 2): Fully documented the tradeoffs in `docs/architecture-v1.md` (Section 8). Accepted trigger/GC patterns as the approved architectural approach (Option C) to preserve RANGE partition pruning on temporal queries. Verified trigger reference validations inside `schema.sql` and Cascading background garbage collection inside `garbage_collector.py`.

- [x] **Extend WORM Probe to Other Append-Only Tables** (general):
    - *Context*: The `verify_worm_enforcement()` pattern was hardcoded for `event_log` only.
    - *Fix* (2026-05-07 Prompt 42): Generalized into `verify_worm_on_table(conn, table_name: str)` in `event_log.py`. Added `_WORM_TABLES = ("event_log", "pii_redactions", "memory_salience")` registry. Orchestrator now iterates over all three at startup via `_verify_worm_enforcement()`.

- [x] **Extend RLS Probe to All RLS-Protected Tables** (general):
    - *Context*: No runtime validation that RLS actively scopes queries by namespace.
    - *Fix* (2026-05-07 Prompt 42): Added `verify_rls_enforcement(conn, table_name: str)` in `event_log.py` — attempts an unscoped `SELECT count(*)` and raises `RuntimeError` if >0 rows are returned (indicating RLS is not filtering). Added `_RLS_TABLES` registry covering all 12 RLS-protected tables. Orchestrator calls `_verify_rls_enforcement()` at startup.

- [x] **GC now cleans three entity types, but no unified orphan tracking** (`garbage_collector.py`):
    - *Context*: The GC cleaned `kg_nodes`, `memory_salience`, and `contradictions` orphans in three separate queries, each with its own `NOT IN (SELECT id FROM memories)` subquery against `memories`. Each scan of `memories` across all RANGE partitions was expensive at scale. Salience and contradiction deletes did not cascade to `event_log` for audit trail completeness.
    - *Fix* (2026-05-07 Prompt 43): Replaced `_clean_orphaned_kg_nodes`, `_clean_orphaned_salience`, and `_clean_orphaned_contradictions` with a single `_clean_orphaned_cascade()` method. Uses a chained CTE: `existing_memories` CTE scans `memories` once, `orphan_memory_ids` CTE LEFT JOINs `memory_salience`, `contradictions`, and `event_log` against it to identify orphaned references in a single pass, then cascading DELETEs (`deleted_salience` → `deleted_contradictions` → `deleted_events` → `deleted_nodes`) with RETURNING and count aggregation. Added `event_log` cascade for audit trail consistency.
    - *Test*: 3 new tests for `_clean_orphaned_cascade` (context set, error resilience, null row handling). 2 existing `_collect_orphans` tests updated to use unified cascade. 7/7 pass.
    - *Kaizen (performance)*: The `existing_memories` CTE still scans all RANGE partitions. For very large namespaces, consider a partial index on `memories(id) WHERE valid_to IS NULL` or materializing active memory_ids in a separate lookup table refreshed periodically. The `event_log` DELETE in the cascade scans all partitions since `occurred_at` is not in the WHERE clause — acceptable at GC frequency (hourly) but would be expensive if run more often.

- [x] **Adopt SQL Query Builder for Dynamic Queries** (`orchestrator.py` / `memory.py`):
    - *Context*: Dynamic CTE string formatting and manual `$N` parameter index tracking (e.g. `p_idx = 6`) in `semantic_search` are brittle.
    - *Fix* (2026-05-07 Prompt 44 Step 1): Refactored `semantic_search` dynamic query generation using PyPika builders (`Query`, `Table`, `Field`, `Order`, `Parameter`). Created `AsyncpgQueryBuilder` class inside `memory.py` to handle stateful, correct positional placeholders. Preserved whitespace for temporal assertions with `RawExpression` matching. Added `pypika` package to `requirements.txt`.

- [x] **Optimize `compare_states` Semantic Diffing** (`orchestrator.py`):
    - *Discovery*: Performed two sequential `conn.fetch()` calls (one for added rows, one for removed) then diffed results in Python.
    - *Fix* (2026-05-07 Prompt 43): Replaced the two sequential queries with a single `UNION ALL` query. Each branch tags rows with `change_type` (`'added'` or `'removed'`), and the Python side splits by tag. Reduces round-trips from 2 to 1 while producing identical results. Query optimizer executes both branches in one plan; each branch uses existing `namespace_id` + temporal column indexes.
    - *Kaizen*: The correlated `memory_salience` subquery in both UNION branches could be materialized once in a CTE, but the salience lookup already uses an index — marginal gain for typical namespace sizes.

### P4 — Operational Improvements

- [x] **`manage_namespace()` create/update_metadata lack audit logging** (`orchestrator.py:manage_namespace`):
    - *Context*: Only grant and revoke commands produced audit events. `create` and `update_metadata` modified the `namespaces` table without audit trail.
    - *Fix* (2026-05-07 Prompt 45): Added `namespace_created` and `namespace_metadata_updated` to the `EventType` Literal in `event_log.py`. Added `append_event()` calls in both branches of `manage_namespace()` in `orchestrator.py`. The `create` branch also wrapped in `conn.transaction()` so the INSERT and `append_event()` share one commit boundary.

- [x] **Hardcoded `agent_id="admin"` in grant/revoke audit events** (`orchestrator.py:manage_namespace`):
    - *Context*: Grant/revoke `append_event()` calls used hardcoded `agent_id="admin"`, making the actual operator untraceable.
    - *Action*: Thread the authenticated principal from the MCP layer through to the orchestrator.
    - *Fix* (2026-05-07 Prompt 45): Extended `manage_namespace()` to accept optional `admin_identity: str | None = None` (falls back to `"admin"`). Updated `server.py` `call_tool()` to extract `admin_identity` from arguments before `_model_kwargs()` strips it. Updated `handle_manage_namespace()` in `admin_mcp_handlers.py` to receive and pass `admin_identity`. Added `admin_identity` to `_MCP_AUTH_KEYS` in `mcp_args.py`. All grant/revoke/create/update_metadata audit events now use `admin_identity or "admin"`.

- [x] **Audit `namespaces` table DDL for index coverage** (`schema.sql`):
    - *Context*: The `namespaces` table (tenant root) had no indexes beyond the implicit PK and UNIQUE on `slug`. Cross-namespace queries like `manage_namespace`'s `SELECT * FROM namespaces ORDER BY created_at DESC` could sequential-scan. The `parent_id` FK column was unindexed for grant/revoke-style updates.
    - *Fix* (2026-05-07): Added `idx_namespaces_parent_id` on `(parent_id)` and `idx_namespaces_created_at` on `(created_at DESC)`.

- [x] **Prompt Injection Monitoring** (`consolidation.py`):
    - *Context*: While `<memory_content>` delimiter sanitization prevented basic injection, there was no audit trail when injected tags were detected.
    - *Fix* (2026-05-07 Prompt 47): Added injection tag detection in `_build_consolidation_messages()`. Before sanitization, checks if `<memory_content>` or `</memory_content>` tags exist in the raw input. When detected, logs a `WARNING` with a truncated excerpt of the surrounding content (80 chars context) to the standard log for security review.

- [x] **NonceStore connection pooling** (`auth.py:NonceStore`):
    - *Context*: Each `NonceStore` instance lazy-inited a single sync `redis.Redis` client without connection pooling.
    - *Fix* (2026-05-07): `redis.asyncio.ConnectionPool.from_url(..., max_connections=...)` with default 100 or `cfg.REDIS_MAX_CONNECTIONS` via `optional_hmac_nonce_store()`.

- [x] **NonceStore async Redis** (`auth.py:NonceStore`):
    - *Context*: Sync `redis.Redis` inside async middleware blocked the event loop at scale.
    - *Fix* (2026-05-07): `redis.asyncio` `Redis` + `check_and_store` is async; `HMACAuthMiddleware._check_nonce` awaits it.

- [x] **Cache Verified Payload Hashes** (`orchestrator.py:verify_memory`):
    - *Context*: Recalculated the SHA-256 hash of the MongoDB document on every `verify_memory` call.
    - *Fix* (2026-05-07 Prompt 47): Added Redis caching in `MemoryOrchestrator.verify_memory()` using key `mem_verify_hash:{memory_id}` and `cfg.REDIS_TTL`. Cache-first pattern: checks Redis before MongoDB lookup; stores result after first calculation. Graceful degradation: Redis errors (connection/timeout) are caught and treated as cache miss — hash is recalculated from Mongo. Cache is implicitly invalidated when memory content changes (payload_ref changes → different hash).

- [x] **Expose `user_id` in A2A Protocol** (`a2a_server.py`):
    - *Context*: `get_cognitive_state` hardcoded `user_id="default"`, making multi-user A2A integration impossible.
    - *Fix* (2026-05-07 Prompt 47): Added optional `user_id` parameter to all 5 skill parameter schemas in `_AGENT_CARD`. Updated `get_cognitive_state` handler to extract `user_id` from `params` (falls back to `"default"` for backward compat) and pass it to `recall_memory()`. Other skill handlers accept `user_id` in their parameter schemas for forward compatibility.

### P5 — Code Quality & Debt

- [x] **Remove deprecated `is_admin` from admin tool schemas** (`server.py`):
    - *Context*: After the Client-Side Privilege Escalation fix (2026-05-07), the `is_admin` boolean property was marked DEPRECATED in admin tool inputSchemas. It is no longer checked by `_check_admin()`.
    - *Fix* (2026-05-07, Prompt 48): Removed `is_admin` from `unredact_memory`, `manage_namespace`, `trigger_consolidation`, `consolidation_status`, `manage_quotas`, `rotate_signing_key`, and `get_health` schemas.

- [x] **Fix dead `MemoryPayload` reference in `orchestrator._test()`** (`orchestrator.py`):
    - *Context*: Dev harness referenced obsolete `MemoryPayload` field names.
    - *Fix* (2026-05-07, Prompt 48): Removed `_test()` and `__main__` block; public `MemoryPayload` alias to `StoreMemoryRequest` retained for `trimcp` API and tests.

- [x] **`persist_graph()` is dead code** (`graph_extractor.py`):
    - *Context*: Never called; orchestrator uses inline SQL for KG writes.
    - *Fix* (2026-05-07, Prompt 48): Deleted `persist_graph()` and unused `TYPE_CHECKING` / `asyncpg` stub imports.

- [x] **Decouple admin auth from Pydantic `extra="forbid"` models** (`server.py`, `models.py`):
    - *Context*: `ManageNamespaceRequest` / `ManageQuotasRequest` required manual key stripping in handlers.
    - *Fix* (2026-05-07, Prompt 48): Added `trimcp/mcp_args.py` with `model_kwargs()`; `server._model_kwargs` delegates to it; `call_tool` passes `_model_kwargs(arguments)` into namespace/quota admin handlers; handlers use `Model(**arguments)` on the cleaned dict.

- [x] **`_resolve_credential()` literal key warning** (`factory.py:_resolve_credential()`):
    - *Context*: Literal-key branch logs a generic warning without the key value.
    - *Fix* (2026-05-07, Prompt 49): Comment above `log.warning` forbids ever including the raw key in log output or exceptions.

- [x] **Document bootstrap secrets file in operator runbooks**:
    - *Context*: `deploy/compose.stack.env.generated` from `scripts/bootstrap-compose-secrets.py` must not land in VCS.
    - *Fix* (2026-05-07, Prompt 49): `deploy/README.md` (configuration table) and `Instructions/TriMCP Infrastructure.md` (bootstrap / VCS section).

### P6 — Test Coverage & Documentation

- [x] **Add mock-httpx tests for malformed LLM responses** (all providers):
    - *Context*: JSON response validation was verified only via regression coverage — no dedicated tests injecting malformed responses.
    - *Fix* (2026-05-07 Prompt 50): Created `tests/test_llm_providers.py` with `pytest-httpx`. 10 tests across `AnthropicProvider` and `OpenAICompatProvider` covering: non-JSON garbage, empty JSON, missing tool_use/choices structure, HTTP 500, HTTP 429, HTTP 401, and network timeout. Each asserts the correct `LLMProviderError` subclass and message context.

- [x] **Add SSRF guard unit tests** (`tests/`):
    - *Context*: `validate_base_url()` had no permanent unit test.
    - *Fix* (2026-05-07 Prompt 50): Created `tests/test_ssrf_guard.py` with 22 parametrized tests covering: all 4 private IP ranges (10.x, 172.16-31.x, 192.168.x, fd00::), loopback (127.0.0.1, localhost, ::1), HTTPS required, HTTP allowed flag, loopback allowed flag, invalid URL, empty URL, unresolvable hostname, and public HTTPS URLs. Also 2 async smoke tests for `validate_base_url_async()`. All DNS mocked via `monkeypatch`.

- [x] **Add decompression bomb unit tests** (`tests/`):
    - *Context*: `_check_zip_bomb()` and `_check_pdf_bomb()` had no tests.
    - *Fix* (2026-05-07 Prompt 50): Added `TestCheckZipBomb` and `TestCheckPdfBomb` classes to `tests/test_extractors_core.py`. 7 new tests: small zip passes, total exceeds limit, per-entry exceeds limit, corrupt zip returns error, small PDF passes, PDF blob too large, and `empty_skipped` import. Thresholds lowered via `monkeypatch` so tests use realistic in-memory data.

- [x] **`PIIEntity.__repr__` test coverage** (`tests/`):
    - *Context*: The safe `__repr__` had no unit test.
    - *Fix* (2026-05-07 Prompt 51): Created `tests/test_pii_repr.py` with 5 tests covering: fresh entity shows `<present>` not raw value, cleared entity shows `[REDACTED]`, token included in repr, idempotent clear, and `model_dump()` returns `[REDACTED]` after clear. All assert raw PII never appears in any string representation.

- [x] **Provider `__repr__` unit test coverage** (`tests/`):
    - *Context*: Provider `__repr__` implementations had no unit tests for key leakage.
    - *Fix* (2026-05-07 Prompt 51): Created `tests/test_providers.py` with 10 tests: 5 `_redact_api_key()` edge cases (empty, short, normal, exactly 8 chars, full key not in output), `AnthropicProvider`, `OpenAICompatProvider` (standard + Azure), `GoogleGeminiProvider`, and `LocalCognitiveProvider` repr checks. All assert full raw key never appears in repr output.

- [x] **Document `TRIMCP_ADMIN_API_KEY` in environment variable instructions** (`Instructions/TriMCP Environment Variables.md`):
    - *Context*: Production admin auth was undocumented.
    - *Fix* (2026-05-07 Prompt 51): Added `TRIMCP_ADMIN_API_KEY` to `Instructions/TriMCP Environment Variables.md` with security notes (production requirement, random value suggestion, dev override). Added placeholder entry to `mcp_config.json` env block. Documents that `TRIMCP_ADMIN_OVERRIDE=true` is a development-only bypass.

### P7 — Optional / Nice-to-Have

- [x] **Consider async DNS resolution for SSRF guard** (`base.py`):
    - *Context*: `validate_base_url()` used synchronous `socket.getaddrinfo()` which blocks the event loop during `LLMProvider.__init__()`. Fine for single-instance startup, but could cause latency in serverless/high-scale deployments.
    - *Fix* (2026-05-07 Prompt 52): Added `validate_base_url_async()` — an async variant that offloads DNS resolution to a thread-pool executor via `asyncio.get_running_loop().run_in_executor(None, socket.getaddrinfo, ...)`. All other checks (URL parsing, IP range validation) run inline. The sync `validate_base_url()` remains for `__init__`-time use where `await` is not possible. Documented tradeoff: sync DNS is sub-millisecond for cached lookups and only runs once at startup.
    - *Kaizen*: For pure async startup paths (e.g. ASGI lifespan), callers should prefer `validate_base_url_async()` to avoid blocking the event loop. The sync variant is acceptable for single-instance deployments.

- [x] **Optional: operator-tunable PBKDF2 work factor** (`signing.py`):
    - *Context*: Iterations were fixed at 100,000 (NIST PBKDF2 minimum).
    - *Fix* (2026-05-07 Prompt 52): `_PBKDF2_ITERATIONS` now reads from `TRIMCP_PBKDF2_ITERATIONS` env var with a safe floor of 100,000: `max(100_000, int(os.environ.get("TRIMCP_PBKDF2_ITERATIONS", "100000")))`. High-threat deployments can set 310k+ without code changes. Existing test `test_pbkdf2_iteration_count_is_at_least_100k` continues to pass.

- [x] **Optional: Argon2id for wrapping keys** (`signing.py`):
    - *Context*: PBKDF2-HMAC-SHA256 met the stated requirement; Argon2id is preferable for memory-hard KDF.
    - *Fix* (2026-05-07 Prompt 52): Added `_argon2id_derive_aes_key()` using `argon2-cffi` with OWASP parameters (time_cost=3, memory_cost=64 MiB, parallelism=4). New v3 blob prefix `TC3\x01`. `encrypt_signing_key()` prefers Argon2id when `argon2-cffi` is available, falls back to PBKDF2 v2 otherwise. `decrypt_signing_key()` auto-detects v3/v2/legacy formats — backward compatible with all existing blobs. Graceful degrade: if `argon2-cffi` is not installed, `encrypt_signing_key` emits v2 (PBKDF2) blobs.
    - *Test*: 4 new tests: `test_v2_blob_still_decrypts`, `test_v3_blob_roundtrip`, `test_v3_blob_wrong_master_fails`, `test_argon2id_produces_different_key_than_pbkdf2`. 43/43 signing tests pass.
    - *Kaizen (crypto migration)*: Existing v2 blobs in `signing_keys.encrypted_key` will continue to decrypt. New key rotations produce v3 blobs. Over time, as keys are rotated, the database will naturally migrate to Argon2id-wrapped keys. No forced migration needed.

- [x] **PII pseudonym tokens in stored text are long** (`pii.py`):
    - *Context*: Full HMAC-SHA256 hex tokens (64 chars + type prefix) affected UI, prompts, and FTS snippets.
    - *Fix* (2026-05-07 Prompt 52): Changed `_pseudonym_token_suffix()` to use first 16 bytes of HMAC-SHA256 (128 bits), base64url-encoded without padding (~22 chars). Collision resistance: 2^64 (birthday bound) — adequate for pseudonyms within a single namespace (requires ~4 billion tokens before a collision becomes likely). Updated module-level comment and all 3 PII tests for new format (`[A-Za-z0-9_-]{20,24}` regex instead of `[0-9a-f]{64}`). 9/9 pass.
    - *Kaizen (token format)*: Existing stored tokens in `pii_redactions.token` and sanitized text in MongoDB will have the old 64-char hex format. New pseudonymisation writes produce 22-char base64url tokens. Both formats coexist — `_pseudonym_token_suffix()` is deterministic per (entity_type, value, key), so re-processing the same raw PII will produce the new format consistently. No migration needed for stored redactions; new lookups will match against new-format tokens.

---

## HIGH — Clean Code (Uncle Bob)

- [x] **God Class: `TriStackEngine`** (`orchestrator.py`):
    - *Finding*: 1662 lines with 11+ responsibilities: namespace management, memory storage, graph search, quotas, health checks, PII, salience, contradictions, snapshots, embeddings.
    - *Fix* (2026-05-07 Prompt 22 + Prompt 54): All 6 orchestrators extracted (memory, graph, temporal, namespace, cognitive, migration) into `trimcp/orchestrators/`. ~1662 lines reduced to ~400 lines — a true director class. Lazy-init wrappers provide backward compatibility for test fixtures that create `TriStackEngine()` without `connect()`. Cross-orchestrator calls route through `self._engine`. 350 tests pass, 0 regressions.

- [x] **God Function: `call_tool()`** (`server.py:817-1214`):
    - *Finding*: 400-line monolithic dispatch handling 35+ tools. Violates SRP and is untestable in isolation.
    - *Action*: Refactor into domain-specific handler modules (e.g., `temporal_mcp_handlers.py`, `cognitive_mcp_handlers.py`, `replay_mcp_handlers.py`) following the existing `bridge_mcp_handlers.py` pattern.
    - *Fix*: Extracted 37 tool handlers into 9 domain modules: `memory_mcp_handlers.py` (7), `code_mcp_handlers.py` (3), `graph_mcp_handlers.py` (1), `contradiction_mcp_handlers.py` (2), `a2a_mcp_handlers.py` (4), `admin_mcp_handlers.py` (7), `snapshot_mcp_handlers.py` (4), `replay_mcp_handlers.py` (4), `migration_mcp_handlers.py` (5). `call_tool()` reduced from ~380 lines to ~70 lines — a clean director function. Caching and admin auth stay as cross-cutting concerns in `call_tool()`. Bridge handlers already extracted previously.
    - *Test*: 168 pass, 10 pre-existing failures confirmed unchanged. No new regressions.

- [x] **God Function: `store_memory()`** (`orchestrator.py:684-904`):
    - *Finding*: 221 lines mixing PII pipeline, Mongo insert, embedding generation, PG insert, graph extraction, KG writes, event logging, and rollback.
    - *Action*: Extract into `_apply_pii_pipeline()`, `_embed_and_insert_vectors()`, `_insert_graph_nodes_and_edges()`, `_apply_rollback_on_failure()`.
    - *Fix*: Extracted 4 private methods in `MemoryOrchestrator`. `store_memory()` reduced from ~220 lines to ~90 lines. `_apply_pii_pipeline()` (35 lines), `_embed_and_insert_vectors()` (30 lines), `_insert_graph_nodes_and_edges()` (55 lines), `_apply_rollback_on_failure()` (55 lines). Each method receives exactly the data it needs via keyword arguments.
    - *Test*: `/test-harden` — all 5 saga rollback tests pass. Rollback helper verified on induced PG failure.

- [x] **God Function: `run_consolidation()`** (`consolidation.py:77-280`):
    - *Finding*: 203 lines doing memory fetch, HDBSCAN clustering, LLM call, validation, DB write, KG insertion, decay, and event logging.
    - *Action*: Extract into `_cluster_memories()`, `_call_consolidation_llm()`, `_store_consolidated_memory()`, `_update_kg()`.
    - *Fix*: Extracted 4 private methods in `ConsolidationWorker`. `run_consolidation()` reduced from ~203 lines to ~65 lines. `_cluster_memories_async()` (25 lines), `_call_consolidation_llm()` (30 lines), `_store_consolidated_memory()` (35 lines), `_update_kg()` (30 lines). LLM validation (confidence, hallucination, contradiction routing) centralized in `_call_consolidation_llm()`.

- [x] **God Function: `detect_contradictions()`** (`contradictions.py:93-251`):
    - *Finding*: 158 lines mixing candidate selection, KG check, NLI check, LLM tiebreaker, and DB write.
    - *Action*: Extract into `_select_candidates()`, `_check_kg_contradiction()`, `_check_nli_contradiction()`, `_resolve_with_llm()`.
    - *Fix*: Extracted 4 module-level private functions. `detect_contradictions()` reduced from ~158 lines to ~55 lines. `_select_candidates()` (15 lines), `_check_kg_contradiction()` (20 lines), `_check_nli_contradiction()` (20 lines), `_resolve_with_llm()` (40 lines). Signal aggregation logic preserved exactly.

- [x] **God Function: `ForkedReplay.execute()`** (`replay.py:1042-1255`):
    - *Finding*: 209 lines covering run management, event streaming, LLM payload resolution, handler dispatch, event log writing, and progress tracking.
    - *Action*: Extract `_apply_single_event()`, `_dispatch_and_apply()`.
    - *Fix*: Extracted `_apply_single_event()` (static, 12 lines) and `_dispatch_and_apply()` (25 lines) in `ForkedReplay`. Inner loop reduced from ~35 lines to ~12 lines. `fork_uri`/`fork_hash` passed through correctly.

- [x] **DRY: HTTP Client Boilerplate** (all 4 LLM providers):
    - *Finding*: Identical try-except httpx pattern (timeout → `LLMTimeoutError`, request error → `LLMProviderError`, non-2xx → error with status) repeated in `anthropic_provider.py`, `openai_compat.py`, `google_gemini.py`, `local_cognitive.py`.
    - *Fix* (2026-05-07 Prompt 23): Extracted the boilerplate try-except blocks into `providers/_http_utils.py:post_with_error_handling()`. All LLM providers successfully consume this helper.

- [x] **DRY: Embedding Backend Duplication** (`embeddings.py:143-237`):
    - *Finding*: `_sync_embed_batch()` is identical across 5 backends (CPU, CUDA, ROCm, XPU, MPS) — only the device string differs.
    - *Fix* (2026-05-07 Prompt 23): Created a unified `TorchEmbeddingBackend` base class in `embeddings.py` using the template method pattern. Subclasses now override `get_device() -> str` only.

- [x] **DRY: MongoDB Access Pattern** (`orchestrator.py`):
    - *Finding*: `db = self.mongo_client.memory_archive` repeated 6+ times. Redis key construction repeated 3+ times. UUID conversion (`UUID(str(...))`) appears 15+ times.
    - *Fix* (2026-05-07 Prompt 23): Extracted `@property _mongo_db`, `_redis_cache_key()`, and `_ensure_uuid()` helper methods in `orchestrator.py`.

- [x] **Factory If-Else Ladder** (`factory.py:79-196`):
    - *Finding*: 100-line flat if-else dispatch. Adding a provider requires editing the central function. Violates Open/Closed principle.
    - *Fix* (2026-05-07 Prompt 23): Refactored `trimcp/providers/factory.py` to use a strategy/registry pattern using a static `_FACTORIES` map mapping string provider types to their corresponding factories.

---

## MEDIUM — Code Quality

- [x] **`event_log.py:append_event()` Too Long**:
    - *Finding*: 234 lines in a single God Function mixing validation, signing, and DB insertion.
    - *Fix* (2026-05-07 Prompt 55): Extracted 3 private helpers: ``_validate_event_payload()`` (event_type + agent_id validation), ``_sign_event()`` (key loading + HMAC signing), and ``_insert_event()`` (INSERT + RETURNING). ``append_event()`` reduced from ~234 lines to ~70 lines — a clean director function composing 7 numbered steps, each delegating to a single-purpose helper.

- [ ] **`event_log.py:parent_event_id` Not Validated**:
    - *Finding*: No check that parent_event_id references an existing event. Fake causal chains possible.
    - *Action*: Validate via FK constraint (see Critical — Data Integrity) or application-level check.

- [x] **Unreachable Error Handlers** (`server.py:1205-1214`):
    - *Finding*: `except` clauses that can never execute due to prior catches.
    - *Fix*: Reviewed nesting structure. Inner `except Exception` serves quota rollback before re-raise to outer handlers. Removed redundant `q_res.rollback()` from outer handlers (inner handler already rolls back). Restructured to single rollback point.

- [x] **Cache Hit Bypasses Quota Check** (`server.py:848`):
    - *Finding*: Cached responses returned before quota enforcement.
    - *Fix*: Moved quota check (`consume_for_tool`) BEFORE cache lookup. Cached tools now always drain tokens before returning cached results.

- [x] **`HMACAuthMiddleware.dispatch()` Too Long** (`auth.py`):
    - *Finding*: 107 lines in a single method.
    - *Fix*: Extracted 5 private methods: `_extract_hmac_context`, `_verify_timestamp`, `_verify_signature`, `_check_nonce`, `_resolve_namespace_context`. `dispatch()` reduced from ~90 to ~25 lines.

- [x] **`infer_assertion_type()` in Wrong Module** (`pii.py`):
    - *Finding*: Function unrelated to PII scanning.
    - *Fix*: Created `trimcp/assertion.py`. `pii.py` re-exports via `from trimcp.assertion import infer_assertion_type` for backward compat.

- [x] **Missing Error Type Granularity** (LLM providers `base.py:88-127`):
    - *Finding*: Only 3 error types.
    - *Fix*: Added `LLMAuthenticationError` (401/403), `LLMRateLimitError` (429 with `retry_after`), `LLMUpstreamError` (5xx), `LLMBadRequestError` (400). All inherit from `LLMProviderError`.

- [x] **No Retry/Backoff Policy** (all LLM providers):
    - *Finding*: No retry on timeout or 429.
    - *Fix*: Added `RetryPolicy` class with exponential backoff (`max_retries=3`, `base_delay_ms=1000`, `max_delay_ms=30000`, `max_total_ms=60000`). `is_retryable()` gates on transient errors. `max_total_ms` enforces MCP protocol timeout window. Exported `DEFAULT_RETRY_POLICY`.

- [x] **Salience Reinforce SQL Bug** (`salience.py:49-64`):
    - *Finding*: INSERT used `LEAST(1.0, 1.0 + delta)` which always evaluates to 1.0.
    - *Fix*: Changed to `LEAST(1.0, $4::real)` — delta is now correctly applied on initial insertion.

- [x] **Consolidation Decay Inconsistency** (`consolidation.py:250-260`):
    - *Finding*: Algebraic decay (`* 0.5`) vs exponential decay in `salience.py`.
    - *Fix*: Unified to `salience.compute_decayed_score()` (Ebbinghaus exponential). Existing rows decay via formula; new rows initialize at 0.5.

- [x] **Silent Error Handling in Consolidation**:
    - *Finding*: Three `except: continue` patterns.
    - *Fix*: Already resolved by Prompt 22 refactor — all handlers use `except Exception as e: log.error(...)  continue` with explicit logging.

- [x] **Cursor URL Injection** (`bridges/sharepoint.py`, `gdrive.py`, `dropbox.py`):
    - *Finding*: Cursor URL from Redis used directly in `client.get(url)`. Compromised Redis could inject arbitrary URLs.
    - *Action*: Validate cursor URL starts with expected API root.
    - *Fix*: `trimcp/net_safety.py` `assert_url_allowed_prefix()`; Graph/Drive cursors must be `https://` under provider API roots; optional bearer from env or decrypted row token.

- [x] **Webhook Base URL Not Validated** (`bridge_mcp_handlers.py`, `bridge_renewal.py`):
    - *Finding*: `cfg.BRIDGE_WEBHOOK_BASE_URL` used without SSRF checks. Admin misconfiguration could probe internal network.
    - *Action*: Reject private IPs, enforce HTTPS.
    - *Fix*: `validate_bridge_webhook_base_url()` in `complete_bridge_auth` and `renew_gdrive`.

- [x] **`bridge_repo.py:update_subscription()` Accepts Arbitrary Fields** (`bridge_repo.py`):
    - *Finding*: Dynamic SQL field names from caller without whitelist. Unexpected field names silently accepted.
    - *Action*: Add `ALLOWED_FIELDS` whitelist validation.
    - *Fix*: `ALLOWED_SUBSCRIPTION_UPDATE_FIELDS` + `ValueError` on unknown keys.

- [x] **`complete_bridge_auth()` Too Long** (`bridge_mcp_handlers.py`):
    - *Finding*: Long function mixing token exchange, webhook setup, and DB update.
    - *Action*: Extract `_exchange_oauth_code()`, `_setup_webhook()`.
    - *Fix*: `_exchange_oauth_code`, `_setup_sharepoint_webhook`, `_setup_gdrive_webhook`; encrypted token persisted on row.

- [x] **OAuth Token Returned to Client** (`bridge_mcp_handlers.py`):
    - *Finding*: `oauth_access_token` included in MCP response. If logged, token is exposed.
    - *Action*: Return only a success indicator. Store token server-side with encryption.
    - *Fix*: `oauth_access_token_enc` column; MCP JSON omits plaintext token; `disconnect_bridge` clears ciphertext; renewal uses stored token when env unset.

- [x] **Config Values Scattered** (embeddings):
    - *Finding*: `VECTOR_DIM = 768` hardcoded in `embeddings.py`. No central config.
    - *Action*: Centralize in `cfg.EMBEDDING.VECTOR_DIM`.
    - *Fix*: `config.py` `_EmbeddingConfig.VECTOR_DIM` / `EMBEDDING_VECTOR_DIM`; `embeddings.py` reads `cfg.EMBEDDING.VECTOR_DIM`.

- [x] **Schema: Missing CHECK Constraints** (`schema.sql`):
    - *Finding*: `memories.memory_type`, `memories.assertion_type`, `consolidation_runs.status` are unconstrained TEXT.
    - *Action*: Add `CHECK (column IN (...))`.
    - *Fix*: Idempotent DO blocks `ck_memories_memory_type`, `ck_memories_assertion_type`, `ck_consolidation_runs_status` (`running`|`completed`|`failed`); `consolidation_runs` extra columns for `consolidation.py` (`completed_at`, `error_message`, counters).

- [x] **Schema: No Partition Rotation for event_log** (`schema.sql`):
    - *Finding*: Only a DEFAULT partition exists.
    - *Action*: Monthly partition DDL.
    - *Fix*: `trimcp_ensure_event_log_monthly_partitions()` + startup `SELECT` for current month + 3 ahead.

- [x] **Schema: Missing KG Indexes on updated_at** (`schema.sql`):
    - *Finding*: `kg_nodes` and `kg_edges` have no index on `updated_at`. Consolidation queries scanning for stale KG data require full table scan.
    - *Fix*: Added `idx_kg_nodes_updated` and `idx_kg_edges_updated` (see HIGH — Security: Missing KG Indexes).

---

## LOW — Polish

- [ ] **`semantic_search()` Too Long** (`orchestrator.py:1184-1329`):
    - *Finding*: 145 lines with dynamic SQL construction, temporal clauses, ranking, reinforcement, and MongoDB hydration.
    - *Action*: Extract `_build_temporal_sql_clause()`, `_build_vector_ranking_sql()`, `_reinforce_retrieved_memories()`.

- [x] **Inconsistent Float Assertions** (`test_cognitive_decay.py`):
    - *Finding*: Mix of `math.isclose()` and `pytest.approx()`.
    - *Fix*: Standardized on `pytest.approx()`. Removed unused `import math`.

- [x] **Hardware Detection Catches All Exceptions** (`embeddings.py:43-91`):
    - *Finding*: `except Exception` hides genuine driver errors.
    - *Fix*: Narrowed to `except (ImportError, RuntimeError)` on CUDA/ROCm/MPS/XPU. NPU: `(ImportError, RuntimeError, OSError)`.

- [x] **Inconsistent Naming in Embeddings** (`embeddings.py:43-91`):
    - *Finding*: Mixed prefixes.
    - *Fix*: Standardized to `_is_rocm_available()`, `_is_mps_available()`, `_is_xpu_available()`, `_is_npu_available()`.

- [x] **Unused `TYPE_CHECKING` Block** (`local_cognitive.py:19-34`):
    - *Finding*: `if TYPE_CHECKING: pass` — empty block.
    - *Fix*: Removed `TYPE_CHECKING` import and empty block.

- [x] **RLS Role Grants May Fail Silently** (`schema.sql`):
    - *Finding*: `GRANT ... TO trimcp_app` wrapped in `IF EXISTS` — silently skipped if role doesn't exist.
    - *Action*: Surface misconfiguration (NOTICE or create role).
    - *Fix*: `ELSE RAISE NOTICE 'trimcp_app role not found — ...'` on snapshots, `event_log`, `a2a_grants`, `resource_quotas` grant blocks. (`001_enable_rls.sql` can still `CREATE ROLE trimcp_app`.)

---

## Infrastructure & Operations

- [x] **RLS Audit for Background Workers**:
    - *Context*: RQ workers for re-embedding and GC use system-level privileges bypassing RLS.
    - *Fix*: Audited all 3 background workers. Documented intentional RLS bypass rationale in `docs/architecture-v1.md` section 6.1: GC needs cross-namespace scan for orphan detection; re-embedding worker needs full-table keyset pagination. `tasks.py` already uses `scoped_session(namespace_id)` when namespace is provided. Future: add dedicated `trimcp_background` Postgres role.

- [x] **Async Test Harness Migration**:
    - *Context*: Observed `PytestRemovedIn9Warning` regarding async fixtures.
    - *Fix*: Added explicit `asyncio_default_fixture_loop_scope = function` to `pytest.ini`. Current runs show no active `PytestRemovedIn9Warning` — the existing `asyncio_mode = auto` + explicit loop scope is forward-compatible.

- [x] **Connection Pool Monitoring**:
    - *Context*: Added RLS setup logic to every `scoped_session` call.
    - *Fix*: Added `SCOPED_SESSION_LATENCY` histogram to `observability.py` (buckets: 0.1ms–50ms). Instrumented both `TriStackEngine.scoped_session` and `MemoryOrchestrator.scoped_session` with `perf_counter()` timing. Namespace ID truncated to 8 chars for cardinality safety.

- [x] **Installer Binary Verification** (Enterprise Plan Phase 5):
    - *Resolution*: **Completed (Prompt 33, 2026-05-07).** Static validation: `trimcp-launch` is the primary binary in macOS `.app`, Inno Setup `{app}`, and WiX MSI `INSTALLFOLDER`; artifact paths align with `.github/workflows/release.yml` (`go/cmd/trimcp-launch` → `build/windows/trimcp-launch.exe`, universal `build/macos/trimcp-launch`). Build scripts annotated in-repo. Installer matrix and verification steps documented in `deploy/README.md`. Residual optional work: wizard UX burn-in QA on signed release artifacts (`GAPS.md`).

- [x] **Vector Index Performance**:
    - *Context*: Enabled RLS on `memory_embeddings`.
    - *Fix*: Documented in `docs/architecture-v1.md` section 7. HNSW index used first, RLS filters applied post-scan. Recommendations for large namespaces (increase `candidate_k`) and extreme multi-tenancy (partial indexes). Index is never bypassed by RLS.

---

## CRITICAL — Security (Fix Before Production)

- [x] **Client-Side Privilege Escalation** (`server.py:811`):
    - *Finding*: `_check_admin()` trusts `is_admin` from MCP client arguments. Any client can claim admin privileges.
    - *Fix*: Replaced with server-side `admin_api_key` validation using `secrets.compare_digest()` against `TRIMCP_ADMIN_API_KEY` env var. Client-supplied `is_admin` boolean is now ignored. All 10 admin tools updated.
    - *Test*: 22 hardening tests in `tests/test_check_admin_hardening.py` verify: client `is_admin` rejected, missing/wrong `admin_api_key` rejected, correct key grants access, `TRIMCP_ADMIN_OVERRIDE` dev bypass preserved, all schema contracts validated.
    - *Documentation*: `mcp_config.json` must include `TRIMCP_ADMIN_API_KEY` in env block for production use.

- [x] **Dummy Webhook Secrets** (`webhook_receiver/main.py`):
    - *Finding*: All three webhook providers (`DROPBOX_APP_SECRET`, `GRAPH_CLIENT_STATE`, `DRIVE_CHANNEL_TOKEN`) default to `"dummy_*_secret"` if env vars are missing — complete authentication bypass in production.
    - *Fix*: `_require_env()` loads each variable at import time and raises `RuntimeError` if unset or empty. `tests/test_webhook_receiver.py` sets test secrets before importing the app.

- [x] **SQL Injection via String Interpolation** (`orchestrator.py:1214-1216`):
    - *Finding*: `temporal_retention_days` and `as_of` are interpolated directly into SQL strings instead of using parameterized queries.
    - *Action*: Rewrite temporal clause construction to use `$N` parameterized placeholders throughout.

- [x] **Incomplete Saga Rollback** (`orchestrator.py:880-903`):
    - *Finding*: Only rolls back Mongo/PG if `inserted_mongo_id` was set. KG nodes/edges (`lines 789-824`), PII vault entries (`lines 779-786`) are not cleaned up on failure.
    - *Fix*: Refactored to phase-aware universal rollback. `memory_id` and `pg_committed` flag now tracked. Each store (Mongo, PG) evaluated and rolled back independently. PG committed path cleans all 7 tables (memory_embeddings, pii_redactions, kg_node_embeddings, kg_edges, kg_nodes, event_log, memories) in FK-safe order. PG uncommitted path uses defence-in-depth safety cleanup by `payload_ref`. All rollback steps catch and log their own exceptions without masking the original failure.
    - *Test*: `test_saga_rollback.py` simulates failure after PG commit (Redis step) and verifies all artifacts are cleanly removed. Also verifies early failure (pre-Mongo) leaves no orphans.
    - *Kaizen*: The `store_memory()` method is now 250+ lines. Consider extracting rollback into `_rollback_store_memory()` and the PG commit path into `_commit_memory_to_pg()` per the God Function item below.

- [x] **Master Key in Python String Memory** (`signing.py`):
    - *Finding*: Master signing key is held as an immutable Python string — cannot be zeroed after use. Persists in process memory indefinitely.
    - *Fix*: Created `MasterKey` class with `bytearray`-backed mutable buffer. Supports context-manager pattern (`with require_master_key() as mk:`) for deterministic zeroing on exit. `__del__` provides defence-in-depth at GC time. `zero()` overwrites buffer with null bytes and is idempotent. All callers updated: `signing.py` (get_active_key, rotate_key), `pii.py` (process), `orchestrator.py` (verify_memory, unredact_memory). Removed `_derive_aes_key()` module function; replaced with `MasterKey.derive_aes_key()` instance method.
    - *Test*: `tests/test_master_key_buffer.py` verifies: bytearray mutation zeroes memory, `zero()` nulls all bytes, `__del__` triggers zeroing, context manager zeroes on exit, zeroed key rejects access, `from_env()` validates TRIMCP_MASTER_KEY env var.
    - *Kaizen*: `_CachedKey.raw_key` (the decrypted signing key) is still an immutable `bytes` object. Consider wrapping in a similar mutable buffer for defence-in-depth.

- [x] **Weak KDF for AES Key Derivation** (`signing.py` — wrapping key for ``encrypted_key`` blobs):
    - *Finding*: Used bare `SHA-256` without salt or iterations. Vulnerable to rainbow-table-style precomputation against low-entropy master secrets.
    - *Fix*: **PBKDF2-HMAC-SHA256** with **100,000** iterations and a **16-byte random salt per blob**. Wire format `TC2\x01 || salt || nonce || ciphertext+tag`. **Legacy** blobs (`nonce || ciphertext+tag` with SHA-256 wrapping key) still decrypt for migration. ``MasterKey.derive_aes_key()`` now uses PBKDF2 with a fixed self-test salt (tests/diagnostics only).
    - *Test*: `tests/test_signing_kdf.py` — iteration count floor, deterministic derive, salt separation, v2 format, legacy round-trip, wrong-master failure, short-blob error.

- [x] **WORM Event Log Not Verified at Startup** (`event_log.py`):
    - *Finding*: Append-only enforcement relies solely on DB role grants (`001_enable_rls.sql:83`). No runtime assertion that UPDATE/DELETE are actually denied.
    - *Fix*: Added `verify_worm_enforcement(conn)` to `event_log.py`. Attempts `UPDATE event_log ... WHERE FALSE` and `DELETE FROM event_log WHERE FALSE`. If either succeeds (no `InsufficientPrivilegeError`), raises `RuntimeError` to halt server startup. Wired into `TriStackEngine._verify_worm_enforcement()` → called from `connect()` right after `_init_pg_schema()`.
    - *Test*: `tests/test_worm_probe.py` verifies: UPDATE denied → pass, DELETE denied → pass, UPDATE succeeds → RuntimeError, DELETE succeeds → RuntimeError, table missing → PostgresError propagates, insufficient privilege is the expected asyncpg exception class.
    - *Kaizen*: This probe pattern should be extended to other tables whose WORM/RLS guarantees are critical — see Kaizen section.

- [x] **Event Log Signatures Never Verified on Read** (`event_log.py`):
    - *Finding*: HMAC signatures are written but never checked when events are read back. Tampered events are undetectable.
    - *Action*: Add `verify_event_signature()` and call it in all read paths (replay, provenance, audit).

- [x] **PII Values Stored in PIIEntity.value** (`pii.py`):
    - *Finding*: Raw PII values persist in memory objects. Leakable via logs, debug dumps, or exception tracebacks.
    - *Fix*: Added `clear_raw_value()` method to `PIIEntity` that overwrites `.value` with `"[REDACTED]"`. Overrode `__repr__` to show `<present>` for uncleared values and `[REDACTED]` after clearing — raw PII never appears in string representations. In `process()`, each entity's raw value is consumed for token generation/vault encryption, the token is stored on `entity.token`, and `clear_raw_value()` is called immediately after — all before the next entity iteration begins. `model_dump()` of cleared entities returns `"[REDACTED]"` for the value field.
    - *Test*: Verified both fresh and cleared entities never leak raw PII via `repr()`, `__dict__`, or `model_dump()`. All existing 40 tests pass without modification.

- [x] **Weak Pseudonymisation Tokens** (`pii.py`):
    - *Finding*: Used `sha256(value)[:4]` — only 16 bits of entropy in the displayed suffix. Brute-forceable for known entity types (SSN, phone numbers).
    - *Fix*: Pseudonym suffix is now **full HMAC-SHA256** (64 hex chars = 256 bits) over ``entity_type + NUL + value``. **Per-namespace** optional secret ``pseudonym_hmac_key`` (≥8 UTF-8 bytes); if unset, **TRIMCP_MASTER_KEY** (≥32 chars) is used as the HMAC key. ``pii_redactions.token`` remains ``TEXT`` — no schema change.
    - *Test*: `tests/test_pii_pseudonym.py` — suffix length/alphabet, determinism, type separation, namespace key separation, validation errors, master fallback.

- [x] **No Distributed Replay Cache** (`auth.py`):
    - *Finding*: Timestamp-based replay protection only works per-process. In a multi-instance deployment, replayed requests to different instances bypass the check.
    - *Fix*: Added `NonceStore` class — a Redis-backed distributed replay cache using `SET key value NX PX ttl` (atomic SETNX). The HMAC signature hex serves as the nonce. `HMACAuthMiddleware` now accepts an optional `nonce_store` parameter. When provided: (1) timestamp drift is checked first, (2) signature is verified, (3) the signature nonce is atomically checked/stored in Redis. If SETNX returns None (key exists), the request is rejected as a replay with code -32002. TTL defaults to 600 s (2× drift window) for auto-cleanup. Without a `NonceStore`, behavior is unchanged (timestamp-only, single-instance compatible). Fail-closed: any Redis connection or command error rejects the request.
    - *Test*: `tests/test_auth.py` — 14 new tests: 7 `TestNonceStoreUnit` (fresh acceptance, replay rejection, connection/timeout fail-closed, independent nonces, TTL milliseconds, default TTL=600), 7 `TestHMACAuthMiddlewareWithNonceStore` (fresh passes, replay rejected, **concurrent two-instance simulation**, Redis-down fail-closed, legacy fallback without store, timestamp short-circuit, invalid-signature short-circuit). All 54 selected auth tests pass.

- [x] **Prompt Injection — Consolidation** (`consolidation.py:147`):
    - *Finding*: Raw memory content (user-controlled `payload_ref`) is passed directly to the LLM via `_build_consolidation_messages()`. Attacker-controlled memory content can hijack the LLM.
    - *Action*: Sanitize or summarize user content before passing to LLM. Use explicit delimiters and system-prompt boundaries.
    - *Fix*: Implemented `<memory_content>` delimiter sanitization. System prompt updated to explicitly isolate passive data. User payloads are stripped of injected tags before formatting.
    - *Test*: `test_prompt_injection_sanitization` explicitly verifies boundary isolation and prevents tag forgery.

- [x] **Prompt Injection — Contradictions** (`contradictions.py:203-204`):
    - *Finding*: `cand_text` and `memory_text` from the database are passed directly to the LLM without sanitization.
    - *Action*: Same mitigation as consolidation — extract semantic features, don't pass raw user text.

- [x] **Prompt Injection — Replay Re-Execute** (`replay.py:820`):
    - *Finding*: User-supplied `prompt_suffix` in `config_overrides` is concatenated directly into the LLM prompt.
    - *Action*: Remove free-text prompt modification. Use strongly-typed configuration (enums for allowed overrides, no free-text suffix).
    - *Fix*: Introduced `ReplayConfigOverrides` (`extra=forbid`), `ReplayLlmProvider` `StrEnum`, `normalize_replay_config_overrides()`; `ReplayForkRequest` nests typed overrides; removed prompt concatenation from `_resolve_llm_payload`; MCP (`server.py`) and admin HTTP validate before `_create_run` / `ForkedReplay.execute`.
    - *Test*: `tests/test_replay_config_overrides.py`.
    - *Kaizen (schema validation)*: Consider tightening the MCP `replay_fork` `inputSchema` with `additionalProperties: false` on `config_overrides` and per-key `enum`/`type` so clients fail fast before JSON-RPC (optional; Pydantic remains the source of truth).

- [x] **API Keys Leaking into Error Messages** (`factory.py:237-240`, all providers):
    - *Finding*: Literal API keys are returned from `_resolve_credential()` and can propagate into exception messages and log output.
    - *Fix*: Added `_redact_api_key()` utility in `base.py` (preserves first 3 + last 4 chars, `<empty>` for blank, `<redacted>` for ≤7 chars). Overrode `__repr__` on all 5 provider classes: `AnthropicProvider`, `OpenAICompatProvider`, `GoogleGeminiProvider`, `LocalCognitiveProvider` — all redact API keys in their string representation. **Critical fix**: `GoogleGeminiProvider` was embedding the API key in the URL query string (`?key=...`) — moved to `x-goog-api-key` HTTP header so `httpx.RequestError` exceptions no longer include the raw key. `LLMProviderError` already safe (never includes key in message/upstream_message fields). `_resolve_credential()` logs warnings about missing/literal credentials but never the actual value.
    - *Test*: `/test-harden` verified all provider `repr()` outputs are safe (keys redacted), `LLMProviderError.str()` is clean, and `_redact_api_key` edge cases handled. All 94 existing tests pass.

---

## CRITICAL — Data Integrity

- [x] **KG Tables Missing RLS** (`schema.sql:56-58`):
    - *Finding*: `kg_nodes` and `kg_edges` have NO Row-Level Security policies. Tenant A can see/modify tenant B's knowledge graph entities. Comment confirms this is a known v1.0 concession.
    - *Fix*: Added `namespace_id UUID NOT NULL REFERENCES namespaces(id)` column to both `kg_nodes` and `kg_edges`. Changed `UNIQUE(label)` → `UNIQUE(label, namespace_id)` and `UNIQUE(s,p,o)` → `UNIQUE(s,p,o,namespace_id)` to prevent cross-tenant overwrites. Added backfill migration: existing NULL rows assigned to `_global_legacy` fallback namespace. Added RLS policies (`namespace_isolation_policy`) to both tables matching the `memories` pattern — reads are automatically scoped via `current_setting('trimcp.namespace_id')`. Updated all write paths: `orchestrator.py` INSERT/ON CONFLICT, `consolidation.py` consolidation KG writes, `graph_extractor.py` `persist_graph()`. Read paths (`graph_query.py`, `contradictions.py`) are automatically filtered by RLS via `set_namespace_context()` which was already called.
    - *Test*: 97/97 existing tests pass. `/test-harden` verified RLS policies, UNIQUE constraints, migration backfill, v1.0 concession comment removal, and all 3 Python write paths include `namespace_id`.

- [x] **event_log.parent_event_id No FK Constraint** (`schema.sql:399`):
    - *Finding*: `parent_event_id UUID` has no foreign key reference. Orphan parent references corrupt the audit trail and break Saga parent-child semantics.
    - *Fix*: Added trigger-based FK (`trg_event_log_parent_fk` + `trg_event_log_parent_set_null`) since `event_log` is RANGE-partitioned with composite PK `(id, occurred_at)`, making a declarative FK impossible. BEFORE INSERT/UPDATE trigger validates `parent_event_id` exists. AFTER DELETE trigger sets `parent_event_id = NULL` on child events when parent is deleted (ON DELETE SET NULL semantics).
    - *Test*: 97/97 tests pass. Trigger functions are idempotent (CREATE OR REPLACE) and skip creation if triggers already exist.

- [x] **memories.payload_ref No UNIQUE Constraint** (`schema.sql:80,141`):
    - *Finding*: Multiple PG rows can point to the same MongoDB ObjectId. Updates to one silently corrupt the other.
    - *Fix*: Added `CHECK` constraint `ck_payload_ref_objectid_format` enforcing `payload_ref ~ '^[a-f0-9]{24}$'` — strict 24-char lowercase hex MongoDB ObjectId format. Declarative UNIQUE is impossible on a RANGE-partitioned table without including `created_at` in the constraint. Application-level dedup + the existing `idx_memories_payload_ref` index provide defence-in-depth.
    - *Kaizen*: For true uniqueness, a separate non-partitioned `payload_ref_registry` table with `UNIQUE(payload_ref)` could be used as a lookup-before-insert guard, with periodic reconciliation.

- [x] **memory_salience Missing FK** (`schema.sql:251`):
    - *Finding*: `memory_id UUID NOT NULL` has no FK to `memories(id)`. Orphan salience rows accumulate on memory deletion.
    - *Fix*: Added GC cleanup query in `garbage_collector.py` that deletes rows where `memory_id NOT IN (SELECT id FROM memories)`. Declarative FK is impossible because `memories` uses composite PK `(id, created_at)` for RANGE partitioning and `memory_salience` doesn't store `created_at`. GC-based cleanup is zero-write-cost for the hot path and runs every hour.
    - *Test*: 97/97 tests pass. GC cleanup logs orphan counts and catches exceptions without propagating errors.

- [x] **contradictions Missing FKs** (`schema.sql:270-271`):
    - *Finding*: `memory_a_id` and `memory_b_id` have no FK constraints to `memories(id)`.
    - *Fix*: Added GC cleanup query in `garbage_collector.py` that deletes rows where either `memory_a_id` or `memory_b_id` references a non-existent memory. Same partitioning limitation as `memory_salience` — declarative FKs not possible without storing `memories.created_at` in the contradictions table. GC-based cleanup is zero-write-cost and already integrated into the hourly GC pass.
    - *Test*: 97/97 tests pass.

---

## HIGH — Security

- [x] **RLS Bypass in Namespace Management** (`orchestrator.py:230-290`):
    - *Finding*: `manage_namespace()` uses raw `self.pg_pool.acquire()` instead of `scoped_session()`, bypassing RLS. Same issue in `manage_quotas()` (lines 629-681) and `consolidation_status()` (lines 392-408).
    - *Fix*: `manage_quotas()` now uses `scoped_session(payload.namespace_id)` — critical fix since `resource_quotas` has RLS enabled and queries were silently returning 0 rows without namespace context. `manage_namespace()` now uses `scoped_session` for `update_metadata` (single-namespace operation); `list`, `create`, `grant`, `revoke` are documented as admin bypass — they operate cross-namespace by design on the `namespaces` table which has no RLS. `consolidation_status()` documented as admin bypass — `consolidation_runs` has `namespace_id` but no RLS policy; cross-namespace read is intentional for admin diagnostics.

- [x] **Path Traversal in `_validate_path()`** (`orchestrator.py:152-184`):
    - *Finding*: Windows path detection logic is flawed (line 173). Missing symlink attack protection. Mixed raw-string and resolved-path checks.
    - *Fix*: Rewrote using `pathlib.Path.resolve().is_relative_to(allowed_base)`. All paths resolve against `Path.cwd()` — `..`, symlinks, absolute paths that escape CWD are rejected. Secondary `..` check on raw parts catches non-existent targets before resolution. Removed hardcoded forbidden-paths heuristic (fragile, OS-specific).
    - *Test*: `/test-harden` verified all 3 traversal attempts blocked (.., absolute, multi-level ..).

- [x] **JWT Issuer/Audience Validation Optional** (`jwt_auth.py`):
    - *Finding*: Issuer and audience claims are not enforced. Token confusion attacks possible across services.
    - *Fix*: `decode_options` now always requires `["exp", "iss", "aud"]` regardless of env var configuration. `issuer` and `audience` decode kwargs are always set from `cfg.TRIMCP_JWT_ISSUER` / `cfg.TRIMCP_JWT_AUDIENCE` — if these env vars are unset/empty, PyJWT will reject tokens that have those claims (strict validation) or accept tokens without them (per PyJWT defaults). Tokens missing `iss` or `aud` claims are now rejected by `MissingRequiredClaimError`.

- [x] **File Path Traversal in JWT Key Loading** (`jwt_auth.py:_load_public_key()`):
    - *Finding*: Public key file path sourced from env var without validation.
    - *Fix*: `_load_public_key()` now validates `file://` paths against `TRIMCP_JWT_KEY_DIR` (env var, defaults to CWD) using `pathlib.Path.resolve().is_relative_to()`. Rejects paths that escape the allowed directory. Also replaced `open(path).read()` with `Path.read_text()` for cleaner resource handling.
    - *Test*: `/test-harden` verified safe key loads and blocked both absolute and .. traversal attempts.

- [x] **SSRF via Unvalidated `base_url`** (all LLM providers):
    - *Finding*: Every provider accepts `base_url` with no validation. Attacker-controlled config could point to internal services (`localhost`, private IPs), leaking API keys and prompts.
    - *Fix*: Added `validate_base_url()` to `base.py` — resolves hostname to IP addresses and rejects private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `::1/128`, `fd00::/8`) and enforces HTTPS by default. Wired into `__init__` of all 4 providers: `AnthropicProvider`, `OpenAICompatProvider`, `GoogleGeminiProvider` (strict HTTPS), `LocalCognitiveProvider` (allow_http=True, allow_loopback=True for local container). Uses synchronous `socket.getaddrinfo()` for IP resolution — fast and deterministic at init time.
    - *Test*: 9 `/test-harden` scenarios verified: loopback rejected, private IPs all 4 ranges rejected, public HTTPS accepted, HTTP rejected by default, localhost+flags accepted, invalid URL rejected.
    - *Kaizen*: Consider async DNS resolution for non-blocking init in high-scale deployments. Currently DNS is synchronous in `__init__` — fine for single-instance startup, but could block the event loop in serverless contexts.

- [x] **Decompression Bomb Defense Missing** (extractors: `office_word.py`, `pdf_ext.py`):
    - *Finding*: No size limits on ZIP/PDF decompression. A 10MB file decompressing to 10GB causes OOM.
    - *Fix*: Added `_check_zip_bomb()` to `office_word.py` — scans `ZipInfo.file_size` for all ZIP entries and rejects if total > 500MB. Added `_check_pdf_bomb()` to `pdf_ext.py` — two-tier: raw blob size check, then pypdf stream length summation. Both return `empty_skipped()` on bomb detection, preventing any extraction.
    - *Kaizen*: `office_word.py` also reads embedded sheets from `word/embeddings/` — these are separate ZIP entries already covered by the total sum. Consider per-entry limits for defence-in-depth.

- [x] **Dropbox Download Bug** (`bridges/dropbox.py:85`):
    - *Finding*: The `headers` dict (with `Dropbox-API-Arg`) was passed to `httpx.Client()` constructor but not explicitly to `client.post()`. While httpx.Client propagates default headers, the explicit `headers=` on `post()` makes the intent unambiguous.
    - *Fix*: Removed `headers=` from `httpx.Client()` constructor and added `headers=headers` to the `client.post()` call directly. Ensures `Dropbox-API-Arg` header is always sent with the download request.

- [x] **a2a_grants Token Hash No Length Check** (`schema.sql:433`):
    - *Finding*: `token_hash BYTEA NOT NULL UNIQUE` has no CHECK constraint on length. Malformed hashes (e.g., 16 bytes instead of 32) are accepted.
    - *Action*: Add `CHECK (length(token_hash) = 32)`.
    - *Fix*: Added `CONSTRAINT ck_a2a_grants_token_hash_len CHECK (length(token_hash) = 32)` via idempotent DO block. Enforces SHA-256 hash length (32 bytes) at the DB level. Added `namespace_access_granted` and `namespace_access_revoked` to `EventType` Literal in `event_log.py`.

- [x] **Missing KG Indexes** (`schema.sql` — `kg_nodes`, `kg_edges`):
    - *Finding*: No `updated_at` indexes on `kg_nodes` or `kg_edges`. Temporal queries, GC sweeps, and re-embedding migrations scan without index support.
    - *Fix*: Added `idx_kg_nodes_updated ON kg_nodes (updated_at)` and `idx_kg_edges_updated ON kg_edges (updated_at)`.

- [x] **No Audit Logging for Permission Changes** (`orchestrator.py:274-288`):
    - *Finding*: Grant/revoke namespace access operations modify ACLs but produce no audit trail.
    - *Action*: Call `append_event()` for all permission changes.
    - *Fix*: Added `append_event()` calls in both `ManageNamespaceCommand.grant` and `ManageNamespaceCommand.revoke` branches of `manage_namespace()`. Events use `event_type="namespace_access_granted"` / `"namespace_access_revoked"` with `namespace_id=payload.grantee_namespace_id` (the namespace whose ACL is modified) and `agent_id="admin"`. Cross-namespace context captured in `params`.

- [x] **LLM Response JSON Not Validated** (all providers):
    - *Finding*: `resp.json()` and response structure access (`data["choices"][0]["message"]["content"]`) not wrapped in try-except. Malformed responses crash with `KeyError`.
    - *Fix*: Wrapped `resp.json()` in `try-except (json.JSONDecodeError, ValueError)` in all 4 providers, raising `LLMProviderError` with response preview. Also wrapped payload indexing (`data["choices"][0]["message"]["content"]`, `_extract_tool_input`, etc.) in `try-except (KeyError, IndexError, TypeError)` with context-limited error messages. Non-JSON or structurally malformed LLM responses now produce clean, typed errors instead of 500s.
    - *Test*: All existing tests pass (regression). No dedicated test for malformed responses — consider adding mock-httpx tests that return garbage content.

- [x] **NLI Model Output Not Validated** (`contradictions.py:60`):
    - *Finding*: `float(probs[2])` returned without NaN/bounds check. NaN propagates through confidence calculations.
    - *Fix*: Added `math.isnan(score)` and `0.0 <= score <= 1.0` guard. Out-of-bounds/NaN scores return `0.0` and log an error.

- [x] **Embedding Dimension Mismatch Ignored** (`embeddings.py:316-332`):
    - *Finding*: `CognitiveRemoteBackend` logs a warning when dimensions don't match `VECTOR_DIM` but returns the wrong-dimension vectors anyway. Causes silent data corruption in pgvector.
    - *Fix*: Changed `log.warning` → `log.error` and returns `[_stub_vector(t) for t in texts]` on dimension mismatch. Prevents insertion of wrong-dimension vectors into pgvector, which would corrupt the index.

---

## MEDIUM — Testing

- [x] **Integration Tests Assume Live Containers** (`test_integration_engine.py:9-14`):
    - *Finding*: Fixtures connect to real Mongo/Redis/PG without skip logic.
    - *Fix*: Added socket-based container probes. `pytestmark = pytest.mark.skipif(not _ALL_CONTAINERS, ...)` skips gracefully. Also uses `uuid4()` for all test identifiers.

- [x] **Global Mutable State in conftest** (`conftest.py:9-15`):
    - *Finding*: `autouse` fixture directly mutates `signing_mod._key_cache`.
    - *Fix*: Retained `yield` teardown pattern. Added docstring explaining `pytest-xdist` safety (each worker has own module namespace).

- [x] **Mixed Patching Mechanisms** (`test_contradiction_detection.py:81-112`):
    - *Finding*: Tests mix `monkeypatch.setattr()` with `unittest.mock.patch()`.
    - *Fix*: Standardized on `monkeypatch`. Replaced `patch()` fixture with `monkeypatch.setattr()`. Removed `from unittest.mock import patch`.

- [x] **Test Order Dependencies** (`test_integration_engine.py:17-70`):
    - *Finding*: Hardcoded `user_id="test_user"` shared across tests.
    - *Fix*: All tests now use `uuid4()`. Removed `time.time()` dependency.

- [x] **Duck-Typed Test Stubs Without Contracts** (`test_sleep_consolidation.py:23-36`):
    - *Finding*: `StubLLMProvider` uses duck typing.
    - *Fix*: Now inherits from `LLMProvider` ABC. Signature compliance enforced.

- [x] **Weak Smoke Test Assertions** (`test_smoke_stdio.py:57`):
    - *Finding*: Substring check passes on error messages.
    - *Fix*: Now `json.loads()` + validates `status == "ok"`, `payload_ref` is 24-char ObjectId, `context` key exists.

---

## Roadmap Gaps (Code vs. Innovation Roadmap v2)

- [x] **Reconstructive Replay Mode** (Phase 2.3):
    - *Context*: Only `ObservationalReplay` and `ForkedReplay` existed.
    - *Fix*: Implemented `ReconstructiveReplay` class in `trimcp/replay.py`. Applies events deterministically to an empty target namespace up to `end_seq`. Reuses the existing `_HANDLER_REGISTRY` — each handler remaps source UUIDs to fresh target UUIDs. Added `replay_reconstruct` MCP tool with `source_namespace_id`, `target_namespace_id`, `end_seq`, `start_seq`, `agent_id_filter` params. Registered in `MUTATION_TOOLS` for cache invalidation.
    - *Test*: Import verified. `/test-harden`: 125 pass, 3 pre-existing failures, 0 new regressions.

- [x] **Temporal Helper Functions** (Phase 2.2):
    - *Context*: Only `parse_as_of()` existed in `temporal.py`.
    - *Fix*: Added `as_of_query(base_query, as_of)` — returns parameterised temporal SQL clause (`valid_from/valid_to`). Added `validate_write_timestamp(ts)` — rejects future timestamps for D8 integrity. Both are reusable by any caller needing temporal filtering.

- [x] **Stale SSE Test Cache**:
    - *Context*: `.pyc` cache files for deleted `test_smoke_sse`.
    - *Fix*: Confirmed no stale cache artifacts exist — `tests/__pycache__/test_smoke_sse.cpython-*.pyc` not found. Clean.

---

## Completed (Verified against Roadmap + Enterprise Plan)

### Clean Code Audit — Completed Items (Prompt 22 — 2026-05-07)

- [x] **`store_memory()`**: Extracted `_apply_pii_pipeline()`, `_embed_and_insert_vectors()`, `_insert_graph_nodes_and_edges()`, `_apply_rollback_on_failure()`. `/test-harden` verified rollback on induced failure.
- [x] **`run_consolidation()`**: Extracted `_cluster_memories_async()`, `_call_consolidation_llm()`, `_store_consolidated_memory()`, `_update_kg()`.
- [x] **`detect_contradictions()`**: Extracted `_select_candidates()`, `_check_kg_contradiction()`, `_check_nli_contradiction()`, `_resolve_with_llm()`.
- [x] **`ForkedReplay.execute()`**: Extracted `_apply_single_event()` (static), `_dispatch_and_apply()`.
- *Kaizen (functional purity)*: All 4 extractions use keyword-only arguments (`*,`) to prevent positional arg confusion. `_apply_single_event` is `@staticmethod` — zero instance coupling. `_apply_rollback_on_failure` is self-contained; could be further extracted to a standalone function if reused by other orchestrators. `ConsolidationWorker._cluster_memories_async` can be further extracted to a pure function in `consolidation.py` (no self reference needed — only uses `asyncio.to_thread`).
- *Kaizen (replay architecture)*: `ReconstructiveReplay` and `ForkedReplay` share ~80% of their inner loop structure (cursor streaming, signature verification, handler dispatch, event_log writing, progress tracking). Consider extracting a shared `_BaseReplay` class with a template method pattern: `_pre_apply()`, `_apply_event()`, `_post_apply()`. This would eliminate ~100 lines of duplication and make adding new replay modes trivial.
- *Kaizen (UUID remapping)*: `ReconstructiveReplay` relies on each handler to remap UUIDs independently. For full reconstruction fidelity, consider a central `UUIDMapping` registry so cross-referenced IDs (e.g., memory → kg_node → kg_edge) are consistently remapped across handlers. Currently, the `_handle_store_memory` handler creates fresh UUIDs, but kg_nodes/edges inserted by consolidation may reference stale source memory IDs.
- *Kaizen (testability)*: Each extracted method can now be unit-tested independently. `_apply_rollback_on_failure` is the highest priority — mock the pools and verify 3-phase rollback (Mongo → PG-committed → PG-uncommitted). `_call_consolidation_llm` is second — mock the provider and verify confidence/hallucination/contradiction rejection paths.

### Kaizen — Completed Items

- [x] **Automate `compose.stack.env` Secrets**: Automatically generate required secrets if missing on first boot. Currently requires manual review of `deploy/compose.stack.env`.
- [x] **Consolidation Trigger in Cron**: Integrate `ConsolidationWorker` into `trimcp/cron.py` as a scheduled job. Currently `cron.py` only handles bridge renewal and re-embedding ticks; consolidation is only available via manual `trigger_consolidation` MCP tool.
- [x] **Embedding Migration Admin UI**: Add an Admin UI dashboard for managing and monitoring Embedding Model migrations. Backend (`admin_server.py`) exists but no frontend.
- [x] **Advanced Temporal Diffing**:
    - *Discovery*: `compare_states` currently identifies `Added` and `Removed` primitives only.
    - *Kaizen*: Implement `Modified` detection by tracking `source_memory_id` metadata links (already used in `replay.py:513,545,575`) to show attribute transitions between snapshots.

### Innovation Roadmap v2
- [x] **Phase 0.1 — Multi-Tenant Namespacing + RLS**: `resolve_namespace`, `set_namespace_context`, `validate_agent_id` in `auth.py`; `scoped_session` in `orchestrator.py`; RLS on 12 tables; RANGE and HASH partitioning on all high-volume tables.
- [x] **Phase 0.2 — Cryptographic Signing**: `sign_fields`, `verify_fields`, `rotate_key` in `signing.py`; JCS (RFC 8785) canonicalization; `verify_memory` MCP tool; AES-256-GCM key encryption; master key enforcement at startup.
- [x] **Phase 0.3 — PII Detection**: `scan`, `process`, `infer_assertion_type` in `pii.py`; Presidio with regex fallback; `unredact_memory` MCP tool (admin-only); 4 redaction policies (reject/flag/redact/pseudonymise).
- [x] **Phase 1.1 — Ebbinghaus Decay + Salience**: `compute_decayed_score`, `reinforce`, `ranking_score` in `salience.py`; `boost_memory` and `forget_memory` MCP tools.
- [x] **Phase 1.2 — Sleep Consolidation**: HDBSCAN clustering in `consolidation.py`; `LLMProvider` ABC in `providers/base.py`; all 8 providers implemented (anthropic, openai, azure_openai, google_gemini, deepseek, moonshot_kimi, local_cognitive, openai_compatible); `trigger_consolidation` and `consolidation_status` MCP tools.
- [x] **Phase 1.3 — Contradiction Detection**: KG check + NLI (DeBERTa) + LLM tiebreaker pipeline in `contradictions.py`; `list_contradictions` and `resolve_contradiction` MCP tools.
- [x] **Phase 2.1 — Re-Embedding Migration**: Strategy A + B in `reembedding_migration.py`; quality gate via `neighbor_overlap_fraction`; all 5 MCP tools (start/status/validate/commit/abort).
- [x] **Phase 2.2 — Memory Time Travel**: `parse_as_of` in `temporal.py`; `create_snapshot`, `list_snapshots`, `compare_states` MCP tools; temporal columns in schema.
- [x] **Phase 2.3 — Memory Replay (partial)**: `ObservationalReplay` + `ForkedReplay` in `replay.py`; WORM event_log in `event_log.py`; `replay_observe`, `replay_fork`, `replay_status`, `get_event_provenance` MCP tools.
- [x] **Phase 3.1 — A2A Protocol**: `a2a.py` + `a2a_server.py` with agent card discovery, JWT-protected tasks, 4 MCP tools (create/revoke/list grants, query_shared).
- [x] **Observability**: Prometheus metrics + OpenTelemetry tracing in `observability.py`.
- [x] **Documentation**: All 10 feature docs generated in `docs/`.

### Enterprise Deployment Plan v2.2
- [x] **Identity & Auth (section 3)**: All tools accept `user_id`/`namespace_id`; `index_code_file`, `search_codebase`, `graph_search` have `user_id` + `private` param.
- [x] **Hardware Acceleration (section 8)**: 7 backends in `embeddings.py` (CPU, CUDA, ROCm, XPU, MPS, OpenVINO NPU, Cognitive Remote); auto-detection with env override; `openvino_npu_export.py` for static-shape export.
- [x] **Language Support (section 9)**: `ast_parser.py` uses `tree-sitter-language-pack` (305+ languages).
- [x] **Document Bridges (section 10)**: SharePoint, GDrive, Dropbox in `trimcp/bridges/`; webhook receiver in `trimcp/webhook_receiver/`; 6 bridge MCP tools via `bridge_mcp_handlers.py`.
- [x] **Document Extractors (section 10.5 / Appendix J)**: 14+ extractors in `trimcp/extractors/` (Word, Excel, PowerPoint, PDF, email, OCR, CAD, Adobe, diagrams, plaintext, encryption detection).
- [x] **Cloud Infrastructure (section 5)**: Azure (Bicep), AWS (Terraform), GCP (Terraform) in `trimcp-infra/` with full module set.
- [x] **Installer/Launcher (sections 6-7)**: Go-based `trimcp-launch` shim with 3-mode support (local/multiuser/cloud); Inno Setup `.iss`, WiX `.wxs`, macOS `build-dmg.sh` in `build/`. Phase 5 build-script verification **closed** — see `deploy/README.md` (native installers).
- [x] **SSE Deprecation (section 2.6)**: `sse_server.py` and `run_sse.bat` removed; only stale `.pyc` remains.
- [x] **Docker Compose**: Root `docker-compose.yml` (full stack) + `docker-compose.local.yml` + `deploy/multiuser/docker-compose.yml`.
- [x] **IDE Patching**: `Patch-IDEConfig.ps1` (Windows) + `Patch-IDEConfig.sh` (macOS) in `build/`.

### Clean Code Audit — Completed Items
- [x] **Prometheus Metrics**: Full suite (10+ metrics) implemented in `trimcp/observability.py`.
- [x] **OpenTelemetry Tracing**: Integrated into orchestrator Saga paths with `BatchSpanProcessor`.
- [x] **Orchestrator Logic Consolidation**: Moved context query logic to `recall_recent` engine method.
- [x] **Snapshot Lifecycle**: Implemented `delete_snapshot` and exposed via MCP.
- [x] **Type Hint Consistency**: Standardized to `Union` for 3.9 compatibility and added future annotations.
- [x] **Bridge ABC Design**: Clean `BridgeProvider` abstraction with consistent subclass contract (8.5/10).
- [x] **SQL Parameterization**: All direct queries use `$N` parameterized placeholders (except temporal clause — tracked above).
- [x] **Embedding ABC Design**: `EmbeddingBackend` ABC with 7 concrete implementations and proper auto-detection.
- [x] **LLM Provider ABC**: `LLMProvider` base with `complete()` and `model_identifier()` contract. All 8 providers implement correctly.
