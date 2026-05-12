# TriMCP — Phase 6 Enterprise Audit

**Auditor:** Claude Sonnet 4.6  
**Standard:** Uncle Bob craftsmanship, distributed-systems physics  
**Scope:** ~80 Python files audited (complete codebase)  
**Date:** 2026-05-11  

---

## Executive Summary

The TriMCP codebase exhibits a distributed-systems architecture with multi-tenancy, transactional event logging, and asynchronous orchestration. The infrastructure is mature in structure but contains **44 CRITICAL-severity flaws** and **92 MAJOR-severity flaws** that compound under production load. These are not code-style issues; they are failures of isolation, atomicity, and resource management that break the core contracts: RLS (row-level security) tenant isolation is silently bypassed in multiple orchestration paths, the WORM event log can be mutated in saga recovery, connection pools exhaust and block the event loop indefinitely under concurrency, and distributed locks fail open during outages, causing duplicate task execution.

The most dangerous patterns are systemic: `SET LOCAL` SQL statements intended to enforce RLS are placed **outside of database transactions**, rendering them no-ops in autocommit mode. This occurs in **ten files** (db_utils.py, memory.py, namespace.py, garbage_collector.py, graph_query.py, orchestrators/graph.py, orchestrators/cognitive.py, orchestrators/temporal.py, and two bridge files). The second pervasive anti-pattern is pool acquire without timeout: **every file that touches PostgreSQL** calls `pool.acquire()` with no timeout parameter, allowing connection exhaustion to block the entire asyncio event loop indefinitely. Third, distributed locks fail open on Redis outage (cron_lock.py, garbage_collector.py, auth.py rate limiter), permitting concurrent execution of supposedly-singleton jobs. Fourth, `append_event()` is called without wrapping in database transactions in **six locations**, breaking the advisory-lock sequence guarantee that is the WORM audit log's foundation. These patterns are not isolated bugs; they represent a systemic failure to enforce the transaction and isolation boundaries that the architecture claims to provide.

The embedded credentials (MinIO default password in config.py, admin API key in plaintext MCP schema in server.py, TRIMCP_ADMIN_OVERRIDE dev bypass with no production guard) and silent data corruption (MD5-hashed junk embeddings inserted into pgvector index without flag in embeddings.py, quota consumed but not rolled back on cache hit in server.py, OFFSET pagination false-orphan deletions in garbage_collector.py) are the highest operational risks. The codebase is **not production-ready** without addressing the 44 CRITICAL and 92 MAJOR findings documented below.

---

## Findings Index

| File | CRITICAL | MAJOR | MINOR | NITPICK |
|------|----------|-------|-------|---------|
| `trimcp/db_utils.py` | 1 | 1 | 1 | — |
| `trimcp/config.py` | 1 | 2 | 1 | — |
| `trimcp/auth.py` | 2 | 2 | — | — |
| `trimcp/signing.py` | 1 | 2 | 1 | — |
| `trimcp/event_log.py` | 1 | 2 | 1 | — |
| `trimcp/tasks.py` | 1 | 2 | — | — |
| `trimcp/cron.py` | 1 | 2 | — | — |
| `trimcp/cron_lock.py` | 1 | 1 | 1 | — |
| `trimcp/outbox_relay.py` | 2 | 1 | — | — |
| `trimcp/semantic_search.py` | 1 | 2 | — | — |
| `trimcp/quotas.py` | 1 | 2 | — | — |
| `trimcp/embeddings.py` | 2 | 1 | 1 | — |
| `server.py` | 3 | 3 | — | 1 |
| `trimcp/orchestrator.py` | — | 8 | 2 | — |
| `trimcp/orchestrators/memory.py` | 3 | 3 | 1 | — |
| `trimcp/orchestrators/namespace.py` | 3 | 2 | 2 | — |
| `trimcp/dead_letter_queue.py` | — | 3 | 1 | 1 |
| `trimcp/garbage_collector.py` | 2 | 2 | 2 | — |
| `trimcp/pii.py` | 1 | 2 | 2 | — |
| `admin_server.py` | 2 | 4 | 2 | — |
| `trimcp/jwt_auth.py` | — | 2 | 2 | 1 |
| `trimcp/mtls.py` | — | 1 | 2 | — |
| `trimcp/a2a.py` | 1 | 2 | 2 | — |
| `trimcp/a2a_server.py` | — | 3 | 3 | — |
| `trimcp/bridges/` (4 files) | 1 | 1 | 3 | — |
| `trimcp/bridge_renewal.py` | 1 | 3 | 2 | — |
| `trimcp/bridge_repo.py` | 1 | — | 2 | — |
| `trimcp/bridge_runtime.py` | 1 | 2 | 1 | — |
| `trimcp/webhook_receiver/main.py` | — | 2 | 2 | — |
| `trimcp/orchestrators/graph.py` | 1 | 2 | 2 | — |
| `trimcp/orchestrators/cognitive.py` | 1 | — | 2 | — |
| `trimcp/orchestrators/migration.py` | 1 | 2 | 1 | — |
| `trimcp/orchestrators/temporal.py` | 1 | 2 | 2 | — |
| `trimcp/consolidation.py` | 1 | 2 | 1 | — |
| `trimcp/salience.py` | — | — | 1 | — |
| `trimcp/temporal.py` | — | 1 | 1 | — |
| `trimcp/sanitize.py` | — | — | 1 | — |
| `trimcp/net_safety.py` | — | 1 | 2 | — |
| `trimcp/*_mcp_handlers.py` (10 files) | — | 4 | 6 | — |
| `trimcp/replay.py` | — | 3 | 1 | — |
| `trimcp/reembedding_worker.py` | — | 3 | 1 | — |
| `trimcp/contradictions.py` | — | 2 | 2 | — |
| `trimcp/graph_query.py` | 1 | 2 | 1 | — |
| `trimcp/models.py` | — | — | 1 | — |
| `trimcp/observability.py` | — | — | 2 | — |
| `trimcp/mcp_args.py` | — | — | 1 | — |
| `trimcp/graph_extractor.py` | — | 1 | — | — |
| `trimcp/notifications.py` | — | — | 2 | — |
| `trimcp/ast_parser.py` | — | — | 1 | — |
| `trimcp/re_embedder.py` | — | 2 | 1 | — |
| `trimcp/providers/base.py` | — | 1 | — | — |
| `trimcp/providers/factory.py` | — | 1 | — | — |
| `trimcp/extractors/dispatch.py` | — | — | 2 | — |
| `trimcp/openvino_npu_export.py` | — | — | 1 | — |
| `trimcp/{assertion,snapshot_serializer,reembedding_migration,mcp_errors,_http_utils}` | — | — | — | — |
| `trimcp/providers/{anthropic,openai_compat,google_gemini,local_cognitive,_http_utils}` | — | — | — | — |
| `trimcp/extractors/{format parsers}` (11 files) | — | — | — | — |
| `trimcp/schema.sql` | 1 | 2 | 4 | — |
| `trimcp/migrations/001_enable_rls.sql` | 1 | 1 | — | — |
| `trimcp/migrations/003_quota_check.sql` | — | — | — | — |
| `deploy/multiuser/Dockerfile` | — | — | 1 | — |
| `trimcp-infra/aws/**` (Terraform) | — | 1 | 3 | — |
| **TOTALS** | **44** | **92** | **81** | **3** |

---

## File Audits

### 1. trimcp/db_utils.py

**[plan]** Core RLS session manager; every multi-tenant DB operation passes through here. Attack vectors: (1) pool.acquire() has no timeout — exhaustion blocks event loop indefinitely; (2) latency metric measured before yield, not after — measures RLS setup time not session hold time; (3) ConnectionProvider Protocol unused.

**[execution]**

- **[CRITICAL] Location:** `scoped_pg_session`, `pool.acquire()` call — no timeout parameter  
  **The Flaw:** `pool.acquire()` with no timeout blocks the asyncio event loop indefinitely when the pool is exhausted. Under high load, all available connections are checked out; new callers block forever, preventing any other coroutine from running.  
  **The Fix:**
  ```python
  async with pool.acquire(timeout=acquire_timeout) as conn:
      # or
  conn = await asyncio.wait_for(pool.acquire(), timeout=30.0)
  ```

- **[MAJOR] Location:** `SCOPED_SESSION_LATENCY.observe()` placed before `yield conn`  
  **The Flaw:** The Prometheus histogram measures RLS setup time (~1ms), not actual session hold time. The metric label "scoped_pg_session_duration" implies it tracks how long connections are held, but it measures only the setup phase. Operators using this metric to detect pool starvation get false negatives.  
  **The Fix:** Move `observe()` to a `finally` block after the `yield`:
  ```python
  start = time.perf_counter()
  try:
      yield conn
  finally:
      SCOPED_SESSION_LATENCY.observe(time.perf_counter() - start)
  ```

- **[MINOR] Location:** `ConnectionProvider` Protocol definition  
  **The Flaw:** The Protocol is defined but never used in any function signature in the file or the wider codebase. It is dead abstraction — it adds cognitive weight without enabling any polymorphism.  
  **The Fix:** Delete it.

**[validation]** `db_utils.py` is the RLS foundation for all multi-tenant access. The missing acquire timeout is the highest-leverage single fix in the codebase — it affects every file that calls `scoped_pg_session`. Not production-ready.

---

### 2. trimcp/config.py

**[plan]** Centralized env-var configuration singleton. Attack vectors: (1) hardcoded default secret; (2) phantom read/write split config; (3) missing pool-size validation.

**[execution]**

- **[CRITICAL] Location:** `MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "super_secure_minio_password")`  
  **The Flaw:** A known default credential is committed in the repository. Any deployment that fails to set `MINIO_SECRET_KEY` ships with a publicly-known MinIO password. Attackers who find the repo can immediately authenticate to any TriMCP MinIO instance that used the default.  
  **The Fix:** Default to `""` and raise in `validate()`:
  ```python
  MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "")
  # in validate():
  if not self.MINIO_SECRET_KEY:
      raise ValueError("MINIO_SECRET_KEY must be set")
  ```

- **[MAJOR] Location:** `DB_READ_URL` and `DB_WRITE_URL` config fields  
  **The Flaw:** Both fields are declared and documented but never referenced in any orchestrator path that routes queries. Operators who configure `DB_READ_URL` expecting read/write split see zero benefit — all traffic hits the primary.  
  **The Fix:** Either remove the fields and add a warning, or implement actual routing in `db_utils.scoped_pg_session` using a `read_only` parameter.

- **[MAJOR] Location:** `validate()` method — no pool size validation  
  **The Flaw:** `PG_MAX_POOL < 20` is a common misconfiguration that causes pool starvation under any real load. `validate()` checks for missing secrets but not for obviously dangerous pool sizes.  
  **The Fix:**
  ```python
  if self.PG_MAX_POOL < 10:
      log.warning("PG_MAX_POOL=%d is dangerously low for production; recommend >= 20", self.PG_MAX_POOL)
  ```

- **[MINOR] Location:** `TRIMCP_MASTER_KEY` attribute on `_Config`  
  **The Flaw:** The master key is stored as a plaintext class attribute on the config singleton, which lives for the entire process lifetime. Any code that can access `cfg` can read the master key. It should be zeroed after use.  
  **The Fix:** Use a `SecureKeyBuffer` wrapper and zero after `validate()`.

**[validation]** `config.py` is clean in structure but the hardcoded MinIO default is a ship-blocking credential leak. The phantom read/write split creates false confidence in an operator who configures `DB_READ_URL`. Not production-ready.

---

### 3. trimcp/auth.py

**[plan]** HMAC middleware, PBKDF2 admin password hashing, RBAC `require_scope`, Redis rate limiter. Attack vectors: (1) Lua rate-limit member collision bypasses burst limit; (2) per-process in-memory fallback multiplies effective rate by replica count; (3) admin key read from os.environ on every call.

**[execution]**

- **[CRITICAL] Location:** `_RATE_LIMIT_LUA` — `ZADD key now now` (score = member = same float)  
  **The Flaw:** Multiple requests within the same microsecond all produce identical ZADD members (the timestamp float). ZADD with a duplicate member updates the existing entry rather than adding a new one. The sorted set never grows beyond one entry per microsecond, effectively collapsing the sliding window to a 1-request-per-microsecond limit at high burst rates — but in practice the requests within one microsecond bypass the burst count entirely.  
  **The Fix:** Pass a unique member:
  ```python
  # ARGV[5] = unique nonce (uuid4 hex)
  redis.call('ZADD', key, now, now .. ':' .. ARGV[5])
  ```

- **[CRITICAL] Location:** `_IN_MEMORY_LIMITS` per-process fallback  
  **The Flaw:** When Redis is unavailable, rate limiting falls back to per-process counters. In a 10-replica deployment, the effective rate limit is `limit × 10`. A tenant limited to 100 req/min can send 1,000 req/min across replicas — each replica sees only 100.  
  **The Fix:** Log a CRITICAL alert when falling back and use a much lower in-process limit (e.g., `limit // max_replicas`) or fail-closed (deny all requests during Redis outage for rate-limited endpoints).

- **[MAJOR] Location:** `_validate_scope` — `os.environ.get("TRIMCP_ADMIN_API_KEY")` on every call  
  **The Flaw:** Admin key is read from the environment on every tool invocation. `os.environ` is not a constant-time operation and bypasses any caching in `cfg`. If the key changes at runtime (e.g., secret rotation via a sidecar), there is no controlled switchover.  
  **The Fix:** Read from `cfg.TRIMCP_ADMIN_API_KEY` (validated once at startup) and cache in a module-level variable.

- **[MAJOR] Location:** `BasicAuthMiddleware` — `auto_upgrade=False`  
  **The Flaw:** PBKDF2 hash upgrades (increasing iteration count as hardware improves) are never applied. Users authenticated with a 100K-iteration hash from 2023 never get upgraded to 600K. Over time, stored hashes become cheaper to brute-force.  
  **The Fix:** Set `auto_upgrade=True` and handle the re-hash on successful authentication.

**[validation]** `auth.py` has two CRITICALs that directly undermine the rate-limiting contract in multi-replica deployments. Not production-ready.

---

### 4. trimcp/signing.py

**[plan]** AES-256-GCM key wrapping, TTLCache secure zeroing, MasterKey/MutableKeyBuffer/SecureKeyBuffer. Attack vectors: (1) PBKDF2 KDF called synchronously inside asyncio.Lock; (2) TTL expiry bypasses __delitem__ override; (3) bytes copy on every key read.

**[execution]**

- **[CRITICAL] Location:** `decrypt_signing_key` called synchronously inside `async with _get_key_cache_lock():`  
  **The Flaw:** PBKDF2-HMAC-SHA256 at 600,000 iterations takes ~300ms CPU. Called synchronously inside an async lock, it blocks the entire asyncio event loop for that duration. All concurrent MCP tool calls freeze for 300ms on every cache miss.  
  **The Fix:**
  ```python
  loop = asyncio.get_running_loop()
  from functools import partial
  raw_key = await loop.run_in_executor(
      None, partial(decrypt_signing_key, encrypted, master_key)
  )
  ```

- **[MAJOR] Location:** `_SigningKeyCache.__delitem__` override not invoked by cachetools TTL expiry  
  **The Flaw:** The docstring claims "keys are zeroed on TTL expiry." cachetools TTL eviction does not call `__delitem__` — it uses internal cache machinery that bypasses the override. The secure zeroing on expiry is documentation fiction.  
  **The Fix:** Override `_SigningKeyCache` to use `expire()` with explicit eviction callbacks, or use a custom TTL implementation that calls `__delitem__` on expiry.

- **[MAJOR] Location:** `get_active_key` returns `bytes(entry.raw_key.raw)`  
  **The Flaw:** Every call creates a new unzeroable Python `bytes` object — a copy of the key material that cannot be explicitly zeroed. The `SecureKeyBuffer` is designed to be the sole owner of key bytes; this copy defeats that purpose.  
  **The Fix:** Return the `SecureKeyBuffer` itself and require callers to use it within a context manager that zeros on exit.

**[validation]** `signing.py` has a blocking 300ms event-loop freeze on cache miss that is reproducible under any deployment. The secure-zeroing claims are mostly false. Not production-ready.

---

### 5. trimcp/event_log.py

**[plan]** WORM append-only log, advisory lock sequence allocation, Merkle chain, cryptographic signing. Attack vectors: (1) verify_merkle_chain loads entire namespace history into heap; (2) advisory lock has no timeout; (3) DB clock fetched before lock.

**[execution]**

- **[CRITICAL] Location:** `verify_merkle_chain` — `rows = await conn.fetch(...)` with no LIMIT  
  **The Flaw:** Loads the entire event_log for a namespace into Python heap. A namespace with 10M events loads 10M rows. Python heap bloat triggers OOM kill.  
  **The Fix:** Cursor-based streaming with batch_size=1000:
  ```python
  async for batch in conn.cursor("SELECT ... FROM event_log WHERE namespace_id=$1 ORDER BY seq", ns_id, prefetch=1000):
      # process batch
  ```

- **[MAJOR] Location:** `pg_advisory_xact_lock` — no lock_timeout set  
  **The Flaw:** Hot namespaces serialize all writers on the advisory lock indefinitely. One slow writer blocks all subsequent writers for that namespace until it completes.  
  **The Fix:**
  ```python
  await conn.execute("SET LOCAL lock_timeout = '10s'")
  await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)
  ```

- **[MAJOR] Location:** `_fetch_db_clock` called BEFORE `_acquire_seq_lock`  
  **The Flaw:** `occurred_at` timestamp is fetched before the advisory lock is acquired. Under contention, 500ms can elapse between the clock fetch and the actual row insert, making timestamps stale.  
  **The Fix:** Move `_fetch_db_clock` to after `_acquire_seq_lock`.

**[validation]** `event_log.py` is the WORM audit backbone. The unbounded Merkle verification is a DoS vector on any large namespace. Not production-ready.

---

### 6. trimcp/tasks.py

**[plan]** RQ worker tasks for code indexing and bridge events. Attack vectors: (1) new asyncpg pool per task invocation; (2) MD5 file hash; (3) DLQ persistence creates pool when PG is saturated.

**[execution]**

- **[CRITICAL] Location:** `engine = TriStackEngine()` inside each task function  
  **The Flaw:** Each RQ worker task creates a new `TriStackEngine` with a new asyncpg pool (min=2, max=10 by default). With N workers, N×10 connections are created simultaneously. This rapidly exhausts PostgreSQL's `max_connections`.  
  **The Fix:** Module-level singleton pool initialized once per worker process:
  ```python
  _WORKER_POOL: asyncpg.Pool | None = None

  async def _get_pool() -> asyncpg.Pool:
      global _WORKER_POOL
      if _WORKER_POOL is None:
          _WORKER_POOL = await asyncpg.create_pool(cfg.PG_DSN, min_size=1, max_size=3)
      return _WORKER_POOL
  ```

- **[MAJOR] Location:** `hashlib.md5()` for file content hashing  
  **The Flaw:** MD5 has known collision attacks. A malicious actor can craft two different code files with the same MD5 hash, causing the embedding index to believe a file hasn't changed when it has.  
  **The Fix:** `hashlib.sha256(raw_code.encode("utf-8")).hexdigest()`

- **[MAJOR] Location:** DLQ persistence creates a short-lived pool when PG is already saturated  
  **The Flaw:** When a task fails and tries to write to the DLQ, it creates a new pool. If PG is already at max_connections (the likely failure mode), the DLQ write also fails, silently dropping the failed task record.  
  **The Fix:** Use the module-level singleton pool for DLQ writes.

**[validation]** `tasks.py` is a connection-exhaustion bomb in multi-worker deployments. Not production-ready.

---

### 7. trimcp/cron.py

**[plan]** APScheduler with 5 jobs. Attack vectors: (1) saga_recovery calls append_event without transaction; (2) sequential namespace consolidation O(N×time); (3) startup fires all 5 ticks immediately against 4-connection pool.

**[execution]**

- **[CRITICAL] Location:** `_saga_recovery_tick` — `append_event(conn=conn, ...)` without `async with conn.transaction():`  
  **The Flaw:** `append_event` acquires `pg_advisory_xact_lock` which is a transaction-scoped lock. Without a transaction, the lock is released immediately after acquisition, and the sequence number allocation has no isolation. The WORM event_log's gap-free sequence guarantee is broken for every saga recovery compensating event.  
  **The Fix:**
  ```python
  async with pool.acquire() as conn:
      async with conn.transaction():
          await set_namespace_context(conn, UUID(ns_id))
          # ... all recovery operations ...
          await append_event(conn=conn, ...)
  ```

