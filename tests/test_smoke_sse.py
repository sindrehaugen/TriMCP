import asyncio
import json
import pytest
import aiohttp
from mcp import ClientSession
from mcp.client.sse import sse_client

@pytest.mark.asyncio
async def test_sse_smoke():
    url = "http://localhost:8000/sse"
    
    # Check if SSE server is running, if not, skip
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                pass
    except aiohttp.ClientConnectorError:
        pytest.skip("SSE Server not running on localhost:8000")

    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=10.0)
            
            index_res = await asyncio.wait_for(
                session.call_tool('index_code_file', {
                    'filepath': 'analysis_target_sse_smoke.py',
                    'language': 'python',
                    'raw_code': 'def sse_task():\n    return "success"'
                }),
                timeout=10.0
            )
            index_data = json.loads(index_res.content[0].text)
            assert index_data.get('status') in ['indexed', 'skipped']
