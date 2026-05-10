"""Shared MCP transport utilities.

Thin helpers that convert raw JSON-RPC arguments into typed domain objects.
Kept in a dedicated module so multiple handler modules can share them
without depending on each other's domain logic.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from trimcp.a2a import A2AScope
from trimcp.auth import NamespaceContext


def build_caller_context(arguments: dict[str, Any]) -> NamespaceContext:
    """Extract the caller's identity from raw MCP arguments."""
    return NamespaceContext(
        namespace_id=uuid.UUID(arguments["namespace_id"]),
        agent_id=arguments.get("agent_id", "default"),
    )


def parse_scopes(raw_scopes: Any) -> list[A2AScope]:
    """Parse A2A scopes from JSON string or list-of-dicts."""
    if isinstance(raw_scopes, str):
        raw_scopes = json.loads(raw_scopes)
    return [A2AScope.model_validate(s) for s in raw_scopes]