- **[MAJOR] Location:** `_consolidation_tick` — sequential iteration over all enabled namespaces  
  **The Flaw:** O(N × consolidation_time) execution time. If consolidation takes 60s per namespace and 20 namespaces are enabled, the tick takes 20 minutes — vastly exceeding any reasonable cron interval.  
  **The Fix:**
  ```python
  sem = asyncio.Semaphore(4)
  async def _run_one(ns_id, meta):
      async with sem:
          ...
  await asyncio.gather(*[_run_one(row["id"], row["metadata"]) for row in rows])
  ```

- **[MAJOR] Location:** Lines 327–331 — 5 ticks fired immediately at startup against 4-connection pool  
  **The Flaw:** The startup jitter (applied before pool creation) is defeated by immediately firing all 5 ticks at startup, all competing for connections from a 4-connection pool.  
  **The Fix:** Fire startup ticks in sequence with `await asyncio.sleep(0)` between them, or use `asyncio.gather` with pool-size-aware concurrency.

**[validation]** `cron.py` has a WORM-breaking CRITICAL in saga recovery. Not production-ready.

---

### 8. trimcp/cron_lock.py

**[plan]** Redis SETNX distributed lock for singleton cron jobs. Attack vectors: (1) fail-open on Redis error; (2) new Redis connection per invocation; (3) no heartbeat.

**[execution]**

- **[CRITICAL] Location:** `except Exception: return True` — fail-open  
  **The Flaw:** Under Redis outage, every cron instance acquires the "lock" and executes the job. For non-idempotent jobs (bridge subscription renewal, saga recovery), concurrent execution produces duplicate operations, double-billing, or conflicting state.  
  **The Fix:**
  ```python
  async def acquire_cron_lock(job_name: str, ttl: int, *, fail_open: bool = False) -> bool:
      try:
          ...
      except Exception as exc:
          log.error("Cron lock acquisition failed for %s: %s", job_name, exc)
          return fail_open  # callers decide based on idempotency
  ```

- **[MAJOR] Location:** `AsyncRedis.from_url(cfg.REDIS_URL)` + `await client.aclose()` on every invocation  
  **The Flaw:** Creates and destroys a TCP connection on every cron tick. At 1-minute intervals across 5 jobs, this is 5 TCP handshakes per minute — unnecessary connection churn that adds latency and load.  
  **The Fix:** Module-level singleton:
  ```python
  _shared_redis: AsyncRedis | None = None

  async def _get_redis() -> AsyncRedis:
      global _shared_redis
      if _shared_redis is None:
          _shared_redis = AsyncRedis.from_url(cfg.REDIS_URL)
      return _shared_redis
  ```

- **[MINOR] Location:** No lock heartbeat mechanism  
  **The Flaw:** An OOM-killed pod releases its Redis SETNX lock only after TTL expires. For bridge renewal with `BRIDGE_CRON_INTERVAL_MINUTES=45`, TTL = 45×60+60 = 2,760 seconds = 46 minutes. Other instances are locked out for 46 minutes after a pod kill.  
  **The Fix:** Implement a heartbeat task that extends TTL periodically while the job runs.

**[validation]** `cron_lock.py` is the distributed coordination layer for all cron jobs. Fail-open on Redis error is the single most dangerous default in this file. Not production-ready.

---

### 9. trimcp/outbox_relay.py

**[plan]** Transactional outbox polling. Attack vectors: (1) FOR UPDATE SKIP LOCKED outside transaction; (2) no mark-as-published step; (3) unused parameter.

**[execution]**

- **[CRITICAL] Location:** `FOR UPDATE SKIP LOCKED` outside a transaction  
  **The Flaw:** `FOR UPDATE SKIP LOCKED` acquires row-level locks only within a transaction. Outside a transaction (auto-commit mode), the lock is released immediately after the SELECT. Concurrent callers see the same rows. Any deployment with more than one outbox relay instance delivers every event multiple times.  
  **The Fix:**
  ```python
  async with conn.transaction():
      rows = await conn.fetch("SELECT ... FOR UPDATE SKIP LOCKED LIMIT $1", batch_size)
      for row in rows:
          await delivery_fn(row)
          await conn.execute("UPDATE outbox_events SET published_at = now() WHERE id = $1", row["id"])
  ```

- **[CRITICAL] Location:** No `UPDATE outbox_events SET published_at` step  
  **The Flaw:** Even if the transaction issue were fixed, there is no step to mark events as delivered. Any polling loop re-processes the same events on every poll iteration — infinite re-delivery.  
  **The Fix:** Mark as published inside the same transaction as delivery (see above).

- **[MAJOR] Location:** `poll_interval_seconds` parameter declared but never used  
  **The Flaw:** The sleep loop uses a hardcoded value instead of the parameter, making the parameter a documentation lie.  
  **The Fix:** Use `await asyncio.sleep(poll_interval_seconds)`.

**[validation]** `outbox_relay.py` delivers every event an unbounded number of times. Not production-ready.

---

### 10. trimcp/semantic_search.py

**[plan]** pgvector + FTS hybrid search with RRF scoring. Attack vectors: (1) N+1 MongoDB for result hydration; (2) RawExpression f-string embeds parameter index (fragile); (3) reinforce() N calls without transaction.

**[execution]**

- **[CRITICAL] Location:** Lines 281–291 — sequential `find_one` per result  
  **The Flaw:** For `limit=100`, 100 sequential MongoDB round-trips. Latency = 100 × ~5ms = 500ms minimum, and each round-trip is serial.  
  **The Fix:**
  ```python
  object_ids = [ObjectId(r["payload_ref"]) for r in top_results]
  docs = await db.episodes.find({"_id": {"$in": object_ids}}).to_list(length=len(object_ids))
  doc_map = {str(d["_id"]): d for d in docs}
  ```

- **[MAJOR] Location:** `RawExpression(f"me.embedding <=> {p_vector}::vector")` — parameter index in f-string  
  **The Flaw:** The `p_vector` parameter index (e.g., `$1`) is embedded in an f-string as part of the SQL text. Adding any parameter before line 116 silently shifts all subsequent parameter indices, causing binding errors or, worse, silently substituting the wrong parameter value.  
  **The Fix:** Build the SQL string with explicit numbered placeholders only at the final query assembly stage, after all `builder.param()` calls are complete.

- **[MAJOR] Location:** `reinforce()` called N times without a wrapping transaction  
  **The Flaw:** Partial salience updates on asyncio task cancellation. If the task is cancelled between the 3rd and 4th `reinforce()` call, 3 memories have boosted salience and N-3 do not — skewing the cognitive model asymmetrically.  
  **The Fix:** Wrap all `reinforce()` calls in a single transaction.

**[validation]** `semantic_search.py` is the query hot path. The N+1 MongoDB pattern is a latency multiplier proportional to result count. Not production-ready for `limit > 10`.

---

### 11. trimcp/quotas.py

**[plan]** Per-namespace/agent quota enforcement with FOR UPDATE row locking. Attack vectors: (1) DeadlockDetectedError silently caught as quota error; (2) double-rollback corrupts used_amount; (3) unchecked UUID parse.

**[execution]**

- **[CRITICAL] Location:** `IntegrityConstraintViolationError` handler catches `DeadlockDetectedError`  
  **The Flaw:** `asyncpg.exceptions.DeadlockDetectedError` is a subclass of `IntegrityConstraintViolationError`. It is caught by the quota error handler and re-raised as a generic quota error. Deadlocks silently appear as quota exceeded errors to clients; no retry is attempted; the operation is permanently failed.  
  **The Fix:**
  ```python
  except asyncpg.exceptions.DeadlockDetectedError:
      # exponential backoff retry, max 3 attempts
      raise
  except asyncpg.exceptions.IntegrityConstraintViolationError:
      raise QuotaExceededError(...)
  ```

- **[MAJOR] Location:** `QuotaReservation.rollback()` — not idempotent  
  **The Flaw:** Calling `rollback()` twice decrements `used_amount` by 2×reservation, creating a negative quota usage that allows unlimited future operations.  
  **The Fix:**
  ```python
  def rollback(self):
      if self._rolled_back:
          return
      self._rolled_back = True
      # decrement
  ```

- **[MAJOR] Location:** `UUID(str(arguments["namespace_id"]))` — unchecked ValueError  
  **The Flaw:** If `namespace_id` is malformed, `UUID()` raises `ValueError` which propagates and bypasses the entire quota check. Callers proceed without quota enforcement.  
  **The Fix:** Validate and raise a proper error before the quota check path.

**[validation]** `quotas.py` silently turns deadlocks into quota errors and allows unlimited bypass via double-rollback. Not production-ready.

---

### 12. trimcp/embeddings.py

**[plan]** Hardware-backend embedding abstraction. Attack vectors: (1) ContextVar mutation in ThreadPoolExecutor not visible to caller; (2) MD5 junk vectors silently inserted on failure; (3) lazy singleton unsafe under concurrent pytest.

**[execution]**

- **[CRITICAL] Location:** `degraded_embedding_flag.set(True)` inside `ThreadPoolExecutor` thread  
  **The Flaw:** ContextVar mutations in executor threads are not propagated to the calling coroutine's context. The flag is set in the thread's copy of the context, which is discarded when the thread returns. The degraded state is never recorded.  
  **The Fix:**
  ```python
  ctx = contextvars.copy_context()
  result = await loop.run_in_executor(_executor, lambda: ctx.run(self._sync_embed_batch, texts))
  ```

- **[CRITICAL] Location:** `return [_deterministic_hash_embedding(t) for t in texts]` on all failures  
  **The Flaw:** MD5-seeded pseudorandom vectors are silently returned as embeddings when the backend fails. These junk vectors are inserted into the pgvector index with no flag (the degraded ContextVar never propagates). Every semantic search against these vectors returns nonsense results. There is no way to retroactively identify which memories have corrupted embeddings.  
  **The Fix:** Raise `EmbeddingProviderError` instead; let the caller (DLQ) handle the failure.

- **[MAJOR] Location:** Lazy `_backend` singleton  
  **The Flaw:** Not guarded by a lock. Under concurrent pytest-asyncio test runs that share module state, two coroutines can both initialize `_backend` simultaneously.  
  **The Fix:** Use `asyncio.Lock()` for initialization.

- **[MINOR] Location:** `asyncio.get_event_loop()` call in `embed_batch`  
  **The Flaw:** Deprecated since Python 3.10. Use `asyncio.get_running_loop()`.

**[validation]** `embeddings.py` silently poisons the vector index on any embedding failure. This is the most insidious data-quality bug in the codebase — it produces no errors, no alerts, and permanently corrupts search results. Not production-ready.

---

### 13. server.py

**[plan]** Main MCP server, 50+ tool dispatch, quota/cache/auth gating. Attack vectors: (1) quota consumed before cache check — no rollback on cache hit or Redis error; (2) store_media LFI; (3) CACHEABLE_TOOLS defined twice; (4) admin_api_key in plaintext MCP schema.

**[execution]**

- **[CRITICAL] Location:** Lines 1383–1410 — quota consumed before cache check, no rollback on cache hit  
  **The Flaw:** `q_res = await _quotas.consume_for_tool(...)` at line 1383. The cache check happens at line 1393–1410. On a cache hit (line 1410), the function returns immediately without calling `q_res.rollback()`. The quota is permanently consumed even though no actual tool work was performed. Tenants are billed for cache hits.  
  **The Fix:** Check cache FIRST, then consume quota only on miss:
  ```python
  # Cache check first
  if name in CACHEABLE_TOOLS:
      cached_val = await engine.redis_client.get(cache_key)
      if cached_val:
          return [TextContent(type="text", text=cached_val.decode())]
  # Only then consume quota
  q_res = await _quotas.consume_for_tool(engine.pg_pool, name, arguments)
  ```

- **[CRITICAL] Location:** `store_media` tool — `file_path_on_disk` parameter with no path validation  
  **The Flaw:** The tool schema accepts `file_path_on_disk: str`. In `memory.py:store_media`, the code does `os.path.exists(payload.file_path_on_disk)` then uploads it to MinIO. No path validation is performed. Any MCP client can pass `/etc/shadow`, `/proc/self/environ`, or any server-readable file path and receive its contents uploaded to MinIO (and logged in MongoDB metadata including `"original_path"`).  
  **The Fix:**
  ```python
  ALLOWED_BASE = Path(cfg.TRIMCP_MEDIA_UPLOAD_BASE_DIR).resolve()
  candidate = (ALLOWED_BASE / Path(file_path).name).resolve()
  if not str(candidate).startswith(str(ALLOWED_BASE) + "/"):
      raise ValueError("Path escapes upload directory")
  ```

- **[CRITICAL] Location:** Lines 1394–1410 — quota not rolled back on Redis error during cache read  
  **The Flaw:** After `q_res` is consumed at line 1383, the cache read at line 1403 (`engine.redis_client.get(cache_key)`) can throw. This exception bypasses the `except Exception: await q_res.rollback()` block at line 1718–1720 (which is inside the inner tool dispatch try). The quota decrement is permanent despite no tool work being done.  
  **The Fix:** Wrap the entire post-quota section in a try/finally that always calls `q_res.rollback()` unless explicitly committed.

- **[MAJOR] Location:** Lines 1324 and 1388 — `CACHEABLE_TOOLS` defined twice  
  **The Flaw:** The set is assigned at line 1324, then unconditionally overwritten at line 1388 by an identical assignment. The first definition is dead code. A developer adding a fourth cacheable tool must find and update the second definition, not the first.  
  **The Fix:** Move to module level as `frozenset`, delete the duplicate.

- **[MAJOR] Location:** Lines 1186–1234, `_check_admin` — deprecated but still used by 5 tools; `TRIMCP_ADMIN_OVERRIDE` has no production guard  
  **The Flaw:** `_check_admin` is documented as deprecated. Five tools still call it. The dev bypass `TRIMCP_ADMIN_OVERRIDE=true` has no production environment check — an operator who forgets to unset it ships an auth bypass to production.  
  **The Fix:** Migrate all 5 tools to `@require_scope("admin")`. Add a production guard:
  ```python
  if os.environ.get("TRIMCP_ADMIN_OVERRIDE") == "true":
      if os.environ.get("TRIMCP_ENVIRONMENT", "").lower() == "production":
          raise ValueError("TRIMCP_ADMIN_OVERRIDE is prohibited in production.")
      return
  ```

- **[MAJOR] Location:** Tool inputSchema for 8 admin tools — `admin_api_key` as plaintext MCP argument  
  **The Flaw:** The admin API key is transmitted in cleartext over MCP stdio. Any host that logs MCP tool calls captures the key permanently.  
  **The Fix:** Remove from inputSchema. Authenticate via the HMAC transport layer in `admin_server.py` instead.

- **[MINOR] Location:** Line 58 — `engine: TriStackEngine | None = None` module-level global  
  **The Flaw:** No guard against double-initialization. In test environments that share module state, a second `main()` call silently overwrites the engine.

**[validation]** `server.py` sits on the trust boundary and has three CRITICALs in the quota/cache interaction and LFI path. The admin API key leakage is a structural security design flaw. Not production-ready.

---

### 14. trimcp/orchestrator.py

**[plan]** Central coordination layer: connection lifecycle, tenant session routing, delegate orchestrators. Attack vectors: (1) scoped_session() hardwires write pool — read replica dead; (2) concurrent lazy-init races across 12 delegate methods; (3) _validate_path uses CWD as trust boundary.

**[execution]**

- **[MAJOR] Location:** Lines 500–501 — `scoped_session()` hardwires `self.pg_pool`  
  **The Flaw:** `scoped_session()` always passes `self.pg_pool` (write primary) regardless of whether the operation is read-only. `pg_read_pool` is configured and allocated but never used by any path that goes through `scoped_session()`.  
  **The Fix:**
  ```python
  @asynccontextmanager
  async def scoped_session(self, namespace_id, *, read_only: bool = False):
      pool = self._get_db_pool(read_only=read_only)
      async with scoped_pg_session(pool, namespace_id) as conn:
          yield conn
  ```

- **[MAJOR] Location:** All 12 lazy-init blocks (e.g., lines 652–658) — unguarded TOCTOU races  
  **The Flaw:** Every `if self.X is None: self.X = OrchestratorType(...)` block has no asyncio lock. Two concurrent calls can both pass the `is None` check and create duplicate orchestrators. The second assignment silently discards the first.  
  **The Fix:** Double-checked locking with a shared `asyncio.Lock`:
  ```python
  async with self._init_lock:
      if self.memory is None:
          self.memory = MemoryOrchestrator(...)
  ```

- **[MAJOR] Location:** Lines 339–365 — `_validate_path()` uses `Path.cwd()` as trust boundary  
  **The Flaw:** In Docker without explicit `WORKDIR`, CWD is `/`. Every absolute path is relative to `/` — the jail is completely open. The secondary `..` check at lines 359–362 is logically dead (it re-checks a condition already verified).  
  **The Fix:** Use `cfg.TRIMCP_MEDIA_UPLOAD_BASE_DIR` as the base, validated at startup.

- **[MAJOR] Location:** `check_health()` lines 741–748 — synchronous Redis I/O in async method  
  **The Flaw:** `len(q)` on an RQ Queue object calls synchronous `LLEN` via `redis_sync_client` directly on the event loop thread. Under Redis latency spike (5s socket timeout), freezes all concurrent tool calls for 5 seconds.  
  **The Fix:** `count = await asyncio.to_thread(lambda: len(q))`

- **[MAJOR] Location:** Lines 216–220, 378, 393, 409, 422, 444 — 5 sequential `pool.acquire()` in `connect()` without timeout  
  **The Flaw:** All startup verification queries use `async with self.pg_pool.acquire() as conn:` with no timeout. Slow PostgreSQL startup causes `connect()` to hang indefinitely.  
  **The Fix:** `async with asyncio.timeout(10.0): async with self.pg_pool.acquire() as conn:`

- **[MAJOR] Location:** Lines 472–476 — `_init_mongo_indexes()` missing namespace scoping  
  **The Flaw:** `db.code_files.create_index("filepath")` and `db.code_files.create_index("user_id")` have no `namespace_id` prefix. Cross-tenant code searches are cheap and potentially return data from other tenants.  
  **The Fix:** Compound indexes: `[("namespace_id", 1), ("filepath", 1)]`

- **[MINOR] Location:** Lines 287–298 — `disconnect()` no error isolation  
  **The Flaw:** First `close()` failure prevents remaining resources from being closed.  
  **The Fix:** Wrap each close in try/except with individual logging.

- **[MINOR] Location:** Lines 760–773 — `check_health()` hardcoded `localhost:11435` fallback  
  **The Flaw:** When `TRIMCP_COGNITIVE_BASE_URL` is not set, probes Ollama's localhost port. In containerized deployments, this always fails silently and masks real service unavailability.

**[validation]** `orchestrator.py` is the coordination root. The `scoped_session()` read-replica routing failure means operators who provision a read replica see zero benefit. The TOCTOU lazy-init races are exploitable under concurrent startup traffic. Not production-ready.

---

### 15. trimcp/orchestrators/memory.py

**[plan]** `store_memory` saga, `verify_memory`, `unredact_memory`, recall, semantic search. Attack vectors: (1) MongoDB insert + embedding computation inside scoped_pg_session holds pool connection 300ms+; (2) verify_memory calls PBKDF2 while holding pool connection; (3) unredact_memory uses raw pool acquire (no RLS) + append_event without transaction.

**[execution]**

- **[CRITICAL] Location:** Lines 536–604 — MongoDB insert + embedding inside `scoped_pg_session`  
  **The Flaw:** The outer `scoped_pg_session` is opened at line 536 and holds the pool connection through the MongoDB `insert_one` (~50ms) and `embed_batch` (~300ms) calls before the PG transaction begins at line 583. Pool connection held for ~350ms+ per `store_memory` call. At 20-connection pool, saturation at ~57 concurrent writes.  
  **The Fix:** Release the PG connection before external service calls. Structure: brief PG session for config read → MongoDB insert (no PG conn held) → embedding computation (no PG conn held) → brief PG transaction for atomic write.

- **[CRITICAL] Location:** Lines 820–821 — `decrypt_signing_key` (PBKDF2@600K) while holding pool connection  
  **The Flaw:** `verify_memory` acquires a pool connection at line 792 and calls `decrypt_signing_key` (~300ms CPU) at line 821 while holding it. Event loop blocked + pool connection held simultaneously.  
  **The Fix:** Release the connection before the KDF call, then `await loop.run_in_executor(None, partial(decrypt_signing_key, ...))`.

- **[CRITICAL] Location:** Lines 875, 927 — `unredact_memory` raw pool acquire (no RLS) + `append_event` without transaction  
  **The Flaw:** (1) `async with self.pg_pool.acquire() as conn:` with no namespace context. RLS not enforced. Any `memory_id` returns data regardless of namespace — cross-tenant PII leak. (2) `append_event` called without `async with conn.transaction():` — advisory lock released immediately, sequence guarantee broken.  
  **The Fix:** Use `scoped_pg_session` and wrap `append_event` in a transaction.

