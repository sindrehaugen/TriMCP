import asyncio
import logging
import hashlib
from trimcp.orchestrator import TriStackEngine, MemoryPayload

logging.basicConfig(level=logging.INFO)

async def test_path_traversal(engine):
    print("\n--- Testing Path Traversal Protection ---")
    bad_paths = [
        "../../etc/passwd",
        "C:\\Windows\\System32\\config\\SAM",
        "/etc/shadow",
        "nested/../../../secret.txt"
    ]
    for path in bad_paths:
        try:
            engine._validate_path(path)
            print(f"FAIL: {path} was allowed")
        except ValueError as e:
            print(f"PASS: {path} rejected: {e}")

async def test_hybrid_search(engine):
    print("\n--- Testing Hybrid Search (RRF) ---")
    user_id = "test_verify_user"
    session_id = "session_1"
    
    # 1. Ingest test data
    payload = MemoryPayload(
        user_id=user_id,
        session_id=session_id,
        content_type="chat",
        summary="Scaling TriMCP with async queues and hybrid search.",
        heavy_payload="Detailed technical documentation about the TriMCP scalability expansion plan."
    )
    await engine.store_memory(payload)
    print("Ingested test memory.")

    # 2. Search
    results = await engine.semantic_search(user_id, "scaling trimcp")
    print(f"Query executed. Results count: {len(results)}")
    if results:
        print(f"Top result score: {results[0].get('score')}")
        if "score" in results[0]:
            print("PASS: results contain RRF score")
        else:
            print("FAIL: missing score field")
    else:
        print("FAIL: no results found for valid query")

async def test_async_queue(engine):
    print("\n--- Testing Async Job Queue ---")
    try:
        res = await engine.index_code_file("verify_test.py", "def verify(): pass", "python")
        print(f"Index response: {res}")
        if res.get("status") == "enqueued":
            print(f"PASS: Job enqueued with ID: {res.get('job_id')}")
            status = await engine.get_job_status(res.get("job_id"))
            print(f"Job status check: {status}")
        elif res.get("status") == "skipped":
             print("Job skipped (already indexed).")
        else:
             print(f"Unexpected status: {res.get('status')}")
    except Exception as e:
        print(f"Error during async queue test: {e}")

async def main():
    engine = TriStackEngine()
    await engine.connect()
    try:
        await test_path_traversal(engine)
        await test_hybrid_search(engine)
        await test_async_queue(engine)
    finally:
        await engine.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
