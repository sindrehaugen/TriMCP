# TriMCP Phase 4 Remediation — Microstepped Execution Plan
> **Craft Standard**: Uncle Bob (Clean Code + Clean Architecture + SOLID).  
> Every batch produces small, single-purpose functions; dependencies point inward; patterns are earned by duplication, not cargo-culted.  
> Lint and test gates are machine-enforced; design and smell checks are human-reviewed.

---

## BATCH 1: GC Safety & WORM Immutability (Task 4 + Task 5.1)
**Skills**: `python-expert`, `pytest-master`, `security-audit`, `database-design`, `uncle-bob-craft`
**ETA**: ~15 min | **Risk**: Low | **Smell Target**: Fragility, needless repetition

| Step | Action | Uncle-Bob Craft Gate |
|---|---|---|
| 1.1 | **Schema — WORM Immutability**: Add `prevent_mutation()` trigger on `event_log` in `schema.sql` | SRP: trigger does one thing — reject mutation |
| 1.2 | **Schema — I/O Fix**: Remove `trg_event_log_parent_fk_insupd` from `schema.sql` | Dependency Rule: FK validation moves to app layer or partition-aware query, not DB trigger hammer |
| 1.3 | **GC — Safe-Mode**: Change `GC_ORPHAN_AGE_SECONDS` 300 → 86400 in `garbage_collector.py` | Named constant; no magic numbers |
| 1.4 | **GC — Safe-Mode**: Remove `DELETE FROM kg_nodes WHERE label NOT IN (...)` from `garbage_collector.py` | SRP: GC collects orphans, not lobbies nodes; graph topology is not GC's business |
| 1.5 | **Test**: `pytest tests/test_garbage_collector.py tests/test_event_log_worm_privileges_pg.py -v` | Green before next step |
| 1.6 | **Lint**: `ruff check . --fix && black . --target-version py310` | Tooling, not craft |

**Smell Watch**: If GC code mixes Mongo + PG + S3 in one function, extract into `_purge_postgres()`, `_purge_mongo()`.

---

## BATCH 2: RLS Hygiene + Redis Lua Rate Limiter (Task 3.1 + 3.2)
**Skills**: `python-expert`, `pytest-master`, `backend-security-coder`, `uncle-bob-craft`
**ETA**: ~20 min | **Risk**: Medium | **Smell Target**: Rigidity, fragility

| Step | Action | Uncle-Bob Craft Gate |
|---|---|---|
| 2.1 | **RLS Patch**: Wrap all `yield conn` in `auth.py` with `try...finally` resetting `trimcp.namespace_id` to `''` | RAII pattern; resource cleanup is the caller's responsibility, not the borrower's guess |
| 2.2 | **RLS Patch**: Same for `orchestrators/memory.py` scoped sessions | DRY: extract `_reset_rls_context(conn)` helper if pattern repeats ≥3× |
| 2.3 | **Redis Lua**: Replace Python `zcard`/`zadd` in `auth.py` with atomic `redis_client.eval()` Lua script | SRP: rate-limit policy lives in one script, not split across Python branches |
| 2.4 | **Test**: `pytest tests/test_auth.py tests/test_cognitive_orchestrator_rls.py -v` | Green before next step |
| 2.5 | **Lint** | Tooling |

**Smell Watch**: If `set_namespace_context` is copy-pasted in 3+ files, extract to `trimcp/auth_rls.py` boundary.

---

## BATCH 3: DB Quota + Re-embedding Row Locks (Task 3.3 + 3.4)
**Skills**: `python-expert`, `pytest-master`, `database-design`, `uncle-bob-craft`
**ETA**: ~15 min | **Risk**: Low | **Smell Target**: Fragility, opacity

| Step | Action | Uncle-Bob Craft Gate |
|---|---|---|
| 3.1 | **Schema**: Add `ALTER TABLE resource_quotas ADD CONSTRAINT chk_quota CHECK (used_amount <= limit_amount);` | Single source of truth; policy in schema, not scattered asserts |
| 3.2 | **Worker**: Update `reembedding_worker.py` SELECT to use `FOR UPDATE SKIP LOCKED` | SRP: worker fetches *and* locks in one query; no Python-side race logic |
| 3.3 | **Test**: `pytest tests/test_reembedding_worker.py -v` | Green |
| 3.4 | **Lint** | Tooling |

**Smell Watch**: If worker function is >40 lines, extract `_fetch_locked_batch(conn, size)`.

---

## BATCH 4: SSRF Guard + PII Thread Offloading (Task 5.3 + 5.2)
**Skills**: `python-expert`, `pytest-master`, `security-audit`, `regex-expert`, `uncle-bob-craft`
**ETA**: ~20 min | **Risk**: Medium | **Smell Target**: Viscosity, opacity

