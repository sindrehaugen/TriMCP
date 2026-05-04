"""
Tri-Stack MCP Server
Wraps TriStackEngine in the official MCP Python SDK (stdio transport).
Exposes MCP tools to any MCP-compatible LLM client (Claude Desktop, Cursor, etc.).
GC background task is co-launched on startup for absolute data purity.
"""
import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from trimcp import MemoryPayload, MediaPayload, TriStackEngine, run_gc_loop
from trimcp import bridge_mcp_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s %(message)s",
)
log = logging.getLogger("tri-stack-mcp")

# --- Global engine instance (lifecycle managed by lifespan) ---
engine: TriStackEngine | None = None
app = Server("tri-stack-memory")


# --- Tool Definitions ---

TOOLS = [
    Tool(
        name="store_memory",
        description=(
            "Persist a memory (conversation turn, document, or summary) to the Tri-Stack. "
            "Writes heavy payload to MongoDB, vector index to PostgreSQL, summary to Redis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "user_id":       {"type": "string", "description": "Unique user identifier"},
                "session_id":    {"type": "string", "description": "Session or conversation ID"},
                "content_type":  {"type": "string", "enum": ["chat", "code"], "description": "Type of content"},
                "summary":       {"type": "string", "description": "Short summary used for embedding"},
                "heavy_payload": {"type": "string", "description": "Full raw content to archive"},
            },
            "required": ["user_id", "session_id", "content_type", "summary", "heavy_payload"],
        },
    ),
    Tool(
        name="store_media",
        description=(
            "Ingest large media (audio/video/image) into the Quad-Stack. "
            "Uploads raw file to MinIO and indexes the summary into the Tri-Stack."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "user_id":           {"type": "string"},
                "session_id":        {"type": "string"},
                "media_type":        {"type": "string", "enum": ["audio", "video", "image"]},
                "file_path_on_disk": {"type": "string", "description": "Local path to the media file"},
                "summary":           {"type": "string", "description": "AI-generated summary of the media content"},
            },
            "required": ["user_id", "session_id", "media_type", "file_path_on_disk", "summary"],
        },
    ),
    Tool(
        name="semantic_search",
        description=(
            "Search stored memories by semantic similarity. "
            "Uses pgvector cosine search then hydrates full content from MongoDB."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "query":   {"type": "string", "description": "Natural language search query"},
                "top_k":   {"type": "integer", "default": 5, "description": "Max results to return"},
            },
            "required": ["user_id", "query"],
        },
    ),
    Tool(
        name="index_code_file",
        description=(
            "Index a source code file into the Tri-Stack. "
            "Parses AST nodes (functions/classes), embeds each chunk, stores full file in MongoDB. "
            "Runs asynchronously: returns a job_id immediately."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "filepath":  {"type": "string", "description": "Absolute or relative path of the file"},
                "raw_code":  {"type": "string", "description": "Full source code content"},
                "language":  {"type": "string", "description": "Language: 'python', 'javascript', 'typescript', 'go', 'rust'"},
                "user_id":   {"type": "string", "description": "Optional. Required when private=true — scopes this index to the user."},
                "private":   {"type": "boolean", "default": False, "description": "When true, index is private to user_id (shared corpus uses user_id unset)."},
            },
            "required": ["filepath", "raw_code", "language"],
        },
    ),
    Tool(
        name="check_indexing_status",
        description="Check the status of a background indexing job.",
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job_id returned by index_code_file"},
            },
            "required": ["job_id"],
        },
    ),
    Tool(
        name="search_codebase",
        description=(
            "Semantic search over indexed code chunks. "
            "Returns matching functions/classes with file path and line numbers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query":           {"type": "string", "description": "Natural language description of the code to find"},
                "language_filter": {"type": "string", "description": "Optional: filter by language ('python', 'javascript')"},
                "top_k":           {"type": "integer", "default": 5},
                "user_id":         {"type": "string", "description": "Optional. Required when private=true — searches only that user's private index."},
                "private":         {"type": "boolean", "default": False, "description": "When false (default), search the shared corpus only. When true, search only chunks for user_id."},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="graph_search",
        description=(
            "GraphRAG traversal over the Knowledge Graph. "
            "Finds the closest entity node by vector similarity, then BFS-traverses edges "
            "to return a structured subgraph with nodes, relations, and source document excerpts."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query":     {"type": "string", "description": "Natural language query to anchor the graph search"},
                "max_depth": {"type": "integer", "default": 2, "description": "BFS hop depth (1-3 recommended)"},
                "user_id":   {"type": "string", "description": "Optional. Required when private=true — restricts hydrated sources to this user."},
                "private":   {"type": "boolean", "default": False, "description": "When false (default), hydrate all matching sources. When true, only documents owned by user_id."},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_recent_context",
        description=(
            "Retrieve the most recent cached context for a user/session from Redis. "
            "Sub-millisecond — does not touch PostgreSQL or MongoDB."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "user_id":    {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["user_id", "session_id"],
        },
    ),
    Tool(
        name="connect_bridge",
        description=(
            "Start OAuth for a document bridge (SharePoint / Google Drive / Dropbox). "
            "Creates a bridge_subscriptions row and returns auth_url when OAuth is configured."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Owning user id"},
                "provider": {
                    "type": "string",
                    "enum": ["sharepoint", "gdrive", "dropbox"],
                    "description": "Bridge provider",
                },
            },
            "required": ["user_id", "provider"],
        },
    ),
    Tool(
        name="complete_bridge_auth",
        description=(
            "Exchange OAuth authorization code, create provider push subscription / watch "
            "when webhook base URL is set, and mark bridge ACTIVE."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "bridge_id": {"type": "string", "description": "UUID from connect_bridge"},
                "provider": {
                    "type": "string",
                    "enum": ["sharepoint", "gdrive", "dropbox"],
                },
                "authorization_code": {"type": "string", "description": "OAuth code from redirect"},
                "code": {"type": "string", "description": "Alias for authorization_code"},
                "resource_id": {
                    "type": "string",
                    "description": (
                        "Provider resource: SharePoint 'site_id|drive_id'; "
                        "Drive: folder or root as used by watch; Dropbox: account id"
                    ),
                },
            },
            "required": ["user_id", "bridge_id", "provider"],
        },
    ),
    Tool(
        name="list_bridges",
        description="List bridge subscriptions for a user.",
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "include_disconnected": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include DISCONNECTED rows",
                },
            },
            "required": ["user_id"],
        },
    ),
    Tool(
        name="disconnect_bridge",
        description="Stop provider subscription / channel when tokens are configured; mark DISCONNECTED.",
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "bridge_id": {"type": "string"},
            },
            "required": ["user_id", "bridge_id"],
        },
    ),
    Tool(
        name="force_resync_bridge",
        description="Clear stored cursor, optional Redis cursor key, enqueue a full bridge sync job.",
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "bridge_id": {"type": "string"},
            },
            "required": ["user_id", "bridge_id"],
        },
    ),
    Tool(
        name="bridge_status",
        description="Return one bridge subscription row (public fields) and expiry hint.",
        inputSchema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "bridge_id": {"type": "string"},
            },
            "required": ["user_id", "bridge_id"],
        },
    ),
]