- **[MAJOR] Location:** Lines 441–475 — `_apply_rollback_on_failure` DELETEs without transaction  
  **The Flaw:** Five sequential DELETEs on a raw connection. OOM-kill between any two leaves the database in a partially-rolled-back state with the `memories` row still live (`valid_to IS NULL`), returned by all searches.  
  **The Fix:** Wrap all compensating operations in `async with conn.transaction():`.

- **[MAJOR] Location:** Lines 1033–1037 — `recall_recent` N+1 MongoDB queries  
  **The Flaw:** Sequential `find_one` per row. `limit=100` → 100 serial MongoDB round-trips.  
  **The Fix:** Batch `find` with `{"_id": {"$in": object_ids}}`.

- **[MAJOR] Location:** Lines 354–372 — `_saga_log_start` calls `set_namespace_context` outside a transaction  
  **The Flaw:** `SET LOCAL` without a transaction is a no-op. Saga log INSERT executes without RLS namespace context.  
  **The Fix:** Open `async with conn.transaction():` before calling `set_namespace_context`.

- **[MINOR] Location:** Line 122 — `json.loads(ns_row["metadata"])` on JSONB column  
  **The Flaw:** asyncpg returns JSONB as native Python dicts. `json.loads(dict)` raises `TypeError`, crashing every `store_memory` call for namespaces with PII config.  
  **The Fix:** `meta = ns_row["metadata"] if isinstance(ns_row["metadata"], dict) else json.loads(ns_row["metadata"])`

**[validation]** `memory.py` is the hottest write path. Three CRITICALs that compound under exactly the conditions (concurrent writes, admin operations, OOM recovery) the saga pattern was designed to handle. Not production-ready.

---

### 16. trimcp/orchestrators/namespace.py

**[plan]** Namespace CRUD, grants, quota management. Attack vectors: (1) scoped_session uses SET LOCAL outside transaction — RLS never set; (2) delete command deletes from event_log — WORM violation; (3) single large transaction wrapping chunked deletes defeats purpose.

**[execution]**

- **[CRITICAL] Location:** Lines 65–83 — `scoped_session()` SET LOCAL outside transaction  
  **The Flaw:** Same pattern as memory.py. `set_namespace_context` (SET LOCAL) outside a transaction is a no-op. Every `update_metadata`, `manage_quotas.set/delete/reset` executes without RLS namespace isolation.  
  **The Fix:** Open a transaction inside the context manager before calling `set_namespace_context`.

- **[CRITICAL] Location:** Lines 150–182 — `update_metadata` calls `append_event` without transaction  
  **The Flaw:** `UPDATE namespaces` and `append_event` execute as two independent auto-commit statements. Crash between them leaves metadata updated with no audit event. `append_event` without a transaction breaks advisory-lock sequence guarantee.  
  **The Fix:** Resolved by fixing `scoped_session` to open a transaction (see above).

- **[CRITICAL] Location:** Line 255 — `delete` command deletes rows from `event_log`  
  **The Flaw:** `event_log` is WORM-protected. Either WORM triggers fire and namespace deletion crashes mid-way (leaving PG in partially deleted state), or the WORM guarantee is silently bypassed.  
  **The Fix:** Replace hard-delete with soft-delete: `UPDATE namespaces SET deleted_at = NOW()`. Leave event_log rows intact as the audit trail.

- **[MAJOR] Location:** Lines 252–296 — entire namespace delete in one transaction wrapping chunked deletes  
  **The Flaw:** Chunking to "limit lock duration" is negated by the outer transaction holding all row locks until COMMIT. 1M-row namespace → minutes-long transaction, blocking VACUUM.  
  **The Fix:** Use a state machine: mark namespace `state='deleting'`, then batch-delete in chunks as separate auto-commit statements; cron job resumes incomplete deletions.

- **[MAJOR] Location:** Line 31 — `_delete_namespace_rows_chunked` f-string table name injection  
  **The Flaw:** Table name is interpolated into SQL via f-string. Safe for current hardcoded callers; SQL injection vector for any future caller passing user-controlled table name.  
  **The Fix:** Allowlist validation: `if table not in _DELETABLE_TABLES: raise ValueError(...)`.

- **[MINOR] Location:** Line 158 — `json.loads(old_meta_json)` on JSONB column  
  **The Flaw:** Same asyncpg JSONB issue — crashes on every `update_metadata` call when asyncpg returns a dict.

**[validation]** `namespace.py` manages the fundamental trust boundary of the multi-tenant system. The `scoped_session` RLS bypass undermines the security claims of the entire architecture. The event_log deletion breaks WORM. Not production-ready.

---

### 17. trimcp/dead_letter_queue.py

**[plan]** Persistent store for exhausted background tasks. Attack vectors: (1) replay marks row as replayed before re-enqueue is confirmed; (2) all pool acquires lack timeout; (3) sanitization case-sensitive.

**[execution]**

- **[MAJOR] Location:** Lines 263–308 — `replay_dead_letter` marks `replayed` before re-enqueue confirmed  
  **The Flaw:** The DB transaction commits `status='replayed'` and the function returns. The caller then re-enqueues to RQ. If RQ is unavailable, the entry is permanently stuck in `replayed` state with the task never actually executed — silent task loss.  
  **The Fix:** Pass `enqueue_fn` as a parameter and call it INSIDE the transaction. If enqueue fails, the transaction rolls back and the entry stays `pending`.

- **[MAJOR] Location:** Lines 138, 183, 241, 274, 320 — all `pg_pool.acquire()` without timeout  
  **The Flaw:** `store_dead_letter` is called from RQ worker exception handlers. If the pool is exhausted (the failure mode that triggered the DLQ write), the acquire blocks indefinitely.  
  **The Fix:** `async with pg_pool.acquire(timeout=10.0) as conn:`

- **[MINOR] Location:** Lines 55–79 — `_sanitize_dlq_kwargs` case-sensitive key matching  
  **The Flaw:** `"ACCESS_TOKEN"`, `"ApiKey"`, `"Authorization"` bypass the sensitive-key redaction.  
  **The Fix:** `if k.lower() in _DLQ_SENSITIVE_KEYS_LOWER:` using lowercased key set.

- **[NITPICK] Location:** Line 135 — placeholder zero-UUID  
  **The Flaw:** `dlq_id = str(UUID(int=0))` before the try block is confusing but harmless since the function always either assigns the real UUID or raises.  
  **The Fix:** Remove the pre-initialization.

**[validation]** `dead_letter_queue.py` is one of the cleaner files. The replay sequencing issue is the only structural bug. Close to production-ready.

---

### 18. trimcp/garbage_collector.py

**[plan]** Hourly MongoDB orphan detection and PG cascade cleanup. Attack vectors: (1) set_namespace_context outside transaction — empty pg_refs set → deletes all MongoDB documents; (2) OFFSET pagination over live table causes false orphans; (3) fail-open lock under Redis outage.

**[execution]**

- **[CRITICAL] Location:** Lines 117–118, 179–180 — `set_namespace_context` outside transaction  
  **The Flaw:** `SET LOCAL trimcp.namespace_id` outside a transaction is a no-op. If RLS uses `FORCE ROW LEVEL SECURITY`, `_fetch_pg_refs` returns zero rows → `pg_refs = {}` → every MongoDB document older than `GC_ORPHAN_AGE_SECONDS` is treated as an orphan → complete MongoDB wipeout on first GC pass.  
  **The Fix:**
  ```python
  async with pg_pool.acquire() as conn:
      async with conn.transaction():
          await set_namespace_context(conn, ns_id)
          rows = await conn.fetch(...)
  ```

- **[CRITICAL] Location:** Lines 120–136 — OFFSET pagination over live table  
  **The Flaw:** Concurrent `store_memory` inserts during the GC scan shift row positions between pages. A new row inserted in a page already scanned is missed — its `payload_ref` is absent from `pg_refs` — and the MongoDB document is deleted as a false orphan. Permanent data loss.  
  **The Fix:** Replace OFFSET with keyset pagination inside a REPEATABLE READ transaction for a stable snapshot.

- **[MAJOR] Location:** Line 48 — GC distributed lock fail-open  
  **The Flaw:** Under Redis outage, all GC instances run `_clean_orphaned_cascade` concurrently for the same namespaces, causing PG deadlocks in the CTE-with-DELETE queries.  
  **The Fix:** Fail-closed (return False on Redis error) — GC is eventually consistent and safe to skip.

- **[MAJOR] Location:** Lines 269–296 — wrong scan order (Mongo first, PG second) + full in-memory sets  
  **The Flaw:** Mongo snapshot captured first, PG refs collected minutes later. A `store_memory` call that inserts between the two scans has a MongoDB document (in `candidates`) but no PG reference yet — false orphan. Reversing the order (PG first, Mongo second) eliminates this window. Additionally, both full datasets are materialized in Python heap simultaneously.  
  **The Fix:** Collect PG refs first, then scan Mongo.

- **[MINOR] Location:** Line 119 — `code_files` cross-checked against `memories` table only  
  **The Flaw:** `code_files` MongoDB documents are checked against `memories.payload_ref`. If code files have their PG references in a different table, all `code_files` appear as orphans.

- **[MINOR] Location:** Line 42 — new Redis connection per GC lock call  
  **The Flaw:** Same TCP churn pattern as `cron_lock.py`. Use module-level singleton.

**[validation]** `garbage_collector.py` can cause complete MongoDB data wipeout on first run with properly-enforced RLS. The OFFSET pagination race causes silent data loss under concurrent load. Not production-ready.

---

## Systemic Patterns

### Pattern 1: SET LOCAL Outside Transactions — RLS Silently Bypassed

**Affected files:** `db_utils.py`, `memory.py` (lines 354–372), `namespace.py` (lines 65–83), `garbage_collector.py` (lines 117–118, 179–180), and others.

**The Anti-Pattern:** PostgreSQL `SET LOCAL` statements are used to enforce row-level security (RLS) by setting a namespace context variable. The intent is:
```sql
BEGIN;
SET LOCAL trimcp.namespace_id = 'tenant-uuid';
SELECT * FROM memories WHERE namespace_id = current_setting('trimcp.namespace_id');
COMMIT;
```

The `SET LOCAL` is scoped to the transaction and guarantees that all subsequent operations in that transaction use the correct RLS context. **However, when `SET LOCAL` is called outside a transaction (in autocommit mode), the setting is immediately reverted.** This pattern appears in at least five locations where a scoped session is opened but no explicit transaction is opened before `set_namespace_context()` is called.

**Impact:** RLS is completely bypassed for these operations. A query in `namespace.py:update_metadata` or `garbage_collector.py:_fetch_pg_refs` executes with the global context (no namespace isolation). A malicious user can read or modify any tenant's data.

**Fix Across All Locations:**
```python
async with pool.acquire() as conn:
    async with conn.transaction():
        await set_namespace_context(conn, namespace_id)
        # All queries here are now RLS-protected
```

### Pattern 2: pool.acquire() Without Timeout — Event Loop Blocking

**Affected files:** Every file that touches PostgreSQL, including `db_utils.py`, `memory.py`, `namespace.py`, `event_log.py`, `orchestrator.py`, `quotas.py`, `dead_letter_queue.py`, `garbage_collector.py`, and others.

**The Anti-Pattern:** All calls to `pool.acquire()` omit the `timeout` parameter. Under connection pool exhaustion, a coroutine calling `pool.acquire()` blocks indefinitely, preventing the asyncio event loop from scheduling any other coroutine. This is a silent deadlock.

**Impact:** Deployment with 20-connection pool becomes unresponsive when 20 concurrent operations all call `pool.acquire()`. The 21st call blocks the entire event loop. No timeouts, no backoff, no error — the service hangs.

**Fix:**
```python
async with asyncio.timeout(10.0):
    async with pool.acquire(timeout=10.0) as conn:
        ...
```

### Pattern 3: Fail-Open Distributed Locks — Concurrent Singleton Execution

**Affected files:** `cron_lock.py`, `garbage_collector.py` (line 48), `auth.py` (rate limiter).

**The Anti-Pattern:** Distributed locks (implemented via Redis SETNX or similar) return `True` (lock acquired) on any error, including Redis unavailability. The calling job then executes, assuming it is the sole executor. Under Redis outage, all instances execute the job concurrently.

**Impact:** Non-idempotent jobs (bridge subscription renewal, saga recovery, garbage collection with false-orphan deletion) produce duplicate operations, inconsistent state, double-billing, or data loss. The codebase claims to have singleton distributed coordination; it actually has silent failure-to-coordinate under the most critical failure mode (Redis outage).

**Fix:**
```python
async def acquire_cron_lock(job_name: str, ttl: int, *, fail_open: bool = False) -> bool:
    try:
        # attempt SETNX
        acquired = await redis.set(key, uuid, ex=ttl, nx=True)
        return acquired
    except Exception as exc:
        log.error("Cron lock acquisition failed for %s: %s", job_name, exc)
        return fail_open  # caller decides based on idempotency
```

Non-idempotent jobs must explicitly set `fail_open=False` (fail-closed); idempotent jobs can tolerate a skip on outage.

### Pattern 4: append_event Without Transaction — WORM Guarantee Broken

**Affected files:** `cron.py` (line ~450), `memory.py` (lines 875, 927), `namespace.py` (lines 150–182), and others.

**The Anti-Pattern:** `append_event()` acquires an advisory lock via `pg_advisory_xact_lock()`, allocates a sequence number, and inserts a row. The advisory lock is **transaction-scoped** — it is released when the transaction ends. Calling `append_event()` without wrapping it in `async with conn.transaction():` means the advisory lock is acquired and released between the lock acquisition and the sequence allocation, destroying isolation.

**Impact:** The WORM event_log's gap-free sequence guarantee is broken. Multiple concurrent callers racing to call `append_event()` on the same namespace can receive the same sequence number, creating duplicate events. The audit trail is corrupted.

**Fix:**
```python
async with conn.transaction():
    await append_event(conn, ...)  # lock held for entire duration
```

### Pattern 5: N+1 MongoDB Queries — Latency Multiplier

**Affected files:** `semantic_search.py` (lines 281–291), `memory.py` (lines 1033–1037).

**The Anti-Pattern:** For each result from a primary database query, a secondary query is issued to MongoDB to fetch full document content. A query returning 100 results issues 100 sequential MongoDB round-trips.

**Impact:** Query latency scales linearly with result count. A `limit=100` search with 5ms MongoDB latency becomes 500ms minimum. Batch operations become infeasible.

**Fix:**
```python
# Instead of:
for result in pg_results:
    doc = await db.episodes.find_one({"_id": ObjectId(result["payload_ref"])})

# Do:
object_ids = [ObjectId(r["payload_ref"]) for r in pg_results]
docs = await db.episodes.find({"_id": {"$in": object_ids}}).to_list(length=len(object_ids))
doc_map = {str(d["_id"]): d for d in docs}
```

### Pattern 6: ContextVar Mutations Across Thread Boundaries

**Affected files:** `embeddings.py` (line ~180).

**The Anti-Pattern:** ContextVar mutations inside a ThreadPoolExecutor thread do not propagate to the caller's context. The `degraded_embedding_flag.set(True)` inside the executor thread sets the flag in the thread's copy of the context, which is discarded when the thread returns. The flag is never actually set in the calling coroutine's context.

**Impact:** The `degraded_embedding_flag` never propagates. Subsequent queries that check this flag do not know the embedding backend failed. Bad vectors are inserted into the index silently.

**Fix:**
```python
ctx = contextvars.copy_context()
result = await loop.run_in_executor(
    None, lambda: ctx.run(self._sync_embed_batch, texts)
)
```

### Pattern 7: Hardcoded Credentials and Dev Bypasses

**Affected files:** `config.py` (MINIO_SECRET_KEY), `server.py` (TRIMCP_ADMIN_OVERRIDE, admin_api_key in MCP schema).

**The Anti-Pattern:** Production credentials are committed as default values in config. Dev bypasses (environment variables like `TRIMCP_ADMIN_OVERRIDE=true`) lack environment checks and are shipped to production if not explicitly unset.

**Impact:** Any deployment that fails to override the defaults uses known credentials. Any operator who forgets to unset a dev bypass ships an auth bypass to production.

**Fix:**
- Default secrets to empty strings and raise errors if not set at startup.
- Add production environment guards to all dev bypasses.

---

### 19. trimcp/pii.py

**[plan]**
1. `require_master_key()` is a context manager (`@contextmanager`); calling it without `with` returns a generator object, not key bytes — crashes every reversible-pseudonymization call.
2. `AnalyzerEngine()` instantiation inside `_scan_sync` loads spaCy models on every call — ~500ms-2s per `store_memory`.
3. Master key used as HMAC pseudonym key with no version binding — key rotation silently invalidates all tokens.

**[execution]**

**CRITICAL — `require_master_key()` context manager misuse: reversible pseudonymization crashes on every call**
- Location: lines 207, 224–225, 249
- The Flaw: `mk = require_master_key() if config.reversible else None`. `require_master_key` is decorated with `@contextmanager` — calling it without `with` returns a `contextlib._GeneratorContextManager` object, not key bytes. Line 224: `encrypt_signing_key(entity.value.encode("utf-8"), mk)` receives the generator object → `TypeError` at the AES-GCM layer. Line 249: `mk.zero()` in the `finally` block → `AttributeError` on the generator object. Every namespace configured with `reversible=True` PII gets a crash instead of a redacted result. If the exception is swallowed upstream, the unredacted text is stored.
- The Fix: `with require_master_key() as mk: ... for entity in entities: encrypt_signing_key(entity.value.encode("utf-8"), mk)`. Move the entire entity-processing loop inside the `with` block so the key is live for the duration and is zeroed on context exit.

**MAJOR — `AnalyzerEngine()` instantiated on every `_scan_sync` call**
- Location: line 53 — `analyzer = AnalyzerEngine()`
- The Flaw: `AnalyzerEngine` from `presidio_analyzer` loads spaCy NLP models on construction (~400MB, 500ms–2s). `_scan_sync` is called for every `store_memory` invocation via `asyncio.to_thread`. Under moderate load (10 req/s), this creates 10 separate model load operations per second, saturating the thread pool and adding seconds of latency to every store operation.
- The Fix: Module-level singleton: `_analyzer: AnalyzerEngine | None = None; _analyzer_lock = threading.Lock()`. In `_scan_sync`: `global _analyzer; if _analyzer is None: with _analyzer_lock: if _analyzer is None: _analyzer = AnalyzerEngine()`.

**MAJOR — HMAC pseudonym key has no key version binding; rotation invalidates all existing tokens**
- Location: lines 146–152 — `os.environ.get("TRIMCP_MASTER_KEY", "").strip().encode("utf-8")` as HMAC key
- The Flaw: The master key is used directly as the HMAC-SHA256 key for pseudonym tokens. When `TRIMCP_MASTER_KEY` is rotated (required security practice), all existing pseudonym tokens in stored memories change value — any downstream system that stored tokens like `<EMAIL_abc123>` now cannot find the matching vault entry because the token hash changed. Silent data corruption: PII pseudonyms are permanently unresolvable after key rotation.
- The Fix: Bind the HMAC key to a key version: derive per-namespace per-version keys using `HKDF(master_key, info=f"pii:v{version}:{namespace_id}")`. Store the key version alongside vault entries so old tokens can be decrypted with the old derived key.

**MINOR — `os.environ.get` bypasses `cfg` for HMAC key**
- Location: line 146
- The Flaw: Uses `os.environ.get("TRIMCP_MASTER_KEY")` directly instead of `cfg.TRIMCP_MASTER_KEY`, bypassing config validation, redaction, and consistent secret management.
- The Fix: Use `cfg.TRIMCP_MASTER_KEY`.

**MINOR — `CREDIT_CARD` regex produces false positives on timestamps and phone numbers**
- Location: line 36 — `r"\b(?:\d[ -]*?){13,16}\b"`
- The Flaw: The pattern matches any 13–16 digit sequence with optional separators. ISO 8601 timestamps (`20241013123456`), phone numbers with extensions, and invoice numbers all match. Under `PIIPolicy.redact`, these false positives replace legitimate non-PII content.
- The Fix: Use a Luhn-validated regex or add a post-match Luhn check. The presidio `CREDIT_CARD` recognizer includes Luhn validation; the fallback regex should too.

**[validation]**

`pii.py` has a CRITICAL that makes reversible pseudonymization completely non-functional — `require_master_key()` called without `with` crashes on every invocation with `config.reversible=True`. This is the premium PII feature of the module and it crashes silently (if the caller swallows the exception, unredacted PII is stored). The `AnalyzerEngine` singleton gap degrades every `store_memory` call by 500ms–2s under load. `pii.py` is **not production-ready** for reversible PII configurations.

---

### 20. admin_server.py

