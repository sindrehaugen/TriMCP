"""
Tri-Stack MCP Server
Wraps TriStackEngine in the official MCP Python SDK (stdio transport).
Exposes 5 tools to any MCP-compatible LLM client (Claude Desktop, Cursor, etc.).
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
]


# --- Tool Handlers ---

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


def _err(msg: str) -> list[TextContent]:
    log.warning("Tool error: %s", msg)
    return [TextContent(type="text", text=json.dumps({"error": msg}))]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if engine is None:
        return _err("Engine not initialized")

    try:
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
            return [TextContent(type="text", text=json.dumps(results))]

        if name == "index_code_file":
            result = await engine.index_code_file(
                filepath=arguments["filepath"],
                raw_code=arguments["raw_code"],
                language=arguments["language"],
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
            )
            return [TextContent(type="text", text=json.dumps(results))]

        if name == "graph_search":
            result = await engine.graph_search(
                query=arguments["query"],
                max_depth=max(1, min(int(arguments.get("max_depth", 2)), 3)),
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        if name == "get_recent_context":
            context = await engine.recall_memory(
                user_id=arguments["user_id"],
                session_id=arguments["session_id"],
            )
            return [TextContent(type="text", text=json.dumps({"context": context}))]

        return _err(f"Unknown tool: {name}")

    except (ValueError, TypeError) as e:
        return _err(f"Invalid input: {e}")
    except Exception as e:
        log.exception("Unhandled error in tool '%s'", name)
        return _err(f"Internal error: {type(e).__name__}")


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
