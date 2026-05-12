# TriMCP Phase 6 — Supplemental Remediation Sequences
# Generated: 2026-05-12 | Uncle-Bob-Craft + Antigravity-Workflows
# Covers: all dispatched:NO items in to-do-v1-phase6.md

---

## Resource Map

| Tool | Capability tier | Best for |
|------|----------------|----------|
| **Cursor / Composer 2** | Highest | Multi-file async Python, context-manager rewrites, DI refactors |
| **Gemini CLI / Gemini 3.1 Pro** | High | Complex SQL (CTEs, ON CONFLICT), Terraform, algorithmic logic |
| **VS Code / Haiku 4.5** | Medium | Single-file Python, config guards, trivial one-liners |
| **Google Antigravity / Gemini 3 Flash** | Light | SQL index additions, YAML/doc patches, schema.sql simple changes |

---

## Dependency Wave Diagram

```
WAVE 1  ── run these first, both in parallel ──────────────────────────
  W1-A  FIX-013  Haiku      trimcp/config.py          hardcoded MinIO secret
  W1-B  FIX-020  Composer   trimcp/server.py           quota double-billing

        ▼ after Wave 1 completes (or immediately if you accept risk) ▼

WAVE 2  ── P1 RLS + data-integrity cluster (all parallel) ────────────
  W2-A  FIX-025  Composer   orchestrators/memory.py   RLS bypass in unredact
  W2-B  FIX-026  Composer   orchestrators/namespace.py WORM audit deletion
  W2-C  FIX-027  Gemini Pro garbage_collector.py      OFFSET → keyset pagination
  W2-D  FIX-029  Composer   contradictions.py         conn held during LLM call

WAVE 3  ── P1 correctness + perf cluster (parallel with Wave 2) ──────
  W3-A  FIX-030  Gemini Pro graph_query.py            BFS cycle guard CTE
  W3-B  FIX-031  Haiku      graph_extractor.py        spacy.load lru_cache
  W3-C  FIX-032  Composer   providers/base.py         shared circuit breaker
  W3-D  FIX-038  Haiku      schema.sql                ON CONFLICT 4-col target
  W3-E  FIX-039  Haiku      server.py + admin_server  ADMIN_OVERRIDE guard
  W3-F  FIX-040  Gemini Pro orchestrators/migration.py TOCTOU atomic INSERT
  W3-G  FIX-041  Composer   replay.py                 LLM outside REPEATABLE READ

WAVE 4  ── P2 quality (parallel with Waves 2+3, lower priority) ──────
  W4-A  FIX-051  Haiku      ast_parser.py             recursion depth limit
  W4-B  FIX-052  Haiku      notifications.py          SMTP port 25 → 587+TLS
  W4-C  FIX-053  Haiku      openvino_npu_export.py    trust_remote_code guard
  W4-D  FIX-054+055 Flash   schema.sql                index + RLS policy
  W4-E  FIX-057  Gemini Pro fargate-worker/main.tf    ECS autoscaling
  W4-F  FIX-046  Composer   trimcp-launch (Go)        signal forwarding audit
```

### Scheduling with 4 simultaneous tools

```
Round 1  │ Haiku: W1-A  │ Composer: W1-B  │ —      │ —
         └─ await both ─┘
Round 2  │ Haiku: W3-B  │ Composer: W2-A  │ Gemini Pro: W2-C  │ Flash: W4-D
Round 3  │ Haiku: W3-D  │ Composer: W2-B  │ Gemini Pro: W3-A  │ Flash: (idle/docs)
Round 4  │ Haiku: W3-E  │ Composer: W2-D  │ Gemini Pro: W3-F  │ Flash: (idle/docs)
Round 5  │ Haiku: W4-A  │ Composer: W3-C  │ Gemini Pro: W4-E  │ Flash: (idle/docs)
Round 6  │ Haiku: W4-B  │ Composer: W3-G  │ Gemini Pro: (done)│ Flash: (idle/docs)
Round 7  │ Haiku: W4-C  │ Composer: W4-F  │ —      │ —
```

---

## Uncle Bob Craft Principles Applied Per Prompt

Every prompt below follows these rules (@ `uncle-bob-craft`):
- **SRP** — one prompt, one fix, one reason to change.
- **Boy Scout Rule** — leave every touched function cleaner than found.
- **Small functions** — extract named helpers; never leave business logic inline.
- **No hacks** — no `# TODO fix later`; fix it or defer it explicitly in the todo.
- **Tests/verification** — every prompt ends with a concrete verification step.
- **Do no harm** — read before editing; confirm before moving to next step.

---

## WAVE 1 — P0 Blockers (Run First)

---

### W1-A · FIX-013 · Haiku 4.5 (VS Code)
**File:** `trimcp/config.py` · **Priority:** P0 CRITICAL

```
@uncle-bob-craft

You are fixing a hardcoded MinIO credential in TriMCP (FIX-013, P0 CRITICAL).

STEP 1 — READ FIRST
Read `trimcp/config.py` in full. Find the MINIO_SECRET_KEY field and any other
*_SECRET_KEY or *_PASSWORD fields that have non-empty string defaults.

STEP 2 — APPLY THE FIX
For MINIO_SECRET_KEY (and any other credential fields with non-empty defaults):
  a. Change the default value to an empty string: `MINIO_SECRET_KEY: str = ""`
  b. Add a @validator or __post_init__ / model_validator that raises ValueError
     when the field is empty at startup.

Name the validator clearly: `validate_minio_credentials` (SRP — one validator,
one responsibility). Do NOT add a generic "all fields" validator that hides the
intent. Each credential field should fail loudly with a message that names
the environment variable to set:
  raise ValueError(
      "MINIO_SECRET_KEY must be set via the MINIO_SECRET_KEY environment variable. "
      "No default is permitted in production."
  )

STEP 3 — BOY SCOUT
While in config.py, check: are there any other fields with hardcoded secrets
(passwords, tokens, keys)? If yes, apply the same treatment. If unsure, add a
comment: `# SECURITY: empty default enforced — see FIX-013`.

