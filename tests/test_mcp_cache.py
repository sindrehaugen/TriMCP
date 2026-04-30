import pytest
import json
import hashlib
from unittest.mock import AsyncMock, MagicMock
from mcp.types import TextContent

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.redis_client = AsyncMock()
    engine.store_memory = AsyncMock(return_value="mongo_123")
    engine.semantic_search = AsyncMock(return_value=[{"id": 1}])
    engine.search_codebase = AsyncMock(return_value=[{"code": "def"}])
    engine.graph_search = AsyncMock(return_value={"nodes": []})
    engine.index_code_file = AsyncMock(return_value={"status": "indexed"})
    engine.store_media = AsyncMock(return_value="mongo_456")
    engine.get_job_status = AsyncMock(return_value={"status": "completed"})
    engine.recall_memory = AsyncMock(return_value="recent context")
    return engine

@pytest.fixture(autouse=True)
def setup_server_engine(mock_engine):
    import server
    # Preserve original
    original_engine = server.engine
    server.engine = mock_engine
    yield
    server.engine = original_engine

@pytest.mark.asyncio
async def test_cache_miss_writes_to_cache(mock_engine):
    """Verify that a cache miss calls the engine and writes to Redis."""
    from server import call_tool
    mock_engine.redis_client.get.return_value = None
    
    args = {"user_id": "u1", "query": "test query", "top_k": 5}
    res = await call_tool("semantic_search", args)
    
    # Engine should be called because of cache miss
    mock_engine.semantic_search.assert_called_once_with(user_id="u1", query="test query", top_k=5)
    mock_engine.redis_client.setex.assert_called_once()
    
    # Verify deterministic key creation
    args_str = json.dumps(args, sort_keys=True)
    args_hash = hashlib.md5(args_str.encode()).hexdigest()
    expected_key = f"mcp_cache:v0:semantic_search:{args_hash}"
    
    call_args = mock_engine.redis_client.setex.call_args[0]
    assert call_args[0] == expected_key
    assert call_args[1] == 300
    assert call_args[2] == json.dumps([{"id": 1}])

@pytest.mark.asyncio
async def test_cache_hit_returns_cached_value(mock_engine):
    """Verify that a cache hit returns immediately without querying DB."""
    from server import call_tool
    
    async def mock_get(key):
        if key == "mcp_cache_generation":
            return b"2"
        if "mcp_cache:v2:semantic_search" in key:
            return b'[{"cached": "result"}]'
        return None
        
    mock_engine.redis_client.get.side_effect = mock_get
    
    args = {"user_id": "u1", "query": "cached query", "top_k": 5}
    res = await call_tool("semantic_search", args)
    
    # Engine should NOT be called due to cache hit
    mock_engine.semantic_search.assert_not_called()
    assert res[0].text == '[{"cached": "result"}]'

@pytest.mark.asyncio
async def test_read_after_write_invalidation(mock_engine):
    """Verify that mutation tools invalidate the cache generation."""
    from server import call_tool
    
    args = {
        "user_id": "u1", 
        "session_id": "s1", 
        "content_type": "chat",
        "summary": "new memory", 
        "heavy_payload": "full content"
    }
    
    res = await call_tool("store_memory", args)
    
    # Cache generation should be incremented to invalidate reads
    mock_engine.redis_client.incr.assert_called_once_with("mcp_cache_generation")
    mock_engine.store_memory.assert_called_once()
    assert "mongo_123" in res[0].text

@pytest.mark.asyncio
async def test_cacheable_tool_search_codebase(mock_engine):
    """Verify codebase searches are also cached correctly."""
    from server import call_tool
    mock_engine.redis_client.get.return_value = None
    
    args = {"query": "find stuff", "top_k": 5}
    res = await call_tool("search_codebase", args)
    
    mock_engine.search_codebase.assert_called_once()
    mock_engine.redis_client.setex.assert_called_once()
    assert '[{"code": "def"}]' in res[0].text

@pytest.mark.asyncio
async def test_cacheable_tool_graph_search(mock_engine):
    """Verify graph_search is also cached correctly."""
    from server import call_tool
    mock_engine.redis_client.get.return_value = None
    
    args = {"query": "find stuff", "max_depth": 2}
    res = await call_tool("graph_search", args)
    
    mock_engine.graph_search.assert_called_once()
    mock_engine.redis_client.setex.assert_called_once()
    assert '{"nodes": []}' in res[0].text