**[plan]**
1. Unfiltered multi-tenant admin queries: five endpoints return data for all tenants when `namespace_id` is omitted; no pool acquires set RLS context.
2. `api_admin_verify_chain` — raw pool acquire with no RLS + passes connection to LIMIT-less Merkle chain fetch: authenticated DoS.
3. Fire-and-forget fork task and broken DLQ replay perpetuate the atomicity bugs from `replay.py` and `dead_letter_queue.py`.

**[execution]**

**CRITICAL — Cross-tenant event log, quota, and A2A grant leak via unguarded admin queries**
- Location: `api_admin_events` lines 745–783, `api_admin_events_summary` lines 830–856, `api_admin_a2a_grants` lines 957–988, `api_admin_a2a_grants_summary` lines 1039–1055, `api_admin_quotas` lines 1101–1121
- The Flaw: All five handlers build `where_sql = f"WHERE {' AND '.join(where)}" if where else ""`. When no `namespace_id` query param is supplied, `where_sql = ""` and the SELECT hits the entire multi-tenant table. `event_log`, `resource_quotas`, and `a2a_grants` all store rows for every tenant. None of the pool acquires call `set_namespace_context`, so RLS (if FORCE-enabled) either returns 0 rows silently or is bypassed entirely. An admin API caller — which only needs the HMAC key, not per-namespace credentials — gets all tenants' event history, quota balances, and A2A sharing arrangements with one unauthenticated-per-tenant request.
- The Fix: Require `namespace_id` for all admin query endpoints. Cross-namespace superadmin views must be served from a separately-audited superadmin role not reachable via the shared HMAC key.

**CRITICAL — `api_admin_verify_chain` triggers unbounded Merkle chain fetch (OOM/stall DoS)**
- Location: lines 904–906
- The Flaw: `async with engine.pg_pool.acquire() as conn: result = await verify_merkle_chain(conn, namespace_id=namespace_id)`. No `set_namespace_context` is called. More critically: `verify_merkle_chain` fetches every `event_log` row for the namespace with no LIMIT (identified in `event_log.py` audit). A namespace with 10M events exhausts worker RSS. The endpoint is reachable by any HMAC key holder, without mTLS in a default deployment.
- The Fix: Add `max_events` guard inside `verify_merkle_chain`; require explicit `from_seq`/`to_seq` bounds at this endpoint. Add `set_namespace_context` before the verify call.

**MAJOR — `api_replay_fork` creates an untracked fire-and-forget task**
- Location: line 445 — `asyncio.create_task(_run_fork(), name=f"fork-{fork_run_id}")`
- The Flaw: No reference to the task is stored. The `lifespan` context manager calls `await engine.disconnect()` without draining running forks. A fork that crashes after 30 seconds leaves `replay_runs` in a terminal state with no notification. Exceptions are logged inside `_run_fork` but not surfaced to any monitoring system.
- The Fix: Store the task in a module-level dict keyed by `fork_run_id`; in `lifespan` shutdown, cancel and await all pending fork tasks before disconnecting.

**MAJOR — `api_admin_dlq_replay` calls `replay_dead_letter` without `enqueue_fn`**
- Location: line 1455 — `result = await replay_dead_letter(engine.pg_pool, dlq_id)`
- The Flaw: `replay_dead_letter` marks `status='replayed'` then returns. The actual task re-enqueue to RQ happens outside the transaction. With no `enqueue_fn` argument wired here, re-enqueue never happens — the entry is stuck in `replayed` state permanently with the task never re-executed. The fix proposed in `dead_letter_queue.py` cannot take effect until this call site passes an `enqueue_fn`.
- The Fix: `await replay_dead_letter(engine.pg_pool, dlq_id, enqueue_fn=_rq_enqueue)`.

**MAJOR — All `pool.acquire()` calls lack `timeout=` and `set_namespace_context`**
- Location: lines 57, 418, 574, 628, 677, 781, 848, 905, 986, 1048, 1112, 1191, 1279
- The Flaw: Every direct pool acquire in the file omits `timeout=10.0`. Under pool exhaustion, all 13 request handlers queue indefinitely, stalling responses including `/api/health`. None set `set_namespace_context`.
- The Fix: `async with engine.pg_pool.acquire(timeout=10.0) as conn: await set_namespace_context(conn, ns_id)`.

**MAJOR — mTLS is opt-in with a default of disabled**
- Location: lines 1490–1496 — `enabled=cfg.TRIMCP_ADMIN_MTLS_ENABLED`
- The Flaw: The entire `/api/` surface is protected only by HMAC when `TRIMCP_ADMIN_MTLS_ENABLED` is not explicitly `true`. If `TRIMCP_API_KEY` leaks (env var in Docker Compose, CI logs), all admin endpoints including `dlq/replay`, namespace management, and Merkle chain verification are accessible from the public internet.
- The Fix: Default `TRIMCP_ADMIN_MTLS_ENABLED=true`. For deployments that cannot use mTLS, require explicit `TRIMCP_ADMIN_MTLS_ENABLED=false` with a startup warning.

**MINOR — `api_event_provenance` performs cross-tenant provenance trace**
- Location: lines 513–522
- The Flaw: `get_event_provenance(pool=engine.pg_pool, memory_id=memory_id)` — no `namespace_id` scoping. The provenance traversal can cross namespace boundaries via `parent_event_id` links without RLS context set.
- The Fix: Require `namespace_id` as a query param and pass it to `get_event_provenance`.

**MINOR — Lifespan startup partition check acquires pool connection with no timeout**
- Location: lines 57–79
- The Flaw: Under slow PG startup, `lifespan` blocks indefinitely before yielding, preventing health checks. Kubernetes liveness probes time out and restart the pod in a loop.
- The Fix: Add `timeout=30.0`; wrap in `asyncio.wait_for`.

**[validation]**

`admin_server.py` surfaces two CRITICALs that are dangerous at rest: unfiltered multi-tenant queries expose every tenant's event history, quota balances, and A2A grants to any HMAC key holder, and the `verify_chain` endpoint is a low-cost OOM DoS requiring the same key. mTLS default-off means the protection perimeter in a default deployment is a single symmetric secret. The DLQ replay is silently broken. `admin_server.py` is **not production-ready** and should not be internet-accessible in its current form.

---

### 21. trimcp/jwt_auth.py

**[plan]**
1. Issuer validation is silently disabled when `TRIMCP_JWT_ISSUER` is unconfigured — `require=["iss"]` forces claim presence but `issuer=None` accepts any issuer string.
2. Path traversal guard on `file://` PEM keys uses `Path.cwd()` — collapses to `/` in Docker without `WORKDIR`.
3. No algorithm safety check; `algorithm="none"` is operator-reachable.

**[execution]**

**MAJOR — Issuer claim required-but-not-validated when `TRIMCP_JWT_ISSUER` is unset**
- Location: lines 271, 280–287 — `resolved_issuer = cfg.TRIMCP_JWT_ISSUER or None` → `jwt.decode(..., issuer=None, ...)`
- The Flaw: `decode_options` includes `"iss"` in `require`, so PyJWT raises `MissingRequiredClaimError` if the claim is absent. But `issuer=None` passed to `jwt.decode` means PyJWT does not compare the claim's value to any expected issuer string — it only checks presence. Tokens with `"iss": "attacker-controlled-service"` pass validation as long as `exp` is valid and the signature verifies. For a multi-service deployment where `TRIMCP_JWT_SECRET` is reused, a JWT minted by any other service is accepted as a valid TriMCP agent credential.
- The Fix: Require `TRIMCP_JWT_ISSUER` in `cfg.validate()`. If not set, drop `"iss"` from `require` and log a warning — the current code looks strict but isn't.

**MAJOR — `file://` PEM key path traversal guard collapses in Docker**
- Location: lines 171–177 — `allowed_dir_raw = os.getenv("TRIMCP_JWT_KEY_DIR", str(Path.cwd()))`
- The Flaw: When `TRIMCP_JWT_KEY_DIR` is not set and the container runs without `WORKDIR`, `Path.cwd()` resolves to `/`. `key_path.is_relative_to(Path("/"))` is always `True`. Any absolute path passes the guard, reading any file on the container filesystem.
- The Fix: Require `TRIMCP_JWT_KEY_DIR` explicitly; raise `RuntimeError` at startup if a `file://` key is configured but `TRIMCP_JWT_KEY_DIR` is not set.

**MINOR — No algorithm safety check; `"none"` algorithm is operator-reachable**
- Location: line 255 — `algorithm = cfg.TRIMCP_JWT_ALGORITHM`
- The Flaw: `cfg.TRIMCP_JWT_ALGORITHM` is a free string. `"none"` would accept unsigned tokens. Startup check validates key availability, not algorithm safety.
- The Fix: `assert algorithm in {"HS256", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"}, f"Unsafe JWT algorithm: {algorithm!r}"` at module load.

**MINOR — JTI replay protection advertised but not implemented**
- Location: module docstring line 41
- The Flaw: `jti` is documented as available for replay detection, but there is no nonce store, no `jti` extraction, and no replay check in `decode_agent_token`. Operators who rely on this in threat model documentation are deceived.
- The Fix: Implement `jti` tracking via the Redis nonce store, or remove the JTI reference from the docstring.

**NITPICK — Error reason reflects raw attacker-controlled claim value**
- Location: line 352 — `f"invalid_claim:namespace_id:{raw_ns!r}"`
- The Fix: Return `"invalid_claim:namespace_id"` without the raw value.

**[validation]**

`jwt_auth.py` is structurally the cleanest file in the codebase — PyJWT integration is correct and exception handling is exhaustive. Both MAJORs are operator-misconfiguration traps: `TRIMCP_JWT_ISSUER` being unconfigured looks safe (because `require=["iss"]` is set) but is silently unsafe, and the `Path.cwd()` PEM key guard is the same Docker `/` collapse seen in `orchestrator.py`. With those two fixed and the algorithm allowlist added, `jwt_auth.py` would be **production-ready**.

---

### 22. trimcp/mtls.py

**[plan]**
1. `enabled=False` default makes every instantiation a silent no-op unless explicitly overridden.
2. Duplicate HTTP header last-write-wins enables cert header injection.
3. `str(exc)` in error response leaks internal mTLS configuration.

**[execution]**

**MAJOR — `enabled=False` default makes instantiation a silent no-op**
- Location: line 54 — `enabled: bool = False`
- The Flaw: The middleware constructor defaults to `enabled=False`. Every call site must explicitly pass `enabled=True` or the middleware is a transparent pass-through. Combined with `cfg.TRIMCP_ADMIN_MTLS_ENABLED` defaulting to False in admin_server.py, two independently-false defaults both must be overridden for mTLS to engage. One misconfiguration silently disables a security layer with no log output.
- The Fix: Default `enabled=True`. Require explicit `enabled=False` with a startup warning for deployments that genuinely cannot use mTLS.

**MINOR — Duplicate header last-write-wins in header dict construction**
- Location: lines 81–82 — `headers[key.decode("latin-1").lower()] = value.decode("latin-1")`
- The Flaw: When the ASGI scope contains two `x-ssl-client-cert` headers, this loop takes the last one. An attacker who can inject a header upstream of the proxy wins the dict value if the load balancer appends rather than overwrites.
- The Fix: Collect security-sensitive header values as `list[str]` and pass the first occurrence to `mtls_enforce`.

**MINOR — `str(exc)` in client error response may expose internal mTLS configuration**
- Location: line 102 — `"data": {"reason": str(exc)}`
- The Flaw: `A2AMTLSError` message from `mtls_enforce` is sent directly to the client. If `mtls_enforce` embeds SAN values or fingerprint expectations in the error (which it does — see `a2a.py` finding), clients learn the allowlist.
- The Fix: Map to opaque codes: `"reason": "mtls_certificate_rejected"` for mismatches, `"reason": "mtls_certificate_missing"` for absent cert.

**[validation]**

`mtls.py` is a thin 112-line shim. Its structural correctness depends on `mtls_enforce` in `a2a.py`. The file's own bugs: default-disabled posture silently nullifies the security layer, duplicate-header last-write-wins is exploitable when an attacker controls request headers upstream of the proxy, and error leakage. `mtls.py` is **not production-ready** as configured: the default `enabled=False` must be inverted before it provides any protection.

---

### 23. trimcp/a2a.py

**[plan]**
1. `enforce_scope` namespace wildcard is structurally broken: a namespace grant allows access to any memory/kg_node/subgraph regardless of which namespace they belong to, with no boundary check.
2. Proxy header trust for mTLS cert data has no origin validation — forged headers bypass cert verification when `trusted_proxy_hops > 0`.
3. Error messages leak cert fingerprint prefix and scope lists to the rejecting party.

**[execution]**

**CRITICAL — `enforce_scope` namespace wildcard allows cross-namespace resource access**
- Location: lines 817–825
- The Flaw:
  ```python
  if scope.resource_type == "namespace" and resource_type in ("memory", "kg_node", "subgraph"):
      return  # access granted — NO check that resource_id belongs to the granted namespace
  ```
  When a namespace-type scope exists, the function returns True for any memory/kg_node/subgraph regardless of which namespace it belongs to. Agent A grants `{resource_type:"namespace", resource_id:"ns-A"}` to Agent B. Agent B calls `enforce_scope(grant.scopes, "memory", "memory-in-ns-C")` → returns True. The comment claims "the RLS context enforces the boundary," but RLS is broken without open transactions, and `enforce_scope` is itself the authorization gate.
- The Fix: Add `resource_namespace_id: UUID` parameter. For namespace wildcards: `if scope.resource_type == "namespace" and scope.resource_id == str(resource_namespace_id) and resource_type in ("memory", "kg_node", "subgraph"): return`.

**MAJOR — `trusted_proxy_hops > 0` accepts cert headers from any request origin**
- Location: lines 513–515 — `if trusted_proxy_hops > 0: cert_dict = parse_client_cert_from_headers(headers)`
- The Flaw: `trusted_proxy_hops` controls which code path is taken, not whether the request originated from a trusted proxy. No check against the connection's remote IP. An attacker who can reach the ASGI port directly sends `X-Client-Cert-Fingerprint: <known-good-fingerprint>` and bypasses mTLS completely. The entire mTLS model collapses to header injection in any deployment without firewall-level protection of the ASGI port.
- The Fix: Before trusting cert headers, verify `scope["client"][0]` against a `TRIMCP_TRUSTED_PROXY_CIDRS` allowlist. If the CIDR check fails, fall back to `parse_client_cert_from_scope()` or reject.

**MAJOR — `validate_mtls_cert` error message leaks fingerprint prefix to client**
- Location: lines 474–478 — `f"Client certificate not in allowlist. Fingerprint: {fp_display}, SANs: {sans_display}"`
- The Flaw: The first 16 hex chars of the presented cert's fingerprint and the cert's SAN values are included in the `A2AMTLSError` message, which `mtls.py` forwards as `str(exc)` in the JSON response body. This reveals partial fingerprint of rejected certs and exposes CN/SAN values to the attacker.
- The Fix: `raise A2AMTLSError("mtls_certificate_rejected")`. Log the detail server-side only.

**MINOR — `verify_token` auto-expire UPDATE races with the SELECT fetch**
- Location: lines 630–658
- The Flaw: SELECT then separate UPDATE is not atomic. Between fetch and expire-UPDATE, a concurrent call may have already processed the same grant. The SELECT uses `AND status = 'active'`, so a concurrent expiry causes a misleading "Invalid or revoked token" error for a token that was valid.
- The Fix: Combine into a single `WITH cte AS (SELECT ... FOR UPDATE) UPDATE ... RETURNING ...` statement.

**MINOR — `A2AScopeViolationError` leaks granted scope list to requester**
- Location: line 829 — `f"Access denied: ... Available scopes: {[...]}"` 
- The Flaw: The full granted scope list (resource types and IDs) is included in the exception message returned to the caller. Agent B, denied access to a specific resource, learns the complete scope of what Agent A granted.
- The Fix: `"Access denied: requested resource is not covered by grant"` — no scope enumeration.

**[validation]**

`a2a.py` has a CRITICAL that makes the entire A2A authorization model untrustworthy: a namespace-type scope grants access to any resource of any type in any namespace, not just the named namespace. This bypass requires only a legitimate (but minimally-scoped) grant. The proxy header forgery MAJOR means mTLS is completely bypassable in any reverse-proxy deployment (which is the documented deployment model). `a2a.py` is **not production-ready** for the A2A sharing feature in its current form.

---

## Remaining Files Not Yet Audited

The following files are in scope for future audit phases but were not included in this Phase 6 report:

### 24. trimcp/a2a_server.py

**[plan]**
1. In-memory task store is process-local: tasks are lost on restart and grow without bound.
2. `archive_session` iterates `store_memory` serially with no bound or timeout, exhausting the pool.
3. Caller-controlled task IDs accepted without validation: silent overwrites.

**[execution]**

**MAJOR — In-memory task store: tasks lost on restart, unbounded growth**
- Location: line 149 — `_tasks: dict[str, dict[str, Any]] = {}`
- The Flaw: Every task is stored only in a module-level dict. On any process restart, all tasks vanish. Clients polling `/tasks/{task_id}` get 404. There is no eviction — every completed and failed task remains in memory indefinitely.
- The Fix: Persist task state in Redis with a TTL. Add an LRU eviction cap as a local cache in front of Redis.

**MAJOR — `pool.acquire()` without timeout and without RLS for `verify_token`**
- Location: line 370 — `async with _engine.pg_pool.acquire() as conn:`
- The Flaw: No timeout; no `set_namespace_context`. `verify_token` queries `a2a_grants` with RLS bypassed. Under pool exhaustion, every A2A task with a sharing token stalls indefinitely.
- The Fix: `async with _engine.pg_pool.acquire(timeout=10.0) as conn: await set_namespace_context(conn, caller_ctx.namespace_id)`.

**MAJOR — `archive_session` iterates `store_memory` serially with no bound or timeout**
- Location: lines 523–534 — `for m in memories: result = await _engine.store_memory(req)`
- The Flaw: Each `store_memory` holds a PG connection and runs embedding (~300ms). A 100-memory archive takes ~30s+ minimum. No `max_memories` cap enforced.
- The Fix: Cap `memories` at a configurable max (50). Run stores concurrently via `asyncio.gather` limited by a semaphore.

**MINOR — Caller-controlled task IDs accepted without validation; silent overwrites**
- Location: line 353 — `task_id: str = str(body.get("id") or uuid4())`
- The Flaw: Caller-supplied task IDs overwrite existing task state without a collision check. Values like `"<script>alert(1)</script>"` persist in task state returned in responses.
- The Fix: Generate `task_id` server-side unconditionally.

**MINOR — `A2AAuthorizationError`/`A2AScopeViolationError` messages leaked in JSON-RPC response**
- Location: lines 406, 414 — `str(exc)` in error body
- The Fix: Use opaque reasons: `"a2a_authorization_failed"`, `"a2a_scope_violation"`. Log full detail server-side.

**MINOR — `assert` instead of explicit guard in `_dispatch_skill`**
- Location: line 488 — `assert _engine is not None, "engine not initialized"`
- The Fix: `if _engine is None: raise RuntimeError("engine not initialized")`.

**[validation]**

`a2a_server.py` has correct graceful shutdown machinery — better than most files in the codebase. But the in-memory task store makes the A2A async task API non-durable, and the `archive_session` serial loop is a latency bomb under load. **Not production-ready** for multi-tenant or high-concurrency use.

---

### 25. trimcp/bridges/ (base.py, sharepoint.py, gdrive.py, dropbox.py)

**[plan]**
1. All three `download_file` implementations load entire file content into memory via `resp.content` with no size limit — a single large file OOM-kills the RQ worker.
2. Redis cursor keys incorporate untrusted webhook notification fields — attacker-controlled values overwrite legitimate cursors.
3. OAuth tokens stored as instance attributes not zeroed after use.

**[execution]**

**CRITICAL — `download_file` loads entire file into memory with no size cap**
- Location: `sharepoint.py` line 136, `gdrive.py` line 106, `dropbox.py` line 110 — `return resp.content`
- The Flaw: `resp.content` materializes the entire HTTP response body into a single `bytes` object. A 2GB SharePoint Excel file, 4GB GDrive video, or large Dropbox archive exhausts the RQ worker's RSS. No `Content-Length` check, no streaming with size limit. Worker dies; task is re-enqueued and retried on loop under Kubernetes.
- The Fix: Stream with `client.stream("GET", url)` and enforce a configurable max: `for chunk in resp.iter_bytes(8192): accumulated += len(chunk); if accumulated > MAX_FILE_BYTES: raise ValueError(...)`.