# --- Tool Handlers ---

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


def _err(msg: str, is_error: bool = True) -> list[TextContent]:
    log.warning("Tool error: %s", msg)
    # The SDK exposes isError through CallToolResult at the server level, but typically
    # a tool handler raising an exception or returning specific error types causes the 
    # server to format the response with isError=True. If we want to return TextContent
    # directly and signal an error to the MCP server, we should raise an exception,
    # or rely on the caller to format.
    # Actually, the python SDK expects exceptions for `isError=True` inside `call_tool`, 
    # or the return value must be a `CallToolResult`. But since we return `list[TextContent]`,
    # returning text does NOT set `isError=True`.
    # Let's change this to raise ValueError which the SDK catches and turns into an error result,
    # or we can just raise a generic Exception.
    raise ValueError(msg)

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if engine is None:
        raise RuntimeError("Engine not initialized")

    try:
        # --- API Cache Layer ---
        # Cache read-heavy determinisic queries
        CACHEABLE_TOOLS = {"semantic_search", "search_codebase", "graph_search"}
        MUTATION_TOOLS = {
            "store_memory",
            "store_media",
            "index_code_file",
            "connect_bridge",
            "complete_bridge_auth",
            "disconnect_bridge",
            "force_resync_bridge",
        }
        
        # Read-after-write invalidation via generation counter
        if name in MUTATION_TOOLS:
            await engine.redis_client.incr("mcp_cache_generation")
            
        cache_key = None
        if name in CACHEABLE_TOOLS:
            import hashlib
            args_str = json.dumps(arguments, sort_keys=True)
            args_hash = hashlib.md5(args_str.encode()).hexdigest()
            
            gen = await engine.redis_client.get("mcp_cache_generation")
            gen_val = gen.decode() if gen else "0"
            cache_key = f"mcp_cache:v{gen_val}:{name}:{args_hash}"
            
            cached_val = await engine.redis_client.get(cache_key)
            if cached_val:
                log.info(f"API Cache hit for tool {name}")
                return [TextContent(type="text", text=cached_val.decode())]

        if name == "store_memory":
            payload = MemoryPayload(**arguments)
            mongo_id = await engine.store_memory(payload)
            return [TextContent(type="text", text=json.dumps({"status": "ok", "mongo_ref_id": mongo_id}))]

        if name == "store_media":
            payload = MediaPayload(**arguments)
            mongo_id = await engine.store_media(payload)
            return [TextContent(type="text", text=json.dumps({"status": "ok", "mongo_ref_id": mongo_id, "storage": "minio"}))]

        if name == "semantic_search":
            results = await engine.semantic_search(
                user_id=arguments["user_id"],
                query=arguments["query"],
                top_k=int(arguments.get("top_k", 5)),
            )
            result_text = json.dumps(results)
            if cache_key: await engine.redis_client.setex(cache_key, 300, result_text)
            return [TextContent(type="text", text=result_text)]

        if name == "index_code_file":
            result = await engine.index_code_file(
                filepath=arguments["filepath"],
                raw_code=arguments["raw_code"],
                language=arguments["language"],
                user_id=arguments.get("user_id"),
                private=bool(arguments.get("private", False)),
            )
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "check_indexing_status":
            result = await engine.get_job_status(
                job_id=arguments["job_id"],
            )
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "search_codebase":
            results = await engine.search_codebase(
                query=arguments["query"],
                language_filter=arguments.get("language_filter"),
                top_k=int(arguments.get("top_k", 5)),
                user_id=arguments.get("user_id"),
                private=bool(arguments.get("private", False)),
            )
            result_text = json.dumps(results)
            if cache_key: await engine.redis_client.setex(cache_key, 300, result_text)
            return [TextContent(type="text", text=result_text)]

        if name == "graph_search":
            result = await engine.graph_search(
                query=arguments["query"],
                max_depth=max(1, min(int(arguments.get("max_depth", 2)), 3)),
                user_id=arguments.get("user_id"),
                private=bool(arguments.get("private", False)),
            )
            result_text = json.dumps(result, indent=2)
            if cache_key: await engine.redis_client.setex(cache_key, 300, result_text)
            return [TextContent(type="text", text=result_text)]

        if name == "get_recent_context":
            context = await engine.recall_memory(
                user_id=arguments["user_id"],
                session_id=arguments["session_id"],
            )
            return [TextContent(type="text", text=json.dumps({"context": context}))]

        if name == "connect_bridge":
            text = await bridge_mcp_handlers.connect_bridge(engine, arguments)
            return [TextContent(type="text", text=text)]

        if name == "complete_bridge_auth":
            text = await bridge_mcp_handlers.complete_bridge_auth(engine, arguments)
            return [TextContent(type="text", text=text)]

        if name == "list_bridges":
            text = await bridge_mcp_handlers.list_bridges(engine, arguments)
            return [TextContent(type="text", text=text)]

        if name == "disconnect_bridge":
            text = await bridge_mcp_handlers.disconnect_bridge(engine, arguments)
            return [TextContent(type="text", text=text)]

        if name == "force_resync_bridge":
            text = await bridge_mcp_handlers.force_resync_bridge(engine, arguments)
            return [TextContent(type="text", text=text)]

        if name == "bridge_status":
            text = await bridge_mcp_handlers.bridge_status(engine, arguments)
            return [TextContent(type="text", text=text)]

        raise ValueError(f"Unknown tool: {name}")

    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid input: {e}")
    except Exception as e:
        log.exception("Unhandled error in tool '%s'", name)
        raise RuntimeError(f"Internal error: {type(e).__name__}")


# --- Startup / Shutdown ---

async def main():
    global engine
    engine = TriStackEngine()
    await engine.connect()
    log.info("TriStackEngine connected to all three databases.")

    gc_task = asyncio.create_task(run_gc_loop())
    log.info("GC background task started.")

    try:
        async with stdio_server() as (read_stream, write_stream):
            log.info("MCP server listening on stdio.")
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        gc_task.cancel()
        try:
            await gc_task
        except asyncio.CancelledError:
            pass
        await engine.disconnect()
        log.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