STEP 4 — VERIFY
After editing, run:
  grep -n "MINIO_SECRET_KEY" trimcp/config.py
Confirm the default is now `""` and a validator is present.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, find the FIX-013 YAML block and change:
  dispatched: NO
  dispatched_by: NONE — GAP
to:
  dispatched: yes
  dispatched_by: W1-A
  completed: 2026-05-12
```

---

### W1-B · FIX-020 · Composer 2 (Cursor)
**File:** `trimcp/server.py` · **Priority:** P0 CRITICAL

```
@uncle-bob-craft

You are fixing a quota double-billing bug in TriMCP (FIX-020, P0 CRITICAL).
A quota counter is incremented BEFORE the cache is checked, meaning cache hits
still consume quota.

STEP 1 — READ FIRST
Read `trimcp/server.py`. Find the request handler that:
  1. Increments a quota counter (look for quota, increment, consume, decrement)
  2. Checks a cache (look for cache.get, redis.get, lookup)
  3. Makes an LLM call on cache miss

Map the current order of these three operations.

STEP 2 — EXTRACT INTENT (Uncle Bob: reveal the algorithm)
Before patching, extract the three operations into named sub-steps if they are
currently inline. Name them clearly:
  - `_increment_quota(namespace_id, conn)`
  - `_check_cache(key)` (may already exist)
  - `_call_llm_and_cache(prompt, key, ...)`

This makes the ordering explicit and the bug obvious.

STEP 3 — APPLY THE FIX
Reorder to: check cache FIRST, then increment quota, then call LLM.
  result = await _check_cache(cache_key)
  if result is not None:
      return result          # quota NOT incremented on hit
  await _increment_quota(namespace_id, conn)
  result = await _call_llm_and_cache(prompt, cache_key, provider)
  return result

Add a comment above the quota increment:
  # Quota is incremented only on cache miss, immediately before the LLM call.
  # Never increment on cache hit — see FIX-020.

STEP 4 — VERIFY
Trace the code path manually:
  - Cache hit path: confirm quota increment is NOT called.
  - Cache miss path: confirm quota increment IS called before LLM.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, find FIX-020 and update:
  dispatched: yes
  dispatched_by: W1-B
  completed: 2026-05-12
```

---

## WAVE 2 — P1 RLS / Data Integrity (After Wave 1, All Parallel)

---

### W2-A · FIX-025 · Composer 2 (Cursor)
**File:** `trimcp/orchestrators/memory.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing an RLS bypass in TriMCP (FIX-025, P1 MAJOR).
The `unredact_memory` function uses a raw `pool.acquire()` call, which skips
the `scoped_pg_session` context manager that sets the `trimcp.namespace_id`
PostgreSQL session variable required for Row-Level Security.

STEP 1 — READ FIRST
Read `trimcp/orchestrators/memory.py`. Find `unredact_memory`.
Also read `trimcp/db_utils.py` to understand the `scoped_pg_session` signature
(it takes pool + namespace_id as minimum args).

STEP 2 — CHECK CALLERS
Grep for all callers of `unredact_memory`:
  grep -rn "unredact_memory" trimcp/
Confirm that namespace_id is available at each call site. If it is NOT passed in,
add it as a required parameter (do not use a default of None — that would silently
bypass RLS, which is a smell: Fragility).

STEP 3 — APPLY THE FIX
Replace:
  async with pool.acquire() as conn:
With:
  async with scoped_pg_session(pool, namespace_id=namespace_id) as conn:

If namespace_id is not currently a parameter of unredact_memory, add it:
  async def unredact_memory(memory_id: UUID, namespace_id: UUID, pool: Pool) -> ...:

Update all callers to pass namespace_id.

STEP 4 — BOY SCOUT (SRP check)
While in this function: does `unredact_memory` do more than one thing?
If it fetches AND transforms AND writes, consider extracting named helpers.

STEP 5 — VERIFY
  grep -n "pool.acquire()" trimcp/orchestrators/memory.py
Confirm no raw pool.acquire() remains in unredact_memory.

STEP 6 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-025:
  dispatched: yes
  dispatched_by: W2-A
  completed: 2026-05-12
```

---

### W2-B · FIX-026 · Composer 2 (Cursor)
**File:** `trimcp/orchestrators/namespace.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing a WORM audit trail violation in TriMCP (FIX-026, P1 MAJOR).
The namespace `delete` method issues a `DELETE FROM event_log` which permanently
destroys the immutable audit trail. event_log is WORM (Write-Once, Read-Many).

STEP 1 — READ FIRST
Read `trimcp/orchestrators/namespace.py` in full.
Find the `delete` (or equivalent) method and locate the event_log DELETE.

STEP 2 — UNDERSTAND INTENT
Ask: why was event_log included in the deletion? Is it for GDPR right-to-erasure,
test teardown, or an oversight? If it is for GDPR, the correct pattern is
soft-deletion/pseudonymization, NOT hard delete of audit records.

STEP 3 — APPLY THE FIX
Remove the `DELETE FROM event_log` (and any `TRUNCATE event_log`) from the
namespace deletion path.

If the delete path MUST clean up event data (e.g. GDPR), replace the hard delete
with an archival step:
  await conn.execute(
      "INSERT INTO event_log_archive SELECT * FROM event_log WHERE namespace_id=$1",
      namespace_id
  )
  await conn.execute(
      "DELETE FROM event_log WHERE namespace_id=$1", namespace_id
  )
  # Archive table must exist — add migration if needed.

