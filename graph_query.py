"""
Phase 2 — Graphify Layer: Deterministic GraphRAG Traverser
Algorithm:
  1. Embed the query → cosine search kg_nodes for an anchor node.
  2. BFS outward over kg_edges up to `max_depth` hops.
  3. Hydrate each edge's source document from MongoDB.
  4. Return a structured subgraph: nodes, edges, and source excerpts.
"""
from __future__ import annotations

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
    mongo_ref_id: str | None
    distance: float = 0.0       # cosine distance from query anchor


@dataclass
class GraphEdge:
    subject: str
    predicate: str
    obj: str
    confidence: float
    mongo_ref_id: str | None


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

    async def _find_anchor(self, query: str, top_k: int = 3) -> list[GraphNode]:
        vector = await self._embed(query)
        async with self.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT label, entity_type, mongo_ref_id,
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
                mongo_ref_id=r["mongo_ref_id"],
                distance=r["distance"],
            )
            for r in rows
        ]

    # --- Step 2: BFS edge traversal ---

    async def _bfs(self, start_label: str, max_depth: int) -> tuple[set[str], list[GraphEdge]]:
        visited: set[str] = {start_label}
        all_edges: list[GraphEdge] = []
        queue: deque[tuple[str, int]] = deque([(start_label, 0)])

        async with self.pg_pool.acquire() as conn:
            while queue and len(visited) < MAX_NODES:
                current_label, depth = queue.popleft()
                if depth >= max_depth:
                    continue

                # Outbound edges (current is subject)
                rows = await conn.fetch(
                    """
                    SELECT subject_label, predicate, object_label, confidence, mongo_ref_id
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
                        confidence=row["confidence"],
                        mongo_ref_id=row["mongo_ref_id"],
                    )
                    all_edges.append(edge)
                    neighbor = row["object_label"] if row["subject_label"] == current_label else row["subject_label"]
                    if neighbor not in visited and len(visited) < MAX_NODES:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))

        return visited, all_edges

    # --- Step 3: Hydrate source documents from MongoDB ---

    async def _hydrate_sources(self, mongo_ref_ids: set[str]) -> list[dict]:
        db = self.mongo_client.memory_archive
        sources = []
        seen: set[str] = set()
        for ref_id in mongo_ref_ids:
            if not ref_id or ref_id in seen:
                continue
            seen.add(ref_id)
            try:
                doc = await db.episodes.find_one({"_id": ObjectId(ref_id)})
                if doc:
                    raw = doc.get("raw_data", "")
                    sources.append({
                        "mongo_ref_id": ref_id,
                        "type": doc.get("type", "unknown"),
                        "excerpt": str(raw)[:600],   # trim for LLM context budget
                    })
            except Exception as e:
                log.warning(f"Could not hydrate mongo_ref_id={ref_id}: {e}")
        return sources

    # --- Public API ---

    async def search(self, query: str, max_depth: int = 2, anchor_top_k: int = 1) -> Subgraph:
        """
        Full GraphRAG traversal pipeline.
        Returns a Subgraph with nodes, edges, and hydrated source excerpts.
        """
        anchors = await self._find_anchor(query, top_k=anchor_top_k)
        if not anchors:
            log.info("No anchor node found in knowledge graph.")
            return Subgraph(anchor="<none>")

        anchor = anchors[0]
        log.info(f"Anchor: '{anchor.label}' (distance={anchor.distance:.4f})")

        visited_labels, edges = await self._bfs(anchor.label, max_depth=max_depth)

        # Fetch full node metadata for all visited labels
        async with self.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT label, entity_type, mongo_ref_id FROM kg_nodes WHERE label = ANY($1::text[])",
                list(visited_labels),
            )
        nodes = [
            GraphNode(
                label=r["label"],
                entity_type=r["entity_type"],
                mongo_ref_id=r["mongo_ref_id"],
                distance=anchor.distance if r["label"] == anchor.label else 0.0,
            )
            for r in rows
        ]

        # Collect all unique mongo_ref_ids for source hydration
        all_refs = {n.mongo_ref_id for n in nodes if n.mongo_ref_id}
        all_refs |= {e.mongo_ref_id for e in edges if e.mongo_ref_id}
        sources = await self._hydrate_sources(all_refs)

        # Deduplicate edges (BFS can traverse same edge from both directions)
        seen_edges: set[tuple] = set()
        unique_edges = []
        for e in edges:
            key = (e.subject, e.predicate, e.obj)
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(e)

        return Subgraph(anchor=anchor.label, nodes=nodes, edges=unique_edges, sources=sources)
