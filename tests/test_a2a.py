"""
tests/test_a2a.py

Phase 3.1 — A2A protocol unit tests (multi-agent isolation, no shared DB).

Uses unique UUIDs per case so parallel pytest workers do not collide.
All Postgres access is mocked unless noted.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from trimcp.a2a import (
    A2AAuthorizationError,
    A2AScopeViolationError,
    A2AGrantRequest,
    A2AScope,
    create_grant,
    enforce_scope,
    verify_token,
)
from trimcp.auth import NamespaceContext


def _future_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


def _grant_row(
    *,
    owner_ns: uuid.UUID,
    owner_agent: str,
    consumer_ns: uuid.UUID | None,
    consumer_agent: str | None,
    scopes: list[dict],
) -> dict:
    return {
        "id": uuid.uuid4(),
        "owner_namespace_id": owner_ns,
        "owner_agent_id": owner_agent,
        "target_namespace_id": consumer_ns,
        "target_agent_id": consumer_agent,
        "scopes": json.dumps(scopes),
        "expires_at": _future_expiry(),
        "status": "active",
    }


class TestEnforceScopeMultiAgent:
    """Agent B must present a grant that covers the resource; memory grants are not wildcards."""

    def test_memory_not_covered_when_grant_is_different_memory(self) -> None:
        mem_a = str(uuid.uuid4())
        mem_b = str(uuid.uuid4())
        scopes = [A2AScope(resource_type="memory", resource_id=mem_a, permissions=["read"])]
        with pytest.raises(A2AScopeViolationError):
            enforce_scope(scopes, "memory", mem_b)

    def test_memory_not_covered_when_grant_is_only_kg_node(self) -> None:
        node = str(uuid.uuid4())
        mem = str(uuid.uuid4())
        scopes = [A2AScope(resource_type="kg_node", resource_id=node, permissions=["read"])]
        with pytest.raises(A2AScopeViolationError):
            enforce_scope(scopes, "memory", mem)

    def test_namespace_grant_allows_typed_memory_reads(self) -> None:
        """Namespace-shaped grant authorises memory / kg_node / subgraph resource_type checks."""
        ns = str(uuid.uuid4())
        scopes = [A2AScope(resource_type="namespace", resource_id=ns, permissions=["read"])]
        enforce_scope(scopes, "memory", str(uuid.uuid4()))
        enforce_scope(scopes, "kg_node", str(uuid.uuid4()))

    def test_exact_memory_grant_allows_that_memory(self) -> None:
        mem = str(uuid.uuid4())
        scopes = [A2AScope(resource_type="memory", resource_id=mem, permissions=["read"])]
        enforce_scope(scopes, "memory", mem)


class TestVerifyTokenIsolation:
    """Token must match consumer namespace / agent bindings from the grant row."""

    @pytest.mark.asyncio
    async def test_wrong_consumer_namespace_raises(self) -> None:
        owner_ns = uuid.uuid4()
        bound_ns = uuid.uuid4()
        wrong_ns = uuid.uuid4()
        assert wrong_ns != bound_ns

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            return_value=_grant_row(
                owner_ns=owner_ns,
                owner_agent="agent-a",
                consumer_ns=bound_ns,
                consumer_agent=None,
                scopes=[{"resource_type": "namespace", "resource_id": str(owner_ns), "permissions": ["read"]}],
            )
        )
        consumer = NamespaceContext(namespace_id=wrong_ns, agent_id="agent-b")
        with pytest.raises(A2AAuthorizationError, match="not valid for this namespace"):
            await verify_token(conn, "trimcp_a2a_x", consumer)

    @pytest.mark.asyncio
    async def test_unknown_token_raises(self) -> None:
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        consumer = NamespaceContext(namespace_id=uuid.uuid4(), agent_id="b")
        with pytest.raises(A2AAuthorizationError, match="Invalid or revoked"):
            await verify_token(conn, "trimcp_a2a_y", consumer)

    @pytest.mark.asyncio
    async def test_wrong_consumer_agent_raises(self) -> None:
        owner_ns = uuid.uuid4()
        consumer_ns = uuid.uuid4()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            return_value=_grant_row(
                owner_ns=owner_ns,
                owner_agent="agent-a",
                consumer_ns=consumer_ns,
                consumer_agent="expected-bot",
                scopes=[{"resource_type": "namespace", "resource_id": str(owner_ns), "permissions": ["read"]}],
            )
        )
        consumer = NamespaceContext(namespace_id=consumer_ns, agent_id="other-bot")
        with pytest.raises(A2AAuthorizationError, match="not valid for this agent"):
            await verify_token(conn, "trimcp_a2a_za", consumer)

    @pytest.mark.asyncio
    async def test_verify_success_returns_owner(self) -> None:
        owner_ns = uuid.uuid4()
        consumer_ns = uuid.uuid4()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            return_value=_grant_row(
                owner_ns=owner_ns,
                owner_agent="agent-a",
                consumer_ns=consumer_ns,
                consumer_agent=None,
                scopes=[{"resource_type": "namespace", "resource_id": str(owner_ns), "permissions": ["read"]}],
            )
        )
        consumer = NamespaceContext(namespace_id=consumer_ns, agent_id="agent-b")
        v = await verify_token(conn, "trimcp_a2a_zb", consumer)
        assert v.owner_namespace_id == owner_ns
        assert v.owner_agent_id == "agent-a"
        assert len(v.scopes) == 1


class TestVerifyTokenExpiry:
    @pytest.mark.asyncio
    async def test_expired_token_raises_and_marks_expired(self) -> None:
        owner_ns = uuid.uuid4()
        consumer_ns = uuid.uuid4()
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            return_value={
                "id": uuid.uuid4(),
                "owner_namespace_id": owner_ns,
                "owner_agent_id": "agent-a",
                "target_namespace_id": consumer_ns,
                "target_agent_id": None,
                "scopes": json.dumps(
                    [{"resource_type": "namespace", "resource_id": str(owner_ns), "permissions": ["read"]}]
                ),
                "expires_at": past,
                "status": "active",
            }
        )
        conn.execute = AsyncMock()
        consumer = NamespaceContext(namespace_id=consumer_ns, agent_id="agent-b")
        with pytest.raises(A2AAuthorizationError, match="expired"):
            await verify_token(conn, "trimcp_a2a_zc", consumer)
        conn.execute.assert_awaited()


class TestCreateGrantSqlShape:
    """ensure INSERT is invoked (still isolated — no real DB)."""

    @pytest.mark.asyncio
    async def test_create_grant_executes_insert(self) -> None:
        conn = AsyncMock()
        conn.execute = AsyncMock()
        owner = NamespaceContext(namespace_id=uuid.uuid4(), agent_id="owner-agent")
        req = A2AGrantRequest(
            target_namespace_id=uuid.uuid4(),
            target_agent_id="visitor",
            scopes=[A2AScope(resource_type="namespace", resource_id=str(owner.namespace_id), permissions=["read"])],
            expires_in_seconds=120,
        )
        resp = await create_grant(conn, owner, req)
        assert resp.sharing_token.startswith("trimcp_a2a_")
        conn.execute.assert_awaited_once()
