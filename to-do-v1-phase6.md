# to-do-v1-phase6.md
# TriMCP Phase 6 Remediation Task List
# Format: YAML blocks, one per task
# Machine-parseable. Fields: id|priority|severity|source|confirmed|dispatched|dispatched_by|file|line|category|title|fix
# Generated: 2026-05-11 | Last dispatch-status update: 2026-05-11
# Source audits: Phase6_Audit_Sonnet4-6.md (S) + Phase6_Audit_GeminiPro3.1.md (G)
# Dispatch sequences pushed: Seq-1, Seq-2A, Seq-2B, Seq-2C, Seq-3, Seq-4, Seq-5(WASTED), Seq-6A, Seq-6B, Seq-6C, Seq-7, Seq-8
# Supplemental sequences: Seq-9A READY; Seq-9B partial — FIX-025/026/029 done 2026-05-12, FIX-027 open; Seq-9C partial — FIX-032/041 done 2026-05-12, remainder open

## DISPATCH COVERAGE MAP

```yaml
dispatch_map:
  seq1:
    tool: "Gemini 3 Flash (Google Antigravity)"
    covers: [FIX-001, FIX-002, FIX-016, FIX-017]
    status: pushed

  seq2a:
    tool: "Composer 2 (Cursor)"
    covers: [FIX-010, FIX-011, FIX-012]
    status: pushed

  seq2b:
    tool: "Haiku 4.5 (VS Code)"
    covers: [FIX-003, FIX-043, FIX-044, FIX-045, FIX-056]
    status: pushed

  seq2c:
    tool: "Gemini 3.1 Pro (CLI)"
    covers: [FIX-014, FIX-015, FIX-018, FIX-019, FIX-035]
    status: pushed

  seq3:
    tool: "Composer 2 (Cursor)"
    covers: [FIX-021, FIX-024, FIX-028, FIX-033]
    status: pushed

  seq4:
    tool: "Haiku 4.5 (VS Code)"
    covers: [FIX-034]
    status: pushed

  seq5:
    tool: "Gemini 3.1 Pro (CLI)"
    covers: []
    status: WASTED
    warning: "All 4 targets (pickle, exec/eval, shell=True, JWT-alg) are DISMISSED findings. Agents will grep, find nothing, produce no output. Seq-5 was designed before grep verification."

  seq6a:
    tool: "Composer 2 (Cursor)"
    covers: []
    status: COLLISION_RISK
    warning: "Prompt targets P2 retry/timeout items. FIX-058 (retry jitter) is DISMISSED because base.py RetryPolicy already has full-jitter. Seq-6A may attempt to add retries ON TOP of the existing RetryPolicy — risk of double-wrapping tenacity decorators."

  seq6b:
    tool: "Composer 2 (Cursor)"
    covers: []
    status: vague
    note: "Scans todo for pydantic/validation P2s. No specific FIX items targeted. Low collision risk."

  seq6c:
    tool: "Haiku 4.5 (VS Code)"
    covers: [FIX-050, FIX-060]
    status: vague
    note: "Scans for dead code/TODO P2s. May catch FIX-050 (MD5) and FIX-060 (OTel private API) if agent reads todo carefully."

  seq7:
    tool: "Gemini 3 Flash"
    covers: []
    status: pushed
    note: "Testing and documentation — no code fixes. Depends on Seq 1-6 completing first."

  seq8:
    tool: "Gemini 3 Flash"
    covers: []
    status: pushed
    note: "Deployment runbook. No code fixes."

  seq9a:
    tool: "Composer 2 (Cursor) or Gemini 3.1 Pro"
    covers: [FIX-013, FIX-020]
    status: READY — not yet pushed
    note: "P0 CRITICALs missing from all prior sequences. FIX-013=hardcoded MinIO secret (config.py). FIX-020=quota double-billing (server.py). Safe to run in parallel — different files."

  seq9b:
    tool: "Composer 2 (Cursor)"
    covers: [FIX-025, FIX-026, FIX-027, FIX-029]
    status: partial — FIX-027 (GC OFFSET) remains
    note: "FIX-025/026/029 landed 2026-05-12. Pending: garbage_collector.py (FIX-027)."

  seq9c:
    tool: "Gemini 3.1 Pro (CLI) or Composer 2"
    covers: [FIX-030, FIX-031, FIX-032, FIX-038, FIX-039, FIX-040, FIX-041]
    status: partial — FIX-030/031/038/039/040 remain
    note: "FIX-032/041 landed 2026-05-12. Pending: graph_query, graph_extractor, schema.sql/admin guard, migration TOCTOU."

gaps_critical:
  - id: FIX-013
    priority: P0
    severity: CRITICAL
    title: "Hardcoded MinIO secret in config.py — NOT IN ANY SEQUENCE"
    action_needed: "Dispatch immediately — blocks production security"

  - id: FIX-020
    priority: P0
    severity: CRITICAL
    title: "Quota double-billing in server.py — NOT IN ANY SEQUENCE"
    action_needed: "Dispatch immediately — revenue and fairness integrity"

gaps_p1:
  - FIX-027  # GC OFFSET pagination creates false orphans
  - FIX-030  # BFS cycle guard unbounded traversal
  - FIX-031  # spacy.load() per extraction (15MB reload)
  - FIX-038  # kg_edges_old wrong ON CONFLICT target
  - FIX-039  # TRIMCP_ADMIN_OVERRIDE no production guard
  - FIX-040  # TOCTOU race in start_migration

gaps_p2:
  - FIX-051  # ast_parser recursion depth limit
  - FIX-052  # SMTP port 25 / placeholder emails
  - FIX-053  # trust_remote_code=True openvino
  - FIX-054  # pii_redactions missing namespace_id index
  - FIX-055  # kg_node_embeddings RLS enabled but no policy
  - FIX-057  # no ECS auto-scaling
```

---

## P0 — Blocking Production

```yaml
id: FIX-001
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-1
completed: 2026-05-12
file: trimcp/schema.sql
line: "776-793"
category: rls
title: "RLS policy DO block never creates any policies — zero tenant isolation"
fix: "Split single DO block into per-table IF-NOT-EXISTS blocks; move outbox_events and saga_execution_log policies to after their CREATE TABLE statements; add namespace_id UUID to memory_embeddings and kg_node_embeddings or exclude them from policy creation"
```

