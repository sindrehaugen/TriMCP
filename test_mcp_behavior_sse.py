import asyncio
import json
import logging
import sys
from mcp import ClientSession
from mcp.client.sse import sse_client

# Set up local logging for the test script
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("test-client")

async def test():
    url = "http://localhost:8000/sse"
    
    logger.info(f"Connecting to SSE server at {url}...")
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            logger.info("Initializing session...")
            await asyncio.wait_for(session.initialize(), timeout=10.0)
            
            # 1. Async Indexing
            print("\n--- Command 1: index_code_file ---")
            logger.info("Calling index_code_file...")
            index_res = await asyncio.wait_for(
                session.call_tool('index_code_file', {
                    'filepath': 'analysis_target_sse.py',
                    'language': 'python',
                    'raw_code': 'def sse_task():\n    return \"success\"'
                }),
                timeout=10.0
            )
            index_data = json.loads(index_res.content[0].text)
            print(f"Status: {index_data.get('status')}")
            print(f"Job ID: {index_data.get('job_id')}")
            
            # 2. Status Check
            job_id = index_data.get('job_id')
            if job_id:
                print("\n--- Command 2: check_indexing_status ---")
                logger.info(f"Checking status for job {job_id}...")
                status_res = await asyncio.wait_for(
                    session.call_tool('check_indexing_status', {'job_id': job_id}),
                    timeout=10.0
                )
                print(f"Job Status: {status_res.content[0].text}")

            # 3. Hybrid Search
            print("\n--- Command 3: semantic_search (Hybrid) ---")
            logger.info("Calling semantic_search...")
            try:
                search_res = await asyncio.wait_for(
                    session.call_tool('semantic_search', {
                        'user_id': 'test_verify_user',
                        'query': 'scaling trimcp'
                    }),
                    timeout=20.0
                )
                print(f"Search Results: {search_res.content[0].text}")
            except asyncio.TimeoutError:
                logger.error("Command 3 timed out after 20 seconds!")

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except Exception as e:
        logger.error(f"Test failed: {e}")