**MAJOR — SharePoint cursor keys incorporate untrusted notification fields**
- Location: `sharepoint.py` lines 80–90 — `site_id, drive_id = parsed; ck = self._cursor_key(site_id, drive_id); r.set(ck, delta_link)`
- The Flaw: `site_id` and `drive_id` are parsed from the `resource` field of the notification payload. If the webhook endpoint lacks authentication, an attacker can POST a forged notification with `site_id` and `drive_id` matching a legitimate subscription and overwrite the cursor with an attacker-controlled `delta_link` URL, causing the bridge to fetch from an attacker-controlled endpoint on the next real delivery.
- The Fix: Validate that `site_id`/`drive_id` match a registered subscription from the database (via `bridge_repo.py`) before using them as cursor keys.

**MINOR — `gdrive.py` has no URL safety check on Drive API calls**
- Location: `gdrive.py` lines 79–82
- The Flaw: Unlike `sharepoint.py` which calls `assert_url_allowed_prefix`, `gdrive.py` constructs Drive API URLs without prefix validation. Redis cursor poisoning could redirect requests to internal addresses.
- The Fix: Add `assert_url_allowed_prefix(url, ("https://www.googleapis.com/",), what="Google Drive API URL")` before each request.

**MINOR — `base.py` `redis_client()` creates a new TCP connection on every call**
- Location: `base.py` lines 59–65
- The Flaw: `Redis.from_url()` opens a new TCP connection on every `redis_client()` call. Bridge workers call this 2–3× per delta walk.
- The Fix: Module-level singleton with lazy init and `threading.Lock`.

**MINOR — OAuth token stored as instance attribute not zeroed after use**
- Location: `sharepoint.py` lines 52–87, `gdrive.py` lines 47–96, `dropbox.py` lines 47–63
- The Flaw: `self._oauth_token_override` stores raw bearer token. `finally` block sets it to `None` but does not zero the bytes. In fork-based RQ workers, parent process state containing live tokens is copied to child processes.
- The Fix: Store tokens in `bytearray` and zero on release. Or use `secrets.token_bytes` and `memoryview` zeroing pattern.

**[validation]**

The CRITICAL (full file download into memory) makes all three bridges unsuitable for enterprise document libraries where files regularly exceed several hundred MB. The cursor key injection MAJOR requires only an unauthenticated webhook POST. **Not production-ready** for anything beyond small-file stores.

### 26. trimcp/bridge_renewal.py

**[plan]**
1. `require_master_key()` called without `with` at four sites — all OAuth token decryption is broken.
2. `_perform_oauth_refresh` (30s HTTP call) executed inside a `FOR UPDATE` transaction — lock held for full HTTP duration.
3. `renew_gdrive` non-atomic stop+watch leaves orphaned subscription on watch failure.

**[execution]**

**CRITICAL — `require_master_key()` context manager misuse: all OAuth token decryption broken**
- Location: lines 206, 265, 325, 380 — `decrypt_signing_key(bytes(raw), require_master_key())`
- The Flaw: Same as `pii.py` — `require_master_key()` without `with` returns a generator object, not key bytes. `decrypt_signing_key` receives the generator → TypeError at all four call sites. Every bridge relying on encrypted stored OAuth tokens (all bridges after initial token handoff) gets an empty bearer token and 401s from Microsoft/Google/Dropbox on every API call.
- The Fix: `with require_master_key() as mk: decrypted = decrypt_signing_key(bytes(raw), mk).decode("utf-8")`. Apply to all four call sites.

**MAJOR — `_perform_oauth_refresh` HTTP call executed inside a `FOR UPDATE` transaction**
- Location: lines 311–367
- The Flaw: The OAuth token endpoint HTTP POST (30s timeout) is executed while holding a `FOR UPDATE` lock on the `bridge_subscriptions` row inside an open transaction. Lock held for up to 30 seconds per renewal. Under concurrent renewal of multiple subscriptions, the pool exhausts.
- The Fix: Fetch and extract outside the transaction, release the connection, make the HTTP call, re-acquire to save the new token with an optimistic concurrency check.

**MAJOR — `renew_gdrive` non-atomic stop+watch leaves orphaned subscription on watch failure**
- Location: lines 491–535
- The Flaw: `channels/stop` runs first. If it succeeds but `changes/watch` fails, the old channel is gone and no new one was created. Bridge marked DEGRADED with stale `subscription_id`/`resource_id` requiring manual recovery.
- The Fix: Write new `subscription_id` to DB first (in transaction), then stop old, then register new. Separate "stop failed" from "watch failed" in the DEGRADED reason.

**MAJOR — All `pool.acquire()` calls without timeout**
- Location: lines 194, 311, 430, 520, 546, 567
- The Fix: `pool.acquire(timeout=10.0)` at every site.

**MINOR — `renew_expiring_subscriptions` uses `SELECT *`**
- Location: line 568
- The Flaw: Fetches encrypted OAuth token blob for every expiring subscription even before the token is needed.
- The Fix: Select explicit columns; load token inside the renewal function only.

**MINOR — `get_token_expiry` decodes JWT without signature verification without a comment**
- Location: line 80 — `jwt.decode(token, options={"verify_signature": False})`
- The Fix: Add `# intentional: claims-only read for expiry check, not for auth`.

**[validation]**

`bridge_renewal.py` has a CRITICAL that makes encrypted OAuth token storage completely non-functional — all four `require_master_key()` misuse sites crash with TypeError. The FOR UPDATE HTTP call MAJOR creates a 30-second lock window. **Not production-ready**.

---

### 27. trimcp/bridge_repo.py

**[plan]**
1. `require_master_key()` called without `with` in both `save_token` and `get_token` — same contextmanager misuse as `pii.py` and `bridge_renewal.py`.
2. Multiple `SELECT *` queries return the encrypted OAuth token blob even when not needed.

**[execution]**

**CRITICAL — `require_master_key()` context manager misuse in `save_token` and `get_token`**
- Location: lines 317–318 and lines 353–354
- The Flaw: Same as `pii.py` and `bridge_renewal.py`. Both `save_token` and `get_token` receive the generator object as the key → TypeError. All OAuth token storage and retrieval via the canonical `bridge_repo` path is non-functional.
- The Fix: `with require_master_key() as mk:` wrapping both operations.

**MINOR — Multiple queries use `SELECT *` including encrypted token column**
- Location: `get_by_id` line 108, `fetch_active_subscription` line 241, `list_for_user` lines 121–135, `fetch_expiring` line 90
- The Flaw: All four functions return encrypted token bytes for every row, even `list_for_user` which is used for display-only purposes.
- The Fix: Use explicit column lists; only `get_token` needs the token column.

**MINOR — `update_subscription` dynamic SQL via f-string on allowlisted column names**
- Location: lines 154–161
- The Flaw: Column names are interpolated directly into the SQL string via f-string, bypassing parameterized query protection. The allowlist is correct today but fragile to extension.
- The Fix: Map allowed field names to literal SQL column fragments in an explicit dict.

**[validation]**

`bridge_repo.py` is the canonical token storage layer. Both `save_token` and `get_token` crash on every call due to `require_master_key()` misuse. The entire bridge OAuth lifecycle is broken. **Not production-ready**.

---

### 28. trimcp/bridge_runtime.py

**[plan]**
1. Full `TriStackEngine` spawned per token resolution call — new PG pool per webhook notification.
2. `asyncio.run()` in sync function will crash under event-loop-aware workers.

**[execution]**

**CRITICAL — Full `TriStackEngine` spawned on every call: new PG pool per token resolution**
- Location: lines 42–43 — `engine = TriStackEngine(); await engine.connect()`
- The Flaw: `resolve_stored_oauth_access_token` is called from `walk_delta` during webhook processing. Every invocation creates a new `asyncpg.Pool` (TCP handshakes, PG authentication) and `AsyncIOMotorClient`, makes one query, then tears down. Under a SharePoint webhook batch of 50 notifications, this creates 50 new connection pools. Connection limits exhausted.
- The Fix: Pass an existing `asyncpg.Pool` from the bridge worker's persistent context. Never construct a TriStackEngine per-lookup.

**MAJOR — `asyncio.run()` in synchronous function crashes under event-loop-aware workers**
- Location: line 83 — `return asyncio.run(_run_with_timeout())`
- The Flaw: If the RQ worker uses `gevent` or any cooperative I/O wrapper, `asyncio.run()` raises `RuntimeError: This event loop is already running`.
- The Fix: Accept a `loop` parameter or make the function async and require callers to await it.

**MAJOR — `pool.acquire()` without timeout**
- Location: line 45. The Fix: `engine.pg_pool.acquire(timeout=10.0)`.

**MINOR — `_RESOLVE_TIMEOUT_S` loaded via `os.environ.get` bypassing `cfg`**
- Location: line 21. The Fix: Add `BRIDGE_RESOLVE_TIMEOUT_S` to `cfg`.

**[validation]**

`bridge_runtime.py` has a CRITICAL that makes it unusable under real webhook load. Combined with `bridge_repo.py`'s CRITICAL, the entire bridge OAuth token flow has two independent CRITICALs. **Not production-ready**.

---

### 29. trimcp/webhook_receiver/main.py

**[plan]**
1. Module-level `_require_env` for all three providers at startup — crashes if any provider's secret is unconfigured.
2. New Redis connection per webhook notification.
3. No body size limit on public webhook endpoints.

**[execution]**

**MAJOR — Module-level `_require_env` forces all three provider secrets to be configured at startup**
- Location: lines 35–37
- The Flaw: All three secrets required at import time. A deployment using only SharePoint fails to start because `DROPBOX_APP_SECRET` and `DRIVE_CHANNEL_TOKEN` are missing.
- The Fix: Lazy-load provider secrets on first request; raise HTTP 503 if unconfigured.

**MAJOR — New Redis connection created per webhook notification**
- Location: line 47 — `Redis.from_url(cfg.REDIS_URL)` inside `enqueue_process_bridge_event`
- The Flaw: New TCP connection per webhook delivery. SharePoint burst notifications (10–50 per POST) open 10–50 Redis connections per webhook.
- The Fix: Module-level Redis connection pool singleton.

**MINOR — No request body size limit on webhook endpoints**
- Location: lines 71, 100 — body read before size validation
- The Flaw: Full body materialized before HMAC check; a 1GB POST exhausts worker memory.
- The Fix: Check `Content-Length` before reading; configure uvicorn body limits.

**MINOR — MS Graph `validationToken` echo accepts any input without validation**
- Location: lines 97–98
- The Fix: Validate `validationToken` matches UUID format before echoing.

**[validation]**

HMAC verification is correct and constant-time for all three providers. Resource URL validation provides SSRF defense. Relative to the rest of the codebase, this file is near production-ready — fix the MAJORs and it's deployable.

---

---

### 30. trimcp/orchestrators/graph.py

**[plan]**
1. Custom `scoped_session` calls `set_namespace_context` outside a transaction — SET LOCAL no-op, RLS bypassed on all graph queries.
2. N+1 MongoDB `find_one` per result row in `search_codebase` (up to 100 serial awaits).
3. `pool.acquire()` without timeout in `scoped_session`.

**[execution]**

**CRITICAL — `set_namespace_context` called outside transaction (RLS bypassed)**
- Location: `scoped_session`, lines 62–64
- The Flaw: `set_namespace_context` executes `SET LOCAL app.current_namespace_id = $1`. `SET LOCAL` only persists for the current transaction. In asyncpg autocommit mode, there is no transaction, so the setting reverts immediately. RLS policies see an empty namespace for all subsequent queries in this session. Cross-tenant data leak on all `search_codebase` and `graph_search` calls. Identical to the bug in db_utils.py, memory.py, namespace.py, garbage_collector.py.
- The Fix: `async with self.pg_pool.acquire(timeout=10.0) as conn: async with conn.transaction(): await set_namespace_context(conn, ns_uuid); yield conn`

**MAJOR — N+1 MongoDB `find_one` per result in `search_codebase`**
- Location: lines 225–228, inside `for row in rows` loop
- The Flaw: Up to `top_k` (max 100) sequential `await self._mongo_db.code_files.find_one({"_id": oid})` calls. At 5ms round-trip per query, 100 results = 500ms serial I/O blocking the asyncio task.
- The Fix: Batch all ObjectIds into a single `find({"_id": {"$in": oids}})` and map results.

**MAJOR — `pool.acquire()` without timeout**
- Location: `scoped_session`, line 61
- The Fix: `self.pg_pool.acquire(timeout=10.0)`.

**MINOR — Positional SQL parameter numbers hardcoded in f-string clauses**
- Location: lines 131–165 — `scope_clause = "AND user_id = $5"` hardcoded with `$5`
- The Flaw: Adding a parameter before position 5 silently shifts the binding to the wrong value with no compile-time error.
- The Fix: Compute positional numbers from `len(query_params)` dynamically.

**MINOR — `except Exception: pass` in MongoDB excerpt hydration**
- Location: lines 224–229
- Connection failures and invalid ObjectIds are silently swallowed. Fix: `log.warning("code excerpt fetch failed: %s", e)`.

**[validation]**
RRF fusion logic is correct. Parameter validation (`_SAFE_ID_RE`, `_ALLOWED_LANGUAGES`) is present. The RLS bypass and N+1 MongoDB pattern are the only substantial issues. **Not production-ready** until SET LOCAL is wrapped in a transaction.

---

### 31. trimcp/orchestrators/cognitive.py

**[plan]**
1. `scoped_session` delegates to `scoped_pg_session` from db_utils — `set_namespace_context` runs outside any transaction, SET LOCAL no-op. All 4 methods affected.
2. `list_contradictions` uses `SELECT *` and accepts unvalidated `resolution` enum value.
3. Inherits systemic pool.acquire() timeout absence from db_utils.

**[execution]**

**CRITICAL — Inherited RLS bypass: `set_namespace_context` runs before any transaction**
- Location: `scoped_session` → `scoped_pg_session` (db_utils) → `set_namespace_context`, called before `yield conn`. All 4 methods affected.
- The Flaw: `set_namespace_context` executes `SET LOCAL` in autocommit mode, reverting immediately. The `conn.transaction()` blocks in `boost_memory`/`forget_memory`/`resolve_contradiction` start transactions AFTER the namespace context has already reverted. `list_contradictions` has no transaction at all — reads directly with zero namespace context. Cross-tenant data leak on all queries.
- The Fix: `set_namespace_context` must run as the first statement INSIDE `conn.transaction()`, not before it. The root fix is in `db_utils.scoped_pg_session`.

**MINOR — `SELECT *` on `contradictions` table**
- Location: `list_contradictions`, line 159
- Fix: Enumerate required columns explicitly.

**MINOR — `resolution` string not validated against enum allowlist**
- Location: lines 162–164
- The value is parameterized (no injection), but any arbitrary string is accepted as filter. Fix: validate against `frozenset({'approved', 'rejected', 'deferred'})` before use.

**[validation]**
`cognitive.py` is structurally the cleanest orchestrator audited — it correctly uses `conn.transaction()` for all mutations. The only flaw is that `set_namespace_context` runs outside those transactions due to `scoped_pg_session`. One targeted fix to `db_utils.scoped_pg_session` fixes this file entirely. **Not production-ready** until RLS is corrected.

---

### 32. trimcp/orchestrators/migration.py

**[plan]**
1. `start_migration` check-then-act (SELECT active → INSERT) outside a transaction — TOCTOU race, two concurrent callers create two simultaneous migrations.
2. `_validate_path` uses `Path.cwd()` — collapses to `/` in Docker, making path traversal guard a no-op.
3. `pool.acquire()` without timeout on all 6 method calls.

**[execution]**

**CRITICAL — TOCTOU race in `start_migration` (no transaction wrapping check + insert)**
- Location: lines 139–161 — `SELECT id FROM embedding_migrations WHERE status IN ('running', 'validating')` → `INSERT INTO embedding_migrations` — two queries, no transaction
- The Flaw: Two concurrent `start_migration` calls both see no active migration, both proceed, both INSERT. Database ends with two concurrent running migrations; embedding model status column is double-updated. No unique constraint prevents this.
- The Fix: Wrap the check and insert in `conn.transaction()` with `SELECT ... FOR UPDATE SKIP LOCKED` on the active migration check, or use a PostgreSQL advisory lock.

**MAJOR — `_validate_path` collapses to `/` in Docker**
- Location: lines 48–51 — `cwd = Path.cwd().resolve()`
- The Flaw: Docker containers run with CWD=`/`. `str(cwd)` = `"/"`. Every resolved absolute path starts with `"/"`, so the traversal check always passes. An attacker can supply any filesystem path (e.g., `/etc/passwd`). Identical to the bug in `orchestrator.py`.
- The Fix: Set `TRIMCP_SAFE_DIR` env var at startup; validate it's non-root; use it as the allowed root.

**MAJOR — `pool.acquire()` without timeout (6 call sites)**
- Location: lines 139, 164, 181, 195, 223, 248
- Fix: `pool.acquire(timeout=10.0)` at each site.

**MINOR — MD5 for file deduplication**
- Location: line 77 — `hashlib.md5(payload.raw_code.encode()).hexdigest()`
- MD5 has known collision attacks. Fix: `hashlib.sha256`.

**[validation]**
`migration.py` handles an admin lifecycle operation appropriately without tenant scoping. The TOCTOU race is the only safety issue; the rest are defensive hardening. Fix the CRITICAL and it's deployable for admin use.

---

### 33. trimcp/orchestrators/temporal.py

**[plan]**
1. Custom `scoped_session` (copy of graph.py implementation) — SET LOCAL outside transaction, RLS bypassed on all snapshot and diff operations.
2. `trigger_consolidation` creates an `asyncio.Task` with no stored reference — fire-and-forget, silent crash.
3. `compare_states` full-namespace UNION ALL query has no LIMIT — unbounded OOM.

**[execution]**

**CRITICAL — RLS bypass in custom `scoped_session`**
- Location: lines 104–123 — identical to `graph.py:scoped_session`
- The Flaw: `set_namespace_context` executes `SET LOCAL` outside any transaction. In asyncpg autocommit, the namespace setting reverts immediately. All snapshot and diff queries run without namespace context. Cross-tenant data leak on `list_snapshots`, `compare_states`, `create_snapshot`.
- The Fix: `async with self.pg_pool.acquire(timeout=10.0) as conn: async with conn.transaction(): await set_namespace_context(conn, ns_uuid); yield conn`

**MAJOR — Fire-and-forget `asyncio.create_task` in `trigger_consolidation`**
- Location: line 182 — `asyncio.create_task(worker.run_consolidation(...))`
- The Flaw: No reference stored. Task exception is silently discarded. Caller receives `{"status": "triggered"}` but work may never happen. No way to correlate to `consolidation_status`.
- The Fix: Store reference and attach a `done_callback` for failure logging. Better: use RQ for durable execution via the existing task infrastructure.

**MAJOR — Unbounded UNION ALL in `compare_states` full-namespace diff**
- Location: lines 412–440 — UNION ALL of added+removed memories between two timestamps, no LIMIT
- The Flaw: A namespace with 500K memories and a year-wide time range materializes all 500K rows into the Python process. Combined with `_hydrate` running N+1 MongoDB `find_one` per result, this is both an OOM vector and a throughput killer.
- The Fix: Add `LIMIT 1000` to the UNION ALL; paginate via cursor. Batch the MongoDB hydration to a single `find({"_id": {"$in": [...]})`.

**MINOR — `pool.acquire()` without timeout**
- Location: lines 169, 195, 411
- Fix: `pool.acquire(timeout=10.0)`.

**MINOR — `json.loads(ns_row["metadata"])` crashes when asyncpg returns JSONB as dict**
- Location: line 176 — `metadata = json.loads(ns_row["metadata"])`
- The Flaw: asyncpg decodes JSONB columns as Python dicts. `json.loads(dict)` raises TypeError.
- The Fix: `metadata = _metadata_as_dict(ns_row["metadata"])` (module already defines this helper).

**[validation]**
`temporal.py` has solid lineage-tracking logic for state diffs. Fix the CRITICAL (RLS), fire-and-forget task, and OOM query, and it's production-ready. **Not production-ready** as written.

---

---

### 39. trimcp/admin_mcp_handlers.py

**[plan]**
Thin RBAC-enforced routing facade. Decorator stack `@require_scope("admin")` → `@admin_rate_limit` → `@mcp_handler` is intentional per docstring. No domain logic here.

**[execution]**

**MINOR — `handle_rotate_signing_key`: `pool.acquire()` without timeout**
- Location: line 116
- Fix: `engine.pg_pool.acquire(timeout=10.0)`.

**[validation]** RBAC and rate limiting applied correctly. **Production-ready** with minor fix.

---

### 40–48. MCP Handler Files (9 remaining files)

**Collective overview:** All files follow the correct thin-facade SRP pattern — parse args → delegate to engine → serialize response. `@mcp_handler` handles exception formatting; `@require_scope("admin")` handles RBAC where required. Clean architecture.

**[execution]**

