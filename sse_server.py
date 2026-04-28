"""
TriMCP SSE Server
Exposes the TriMCP server over HTTP/SSE for persistent background access.
"""
import logging
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from server import app as mcp_app
import asyncio
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trimcp-sse")

sse = SseServerTransport("/messages")

@asynccontextmanager
async def lifespan(app: Starlette):
    import server
    if server.engine is None:
        from trimcp import TriStackEngine
        server.engine = TriStackEngine()
    await server.engine.connect()
    logger.info("TriStackEngine connected (SSE)")
    
    from server import run_gc_loop
    gc_task = asyncio.create_task(run_gc_loop())
    logger.info("GC loop started (SSE)")
    
    yield
    
    gc_task.cancel()
    try:
        await gc_task
    except asyncio.CancelledError:
        pass
        
    if server.engine:
        await server.engine.disconnect()
    logger.info("TriStackEngine disconnected (SSE)")

from starlette.routing import Route

async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp_app.run(
            read_stream,
            write_stream,
            mcp_app.create_initialization_options()
        )

async def handle_messages(request):
    await sse.handle_post_message(request.scope, request.receive, request._send)

starlette_app = Starlette(
    debug=True, 
    lifespan=lifespan,
    routes=[
        Route("/sse", endpoint=handle_sse),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
    ]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(starlette_app, host="0.0.0.0", port=8002)