Add a guard so namespace deletion requires explicit intent:
  if not allow_audit_destruction:
      raise PermissionError(
          "Namespace deletion would destroy the WORM audit trail. "
          "Pass allow_audit_destruction=True only with explicit legal/compliance approval."
      )

Name the parameter clearly: `allow_audit_destruction: bool = False` (not `force=True`
— that name hides the consequence).

STEP 4 — VERIFY
  grep -n "DELETE.*event_log\|TRUNCATE.*event_log" trimcp/orchestrators/namespace.py
Confirm no unconditional DELETE on event_log remains.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-026:
  dispatched: yes
  dispatched_by: W2-B
  completed: 2026-05-12
```

---

### W2-C · FIX-027 · Gemini CLI / Gemini 3.1 Pro
**File:** `trimcp/garbage_collector.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing a false-orphan deletion bug in TriMCP (FIX-027, P1 MAJOR).
The garbage collector uses OFFSET-based pagination. Under concurrent inserts,
rows shift between pages: the GC skips records and incorrectly identifies live
memories as orphans, then deletes them.

STEP 1 — READ FIRST
Read `trimcp/garbage_collector.py` in full.
Find every occurrence of OFFSET in SQL queries (grep: `OFFSET`).
Note the current pagination pattern: likely `LIMIT $n OFFSET $page * $n`.

STEP 2 — UNDERSTAND THE BUG
OFFSET pagination on a live table is unsafe:
  Page 1: rows 1-100  →  row 50 gets inserted  →  Page 2 starts at row 101
  But the new insert shifted row 100 to page 2, and row 101 is now row 102.
  Row 100 is never seen → classified as orphan → deleted.

STEP 3 — APPLY THE FIX
Replace OFFSET pagination with keyset (cursor) pagination:

OLD pattern:
  SELECT id, ... FROM memories
  WHERE orphan_condition
  ORDER BY id
  LIMIT $batch_size OFFSET $page_offset

NEW pattern:
  SELECT id, ... FROM memories
  WHERE orphan_condition
    AND id > $last_seen_id      -- keyset cursor
  ORDER BY id
  LIMIT $batch_size

Track `last_seen_id` between iterations:
  last_seen_id = uuid('00000000-0000-0000-0000-000000000000')  # or min uuid
  while True:
      batch = await fetch_orphan_batch(conn, last_seen_id, batch_size)
      if not batch:
          break
      last_seen_id = batch[-1]['id']
      await delete_confirmed_orphans(conn, batch)

Extract the batch fetch into a named function: `_fetch_orphan_batch(conn, after_id, limit)`.
Extract the deletion into: `_delete_orphan_batch(conn, ids)`.
(SRP: two responsibilities → two functions.)

STEP 4 — VERIFY
  grep -n "OFFSET" trimcp/garbage_collector.py
Confirm no OFFSET remains in GC queries.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-027:
  dispatched: yes
  dispatched_by: W2-C
  completed: 2026-05-12
```

---

### W2-D · FIX-029 · Composer 2 (Cursor)
**File:** `trimcp/contradictions.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing a DB connection pool starvation bug in TriMCP (FIX-029, P1 MAJOR).
The `_resolve_with_llm` function (or equivalent) holds an open asyncpg connection
while making a 10–30s external LLM API call. Under concurrent contradiction
resolution, this exhausts the connection pool.

STEP 1 — READ FIRST
Read `trimcp/contradictions.py` in full.
Find `_resolve_with_llm` (or the function that calls the LLM provider).
Map exactly where the DB connection context manager (`async with ...`) is open
relative to the `provider.complete(...)` call.

STEP 2 — UNDERSTAND THE DEPENDENCY RULE
The database is an outer-layer detail (framework & driver layer). The LLM call
is also an outer-layer adapter. Business logic should orchestrate, not hold
resources across multiple I/O boundaries simultaneously.

STEP 3 — APPLY THE FIX
Split the function into three named phases (SRP per phase):

  async def _fetch_contradiction_context(conn, subject, predicate, object_) -> dict:
      """Phase 1: fetch data needed for resolution. Connection is released after."""
      return await conn.fetchrow(...)

  async def _resolve_contradiction_via_llm(context: dict, provider) -> str:
      """Phase 2: call LLM with no DB connection held. Pure I/O, no DB."""
      messages = _build_resolution_messages(context)
      result = await provider.complete(messages, ResolutionModel)
      return result.resolution

  async def _persist_resolution(conn, subject, predicate, object_, resolution: str):
      """Phase 3: write result. New connection acquired here."""
      await conn.execute("INSERT INTO ...", subject, predicate, object_, resolution)

Orchestrate from the caller:
  context = await _fetch_contradiction_context(conn, ...)
# conn context exits here — connection returned to pool
resolution = await _resolve_contradiction_via_llm(context, provider)
  async with scoped_pg_session(pool, namespace_id=ns_id) as conn2:
      await _persist_resolution(conn2, ..., resolution)

STEP 4 — VERIFY
Read the refactored function. Confirm:
  - No `provider.complete(...)` call appears inside a DB context manager.
  - Each of the three named functions has exactly one reason to change (SRP).

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-029:
  dispatched: yes
  dispatched_by: W2-D
  completed: 2026-05-12
```

---

## WAVE 3 — P1 Correctness / Performance (Parallel with Wave 2)

---

### W3-A · FIX-030 · Gemini CLI / Gemini 3.1 Pro
**File:** `trimcp/graph_query.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing an unbounded BFS traversal in TriMCP (FIX-030, P1 MAJOR).
The recursive CTE cycle guard uses `NOT EXISTS` referencing only the PostgreSQL
working table. For cyclic knowledge-graph nodes this produces infinite recursion.

STEP 1 — READ FIRST
Read `trimcp/graph_query.py` in full.
Find the `WITH RECURSIVE` CTE. Note its current structure: base case, recursive
case, and the cycle guard condition.

