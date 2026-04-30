import pytest
import os
import time
from trimcp import MemoryPayload, TriStackEngine

# Tests require live DB containers (MongoDB, Redis, PostgreSQL).
# Set via .env or assume defaults.

@pytest.fixture
async def engine():
    eng = TriStackEngine()
    await eng.connect()
    yield eng
    await eng.disconnect()

@pytest.mark.asyncio
async def test_store_and_recall(engine):
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

@pytest.mark.asyncio
async def test_semantic_search(engine):
    """semantic_search returns stored document"""
    user_id = f"test_user_t2_{int(time.time())}"
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
    assert "pgvector" in str(results_sr[0].get("raw_data", "")), \
        f"Expected pgvector in top result, got: {results_sr[0].get('raw_data', '')!r}"

@pytest.mark.asyncio
async def test_index_and_search_code(engine):
    """index_code_file + search_codebase finds the function"""
    run_id = str(int(time.time()))
    sample_code = (
        "def calculate_embedding_distance(vec_a, vec_b):\n"
        "    pass\n"
        "class VectorStore:\n"
        "    pass\n"
    )
    result = await engine.index_code_file(
        filepath=f"test_fixtures/vector_utils_{run_id}.py",
        raw_code=sample_code,
        language="python",
    )
    assert result["status"] == "indexed", f"Unexpected status: {result}"
    
    code_results = await engine.search_codebase("cosine distance between vectors", top_k=3)
    assert len(code_results) > 0, "No code results returned"
    assert any("calculate_embedding_distance" in r.get("name", "") for r in code_results)

@pytest.mark.asyncio
async def test_change_detection(engine):
    """Re-indexing unchanged file returns status=skipped"""
    code = "def noop(): pass\n"
    fp = "test_fixtures/noop.py"
    await engine.index_code_file(filepath=fp, raw_code=code, language="python")
    result2 = await engine.index_code_file(filepath=fp, raw_code=code, language="python")
    assert result2["status"] == "skipped", f"Expected skipped, got: {result2}"

@pytest.mark.asyncio
async def test_graph_search(engine):
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

@pytest.mark.asyncio
async def test_rollback(engine):
    """Forcing a PG failure must leave MongoDB clean"""
    from motor.motor_asyncio import AsyncIOMotorClient
    
    db = AsyncIOMotorClient(os.getenv("MONGO_URI", "mongodb://localhost:27017")).memory_archive
    before_count = await db.episodes.count_documents({})

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
        pytest.fail("Exception was NOT raised — rollback did not trigger")
    except Exception:
        pass
    finally:
        engine.pg_pool = real_pool

    after_count = await db.episodes.count_documents({})
    assert after_count == before_count, \
        f"MongoDB grew by {after_count - before_count} — orphan NOT cleaned up"
