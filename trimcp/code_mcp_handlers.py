"""
MCP tool handlers for code indexing operations (§4). Extracted from server.py:call_tool().
Follows the same pattern as bridge_mcp_handlers.py — each handler receives the engine
and raw arguments dict, and returns a JSON string that call_tool() wraps in TextContent.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from trimcp.mcp_errors import mcp_handler
from trimcp.models import IndexCodeFileRequest
from trimcp.orchestrator import TriStackEngine

log = logging.getLogger("trimcp.code_mcp_handlers")


@mcp_handler
async def handle_index_code_file(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Index a source code file into the Tri-Stack. Runs asynchronously — returns a job_id.

    Routes to the ``high_priority`` queue lane so user-facing MCP calls
    are never blocked behind batch indexing jobs (§5.4).
    """
    result = await engine.index_code_file(
        IndexCodeFileRequest(
            filepath=arguments["filepath"],
            raw_code=arguments["raw_code"],
            language=arguments["language"],
            namespace_id=arguments.get("namespace_id"),
            user_id=arguments.get("user_id"),
            private=bool(arguments.get("private", False)),
        ),
        priority=10,  # high-priority lane for real-time API calls
    )
    return json.dumps(result)


@mcp_handler
async def handle_check_indexing_status(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Check the status of a background indexing job."""
    result = await engine.get_job_status(job_id=arguments["job_id"])
    return json.dumps(result)


@mcp_handler
async def handle_search_codebase(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Semantic search over indexed code chunks. Returns matching functions/classes."""
    results = await engine.search_codebase(
        query=arguments["query"],
        namespace_id=arguments.get("namespace_id"),
        language_filter=arguments.get("language_filter"),
        top_k=int(arguments.get("top_k", 5)),
        user_id=arguments.get("user_id"),
        private=bool(arguments.get("private", False)),
    )
    return json.dumps(results)