STEP 2 — UNDERSTAND THE BUG
PostgreSQL's working table only contains rows added in the current recursion step,
not the full accumulated path. `NOT EXISTS (SELECT 1 FROM working_table WHERE ...)` 
does NOT prevent cycles — it only prevents re-visiting within a single step.

STEP 3 — APPLY THE FIX
Add two defenses:

Defense A — Path accumulator (prevents cycles):
  Add a `path text[]` column that accumulates visited node labels.
  In the base case: `path := ARRAY[start_label]`
  In the recursive case: `path := traversal.path || e.target_label`
  Guard: `WHERE NOT e.target_label = ANY(traversal.path)`

Defense B — Depth limit (prevents runaway queries):
  Add a `depth integer` column.
  Base case: `depth := 0`
  Recursive case: `depth := traversal.depth + 1`
  Guard: `AND traversal.depth < 50`   -- adjust constant to project needs

Full revised CTE skeleton:
  WITH RECURSIVE traversal(node_label, depth, path) AS (
    SELECT $1::text, 0, ARRAY[$1::text]
    UNION ALL
    SELECT e.target_label,
           t.depth + 1,
           t.path || e.target_label
    FROM kg_edges e
    JOIN traversal t ON e.source_label = t.node_label
    WHERE NOT e.target_label = ANY(t.path)
      AND t.depth < 50
  )
  SELECT node_label FROM traversal;

STEP 4 — BOY SCOUT
While in graph_query.py: check for any other CTEs with similar cycle-guard issues.
Apply the same pattern if found.

STEP 5 — VERIFY
  grep -n "WITH RECURSIVE" trimcp/graph_query.py
Confirm every RECURSIVE CTE now has both `ANY(path)` and `depth <` guards.

STEP 6 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-030:
  dispatched: yes
  dispatched_by: W3-A
  completed: 2026-05-12
```

---

### W3-B · FIX-031 · Haiku 4.5 (VS Code)
**File:** `trimcp/graph_extractor.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing a performance bug in TriMCP (FIX-031, P1 MAJOR).
`spacy.load()` is called inside `_spacy_extract()` on every invocation,
reloading a 15MB model from disk on each KG extraction request.

STEP 1 — READ FIRST
Read `trimcp/graph_extractor.py`.
Find all calls to `spacy.load(...)`.

STEP 2 — APPLY THE FIX
Add a module-level cached loader (DIP: the function depends on the cached
abstraction, not the concrete spacy.load call every time):

  from functools import lru_cache

  @lru_cache(maxsize=1)
  def _get_spacy_model(model_name: str = "en_core_web_sm"):
      """Load and cache the spaCy model. Called once per process lifetime."""
      import spacy
      return spacy.load(model_name)

Replace every `spacy.load(...)` call in the file with `_get_spacy_model()`.

Name clarity (Uncle Bob): `_get_spacy_model` clearly states it returns a model,
is private (underscore prefix), and is a getter — not `_nlp` or `_model` which
hide what the cached object is.

STEP 3 — VERIFY
  grep -n "spacy.load" trimcp/graph_extractor.py
Confirm zero direct `spacy.load(` calls remain (only the one inside `_get_spacy_model`).

STEP 4 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-031:
  dispatched: yes
  dispatched_by: W3-B
  completed: 2026-05-12
```

---

### W3-C · FIX-032 · Composer 2 (Cursor)
**File:** `trimcp/providers/base.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing a shared singleton circuit breaker in TriMCP (FIX-032, P1 MAJOR).
`DEFAULT_CIRCUIT_BREAKER` is a module-level singleton shared by ALL LLMProvider
subclasses. When one provider trips the breaker (e.g., Anthropic rate-limit),
it blocks ALL other providers — a classic Fragility smell.

STEP 1 — READ FIRST
Read `trimcp/providers/base.py` in full.
Find `DEFAULT_CIRCUIT_BREAKER` and `execute_with_retry`.
Note which methods reference the module-level breaker vs `self._circuit_breaker`.

Also read `trimcp/providers/` to list all subclasses:
  grep -rn "class.*LLMProvider" trimcp/providers/

STEP 2 — UNDERSTAND THE SMELL
Module-level mutable singleton that is shared across instances = Fragility (a change
to one provider's state breaks all providers) + SRP violation (base.py has two reasons
to change: provider interface AND global circuit-breaker state).

STEP 3 — APPLY THE FIX
a. Remove or privatize `DEFAULT_CIRCUIT_BREAKER`.
b. In `LLMProvider.__init__`, add:
     self._circuit_breaker: CircuitBreaker = CircuitBreaker()
   (Each instance gets its own breaker — no cross-contamination.)
c. Change `execute_with_retry` to use `self._circuit_breaker` instead of the global.
d. If any subclass `__init__` currently overrides the breaker, ensure it calls
   `super().__init__()` first (Liskov: subtype must remain substitutable).

STEP 4 — VERIFY SUBCLASSES
For each provider subclass:
  - Does it call `super().__init__()` or pass through `**kwargs`? If yes, ✓.
  - Does it reference `DEFAULT_CIRCUIT_BREAKER` directly? If yes, fix it.
  grep -rn "DEFAULT_CIRCUIT_BREAKER" trimcp/

STEP 5 — VERIFY
  grep -n "DEFAULT_CIRCUIT_BREAKER" trimcp/providers/base.py
Should return zero or one line (the definition removed, or a deprecation comment).
  grep -rn "DEFAULT_CIRCUIT_BREAKER" trimcp/
Should return zero usage references.

STEP 6 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-032:
  dispatched: yes
  dispatched_by: W3-C
  completed: 2026-05-12
