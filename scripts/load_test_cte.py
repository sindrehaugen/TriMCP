import asyncio
import time
import asyncpg
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("load-test-cte")

PG_DSN = "postgres://mcp_user:mcp_password@localhost:5432/memory_meta"

async def run_load_test():
    pool = await asyncpg.create_pool(PG_DSN, min_size=5, max_size=20)
    
    # Simple BFS traversal query using the new path accumulation array to prevent cycles
    query = """
    WITH RECURSIVE traversal AS (
        SELECT id, label, 0 AS depth, ARRAY[id] AS path
        FROM kg_nodes
        WHERE id = (SELECT id FROM kg_nodes LIMIT 1)
        UNION
        SELECT n.id, n.label, t.depth + 1, t.path || n.id
        FROM traversal t
        JOIN kg_edges e ON t.label = e.subject_label
        JOIN kg_nodes n ON e.object_label = n.label
        WHERE t.depth < 3
          AND n.id != ALL(t.path)
    )
    SELECT * FROM traversal LIMIT 100;
    """

    async def worker(i):
        async with pool.acquire() as conn:
            start = time.time()
            try:
                await conn.fetch(query)
            except Exception as e:
                logger.error(f"Worker {i} error: {e}")
            return time.time() - start

    logger.info("Starting recursive CTE load test with 50 concurrent connections...")
    start_total = time.time()
    results = await asyncio.gather(*(worker(i) for i in range(50)))
    total_time = time.time() - start_total
    
    logger.info(f"Ran 50 concurrent CTE traversals in {total_time:.2f}s")
    logger.info(f"Average time per query: {sum(results)/len(results):.3f}s")
    logger.info(f"Max time: {max(results):.3f}s")
    logger.info(f"Min time: {min(results):.3f}s")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(run_load_test())
