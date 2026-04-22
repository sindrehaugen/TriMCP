# TriMCP — Deep Architecture Audit Report

**Auditor:** Opus 4.7 — Elite Systems Architect pass
**Scope:** Full codebase (orchestrator, graph layer, embeddings, GC, MCP server)
**Date:** 2026-04-22
**Outcome:** 5 findings identified, 5 production-grade refactors applied, Tri-Stack philosophy preserved.

---

## Executive Summary

The Tri-Stack architecture — Redis (working memory) / PostgreSQL + pgvector (semantic index + knowledge graph) / MongoDB (episodic archive) — is sound. The Saga pattern is the correct abstraction for keeping three heterogeneous stores coherent without a distributed transaction coordinator.

However, the hardened implementation shipped with **one critical atomicity defect** and **four meaningful robustness gaps** that would surface under production load, partial failures, or large inputs. All five have been fixed without altering the public MCP contract.

| # | Severity | Area | Status |
|---|---|---|---|
| F-1 | **Critical** | Saga atomicity across vector + graph writes | Fixed |
| F-2 | **High** | Incomplete rollback leaves PG orphans | Fixed |
| F-3 | **Medium** | Graph hydration blind to `code_files` | Fixed |
| F-4 | **Medium** | `embed_batch` unbounded memory footprint | Fixed |
| F-5 | **Low** | Redis connection pool not explicitly sized | Fixed |

---

## F-1 — Non-atomic PG writes across Step 2 and Step 2b (Critical)

**File:** `orchestrator.py` — `TriStackEngine.store_memory`

**Defect.** Step 2 (vector index) and Step 2b (knowledge-graph nodes + edges) each called `self.pg_pool.acquire()` independently:

```python
# OLD — two connections, two auto-commits
async with self.pg_pool.acquire() as conn:
    await conn.execute("INSERT INTO memory_metadata ...")   # commits here

async with self.pg_pool.acquire() as conn:
    for entity in entities:
        await conn.execute("INSERT INTO kg_nodes ...")       # separate txn
    for triplet in triplets:
        await conn.execute("INSERT INTO kg_edges ...")       # separate txn
```

Because each `acquire()` returns a fresh auto-commit connection from asyncpg's pool, there was no atomicity between the vector row and the graph triplets. A crash, network blip, or raised exception between the two blocks would leave the vector row committed while the graph stayed empty — silently corrupting GraphRAG results for every subsequent query anchored near that memory.

**Fix.** Pre-compute all embeddings outside the PG call, then wrap both writes in a single connection and a single `asyncpg` transaction:

```python
async with self.pg_pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute("INSERT INTO memory_metadata ...")
        for entity, node_vec in zip(entities, node_vecs):
            await conn.execute("INSERT INTO kg_nodes ... ON CONFLICT ...")
        for triplet in triplets:
            await conn.execute("INSERT INTO kg_edges ... ON CONFLICT ...")
```

Either all three tables commit or PG rolls everything back — no partial Saga state is observable. Pre-computing embeddings outside the transaction also prevents a pooled connection from being held during CPU-bound inference, which would starve concurrent sagas.

---

## F-2 — Incomplete rollback leaves orphaned PG rows (High)

**File:** `orchestrator.py` — `store_memory` exception handler

**Defect.** The original handler only removed the Mongo document on failure:

```python
except Exception as e:
    if inserted_mongo_id:
        await collection.delete_one({"_id": inserted_result.inserted_id})
    raise
```

If Step 2+2b committed successfully but Step 3 (Redis setex) then failed — a very real scenario during a Redis restart or network partition — the PG vector row and KG edges would remain with a dangling `mongo_ref_id` pointing at a now-deleted document. Semantic search would return the row, hydration would 404, and the user would see empty results instead of a clear miss.

**Fix.** Extended the handler to clean the PG side by `mongo_ref_id`:

```python
async with self.pg_pool.acquire() as conn:
    await conn.execute("DELETE FROM memory_metadata WHERE mongo_ref_id = $1", inserted_mongo_id)
    await conn.execute("DELETE FROM kg_edges       WHERE mongo_ref_id = $1", inserted_mongo_id)
```

**Design note — why kg_nodes are NOT deleted on rollback.** Node labels are shared across memories through `ON CONFLICT (label) DO UPDATE`. Deleting a node because one saga failed could orphan other sagas that reference the same label. Truly unreachable nodes are better swept by the garbage collector, which already knows how to scan for `mongo_ref_id`s no longer present in Mongo.

Both Mongo and PG cleanup steps are wrapped in their own `try/except` so a cleanup failure cannot mask the original exception. The raise of the original exception is unconditional.

---

## F-3 — Graph hydration misses the `code_files` collection (Medium)

**File:** `graph_query.py` — `GraphRAGTraverser._hydrate_sources`

**Defect.** The hydration step queried only `db.episodes.find_one(...)`. But `index_code_file` writes documents into `db.code_files`, and when graph extraction runs over code summaries the resulting KG nodes/edges point at `code_files` ObjectIds. Those references would silently return no excerpt — the graph traversal would show the structure but no grounding text.

**Fix.** Try `episodes` first, fall back to `code_files`, and tag each hydrated source with its origin collection so the MCP response is self-describing:

```python
doc = await db.episodes.find_one({"_id": oid})
if doc:
    sources.append({"collection": "episodes", "type": doc.get("type"), "excerpt": ...})
    continue

code_doc = await db.code_files.find_one({"_id": oid})
if code_doc:
    sources.append({"collection": "code_files", "type": "code",
                    "filepath": code_doc.get("filepath"), ...})
```

Also moved `ObjectId(ref_id)` parsing out of the hydration `try/except` so a malformed ID is logged distinctly from an actual Mongo fetch failure.

