"""
Phase 3.1 — A2A (Agent-to-Agent) Protocol

Facilitates secure memory sharing between entirely separate AI agents.
Provides a cryptographic handshake allowing Agent A to grant read scopes
to Agent B for specific namespaces, memories, KG nodes, or subgraphs.

JSON-RPC 2.0 error codes defined here:
  -32010  Unauthorized — token missing, invalid, expired, or revoked
  -32011  Scope violation — resource not covered by the granted scopes
  -32012  Bad skill / bad request parameters
"""

import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

import asyncpg
from pydantic import BaseModel, Field

from trimcp.auth import NamespaceContext

log = logging.getLogger("trimcp.a2a")

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 error codes
# ---------------------------------------------------------------------------
A2A_CODE_UNAUTHORIZED = -32010    # token invalid / expired / revoked / constraints
A2A_CODE_SCOPE_VIOLATION = -32011  # resource not within granted scopes
A2A_CODE_BAD_REQUEST = -32012      # missing / invalid parameters


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class A2AScope(BaseModel):
    """Defines the resource type and permissions granted in an A2A share."""
    resource_type: Literal["namespace", "memory", "kg_node", "subgraph"] = Field(
        ..., description="Type of resource being shared"
    )
    resource_id: str = Field(
        ..., description="UUID or label of the resource"
    )
    permissions: list[Literal["read"]] = Field(
        default=["read"], description="Granted permissions (currently only 'read' is supported)"
    )


class A2AGrantRequest(BaseModel):
    """Request payload to create a new A2A sharing grant."""
    target_namespace_id: Optional[UUID] = Field(
        None, description="Restrict to a specific receiving namespace (None = any bearer)"
    )
    target_agent_id: Optional[str] = Field(
        None, description="Restrict to a specific receiving agent (None = any agent)"
    )
    scopes: list[A2AScope] = Field(..., min_length=1)
    expires_in_seconds: int = Field(
        3600, ge=60, le=86400 * 30, description="Token validity duration (max 30 days)"
    )


class A2AGrantResponse(BaseModel):
    """Response payload containing the secure sharing token."""
    grant_id: UUID
    sharing_token: str
    expires_at: datetime


class VerifiedGrant(BaseModel):
    """Result of a successful token verification — includes owner identity and scopes."""
    grant_id: UUID
    owner_namespace_id: UUID
    owner_agent_id: str
    scopes: list[A2AScope]
    expires_at: datetime


class A2AAuthorizationError(Exception):
    """
    Raised when an A2A token is invalid, expired, revoked, or violates
    namespace/agent constraints. Maps to JSON-RPC error -32010.
    """
    code: int = A2A_CODE_UNAUTHORIZED


