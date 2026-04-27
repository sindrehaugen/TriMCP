import asyncio
import json
import logging
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("test-client-simple")

async def test():
    server_params = StdioServerParameters(command='.venv/Scripts/python.exe', args=['server.py'])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=10.0)
            
            print("\n1. Testing store_memory...")
            res = await session.call_tool('store_memory', {
                'user_id': 'u1',
                'session_id': 's1',
                'content_type': 'chat',
                'summary': 'Test summary for context',
                'heavy_payload': 'Test payload long content'
            })
            print(f"Store Response: {res.content[0].text}")
            
            print("\n2. Testing get_recent_context...")
            res = await session.call_tool('get_recent_context', {
                'user_id': 'u1',
                'session_id': 's1'
            })
            print(f"Recent Context: {res.content[0].text}")

if __name__ == "__main__":
    asyncio.run(test())