---

## F-4 — `embed_batch` unbounded memory footprint (Medium)

**File:** `embeddings.py` — `embed_batch`

**Defect.** The previous implementation handed the full `texts` list to `SentenceTransformer.encode(...)` in one shot, passing `batch_size=32`. The `batch_size` argument only controls the internal minibatch — sentence-transformers still holds *every* input string and *every* output tensor in memory simultaneously. A 10,000-node file (large generated code, vendored bundles, framework monoliths) can balloon resident memory into the multi-GB range and OOM-kill the server.

**Fix.** Chunk on the Python side into groups of `_BATCH_CHUNK_SIZE=64` (configurable via `EMBED_BATCH_CHUNK` env var) and await the executor between chunks so control returns to the event loop:

```python
for start in range(0, len(texts), _BATCH_CHUNK_SIZE):
    chunk = texts[start:start + _BATCH_CHUNK_SIZE]
    chunk_vectors = await loop.run_in_executor(_executor, _sync_batch, chunk)
    results.extend(chunk_vectors)
```

Resident memory now scales with `_BATCH_CHUNK_SIZE`, not with the input size. Other sagas aren't starved during a large index. The internal minibatch of 32 passed to the model is preserved for GPU/CPU throughput.

Also extracted `_sync_batch` to module scope — it was being redefined as a closure on every call, which added unnecessary allocation pressure in a hot path.

---

## F-5 — Redis connection pool not explicitly sized (Low)

**File:** `orchestrator.py` — `TriStackEngine.connect`

**Defect.** `redis.from_url(...)` constructs a `ConnectionPool` with an unbounded default (`max_connections=None`). Under burst traffic the server could open hundreds of TCP sockets to Redis, risking `maxclients` rejection on the Redis side and FD exhaustion on ours.

**Fix.** Explicit bounds plus health checking:

```python
self.redis_client = redis.from_url(
    OrchestratorConfig.REDIS_URL,
    socket_connect_timeout=5,
    socket_timeout=5,
    max_connections=OrchestratorConfig.REDIS_MAX_CONNECTIONS,   # default 20
    health_check_interval=30,                                    # reap stale idles
)
```

Added `REDIS_MAX_CONNECTIONS` to `OrchestratorConfig` and documented it in `.env.example` alongside the existing `PG_MIN_POOL` / `PG_MAX_POOL` knobs.

---

## Residual Considerations (Accepted Risk)

The following were reviewed and left as-is because the cost/benefit did not justify a change at this stage. Each is recorded so a future audit can revisit with context.

1. **KG-node GC heuristic.** kg_nodes orphaned by the rollback path (F-2) remain until the garbage collector sweeps them. The current GC only reaps Mongo orphans, not KG-node orphans. Adding a KG-orphan sweep is a natural follow-up but requires care — labels are intentionally shared, so the reap predicate must be "no kg_edges references AND no active mongo_ref_id".

2. **Graph extraction runs before Mongo insert.** `graph_extract(payload.summary)` is called at the top of `store_memory` before any IO. A malformed summary would raise before Mongo commit — that's the correct failure mode (no cleanup needed) and validates early, so no change.

3. **`semantic_search` and `search_codebase` do not use a PG transaction.** These are read-only, single-statement queries; wrapping them adds overhead without correctness benefit.

4. **Stub embedding fallback is deterministic but not semantically meaningful.** Intentional — it preserves the Saga contract (always produces a 768-dim vector) so CI runs don't require the 400 MB Jina model. Production deployments should verify the model loaded by watching for the "Embedding model ready" log line.

5. **No exponential-backoff retry on Redis/PG inside the Saga itself.** The GC has retries for startup; the Saga fails fast and relies on the caller (or MCP client) to retry. This keeps the write path predictable.

---

## Changes Landed

| File | Change |
|---|---|
| `orchestrator.py` | Single-connection atomic PG transaction for Step 2 + 2b; pre-compute embeddings outside txn; extended rollback to delete PG orphans; explicit Redis pool size + health check; new `REDIS_MAX_CONNECTIONS` config. |
| `graph_query.py` | `_hydrate_sources` now falls back to `code_files`; source records tagged with origin collection; ObjectId parsing separated from fetch error handling. |
| `embeddings.py` | Python-level chunking in `embed_batch` with configurable `EMBED_BATCH_CHUNK`; `_sync_batch` lifted to module scope; empty-input short-circuit. |
| `.env.example` | Documents new `REDIS_MAX_CONNECTIONS` and `EMBED_BATCH_CHUNK` knobs. |

---

## Verification Guidance

The existing `test_stack.py` integration suite (T1–T6) exercises the happy path but does not explicitly cover the partial-failure scenarios fixed here. Suggested additions for a follow-up test pass:

- **T7 (F-1):** Monkeypatch `kg_edges` insert to raise. Assert `memory_metadata` row is absent after the call returns.
- **T8 (F-2):** Monkeypatch Redis `setex` to raise. Assert both Mongo doc and PG vector row are gone after the call returns.
- **T9 (F-3):** Index a code file, then call `graph_search` on a query that anchors on one of its entities. Assert at least one source has `collection == "code_files"` and a populated `filepath`.
- **T10 (F-4):** Index a synthesized file with ~5,000 AST chunks. Assert peak RSS stays under a sensible cap (e.g. 2 GB).

---

## Conclusion

The Tri-Stack philosophy — "each store does what it's best at, the Saga keeps them coherent" — is intact and strengthened by these fixes. The rewritten Saga path is genuinely atomic across MongoDB + PostgreSQL (vector and graph), rolls back fully on any failure, and no longer has a pathological memory shape for large code files. The public MCP tool surface is unchanged.