```

---

### W3-D · FIX-038 · Haiku 4.5 (VS Code)
**File:** `trimcp/schema.sql` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing a wrong ON CONFLICT target in TriMCP (FIX-038, P1 MAJOR).
The `kg_edges_old` migration at line ~274 of schema.sql uses a 3-column
ON CONFLICT clause, but the live unique constraint on the table is 4 columns
(includes namespace_id). The INSERT silently fails with a constraint error
instead of upserting correctly.

STEP 1 — READ FIRST
Read `trimcp/schema.sql` around line 274.
Find the INSERT ... ON CONFLICT for kg_edges_old.
Read the CREATE UNIQUE INDEX or UNIQUE CONSTRAINT for kg_edges to confirm
the exact columns in the 4-column constraint.

STEP 2 — APPLY THE FIX
Change:
  ON CONFLICT (subject_label, predicate, object_label) DO UPDATE ...
To:
  ON CONFLICT (subject_label, predicate, object_label, namespace_id) DO UPDATE ...

Verify the column order matches the actual UNIQUE constraint definition exactly.
PostgreSQL requires the ON CONFLICT target to match the constraint column order.

STEP 3 — ADD A COMMENT (Boy Scout)
Directly above the ON CONFLICT line, add:
  -- FIX-038: 4-column conflict target matches the unique constraint on kg_edges.
  -- Do not revert to 3-column; namespace_id is required for multi-tenant isolation.

STEP 4 — VERIFY
  grep -n "ON CONFLICT.*subject_label" trimcp/schema.sql
Confirm all occurrences include namespace_id in the target list.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-038:
  dispatched: yes
  dispatched_by: W3-D
  completed: 2026-05-12
```

---

### W3-E · FIX-039 · Haiku 4.5 (VS Code)
**Files:** `server.py`, `trimcp/admin_server.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are adding a production environment guard in TriMCP (FIX-039, P1 MAJOR).
`TRIMCP_ADMIN_OVERRIDE` is a dev shortcut with no guard preventing it from
being active in production, creating a silent auth bypass.

STEP 1 — READ FIRST
Read `server.py`. Search for all `TRIMCP_ADMIN_OVERRIDE` references.
Read `trimcp/admin_server.py`. Do the same.

STEP 2 — EXTRACT A NAMED GUARD FUNCTION (SRP)
Create a small, named function that encodes the policy. Do NOT inline the check
at every call site (DRY — Needless Repetition smell):

  def _assert_admin_override_not_in_production() -> None:
      """Raise at startup if TRIMCP_ADMIN_OVERRIDE is active in production.

      This guard prevents a development shortcut from silently bypassing
      authentication in production deployments. See FIX-039.
      """
      if os.getenv("TRIMCP_ADMIN_OVERRIDE") and os.getenv("ENVIRONMENT", "dev") == "prod":
          raise RuntimeError(
              "TRIMCP_ADMIN_OVERRIDE must not be set when ENVIRONMENT=prod. "
              "Remove this environment variable from the production configuration."
          )

STEP 3 — CALL AT STARTUP
Call `_assert_admin_override_not_in_production()` during application startup
(before the server begins accepting connections), in both server.py and
admin_server.py (or in a shared startup module if one exists).

STEP 4 — VERIFY
  grep -n "TRIMCP_ADMIN_OVERRIDE" server.py trimcp/admin_server.py
Confirm both files have either the guard call or import the shared guard.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-039:
  dispatched: yes
  dispatched_by: W3-E
  completed: 2026-05-12
```

---

### W3-F · FIX-040 · Gemini CLI / Gemini 3.1 Pro
**File:** `trimcp/orchestrators/migration.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing a TOCTOU race condition in TriMCP (FIX-040, P1 MAJOR).
`start_migration` checks for a running migration in one query, then inserts
in a second query. Two concurrent callers can both pass the check and create
two simultaneous active migrations.

STEP 1 — READ FIRST
Read `trimcp/orchestrators/migration.py` in full.
Find `start_migration` (or equivalent). Note the current check-then-insert pattern.

STEP 2 — UNDERSTAND TOCTOU
Time-of-check / time-of-use: the state can change between the SELECT (check)
and the INSERT (use). The fix is to make them atomic using a conditional INSERT.

STEP 3 — APPLY THE FIX
Replace the two-step check + insert with a single atomic conditional INSERT:

  async def _try_start_migration(
      conn, namespace_id: UUID, model: str, batch_size: int
  ) -> UUID | None:
      """Atomically create a new migration only if none is currently running.

      Returns the new migration id, or None if a migration is already active.
      This is a single SQL statement — no TOCTOU race.
      """
      row = await conn.fetchrow(
          """
          INSERT INTO embedding_migrations (namespace_id, model, batch_size, status, created_at)
          SELECT $1, $2, $3, 'running', now()
          WHERE NOT EXISTS (
              SELECT 1 FROM embedding_migrations
              WHERE namespace_id = $1
                AND status = 'running'
          )
          RETURNING id
          """,
          namespace_id, model, batch_size,
      )
      return row["id"] if row else None

Rename the public-facing method to clearly signal the conditional semantics:
  `start_migration` → `start_migration_if_not_running` (or keep name and add docstring).

STEP 4 — VERIFY
Read the refactored function. Confirm:
  - Single `conn.fetchrow` or `conn.execute` with INSERT ... WHERE NOT EXISTS.
  - No separate SELECT before the INSERT.
  - Returns None (not raises) when migration is already running.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-040:
  dispatched: yes
  dispatched_by: W3-F
  completed: 2026-05-12
```

---

### W3-G · FIX-041 · Composer 2 (Cursor)
**File:** `trimcp/replay.py` · **Priority:** P1 MAJOR