| Step | Action | Uncle-Bob Craft Gate |
|---|---|---|
| 4.1 | **Create** `trimcp/_http_utils.py` with `SafeAsyncClient` subclass blocking private IP ranges | Boundary: network policy is an adapter, not leaked into business logic |
| 4.2 | **Update** `dispatch.py` to use `SafeAsyncClient` for all outbound agent tool requests | Dependency Inversion: dispatch depends on abstraction, not `httpx.AsyncClient` directly |
| 4.3 | **Thread Offloading**: Wrap pytesseract calls in `dispatch.py` with `run_in_executor` | SRP: dispatch orchestrates, does not block the event loop |
| 4.4 | **Thread Offloading**: Wrap heavy regex in `pii.py` with `run_in_executor` | Same |
| 4.5 | **Test**: `pytest tests/test_ssrf_guard.py tests/test_pii_pseudonym.py -v` | Green |
| 4.6 | **Lint** | Tooling |

**Smell Watch**: If `_http_utils.py` grows beyond SSRF, split into `_net_policy.py` and `_http_client.py`.

---

## BATCH 5: OAuth Mutex + DLQ Redaction (Task 5.4 + Task B.6)
**Skills**: `python-expert`, `pytest-master`, `backend-security-coder`, `uncle-bob-craft`
**ETA**: ~15 min | **Risk**: Low | **Smell Target**: Fragility

| Step | Action | Uncle-Bob Craft Gate |
|---|---|---|
| 5.1 | **Redis SET NX EX mutex** around vendor token refresh in `bridge_renewal.py` | SRP: one function acquires mutex, another refreshes; mutex policy is separate from OAuth flow |
| 5.2 | **DLQ Redaction**: In `dead_letter_queue.py` / `tasks.py`, truncate/redact `kwargs` before persistence | SRP: logging/persistence layer sanitizes, not the business task |
| 5.3 | **Test**: `pytest tests/test_bridge_renewal.py tests/test_hmac_edge_cases.py -v` | Green |
| 5.4 | **Lint** | Tooling |

**Smell Watch**: If mutex logic is inline, extract `_acquire_refresh_lock(redis, provider) -> bool`.

---

## BATCH 6: Transactional Outbox Schema (Task 2.1 — Foundation Only)
**Skills**: `python-expert`, `pytest-master`, `architecture`, `database-design`, `uncle-bob-craft`
**ETA**: ~25 min | **Risk**: Medium | **Smell Target**: Needless complexity, rigidity

| Step | Action | Uncle-Bob Craft Gate |
|---|---|---|
| 6.1 | **Schema**: Add `outbox_events` table to `schema.sql` | SRP: one table, one responsibility — ordered, at-most-once delivery |
| 6.2 | **Stub**: Create `trimcp/outbox_relay.py` with `poll_outbox()` skeleton | Boundary: relay is an adapter, not in `memory.py` |
| 6.3 | **memory.py**: Add `_enqueue_outbox(conn, aggregate_type, payload)` helper; do NOT wire into hot path yet | Dependency Rule: memory.py writes to PG outbox, knows nothing of Mongo/MinIO |
| 6.4 | **Test**: `pytest tests/test_memory_orchestrator_observability.py -v` | Green |
| 6.5 | **Lint** | Tooling |

**Pattern Rule**: Outbox is introduced because we have **3 duplications** of "PG + Mongo + MinIO must stay consistent." This justifies the pattern.

---

## BATCH 7: Infrastructure Config + Read/Write Split (Task 1)
**Skills**: `architecture`, `database-design`, `uncle-bob-craft`
**ETA**: ~15 min | **Risk**: Low | **Smell Target**: Viscosity

| Step | Action | Uncle-Bob Craft Gate |
|---|---|---|
| 7.1 | **config.py**: Add `DB_READ_URL`, `DB_WRITE_URL`, `PG_BOUNCER_URL` | Named config; no env-var strings inline |
| 7.2 | **Orchestrator**: Route GET/search to read replica, workers to write node | SRP: routing is one function, not scattered in handlers |
| 7.3 | **.env.example**: Document new env vars | Professionalism: config is discoverable |
| 7.4 | **Lint** | Tooling |

**Smell Watch**: If routing logic is copy-pasted per handler, extract `_get_db_pool(read_only: bool)`.

---

## Global Validation Gates (Every Batch)
1. `ruff check .` — must pass
2. Relevant `pytest` suite — must pass
3. `python scripts/verify_todo.py` — must not crash
4. **Uncle-Bob Self-Review** (checklist):
   - [ ] Functions are <20 lines when possible
   - [ ] No function does more than one thing
   - [ ] Dependencies point inward (business rules don't know about httpx/redis)
   - [ ] No pattern introduced without duplication justification
   - [ ] Tests exist before or alongside the change

## Kill Criteria
- Test fails after 2 fix attempts → halt for RCA
- Schema change breaks existing tests → rollback, add migration step
- Function exceeds 40 lines without extraction → refactor before merging batch
