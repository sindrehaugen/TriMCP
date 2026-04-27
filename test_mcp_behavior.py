import asyncio
import json
import logging
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Set up local logging for the test script
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
logger = logging.getLogger("test-client")

async def test():
    server_params = StdioServerParameters(command='.venv/Scripts/python.exe', args=['server.py'])
    
    logger.info("Connecting to server...")
    # Capture stderr to see server logs
    import subprocess
    async with stdio_client(server_params) as (read, write):
        # We need to access the underlying process to get stderr
        # But stdio_client doesn't easily expose it.
        # Let's just run uvicorn in a way we can see logs or rely on sse_server.log
        async with ClientSession(read, write) as session:
            logger.info("Initializing session...")
            await asyncio.wait_for(session.initialize(), timeout=30.0)
            
            # 1. Async Indexing
            print("\n--- Command 1: index_code_file ---")
            logger.info("Calling index_code_file...")
            index_res = await asyncio.wait_for(
                session.call_tool('index_code_file', {
                    'filepath': 'analysis_target.py',
                    'language': 'python',
                    'raw_code': 'def heavy_task():\n    """Processes RRF logic for scalability."""\n    return 42'
                }),
                timeout=30.0
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
                    timeout=30.0
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
                    timeout=30.0
                )
                print(f"Search Results: {search_res.content[0].text}")
            except asyncio.TimeoutError:
                logger.error("Command 3 timed out after 30 seconds!")

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except Exception as e:
        logger.exception("Test failed with error:")