```
@uncle-bob-craft

You are fixing a long-held database transaction in TriMCP (FIX-041, P1 MAJOR).
An LLM API call (external I/O, 10–30s) is made while a REPEATABLE READ cursor
transaction is held open. This blocks PostgreSQL autovacuum and causes pool
starvation during replay operations.

STEP 1 — READ FIRST
Read `trimcp/replay.py` in full.
Find the REPEATABLE READ transaction (look for isolation_level, REPEATABLE READ,
or BEGIN ISOLATION LEVEL). Map exactly:
  a. Where the cursor/transaction is opened.
  b. Where the LLM call (`provider.complete`) is made.
  c. Where the transaction is committed/closed.

STEP 2 — UNDERSTAND THE RULE
Never hold a database transaction open across external network I/O.
Transactions are DB-layer resources; LLM calls are external adapter calls.
They must not be nested. (Dependency Rule: DB and LLM are both outer-layer
adapters — mixing their lifecycles creates Fragility.)

STEP 3 — APPLY THE FIX
Extract into three clearly-named phases:

  async def _fetch_replay_event_batch(conn, cursor_pos, batch_size) -> list[dict]:
      """Phase 1: read events inside REPEATABLE READ. Returns list of dicts."""
      ...

  async def _process_events_with_llm(events: list[dict], provider) -> list[ReplayResult]:
      """Phase 2: call LLM for each event. No DB connection held. Pure I/O."""
      ...

  async def _persist_replay_results(conn, results: list[ReplayResult]) -> None:
      """Phase 3: write results in a new transaction."""
      ...

Orchestrate:
  # Phase 1 — read batch (connection held briefly)
  async with scoped_pg_session(pool, namespace_id=ns_id) as conn:
      events = await _fetch_replay_event_batch(conn, cursor_pos, batch_size)
  # Phase 2 — LLM processing (NO connection held, can take 10–30s)
  results = await _process_events_with_llm(events, provider)
  # Phase 3 — write results (new short-lived connection)
  async with scoped_pg_session(pool, namespace_id=ns_id) as conn:
      await _persist_replay_results(conn, results)

STEP 4 — VERIFY
Read the refactored replay loop. Confirm no `provider.complete(...)` call
appears inside a DB context manager (async with ... as conn: block).

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-041:
  dispatched: yes
  dispatched_by: W3-G
  completed: 2026-05-12
```

---

## WAVE 4 — P2 Operational Quality (Parallel with Waves 2+3)

---

### W4-A · FIX-051 · Haiku 4.5 (VS Code)
**File:** `trimcp/ast_parser.py` · **Priority:** P2 MINOR

```
@uncle-bob-craft

You are adding a recursion depth limit in TriMCP (FIX-051, P2 MINOR).
`_walk()` (or equivalent recursive AST traversal) has no depth limit,
causing RecursionError on deeply nested auto-generated code.

STEP 1 — READ FIRST
Read `trimcp/ast_parser.py`. Find the recursive `_walk` function.

STEP 2 — APPLY THE FIX
Add an explicit depth parameter with a named constant (not a magic number):

  _MAX_AST_DEPTH = 200  # protects against RecursionError on generated code

  def _walk(node: ast.AST, depth: int = 0) -> Iterator[ast.AST]:
      """Walk an AST node tree up to _MAX_AST_DEPTH levels deep."""
      if depth > _MAX_AST_DEPTH:
          return
      yield node
      for child in ast.iter_child_nodes(node):
          yield from _walk(child, depth + 1)

Name the constant `_MAX_AST_DEPTH` — a magic `200` inline is Opacity (Uncle Bob smell).

STEP 3 — VERIFY
  grep -n "_walk\|_MAX_AST_DEPTH" trimcp/ast_parser.py
Confirm the depth parameter and constant are present.

STEP 4 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-051:
  dispatched: yes
  dispatched_by: W4-A
  completed: 2026-05-12
```

---

### W4-B · FIX-052 · Haiku 4.5 (VS Code)
**File:** `trimcp/notifications.py` · **Priority:** P2 MINOR

```
@uncle-bob-craft

You are fixing insecure SMTP configuration in TriMCP (FIX-052, P2 MINOR).
The notification module uses hardcoded placeholder emails (admin@example.com)
and sends on port 25 (unencrypted).

STEP 1 — READ FIRST
Read `trimcp/notifications.py`. Note the current SMTP host, port, From, and To.

STEP 2 — APPLY THE FIX

a. Replace hardcoded addresses with env var reads:
   SMTP_FROM = os.environ.get("TRIMCP_SMTP_FROM", "")
   SMTP_TO   = os.environ.get("TRIMCP_SMTP_TO", "")
   if not SMTP_FROM or not SMTP_TO:
       raise ValueError(
           "TRIMCP_SMTP_FROM and TRIMCP_SMTP_TO must be set. "
           "No example.com defaults permitted."
       )

b. Switch from port 25 to STARTTLS on 587:
   await aiosmtplib.send(
       message,
       hostname=smtp_host,
       port=587,
       use_tls=False,
       start_tls=True,
       username=smtp_user,
       password=smtp_password,
   )

STEP 3 — NAMING (Uncle Bob)
Extract a `_build_smtp_config()` function that reads env vars and validates them.
This separates configuration reading (outer-layer concern) from message sending
(use-case concern). Do NOT inline the `os.environ.get` calls inside the send path.

STEP 4 — VERIFY
  grep -n "example.com\|port.*25\b" trimcp/notifications.py
Confirm no example.com addresses and no plain port 25 remain.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-052:
  dispatched: yes
  dispatched_by: W4-B
  completed: 2026-05-12
```

---

### W4-C · FIX-053 · Haiku 4.5 (VS Code)
**File:** `trimcp/openvino_npu_export.py` · **Priority:** P2 MINOR

