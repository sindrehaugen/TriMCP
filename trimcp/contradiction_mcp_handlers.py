"""
MCP tool handlers for contradiction detection and resolution (§6). Extracted from
server.py:call_tool(). Follows the same pattern as bridge_mcp_handlers.py.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from trimcp.mcp_errors import mcp_handler
from trimcp.orchestrator import TriStackEngine

log = logging.getLogger("trimcp.contradiction_mcp_handlers")


@mcp_handler
async def handle_list_contradictions(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """List contradictions detected in the knowledge graph."""
    res = await engine.list_contradictions(
        namespace_id=arguments["namespace_id"],
        resolution=arguments.get("resolution"),
        agent_id=arguments.get("agent_id"),
    )
    return json.dumps(res, default=str)


@mcp_handler
async def handle_resolve_contradiction(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Resolve a detected contradiction with a resolution decision. RLS-enforced via namespace_id."""
    res = await engine.resolve_contradiction(
        contradiction_id=arguments["contradiction_id"],
        namespace_id=arguments["namespace_id"],
        resolution=arguments["resolution"],
        resolved_by=arguments["resolved_by"],
        note=arguments.get("note"),
    )
    return json.dumps(res, default=str)
