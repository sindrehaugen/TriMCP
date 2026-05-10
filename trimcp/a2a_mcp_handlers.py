"""
MCP tool handlers for Agent-to-Agent (A2A) sharing (§7). Extracted from server.py:call_tool().

Clean Code SRP: Each handler is a thin orchestrator that:
  1. Extracts and validates arguments via typed helpers
  2. Delegates to a single domain function
  3. Serialises the response
Transport logic (args → typed objects) and domain logic (typed objects → result)
are fully separated. All dependencies are module-level imports.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from trimcp.a2a import (
    A2AGrantRequest,
    A2AGrantResponse,
    create_grant,
    enforce_scope,
    list_grants,
    revoke_grant,
    verify_token,
)
from trimcp.mcp_errors import mcp_handler
from trimcp.mcp_utils import build_caller_context as _build_caller_context
from trimcp.mcp_utils import parse_scopes as _parse_scopes
from trimcp.orchestrator import TriStackEngine

log = logging.getLogger("trimcp.a2a_mcp_handlers")

# ---------------------------------------------------------------------------
# Private helpers — argument extraction (transport concern)
# ---------------------------------------------------------------------------


def _build_grant_request(arguments: dict[str, Any]) -> A2AGrantRequest:
    """Build a typed A2AGrantRequest from raw MCP arguments."""
    return A2AGrantRequest(
        target_namespace_id=arguments.get("target_namespace_id"),
        target_agent_id=arguments.get("target_agent_id"),
        scopes=_parse_scopes(arguments.get("scopes", [])),
        expires_in_seconds=int(arguments.get("expires_in_seconds", 3600)),
    )


# ---------------------------------------------------------------------------
# Handlers — each calls exactly one domain function (SRP)
# ---------------------------------------------------------------------------


@mcp_handler
async def handle_a2a_create_grant(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Create an A2A sharing grant — generates a token for cross-namespace access."""
    caller_ctx = _build_caller_context(arguments)
    grant_request = _build_grant_request(arguments)

    async with engine.pg_pool.acquire() as conn:
        response: A2AGrantResponse = await create_grant(conn, caller_ctx, grant_request)

    return json.dumps(
        {
            "grant_id": str(response.grant_id),
            "sharing_token": response.sharing_token,
            "expires_at": response.expires_at.isoformat(),
        }
    )


@mcp_handler
async def handle_a2a_revoke_grant(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Revoke an active A2A sharing grant."""
    caller_ctx = _build_caller_context(arguments)

    async with engine.pg_pool.acquire() as conn:
        revoked = await revoke_grant(conn, uuid.UUID(arguments["grant_id"]), caller_ctx)

    return json.dumps({"revoked": revoked})


@mcp_handler
async def handle_a2a_list_grants(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """List all active A2A sharing grants owned by this namespace."""
    caller_ctx = _build_caller_context(arguments)
    include_inactive = bool(arguments.get("include_inactive", False))

    async with engine.pg_pool.acquire() as conn:
        grants = await list_grants(conn, caller_ctx, include_inactive=include_inactive)

    return json.dumps(grants)


@mcp_handler
async def handle_a2a_query_shared(
    engine: TriStackEngine, arguments: dict[str, Any]
) -> str:
    """Execute a semantic search against another agent's memories using an A2A token."""
    consumer_ctx = _build_caller_context(arguments)

    async with engine.pg_pool.acquire() as conn:
        verified = await verify_token(conn, arguments["sharing_token"], consumer_ctx)

    enforce_scope(
        verified.scopes,
        arguments.get("resource_type", "namespace"),
        arguments.get("resource_id") or str(verified.owner_namespace_id),
    )

    results = await engine.semantic_search(
        namespace_id=str(verified.owner_namespace_id),
        agent_id=verified.owner_agent_id,
        query=arguments["query"],
        limit=int(arguments.get("limit", arguments.get("top_k", 5))),
        offset=int(arguments.get("offset", 0)),
    )

    return json.dumps({"results": results})