```
@uncle-bob-craft

You are hardening a trust_remote_code risk in TriMCP (FIX-053, P2 MINOR).
`AutoTokenizer.from_pretrained(..., trust_remote_code=True)` executes arbitrary
Python code from Hugging Face Hub model repos. If the model is not pinned to a
known-good revision hash, a malicious update to the Hub repo executes on load.

STEP 1 — READ FIRST
Read `trimcp/openvino_npu_export.py`. Find the `AutoTokenizer.from_pretrained` call.
Note the current `revision` argument (or absence of one).

STEP 2 — APPLY THE FIX

a. Add a revision pin (OCP: open to model updates via config, closed to arbitrary
   remote code execution by default):
   OPENVINO_MODEL_REVISION = os.environ.get("TRIMCP_OPENVINO_MODEL_REVISION", "")

b. Guard and warn:
   if trust_remote_code and not OPENVINO_MODEL_REVISION:
       log.warning(
           "trust_remote_code=True is set but TRIMCP_OPENVINO_MODEL_REVISION is not pinned. "
           "This allows arbitrary code execution from the Hub model repo. "
           "Set TRIMCP_OPENVINO_MODEL_REVISION to a commit SHA to pin the model. "
           "See FIX-053."
       )

c. Pass revision to from_pretrained:
   AutoTokenizer.from_pretrained(
       model_name,
       trust_remote_code=trust_remote_code,
       revision=OPENVINO_MODEL_REVISION or None,
   )

STEP 3 — VERIFY
  grep -n "trust_remote_code\|from_pretrained" trimcp/openvino_npu_export.py
Confirm the warning and revision-pin logic are present.

STEP 4 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-053:
  dispatched: yes
  dispatched_by: W4-C
  completed: 2026-05-12
```

---

### W4-D · FIX-054 + FIX-055 · Google Antigravity / Gemini 3 Flash
**File:** `trimcp/schema.sql` · **Priority:** P2 MINOR (two items, same file)

```
@uncle-bob-craft

You are making two small schema fixes in TriMCP (FIX-054 + FIX-055, P2 MINOR).
Both changes are in `trimcp/schema.sql`. Do them in a single pass.

STEP 1 — READ FIRST
Read `trimcp/schema.sql`.
Find:
  a. The `pii_redactions` table — note the existing indexes.
  b. The `kg_node_embeddings` table — note the RLS ENABLE statement and any
     associated policies.

--- FIX-054: Add missing index on pii_redactions.namespace_id ---

After the `CREATE TABLE pii_redactions` definition (or at the bottom of the
schema's index section), add:

  -- FIX-054: namespace-scoped PII queries require this index to avoid full partition scans.
  CREATE INDEX IF NOT EXISTS idx_pii_redactions_namespace_id
      ON pii_redactions (namespace_id);

--- FIX-055: Fix kg_node_embeddings — RLS enabled, no policy defined ---

Option A (preferred): add namespace_id to kg_node_embeddings and create a policy:
  ALTER TABLE kg_node_embeddings ADD COLUMN IF NOT EXISTS namespace_id UUID;
  CREATE POLICY kg_node_embeddings_ns_isolation
      ON kg_node_embeddings FOR ALL
      USING (namespace_id = current_setting('trimcp.namespace_id', true)::uuid);

Option B (if embeddings are intentionally global/shared across namespaces):
  -- FIX-055: kg_node_embeddings are global (not namespace-scoped).
  -- Disabling RLS is intentional; the table has no namespace_id column.
  ALTER TABLE kg_node_embeddings DISABLE ROW LEVEL SECURITY;

READ the table definition carefully before choosing Option A or B.
If the table already has a namespace_id column → use Option A.
If the table has no namespace_id and no plans to add one → use Option B with comment.

STEP 2 — VERIFY
  grep -n "pii_redactions\|kg_node_embeddings" trimcp/schema.sql
Confirm:
  - idx_pii_redactions_namespace_id is present.
  - kg_node_embeddings either has a matching RLS policy OR has RLS explicitly disabled
    with a comment explaining why.

STEP 3 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-054 AND FIX-055:
  dispatched: yes
  dispatched_by: W4-D
  completed: 2026-05-12
```

---

### W4-E · FIX-057 · Gemini CLI / Gemini 3.1 Pro
**File:** `trimcp-infra/aws/modules/fargate-worker/main.tf` · **Priority:** P2 MINOR

```
@uncle-bob-craft

You are adding ECS autoscaling to TriMCP (FIX-057, P2 MINOR).
The Fargate worker services have no autoscaling configured, so queue backlog
has no automatic relief.

STEP 1 — READ FIRST
Read `trimcp-infra/aws/modules/fargate-worker/main.tf` in full.
Note the ECS service names, cluster ARN references, and any existing capacity
provider or scaling configuration.

STEP 2 — APPLY THE FIX
Add autoscaling resources to the Terraform module. Use a named pattern —
not magic numbers inline (Uncle Bob: Opacity smell):

  locals {
    worker_min_capacity = 1
    worker_max_capacity = 10
    scale_out_cpu_threshold = 70
    scale_in_cpu_threshold  = 30
  }

  resource "aws_appautoscaling_target" "worker" {
    max_capacity       = local.worker_max_capacity
    min_capacity       = local.worker_min_capacity
    resource_id        = "service/${var.ecs_cluster_name}/${aws_ecs_service.worker.name}"
    scalable_dimension = "ecs:service:DesiredCount"
    service_namespace  = "ecs"
  }

  resource "aws_appautoscaling_policy" "worker_scale_out" {
    name               = "${local.name}-scale-out"
    policy_type        = "StepScaling"
    resource_id        = aws_appautoscaling_target.worker.resource_id
    scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
    service_namespace  = aws_appautoscaling_target.worker.service_namespace

    step_scaling_policy_configuration {
      adjustment_type         = "ChangeInCapacity"
      cooldown                = 60
      metric_aggregation_type = "Average"
      step_adjustment {
        scaling_adjustment          = 2
        metric_interval_lower_bound = 0
      }
    }
  }

  resource "aws_appautoscaling_policy" "worker_scale_in" {
    name               = "${local.name}-scale-in"
    policy_type        = "StepScaling"
    resource_id        = aws_appautoscaling_target.worker.resource_id
    scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
    service_namespace  = aws_appautoscaling_target.worker.service_namespace

    step_scaling_policy_configuration {
      adjustment_type         = "ChangeInCapacity"
      cooldown                = 300
      metric_aggregation_type = "Average"
      step_adjustment {
        scaling_adjustment          = -1
        metric_interval_upper_bound = 0
      }
    }
  }

Also add the CloudWatch alarms that trigger the policies (scale-out on CPU > 70%,
scale-in on CPU < 30%). Use aws_cloudwatch_metric_alarm resources.

STEP 3 — EXPOSE VARIABLES
Add the new locals as input variables if this module is called from a root module,
so capacity limits can be overridden per environment without editing the module.

STEP 4 — VERIFY
  grep -n "appautoscaling" trimcp-infra/aws/modules/fargate-worker/main.tf
Confirm appautoscaling_target, scale_out, and scale_in resources are present.

STEP 5 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-057:
  dispatched: yes
  dispatched_by: W4-E
  completed: 2026-05-12
```

