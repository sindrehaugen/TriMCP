"""
Tri-Stack MCP Server
Wraps TriStackEngine in the official MCP Python SDK (stdio transport).
Exposes MCP tools to any MCP-compatible LLM client (Claude Desktop, Cursor, etc.).
GC background task is co-launched on startup for absolute data purity.

HTTP HMAC auth and optional Redis-backed replay protection (``NonceStore``) apply
only to the Starlette **admin** stack in ``admin_server.py``. This process does not
mount ``HMACAuthMiddleware``. When ``TRIMCP_DISTRIBUTED_REPLAY`` is truthy and
``REDIS_URL`` is configured, admins should run the HTTP admin server with that env set
so all instances share the same nonce ledger.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from trimcp import (
    TriStackEngine,
    a2a_mcp_handlers,
    admin_mcp_handlers,
    bridge_mcp_handlers,
    code_mcp_handlers,
    contradiction_mcp_handlers,
    graph_mcp_handlers,
    memory_mcp_handlers,
    migration_mcp_handlers,
    replay_mcp_handlers,
    run_gc_loop,
    snapshot_mcp_handlers,
)
from trimcp.auth import RateLimitError, ScopeError
from trimcp.config import cfg, redact_secrets_in_text
from trimcp.mcp_errors import McpError, UnknownToolError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s %(message)s",
)
log = logging.getLogger("tri-stack-mcp")

# MCP / JSON-RPC client-visible prefix when ``consume_for_tool`` hits a hard limit.
MCP_QUOTA_EXCEEDED_PREFIX = "Resource quota exceeded (-32013)"

# Tools whose JSON-RPC payloads are keyed in Redis — quota must NOT run on cache hit (FIX-020).
_MCP_TOOL_RESPONSE_CACHE_TOOLS = frozenset(
    {"semantic_search", "search_codebase", "graph_search"}
)


async def _try_cached_mcp_tool_response(
    eng: TriStackEngine,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[list[TextContent] | None, str | None]:
    """Return cached MCP tool payloads before quota runs; misses return (None, redis_key).

    Naming note: callers treat a non-empty first element as cache hit."""
    from trimcp.mcp_args import build_cache_key

    if tool_name not in _MCP_TOOL_RESPONSE_CACHE_TOOLS:
        return None, None

    gen_raw = await eng.redis_client.get("mcp_cache_generation")
    gen_val = gen_raw.decode() if gen_raw else "0"
    ns_id = arguments.get("namespace_id")
    cache_key = build_cache_key(
        tool_name=tool_name,
        arguments=arguments,
        generation=gen_val,
        namespace_id=ns_id,
    )
    cached_raw = await eng.redis_client.get(cache_key)
    if not cached_raw:
        return None, cache_key

    ns_for_log = str(ns_id)[:8] if ns_id is not None else "global"
    log.info("API Cache hit for tool %s (ns=%s)", tool_name, ns_for_log)
    return (
        [TextContent(type="text", text=cached_raw.decode())],
        cache_key,
    )


async def _consume_quota_for_mcp_tool(
    pg_pool,
    tool_name: str,
    arguments: dict[str, Any],
) -> None:
    from trimcp import quotas as _quotas

    try:
        await _quotas.consume_for_tool(pg_pool, tool_name, arguments)
    except _quotas.QuotaExceededError as exc:
        raise ValueError(f"{MCP_QUOTA_EXCEEDED_PREFIX}: {exc}") from exc


# --- Global engine instance (lifecycle managed by lifespan) ---
engine: TriStackEngine | None = None
app = Server("tri-stack-memory")


# --- Tool Definitions ---

_MIGRATION_TOOLS = [
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
]

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
                "namespace_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "content": {"type": "string"},
                "summary": {
                    "type": "string",
                    "description": "Short summary used for embedding",
                },
                "heavy_payload": {
                    "type": "string",
                    "description": "Full raw content to archive",
                },
                "content_type": {
                    "type": "string",
                    "enum": ["chat", "code"],
                    "description": "Type of content",
                },
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
                "namespace_id": {"type": "string"},
                "user_id": {"type": "string"},
                "session_id": {"type": "string"},
                "media_type": {"type": "string", "enum": ["audio", "video", "image"]},
                "file_path_on_disk": {
                    "type": "string",
                    "description": "Local path to the media file",
                },
                "summary": {
                    "type": "string",
                    "description": "AI-generated summary of the media content",
                },
            },
            "required": [
                "namespace_id",
                "user_id",
                "session_id",
                "media_type",
                "file_path_on_disk",
                "summary",
            ],
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
                "agent_id": {"type": "string"},
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Maximum results to return after offset",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Skip this many ranked hits before returning the page",
                },
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
                "filepath": {
                    "type": "string",
                    "description": "Absolute or relative path of the file",
                },
                "raw_code": {
                    "type": "string",
                    "description": "Full source code content",
                },
                "language": {
                    "type": "string",
                    "description": "Language: 'python', 'javascript', 'typescript', 'go', 'rust'",
                },
                "namespace_id": {
                    "type": "string",
                    "description": "Namespace ID for scoping.",
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional. Required when private=true — scopes this index to the user.",
                },
                "private": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, index is private to user_id (shared corpus uses user_id unset).",
                },
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
                "job_id": {
                    "type": "string",
                    "description": "The job_id returned by index_code_file",
                },
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
                "query": {
                    "type": "string",
                    "description": "Natural language description of the code to find",
                },
                "namespace_id": {
                    "type": "string",
                    "description": "Namespace ID to search within.",
                },
                "language_filter": {
                    "type": "string",
                    "description": "Optional: filter by language ('python', 'javascript')",
                },
                "top_k": {"type": "integer", "default": 5},
                "user_id": {
                    "type": "string",
                    "description": "Optional. Required when private=true — searches only that user's private index.",
                },
                "private": {
                    "type": "boolean",
                    "default": False,
                    "description": "When false (default), search the shared corpus only. When true, search only chunks for user_id.",
                },
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
                "query": {
                    "type": "string",
                    "description": "Natural language query to anchor the graph search",
                },
                "namespace_id": {
                    "type": "string",
                    "description": "Namespace ID to search within.",
                },
                "max_depth": {
                    "type": "integer",
                    "default": 2,
                    "description": "BFS hop depth (1-3 recommended)",
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional. When supplied, restricts hydrated sources to this user.",
                },
                "private": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, only hydrate sources owned by user_id.",
                },
                "as_of": {
                    "type": "string",
                    "format": "date-time",
                    "description": (
                        "Optional ISO 8601 UTC timestamp (e.g. '2026-01-15T10:00:00Z'). "
                        "Traverses the knowledge graph as it existed at or before this instant. "
                        "Omit to traverse the current graph."
                    ),
                },
                "max_edges_per_node": {
                    "type": "integer",
                    "default": 512,
                    "minimum": 1,
                    "maximum": 2048,
                    "description": (
                        "Max incident edges loaded per BFS hop (SQL LIMIT, highest confidence first). "
                        "Prevents OOM on hub nodes."
                    ),
                },
                "edge_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5000,
                    "description": (
                        "Optional page size on the deduplicated edge list (omit for full page from edge_offset)."
                    ),
                },
                "edge_offset": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Offset into deduplicated edges when using edge_limit.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_recent_context",
        description=(
            "Retrieve the N most recent episodic memories for an agent. "
            "Useful for manual context reconstruction or auditing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string"},
                "agent_id": {
                    "type": "string",
                    "description": "Agent identifier; 'default' if not specified.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Skip this many most-recent rows before returning limit rows",
                },
                "as_of": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Optional point-in-time reference (Phase 2.2).",
                },
            },
            "required": ["namespace_id"],
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
                "bridge_id": {
                    "type": "string",
                    "description": "UUID from connect_bridge",
                },
                "provider": {
                    "type": "string",
                    "enum": ["sharepoint", "gdrive", "dropbox"],
                },
                "authorization_code": {
                    "type": "string",
                    "description": "OAuth code from redirect",
                },
                "code": {
                    "type": "string",
                    "description": "Alias for authorization_code",
                },
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
                "resolution": {
                    "type": "string",
                    "description": "Filter by resolution status (e.g. 'unresolved')",
                },
                "agent_id": {"type": "string"},
            },
            "required": ["namespace_id"],
        },
    ),
    Tool(
        name="resolve_contradiction",
        description="[Phase 1.3] Resolve a contradiction. Requires namespace_id for RLS enforcement.",
        inputSchema={
            "type": "object",
            "properties": {
                "contradiction_id": {"type": "string"},
                "namespace_id": {
                    "type": "string",
                    "description": "Tenant namespace (RLS-enforced — only contradictions in the caller's namespace can be resolved).",
                },
                "resolution": {
                    "type": "string",
                    "enum": [
                        "resolved_a",
                        "resolved_b",
                        "both_valid",
                        "false_positive",
                    ],
                },
                "resolved_by": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": [
                "contradiction_id",
                "namespace_id",
                "resolution",
                "resolved_by",
            ],
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
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["memory_id", "namespace_id", "agent_id", "admin_api_key"],
        },
    ),
    # Migration tools are appended conditionally below
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
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["namespace_id", "admin_api_key"],
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
                        "Optional overrides for re-execute mode only. "
                        "Allowed keys: llm_provider (enum: local-cognitive-model, openai, "
                        "azure_openai, deepseek, moonshot_kimi, openai_compatible, "
                        "google_gemini, anthropic), llm_model, llm_credentials, llm_temperature. "
                        "Extra keys and free-text prompt edits are rejected."
                    ),
                },
                "agent_id_filter": {
                    "type": "string",
                    "description": "Optional: replay only events from this agent_id.",
                },
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": [
                "source_namespace_id",
                "target_namespace_id",
                "fork_seq",
                "admin_api_key",
            ],
        },
    ),
    Tool(
        name="replay_reconstruct",
        description=(
            "[Phase 2.3] Reconstruct a byte-identical state by replaying an empty target "
            "namespace from the source namespace's event_log up to end_seq.  All events "
            "are applied deterministically — no LLM re-execution.  UUIDs are remapped "
            "(original → new) to avoid constraint violations."
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
                    "description": "Namespace to replay events INTO (should be empty for true reconstruction).",
                },
                "end_seq": {
                    "type": "integer",
                    "description": "Inclusive upper bound: replay events with event_seq <= end_seq.",
                },
                "start_seq": {
                    "type": "integer",
                    "default": 1,
                    "description": "Inclusive lower bound on event_seq (default: 1).",
                },
                "agent_id_filter": {
                    "type": "string",
                    "description": "Optional: replay only events from this agent_id.",
                },
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": [
                "source_namespace_id",
                "target_namespace_id",
                "end_seq",
                "admin_api_key",
            ],
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
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["run_id", "admin_api_key"],
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
                "namespace_id": {
                    "type": "string",
                    "description": "Owner namespace UUID.",
                },
                "agent_id": {"type": "string", "description": "Owner agent ID."},
                "scopes": {
                    "type": "array",
                    "description": "List of scope objects. Each has resource_type, resource_id, and permissions.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "resource_type": {
                                "type": "string",
                                "enum": ["namespace", "memory", "kg_node", "subgraph"],
                            },
                            "resource_id": {"type": "string"},
                            "permissions": {
                                "type": "array",
                                "items": {"type": "string", "enum": ["read"]},
                            },
                        },
                        "required": ["resource_type", "resource_id"],
                    },
                },
                "target_namespace_id": {
                    "type": "string",
                    "description": "Optional: restrict to a specific recipient namespace.",
                },
                "target_agent_id": {
                    "type": "string",
                    "description": "Optional: restrict to a specific recipient agent.",
                },
                "expires_in_seconds": {
                    "type": "integer",
                    "default": 3600,
                    "description": "Token lifetime (60–2592000 s).",
                },
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
                "namespace_id": {
                    "type": "string",
                    "description": "Owner namespace UUID.",
                },
                "agent_id": {"type": "string", "description": "Owner agent ID."},
                "grant_id": {
                    "type": "string",
                    "description": "UUID of the grant to revoke.",
                },
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
                "namespace_id": {
                    "type": "string",
                    "description": "Owner namespace UUID.",
                },
                "agent_id": {"type": "string", "description": "Owner agent ID."},
                "include_inactive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include revoked and expired grants for audit purposes.",
                },
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
                "sharing_token": {
                    "type": "string",
                    "description": "Token provided by the owning agent.",
                },
                "consumer_namespace_id": {
                    "type": "string",
                    "description": "UUID of the namespace consuming the token.",
                },
                "consumer_agent_id": {
                    "type": "string",
                    "description": "Agent ID of the consumer.",
                },
                "query": {
                    "type": "string",
                    "description": "Semantic search query string.",
                },
                "resource_type": {
                    "type": "string",
                    "enum": ["namespace", "memory", "kg_node", "subgraph"],
                    "default": "namespace",
                    "description": "Resource type to validate against granted scopes.",
                },
                "resource_id": {
                    "type": "string",
                    "description": "Specific resource ID to validate; omit for namespace-level grants.",
                },
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["sharing_token", "consumer_namespace_id", "query"],
        },
    ),
    Tool(
        name="manage_namespace",
        description="[ADMIN] Manage namespaces: create, list, grant, revoke, update_metadata.",
        inputSchema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["create", "list", "grant", "revoke", "update_metadata"],
                },
                "namespace_id": {"type": "string"},
                "create": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "parent_id": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["slug"],
                },
                "metadata_patch": {"type": "object"},
                "grantee_namespace_id": {"type": "string"},
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["command", "admin_api_key"],
        },
    ),
    Tool(
        name="verify_memory",
        description="[Phase 0.2] Verify the integrity and causal provenance of a memory.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "as_of": {"type": "string", "format": "date-time"},
            },
            "required": ["memory_id"],
        },
    ),
    Tool(
        name="trigger_consolidation",
        description="[ADMIN] Manually trigger a sleep-consolidation run for a namespace.",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string"},
                "since_timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Optional filter for events since this point.",
                },
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["namespace_id", "admin_api_key"],
        },
    ),
    Tool(
        name="consolidation_status",
        description="[ADMIN] Check the status of a consolidation run.",
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["run_id", "admin_api_key"],
        },
    ),
    Tool(
        name="manage_quotas",
        description="[ADMIN] Manage resource quotas for a namespace.",
        inputSchema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["set", "list", "delete", "reset"],
                },
                "namespace_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "resource_type": {
                    "type": "string",
                    "enum": ["llm_tokens", "storage_bytes", "memory_count"],
                },
                "limit": {"type": "integer"},
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["command", "namespace_id", "admin_api_key"],
        },
    ),
    Tool(
        name="rotate_signing_key",
        description="[ADMIN] Generate a new active signing key and retire the current one.",
        inputSchema={
            "type": "object",
            "properties": {
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["admin_api_key"],
        },
    ),
    Tool(
        name="get_health",
        description="[ADMIN] Comprehensive system health check (v1.0).",
        inputSchema={
            "type": "object",
            "properties": {
                "admin_api_key": {
                    "type": "string",
                    "description": "Server-side admin API key for elevated access",
                },
            },
            "required": ["admin_api_key"],
        },
    ),
    Tool(
        name="list_dlq",
        description="[ADMIN] List dead-letter queue entries (failed tasks that exhausted retries).",
        inputSchema={
            "type": "object",
            "properties": {
                "admin_api_key": {"type": "string", "description": "Admin API key"},
                "task_name": {"type": "string", "description": "Filter by task function name"},
                "status": {"type": "string", "enum": ["pending", "replayed", "purged"]},
                "limit": {"type": "integer", "default": 50},
                "offset": {"type": "integer", "default": 0},
            },
            "required": ["admin_api_key"],
        },
    ),
    Tool(
        name="replay_dlq",
        description="[ADMIN] Mark a dead-letter queue entry as replayed (re-enqueue manually).",
        inputSchema={
            "type": "object",
            "properties": {
                "admin_api_key": {"type": "string", "description": "Admin API key"},
                "dlq_id": {"type": "string", "description": "UUID of the DLQ entry to replay"},
            },
            "required": ["admin_api_key", "dlq_id"],
        },
    ),
    Tool(
        name="purge_dlq",
        description="[ADMIN] Permanently remove a dead-letter queue entry.",
        inputSchema={
            "type": "object",
            "properties": {
                "admin_api_key": {"type": "string", "description": "Admin API key"},
                "dlq_id": {"type": "string", "description": "UUID of the DLQ entry to purge"},
            },
            "required": ["admin_api_key", "dlq_id"],
        },
    ),
    Tool(
        name="create_snapshot",
        description="Create a named point-in-time reference (snapshot) for a namespace.",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string"},
                "name": {"type": "string"},
                "agent_id": {"type": "string", "default": "default"},
                "snapshot_at": {"type": "string", "format": "date-time"},
                "metadata": {"type": "object"},
            },
            "required": ["namespace_id", "name"],
        },
    ),
    Tool(
        name="list_snapshots",
        description="List all snapshots for a given namespace.",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string"},
            },
            "required": ["namespace_id"],
        },
    ),
    Tool(
        name="delete_snapshot",
        description="Delete a point-in-time reference (snapshot) for a namespace.",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string"},
                "snapshot_id": {"type": "string"},
            },
            "required": ["namespace_id", "snapshot_id"],
        },
    ),
    Tool(
        name="compare_states",
        description="Diff the memory state between two points in time.",
        inputSchema={
            "type": "object",
            "properties": {
                "namespace_id": {"type": "string"},
                "as_of_a": {"type": "string", "format": "date-time"},
                "as_of_b": {"type": "string", "format": "date-time"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 10},
            },
            "required": ["namespace_id", "as_of_a", "as_of_b"],
        },
    ),
]

# Conditionally include migration tools based on operator config.
if not cfg.TRIMCP_DISABLE_MIGRATION_MCP:
    TOOLS = TOOLS + _MIGRATION_TOOLS


# --- Tool Handlers ---


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


def _check_admin(arguments: dict[str, Any]) -> None:
    """Validate admin privileges against server-side authentication state.

    .. deprecated::
        Admin MCP handlers in :mod:`trimcp.admin_mcp_handlers` now use the
        ``@require_scope("admin")`` decorator instead.  This function remains
        for handlers that haven't been migrated yet (``unredact_memory``,
        replay handlers).  New admin tools MUST use the decorator.

    Authorisation order (first match wins):
      1. TRIMCP_ADMIN_OVERRIDE=true  — development bypass (INSECURE in production)
      2. TRIMCP_ADMIN_API_KEY        — constant-time comparison against the
         ``admin_api_key`` argument supplied by the MCP client.

    Only server-side state (environment) can confer admin rights. After a successful
    check, :func:`call_tool` passes :func:`_model_kwargs` (delegates to
    :func:`trimcp.mcp_args.model_kwargs`) into namespace/quota admin handlers so
    ``admin_api_key`` never reaches ``extra='forbid'`` models.

    Raises:
        ValueError:  -32001 when the caller is not authorised.
    """
    # 1. Dev override — intentionally first so local dev is frictionless
    if os.environ.get("TRIMCP_ADMIN_OVERRIDE") == "true":
        return

    # 2. Server-side API key validation
    server_key = os.environ.get("TRIMCP_ADMIN_API_KEY", "")
    if not server_key:
        raise ValueError(
            "Server misconfigured: TRIMCP_ADMIN_API_KEY is not set. "
            "Set the environment variable or enable TRIMCP_ADMIN_OVERRIDE for development. (-32001)"
        )

    provided_key: str | None = arguments.get("admin_api_key")
    if (
        not provided_key
        or not isinstance(provided_key, str)
        or not provided_key.strip()
    ):
        raise ValueError(
            "Unauthorized administrative attempt: missing admin_api_key (-32001)"
        )

    if not secrets.compare_digest(provided_key.strip(), server_key):
        log.warning("Admin auth rejected: invalid admin_api_key")
        raise ValueError(
            "Unauthorized administrative attempt: invalid admin_api_key (-32001)"
        )


def _model_kwargs(arguments: dict[str, Any]) -> dict[str, Any]:
    """Strip MCP auth-only keys before ``**`` into ``extra='forbid'`` domain models."""
    from trimcp.mcp_args import model_kwargs

    return model_kwargs(arguments)


# ── JSON-RPC 2.0 Error Response Helper ─────────────────────────────────────
# Standard error codes per JSON-RPC 2.0:
#   -32600  Invalid Request
#   -32601  Method not found
#   -32602  Invalid params
#   -32603  Internal error
# MCP extended codes (server-errors -32000..-32099):
#   -32001  Admin authentication required
#   -32005  Scope forbidden
#   -32013  Resource quota exceeded
#   -32029  Rate limit exceeded

# Regex to extract embedded MCP error codes from exception messages:
# e.g. "Unauthorized administrative attempt: missing admin_api_key (-32001)"
_MCP_ERROR_CODE_RE = re.compile(r"\((-32\d{3})\)")


def _extract_mcp_code(msg: str, default: int = -32602) -> int:
    """Extract an MCP extended error code embedded in an exception message.

    Some callers (e.g. ``_check_admin``) embed codes like ``(-32001)`` in
    their ``ValueError`` message strings.  This function extracts them so
    the JSON-RPC response preserves the intended error code.
    """
    m = _MCP_ERROR_CODE_RE.search(msg)
    if m:
        return int(m.group(1))
    return default


def _jsonrpc_error_response(
    code: int,
    message: str,
    *,
    detail: str | None = None,
    data: dict[str, Any] | None = None,
) -> list[TextContent]:
    """Return a JSON-RPC 2.0 error response as ``TextContent``.

    Args:
        code: Standard JSON-RPC 2.0 or MCP extended error code.
        message: Short human-readable error summary.
        detail: Optional detail string included under ``error.data.detail``.
        data: Optional extra fields merged into ``error.data``.

    Returns:
        A single-element ``TextContent`` list containing the serialized
        JSON-RPC error object.  The MCP SDK treats this as a *successful*
        tool result; the error payload is for the *client* to interpret.
    """
    error: dict[str, Any] = {"code": code, "message": message}
    error_data: dict[str, Any] = {}
    if detail is not None:
        error_data["detail"] = detail
    if data:
        error_data.update(data)
    if error_data:
        error["data"] = error_data
    return [
        TextContent(
            type="text",
            text=json.dumps({"jsonrpc": "2.0", "error": error}),
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if engine is None:
        return _jsonrpc_error_response(
            -32603,
            "Internal error",
            detail="Engine not initialized",
        )

    from trimcp.observability import instrument_tool_call

    async with instrument_tool_call(name):
        try:
            _base_mutation_tools = {
                "store_memory",
                "store_media",
                "index_code_file",
                "connect_bridge",
                "complete_bridge_auth",
                "disconnect_bridge",
                "force_resync_bridge",
                "create_snapshot",
                "delete_snapshot",
                "manage_namespace",
                "manage_quotas",
                "rotate_signing_key",
                "trigger_consolidation",
                "resolve_contradiction",
                "boost_memory",
                "forget_memory",
                "a2a_create_grant",
                "a2a_revoke_grant",
                "unredact_memory",
                "replay_reconstruct",
            }
            if not cfg.TRIMCP_DISABLE_MIGRATION_MCP:
                _base_mutation_tools |= {
                    "start_migration",
                    "commit_migration",
                    "abort_migration",
                }
            MUTATION_TOOLS = _base_mutation_tools

            if name in MUTATION_TOOLS:
                from trimcp.mcp_args import bump_cache_generation, purge_document_cache

                await bump_cache_generation(engine.redis_client)

                # Document-level cache purge: when a specific memory or snapshot
                # is deleted, evict any cached responses that referenced it.
                doc_id = arguments.get("memory_id") or arguments.get("snapshot_id")
                if name in ("forget_memory", "delete_snapshot") and doc_id:
                    ns_id = arguments.get("namespace_id")
                    if ns_id:
                        try:
                            await purge_document_cache(
                                engine.redis_client,
                                namespace_id=str(ns_id),
                                memory_id=str(doc_id),
                            )
                        except Exception as exc:
                            log.warning(
                                "%s: document cache purge failed: %s",
                                name,
                                exc,
                            )

            # --- API response cache (before quota — FIX-020) ---
            cached_payload, cache_key = await _try_cached_mcp_tool_response(
                engine, name, arguments
            )
            if cached_payload is not None:
                return cached_payload

            # Quota is incremented only on cache miss, immediately before the tool runs.
            # Never increment on cache hit — see FIX-020.
            await _consume_quota_for_mcp_tool(engine.pg_pool, name, arguments)

            # --- Tool dispatch ---
            try:
                if name == "store_memory":
                    result_text = await memory_mcp_handlers.handle_store_memory(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "store_media":
                    result_text = await memory_mcp_handlers.handle_store_media(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "semantic_search":
                    result_text = await memory_mcp_handlers.handle_semantic_search(
                        engine, arguments
                    )
                    if cache_key:
                        await engine.redis_client.setex(cache_key, 300, result_text)
                    return [TextContent(type="text", text=result_text)]

                if name == "index_code_file":
                    result_text = await code_mcp_handlers.handle_index_code_file(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "check_indexing_status":
                    result_text = await code_mcp_handlers.handle_check_indexing_status(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "search_codebase":
                    result_text = await code_mcp_handlers.handle_search_codebase(
                        engine, arguments
                    )
                    if cache_key:
                        await engine.redis_client.setex(cache_key, 300, result_text)
                    return [TextContent(type="text", text=result_text)]

                if name == "graph_search":
                    result_text = await graph_mcp_handlers.handle_graph_search(
                        engine, arguments
                    )
                    if cache_key:
                        await engine.redis_client.setex(cache_key, 300, result_text)
                    return [TextContent(type="text", text=result_text)]

                if name == "get_recent_context":
                    result_text = await memory_mcp_handlers.handle_get_recent_context(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "connect_bridge":
                    text = await bridge_mcp_handlers.connect_bridge(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "complete_bridge_auth":
                    text = await bridge_mcp_handlers.complete_bridge_auth(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=text)]

                if name == "list_bridges":
                    text = await bridge_mcp_handlers.list_bridges(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "disconnect_bridge":
                    text = await bridge_mcp_handlers.disconnect_bridge(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=text)]

                if name == "force_resync_bridge":
                    text = await bridge_mcp_handlers.force_resync_bridge(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=text)]

                if name == "bridge_status":
                    text = await bridge_mcp_handlers.bridge_status(engine, arguments)
                    return [TextContent(type="text", text=text)]

                if name == "boost_memory":
                    result_text = await memory_mcp_handlers.handle_boost_memory(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "forget_memory":
                    result_text = await memory_mcp_handlers.handle_forget_memory(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "list_contradictions":
                    result_text = (
                        await contradiction_mcp_handlers.handle_list_contradictions(
                            engine, arguments
                        )
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "resolve_contradiction":
                    result_text = (
                        await contradiction_mcp_handlers.handle_resolve_contradiction(
                            engine, arguments
                        )
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "unredact_memory":
                    _check_admin(arguments)
                    result_text = await memory_mcp_handlers.handle_unredact_memory(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name in (
                    "start_migration",
                    "migration_status",
                    "validate_migration",
                    "commit_migration",
                    "abort_migration",
                ):
                    if cfg.TRIMCP_DISABLE_MIGRATION_MCP:
                        return [
                            TextContent(
                                type="text",
                                text="Migration tools are disabled (TRIMCP_DISABLE_MIGRATION_MCP=true).",
                            )
                        ]
                    if name == "start_migration":
                        result_text = await migration_mcp_handlers.handle_start_migration(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]
                    if name == "migration_status":
                        result_text = await migration_mcp_handlers.handle_migration_status(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]
                    if name == "validate_migration":
                        result_text = (
                            await migration_mcp_handlers.handle_validate_migration(
                                engine, arguments
                            )
                        )
                        return [TextContent(type="text", text=result_text)]
                    if name == "commit_migration":
                        result_text = await migration_mcp_handlers.handle_commit_migration(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]
                    if name == "abort_migration":
                        result_text = await migration_mcp_handlers.handle_abort_migration(
                            engine, arguments
                        )
                        return [TextContent(type="text", text=result_text)]

                if name == "replay_observe":
                    _check_admin(arguments)
                    result_text = await replay_mcp_handlers.handle_replay_observe(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "replay_reconstruct":
                    _check_admin(arguments)
                    result_text = await replay_mcp_handlers.handle_replay_reconstruct(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "replay_fork":
                    _check_admin(arguments)
                    result_text = await replay_mcp_handlers.handle_replay_fork(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "replay_status":
                    _check_admin(arguments)
                    result_text = await replay_mcp_handlers.handle_replay_status(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "get_event_provenance":
                    result_text = await replay_mcp_handlers.handle_get_event_provenance(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "a2a_create_grant":
                    result_text = await a2a_mcp_handlers.handle_a2a_create_grant(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "a2a_revoke_grant":
                    result_text = await a2a_mcp_handlers.handle_a2a_revoke_grant(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "a2a_list_grants":
                    result_text = await a2a_mcp_handlers.handle_a2a_list_grants(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "a2a_query_shared":
                    result_text = await a2a_mcp_handlers.handle_a2a_query_shared(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "manage_namespace":
                    result_text = await admin_mcp_handlers.handle_manage_namespace(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "verify_memory":
                    result_text = await admin_mcp_handlers.handle_verify_memory(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "trigger_consolidation":
                    result_text = await admin_mcp_handlers.handle_trigger_consolidation(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "consolidation_status":
                    result_text = await admin_mcp_handlers.handle_consolidation_status(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "manage_quotas":
                    result_text = await admin_mcp_handlers.handle_manage_quotas(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "rotate_signing_key":
                    result_text = await admin_mcp_handlers.handle_rotate_signing_key(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "get_health":
                    result_text = await admin_mcp_handlers.handle_get_health(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "create_snapshot":
                    result_text = await snapshot_mcp_handlers.handle_create_snapshot(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "list_snapshots":
                    result_text = await snapshot_mcp_handlers.handle_list_snapshots(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "delete_snapshot":
                    result_text = await snapshot_mcp_handlers.handle_delete_snapshot(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "compare_states":
                    result_text = await snapshot_mcp_handlers.handle_compare_states(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "list_dlq":
                    result_text = await admin_mcp_handlers.handle_list_dlq(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "replay_dlq":
                    result_text = await admin_mcp_handlers.handle_replay_dlq(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                if name == "purge_dlq":
                    result_text = await admin_mcp_handlers.handle_purge_dlq(
                        engine, arguments
                    )
                    return [TextContent(type="text", text=result_text)]

                raise UnknownToolError(name)
            except Exception:
                await q_res.rollback()
                raise

        except McpError as e:
            return _jsonrpc_error_response(e.code, e.message, data=e.data)
        except ScopeError as e:
            return _jsonrpc_error_response(
                -32005,
                "Scope forbidden",
                detail=str(e),
            )
        except RateLimitError as e:
            return _jsonrpc_error_response(
                -32029,
                "Rate limit exceeded",
                detail=str(e),
            )
        except (ValueError, TypeError) as e:
            msg = str(e)
            if msg.startswith(MCP_QUOTA_EXCEEDED_PREFIX):
                return _jsonrpc_error_response(
                    -32013,
                    "Resource quota exceeded",
                    detail=msg,
                )
            if msg.startswith("Rate limit exceeded"):
                return _jsonrpc_error_response(
                    -32029,
                    "Rate limit exceeded",
                    detail=msg,
                )
            # Check for embedded MCP error codes (e.g. (-32001) from _check_admin)
            mcp_code = _extract_mcp_code(msg)
            if mcp_code != -32602:
                return _jsonrpc_error_response(
                    mcp_code,
                    msg,
                    detail=msg,
                )
            return _jsonrpc_error_response(
                -32602,
                "Invalid params",
                detail=msg,
            )
        except Exception as e:
            log.exception("Unhandled error in tool '%s'", name)
            return _jsonrpc_error_response(
                -32603,
                "Internal error",
                data={
                    "type": type(e).__name__,
                    "detail": str(e),
                },
            )


# --- Startup / Shutdown ---


def _assert_admin_override_not_in_production() -> None:
    """Raise at startup if TRIMCP_ADMIN_OVERRIDE is active in production.

    This guard prevents a development shortcut from silently bypassing
    authentication in production deployments. See FIX-039.
    """
    if os.getenv("TRIMCP_ADMIN_OVERRIDE") and os.getenv("ENVIRONMENT", "dev") == "prod":
        raise RuntimeError(
            "TRIMCP_ADMIN_OVERRIDE must not be set when ENVIRONMENT=prod. "
            "Remove this environment variable from the production configuration."
        )


async def main():
    global engine
    _assert_admin_override_not_in_production()
    engine = TriStackEngine()

    from trimcp.observability import init_observability

    init_observability()
    log.info("Observability layer initialized.")

    try:
        await engine.connect()
    except Exception as exc:
        log.critical("FATAL: Startup failure: %s", redact_secrets_in_text(str(exc)))
        sys.exit(1)

    log.info("TriStackEngine connected to all database layers.")

    from trimcp.background_task_manager import create_tracked_task

    gc_task = await create_tracked_task(run_gc_loop(), name="gc_loop")
    log.info("GC background task started.")

    from trimcp.re_embedder import start_re_embedder

    start_re_embedder(engine.pg_pool, engine.mongo_client)
    log.info("Re-embedder background task started.")

    try:
        async with stdio_server() as (read_stream, write_stream):
            log.info("MCP server listening on stdio.")
            await app.run(
                read_stream, write_stream, app.create_initialization_options()
            )
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