**MAJOR — `bridge_mcp_handlers.py`: `disconnect_bridge` missing `@mcp_handler` decorator**
- Location: line 447 — `async def disconnect_bridge(...)` — no decorators
- The Flaw: All other handlers have `@mcp_handler` for standardized exception handling. If httpx times out on subscription delete, or `bridge_repo.save_token` crashes (which it will due to CRITICAL in bridge_repo.py), the exception propagates unformatted to the MCP framework.
- The Fix: Add `@mcp_handler`.

**MAJOR — `bridge_mcp_handlers.py`: `pool.acquire()` without timeout (9 call sites)**
- Location: lines 242, 354, 399, 439, 451, 466, 496, 517, 598

**MAJOR — `replay_mcp_handlers.py`: Fire-and-forget `asyncio.create_task` in fork and reconstruct**
- Location: lines 103, 149 — `asyncio.create_task(_run_fork())` and `asyncio.create_task(_run())`
- The Flaw: No stored reference. Task exceptions silently discarded. Caller receives `{"status": "started"}` but replay may never run. Identical to the bug in `admin_server.py:445` and `temporal.py:182`.
- The Fix: Store task reference; attach `done_callback` for failure logging and status update.

**MAJOR — `a2a_mcp_handlers.py`: `pool.acquire()` without timeout (4 call sites)**
- Location: lines 63, 82, 96, 109

**MINOR — `bridge_mcp_handlers.py`: Redis connection churn in `bridge_redis()`**
- Location: line 591 — `Redis.from_url(cfg.REDIS_URL)` creates a new TCP connection per call; `force_resync_bridge` line 534 calls `Redis.from_url()` directly.
- Fix: Module-level singleton Redis connection pool.

**MINOR — `bridge_mcp_handlers.py`: TOCTOU in `complete_bridge_auth`**
- Location: lines 354–415 — DB ownership check then `_exchange_oauth_code` then UPDATE, non-atomic
- The Flaw: Two concurrent calls with the same `bridge_id` both pass ownership check and exchange codes. Fix: Wrap in `SELECT ... FOR UPDATE`.

**MINOR — `a2a_mcp_handlers.py`: `resource_type` defaults to `"namespace"` in `handle_a2a_query_shared`**
- Location: line 114 — `arguments.get("resource_type", "namespace")`
- NOTE: This default triggers the `enforce_scope` namespace-wildcard bypass (CRITICAL in `a2a.py`). Callers who omit `resource_type` get full cross-namespace access. Fix is in `a2a.py:enforce_scope`.

**MINOR — `migration_mcp_handlers.py`: `pool.acquire()` without timeout in `_audit_migration_action`**
- Location: line 76

**MINOR — `snapshot_mcp_handlers.py`: `pool.acquire()` without timeout**
- Location: lines 126, 179

**[validation]**
The 10 MCP handler files are well-structured thin facades. Four files have actionable issues: `bridge_mcp_handlers.py` (missing decorator, Redis churn, TOCTOU), `replay_mcp_handlers.py` (fire-and-forget tasks), `a2a_mcp_handlers.py` (pool timeout), `migration_mcp_handlers.py` and `snapshot_mcp_handlers.py` (pool timeout). The other five files are production-ready as-is.

---

---

### 49. trimcp/replay.py

**[plan]**
1. `pool.acquire()` inside long-lived server-side cursor transaction — 2 concurrent replays need 4+ pool connections, risking deadlock.
2. LLM API calls (`_resolve_llm_payload` re-execute mode) made while `cursor_conn` REPEATABLE READ transaction is open — 30–60s call holds a PG connection.
3. `pool.acquire()` without timeout throughout.

**[execution]**

**MAJOR — `pool.acquire()` inside long-lived cursor transaction; concurrent replays deadlock pool**
- Location: `ForkedReplay.execute` line 1306 (`write_conn`) and 1336 (`prog_conn`) — both inside `cursor_conn.transaction()` opened at line 1272
- The Flaw: `cursor_conn` holds one connection for the full replay duration. Each event needs a second connection (`write_conn`); every 10th event needs a third (`prog_conn`). With `pool.max_size=4`, two concurrent replays need 4 connections minimum; the progress update needs a 5th — both callers hang forever waiting for a pool slot that never frees.
- The Fix: Increase `pool.max_size` to handle concurrent replays, or use `asyncio.wait_for(pool.acquire(), timeout=10.0)` so deadlock surfaces quickly rather than hanging indefinitely.

**MAJOR — LLM API call inside REPEATABLE READ cursor transaction (re-execute mode)**
- Location: `ForkedReplay.execute` line 1297 — `await _resolve_llm_payload(...)` in re-execute mode makes provider LLM calls (30–60s) while `cursor_conn.transaction()` is open
- The Flaw: A 30–60 second LLM call holds a PostgreSQL connection in REPEATABLE READ. All other pool waiters are blocked for the full duration.
- The Fix: Move `_resolve_llm_payload` outside the cursor transaction context; fetch one step ahead of the apply loop.

**MAJOR — `pool.acquire()` without timeout (12 call sites)**
- Location: lines 959, 982, 995, 1012, 1022, 1043, 1224, 1240, 1271, 1284, 1306, 1336, 1346

**MINOR — New `Minio` client per LLM payload fetch/put**
- Location: `_make_minio()` called at lines 361, 387 — one new HTTP client per event in deterministic replay
- Fix: Class-level Minio singleton.

**[validation]**
Excellent structural design — WORM-compliant causal provenance, `FrozenForkConfig` immutability, server-side cursors for memory efficiency, signature verification on every event. The two MAJORs manifest only under load. **Production-ready** for single concurrent replay; **not safe** for concurrent use with default pool size.

---

### 50. trimcp/reembedding_worker.py

**[plan]**
1. `FOR UPDATE SKIP LOCKED` lock released before UPDATE — fetch and update use different connections, leaving a race window for duplicate re-embedding.
2. PostgreSQL advisory lock held during LLM embedding call, consuming a pool connection for 1–5 seconds.
3. `pool.acquire()` without timeout throughout.

**[execution]**

**MAJOR — `FOR UPDATE SKIP LOCKED` lock released before UPDATE; rows can be processed twice in multi-instance deployments**
- Location: `_run_memories_phase`, lines 482–526 — `FOR UPDATE SKIP LOCKED` in transaction at lines 483–490, released when block exits; `_update_memories_batch` runs on a NEW connection at line 525
- The Flaw: The row-level lock is released at line 490 when the first `conn.transaction()` block exits. Another worker can acquire the same rows between line 490 and line 525. Both workers update the same embedding. `FOR UPDATE SKIP LOCKED` only works when fetch and update are in the SAME open transaction.
- The Fix: Acquire one connection for the full batch cycle — fetch (with `FOR UPDATE SKIP LOCKED`), embed, update — all within a single `conn.transaction()`.

**MAJOR — PostgreSQL advisory lock held during embedding API call**
- Location: `_embed`, lines 405–410 — `pg_advisory_lock` held across `await _embeddings.embed_batch(texts)` (1–5s)
- The Flaw: Holds a pool connection for the full embedding duration. With `pool.max_size=4`, a 5-second embedding blocks one of 4 connections.
- The Fix: Use `asyncio.Lock()` at Python level to serialize embedding calls without holding a DB connection.

**MAJOR — `pool.acquire()` without timeout (9 call sites)**
- Location: lines 405, 417, 439, 482, 525, 535, 571, 581, 591

**MINOR — Schema DDL runs on every `run_once()` call**
- Location: `_ensure_schema`, line 138 — `CREATE TABLE IF NOT EXISTS` per run
- Fix: Check once at startup.

**[validation]**
Solid keyset pagination, rate-limiting, and checkpoint resumability. The `FOR UPDATE`/update connection split is critical in multi-instance deployments. **Production-ready** for single-instance; **not safe** for multi-instance until fetch+update are in one transaction.

---

**Remaining Files Not Yet Audited:**

**Advanced Orchestrators:**
- ~~`trimcp/orchestrators/graph.py`, `trimcp/orchestrators/cognitive.py`, `trimcp/orchestrators/migration.py`, `trimcp/orchestrators/temporal.py`~~ *(audited above)*

---

### 34. trimcp/consolidation.py

**[plan]**
1. `_store_consolidated_memory` writes directly to `event_log` bypassing `append_event`'s advisory-lock + sequence guarantee — WORM integrity violation.
2. `_call_consolidation_llm` sends MongoDB ObjectId references to the LLM, not actual memory content — LLM consolidates garbage.
3. `pool.acquire()` without timeout across 6 call sites.

**[execution]**

**CRITICAL — Direct `INSERT INTO event_log` bypasses advisory-lock sequence guarantee**
- Location: `_store_consolidated_memory`, lines 227–251
- The Flaw: `seq = await conn.fetchval("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM event_log WHERE namespace_id = $1")` then `INSERT INTO event_log (event_seq=seq, ...)`. Two concurrent consolidation runs both read `MAX(event_seq) = N`; both insert row `N+1`, hitting a UNIQUE constraint violation (or producing duplicate event_seq values that corrupt WORM chain integrity). `append_event()` uses a PostgreSQL advisory lock + NEXTVAL sequence specifically to prevent this — bypassing it violates the WORM contract.
- The Fix: Replace manual seq computation and INSERT with `await append_event(conn, namespace_id=namespace_id, agent_id="system", event_type="consolidation_run", params=event_params)`.

**MAJOR — LLM receives MongoDB ObjectId references, not memory content**
- Location: `_call_consolidation_llm`, lines 160–161 — `payloads = [m["payload_ref"] for m in cluster_mems]`
- The Flaw: For episodic memories, `payload_ref` is a MongoDB ObjectId string (e.g., `"507f1f77bcf86cd799439011"`). The LLM receives a JSON array of hex strings and produces abstractions from opaque identifiers, not actual memory content. Every consolidation run outputs semantically meaningless abstractions.
- The Fix: Batch-fetch content from MongoDB before calling the LLM: `docs = {str(d["_id"]): d async for d in mongo_db.episodes.find({"_id": {"$in": oids}})}`.

**MAJOR — `pool.acquire()` without timeout (6 call sites)**
- Location: lines 343, 367, 380, 400, 420, 435
- Fix: `pool.acquire(timeout=10.0)`.

**MINOR — `_cluster_memories` (sync version) is dead code**
- Location: lines 96–121
- `asyncio.run(clusterer.fit_predict(X)) if not callable(getattr(asyncio, "to_thread", None)) else None` — condition is always False in Python 3.9+, so no clustering runs; function returns `valid_memories, {}`. It's never called (only `_cluster_memories_async` is used). Fix: delete.

**[validation]**
The LLM content bug means every consolidation run has produced meaningless abstractions. Fix the CRITICAL (WORM bypass) and the MAJOR (LLM content) and the core functionality becomes correct. **Not production-ready**.

---

### 35. trimcp/salience.py

**[plan]**
1. `compute_decayed_score` handles all edge cases correctly. Very clean.
2. `reinforce` accepts negative `delta` without guard — silently decrements salience.

**[execution]**

**MINOR — `reinforce` accepts negative `delta` without validation**
- Location: line 112 — `delta: float = 0.05`, no guard before UPSERT
- The Flaw: A buggy caller can supply `delta=-1.0`. The INSERT path uses `LEAST(1.0, $4)` which allows negative values (inserts `-1.0`). The salience score floor of 0.0 is not enforced at the application layer.
- The Fix: `delta = max(0.0, float(delta))` at the start of `reinforce`.

**[validation]**
`salience.py` is the cleanest file in the codebase. Ebbinghaus formula is correct, overflow protection is solid, deterministic jitter is well-designed. **Production-ready** after fixing the negative-delta guard.

---

### 36. trimcp/temporal.py

**[plan]**
1. `as_of_query` hardcodes `$1` in returned clause — any caller that has existing parameters ends up binding `as_of` to the wrong position.
2. Redundant future-timestamp check duplicated in `as_of_query` (already enforced in `parse_as_of`).

**[execution]**

**MAJOR — `as_of_query` hardcodes `$1` instead of a dynamic parameter offset**
- Location: lines 97–100 — `"AND valid_from <= $1 AND (valid_to IS NULL OR valid_to > $1)"`, `params=[as_of]`
- The Flaw: The docstring example shows `full_params = [ns_id] + params`, making the `$1` in the clause bind to `ns_id` (a UUID) instead of `as_of` (a datetime). PostgreSQL raises a type error on the comparison, or in worst case silently applies incorrect temporal filtering.
- The Fix: Accept `param_offset: int = 0` and return `f"AND valid_from <= ${param_offset+1} AND (valid_to IS NULL OR valid_to > ${param_offset+1})"`.

**MINOR — Duplicate future-timestamp check in `as_of_query`**
- Location: lines 90–96 — exact duplicate of the check in `parse_as_of` (lines 37–42)
- Fix: Remove from `as_of_query`; trust callers to use `parse_as_of` first.

**[validation]**
`temporal.py` is 117 lines; the parameter-numbering bug makes `as_of_query` unusable for multi-parameter queries. Fix the MAJOR and it's solid. **Not production-ready** until `as_of_query` accepts a param offset.

---

### 37. trimcp/sanitize.py

**[plan]**
1. HTML entities not decoded before sanitization — `&lt;memory_content&gt;` passes through.
2. Defense layers (zero-width purge → tag strip → bracket neutralization) are correct.

**[execution]**

**MINOR — HTML entities not decoded before sanitization**
- Location: `sanitize_llm_payload`, line 35
- The Flaw: `&lt;memory_content&gt;` survives all three sanitization steps unchanged. If the LLM provider decodes HTML entities during preprocessing, the injected tag is reconstructed post-sanitization.
- The Fix: `import html; text = html.unescape(text)` as the first step, before zero-width purge.

**[validation]**
The three-layer defense is correct for the primary threat model. HTML entity gap is a defense-in-depth miss, not a critical bypass. **Production-ready** after adding entity decoding.

---

### 38. trimcp/net_safety.py

**[plan]**
1. `socket.getaddrinfo` is synchronous — blocks the asyncio event loop on every URL validation call from bridge handlers and webhook receivers.
2. `assert_url_allowed_prefix` silently swallows DNS failures — SSRF IP guard skipped if resolution throws.
3. Dead code in `validate_bridge_webhook_base_url`.

**[execution]**

**MAJOR — Synchronous `socket.getaddrinfo` blocks the asyncio event loop**
- Location: `_resolve_ips`, line 53 — `socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)`
- The Flaw: DNS resolution under network timeout (5–30s) is a blocking system call. When called from any async bridge handler or webhook validation, it freezes the entire asyncio event loop for that duration, blocking all concurrent tasks.
- The Fix: `infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None, type=socket.SOCK_STREAM)` — requires all callers to be async, which they already are.

**MINOR — `assert_url_allowed_prefix` silently skips IP check on DNS failure**
- Location: lines 160–163 — `except Exception as e: log.warning(...)`
- The Flaw: If DNS raises anything other than `BridgeURLValidationError`, the private-IP check is skipped. An attacker who controls DNS can force NXDOMAIN to bypass the IP guard while still passing the prefix check.
- The Fix: Raise `BridgeURLValidationError` on unexpected DNS failures rather than logging and continuing.

**MINOR — Dead code in `validate_bridge_webhook_base_url`**
- Location: lines 119–121 — `if parsed.scheme != "http" and parsed.scheme != "https": pass  # unreachable`
- Fix: Remove.

**[validation]**
`net_safety.py` has strong SSRF defense logic: explicit IPv6 denylist, provider prefix allowlists, multiple context-specific validators. The blocking DNS call is the only operational issue. Fix `_resolve_ips` to use `asyncio.to_thread` and this module is production-ready.

---

---

### 51. trimcp/contradictions.py

**[plan]**
1. `_check_kg_contradiction` issues one DB query per triplet, up to 3 candidates × N triplets per detection call — N+1 in the inner loop.
2. `_resolve_with_llm` makes a 10–30s LLM API call while holding the caller's live DB connection — pool starvation.
3. `contradictions` INSERT at line 459 is not inside the caller's transaction — orphaned contradiction records on saga rollback.

**[execution]**

**MAJOR — `_check_kg_contradiction` N+1 DB queries per triplet**
- Location: `_check_kg_contradiction`, lines 152–169 — `for t in triplets: conflict_edge = await conn.fetchrow(...)`
- The Flaw: For each of up to 3 candidates, this function issues one `fetchrow` per KG triplet on the new memory. A memory with 5 triplets produces 15 queries per `detect_contradictions` call. Under concurrency, this saturates the connection pool.
- The Fix: Rewrite as a single `fetchrow` with `WHERE (subject_label, predicate) = ANY($1::record[])` or batch into one IN clause across all triplets.

**MAJOR — LLM call while holding caller's DB connection**
- Location: `_resolve_with_llm`, line 250 — `llm_result = await provider.complete(messages, ContradictionResult)`
- The Flaw: `detect_contradictions` is called from within sagas that hold a `conn`. The same `conn` is threaded through `_detect_contradictions_impl` → `_resolve_with_llm`. The 10–30s LLM call runs while that connection is held in the pool, starving all other coroutines waiting for a connection.
- The Fix: Release the connection before the LLM call; re-acquire for the INSERT. Or use `detection_path="deferred"` for the LLM path.

**MINOR — `contradictions` INSERT not wrapped in caller's transaction**
- Location: `_detect_contradictions_impl`, line 459 — `await conn.execute("INSERT INTO contradictions ...")`
- The Flaw: `conn` is passed from the calling saga's context. The contradiction record is inserted directly without being part of the surrounding transaction. If the saga rolls back (e.g., `memories` INSERT fails), the `contradictions` row persists pointing to a non-existent memory.
- The Fix: Ensure this INSERT is inside `async with conn.transaction():` at the saga level, or use a compensating delete in the saga rollback path.

**MINOR — Unbounded `memory_text` in outbox payload**
- Location: `enqueue_contradiction_check`, lines 328–346 — `json.dumps({"memory_text": memory_text, "embedding": embedding, ...})`
- The Flaw: No size cap on `memory_text` before it's serialised into `outbox_events.payload`. A 1MB memory text creates a 1MB outbox row plus a 1MB embedding JSON array (~12KB per embedding). Large payloads cause outbox polling to slow as PostgreSQL fetches wider rows.
- The Fix: Truncate `memory_text` to a reasonable max (e.g. 10,000 chars) in the outbox payload; store only the `memory_id` and re-fetch text in the consumer.

**[validation]**
Contradiction detection is architected correctly — three-tier pipeline (embedding similarity → KG structural → NLI → LLM tiebreaker), graceful degradation, transactional outbox for deferred mode. The two MAJORs are operational correctness problems not design deficiencies. **Not production-ready** until N+1 and LLM-in-connection issues are fixed.

---

### 52. trimcp/graph_query.py

**[plan]**
1. `set_namespace_context` called outside transactions — systemic SET LOCAL no-op, RLS bypass on `memories` joins in time-travel paths.
2. BFS recursive CTE NOT EXISTS cycle guard references only the current working table (PostgreSQL CTE semantics), not the accumulated visited set — cyclic graphs can produce O(depth×nodes) traversal rows.
3. `pool.acquire()` without timeout at three call sites.

**[execution]**

**CRITICAL — `set_namespace_context` outside transaction, RLS bypass in time-travel joins**
- Location: `_find_anchor` line 211, `_bfs` line 335, `search` line 690-691 — `await set_namespace_context(c, UUID(str(namespace_id)))`
- The Flaw: None of these call sites are inside `async with conn.transaction()`. In asyncpg autocommit mode, `SET LOCAL app.current_namespace_id` reverts immediately after execution, before any subsequent query runs. Time-travel CTEs join through `memories` (which has RLS): `JOIN memories m ON n.memory_id = m.id` at lines 253 and 389. Without RLS active on the `memories` join, rows from other tenants can appear in the time-travel subgraph result.
- The Fix: Wrap each `_run_find_anchor` / `_run_bfs` / `search` connection usage in `async with conn.transaction():` before calling `set_namespace_context`.

**MAJOR — BFS recursive CTE cycle guard references current working table only**
- Location: `_bfs`, lines 480–495 and 394 — `NOT EXISTS (SELECT 1 FROM traversal AS seen WHERE seen.label IN (...))` and `(SELECT count(DISTINCT label) FROM traversal) < $6`
- The Flaw: In PostgreSQL's recursive CTE, the self-reference inside the recursive UNION term refers to the *working table* (the previous iteration's rows), not the accumulated result set. A cycle `A→B→C→A` generates tuples `(A,0), (B,1), (C,2)` then `(A,2)` — the UNION deduplication operates on full-tuple equality, so `(A,0)` and `(A,2)` are distinct and both appear. The NOT EXISTS guard only filters labels visible in the immediately preceding iteration. The MAX_NODES count check suffers the same defect. On a dense cyclic KG, the BFS explores O(max_depth × cycle_length) rows before the depth limit fires.
- The Fix: Use a separate `visited` array accumulated across CTE iterations, or post-process in Python by deduplicating on label after the CTE completes. The `visited = {r["label"] for r in labels}` set at line 496 correctly deduplicates — the issue is only excessive DB work before that point.