```yaml
id: FIX-002
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-1
completed: 2026-05-12
file: trimcp/migrations/001_enable_rls.sql
line: "29-68"
category: rls
title: "FOREACH policy loop fails on memory_embeddings and kg_node_embeddings — no policies created"
fix: "Remove memory_embeddings and kg_node_embeddings from the array until namespace_id column is added to both tables"
```

```yaml
id: FIX-003
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2B
completed: 2026-05-12
file: trimcp-infra/aws/modules/fargate-worker/main.tf
line: "177,205"
category: infra
title: "ECS task definitions use tail -f /dev/null — deployed services run no application code"
fix: "Replace command: [\"tail\",\"-f\",\"/dev/null\"] with [\"python\",\"server.py\"] for orchestrator and [\"python\",\"start_worker.py\"] for worker"
```

```yaml
id: FIX-004
priority: P0
severity: CRITICAL
source: gemini
confirmed: dismissed
result: "grep 'shell=True' libreoffice.py returned no matches; Sonnet PASS confirmed correct"
file: trimcp/extractors/libreoffice.py
line: "unknown"
category: injection
title: "shell=True in LibreOffice subprocess — command injection RCE (contradicts Sonnet PASS)"
fix: "N/A — finding dismissed"
```

```yaml
id: FIX-005
priority: P0
severity: CRITICAL
source: gemini
confirmed: dismissed
result: "decode_kwargs at line 283 explicitly sets algorithms=[algorithm]; issuer, audience, options also set; finding dismissed"
file: trimcp/jwt_auth.py
line: "283"
category: auth
title: "JWT decoded without explicit algorithms= parameter — algorithm confusion attack allows full auth bypass"
fix: "N/A — finding dismissed; algorithms already set"
```

```yaml
id: FIX-006
priority: P0
severity: CRITICAL
source: gemini
confirmed: dismissed
result: "grep 'import pickle|pickle.loads|pickle.dumps' trimcp/tasks.py returned no matches; finding dismissed"
file: trimcp/tasks.py
line: "unknown"
category: injection
title: "Pickle used for task queue serialization — RCE via attacker-controlled queue payload"
fix: "N/A — finding dismissed"
```

```yaml
id: FIX-007
priority: P0
severity: CRITICAL
source: gemini
confirmed: dismissed
result: "grep 'exec(|eval(' trimcp/code_mcp_handlers.py returned no matches; finding dismissed"
file: trimcp/code_mcp_handlers.py
line: "unknown"
category: injection
title: "Agent code execution via exec()/eval() — unconditional RCE"
fix: "N/A — finding dismissed"
```

```yaml
id: FIX-008
priority: P0
severity: CRITICAL
source: gemini
confirmed: dismissed
result: "All handlers use @require_scope('admin') + @mcp_handler; no DDL execution; handlers delegate to orchestrator.start_migration() (embedding migration, not schema DDL); finding dismissed"
file: trimcp/migration_mcp_handlers.py
line: "99-168"
category: auth
title: "DDL migrations triggerable by AI agents via MCP — agents can DROP TABLE or alter schema"
fix: "N/A — finding dismissed; handlers are admin-scoped orchestration, not DDL"
```

```yaml
id: FIX-009
priority: P0
severity: CRITICAL
source: gemini
confirmed: dismissed
result: "project_ext.py handles .mpp (MPXJ CLI sidecar) and .pub (LibreOffice convert) files; no zipfile/tarfile extraction present; finding dismissed"
file: trimcp/extractors/project_ext.py
line: "unknown"
category: injection
title: "Zip Slip path traversal in archive extraction — writes files outside extraction directory"
fix: "N/A — finding dismissed; no archive extraction in project_ext.py"
```

```yaml
id: FIX-010
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2A
completed: 2026-05-12
file: "trimcp/db_utils.py (and 44 other files)"
line: "all pool.acquire() calls"
category: resource
title: "pool.acquire() without timeout — connection exhaustion blocks event loop indefinitely"
fix: "Add timeout=10.0 to every asyncpg pool.acquire() call across the codebase; use asyncio.wait_for(pool.acquire(), timeout=10.0) as fallback pattern"
```

```yaml
id: FIX-011
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2A
completed: 2026-05-12
file: "trimcp/db_utils.py, memory.py, namespace.py, garbage_collector.py, graph_query.py, orchestrators/graph.py, orchestrators/cognitive.py, orchestrators/temporal.py, bridge files (10 total)"
line: "varies per file"
category: rls
title: "SET LOCAL called outside transactions — RLS session variable reverts immediately, data starvation for all tenant queries"
fix: "Wrap every call to set_namespace_context() inside conn.transaction() before calling; all SET LOCAL must occur within an explicit BEGIN/COMMIT block"
```

```yaml
id: FIX-012
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2A
completed: 2026-05-12
file: "trimcp/event_log.py, orchestrators/memory.py (6 sites total)"
line: "varies"
category: atomicity
title: "append_event() called outside database transactions — breaks WORM audit log chain guarantee"
fix: "All append_event() calls must be wrapped in conn.transaction(); the advisory-lock sequence guarantee requires transaction isolation"
```

```yaml
id: FIX-013
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W1-A
completed: 2026-05-12
file: trimcp/config.py
line: "MINIO_SECRET_KEY default"
category: auth
title: "Hardcoded default MinIO credential committed in repository"
fix: "Change default to empty string; add validation: if not self.MINIO_SECRET_KEY: raise ValueError('MINIO_SECRET_KEY must be set')"
```

```yaml
id: FIX-014
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2C
completed: 2026-05-12
file: server.py
line: "store_media handler"
category: injection
title: "LFI vulnerability in store_media — user-controlled path used as S3 key"
fix: "Sanitize path input; use os.path.basename() or UUID-based key; reject paths containing ../ or absolute paths"
```

