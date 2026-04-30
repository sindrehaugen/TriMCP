import asyncio
import json
import sys
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@pytest.mark.asyncio
async def test_stdio_smoke_indexing():
    server_params = StdioServerParameters(command=sys.executable, args=['server.py'])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=30.0)
            
            # Smoke test: index a file and check status
            index_res = await asyncio.wait_for(
                session.call_tool('index_code_file', {
                    'filepath': 'smoke_test_target.py',
                    'language': 'python',
                    'raw_code': 'def smoke_task():\n    return 42'
                }),
                timeout=30.0
            )
            index_data = json.loads(index_res.content[0].text)
            assert index_data.get('status') in ['indexed', 'skipped']
            
            job_id = index_data.get('job_id')
            if job_id:
                status_res = await asyncio.wait_for(
                    session.call_tool('check_indexing_status', {'job_id': job_id}),
                    timeout=30.0
                )
                assert status_res.content[0].text

@pytest.mark.asyncio
async def test_stdio_smoke_memory():
    server_params = StdioServerParameters(command=sys.executable, args=['server.py'])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=30.0)
            
            res = await asyncio.wait_for(
                session.call_tool('store_memory', {
                    'user_id': 'u1',
                    'session_id': 's1',
                    'content_type': 'chat',
                    'summary': 'Smoke test summary',
                    'heavy_payload': 'Smoke test payload'
                }),
                timeout=30.0
            )
            assert 'mongo_ref_id' in res.content[0].text
            
            res_ctx = await asyncio.wait_for(
                session.call_tool('get_recent_context', {
                    'user_id': 'u1',
                    'session_id': 's1'
                }),
                timeout=30.0
            )
            assert 'context' in res_ctx.content[0].text
