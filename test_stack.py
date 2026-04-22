"""
Phase 6 — End-to-End Validation
Runs 6 test cases against live Docker containers. No mocks.
Exits 0 on full pass, 1 on any failure.

Usage:
    python test_stack.py

Prerequisites:
    docker compose up -d   (all three containers must be healthy)
    pip install -r requirements.txt
"""
import asyncio
import sys
import traceback
from textwrap import dedent

from orchestrator import MemoryPayload, TriStackEngine

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
HEAD = "\033[94m{}\033[0m"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    icon = PASS if ok else FAIL
    print(f"{icon}  {name}" + (f"\n        {detail}" if detail and not ok else ""))


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

async def t1_store_and_recall(engine: TriStackEngine):
    """store_memory → get_recent_context (Redis hit)"""
    payload = MemoryPayload(
        user_id="test_user",
        session_id="t1",
        content_type="chat",
        summary="TriMCP uses Redis as working memory for sub-millisecond recall.",
        heavy_payload="Full conversation transcript placeholder for test T1.",
    )
    mongo_id = await engine.store_memory(payload)
    assert mongo_id, "No mongo_id returned"

    cached = await engine.recall_memory("test_user", "t1")
    assert cached == payload.summary, f"Cache mismatch: {cached!r}"
    record("T1: store_memory + recall (Redis hit)", True)


async def t2_semantic_search(engine: TriStackEngine):
    """semantic_search returns stored document"""
    import time
    user_id = f"test_user_t2_{int(time.time())}"   # unique per run — clean search space
    # heavy_payload is what Mongo stores as raw_data — must contain the search term
    payload = MemoryPayload(
        user_id=user_id,
        session_id="t2",
        content_type="chat",
        summary="PostgreSQL pgvector stores 768-dimensional cosine embeddings.",
        heavy_payload="Full transcript: pgvector enables cosine similarity search on 768-dim vectors.",
    )
    await engine.store_memory(payload)

    results_sr = await engine.semantic_search(user_id, "vector database embeddings", top_k=3)
    assert len(results_sr) > 0, "No results returned"
    # With a single document in scope, top result must be the T2 document
    assert "pgvector" in str(results_sr[0].get("raw_data", "")), \
        f"Expected pgvector in top result, got: {results_sr[0].get('raw_data', '')!r}"
    record("T2: semantic_search returns relevant document", True)


async def t3_index_and_search_code(engine: TriStackEngine):
    """index_code_file + search_codebase finds the function"""
    import time
    run_id = str(int(time.time()))   # unique filepath per run — defeats Redis hash cache
    sample_code = dedent("""\
        def calculate_embedding_distance(vec_a, vec_b):
            \"\"\"Compute cosine distance between two vectors.\"\"\"
            dot = sum(a * b for a, b in zip(vec_a, vec_b))
            mag_a = sum(a ** 2 for a in vec_a) ** 0.5
            mag_b = sum(b ** 2 for b in vec_b) ** 0.5
            return 1.0 - (dot / (mag_a * mag_b + 1e-9))

        class VectorStore:
            def __init__(self):
                self.vectors = []

            def add(self, vec):
                self.vectors.append(vec)
    """)

    result = await engine.index_code_file(
        filepath=f"test_fixtures/vector_utils_{run_id}.py",
        raw_code=sample_code,
        language="python",
    )
    assert result["status"] == "indexed", f"Unexpected status: {result}"
    assert result["chunks"] >= 2, f"Expected >=2 chunks, got {result['chunks']}"

    code_results = await engine.search_codebase("cosine distance between vectors", top_k=3)
    assert len(code_results) > 0, "No code results returned"
    assert any("calculate_embedding_distance" in r.get("name", "") for r in code_results), \
        f"Function not found in results: {[r.get('name') for r in code_results]}"
    record("T3: index_code_file + search_codebase finds function", True)


async def t4_change_detection(engine: TriStackEngine):
    """Re-indexing unchanged file returns status=skipped"""
    code = "def noop(): pass\n"
    fp = "test_fixtures/noop.py"
    await engine.index_code_file(filepath=fp, raw_code=code, language="python")
    result2 = await engine.index_code_file(filepath=fp, raw_code=code, language="python")
    assert result2["status"] == "skipped", f"Expected skipped, got: {result2}"
    record("T4: unchanged file re-index is skipped (hash check)", True)


async def t5_graph_search(engine: TriStackEngine):
    """store_memory extracts KG entities; graph_search returns a subgraph"""
    payload = MemoryPayload(
        user_id="test_user",
        session_id="t5",
        content_type="chat",
        summary="MongoDB stores raw data. Redis connects to the cache layer.",
        heavy_payload="Heavy payload for T5.",
    )
    await engine.store_memory(payload)

    subgraph = await engine.graph_search("MongoDB storage", max_depth=2)
    assert "nodes" in subgraph, "No nodes key in subgraph"
    assert "edges" in subgraph, "No edges key in subgraph"
    assert len(subgraph["nodes"]) > 0, "Subgraph has no nodes"
    record("T5: graph_search returns non-empty subgraph", True)


async def t6_rollback(engine: TriStackEngine):
    """Forcing a PG failure must leave MongoDB clean"""
    from motor.motor_asyncio import AsyncIOMotorClient
    import os

    db = AsyncIOMotorClient(os.getenv("MONGO_URI", "mongodb://localhost:27017")).memory_archive
    before_count = await db.episodes.count_documents({})

    # Corrupt the PG pool reference so Step 2 raises AttributeError
    real_pool = engine.pg_pool
    engine.pg_pool = None
    try:
        await engine.store_memory(MemoryPayload(
            user_id="rollback_user",
            session_id="t6",
            content_type="chat",
            summary="This write must be rolled back.",
            heavy_payload="Rollback test payload.",
        ))
        record("T6: rollback on PG failure", False, "Exception was NOT raised — rollback did not trigger")
        return
    except Exception:
        pass
    finally:
        engine.pg_pool = real_pool

    after_count = await db.episodes.count_documents({})
    assert after_count == before_count, \
        f"MongoDB grew by {after_count - before_count} — orphan NOT cleaned up"
    record("T6: rollback on PG failure — Mongo stays clean", True)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [t1_store_and_recall, t2_semantic_search, t3_index_and_search_code,
         t4_change_detection, t5_graph_search, t6_rollback]


async def main():
    print(HEAD.format("\n=== TriMCP End-to-End Validation ===\n"))
    engine = TriStackEngine()
    await engine.connect()

    for test_fn in TESTS:
        try:
            await test_fn(engine)
        except AssertionError as e:
            record(test_fn.__doc__ or test_fn.__name__, False, str(e))
        except Exception as e:
            record(test_fn.__doc__ or test_fn.__name__, False,
                   f"{type(e).__name__}: {e}\n        {traceback.format_exc(limit=3)}")

    await engine.disconnect()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'-'*40}")
    print(HEAD.format(f"Results: {passed}/{total} passed"))

    if passed < total:
        print("\nFailed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"  • {name}")
                if detail:
                    print(f"    {detail}")
        sys.exit(1)

    print("\n\033[92mAll tests passed. Stack is ready.\033[0m\n")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
