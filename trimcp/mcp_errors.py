"""
Centralised MCP error primitives — standard JSON-RPC 2.0 error codes and the
``@mcp_handler`` decorator for consistent error formatting across all handlers.

Usage
-----
Apply ``@mcp_handler`` to every MCP tool handler::

    from trimcp.mcp_errors import McpError, mcp_handler

    @mcp_handler
    async def handle_my_tool(engine, arguments) -> str:
        ...

On success the return value passes through unchanged.  On failure the decorator
catches all exceptions and re-raises an ``McpError`` with the appropriate
JSON-RPC error code.  ``server.py:call_tool()`` catches ``McpError`` and
formats it as a standard ``{"code": ..., "message": ..., "data": ...}`` response.

Mapping
-------
====================  =======  ===========================
Exception             Code     Message
====================  =======  ===========================
``McpError``          (as-is)  (as-is)
``ScopeError``        -32005   Scope forbidden
``RateLimitError``    -32029   Rate limit exceeded
``ValidationError``   -32602   Invalid parameters
``ValueError``        -32602   Invalid parameters
``TypeError``         -32602   Invalid parameters
``KeyError``          -32602   Invalid parameters
``UnknownToolError``  -32601   Method not found
Everything else       -32603   Internal error
====================  =======  ===========================
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import ValidationError

from trimcp.auth import RateLimitError, ScopeError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 standard error codes
# ---------------------------------------------------------------------------
MCP_PARSE_ERROR: int = -32700
MCP_INVALID_REQUEST: int = -32600
MCP_METHOD_NOT_FOUND: int = -32601
MCP_INVALID_PARAMS: int = -32602
MCP_INTERNAL_ERROR: int = -32603

# ---------------------------------------------------------------------------
# MCP extended error codes (server-defined range -32000 to -32099)
# ---------------------------------------------------------------------------
MCP_AUTH_FAILED: int = -32001
MCP_REPLAY_DETECTED: int = -32002
MCP_SCOPE_FORBIDDEN: int = -32005
MCP_QUOTA_EXCEEDED: int = -32013
MCP_RATE_LIMITED: int = -32029


class McpError(Exception):
    """Exception carrying a JSON-RPC 2.0 error code and structured data.

    Raise this inside an ``@mcp_handler``-decorated handler to return a
    specific error code and message.  ``call_tool()`` catches it and formats
    it as a standard ``{"jsonrpc": "2.0", "error": {"code": ..., "message": ...}}``
    response.

    Attributes:
        code:    Standard JSON-RPC 2.0 or MCP extended error code.
        message: Short human-readable error summary.
        data:    Optional dict merged into the ``error.data`` field.
    """

    def __init__(
        self,
        code: int,
        message: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[MCP {code}] {message}")


class UnknownToolError(McpError):
    """Raised when ``call_tool()`` receives a tool name with no registered handler."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(MCP_METHOD_NOT_FOUND, f"Unknown tool: {tool_name}")


# ---------------------------------------------------------------------------
# @mcp_handler decorator
# ---------------------------------------------------------------------------

F = TypeVar("F", bound="Callable[..., Any]")  # noqa: F723 — forward ref for type hint


def mcp_handler(handler_fn: F) -> F:
    """Decorator: catch exceptions in an MCP handler and raise ``McpError``.

    On success the return value is passed through unchanged.
    On failure a typed ``McpError`` is raised so ``call_tool()`` can format it
    as a consistent JSON-RPC 2.0 error response.

    The decorator respects the existing exception class hierarchy so:
    - ``ScopeError`` / ``RateLimitError`` from earlier decorators (``@require_scope``)
      are propagated untouched.
    - ``McpError`` from explicit raises is propagated as-is.
    - All other exceptions are categorised by type.
    """

    @functools.wraps(handler_fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await handler_fn(*args, **kwargs)
        except (ScopeError, RateLimitError, McpError):
            # Already typed — let call_tool format it.
            raise
        except ValidationError as e:
            raise McpError(
                MCP_INVALID_PARAMS,
                "Invalid parameters",
                data={"detail": e.errors(include_url=False)},
            )
        except (ValueError, TypeError, KeyError) as e:
            msg = str(e)
            # Preserve quota-exceeded prefix for the call_tool check
            if msg.startswith("Resource quota exceeded"):
                raise McpError(
                    MCP_QUOTA_EXCEEDED, "Resource quota exceeded", data={"detail": msg}
                )
            raise McpError(
                MCP_INVALID_PARAMS,
                "Invalid parameters",
                data={"detail": msg},
            )
        except Exception as e:
            log.exception("Handler %s failed", handler_fn.__name__)
            raise McpError(
                MCP_INTERNAL_ERROR,
                "Internal error",
                data={"type": type(e).__name__, "detail": str(e)},
            )

    return wrapper  # type: ignore[return-value]