**MAJOR — `pool.acquire()` without timeout**
- Location: lines 290, 530, 687 — three `async with self.pg_pool.acquire() as c:` calls with no timeout
- The Flaw: Consistent with the codebase-wide pattern. Under pool exhaustion, graph traversal calls block indefinitely.
- The Fix: `async with asyncio.timeout(10.0): async with self.pg_pool.acquire() as c:`

**MINOR — Redundant triple `set_namespace_context` calls on same connection**
- Location: `search()` at line 690, then `_find_anchor._run_find_anchor` at line 211, then `_bfs._run_bfs` at line 335 — all called with the same `conn` for the same namespace
- The Flaw: Three identical `SET LOCAL` calls on one connection per search invocation. Harmless but signals that the contract (`conn` ownership vs. sub-function autonomy) is unresolved.
- The Fix: Once the transaction wrapper is added, a single `set_namespace_context` at the outermost scope is sufficient; remove the inner calls.

**[validation]**
`graph_query.py` is architecturally the cleanest file in the codebase — batched Mongo hydration, documented security contracts, `_allow_global_sweep` guard, time-travel signature verification, proper edge pagination, semaphore-bounded concurrency. The CRITICAL SET LOCAL bug is inherited from the codebase pattern. **Not production-ready** without the transaction wrapper.

---

### 53. trimcp/models.py

**[plan]**
1. Single-source-of-truth Pydantic V2 models — no DB/network code, pure domain types. Attack vector: `llm_credentials` field in `NamespaceConsolidationConfig` accepts raw literal API keys with no enforcement against literal storage.
2. No issues — deliberately import-only module.

**[execution]**

**MINOR — `llm_credentials` accepts raw API key strings in namespace metadata JSONB**
- Location: `NamespaceConsolidationConfig.llm_credentials: str | None = None` (line 291)
- The Flaw: The field accepts any string, including literal API keys. These are stored verbatim in the `namespaces.metadata` JSONB column. `providers/factory.py:_resolve_credential` logs a warning but does not prevent it. Any SQL dump, debug endpoint, or monitoring that reads namespace metadata exposes the key. The `ref:env/VAR_NAME` convention is advisory only.
- The Fix: Add a Pydantic `field_validator` that rejects values not starting with `ref:` — force the indirection pattern at the boundary.

**[validation]**
Clean, well-structured Pydantic contract file with thorough cross-field validation, frozen models for immutable replay config, and a built-in smoke-test `__main__` block. The literal credential field is the only gap. **Production-ready** after adding the `ref:` enforcement.

---

### 54. trimcp/observability.py

**[plan]**
1. Prometheus + OTel initialization with optional-dependency stubs — test for silent startup failures.
2. Private OTel API access (`_otel_context`) — breaks on OpenTelemetry SDK version bumps.

**[execution]**

**MINOR — Private `_otel_context` API in distributed trace propagation**
- Location: `extract_trace_from_headers` line 451, `OpenTelemetryTraceMiddleware.__call__` line 506 — `trace.get_tracer_provider()._otel_context.attach(ctx)`
- The Flaw: `_otel_context` is a private attribute of the OTel `TracerProvider`. It is not part of the stable public API and may be renamed, removed, or change behaviour on any OTel SDK upgrade. The correct public API is `context.attach(ctx)` from `opentelemetry.context`.
- The Fix:
  ```python
  from opentelemetry import context as otel_context
  token = otel_context.attach(ctx)
  # ... handler ...
  otel_context.detach(token)
  ```

**MINOR — Silent `except: pass` on Prometheus port bind failure**
- Location: `init_observability`, lines 207-210 — `except Exception: pass`
- The Flaw: If the Prometheus port is already bound by a different process (e.g., mis-configured Kubernetes pod with two instances), metrics silently fail. Operators have no signal that monitoring is not running.
- The Fix: `except Exception: log.warning("Prometheus HTTP server failed to start: %s", ...)` at minimum; raise if the failure is on a freshly-started instance.

**[validation]**
`observability.py` is a supporting layer — the two MINORs are operational gaps, not data correctness issues. **Production-ready** after fixing OTel context API usage.

---

### 55. trimcp/mcp_args.py

**[plan]**
1. Cache key construction uses MD5 — collision-prone for adversarial inputs.
2. `validate_nested_models` mutates the caller's `arguments` dict — potential aliasing hazard.

**[execution]**

**MINOR — MD5 for cache key hashing**
- Location: `build_cache_key`, line 202 — `args_hash = hashlib.md5(args_str.encode()).hexdigest()`
- The Flaw: MD5 produces 128-bit digests with known collision attacks. A crafted arguments dict could produce the same hash as a legitimate request, serving the wrong cached response to a different caller. This is low-probability in practice but violates the principle of using collision-resistant hashes for keyed lookups.
- The Fix: Replace with `hashlib.sha256(...).hexdigest()[:32]` (same key length, collision-resistant).

**[validation]**
`mcp_args.py` provides robust input validation with `SafeMetadataDict`, cache-key construction, and namespace-scoped cache purging via `SCAN`. **Production-ready** after MD5 replacement.

---

### 56. trimcp/graph_extractor.py

**[plan]**
1. `_spacy_extract` calls `spacy.load("en_core_web_sm")` on every invocation — no caching.
2. Regex fallback is coarse but safe for environments without spaCy.

**[execution]**

**MAJOR — spaCy model reloaded from disk on every `_spacy_extract` call**
- Location: `_spacy_extract`, line 45 — `nlp = spacy.load("en_core_web_sm")`
- The Flaw: `spacy.load` reads the model directory from disk (~15MB), deserializes components, and allocates memory on every call. Under any real write throughput, this adds 200–500ms per memory store and creates memory pressure. The fix is one line.
- The Fix:
  ```python
  @lru_cache(maxsize=1)
  def _get_spacy_nlp():
      return spacy.load("en_core_web_sm")
  
  # in _spacy_extract:
  nlp = _get_spacy_nlp()
  ```

**[validation]**
Correct extraction logic with a proper regex fallback and safe deduplication. The spaCy reload is a pure performance bug with a trivial fix. **Not production-ready** under real write load.

---

### 57. trimcp/notifications.py

**[plan]**
1. Placeholder email addresses in production code.
2. SMTP on unencrypted port 25.

**[execution]**

**MINOR — Hardcoded placeholder `From` and `To` email addresses**
- Location: `_send_email`, lines 86-87 — `msg["From"] = "trimcp-alerts@example.com"`, `msg["To"] = "admin@example.com"`
- The Flaw: `example.com` addresses are RFC-reserved non-deliverable placeholders. Alerts sent to these never reach any operator. This is placeholder code shipped as production logic.
- The Fix: Read from config: `cfg.TRIMCP_ALERT_FROM_EMAIL`, `cfg.TRIMCP_ALERT_TO_EMAIL` with mandatory validation that they are set before use.

**MINOR — SMTP on plaintext port 25**
- Location: `_send_email`, line 87 — `await aiosmtplib.send(msg, hostname=self.smtp_host, port=25, timeout=5)`
- The Flaw: Port 25 is unauthenticated SMTP relay. Alert emails (which may contain memory or tenant metadata in the message body) are sent unencrypted. Corporate mail servers typically block port 25 from internal hosts.
- The Fix: Default to port 587 (STARTTLS) with authentication credentials.

**[validation]**
`notifications.py` is a skeleton dispatcher — the supervised queue worker pattern and `asyncio.gather` with `return_exceptions=True` are correct. Both MINORs prevent the module from functioning in production. **Not production-ready**.

---

### 58. trimcp/ast_parser.py

**[plan]**
1. `_walk(node)` recursive function with no depth guard — unbounded recursion on adversarial AST.

**[execution]**

**MINOR — Unbounded recursion in `_walk` for deeply nested AST trees**
- Location: `_try_treesitter_parse`, `_walk` at line 102 — `for child in node.children: _walk(child)`
- The Flaw: Python's default recursion limit is 1000 frames. Auto-generated code (e.g. deeply nested closures, machine-produced expressions) can exceed this. `RecursionError` propagates as an uncaught exception out of `_try_treesitter_parse`, which returns `None` — the caller falls back to whole-file chunking. This is benign but silent.
- The Fix: Either add `sys.setrecursionlimit` or convert `_walk` to an explicit stack loop:
  ```python
  stack = [tree.root_node]
  while stack:
      node = stack.pop()
      # ... extract if target type ...
      stack.extend(node.children)
  ```

**[validation]**
Clean parser with graceful fallback. The recursion issue is benign in practice but easy to fix. **Production-ready** for normal code; fix before indexing user-supplied source files.

---

### 59. trimcp/re_embedder.py

**[plan]**
1. `start_re_embedder` calls `asyncio.create_task` fire-and-forget — no stored reference.
2. `pool.acquire()` without timeout — codebase-wide pattern.
3. Memories query has no namespace filter — scans all tenants' data.

**[execution]**

**MAJOR — `asyncio.create_task` fire-and-forget in `start_re_embedder`**
- Location: `start_re_embedder`, line 264 — `asyncio.create_task(run_re_embedding_worker(pg_pool, mongo_client))`
- The Flaw: No stored reference to the task. On exception inside `run_re_embedding_worker`, the error is silently discarded. The task reference is GC'd immediately (Python asyncio GC behaviour: unreferenced tasks can be garbage-collected mid-execution). The re-embedding worker may stop without any log entry. This is the same pattern found in admin_server.py, temporal.py, replay_mcp_handlers.py.
- The Fix: Store the reference and attach a done-callback: `task = asyncio.create_task(...); task.add_done_callback(lambda t: t.exception() and log.exception(...))`

**MAJOR — `pool.acquire()` without timeout**
- Location: `run_re_embedding_worker`, line 83 — `async with pg_pool.acquire() as conn:`
- The Flaw: Consistent with codebase-wide pattern.
- The Fix: `async with asyncio.timeout(10.0): async with pg_pool.acquire() as conn:`

**MINOR — Memories query scans all tenants without namespace filtering**
- Location: `run_re_embedding_worker`, line 106–119 — `SELECT id, payload_ref FROM memories WHERE id > $1 ORDER BY id ASC LIMIT 100`
- The Flaw: The migration worker processes memories from all namespaces (all tenants) without partition awareness. A large tenant's memories can starve the migration of all other tenants for hours. On multi-tenant deployments, fair migration requires per-namespace keyset cursors or explicit namespace round-robin.
- The Fix: Accept a `namespace_id` parameter and add `AND namespace_id = $3` to the query, iterating over namespaces via a `DISTINCT namespace_id` query first.

**[validation]**
The batch VRAM memory management (`_release_embedding_batch_memory`) and bulk MongoDB `$in` lookup are well-designed. The three flaws above are operational correctness issues. **Not production-ready** in multi-tenant deployments.

---

### 60. trimcp/providers/base.py

**[plan]**
1. `DEFAULT_CIRCUIT_BREAKER` and `DEFAULT_RETRY_POLICY` are module-level singletons shared across all provider instances.
2. `validate_base_url` does synchronous DNS at `__init__` time.

**[execution]**

**MAJOR — Shared singleton `DEFAULT_CIRCUIT_BREAKER` across all provider instances**
- Location: line 516 — `DEFAULT_CIRCUIT_BREAKER = CircuitBreaker()` used as fallback in `_circuit_breaker` property at lines 575-580
- The Flaw: All `LLMProvider` subclasses that do not override `_circuit_breaker` share a single `CircuitBreaker` instance. When `AnthropicProvider` accumulates 5 failures and the breaker opens, the same breaker state is read by `GoogleGeminiProvider`, `OpenAICompatProvider`, etc. — every provider fails fast even though only one is degraded. This defeats the breaker's purpose: protecting one endpoint from cascading to others.
- The Fix: Each `LLMProvider` subclass `__init__` should create a private breaker: `self._circuit_breaker = CircuitBreaker(...)`. The `DEFAULT_CIRCUIT_BREAKER` fallback should be removed.

**[validation]**
`providers/base.py` has an excellent design: retry policy with full jitter, state-machine circuit breaker, API-key redaction, typed `Message` model, full exception hierarchy. The singleton breaker is the only design flaw. **Production-ready** after per-instance circuit breakers.

---

### 61. trimcp/providers/factory.py

**[plan]**
1. `get_provider()` creates a new provider instance on every call — no caching or reuse.

**[execution]**

**MAJOR — `get_provider()` creates a new provider instance (new httpx client, SSRF DNS lookup) on every call**
- Location: `get_provider`, line 50 — returns `_build_provider(...)` which calls e.g. `AnthropicProvider(...)` → `validate_base_url(base_url)` → `socket.getaddrinfo` every time
- The Flaw: `get_provider()` is called per-request in the consolidation and contradiction detection paths (inside the hot write path for every `store_memory` call that triggers LLM checks). Each call: (1) creates a new `httpx.AsyncClient`-backed provider, (2) performs a synchronous DNS resolution via `validate_base_url`, (3) initialises a new circuit breaker, resetting failure state. Provider failures that should trip the circuit breaker are invisible because the breaker is re-created on the next call.
- The Fix: Cache provider instances by `(provider_label, model, cred_ref)` key using a module-level LRU dict or `functools.lru_cache`. Re-create only when credentials change (use credential hash as cache key, never log the credential itself).

**[validation]**
`factory.py` cleanly separates deferred factory functions per provider label. The missing cache is the only issue. **Not production-ready** for high-throughput consolidation paths.

---

### 62–66. trimcp/providers/{anthropic_provider,openai_compat,google_gemini,local_cognitive} + trimcp/providers/_http_utils.py

**[plan]**
Five implementation and utility files for LLM HTTP calls.

**[execution]**
No significant findings:
- All four provider implementations call `validate_base_url` in `__init__` (acceptable one-time cost).
- All use `post_with_error_handling` via `SafeAsyncClient` which correctly offloads DNS to `asyncio.to_thread` (see `trimcp/_http_utils.py:_check_url_host`).
- All validate response JSON against the Pydantic `response_model` before returning.
- `local_cognitive.py` uses `allow_http=True, allow_loopback=True` for the local endpoint — appropriately gated.
- `_http_utils.py` correctly uses `run_in_executor` for blocking DNS checks.

**[validation]**
All five files **production-ready** as-is.

---

### 67. trimcp/extractors/dispatch.py

**[plan]**
1. `ensure_registered()` uses a module-level `_initialized` flag with no lock — concurrent startup can double-register.
2. JSON magic-byte heuristic is fragile — any binary file starting with `{"` would be misidentified.

**[execution]**

**MINOR — `ensure_registered()` has a non-atomic init check**
- Location: lines 159-219 — `global _initialized; if _initialized: return; ... _initialized = True`
- The Flaw: In concurrent startup (multiple asyncio tasks calling `extract_bytes` simultaneously before initialization), two tasks can both pass the `if _initialized: return` check and both execute the registration block. The result is double-registration — the same extension is registered twice with the same handler (benign but wasteful and signals a concurrency discipline gap).
- The Fix: Use `asyncio.Lock` or the `threading.Lock`-based `_initialized` idiom: acquire a module-level lock before the check-and-set.

**MINOR — JSON magic-byte detection can misidentify binary files**
- Location: `_MAGIC_BYTES`, line 85-86 — `(b'{\"', "application/json"), (b'[\n', "application/json")`
- The Flaw: Any binary file whose first two bytes happen to be `{"` will be reported as `application/json`. This could mismatch with a non-JSON extension (e.g., a `.bin` starting with `{"`) triggering MIME mismatch rejection. The practical impact is low because the registry check happens after MIME resolution, but a `.bin` file starting with `{"` could produce an unexpected `mime_mismatch` log.
- The Fix: Use a minimum length check (require `{` followed by `"`) or extend the magic signature to require valid JSON structure.

**[validation]**
`dispatch.py` has excellent security layers: size limit check, encryption detection before dispatch, magic-byte MIME mismatch guard with Prometheus counters. Both MINORs are edge cases. **Production-ready** for normal use.

---

### 68. trimcp/openvino_npu_export.py

**[plan]**
1. One-shot admin tool — no network calls, no DB. `trust_remote_code=True` in tokenizer loading.

**[execution]**

**MINOR — `trust_remote_code=True` in tokenizer `from_pretrained`**
- Location: line 99 — `AutoTokenizer.from_pretrained(..., trust_remote_code=True)`
- The Flaw: `trust_remote_code=True` allows the Hugging Face model to execute arbitrary Python code from the model's `tokenizer_config.json`. On an air-gapped or offline install (`local_files_only=True`) this is acceptable. On a connected install, if the model is pulled from the Hub, a compromised model upload could execute arbitrary code in the context of the export script.
- The Fix: Add a comment making the risk explicit; add `if not local_files_only: log.warning("trust_remote_code=True with hub access — review model provenance")`. For production deployments, pin the model revision hash.

**[validation]**
Clean one-shot export script. The `trust_remote_code` flag is appropriate context here. **Production-ready** with the added warning.

---

### 69. trimcp/{assertion,snapshot_serializer,reembedding_migration,mcp_errors,_http_utils}.py

**[plan]**
Five utility/pure-Python files with no DB/network code.

**[execution]**
No findings:
- `assertion.py` — 31-line rule-based classifier. Clean.
- `snapshot_serializer.py` — Pure serialization layer; stateless, no I/O. Clean.
- `reembedding_migration.py` — Pure algorithm helpers (cosine similarity, Jaccard, in-memory store for tests). Clean.
- `mcp_errors.py` — JSON-RPC error mapping with `@mcp_handler` decorator. Correctly re-raises typed errors. Clean.
- `_http_utils.py` — `SafeAsyncClient` with DNS SSRF check correctly offloaded to `run_in_executor`. Clean.

**[validation]**
All five files **production-ready** as-is.

---

### 70. trimcp/extractors/{format-specific parsers} (11 files)

**[plan]**
Batch audit of: `pdf_ext.py`, `office_word.py`, `office_excel.py`, `office_pptx.py`, `email_ext.py`, `diagrams.py`, `diagram_api.py`, `ocr.py`, `chunking.py`, `libreoffice.py`, `adobe_ext.py`, `cad_ext.py`, `plaintext.py`, `project_ext.py` (14 files — all format-specific extraction).

**[execution]**
No significant findings at architecture level:
- All blocking I/O (pytesseract, LibreOffice, olefile, openpyxl, pptx) is correctly wrapped in `asyncio.to_thread`.
- `email_ext.py` correctly uses `tempfile.mkstemp` + cleanup for `.msg` parsing; no temp-file leaks on happy path.
- `diagram_api.py` validates `base_url` via `validate_extractor_url` before any outbound HTTP call.
- `ocr.py` correctly discards low-confidence OCR results (<30%) to avoid garbage text in the index.
- `chunking.py` enforces section-atomic chunking — no cross-section splicing.
- `dispatch.py` size limit and encryption pre-checks apply before format-specific parsers are called.
- No XML external entity (XXE) exposure found: `openpyxl` and `python-docx` use defusedxml or ETCompatHTMLParser.
- No path traversal: all parsers accept `bytes` blobs, not file paths from user input.

**[validation]**
All 14 format-specific extractor files are **production-ready** at architecture level. Individual library vulnerabilities (openpyxl, pdfminer, etc.) should be tracked via dependency scanning (Dependabot / pip-audit).

---

### 71. trimcp/schema.sql

**[plan]** PostgreSQL schema — tables, indexes, RLS policies, WORM triggers, partition managers. 890 lines loaded on every startup. Attack vectors: (1) RLS policy creation block ordering — tables referenced before creation → entire policy block fails → zero isolation; (2) tables with tenant data but no RLS enabled; (3) data migration conflict target mismatch on kg_edges.

**[execution]**

**[CRITICAL] RLS policy DO block creates policies for non-existent tables and missing columns — no policies ever created**
- Location: lines 776–793 — single `DO $$ BEGIN IF NOT EXISTS ... END $$` block creates ALL `namespace_isolation_policy` entries
- The Flaw: Line 787 references `memory_embeddings.namespace_id` — a column that does not exist in the `memory_embeddings` table definition (lines 389–401, columns: `memory_id, model_id, embedding, created_at`). Lines 790–791 reference `outbox_events` and `saga_execution_log` which are defined at lines 829 and 863 respectively — **after** this policy block. When the `DO` block is executed on a fresh install, it hits either the missing column on line 787 or the non-existent tables on lines 790–791 and throws `ERROR: column "namespace_id" of relation "memory_embeddings" does not exist` / `ERROR: relation "outbox_events" does not exist`. The entire PL/pgSQL block rolls back. **Zero policies are created.** On the next startup, the guard `IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'namespace_isolation_policy')` passes again (no policies exist) and the block fails again. RLS is ENABLED on all tables but no matching policies exist. The `trimcp_app` role sees 0 rows from every RLS-protected table. The application is completely non-functional as a non-superuser.
- The Fix: Split the policy creation into per-table DO blocks. Move `outbox_events` and `saga_execution_log` policy creation to after those tables are defined. Add `namespace_id UUID` to `memory_embeddings` and `kg_node_embeddings`, or exclude them from namespace-scoped isolation and document why.
  ```sql
  -- After CREATE TABLE outbox_events ...:
  DO $$
  BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='outbox_events' AND policyname='namespace_isolation_policy') THEN
          EXECUTE 'CREATE POLICY namespace_isolation_policy ON outbox_events FOR ALL USING (namespace_id = current_setting(''trimcp.namespace_id'', true)::uuid)';
      END IF;
  END $$;
  ```

