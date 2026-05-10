from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from trimcp.orchestrator import TriStackEngine


@pytest.mark.asyncio
async def test_semantic_search_temporal_parameters_prevent_sql_injection():
    # Setup mock engine
    engine = TriStackEngine()
    engine._generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    engine.pg_pool = mock_pool

    # MemoryOrchestrator lazy-init needs mongo_client
    engine.mongo_client = MagicMock()
    engine.mongo_client.memory_archive = MagicMock()

    # Mock scoped_session to yield mock_conn
    class ScopedSessionMock:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    engine.scoped_session = MagicMock(return_value=ScopedSessionMock())

    # Mock fetchrow for namespace metadata
    mock_conn.fetchrow = AsyncMock(
        return_value={"metadata": {"temporal_retention_days": 90}}
    )
    # Mock fetchval for embedding model
    mock_conn.fetchval = AsyncMock(return_value=None)
    # Mock fetch for the main query
    mock_conn.fetch = AsyncMock(return_value=[])

    as_of_dt = datetime.now(timezone.utc)

    # Invoke semantic search
    await engine.semantic_search(
        query="test query",
        namespace_id="00000000-0000-4000-8000-000000000001",
        agent_id="test_agent",
        limit=5,
        as_of=as_of_dt,
    )

    # Assert
    assert mock_conn.fetch.called
    call_args = mock_conn.fetch.call_args
    query_str = call_args[0][0]

    # Assert placeholders are used, not interpolated values
    assert "INTERVAL '90 days'" not in query_str
    assert as_of_dt.isoformat() not in query_str

    # Assert new placeholders exist
    assert "$6::int * INTERVAL '1 day'" in query_str
    assert "<= $7" in query_str

    # Check parameters were passed correctly
    params = call_args[0][1:]
    assert params[5] == 90
    assert params[6] == as_of_dt
