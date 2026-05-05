"""
Phase 2 — Graphify Layer: Deterministic GraphRAG Traverser
Algorithm:
  1. Embed the query → cosine search kg_nodes for an anchor node.
  2. BFS outward over kg_edges up to `max_depth` hops.
  3. Hydrate each edge's source document from MongoDB.
  4. Return a structured subgraph: nodes, edges, and source excerpts.
"""
from __future__ import annotations


from datetime import datetime
import json
import logging

from collections import deque
from dataclasses import dataclass, field

import asyncpg
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("tri-stack-graphrag")

MAX_NODES = 50   # hard cap — prevents runaway BFS on dense graphs


@dataclass
class GraphNode:
    label: str
    entity_type: str
    payload_ref: str | None
    distance: float = 0.0       # cosine distance from query anchor


@dataclass
class GraphEdge:
    subject: str
    predicate: str
    obj: str
    confidence: float
    payload_ref: str | None


@dataclass
class Subgraph:
    anchor: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)   # hydrated Mongo excerpts

    def to_dict(self) -> dict:
        return {
            "anchor": self.anchor,
            "nodes": [
                {"label": n.label, "type": n.entity_type, "distance": round(n.distance, 4)}
                for n in self.nodes
            ],
            "edges": [
                {"subject": e.subject, "predicate": e.predicate,
                 "object": e.obj, "confidence": e.confidence}
                for e in self.edges
            ],
            "sources": self.sources,
        }