```yaml
id: FIX-015
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2C
completed: 2026-05-12
file: "trimcp/cron_lock.py, trimcp/garbage_collector.py"
line: "varies"
category: concurrency
title: "Distributed lock fails open on Redis outage — concurrent singleton job execution"
fix: "On Redis lock acquisition failure, abort the job rather than proceeding; log and return; do not execute without the lock"
```

```yaml
id: FIX-016
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-1
completed: 2026-05-12
file: trimcp/schema.sql
line: "761-793"
category: rls
title: "Four tenant tables have no RLS enabled: bridge_subscriptions, consolidation_runs, embedding_migrations, dead_letter_queue"
fix: "Add ALTER TABLE x ENABLE ROW LEVEL SECURITY; and CREATE POLICY namespace_isolation_policy ON x FOR ALL USING (namespace_id = current_setting('trimcp.namespace_id',true)::uuid) for each table"
```

```yaml
id: FIX-017
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-1
completed: 2026-05-12
file: trimcp/migrations/001_enable_rls.sql
line: "114"
category: rls
title: "ALTER ROLE postgres SET row_security = off — disables all RLS for default superuser role"
fix: "Revoke: ALTER ROLE postgres RESET row_security; create dedicated trimcp_gc role with BYPASSRLS only for legitimate GC admin tasks"
```

```yaml
id: FIX-018
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2C
completed: 2026-05-12
file: trimcp/a2a.py
line: "enforce_scope function"
category: auth
title: "Namespace wildcard in A2A scope check — any namespace grant allows cross-tenant memory access"
fix: "Disable A2A feature or fix enforce_scope to strictly validate namespace_id equality without wildcard expansion; add integration test covering cross-namespace access"
```

```yaml
id: FIX-019
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2C
completed: 2026-05-12
file: "trimcp/pii.py, trimcp/bridge_renewal.py, trimcp/bridge_repo.py"
line: "require_master_key() call sites"
category: crypto
title: "require_master_key() used without async with — returns generator object instead of key bytes, AES-GCM crashes with TypeError"
fix: "Change mk = require_master_key() to async with require_master_key() as mk: at all 7 call sites; or refactor to async def that returns the key directly"
```

```yaml
id: FIX-020
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W1-B
completed: 2026-05-12
file: server.py
line: "quota check before cache hit"
category: data-integrity
title: "Quota consumed but not rolled back on cache hit — double-billing"
fix: "Check cache before incrementing quota; only increment quota on cache miss + successful LLM call"
```

## P1 — Before Production (High Priority)

```yaml
id: FIX-021
priority: P1
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-3
completed: 2026-05-12
file: trimcp/consolidation.py
line: "LLM call site"
category: data-integrity
title: "LLM receives MongoDB ObjectIds instead of content — all consolidation outputs are semantically meaningless"
fix: "Hydrate MongoDB documents before passing to LLM: results = await mongo.find({'_id': {'$in': ids}}); pass actual content to consolidation prompt; all prior consolidation runs are invalid data"
```

```yaml
id: FIX-022
priority: P1
severity: CRITICAL
source: gemini
confirmed: dismissed
result: "signing.py line 906 already uses hmac.compare_digest(computed, expected_signature); constant-time comparison correct; finding dismissed"
file: trimcp/signing.py
line: "906"
category: crypto
title: "HMAC digest compared with == (timing attack) — attacker can reconstruct signature via response-time measurement"
fix: "N/A — finding dismissed; hmac.compare_digest already in use"
```

```yaml
id: FIX-023
priority: P1
severity: CRITICAL
source: gemini
confirmed: dismissed
result: "temporal.py contains no @workflow.run, @workflow.defn, or @activity.defn decorators; it is a plain async orchestrator class; datetime.now at line 218 is in a regular async DB method; finding dismissed"
file: trimcp/orchestrators/temporal.py
line: "N/A"
category: concurrency
title: "Non-deterministic operations inside Temporal @workflow.run — NonDeterministicWorkflowError on worker restart wedges all in-flight workflows"
fix: "N/A — finding dismissed; no Temporal SDK workflow definitions in file"
```

```yaml
id: FIX-024
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-3
completed: 2026-05-12
file: "trimcp/orchestrators/graph.py, trimcp/consolidation.py, trimcp/orchestrators/temporal.py (6+ sites)"
line: "varies"
category: perf
title: "N+1 MongoDB find_one in loops — linear DB roundtrips per result under read load"
fix: "Replace for id in ids: await mongo.find_one({'_id': id}) with docs = {d['_id']: d async for d in mongo.find({'_id': {'$in': ids}})} and index the result"
```

```yaml
id: FIX-025
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Composer (phase6 wave2–4)
completed: 2026-05-12
file: trimcp/orchestrators/memory.py
line: "unredact_memory"
category: rls
title: "unredact_memory uses raw pool.acquire() bypassing RLS scoped session"
fix: "Replace direct pool.acquire() with scoped_pg_session(pool, namespace_id=namespace_id) context manager"
```

```yaml
id: FIX-026
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Composer (phase6 wave2–4)
completed: 2026-05-12
file: trimcp/orchestrators/namespace.py
line: "delete method"
category: data-integrity
title: "namespace.py:delete issues DELETE on event_log — destroys WORM audit trail"
fix: "Remove event_log DELETE from namespace deletion path; archive rather than delete; if deletion required, require explicit superadmin flag"
```

```yaml
id: FIX-027
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W2-C
completed: 2026-05-12
file: trimcp/garbage_collector.py
line: "OFFSET pagination"
category: data-integrity
title: "OFFSET pagination in GC creates false orphan detection — deletes live memories on concurrent insert"
fix: "Rewrite GC to keyset pagination: WHERE id > last_seen_id ORDER BY id LIMIT batch_size; or use FOR UPDATE SKIP LOCKED CTE pattern"
```

```yaml
id: FIX-028
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-3
completed: 2026-05-12
file: trimcp/contradictions.py
line: "152-169"
category: perf
title: "N+1 DB queries in _check_kg_contradiction — up to 3×N individual fetchrow calls per contradiction check"
fix: "Batch into: WHERE (subject_label, predicate, object_label) = ANY($1::text[][]) or use VALUES list; single query for all triplets"
```

