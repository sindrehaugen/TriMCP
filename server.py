"""
Tri-Stack MCP Server
Wraps TriStackEngine in the official MCP Python SDK (stdio transport).
Exposes MCP tools to any MCP-compatible LLM client (Claude Desktop, Cursor, etc.).
GC background task is co-launched on startup for absolute data purity.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from trimcp import MemoryPayload, MediaPayload, TriStackEngine, run_gc_loop
from trimcp import bridge_mcp_handlers
from trimcp.temporal import parse_as_of

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s %(message)s",
)
log = logging.getLogger("tri-stack-mcp")

# MCP / JSON-RPC client-visible prefix when ``consume_for_tool`` hits a hard limit.
MCP_QUOTA_EXCEEDED_PREFIX = "Resource quota exceeded (-32013)"


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
                "namespace_id":  {"type": "string"},
                "agent_id":      {"type": "string"},
                "content":       {"type": "string"},
                "summary":       {"type": "string", "description": "Short summary used for embedding"},
                "heavy_payload": {"type": "string", "description": "Full raw content to archive"},
                "content_type":  {"type": "string", "enum": ["chat", "code"], "description": "Type of content"},
                "check_contradictions": {"type": "boolean", "default": False},
            },
            "required": ["namespace_id", "agent_id", "content"],
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
            "Uses pgvector cosine search then hydrates full content from MongoDB. "
            "Supply as_of to query the state of memory at a specific point in time (Phase 2.2 time travel)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string"},
                "agent_id":     {"type": "string"},
                "query":        {"type": "string", "description": "Natural language search query"},
                "top_k":        {"type": "integer", "default": 5, "description": "Max results to return"},
                "as_of": {
                    "type": "string",
                    "format": "date-time",
                    "description": (
                        "Optional ISO 8601 UTC timestamp (e.g. '2026-01-15T10:00:00Z'). "
                        "Restricts results to memories that existed at or before this instant. "
                        "Omit to query the current state."
                    ),
                },
            },
            "required": ["namespace_id", "agent_id", "query"],
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
            "to return a structured subgraph with nodes, relations, and source document excerpts. "
            "Supply as_of to traverse the graph as it existed at a specific point in time (Phase 2.2 time travel)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query":     {"type": "string", "description": "Natural language query to anchor the graph search"},
                "max_depth": {"type": "integer", "default": 2, "description": "BFS hop depth (1-3 recommended)"},
                "user_id":   {"type": "string", "description": "Optional. When supplied, restricts hydrated sources to this user."},
                "private":   {"type": "boolean", "default": False, "description": "When true, only hydrate sources owned by user_id."},
                "as_of": {
                    "type": "string",
                    "format": "date-time",
                    "description": (
                        "Optional ISO 8601 UTC timestamp (e.g. '2026-01-15T10:00:00Z'). "
                        "Traverses the knowledge graph as it existed at or before this instant. "
                        "Omit to traverse the current graph."
                    ),
                },
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
    Tool(
        name="boost_memory",
        description="[Phase 1.1] Boosts the salience of a memory for the calling agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "namespace_id": {"type": "string"},
                "factor": {"type": "number", "default": 0.2},
            },
            "required": ["memory_id", "agent_id", "namespace_id"],
        },
    ),
    Tool(
        name="forget_memory",
        description="[Phase 1.1] Sets salience to 0.0 for the calling agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "namespace_id": {"type": "string"},
            },
            "required": ["memory_id", "agent_id", "namespace_id"],
        },
    ),
    Tool(
        name="list_contradictions",
        description="[Phase 1.3] List detected contradictions.",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string"},
                "resolution": {"type": "string", "description": "Filter by resolution status (e.g. 'unresolved')"},
                "agent_id": {"type": "string"},
            },
            "required": ["namespace_id"],
        },
    ),
    Tool(
        name="resolve_contradiction",
        description="[Phase 1.3] Resolve a contradiction.",
        inputSchema={
            "type": "object",
            "properties": {
                "contradiction_id": {"type": "string"},
                "resolution": {"type": "string", "enum": ["resolved_a", "resolved_b", "both_valid"]},
                "resolved_by": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["contradiction_id", "resolution", "resolved_by"],
        },
    ),
    Tool(
        name="unredact_memory",
        description="[ADMIN] Reverses pseudonymisation for a given memory. Requires elevated permissions.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "namespace_id": {"type": "string"},
                "agent_id": {"type": "string"},
            },
            "required": ["memory_id", "namespace_id", "agent_id"],
        },
    ),
    Tool(
        name="start_migration",
        description="[Phase 2.1] Start an embedding migration.",
        inputSchema={
            "type": "object",
            "properties": {
                "target_model_id": {"type": "string"},
            },
            "required": ["target_model_id"],
        },
    ),
    Tool(
        name="migration_status",
        description="[Phase 2.1] Check the status of an embedding migration.",
        inputSchema={
            "type": "object",
            "properties": {
                "migration_id": {"type": "string"},
            },
            "required": ["migration_id"],
        },
    ),
    Tool(
        name="validate_migration",
        description="[Phase 2.1] Run quality gate checks on a finished migration.",
        inputSchema={
            "type": "object",
            "properties": {
                "migration_id": {"type": "string"},
            },
            "required": ["migration_id"],
        },
    ),
    Tool(
        name="commit_migration",
        description="[Phase 2.1] Commit a validated migration, making it the active model.",
        inputSchema={
            "type": "object",
            "properties": {
                "migration_id": {"type": "string"},
            },
            "required": ["migration_id"],
        },
    ),
    Tool(
        name="abort_migration",
        description="[Phase 2.1] Abort a migration and clean up.",
        inputSchema={
            "type": "object",
            "properties": {
                "migration_id": {"type": "string"},
            },
            "required": ["migration_id"],
        },
    ),
    # ------------------------------------------------------------------
    # Phase 2.3 — Memory Replay tools
    # ------------------------------------------------------------------
    Tool(
        name="replay_observe",
        description=(
            "[Phase 2.3] Stream historical events from event_log back to the caller "
            "without modifying any engine state.  Returns a JSONL-encoded list of "
            "event dicts (one per line), terminated by a 'complete' summary line.  "
            "Useful for auditing, debugging, and point-in-time inspection."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {
                    "type": "string",
                    "description": "Source namespace UUID to stream events from.",
                },
                "start_seq": {
                    "type": "integer",
                    "default": 1,
                    "description": "Inclusive lower bound on event_seq (default: 1).",
                },
                "end_seq": {
                    "type": "integer",
                    "description": "Inclusive upper bound on event_seq.  Omit to stream to the latest event.",
                },
                "agent_id_filter": {
                    "type": "string",
                    "description": "Optional: restrict stream to events from this agent_id.",
                },
                "max_events": {
                    "type": "integer",
                    "default": 500,
                    "description": "Hard cap on the number of events returned in one call (default: 500).",
                },
            },
            "required": ["namespace_id"],
        },
    ),
    Tool(
        name="replay_fork",
        description=(
            "[Phase 2.3] Fork a namespace by replaying its event_log into an isolated "
            "target namespace.  Events up to 'fork_seq' are applied with fresh HMAC "
            "signatures (alternate causal provenance).  In 'deterministic' mode, LLM "
            "responses are served from the MinIO payload cache for byte-identical "
            "reconstruction.  In 're-execute' mode, the LLM provider is called fresh, "
            "allowing intentional divergence (e.g. A/B testing consolidation prompts).  "
            "Returns a run_id immediately; use replay_status to poll progress."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source_namespace_id": {
                    "type": "string",
                    "description": "Namespace to replay events FROM.",
                },
                "target_namespace_id": {
                    "type": "string",
                    "description": "Namespace to replay events INTO (must exist and be empty).",
                },
                "fork_seq": {
                    "type": "integer",
                    "description": "Inclusive upper bound: replay events with event_seq <= fork_seq.",
                },
                "start_seq": {
                    "type": "integer",
                    "default": 1,
                    "description": "Inclusive lower bound on event_seq (default: 1).",
                },
                "replay_mode": {
                    "type": "string",
                    "enum": ["deterministic", "re-execute"],
                    "default": "deterministic",
                    "description": (
                        "'deterministic': use cached MinIO LLM payloads.  "
                        "'re-execute': call LLM fresh, optionally with config_overrides."
                    ),
                },
                "config_overrides": {
                    "type": "object",
                    "description": (
                        "Optional overrides applied during re-execute mode.  "
                        "Supported keys: prompt_suffix, llm_provider, llm_model, llm_temperature."
                    ),
                },
                "agent_id_filter": {
                    "type": "string",
                    "description": "Optional: replay only events from this agent_id.",
                },
            },
            "required": ["source_namespace_id", "target_namespace_id", "fork_seq"],
        },
    ),
    Tool(
        name="replay_status",
        description=(
            "[Phase 2.3] Poll the status and progress of an active or completed replay run."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "UUID returned by replay_fork.",
                },
            },
            "required": ["run_id"],
        },
    ),
    Tool(
        name="get_event_provenance",
        description=(
            "[Phase 2.3] Return the full causal chain for a memory: the event_log "
            "entries that created and modified it, traversed via parent_event_id.  "
            "Useful for auditing forked replays and tracing alternate causal provenance."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "UUID of the memory whose provenance to trace.",
                },
            },
            "required": ["memory_id"],
        },
    ),

    # ------------------------------------------------------------------
    # Phase 3.1 — A2A (Agent-to-Agent) Protocol Tools
    # ------------------------------------------------------------------
    Tool(
        name="a2a_create_grant",
        description=(
            "[Phase 3.1] Create an A2A sharing grant — generates a secure token "
            "that another agent can use to access your memories within the declared scopes. "
            "Returns grant_id and a one-time sharing_token to pass to the recipient out-of-band."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id":        {"type": "string", "description": "Owner namespace UUID."},
                "agent_id":            {"type": "string", "description": "Owner agent ID."},
                "scopes":              {
                    "type": "array",
                    "description": "List of scope objects. Each has resource_type, resource_id, and permissions.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "resource_type": {"type": "string", "enum": ["namespace", "memory", "kg_node", "subgraph"]},
                            "resource_id":   {"type": "string"},
                            "permissions":   {"type": "array", "items": {"type": "string", "enum": ["read"]}},
                        },
                        "required": ["resource_type", "resource_id"],
                    },
                },
                "target_namespace_id": {"type": "string", "description": "Optional: restrict to a specific recipient namespace."},
                "target_agent_id":     {"type": "string", "description": "Optional: restrict to a specific recipient agent."},
                "expires_in_seconds":  {"type": "integer", "default": 3600, "description": "Token lifetime (60–2592000 s)."},
            },
            "required": ["namespace_id", "agent_id", "scopes"],
        },
    ),
    Tool(
        name="a2a_revoke_grant",
        description=(
            "[Phase 3.1] Revoke an active A2A sharing grant. "
            "Only the owning namespace can revoke its own grants."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string", "description": "Owner namespace UUID."},
                "agent_id":     {"type": "string", "description": "Owner agent ID."},
                "grant_id":     {"type": "string", "description": "UUID of the grant to revoke."},
            },
            "required": ["namespace_id", "agent_id", "grant_id"],
        },
    ),
    Tool(
        name="a2a_list_grants",
        description=(
            "[Phase 3.1] List all active A2A sharing grants owned by this namespace. "
            "Token hashes are never returned — only grant metadata."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id":     {"type": "string", "description": "Owner namespace UUID."},
                "agent_id":         {"type": "string", "description": "Owner agent ID."},
                "include_inactive": {"type": "boolean", "default": False,
                                     "description": "Include revoked and expired grants for audit purposes."},
            },
            "required": ["namespace_id", "agent_id"],
        },
    ),
    Tool(
        name="a2a_query_shared",
        description=(
            "[Phase 3.1] Execute a semantic search against another agent's memories "
            "using an A2A sharing token. Validates the token, enforces scope constraints, "
            "then queries the owner's namespace under RLS. "
            "Error -32010 = unauthorized token. Error -32011 = scope violation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "sharing_token":        {"type": "string", "description": "Token provided by the owning agent."},
                "consumer_namespace_id": {"type": "string", "description": "UUID of the namespace consuming the token."},
                "consumer_agent_id":    {"type": "string", "description": "Agent ID of the consumer."},
                "query":                {"type": "string", "description": "Semantic search query string."},
                "resource_type":        {"type": "string", "enum": ["namespace", "memory", "kg_node", "subgraph"],
                                          "default": "namespace",
                                          "description": "Resource type to validate against granted scopes."},
                "resource_id":          {"type": "string",
                                          "description": "Specific resource ID to validate; omit for namespace-level grants."},
                "top_k":                {"type": "integer", "default": 5},
            },
            "required": ["sharing_token", "consumer_namespace_id", "query"],
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

        from trimcp import quotas as _quotas

        try:
            q_res = await _quotas.consume_for_tool(engine.pg_pool, name, arguments)
        except _quotas.QuotaExceededError as exc:
            # Surface without the generic "Invalid input:" wrapper (see outer except).
            raise ValueError(f"{MCP_QUOTA_EXCEEDED_PREFIX}: {exc}") from exc

        try:
            if name == "store_memory":
                payload = MemoryPayload(**arguments)
                result = await engine.store_memory(payload)
                response = {"status": "ok", "payload_ref": result["payload_ref"]}
                if result.get("contradiction"):
                    response["contradiction"] = result["contradiction"]
                return [TextContent(type="text", text=json.dumps(response))]

            if name == "store_media":
                payload = MediaPayload(**arguments)
                mongo_id = await engine.store_media(payload)
                return [TextContent(type="text", text=json.dumps({"status": "ok", "payload_ref": mongo_id, "storage": "minio"}))]

            if name == "semantic_search":
                try:
                    as_of_dt = parse_as_of(arguments.get("as_of"))
                except ValueError as exc:
                    await q_res.rollback()
                    return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]
                results = await engine.semantic_search(
                    namespace_id=arguments["namespace_id"],
                    agent_id=arguments["agent_id"],
                    query=arguments["query"],
                    top_k=int(arguments.get("top_k", 5)),
                    as_of=as_of_dt,
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
                try:
                    as_of_dt = parse_as_of(arguments.get("as_of"))
                except ValueError as exc:
                    return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]
                result = await engine.graph_search(
                    query=arguments["query"],
                    max_depth=max(1, min(int(arguments.get("max_depth", 2)), 3)),
                    restrict_user_id=arguments.get("user_id"),
                    as_of=as_of_dt,
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

            if name == "boost_memory":
                res = await engine.boost_memory(
                    memory_id=arguments["memory_id"],
                    agent_id=arguments["agent_id"],
                    namespace_id=arguments["namespace_id"],
                    factor=float(arguments.get("factor", 0.2)),
                )
                return [TextContent(type="text", text=json.dumps(res))]

            if name == "forget_memory":
                res = await engine.forget_memory(
                    memory_id=arguments["memory_id"],
                    agent_id=arguments["agent_id"],
                    namespace_id=arguments["namespace_id"],
                )
                return [TextContent(type="text", text=json.dumps(res))]

            if name == "list_contradictions":
                # Convert datetime objects to string before json.dumps
                res = await engine.list_contradictions(
                    namespace_id=arguments["namespace_id"],
                    resolution=arguments.get("resolution"),
                    agent_id=arguments.get("agent_id"),
                )
                for r in res:
                    for k, v in r.items():
                        if isinstance(v, datetime):
                            r[k] = v.isoformat()
                        elif isinstance(v, uuid.UUID):
                            r[k] = str(v)
                return [TextContent(type="text", text=json.dumps(res))]

            if name == "resolve_contradiction":
                res = await engine.resolve_contradiction(
                    contradiction_id=arguments["contradiction_id"],
                    resolution=arguments["resolution"],
                    resolved_by=arguments["resolved_by"],
                    note=arguments.get("note"),
                )
                return [TextContent(type="text", text=json.dumps(res))]

            if name == "unredact_memory":
                result = await engine.unredact_memory(
                    memory_id=arguments["memory_id"],
                    namespace_id=arguments["namespace_id"],
                    agent_id=arguments["agent_id"]
                )
                return [TextContent(type="text", text=json.dumps(result))]

            if name == "start_migration":
                res = await engine.start_migration(arguments["target_model_id"])
                return [TextContent(type="text", text=json.dumps(res))]

            if name == "migration_status":
                res = await engine.migration_status(arguments["migration_id"])
                return [TextContent(type="text", text=json.dumps(res))]

            if name == "validate_migration":
                res = await engine.validate_migration(arguments["migration_id"])
                return [TextContent(type="text", text=json.dumps(res))]

            if name == "commit_migration":
                res = await engine.commit_migration(arguments["migration_id"])
                return [TextContent(type="text", text=json.dumps(res))]

            if name == "abort_migration":
                res = await engine.abort_migration(arguments["migration_id"])
                return [TextContent(type="text", text=json.dumps(res))]

            # ------------------------------------------------------------------
            # Phase 2.3 — Memory Replay
            # ------------------------------------------------------------------

            if name == "replay_observe":
                from trimcp.replay import ObservationalReplay
                ns_id = uuid.UUID(arguments["namespace_id"])
                start_seq = int(arguments.get("start_seq", 1))
                end_seq = int(arguments["end_seq"]) if "end_seq" in arguments else None
                agent_filter = arguments.get("agent_id_filter")
                max_events = int(arguments.get("max_events", 500))

                replay = ObservationalReplay(pool=engine.pg_pool)
                lines: list[str] = []
                count = 0
                async for item in replay.execute(
                    source_namespace_id=ns_id,
                    start_seq=start_seq,
                    end_seq=end_seq,
                    agent_id_filter=agent_filter,
                ):
                    lines.append(json.dumps(item))
                    if item.get("type") == "event":
                        count += 1
                        if count >= max_events:
                            # Append a truncation notice and break; the generator
                            # will be GC'd and close cleanly via aclose().
                            lines.append(json.dumps({
                                "type": "truncated",
                                "reason": "max_events_reached",
                                "events_returned": count,
                            }))
                            break
                return [TextContent(type="text", text="\n".join(lines))]

            if name == "replay_fork":
                from trimcp.replay import ForkedReplay, _create_run
                src_ns = uuid.UUID(arguments["source_namespace_id"])
                tgt_ns = uuid.UUID(arguments["target_namespace_id"])
                fork_seq = int(arguments["fork_seq"])
                start_seq = int(arguments.get("start_seq", 1))
                replay_mode = arguments.get("replay_mode", "deterministic")
                config_overrides = arguments.get("config_overrides")
                agent_filter = arguments.get("agent_id_filter")

                # Pre-create the replay_runs row so we can return run_id
                # immediately — before the background task has had a chance to run.
                async with engine.pg_pool.acquire() as pre_conn:
                    fork_run_id = await _create_run(
                        pre_conn,
                        source_namespace_id=src_ns,
                        target_namespace_id=tgt_ns,
                        mode="forked",
                        replay_mode=replay_mode,
                        start_seq=start_seq,
                        end_seq=fork_seq,
                        divergence_seq=fork_seq,
                        config_overrides=config_overrides,
                    )

                replay = ForkedReplay(pool=engine.pg_pool)

                async def _run_fork() -> None:
                    try:
                        async for _ in replay.execute(
                            source_namespace_id=src_ns,
                            target_namespace_id=tgt_ns,
                            fork_seq=fork_seq,
                            start_seq=start_seq,
                            replay_mode=replay_mode,
                            config_overrides=config_overrides,
                            agent_id_filter=agent_filter,
                            _existing_run_id=fork_run_id,
                        ):
                            pass  # progress is persisted to replay_runs in DB
                    except Exception:
                        log.exception(
                            "Background ForkedReplay task failed run_id=%s", fork_run_id
                        )

                asyncio.create_task(_run_fork(), name=f"fork-{fork_run_id}")
                return [TextContent(type="text", text=json.dumps({
                    "status":           "started",
                    "run_id":           str(fork_run_id),
                    "source_namespace": str(src_ns),
                    "target_namespace": str(tgt_ns),
                    "fork_seq":         fork_seq,
                    "replay_mode":      replay_mode,
                }))]

            if name == "replay_status":
                from trimcp.replay import get_run_status, ReplayRunNotFoundError
                try:
                    status = await get_run_status(
                        pool=engine.pg_pool,
                        run_id=uuid.UUID(arguments["run_id"]),
                    )
                    return [TextContent(type="text", text=json.dumps(status))]
                except ReplayRunNotFoundError as exc:
                    return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

            if name == "get_event_provenance":
                from trimcp.replay import get_event_provenance
                provenance = await get_event_provenance(
                    pool=engine.pg_pool,
                    memory_id=uuid.UUID(arguments["memory_id"]),
                )
                return [TextContent(type="text", text=json.dumps(provenance))]

            # ------------------------------------------------------------------
            # Phase 3.1 — A2A (Agent-to-Agent) Protocol Tools
            # ------------------------------------------------------------------

            if name == "a2a_create_grant":
                from trimcp.a2a import (
                    A2AGrantRequest, A2AScope, create_grant,
                )
                from trimcp.auth import NamespaceContext
                ns_id = uuid.UUID(arguments["namespace_id"])
                agent_id_val = arguments.get("agent_id", "default")
                caller_ctx = NamespaceContext(
                    namespace_id=ns_id,
                    agent_id=agent_id_val,
                )
                scopes_raw = arguments.get("scopes", [])
                if isinstance(scopes_raw, str):
                    scopes_raw = json.loads(scopes_raw)
                scopes = [A2AScope.model_validate(s) for s in scopes_raw]
                req = A2AGrantRequest(
                    target_namespace_id=arguments.get("target_namespace_id"),
                    target_agent_id=arguments.get("target_agent_id"),
                    scopes=scopes,
                    expires_in_seconds=int(arguments.get("expires_in_seconds", 3600)),
                )
                async with engine.pg_pool.acquire() as conn:
                    resp = await create_grant(conn, caller_ctx, req)
                return [TextContent(type="text", text=json.dumps({
                    "grant_id": str(resp.grant_id),
                    "sharing_token": resp.sharing_token,
                    "expires_at": resp.expires_at.isoformat(),
                }))]

            if name == "a2a_revoke_grant":
                from trimcp.a2a import revoke_grant
                from trimcp.auth import NamespaceContext
                ns_id = uuid.UUID(arguments["namespace_id"])
                agent_id_val = arguments.get("agent_id", "default")
                grant_id = uuid.UUID(arguments["grant_id"])
                caller_ctx = NamespaceContext(
                    namespace_id=ns_id,
                    agent_id=agent_id_val,
                )
                async with engine.pg_pool.acquire() as conn:
                    revoked = await revoke_grant(conn, grant_id, caller_ctx)
                return [TextContent(type="text", text=json.dumps({
                    "grant_id": str(grant_id),
                    "revoked": revoked,
                }))]

            if name == "a2a_list_grants":
                from trimcp.a2a import list_grants
                from trimcp.auth import NamespaceContext
                ns_id = uuid.UUID(arguments["namespace_id"])
                agent_id_val = arguments.get("agent_id", "default")
                include_inactive = bool(arguments.get("include_inactive", False))
                caller_ctx = NamespaceContext(
                    namespace_id=ns_id,
                    agent_id=agent_id_val,
                )
                async with engine.pg_pool.acquire() as conn:
                    grants = await list_grants(conn, caller_ctx, include_inactive=include_inactive)
                return [TextContent(type="text", text=json.dumps(grants))]

            if name == "a2a_query_shared":
                from trimcp.a2a import (
                    verify_token, enforce_scope,
                    A2AAuthorizationError, A2AScopeViolationError,
                    A2A_CODE_UNAUTHORIZED, A2A_CODE_SCOPE_VIOLATION,
                )
                from trimcp.auth import NamespaceContext
                sharing_token = arguments["sharing_token"]
                query = arguments["query"]
                resource_type = arguments.get("resource_type", "namespace")
                resource_id = arguments.get("resource_id", "")
                top_k = int(arguments.get("top_k", 5))
                consumer_ns_id = uuid.UUID(arguments["consumer_namespace_id"])
                consumer_agent_id = arguments.get("consumer_agent_id", "default")
                consumer_ctx = NamespaceContext(
                    namespace_id=consumer_ns_id,
                    agent_id=consumer_agent_id,
                )
                async with engine.pg_pool.acquire() as conn:
                    try:
                        verified = await verify_token(conn, sharing_token, consumer_ctx)
                    except A2AAuthorizationError as exc:
                        raise ValueError(f"A2A authorization failure (-32010): {exc}")
                effective_resource_id = resource_id or str(verified.owner_namespace_id)
                try:
                    enforce_scope(verified.scopes, resource_type, effective_resource_id)
                except A2AScopeViolationError as exc:
                    raise ValueError(f"A2A scope violation (-32011): {exc}")
                results = await engine.semantic_search(
                    namespace_id=str(verified.owner_namespace_id),
                    agent_id=verified.owner_agent_id,
                    query=query,
                    top_k=top_k,
                )
                return [TextContent(type="text", text=json.dumps({
                    "grant_id": str(verified.grant_id),
                    "owner_namespace_id": str(verified.owner_namespace_id),
                    "results": results,
                }))]


            raise ValueError(f"Unknown tool: {name}")
        except Exception:
            await q_res.rollback()
            raise

    except (ValueError, TypeError) as e:
        es = str(e)
        if es.startswith(MCP_QUOTA_EXCEEDED_PREFIX):
            raise ValueError(es) from e
        raise ValueError(f"Invalid input: {e}") from e
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

    from trimcp.re_embedder import start_re_embedder
    start_re_embedder(engine.pg_pool, engine.mongo_client)
    log.info("Re-embedder background task started.")

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
