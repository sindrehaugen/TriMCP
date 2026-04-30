import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from trimcp.graph_query import GraphRAGTraverser, GraphNode, GraphEdge, Subgraph
from bson import ObjectId

@pytest.fixture
def mock_pg_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    return pool, conn

@pytest.fixture
def mock_mongo_client():
    client = MagicMock()
    db = MagicMock()
    client.memory_archive = db
    db.episodes.find_one = AsyncMock()
    db.code_files.find_one = AsyncMock()
    return client, db

@pytest.fixture
def traverser(mock_pg_pool, mock_mongo_client):
    pool, conn = mock_pg_pool
    client, db = mock_mongo_client
    
    async def dummy_embed(query: str):
        return [0.1, 0.2, 0.3]
        
    return GraphRAGTraverser(
        pg_pool=pool,
        mongo_client=client,
        embedding_fn=dummy_embed
    )

@pytest.mark.asyncio
async def test_find_anchor(traverser, mock_pg_pool):
    _, conn = mock_pg_pool
    conn.fetch.return_value = [
        {"label": "Redis", "entity_type": "TOOL", "mongo_ref_id": "123", "distance": 0.1}
    ]
    
    anchors = await traverser._find_anchor("query", top_k=1)
    
    assert len(anchors) == 1
    assert anchors[0].label == "Redis"
    assert anchors[0].distance == 0.1
    conn.fetch.assert_called_once()

@pytest.mark.asyncio
async def test_bfs(traverser, mock_pg_pool):
    _, conn = mock_pg_pool
    
    # Mock BFS to return one edge
    conn.fetch.return_value = [
        {
            "subject_label": "Redis",
            "predicate": "caches",
            "object_label": "Data",
            "mongo_ref_id": "456",
            "decayed_confidence": 0.9
        }
    ]
    
    visited, edges = await traverser._bfs("Redis", max_depth=1)
    
    assert "Redis" in visited
    assert "Data" in visited
    assert len(edges) == 1
    assert edges[0].subject == "Redis"
    assert edges[0].obj == "Data"

@pytest.mark.asyncio
async def test_hydrate_sources(traverser, mock_mongo_client):
    _, db = mock_mongo_client
    
    # Mock episodes result
    db.episodes.find_one.return_value = {
        "_id": ObjectId("5f3b3e3e3e3e3e3e3e3e3e3e"),
        "raw_data": "Test memory",
        "type": "chat"
    }
    
    sources = await traverser._hydrate_sources({"5f3b3e3e3e3e3e3e3e3e3e3e"})
    
    assert len(sources) == 1
    assert sources[0]["excerpt"] == "Test memory"
    assert sources[0]["collection"] == "episodes"

@pytest.mark.asyncio
async def test_search_full_pipeline(traverser, mock_pg_pool, mock_mongo_client):
    pool, conn = mock_pg_pool
    _, db = mock_mongo_client
    
    # Setup step 1: find anchor
    async def mock_find_anchor(*args, **kwargs):
        return [GraphNode(label="Anchor", entity_type="CONCEPT", mongo_ref_id="abc", distance=0.0)]
        
    traverser._find_anchor = mock_find_anchor
    
    # Setup step 2: bfs
    async def mock_bfs(*args, **kwargs):
        edges = [GraphEdge(subject="Anchor", predicate="is", obj="Target", confidence=1.0, mongo_ref_id="def")]
        return {"Anchor", "Target"}, edges
        
    traverser._bfs = mock_bfs
    
    # Setup step 3: node metadata query
    conn.fetch.return_value = [
        {"label": "Anchor", "entity_type": "CONCEPT", "mongo_ref_id": "abc"},
        {"label": "Target", "entity_type": "CONCEPT", "mongo_ref_id": "xyz"}
    ]
    
    # Setup step 4: hydrate
    async def mock_hydrate(*args, **kwargs):
        return [{"excerpt": "data"}]
        
    traverser._hydrate_sources = mock_hydrate
    
    subgraph = await traverser.search("query", max_depth=1)
    
    assert subgraph.anchor == "Anchor"
    assert len(subgraph.nodes) == 2
    assert len(subgraph.edges) == 1
    assert len(subgraph.sources) == 1