```yaml
id: FIX-029
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Composer (phase6 wave2–4)
completed: 2026-05-12
file: trimcp/contradictions.py
line: "_resolve_with_llm"
category: resource
title: "10–30s LLM API call made while DB connection held — pool starvation during contradiction resolution"
fix: "Release connection before LLM call; re-acquire after: release conn before provider.complete(); store result; re-enter scoped_pg_session for the INSERT"
```

```yaml
id: FIX-030
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W3-A
completed: 2026-05-12
file: trimcp/graph_query.py
line: "BFS recursive CTE"
category: perf
title: "BFS cycle guard NOT EXISTS references only PostgreSQL working table — cyclic KG nodes produce unbounded traversal"
fix: "Change cycle guard to use accumulated path array: NOT e.target_label = ANY(traversal.path) and carry path as text[] column through the CTE"
```

```yaml
id: FIX-031
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W3-B
completed: 2026-05-12
file: trimcp/graph_extractor.py
line: "_spacy_extract()"
category: perf
title: "spacy.load() called on every extraction — 15MB model reloaded from disk per KG extraction"
fix: "Add @lru_cache(maxsize=1) on a _get_spacy_nlp() helper function; call nlp = _get_spacy_nlp() instead of spacy.load() directly"
```

```yaml
id: FIX-032
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Composer (phase6 wave2–4)
completed: 2026-05-12
file: trimcp/providers/base.py
line: "516 (DEFAULT_CIRCUIT_BREAKER)"
category: concurrency
title: "Shared module-level singleton circuit breaker — one provider's failures open breaker for all providers"
fix: "Remove DEFAULT_CIRCUIT_BREAKER module-level singleton; each LLMProvider subclass __init__ must create its own CircuitBreaker() instance: self._circuit_breaker = CircuitBreaker()"
```

```yaml
id: FIX-033
priority: P1
severity: MAJOR
source: both
confirmed: yes
dispatched: yes
dispatched_by: Seq-3
completed: 2026-05-12
file: trimcp/providers/factory.py
line: "get_provider()"
category: perf
title: "get_provider() creates new httpx client + SSRF DNS validation on every LLM call — socket starvation at scale"
fix: "Add @lru_cache(maxsize=128) keyed on (label, model_id, cred_ref) tuple; cache provider instances per configuration; add eviction on credential rotation"
```

```yaml
id: FIX-034
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-4
completed: 2026-05-12
file: "trimcp/re_embedder.py, trimcp/reembedding_worker.py"
line: "asyncio.create_task() sites"
category: concurrency
title: "Fire-and-forget asyncio.create_task in start_re_embedder — exceptions silently discarded, callers receive false success"
fix: "Store task reference: self._task = asyncio.create_task(run_re_embedding_worker(...)); add task.add_done_callback to log exceptions; or use TaskGroup"
```

```yaml
id: FIX-035
priority: P2
severity: MINOR
source: gemini
confirmed: partial
dispatched: yes
dispatched_by: Seq-2C
completed: 2026-05-12
result: "Regex patterns exist (CREDIT_CARD uses (?:\\d[ -]*?){13,16}); however _scan_sync already runs via asyncio.to_thread(line 133) — event loop CANNOT be frozen. Worker thread may be slow on adversarial input. Downgraded from MAJOR to MINOR."
file: trimcp/pii.py
line: "33-36, 133"
category: perf
title: "CREDIT_CARD regex (?:\\d[ -]*?){13,16} may be slow on adversarial input (event loop already protected by asyncio.to_thread)"
fix: "Mitigated: event loop safe. Optional hardening: add max text length guard (e.g. 500KB) before calling _scan_sync; consider google-re2 if worker CPU becomes a bottleneck under load"
```

```yaml
id: FIX-036
priority: P1
severity: MAJOR
source: gemini
confirmed: dismissed
result: "grep 'genai.configure' trimcp/providers/google_gemini.py returned no matches; finding dismissed"
file: trimcp/providers/google_gemini.py
line: "N/A"
category: concurrency
title: "genai.configure(api_key=) sets process-global state — concurrent tenant requests cross-contaminate API keys"
fix: "N/A — finding dismissed; genai.configure not present"
```

```yaml
id: FIX-037
priority: P1
severity: MAJOR
source: gemini
confirmed: dismissed
result: "jwt_auth.py does not use JWKS or PyJWKClient; RS256/ES256 keys are loaded from TRIMCP_JWT_PUBLIC_KEY PEM env var at startup; HS256 uses TRIMCP_JWT_SECRET; no per-request key fetch; finding dismissed"
file: trimcp/jwt_auth.py
line: "N/A"
category: auth
title: "JWKS fetched per-request without caching — identity provider outage locks out all users"
fix: "N/A — finding dismissed; no JWKS endpoint used"
```

```yaml
id: FIX-038
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W3-D
completed: 2026-05-12
file: trimcp/schema.sql
line: "274"
category: data-integrity
title: "kg_edges_old migration uses wrong ON CONFLICT target — fails when 4-column unique constraint is active"
fix: "Change ON CONFLICT (subject_label, predicate, object_label) to ON CONFLICT (subject_label, predicate, object_label, namespace_id)"
```

```yaml
id: FIX-039
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W3-E
completed: 2026-05-12
file: "server.py, trimcp/admin_server.py"
line: "TRIMCP_ADMIN_OVERRIDE"
category: auth
title: "Admin bypass with no production environment guard — dev shortcut leaks to production"
fix: "Add: if os.getenv('TRIMCP_ADMIN_OVERRIDE') and os.getenv('ENVIRONMENT','dev') == 'prod': raise RuntimeError('ADMIN_OVERRIDE must not be set in production')"
```

```yaml
id: FIX-040
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W3-F
completed: 2026-05-12
file: "trimcp/orchestrators/migration.py"
line: "start_migration"
category: concurrency
title: "TOCTOU race in start_migration — two concurrent calls create two active migrations"
fix: "Wrap check-and-insert in a single SQL: INSERT INTO embedding_migrations ... WHERE NOT EXISTS (SELECT 1 FROM embedding_migrations WHERE status = 'running') RETURNING id; return None if no row returned"
```