---

### W4-F · FIX-046 · Composer 2 (Cursor)
**Files:** `trimcp-launch/` (Go project) · **Priority:** P2 MAJOR (partial)

```
@uncle-bob-craft

You are investigating and fixing Go signal forwarding in TriMCP (FIX-046, P2 MAJOR).
We confirmed that `rootctx_unix.go` correctly captures SIGINT and SIGTERM via
`signal.NotifyContext`. However, the `launch.Run` function (from an internal package)
that manages the Python child process was not in the repo — we cannot confirm
it forwards SIGTERM to the child.

This is a READ-FIRST investigation; the fix depends on what you find.

STEP 1 — READ THE LAUNCH PACKAGE
Read all Go files under `trimcp-launch/`:
  - cmd/trimcp-launch/main.go
  - cmd/trimcp-launch/rootctx_unix.go
  - Any internal/launch/ or pkg/launch/ package directories

Search for the launch.Run implementation:
  grep -rn "func Run\|cmd.Process\|Signal\|syscall.SIGTERM" trimcp-launch/

STEP 2 — EVALUATE: DOES IT FORWARD SIGTERM?
Look for `cmd.Process.Signal(syscall.SIGTERM)` or equivalent in the context
cancellation handler. Three outcomes:

  Outcome A — SIGTERM IS forwarded:
    Add a comment in rootctx_unix.go confirming verified:
      // VERIFIED FIX-046: launch.Run forwards ctx cancellation as SIGTERM to child.
    No code change needed. Update todo as completed.

  Outcome B — SIGTERM IS NOT forwarded (context cancellation only kills Go side):
    Add explicit forwarding in the context cancellation handler:
      go func() {
          <-ctx.Done()
          if cmd.Process != nil {
              _ = cmd.Process.Signal(syscall.SIGTERM)
          }
      }()

  Outcome C — launch package not found / cannot determine:
    Add a TODO with a clear owner note (Uncle Bob: professional honesty):
      // TODO(FIX-046): Cannot verify SIGTERM forwarding to Python child without
      // launch package source. If graceful shutdown is required, verify
      // launch.Run calls cmd.Process.Signal(syscall.SIGTERM) on ctx.Done().
    Update todo as partial.

STEP 3 — VERIFY (for Outcome B)
Build the Go binary (if Go toolchain available):
  cd trimcp-launch && go build ./...
Confirm no compilation errors.

STEP 4 — UPDATE TODO
In `to-do-v1-phase6.md`, update FIX-046:
  dispatched: yes
  dispatched_by: W4-F
  completed: 2026-05-12   (or: partial — see Outcome C)
```

---

## Summary Checklist

| Wave | ID | Tool | File | SRP scope |
|------|----|------|------|-----------|
| W1-A | FIX-013 | Haiku | config.py | credential default + validator |
| W1-B | FIX-020 | Composer | server.py | quota ordering |
| W2-A | FIX-025 | Composer | memory.py | scoped_pg_session in unredact |
| W2-B | FIX-026 | Composer | namespace.py | remove event_log DELETE |
| W2-C | FIX-027 | Gemini Pro | garbage_collector.py | keyset pagination |
| W2-D | FIX-029 | Composer | contradictions.py | release conn before LLM |
| W3-A | FIX-030 | Gemini Pro | graph_query.py | BFS path array + depth cap |
| W3-B | FIX-031 | Haiku | graph_extractor.py | lru_cache spacy model |
| W3-C | FIX-032 | Composer | providers/base.py | per-instance circuit breaker |
| W3-D | FIX-038 | Haiku | schema.sql | 4-col ON CONFLICT |
| W3-E | FIX-039 | Haiku | server.py + admin_server | prod override guard |
| W3-F | FIX-040 | Gemini Pro | migration.py | atomic INSERT |
| W3-G | FIX-041 | Composer | replay.py | LLM outside transaction |
| W4-A | FIX-051 | Haiku | ast_parser.py | depth constant |
| W4-B | FIX-052 | Haiku | notifications.py | SMTP TLS port |
| W4-C | FIX-053 | Haiku | openvino_npu_export.py | revision pin + warning |
| W4-D | FIX-054+055 | Flash | schema.sql | index + RLS policy |
| W4-E | FIX-057 | Gemini Pro | fargate-worker/main.tf | ECS autoscaling |
| W4-F | FIX-046 | Composer | trimcp-launch (Go) | signal forwarding audit |

**Total:** 19 prompts · 4 waves · 19 FIX items closed
**Rounds with 4 tools:** 7 rounds to completion