**Schema clarification: SET LOCAL bypass causes starvation, not leakage**
- The Python audit found `SET LOCAL` outside transactions in 10 files (autocommit mode). The schema shows RLS policies use `current_setting('trimcp.namespace_id', true)` with `missing_ok=true`. When the session var is unset, PostgreSQL returns NULL; `namespace_id = NULL` evaluates to false. The RLS policy blocks ALL rows for that connection — no cross-tenant data exposure, but the correct tenant also sees zero rows. The operational impact of the SET LOCAL bug is **tenant data starvation** (silently empty results) not **tenant data leakage**. This changes remediation priority: the bug is still CRITICAL but does not require emergency security patching under a data-breach framework — it requires bug-fix patching under an availability framework.

**[MAJOR] Four tenant-data tables have no RLS enabled**
- `bridge_subscriptions` (lines 429–442): Contains `user_id`, `oauth_access_token_enc BYTEA`, `subscription_id`, `cursor`. No `ALTER TABLE bridge_subscriptions ENABLE ROW LEVEL SECURITY`. Cross-tenant visibility of OAuth tokens and subscription cursors.
- `consolidation_runs` (lines 474–507): Contains `namespace_id`, LLM provider/model identity, token counts, cluster details. No RLS. Consolidation history visible cross-tenant.
- `embedding_migrations` (lines 418–426): Migration state (target model, status, progress) visible cross-tenant.
- `dead_letter_queue` (lines 798–823): `kwargs JSONB NOT NULL` stores frozen invocation parameters that likely include `namespace_id`, `memory_id`, `agent_id`. No RLS.
- The Fix: Add `ENABLE ROW LEVEL SECURITY` + per-table isolation policies for all four. `dead_letter_queue` needs a `namespace_id` column added first.

**[MAJOR] `kg_edges_old` migration uses wrong conflict target**
- Location: lines 268–277 — `INSERT INTO kg_edges ... ON CONFLICT (subject_label, predicate, object_label) DO NOTHING`
- The Flaw: By the time this migration block runs, the 3-column unique constraint `(subject_label, predicate, object_label)` has been dropped (line 311) and replaced with the 4-column `(subject_label, predicate, object_label, namespace_id)` (line 317). `ON CONFLICT (subject_label, predicate, object_label)` references a non-existent constraint → `ERROR: there is no unique or exclusion constraint matching the ON CONFLICT specification`.
- The Fix: Change to `ON CONFLICT (subject_label, predicate, object_label, namespace_id) DO NOTHING`.

**[MINOR] `pii_redactions` has no index on `namespace_id`**
- The table is partitioned by RANGE(created_at), but the RLS policy and application queries filter by `namespace_id`. Without a `namespace_id` index, each RLS-filtered query scans all partitions. Given PII sensitivity, this query pattern is frequent and latency-critical.
- The Fix: `CREATE INDEX IF NOT EXISTS idx_pii_redactions_ns ON pii_redactions (namespace_id);`

**[MINOR] `kg_node_embeddings` has RLS enabled but no matching policy**
- Line 772 `ALTER TABLE kg_node_embeddings ENABLE ROW LEVEL SECURITY` — but the policy block never creates a policy for this table (it creates `memory_embeddings` on line 787, but `kg_node_embeddings` is absent). RLS enabled with no policy = all rows hidden from `trimcp_app`. KG node vector search broken for non-superusers. Same root cause as the main CRITICAL: this table needs `namespace_id` added or a matching policy.

**[MINOR] WORM trigger `trg_event_log_worm` created on partitioned table parent**
- Line 650: `CREATE TRIGGER trg_event_log_worm BEFORE UPDATE OR DELETE ON event_log`. Row-level trigger on a partitioned table parent is only propagated to partitions since PostgreSQL 13. Any deployment on PostgreSQL 12 or lower (which the Terraform doesn't pin against) silently has no WORM protection on individual partitions.
- The Fix: Add `COMMENT` or `CHECK` asserting PostgreSQL ≥ 13. Add to `validate()` in config.py.

**[MINOR] Dead `trg_event_log_parent_fk()` function left after trigger removal**
- Lines 583–605: The function body scans all `event_log` partitions by `id` without `occurred_at` (full partition scan). The DO block at lines 641–643 correctly drops the trigger citing "Full Table Scan DoS". But the function definition remains. It is unreachable dead code at the DB level but adds cognitive noise for schema readers.
- The Fix: `DROP FUNCTION IF EXISTS trg_event_log_parent_fk();` after dropping the trigger.

**[validation]**
The schema's RLS policy creation is fundamentally broken on fresh installations. The DO block that should create all tenant isolation policies fails silently every startup. Combined with four unprotected tenant tables, the multi-tenant isolation guarantee cannot be made even if the Python-layer SET LOCAL bug were fixed. **Not production-ready.** The WORM trigger and HNSW indexing are well-structured; the migration scaffolding (pg_policies idempotency guards, ON CONFLICT for backfills) shows good intent but has critical execution gaps.

---

### 72. trimcp/migrations/001_enable_rls.sql + 003_quota_check.sql

**[plan]** Two post-schema migrations: 001 adds the `trimcp_app` role, creates isolation policies, and enables FORCE RLS. 003 adds a quota lower-bound CHECK constraint. Attack vectors for 001: (1) same missing-column bug on `memory_embeddings`/`kg_node_embeddings` in policy FOREACH loop; (2) `ALTER ROLE postgres SET row_security = off` — intentional RLS bypass for superuser.

**[execution]**

**[CRITICAL] `001_enable_rls.sql` policy FOREACH loop fails on `memory_embeddings` and `kg_node_embeddings`**
- Location: lines 29–68 — `FOREACH t IN ARRAY ['memories', ..., 'memory_embeddings', 'kg_node_embeddings', ...]` → `CREATE POLICY tenant_isolation_policy ON %I ... USING (namespace_id = get_trimcp_namespace())`
- The Flaw: Both `memory_embeddings` and `kg_node_embeddings` have no `namespace_id` column. When the loop reaches either table, `CREATE POLICY ... USING (namespace_id = ...)` raises `ERROR: column "namespace_id" does not exist`. The entire DO block fails and rolls back. `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and `GRANT ALL ON TABLE` for **all tables** in the array are rolled back. No tenant isolation is established by this migration.
- The Fix: Remove `memory_embeddings` and `kg_node_embeddings` from the array until `namespace_id` is added to both tables. OR add `namespace_id UUID REFERENCES namespaces(id)` to both tables first, then include them.

**[MAJOR] `ALTER ROLE postgres SET row_security = off` disables all RLS for the superuser role**
- Location: line 114
- The Flaw: This statement sets the default `row_security` GUC for the `postgres` role to `off`. Any application process running as `postgres` (common in development, docker-compose, and single-node deployments) bypasses all RLS policies. Every query from such a process sees all tenant rows. The comment says "Ensure admin roles (like 'postgres') bypass RLS for system tasks (GC, etc.)" — but the GC, cron workers, and memory orchestrator all use the same `postgres` role in default deployments. This makes RLS bypass the default operational mode for all background workers, not just admin tasks.
- The Fix: Create a dedicated `trimcp_gc` role with BYPASSRLS for administrative system tasks only. Do not bypass RLS for the application DB user or `postgres` globally. Explicitly grant BYPASSRLS only to the roles that legitimately need it and only in the specific DB where it's needed.

**`003_quota_check.sql`:**
Clean. Idempotent constraint addition with pre-flight negative-value scan and quality gate. **Production-ready.**

**[validation]**
Migration 001 fails to establish RLS isolation due to the same missing-column bug as schema.sql. The postgres role bypass makes tenant isolation opt-in (requires explicitly using `trimcp_app`) rather than default. Together, default deployments have no effective tenant isolation at the database layer. **Not production-ready.**

---

### 73. deploy/multiuser/Dockerfile

**[plan]** Multi-stage build: compile wheels in builder, install from offline wheels in runtime. Attack vectors: (1) spaCy model download during build — network dependency, no version pin; (2) check non-root user, HEALTHCHECK, pinned base image.

**[execution]**

**[MINOR] spaCy model downloaded during image build without pinned version**
- Location: line 31 — `python -m spacy download en_core_web_sm`
- The Flaw: `spacy download en_core_web_sm` fetches the latest compatible version from the spaCy releases CDN at build time. Two builds on the same machine with the same Dockerfile can produce different model binaries if a patch is released between them. Build determinism is broken. In regulated environments, downloading from the internet during image build is also a supply-chain risk.
- The Fix: Pin the model version: `pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl` with a SHA-256 hash check.

Otherwise: non-root UID (10001), multi-stage build, pinned base image (`python:3.12-slim-bookworm`), HEALTHCHECK with appropriate start period, `--no-cache-dir` on pip. **Production-ready** with the pin fix.

**[validation]**
Clean image build. The spaCy model download is the only actionable finding. **Production-ready** with the version pin.

---

### 74. trimcp-infra/aws (Terraform)

**[plan]** AWS IaC: VPC/subnets, RDS PostgreSQL, DocumentDB, ElastiCache Redis, S3, ECS Fargate (worker + orchestrator), API Gateway webhook, monitoring, Secrets Manager. Attack vectors: (1) ECS task container commands; (2) deployment rolling policy; (3) ElastiCache apply_immediately; (4) IAM least privilege.

**[execution]**

**[MAJOR] Both ECS task definitions use `command: ["tail", "-f", "/dev/null"]` — application code never runs**
- Location: `modules/fargate-worker/main.tf` lines 177 and 205
- The Flaw: Both the orchestrator and worker container definitions override the Dockerfile CMD with `["tail", "-f", "/dev/null"]`. ECS `command` takes precedence over the Docker image `CMD`. In production, both deployed services start successfully (containers are "running") but execute no application code — no memories stored, no RQ workers processing tasks, no orchestration. There is no `execute_command_configuration` on the ECS cluster to indicate this is an ECS Exec pattern. The containers are functionally inert.
- The Fix: Set correct commands:
  ```hcl
  command = ["python", "server.py"]      # orchestrator
  command = ["python", "start_worker.py"] # worker
  ```
  If ECS Exec shell access is intentional, add `enable_execute_command = true` on the ECS service and document the pattern.

**[MINOR] `deployment_minimum_healthy_percent = 0` on both ECS services**
- Location: `modules/fargate-worker/main.tf` lines 236 and 253
- The Flaw: A `minimum_healthy_percent` of 0 allows ECS to terminate all running tasks before starting replacement tasks. Every deployment causes a downtime window equal to task startup time (~90s per HEALTHCHECK start_period). For a production MCP server processing live LLM tool calls, this is unacceptable.
- The Fix: Set `deployment_minimum_healthy_percent = 100` and `deployment_maximum_percent = 200` for zero-downtime rolling deployments.

**[MINOR] `apply_immediately = true` on ElastiCache**
- Location: `modules/elasticache/main.tf` line 67
- The Flaw: `apply_immediately = true` means any Terraform configuration change to ElastiCache (parameter group changes, node type, etc.) applies immediately rather than during the next maintenance window. Cache parameter changes that cause a flush or restart will hit production traffic during business hours when applied by CI/CD. This applies unconditionally regardless of environment.
- The Fix: `apply_immediately = var.environment != "prod"`.

**[MINOR] No auto-scaling configured for ECS services**
- Location: `modules/fargate-worker/main.tf` — `desired_count` is a fixed variable
- The Flaw: Worker and orchestrator counts are set via `worker_desired_count` and `desired_count` variables with no `aws_appautoscaling_*` resources. Under load spikes (batch re-embedding, large consolidation runs), fixed-size worker pools exhaust quickly. The result is queue backlog with no automatic relief.
- The Fix: Add `aws_appautoscaling_target` and `aws_appautoscaling_policy` keyed on SQS queue depth or ECS CPU utilization.

Positive findings — RDS: `storage_encrypted=true`, KMS-backed, `publicly_accessible=false`, deletion protection on prod, `skip_final_snapshot` only off-prod. ElastiCache: `at_rest_encryption_enabled=true`, `transit_encryption_enabled=true`, `auth_token` set. S3: all four public-access blocks enabled, KMS SSE, versioning enabled. IAM: orchestrator/worker have separate roles; worker has no Secrets Manager access (correct).

**[validation]**
The `tail -f /dev/null` placeholder in both production task definitions means deployed services process nothing. The infrastructure security posture (encryption, network isolation, secrets management) is otherwise strong. **Not production-ready** until task commands are corrected.

---

## Recommendations

### Immediate (Blocking Production):
1. Fix `schema.sql` + `001_enable_rls.sql` RLS policy DO block — split into per-table blocks, move outbox/saga policies after table definitions, add `namespace_id` to `memory_embeddings` and `kg_node_embeddings`. **Without this, no RLS policies exist on any table.**
2. Fix ECS Fargate task definitions — replace `["tail", "-f", "/dev/null"]` with real application commands. **Without this, deployed services are inert.**
3. Fix `db_utils.py:pool.acquire()` timeout across all files (highest leverage, affects every file).
4. Fix `SET LOCAL` outside transaction pattern (10 files — causes tenant data starvation, not leakage).
5. Fix `append_event` transaction wrapping (breaks WORM).
6. Remove hardcoded MinIO secret from `config.py`.
7. Fix quota/cache ordering in `server.py` (billing issue).
8. Fix `store_media` LFI vulnerability in `server.py`.
9. Fix distributed lock fail-open in `cron_lock.py` and `garbage_collector.py`.
10. Add RLS to `bridge_subscriptions`, `consolidation_runs`, `embedding_migrations`, `dead_letter_queue` (cross-tenant data exposure).
11. Revoke `ALTER ROLE postgres SET row_security = off` in migration 001 — replace with a scoped `trimcp_gc` role with BYPASSRLS only where needed.

### Before Production (High Priority):
1. Fix N+1 MongoDB patterns (5+ locations).
2. Fix event-loop blocking in `signing.py` (300ms freeze on cache miss).
3. Fix RLS bypass in `memory.py:unredact_memory` (raw pool acquire).
4. Fix WORM deletion in `namespace.py:delete`.
5. Fix OFFSET pagination false orphans in `garbage_collector.py`.
6. Implement read-replica routing in `orchestrator.py`.
7. Fix concurrent lazy-init races in `orchestrator.py`.
8. Fix `graph_extractor.py` spaCy model reload — add `@lru_cache(maxsize=1)` on `_get_spacy_nlp()` helper (15MB disk load on every KG extraction call).
9. Fix `providers/base.py` shared singleton circuit breaker — `DEFAULT_CIRCUIT_BREAKER` is module-level; one provider's 5 failures open the breaker for all providers. Each `__init__` must create its own `CircuitBreaker()` instance.
10. Fix `providers/factory.py` — `get_provider()` creates a new httpx client and runs SSRF DNS validation on every LLM call; add `@lru_cache` keyed on `(label, model_id, cred_ref)`.
11. Fix `contradictions.py:_check_kg_contradiction` N+1 — up to 3×N individual DB queries per check call; batch into `WHERE (subject, predicate, object) IN (...)` or use `ANY`.
12. Fix `contradictions.py:_resolve_with_llm` — 10–30s LLM API call made while caller's DB connection is held; release the connection before calling the LLM, re-acquire after.
13. Fix `graph_query.py` BFS cycle guard — `NOT EXISTS` subquery references only the PostgreSQL working table (previous iteration), not the accumulated visited set; cyclic KG nodes produce unbounded traversal rows.

### Operational:
1. Add connection pool size validation in `config.py:validate()`.
2. Add production environment guards to all dev bypasses.
3. Implement comprehensive integration tests for concurrency scenarios.
4. Add observability (distributed tracing) to identify connection pool exhaustion early.
5. Cache `spacy.load` results globally or via process-level singleton to amortize the 15MB load.
6. Add `trust_remote_code=True` model-provenance warning + pin revision hash in `openvino_npu_export.py`.
7. Replace MD5 with SHA-256 for cache key hashing in `mcp_args.py`.
8. Add depth limit to `ast_parser.py:_walk()` to prevent `RecursionError` on deeply nested auto-generated code.
9. Fix placeholder email addresses and switch SMTP from port 25 to 587+TLS in `notifications.py`.

---

## Conclusion

The TriMCP codebase demonstrates mature architectural thinking — saga patterns, deterministic forked replay, causal provenance via WORM event logs, RLS-based multi-tenancy, and keyset-paginated background workers. The complete audit (Python codebase + schema + migrations + infrastructure) reveals **44 CRITICAL and 92 MAJOR flaws** that undermine every foundational guarantee.

**Six systemic patterns account for the majority of CRITICALs:**

1. **`SET LOCAL` outside transactions (CRITICAL × 10 files):** `set_namespace_context` is called in asyncpg autocommit mode across db_utils.py, memory.py, namespace.py, garbage_collector.py, graph_query.py, orchestrators/graph.py, orchestrators/cognitive.py, orchestrators/temporal.py, and two bridge files. `SET LOCAL` reverts immediately outside a transaction. Tenant isolation is disabled for the entire application.

2. **`require_master_key()` context manager misuse (CRITICAL × 3 files, 7 call sites):** Called as `mk = require_master_key()` without `async with`, returning a generator object instead of key bytes. All AES-256-GCM operations in pii.py, bridge_renewal.py, and bridge_repo.py crash with TypeError. No encrypted OAuth token can be written or read. Only env-var bridge tokens function.

3. **`pool.acquire()` without timeout (MAJOR × 45+ call sites in every file):** Connection exhaustion blocks the asyncio event loop indefinitely across the entire codebase.

4. **Fire-and-forget `asyncio.create_task` (MAJOR × 5 sites):** admin_server.py, temporal.py, replay_mcp_handlers.py create tasks without storing references. Exceptions are silently discarded; callers receive success for work that may never have run.

5. **N+1 MongoDB queries (MAJOR × 6+ sites):** Individual `find_one` per result row rather than batched `find({"_id": {"$in": [...]}})` in graph.py, consolidation.py, temporal.py.

6. **Schema RLS policy block ordering failure (CRITICAL × DB layer):** `schema.sql` and `001_enable_rls.sql` both fail to create any RLS policies because the policy DO block references tables (`outbox_events`, `saga_execution_log`) before they exist and references `memory_embeddings.namespace_id` which doesn't exist. RLS is ENABLED on all tables but no matching policies exist — the application running as `trimcp_app` sees 0 rows everywhere. Additionally, `ALTER ROLE postgres SET row_security = off` in migration 001 makes RLS a no-op for the default development role.

**Unique cross-cutting bugs:**
- `consolidation.py`: LLM receives MongoDB ObjectIds, not content — all consolidations produce meaningless abstractions (every prior consolidation run is invalid)
- `a2a.py:enforce_scope`: Namespace-wildcard bypass — any namespace grant allows access to any tenant's memories
- `reembedding_worker.py`: `FOR UPDATE SKIP LOCKED` lock released before UPDATE — duplicate re-embedding in multi-instance deployments
- `migration.py:start_migration`: TOCTOU race creates two concurrent active migrations
- `replay.py`: Pool exhaustion deadlock under concurrent replays; LLM calls inside REPEATABLE READ cursor transactions

**Recommendation:**
1. Fix `schema.sql` / `001_enable_rls.sql` policy DO block (without this no tenant isolation exists at DB level)
2. Fix ECS Fargate `command: ["tail", "-f", "/dev/null"]` (without this the deployed service processes nothing)
3. Fix all 10 `SET LOCAL` outside-transaction sites (tenant data starvation — all queries return zero rows)
4. Fix `require_master_key()` misuse (bridge OAuth lifecycle is entirely broken)
5. Disable A2A feature until `enforce_scope` namespace wildcard is corrected
6. Add `pool.acquire(timeout=10.0)` across all call sites
7. Fix `consolidation.py` to pass actual memory content to the LLM

**The codebase is not production-ready as of 2026-05-11.** Full audit complete: ~80 Python files + schema.sql + migrations + Dockerfile + Terraform.

---

**Audit completed by Claude Sonnet 4.6**  
**Final counts: 44 CRITICAL | 92 MAJOR | 81 MINOR | 3 NITPICK**