```yaml
id: FIX-041
priority: P1
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Composer (phase6 wave2–4)
completed: 2026-05-12
file: trimcp/replay.py
line: "LLM call inside REPEATABLE READ cursor"
category: concurrency
title: "LLM API call inside REPEATABLE READ cursor transaction — long-held transaction + external I/O"
fix: "Fetch event batch, commit transaction, process events (including LLM calls) outside transaction, then write results in new transaction"
```

```yaml
id: FIX-042
priority: P1
severity: MAJOR
source: gemini
confirmed: dismissed
result: "local_cognitive.py uses httpx HTTP client to a containerized model at localhost:11435; no PyTorch/llama.cpp in-process; all inference is async HTTP I/O; no GIL blocking possible; finding dismissed"
file: trimcp/providers/local_cognitive.py
line: "N/A"
category: perf
title: "Synchronous ML inference (PyTorch/llama.cpp) inside async def — locks GIL, freezes event loop"
fix: "N/A — finding dismissed; model runs in separate container accessed via async HTTP"
```

## P2 — Operational / Quality

```yaml
id: FIX-043
priority: P2
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2B
completed: 2026-05-12
file: trimcp-infra/aws/modules/fargate-worker/main.tf
line: "236,253"
category: infra
title: "deployment_minimum_healthy_percent = 0 — every deployment causes full downtime"
fix: "Set deployment_minimum_healthy_percent = 100 and deployment_maximum_percent = 200 on both ECS services"
```

```yaml
id: FIX-044
priority: P2
severity: MAJOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2B
completed: 2026-05-12
file: trimcp-infra/aws/modules/elasticache/main.tf
line: "67"
category: infra
title: "apply_immediately = true on ElastiCache — parameter changes apply in business hours, potential cache flush"
fix: "Change to: apply_immediately = var.environment != \"prod\""
```

```yaml
id: FIX-045
priority: P2
severity: MAJOR
source: gemini
confirmed: yes
dispatched: yes
dispatched_by: Seq-2B
completed: 2026-05-12
result: "Confirmed: gcp/modules/cloudrun-worker/main.tf line 18 has max_instance_request_concurrency = 10; fine for async I/O workloads but may starve async workers during CPU-bound extraction bursts"
file: trimcp-infra/gcp/modules/cloudrun-worker/main.tf
line: "18"
category: infra
title: "Cloud Run max_instance_request_concurrency = 10 — may saturate workers during CPU-bound extraction bursts"
fix: "For async I/O-heavy workers: keep at 10. For extraction workers handling large files: reduce to 2-3 and scale via Cloud Tasks; add TRIMCP_CONCURRENCY env var to make it configurable per deployment type"
```

```yaml
id: FIX-046
priority: P2
severity: MAJOR
source: gemini
confirmed: partial
dispatched: yes
dispatched_by: Composer (phase6 wave2–4)
completed: 2026-05-12
result: "main.go documents that SIGTERM→child forwarding lives in external github.com/trimcp/tri-stack/launch.Run (not verifiable here). rootctx_unix.go capture unchanged."
file: "trimcp-launch/cmd/trimcp-launch/rootctx_unix.go, trimcp-launch/cmd/trimcp-launch/main.go"
line: "13 (notifyRootContext), 27 (launch.Run)"
category: infra
title: "Go launcher SIGTERM capture confirmed; signal forwarding to Python child unverifiable without launch package source"
fix: "Inspect launch.Run source; verify cmd.Process.Signal(syscall.SIGTERM) is called on context cancellation; if not: add os/exec subprocess with explicit signal forwarding before process.Wait()"
```

```yaml
id: FIX-047
priority: P2
severity: MAJOR
source: gemini
confirmed: dismissed
dispatched: N/A
result: "snapshot_serializer.py serializes SnapshotRecord Pydantic model containing id, namespace_id, agent_id, name, snapshot_at, created_at, metadata — snapshot metadata only, not memory content; no user-submitted PII-containing text serialized here; finding dismissed"
file: trimcp/snapshot_serializer.py
line: "63-77"
category: data-integrity
title: "PII not redacted before snapshot serialization — plaintext sensitive data written to snapshot storage"
fix: "N/A — finding dismissed; serializer handles snapshot metadata (names/timestamps), not memory content"
```

```yaml
id: FIX-048
priority: P2
severity: MAJOR
source: gemini
confirmed: dismissed
dispatched: N/A
result: "bridge_status handler uses bridge_repo.subscription_to_public_dict(row) — function explicitly documented 'no secrets' and returns only: id, user_id, provider, resource_id, subscription_id, cursor, status, expires_at; access_token and refresh_token are excluded; finding dismissed"
file: trimcp/bridge_mcp_handlers.py
line: "595-602"
category: auth
title: "Bridge status response may include OAuth token material visible to AI agent"
fix: "N/A — finding dismissed; subscription_to_public_dict() already filters to safe fields only"
```

```yaml
id: FIX-049
priority: P2
severity: MAJOR
source: gemini
confirmed: dismissed
dispatched: N/A
result: "encryption.py is a detection-only module (sniffs whether files are encrypted/locked); uses in-memory io.BytesIO; no decryption, no temp files written to disk; finding dismissed"
file: trimcp/extractors/encryption.py
line: "N/A"
category: data-integrity
title: "Decrypted temp files may survive worker crashes — plaintext PII on disk"
fix: "N/A — finding dismissed; encryption.py is detection-only, no temp files"
```

```yaml
id: FIX-050
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-6C (vague — agent will scan todos, may identify this item)
completed: 2026-05-12
file: trimcp/mcp_args.py
line: "202"
category: crypto
title: "MD5 used for cache key hashing"
fix: "Replace hashlib.md5 with hashlib.sha256 for cache key derivation"
```

```yaml
id: FIX-051
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W4-A
completed: 2026-05-12
file: trimcp/ast_parser.py
line: "_walk() function"
category: resource
title: "Recursive _walk() has no depth limit — RecursionError on deeply nested auto-generated code"
fix: "Add depth parameter: def _walk(node, depth=0): if depth > 200: return; recurse with _walk(child, depth+1)"
```

