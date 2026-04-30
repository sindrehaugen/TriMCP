import os
import json
import logging
from contextlib import asynccontextmanager
from starlette.applications import Starlette
from starlette.responses import JSONResponse, HTMLResponse, FileResponse
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

from trimcp.orchestrator import TriStackEngine
from trimcp.notifications import dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trimcp-admin")

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/api/"):
            auth_header = request.headers.get("Authorization", "")
            if not ADMIN_API_KEY or auth_header != f"Bearer {ADMIN_API_KEY}":
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)

engine: TriStackEngine | None = None

@asynccontextmanager
async def lifespan(app):
    global engine
    engine = TriStackEngine()
    await engine.connect()
    await dispatcher.start_worker()
    logger.info("TriMCP Admin: engine connected, dispatcher started.")
    yield
    await dispatcher.stop_worker()
    await engine.disconnect()
    logger.info("TriMCP Admin: shutdown complete.")

async def get_health(request):
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    health = await engine.check_health()

    if any(status == "down" for status in health.values()):
        await dispatcher.dispatch_alert("Database Health Alert", f"Current health: {json.dumps(health)}")

    return JSONResponse(health)

async def trigger_gc(request):
    if not engine:
        return JSONResponse({"error": "Engine not connected"}, status_code=503)

    try:
        result = await engine.force_gc()
        return JSONResponse({"status": "success", "result": result})
    except Exception as e:
        logger.error("GC failed: %s", e)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

async def serve_index(request):
    index_path = os.path.join(os.path.dirname(__file__), "admin", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("Admin UI not found", status_code=404)

app = Starlette(
    debug=False,
    lifespan=lifespan,
    middleware=[Middleware(AuthMiddleware)],
    routes=[
        Route("/", endpoint=serve_index),
        Route("/api/health", endpoint=get_health, methods=["GET"]),
        Route("/api/gc/trigger", endpoint=trigger_gc, methods=["POST"]),
    ],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
