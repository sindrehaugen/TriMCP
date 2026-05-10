"""
MCP tool handlers for GraphRAG operations (§5). Extracted from server.py:call_tool().
Follows the same pattern as bridge_mcp_handlers.py — each handler receives the engine
and raw arguments dict, and returns a JSON string that call_tool() wraps in TextContent.

Uncle Bob SRP refactoring (2026-05-08):
  - Moved Pydantic import to module top-level (single import block).
  - Handler delegates the validated GraphSearchRequest directly to the engine — no
    field-by-field destructuring.
  - Eliminated legacy raw-dict access ``arguments.get("user_id")``.  The
    ``agent_id`` field on GraphSearchRequest is Pydantic-validated and flows
    through to the GraphOrchestrator as ``user_id``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from trimcp.mcp_errors import mcp_handler
from trimcp.models import GraphSearchRequest
from trimcp.orchestrator import TriStackEngine

log = logging.getLogger("trimcp.graph_mcp_handlers")


@mcp_handler
async def handle_graph_search(engine: TriStackEngine, arguments: dict[str, Any]) -> str:
    """GraphRAG traversal over the Knowledge Graph with temporal and user scoping."""
    req = GraphSearchRequest(**arguments)
    result = await engine.graph_search(req)
    return json.dumps(result, indent=2)