```yaml
id: FIX-052
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W4-B
completed: 2026-05-12
file: trimcp/notifications.py
line: "SMTP config"
category: config
title: "Placeholder emails (admin@example.com) and unencrypted SMTP port 25"
fix: "Read From/To from environment variables; change port 25 to 587 with STARTTLS: aiosmtplib.send(..., port=587, use_tls=False, start_tls=True)"
```

```yaml
id: FIX-053
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W4-C
completed: 2026-05-12
file: trimcp/openvino_npu_export.py
line: "99"
category: auth
title: "trust_remote_code=True in AutoTokenizer.from_pretrained — arbitrary code from Hub model"
fix: "Add: if not local_files_only: log.warning('trust_remote_code=True with hub access'); pin model revision hash in from_pretrained(revision='<sha>')"
```

```yaml
id: FIX-054
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W4-D
completed: 2026-05-12
file: trimcp/schema.sql
line: "pii_redactions table"
category: perf
title: "pii_redactions has no index on namespace_id — full partition scan for namespace-scoped PII queries"
fix: "CREATE INDEX IF NOT EXISTS idx_pii_redactions_ns ON pii_redactions (namespace_id);"
```

```yaml
id: FIX-055
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W4-D
completed: 2026-05-12
file: trimcp/schema.sql
line: "kg_node_embeddings"
category: rls
title: "kg_node_embeddings has RLS enabled but no policy defined — all rows blocked for trimcp_app"
fix: "Either add namespace_id to kg_node_embeddings and create matching policy, or disable RLS if intentionally global: ALTER TABLE kg_node_embeddings DISABLE ROW LEVEL SECURITY"
```

```yaml
id: FIX-056
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-2B
completed: 2026-05-12
file: deploy/multiuser/Dockerfile
line: "31"
category: config
title: "spaCy model downloaded without pinned version — non-deterministic builds"
fix: "Replace 'python -m spacy download en_core_web_sm' with pip install of pinned wheel URL + SHA256 hash"
```

```yaml
id: FIX-057
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W4-E
completed: 2026-05-12
file: trimcp-infra/aws/modules/fargate-worker/main.tf
line: "fargate services"
category: infra
title: "No auto-scaling configured for ECS services — queue backlog with no automatic relief"
fix: "Add aws_appautoscaling_target and aws_appautoscaling_policy resources keyed on SQS queue depth or ECS CPU utilization"
```

```yaml
id: FIX-058
priority: P2
severity: MINOR
source: gemini
confirmed: dismissed
dispatched: N/A
result: "providers/base.py RetryPolicy.delay_for_attempt() uses full-jitter at line 686: delay_ms = max(1, int(random.uniform(0, max(1, cap_ms)))); also respects Retry-After header on 429s; finding dismissed — already implemented"
file: trimcp/providers/anthropic_provider.py
line: "N/A (base.py line 686)"
category: perf
title: "Fixed retry backoff without jitter — thundering herd on Anthropic rate limits"
fix: "N/A — finding dismissed; full-jitter already in RetryPolicy.delay_for_attempt() in base.py"
```

```yaml
id: FIX-059
priority: P2
severity: MINOR
source: gemini
confirmed: dismissed
dispatched: N/A
result: "bridges/base.py has no sync() method; uses walk_delta() returning Iterator[dict[str, Any]] (standard Python generator); generator-style already avoids loading all items into memory; finding dismissed"
file: trimcp/bridges/base.py
line: "N/A"
category: perf
title: "Base bridge sync() returns List[dict] — forces all implementations to load entire document set into memory"
fix: "N/A — finding dismissed; walk_delta() uses Iterator not List"
```

```yaml
id: FIX-060
priority: P2
severity: MINOR
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: Seq-6C (vague — agent will scan todos, may identify this item)
completed: 2026-05-12
file: trimcp/observability.py
line: "_otel_context.attach"
category: config
title: "Private _otel_context API used for OTel context attachment — breaks on OTel SDK version upgrades"
fix: "Replace with: from opentelemetry import context as otel_context; token = otel_context.attach(ctx)"
```

---

## Verification Checklist — COMPLETED 2026-05-11 (all 9 DISMISSED)

```yaml
verification_results:
  - id: VERIFY-001
    file: trimcp/extractors/libreoffice.py
    command: "grep -n 'shell=True' trimcp/extractors/libreoffice.py"
    result: DISMISSED
    note: "No matches; Sonnet PASS confirmed"
    escalates_to: FIX-004
    action_taken: "FIX-004 confirmed: dismissed"

  - id: VERIFY-002
    file: trimcp/jwt_auth.py
    command: "grep -n 'jwt.decode' trimcp/jwt_auth.py"
    result: DISMISSED
    note: "decode_kwargs line 283 sets algorithms=[algorithm], issuer, audience, options; properly configured"
    escalates_to: FIX-005
    action_taken: "FIX-005 confirmed: dismissed"

  - id: VERIFY-003
    file: trimcp/tasks.py
    command: "grep -rn 'import pickle|pickle.loads|pickle.dumps' trimcp/tasks.py"
    result: DISMISSED
    note: "No pickle usage found"
    escalates_to: FIX-006
    action_taken: "FIX-006 confirmed: dismissed"

  - id: VERIFY-004
    file: trimcp/code_mcp_handlers.py
    command: "grep -n 'exec(|eval(' trimcp/code_mcp_handlers.py"
    result: DISMISSED
    note: "No exec/eval found"
    escalates_to: FIX-007
    action_taken: "FIX-007 confirmed: dismissed"

  - id: VERIFY-005
    file: trimcp/migration_mcp_handlers.py
    command: "grep -n 'mcp_command|@mcp' trimcp/migration_mcp_handlers.py"
    result: DISMISSED
    note: "@mcp_handler found but all decorated with @require_scope('admin'); calls orchestrator.start_migration() (embedding migration, not schema DDL)"
    escalates_to: FIX-008
    action_taken: "FIX-008 confirmed: dismissed"

  - id: VERIFY-006
    file: trimcp/extractors/project_ext.py
    command: "grep -n 'extract|zipfile|tarfile|member.filename' trimcp/extractors/project_ext.py"
    result: DISMISSED
    note: "File handles .mpp (MPXJ sidecar) and .pub (LibreOffice convert); no archive extraction"
    escalates_to: FIX-009
    action_taken: "FIX-009 confirmed: dismissed"

  - id: VERIFY-007
    file: trimcp/signing.py
    command: "grep -n 'hmac|compare_digest' trimcp/signing.py"
    result: DISMISSED
    note: "signing.py line 906: return hmac.compare_digest(computed, expected_signature); already correct"
    escalates_to: FIX-022
    action_taken: "FIX-022 confirmed: dismissed"

  - id: VERIFY-008
    file: trimcp/orchestrators/temporal.py
    command: "grep -n '@workflow.|@activity.' trimcp/orchestrators/temporal.py"
    result: DISMISSED
    note: "No @workflow.run, @workflow.defn, or @activity.defn decorators; file is plain async orchestrator class despite name; datetime.now at line 218 is in regular async DB method"
    escalates_to: FIX-023
    action_taken: "FIX-023 confirmed: dismissed"

  - id: VERIFY-009
    file: trimcp/providers/google_gemini.py
    command: "grep -n 'genai.configure' trimcp/providers/google_gemini.py"
    result: DISMISSED
    note: "No matches; genai.configure not called"
    escalates_to: FIX-036
    action_taken: "FIX-036 confirmed: dismissed"
```

