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
``QuotaExceededError``  -32013   Resource quota exceeded
``ValueError``          -32602   Invalid parameters
``TypeError``           -32602   Invalid parameters
``KeyError``            -32602   Invalid parameters (missing field, name not exposed)
``UnknownToolError``  -32601   Method not found
Everything else       -32603   Internal error
====================  =======  ===========================
"""

from __future__ import annotations

import functools
import inspect
import logging
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import ValidationError

from trimcp.auth import RateLimitError, ScopeError
from trimcp.config import cfg
from trimcp.quotas import QuotaExceededError

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


def client_visible_detail(message: str | None) -> str | None:
    """Return *message* for MCP clients only when ``cfg.IS_DEV`` is true."""
    if not message or not cfg.IS_DEV:
        return None
    return message


def internal_error_data(exc: Exception, *, request_id: str | None = None) -> dict[str, Any]:
    """Build a production-safe ``error.data`` payload for uncaught handler failures."""
    rid = request_id or str(uuid.uuid4())
    data: dict[str, Any] = {
        "reason": "internal_error",
        "type": type(exc).__name__,
        "request_id": rid,
    }
    detail = client_visible_detail(str(exc))
    if detail is not None:
        data["detail"] = detail
    return data


def invalid_arguments_data(exc: Exception) -> dict[str, Any]:
    """Build ``error.data`` for ``ValueError`` / ``TypeError`` without leaking in prod."""
    data: dict[str, Any] = {"reason": "invalid_arguments"}
    detail = client_visible_detail(str(exc))
    if detail is not None:
        data["detail"] = detail
    return data


def merge_client_error_data(
    base: dict[str, Any] | None,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """Merge optional client ``detail`` into JSON-RPC error data (dev-only for strings)."""
    merged: dict[str, Any] = dict(base or {})
    visible = client_visible_detail(detail)
    if visible is not None:
        merged["detail"] = visible
    return merged


# ---------------------------------------------------------------------------
# @mcp_handler decorator
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


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

    The wrapper handles both async and sync handlers via ``inspect.iscoroutine``,
    though all production MCP handlers are expected to be async.
    """

    @functools.wraps(handler_fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            result = handler_fn(*args, **kwargs)
            if inspect.iscoroutine(result):
                return await result
            return result
        except (ScopeError, RateLimitError, McpError):
            # Already typed — propagate to call_tool unchanged.
            raise
        except ValidationError as e:
            raise McpError(
                MCP_INVALID_PARAMS,
                "Invalid parameters",
                data={
                    "reason": "validation_error",
                    "errors": e.errors(include_url=False),
                },
            )
        except QuotaExceededError:
            # Must precede ValueError — QuotaExceededError is a ValueError subclass.
            raise McpError(
                MCP_QUOTA_EXCEEDED,
                "Resource quota exceeded",
                data={"reason": "quota_exceeded"},
            )
        except KeyError:
            # Separate handler: str(KeyError) echoes field names ('secret_key').
            raise McpError(
                MCP_INVALID_PARAMS,
                "Invalid parameters",
                data={"reason": "missing_field"},
            )
        except (ValueError, TypeError) as e:
            raise McpError(
                MCP_INVALID_PARAMS,
                "Invalid parameters",
                data=invalid_arguments_data(e),
            )
        except Exception as e:
            if type(e).__name__ == "A2AAuthorizationError":
                raise McpError(
                    -32010,
                    "A2A authorization failure",
                    data={"reason": str(e)},
                )
            if type(e).__name__ == "A2AScopeViolationError":
                raise McpError(
                    -32011,
                    "Scope violation",
                    data={"reason": str(e)},
                )
            request_id = str(uuid.uuid4())
            log.exception(
                "Handler %s failed request_id=%s",
                handler_fn.__name__,
                request_id,
            )
            raise McpError(
                MCP_INTERNAL_ERROR,
                "Internal error",
                data=internal_error_data(e, request_id=request_id),
            )

    return wrapper  # type: ignore[return-value]