class A2AScopeViolationError(Exception):
    """
    Raised when the requested resource is not covered by any granted scope.
    Maps to JSON-RPC error -32011.
    """
    code: int = A2A_CODE_SCOPE_VIOLATION


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hash_token(token: str) -> bytes:
    """Compute SHA-256 hash of the token for secure storage (compare-safe)."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def _jsonrpc_error(code: int, message: str, reason: str) -> dict[str, Any]:
    """Build a compliant JSON-RPC 2.0 error response dict."""
    return {
        "jsonrpc": "2.0",
        "error": {
            "code": code,
            "message": message,
            "data": {"reason": reason},
        },
        "id": None,
    }


# ---------------------------------------------------------------------------
# Core grant lifecycle (raw asyncpg — no ORM)
# ---------------------------------------------------------------------------

async def create_grant(
    conn: asyncpg.Connection,
    owner_ctx: NamespaceContext,
    request: A2AGrantRequest,
) -> A2AGrantResponse:
    """
    Create a new A2A sharing grant.

    Generates a cryptographically secure token, stores its SHA-256 hash,
    and returns the raw token to the caller (Agent A) to share out-of-band.
    The raw token is *never* stored — only the hash is persisted.
    """
    token = f"trimcp_a2a_{secrets.token_urlsafe(32)}"
    token_hash = _hash_token(token)
    grant_id = uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=request.expires_in_seconds)
    scopes_json = json.dumps([s.model_dump() for s in request.scopes])

    await conn.execute(
        """
        INSERT INTO a2a_grants (
            id, owner_namespace_id, owner_agent_id,
            target_namespace_id, target_agent_id,
            scopes, token_hash, status, expires_at
        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'active', $8)
        """,
        grant_id,
        owner_ctx.namespace_id,
        owner_ctx.agent_id,
        request.target_namespace_id,
        request.target_agent_id,
        scopes_json,
        token_hash,
        expires_at,
    )

    log.info(
        "A2A grant created: grant_id=%s owner_ns=%s target_ns=%s scopes=%d expires=%s",
        grant_id, owner_ctx.namespace_id, request.target_namespace_id,
        len(request.scopes), expires_at.isoformat(),
    )
    return A2AGrantResponse(grant_id=grant_id, sharing_token=token, expires_at=expires_at)


async def verify_token(
    conn: asyncpg.Connection,
    token: str,
    consumer_ctx: NamespaceContext,
) -> VerifiedGrant:
    """
    Verify an A2A sharing token presented by Agent B.

    Validates token existence (via hash lookup), expiration, and
    namespace/agent binding constraints using raw asyncpg.
    Returns a VerifiedGrant (owner identity + scopes) on success.
    Raises A2AAuthorizationError on any failure — the error message is
    intentionally non-specific to prevent information leakage.
    """
    token_hash = _hash_token(token)

    row = await conn.fetchrow(
        """
        SELECT id, owner_namespace_id, owner_agent_id,
               target_namespace_id, target_agent_id,
               scopes, expires_at, status
        FROM a2a_grants
        WHERE token_hash = $1 AND status = 'active'
        """,
        token_hash,
    )

    if not row:
        log.warning("A2A token verification failed: not found or inactive hash=<redacted>")
        raise A2AAuthorizationError("Invalid or revoked sharing token.")

    # Normalise timezone awareness for comparison
    expires_at: datetime = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        await conn.execute(
            "UPDATE a2a_grants SET status = 'expired' WHERE id = $1",
            row["id"],
        )
        log.info("A2A token auto-expired: grant_id=%s", row["id"])
        raise A2AAuthorizationError("Sharing token has expired.")

    # Namespace binding check
    if row["target_namespace_id"] is not None:
        if row["target_namespace_id"] != consumer_ctx.namespace_id:
            log.warning(
                "A2A token namespace mismatch: grant_id=%s expected=%s got=%s",
                row["id"], row["target_namespace_id"], consumer_ctx.namespace_id,
            )
            raise A2AAuthorizationError("Token is not valid for this namespace.")

    # Agent binding check
    if row["target_agent_id"] is not None:
        if row["target_agent_id"] != consumer_ctx.agent_id:
            log.warning(
                "A2A token agent mismatch: grant_id=%s expected=%s got=%s",
                row["id"], row["target_agent_id"], consumer_ctx.agent_id,
            )
            raise A2AAuthorizationError("Token is not valid for this agent.")

    scopes_data = json.loads(row["scopes"])
    scopes = [A2AScope.model_validate(s) for s in scopes_data]

    return VerifiedGrant(
        grant_id=row["id"],
        owner_namespace_id=row["owner_namespace_id"],
        owner_agent_id=row["owner_agent_id"],
        scopes=scopes,
        expires_at=expires_at,
    )


async def revoke_grant(
    conn: asyncpg.Connection,
    grant_id: UUID,
    owner_ctx: NamespaceContext,
) -> bool:
    """
    Revoke an active A2A sharing grant.

    Only the owning namespace can revoke a grant.
    Returns True if successfully revoked, False if not found / already inactive.
    """
    result = await conn.execute(
        """
        UPDATE a2a_grants
        SET status = 'revoked'
        WHERE id = $1
          AND owner_namespace_id = $2
          AND status = 'active'
        """,
        grant_id,
        owner_ctx.namespace_id,
    )
    revoked = result == "UPDATE 1"
    if revoked:
        log.info("A2A grant revoked: grant_id=%s owner_ns=%s", grant_id, owner_ctx.namespace_id)
    else:
        log.warning(
            "A2A revoke no-op: grant_id=%s owner_ns=%s (not found or already inactive)",
            grant_id, owner_ctx.namespace_id,
        )
    return revoked


async def list_grants(
    conn: asyncpg.Connection,
    owner_ctx: NamespaceContext,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """
    List A2A grants owned by the given namespace.

    Returns active grants by default. Set include_inactive=True to include
    revoked and expired grants (useful for audit trails).
    Token hashes are never returned — callers only see grant metadata.
    """
    if include_inactive:
        rows = await conn.fetch(
            """
            SELECT id, owner_agent_id, target_namespace_id, target_agent_id,
                   scopes, status, expires_at, created_at
            FROM a2a_grants
            WHERE owner_namespace_id = $1
            ORDER BY created_at DESC
            LIMIT 500
            """,
            owner_ctx.namespace_id,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, owner_agent_id, target_namespace_id, target_agent_id,
                   scopes, status, expires_at, created_at
            FROM a2a_grants
            WHERE owner_namespace_id = $1
              AND status = 'active'
              AND expires_at > now()
            ORDER BY created_at DESC
            LIMIT 500
            """,
            owner_ctx.namespace_id,
        )

    return [
        {
            "grant_id": str(row["id"]),
            "owner_agent_id": row["owner_agent_id"],
            "target_namespace_id": str(row["target_namespace_id"]) if row["target_namespace_id"] else None,
            "target_agent_id": row["target_agent_id"],
            "scopes": json.loads(row["scopes"]),
            "status": row["status"],
            "expires_at": row["expires_at"].isoformat(),
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Scope enforcement (pure — no I/O)
# ---------------------------------------------------------------------------

def enforce_scope(
    scopes: list[A2AScope],
    resource_type: str,
    resource_id: str,
) -> None:
    """
    Enforce that at least one granted scope covers the requested resource.

    Namespace-scoped grants are treated as wildcards: a grant for
    resource_type="namespace" implicitly covers all memories and KG nodes
    within that namespace.

    Raises A2AScopeViolationError (JSON-RPC -32011) if access is denied.
    This function performs no I/O — call it after verify_token().
    """
    for scope in scopes:
        if "read" not in scope.permissions:
            continue

        # Exact match: specific resource type and ID
        if scope.resource_type == resource_type and scope.resource_id == resource_id:
            return

        # Namespace wildcard: a namespace grant covers memories and KG nodes within it
        if scope.resource_type == "namespace" and resource_type in ("memory", "kg_node", "subgraph"):
            # The resource_id is expected to be prefixed with namespace_id or
            # matched via the owner_namespace_id already — the namespace grant
            # itself is the authorisation; the RLS context enforces the boundary.
            return

    raise A2AScopeViolationError(
        f"Access denied: no grant covers {resource_type}/{resource_id}. "
        f"Available scopes: {[f'{s.resource_type}/{s.resource_id}' for s in scopes]}"
    )