---

## Summary Counts

```yaml
summary:
  total_items: 60
  active_items: 44  # 16 dismissed + FIX-035 reclassified; 2026-05-11 full verification pass
  dismissed_items: 16  # all Gemini-only unconfirmed findings — none exist in actual code
  partially_confirmed: 2  # FIX-035 (mitigated), FIX-046 (launch pkg unverifiable)
  by_priority_active:
    P0: 14  # FIX-001 to FIX-003 + FIX-010 to FIX-020 (all sonnet confirmed)
    P1: 16  # was 22; dismissed FIX-022/023/036/037/042 (-5); FIX-035 moved to P2
    P2: 14  # was 18; dismissed FIX-047/048/049/058/059 (-5); +FIX-035 reclassified (+1)
  by_severity_active:
    CRITICAL: 15  # 8 CRITICALs dismissed (FIX-004 to FIX-009, FIX-022, FIX-023); 15 remain
    MAJOR: 19    # dismissed: FIX-036/037/042/047/048/049 (-6); FIX-035 downgraded (-1) = 19
    MINOR: 10    # original 9 active (FIX-050-057,060) + FIX-035 reclassified = 10
  by_source_active:
    sonnet_confirmed: 38
    gemini_fully_dismissed: 16
    gemini_partial_confirmed: 2  # FIX-035 (mitigated), FIX-046 (partial signal verify)
    gemini_verify_needed: 0  # all gemini findings now resolved
  verification_completed: 2026-05-11
  dispatch_status_completed: 2026-05-11
  grand_total_audit_findings:
    CRITICAL: 52
    MAJOR: 96
    MINOR: 83
    NITPICK: 3
```

---

## Supplemental Sequences — Required (Not Yet Pushed)

### Seq-9A — P0 Credential & Billing Gaps (IMMEDIATE)
**Covers:** FIX-013, FIX-020
**Tool:** Any capable code-editing agent (Composer 2 or Gemini 3.1 Pro recommended)
**Rationale:** Both are P0 CRITICAL findings that were missed by all 8 dispatched sequences. FIX-013 is a hardcoded secret committed to the repository. FIX-020 is a billing correctness bug that double-charges users on cache hits. These are safe to fix in parallel — different files, no shared call paths.

```
TASK: Fix two P0 CRITICAL issues in TriMCP:

--- FIX-013: Hardcoded MinIO credential (trimcp/config.py) ---
The MINIO_SECRET_KEY field has a hardcoded default value committed in the repository.
Fix:
  1. Change the default to an empty string.
  2. Add startup validation in the Settings __post_init__ or validator:
       if not self.MINIO_SECRET_KEY:
           raise ValueError("MINIO_SECRET_KEY must be set via environment variable — no default allowed")
  3. Grep for any other *_SECRET_KEY or *_PASSWORD fields in config.py that also have
     non-empty defaults and apply the same treatment.

--- FIX-020: Quota double-billing on cache hit (trimcp/server.py) ---
The quota increment runs BEFORE the cache lookup. When the cache returns a hit,
the quota has already been consumed even though no LLM call was made.
Fix:
  1. Locate the quota-increment call site in the request handler.
  2. Move it to AFTER the cache miss check — only increment when you confirm
     you are about to make an LLM call.
  3. If the cache hit path was already incrementing and then rolling back,
     simplify to never increment on a cache hit at all.
  4. Add a comment: # quota must not be incremented on cache hit — see FIX-020
```

---

### Seq-9B — RLS / Data Integrity Cluster (HIGH)
**Covers:** FIX-025, FIX-026, FIX-027, FIX-029
**Tool:** Composer 2 (Cursor) — multi-file edits required
**Rationale:** All four are P1 MAJOR findings in the database/data-integrity layer. They are safe to fix in the same session because they touch different files and none of the fixes conflict.