class GraphRAGTraverser:
    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        mongo_client: AsyncIOMotorClient,
        embedding_fn,           # async callable: (str) -> list[float]
    ):
        self.pg_pool = pg_pool
        self.mongo_client = mongo_client
        self._embed = embedding_fn

    # --- Step 1: Vector anchor search ---

    async def _find_anchor(self, query: str, namespace_id: str = None, top_k: int = 3, as_of: datetime | None = None) -> list[GraphNode]:
        vector = await self._embed(query)
        async with self.pg_pool.acquire() as conn:
            if as_of and namespace_id:
                # Phase 2.2: Time Travel Anchor Search
                rows = await conn.fetch(
                    """
                    WITH ns AS (
                        SELECT id, parent_id, (metadata->'fork_config'->>'forked_from_as_of')::timestamptz AS forked_as_of
                        FROM namespaces WHERE id = $3::uuid
                    ),
                    memory_events AS (
                        SELECT DISTINCT ON ((params->>'memory_id')::uuid)
                            (params->>'memory_id')::uuid AS memory_id,
                            event_type,
                            params->'entities' AS entities
                        FROM event_log
                        CROSS JOIN ns
                        WHERE (
                            (namespace_id = ns.id AND occurred_at <= $4)
                            OR 
                            (namespace_id = ns.parent_id AND occurred_at <= LEAST($4, ns.forked_as_of))
                        )
                          AND event_type IN ('store_memory', 'forget_memory')
                        ORDER BY (params->>'memory_id')::uuid, occurred_at DESC, event_seq DESC
                    ),
                    active_memories AS (
                        SELECT memory_id, entities 
                        FROM memory_events 
                        WHERE event_type = 'store_memory'
                    ),
                    historical_nodes AS (
                        SELECT DISTINCT ON (label)
                            jsonb_array_elements(entities)->>'label' AS label,
                            jsonb_array_elements(entities)->>'entity_type' AS entity_type,
                            memory_id
                        FROM active_memories
                    )
                    SELECT n.label, n.entity_type, m.payload_ref,
                           m.embedding <=> $1::vector AS distance
                    FROM historical_nodes n
                    JOIN memories m ON n.memory_id = m.id
                    ORDER BY distance ASC
                    LIMIT $2
                    """,
                    json.dumps(vector), top_k, namespace_id, as_of
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT label, entity_type, payload_ref,
                           embedding <=> $1::vector AS distance
                    FROM kg_nodes
                    ORDER BY distance ASC
                    LIMIT $2
                    """,
                    json.dumps(vector), top_k,
                )
        return [
            GraphNode(
                label=r["label"],
                entity_type=r["entity_type"],
                payload_ref=r["payload_ref"],
                distance=r["distance"],
            )
            for r in rows
        ]

    # --- Step 2: BFS edge traversal ---

    async def _bfs(self, start_label: str, max_depth: int, namespace_id: str = None, as_of: datetime | None = None) -> tuple[set[str], list[GraphEdge]]:
        visited: set[str] = {start_label}
        all_edges: list[GraphEdge] = []
        queue: deque[tuple[str, int]] = deque([(start_label, 0)])

        async with self.pg_pool.acquire() as conn:
            while queue and len(visited) < MAX_NODES:
                current_label, depth = queue.popleft()
                if depth >= max_depth:
                    continue

                # Outbound edges (current is subject)
                # GRAPH DECAY: Introduce time-weighted penalty to confidence.
                # penalty = exp(-decay_rate * days_since_update)
                # We'll use a simplified SQL-side decay for performance.
                if as_of and namespace_id:
                    # Phase 2.2: Time Travel Edge Traversal
                    rows = await conn.fetch(
                        """
                    WITH ns AS (
                        SELECT id, parent_id, (metadata->'fork_config'->>'forked_from_as_of')::timestamptz AS forked_as_of
                        FROM namespaces WHERE id = $2::uuid
                    ),
                    memory_events AS (
                        SELECT DISTINCT ON ((params->>'memory_id')::uuid)
                            (params->>'memory_id')::uuid AS memory_id,
                            event_type,
                            params->'triplets' AS triplets
                        FROM event_log
                        CROSS JOIN ns
                        WHERE (
                            (namespace_id = ns.id AND occurred_at <= $3)
                            OR 
                            (namespace_id = ns.parent_id AND occurred_at <= LEAST($3, ns.forked_as_of))
                        )
                          AND event_type IN ('store_memory', 'forget_memory')
                        ORDER BY (params->>'memory_id')::uuid, occurred_at DESC, event_seq DESC
                    ),
                        active_memories AS (
                            SELECT memory_id, triplets 
                            FROM memory_events 
                            WHERE event_type = 'store_memory'
                        ),
                        historical_edges AS (
                            SELECT 
                                jsonb_array_elements(triplets)->>'subject_label' AS subject_label,
                                jsonb_array_elements(triplets)->>'predicate' AS predicate,
                                jsonb_array_elements(triplets)->>'object_label' AS object_label,
                                (jsonb_array_elements(triplets)->>'confidence')::float AS confidence,
                                memory_id
                            FROM active_memories
                        )
                        SELECT e.subject_label, e.predicate, e.object_label, m.payload_ref,
                               e.confidence AS decayed_confidence
                        FROM historical_edges e
                        JOIN memories m ON e.memory_id = m.id
                        WHERE e.subject_label = $1 OR e.object_label = $1
                        """,
                        current_label, namespace_id, as_of
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT subject_label, predicate, object_label, payload_ref,
                               confidence * EXP(-0.01 * EXTRACT(EPOCH FROM (NOW() - updated_at)) / 86400) AS decayed_confidence
                        FROM kg_edges
                        WHERE subject_label = $1 OR object_label = $1
                        """,
                        current_label,
                    )
                for row in rows:
                    edge = GraphEdge(
                        subject=row["subject_label"],
                        predicate=row["predicate"],
                        obj=row["object_label"],
                        confidence=row["decayed_confidence"],
                        payload_ref=row["payload_ref"],
                    )
                    all_edges.append(edge)
                    neighbor = row["object_label"] if row["subject_label"] == current_label else row["subject_label"]
                    if neighbor not in visited and len(visited) < MAX_NODES:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))

        return visited, all_edges

    # --- Step 3: Hydrate source documents from MongoDB ---

    async def _hydrate_sources(
        self,
        mongo_ref_ids: set[str],
        restrict_user_id: str | None = None,
    ) -> list[dict]:
        """
        KG edges/nodes can point at either `episodes` (chat/summary memories) or
        `code_files` (indexed source files). Try both collections so graph_search
        surfaces entities extracted from code as well as from conversations.
        When restrict_user_id is set (private graph search), only include documents
        owned by that user.
        """
        db = self.mongo_client.memory_archive
        sources = []
        seen: set[str] = set()
        for ref_id in mongo_ref_ids:
            if not ref_id or ref_id in seen:
                continue
            seen.add(ref_id)
            try:
                oid = ObjectId(ref_id)
            except Exception as e:
                log.warning(f"Invalid payload_ref={ref_id}: {e}")
                continue
            try:
                doc = await db.episodes.find_one({"_id": oid})
                if doc:
                    if restrict_user_id is not None and doc.get("user_id") != restrict_user_id:
                        continue
                    raw = doc.get("raw_data", "")
                    sources.append({
                        "payload_ref": ref_id,
                        "collection": "episodes",
                        "type": doc.get("type", "unknown"),
                        "excerpt": str(raw)[:600],   # trim for LLM context budget
                    })
                    continue

                code_doc = await db.code_files.find_one({"_id": oid})
                if code_doc:
                    if restrict_user_id is not None and code_doc.get("user_id") != restrict_user_id:
                        continue
                    raw = code_doc.get("raw_code", "")
                    sources.append({
                        "payload_ref": ref_id,
                        "collection": "code_files",
                        "type": "code",
                        "filepath": code_doc.get("filepath"),
                        "language": code_doc.get("language"),
                        "excerpt": str(raw)[:600],
                    })
            except Exception as e:
                log.warning(f"Could not hydrate payload_ref={ref_id}: {e}")
        return sources

    # --- Public API ---

    async def search(
        self,
        query: str,
        namespace_id: str = None,
        max_depth: int = 2,
        anchor_top_k: int = 1,
        *,
        private: bool = False,
        user_id: str | None = None,
        as_of=None,
    ) -> Subgraph:
        """
        Full GraphRAG traversal pipeline.
        Returns a Subgraph with nodes, edges, and hydrated source excerpts.
        private=True: hydrate only Mongo sources belonging to user_id (Phase 0;
        anchor/BFS remain global on kg_nodes/kg_edges).
        """
        anchors = await self._find_anchor(query, namespace_id=namespace_id, top_k=anchor_top_k, as_of=as_of)
        if not anchors:
            log.info("No anchor node found in knowledge graph.")
            return Subgraph(anchor="<none>")

        anchor = anchors[0]
        log.info(f"Anchor: '{anchor.label}' (distance={anchor.distance:.4f})")

        visited_labels, edges = await self._bfs(anchor.label, max_depth=max_depth, namespace_id=namespace_id, as_of=as_of)

        # Fetch full node metadata for all visited labels
        async with self.pg_pool.acquire() as conn:
            if as_of and namespace_id:
                rows = await conn.fetch(
                    """
                    WITH ns AS (
                        SELECT id, parent_id, (metadata->'fork_config'->>'forked_from_as_of')::timestamptz AS forked_as_of
                        FROM namespaces WHERE id = $2::uuid
                    ),
                    memory_events AS (
                        SELECT DISTINCT ON ((params->>'memory_id')::uuid)
                            (params->>'memory_id')::uuid AS memory_id,
                            event_type,
                            params->'entities' AS entities
                        FROM event_log
                        CROSS JOIN ns
                        WHERE (
                            (namespace_id = ns.id AND occurred_at <= $3)
                            OR 
                            (namespace_id = ns.parent_id AND occurred_at <= LEAST($3, ns.forked_as_of))
                        )
                          AND event_type IN ('store_memory', 'forget_memory')
                        ORDER BY (params->>'memory_id')::uuid, occurred_at DESC, event_seq DESC
                    ),
                    active_memories AS (
                        SELECT memory_id, entities 
                        FROM memory_events 
                        WHERE event_type = 'store_memory'
                    ),
                    historical_nodes AS (
                        SELECT DISTINCT ON (label)
                            jsonb_array_elements(entities)->>'label' AS label,
                            jsonb_array_elements(entities)->>'entity_type' AS entity_type,
                            memory_id
                        FROM active_memories
                    )
                    SELECT n.label, n.entity_type, m.payload_ref
                    FROM historical_nodes n
                    JOIN memories m ON n.memory_id = m.id
                    WHERE n.label = ANY($1::text[])
                    """,
                    list(visited_labels), namespace_id, as_of
                )
            else:
                rows = await conn.fetch(
                    "SELECT label, entity_type, payload_ref FROM kg_nodes WHERE label = ANY($1::text[])",
                    list(visited_labels),
                )
        nodes = [
            GraphNode(
                label=r["label"],
                entity_type=r["entity_type"],
                payload_ref=r["payload_ref"],
                distance=anchor.distance if r["label"] == anchor.label else 0.0,
            )
            for r in rows
        ]

        # Collect all unique mongo_ref_ids for source hydration
        all_refs = {n.payload_ref for n in nodes if n.payload_ref}
        all_refs |= {e.payload_ref for e in edges if e.payload_ref}
        restrict = user_id if private else None
        sources = await self._hydrate_sources(all_refs, restrict_user_id=restrict)

        # Deduplicate edges (BFS can traverse same edge from both directions)
        seen_edges: set[tuple] = set()
        unique_edges = []
        for e in edges:
            key = (e.subject, e.predicate, e.obj)
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(e)

        return Subgraph(anchor=anchor.label, nodes=nodes, edges=unique_edges, sources=sources)