```
TASK: Fix four P1 data-integrity and RLS issues in TriMCP:

--- FIX-025: unredact_memory bypasses RLS (trimcp/orchestrators/memory.py) ---
The unredact_memory function uses a raw pool.acquire() call, bypassing the
scoped_pg_session context manager that sets trimcp.namespace_id for RLS.
Fix:
  Replace:
    async with pool.acquire() as conn:
  With:
    async with scoped_pg_session(pool, namespace_id=namespace_id) as conn:
  Ensure namespace_id is passed through to this function from its callers.

--- FIX-026: namespace:delete destroys WORM audit log (trimcp/orchestrators/namespace.py) ---
The delete method issues a DELETE on the event_log table, permanently destroying the
immutable audit trail for the namespace.
Fix:
  Remove the DELETE FROM event_log statement from the namespace deletion path.
  If namespace deletion is intentionally irreversible, add a required superadmin flag:
    if not superadmin_override:
        raise PermissionError("Namespace deletion requires explicit superadmin_override=True")
  Archive event_log rows to a cold_event_log or event_log_archive table instead of deleting.

--- FIX-027: OFFSET pagination in GC causes false orphan detection (trimcp/garbage_collector.py) ---
The garbage collector uses OFFSET-based pagination. Under concurrent inserts, rows shift
between pages, causing the GC to "miss" records and falsely identify live memories as orphans.
Fix:
  Replace OFFSET pagination with keyset (cursor-based) pagination:
    WHERE id > $last_seen_id ORDER BY id LIMIT $batch_size
  Carry last_seen_id between GC batches. Never use OFFSET on a table that receives concurrent writes.

--- FIX-029: LLM call while DB connection held (trimcp/contradictions.py) ---
The _resolve_with_llm function makes a 10–30s external LLM API call while holding
an open asyncpg connection from the pool. Under concurrent contradiction resolution this
exhausts the pool.
Fix:
  1. Before the LLM call: release the connection (exit the scoped_pg_session context).
  2. Make the LLM call outside any database context.
  3. Re-enter scoped_pg_session for the INSERT of the resolution result.
  Pattern:
    resolution = None
    async with scoped_pg_session(pool, namespace_id=ns) as conn:
        # fetch data needed for LLM
        context_data = await conn.fetch(...)
    # conn released here
    resolution = await provider.complete(messages, ...)  # no conn held
    async with scoped_pg_session(pool, namespace_id=ns) as conn:
        await conn.execute("INSERT INTO ...", resolution)
```

---

### Seq-9C — Performance & Correctness Cluster (HIGH)
**Covers:** FIX-030, FIX-031, FIX-032, FIX-038, FIX-039, FIX-040, FIX-041
**Tool:** Gemini 3.1 Pro (CLI) or Composer 2 — seven distinct files
**Rationale:** Seven P1 MAJOR issues spanning graph traversal correctness, performance, auth hardening, and transaction safety. Group them in one session to avoid context-switching overhead, but they can be tackled sequentially.

```
TASK: Fix seven P1 issues in TriMCP. Work through them sequentially.

--- FIX-030: BFS cycle guard unbounded traversal (trimcp/graph_query.py) ---
The recursive CTE cycle guard uses NOT EXISTS referencing only the PostgreSQL working table.
For cyclic KG graphs this produces unbounded recursion.
Fix:
  Add a path accumulator column to the CTE:
    WITH RECURSIVE traversal(node_label, path, depth) AS (
      SELECT start_label, ARRAY[start_label], 0
      UNION ALL
      SELECT e.target_label,
             traversal.path || e.target_label,
             traversal.depth + 1
      FROM kg_edges e
      JOIN traversal ON e.source_label = traversal.node_label
      WHERE NOT e.target_label = ANY(traversal.path)
        AND traversal.depth < 50
    )
  Replace the existing NOT EXISTS guard with NOT e.target_label = ANY(traversal.path).

--- FIX-031: spacy.load() per extraction (trimcp/graph_extractor.py) ---
spacy.load() is called inside _spacy_extract() on every invocation, reloading the 15MB
model from disk each time.
Fix:
  Add a module-level cached loader:
    from functools import lru_cache
    @lru_cache(maxsize=1)
    def _get_spacy_nlp():
        import spacy
        return spacy.load("en_core_web_sm")
  Replace all spacy.load() calls in the file with nlp = _get_spacy_nlp().

--- FIX-032: Shared module-level circuit breaker (trimcp/providers/base.py) ---
DEFAULT_CIRCUIT_BREAKER is a module-level singleton shared by all LLMProvider subclasses.
One provider tripping the breaker blocks all other providers.
Fix:
  Remove or privatize DEFAULT_CIRCUIT_BREAKER.
  In LLMProvider.__init__, add:
    self._circuit_breaker = CircuitBreaker()
  All subclasses that call execute_with_retry must use self._circuit_breaker, not the global.

--- FIX-038: kg_edges_old ON CONFLICT target (trimcp/schema.sql) ---
The migration for kg_edges_old uses ON CONFLICT (subject_label, predicate, object_label)
but the live unique constraint is on 4 columns including namespace_id.
Fix:
  At line 274 (or wherever the ON CONFLICT clause appears for kg_edges_old):
  Change:
    ON CONFLICT (subject_label, predicate, object_label)
  To:
    ON CONFLICT (subject_label, predicate, object_label, namespace_id)

--- FIX-039: ADMIN_OVERRIDE no production guard (server.py, trimcp/admin_server.py) ---
TRIMCP_ADMIN_OVERRIDE is a debug shortcut with no check to prevent it being set in production.
Fix:
  At the point where TRIMCP_ADMIN_OVERRIDE is read/respected, add:
    if os.getenv("TRIMCP_ADMIN_OVERRIDE") and os.getenv("ENVIRONMENT", "dev") == "prod":
        raise RuntimeError(
            "TRIMCP_ADMIN_OVERRIDE must not be set in production (ENVIRONMENT=prod)"
        )
  Apply to all call sites in both server.py and admin_server.py.

--- FIX-040: TOCTOU race in start_migration (trimcp/orchestrators/migration.py) ---
start_migration checks for an active migration in one query, then inserts in a second query.
Two concurrent callers both pass the check and create duplicate active migrations.
Fix:
  Replace the two-step check+insert with an atomic conditional INSERT:
    result = await conn.fetchrow("""
        INSERT INTO embedding_migrations (namespace_id, status, ...)
        SELECT $1, 'running', ...
        WHERE NOT EXISTS (
            SELECT 1 FROM embedding_migrations
            WHERE namespace_id = $1 AND status = 'running'
        )
        RETURNING id
    """, namespace_id, ...)
    if result is None:
        return None  # migration already running

--- FIX-041: LLM call inside REPEATABLE READ cursor (trimcp/replay.py) ---
An LLM API call (external I/O, 10–30s) is made while a REPEATABLE READ cursor transaction
is held open, creating a long-lived transaction and blocking vacuum/autovacuum.
Fix:
  1. Fetch the event batch from the cursor.
  2. Commit/close the transaction.
  3. Process events and make LLM calls outside any transaction.
  4. Open a new transaction to write results.
  Never hold a database transaction open across external network I/O.
```
