"""
Phase 2 — Graphify Layer: Deterministic GraphRAG Traverser
Algorithm:
  1. Embed the query → cosine search ``kg_nodes`` for an anchor node.
  2. BFS outward over ``kg_edges`` up to ``max_depth`` hops using a single
     PostgreSQL **recursive CTE** (one round-trip instead of N).
  3. Fetch all discovered edges in one batch query (``WHERE subject_label = ANY``
     or ``object_label = ANY``).
  4. Hydrate source documents from MongoDB using two batch ``$in`` queries
     (``episodes`` + ``code_files``) — always exactly 2 round-trips.
  5. Return a structured subgraph: nodes, edges, and source excerpts (optional
     ``edge_limit`` / ``edge_offset`` on deduplicated edges).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import asyncpg
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("tri-stack-graphrag")

MAX_NODES = 50  # hard cap — prevents runaway BFS on dense graphs
# Cap incident edges loaded per BFS expansion (hub nodes can have huge degree).
# Frontend / MCP: document that each hop samples at most this many edges (by confidence).
MAX_EDGES_PER_NODE = 512


@dataclass
class GraphNode:
    label: str
    entity_type: str
    payload_ref: str | None
    distance: float = 0.0  # cosine distance from query anchor


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
    sources: list[dict] = field(default_factory=list)  # hydrated Mongo excerpts
    # Pagination / limits (optional metadata for API consumers)
    edge_total: int | None = None
    edge_offset: int | None = None
    edge_limit: int | None = None
    has_more_edges: bool | None = None
    max_edges_per_node: int | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "anchor": self.anchor,
            "nodes": [
                {"label": n.label, "type": n.entity_type, "distance": round(n.distance, 4)}
                for n in self.nodes
            ],
            "edges": [
                {
                    "subject": e.subject,
                    "predicate": e.predicate,
                    "object": e.obj,
                    "confidence": e.confidence,
                }
                for e in self.edges
            ],
            "sources": self.sources,
        }
        if self.max_edges_per_node is not None:
            out["max_edges_per_node"] = self.max_edges_per_node
        if self.edge_total is not None:
            out["edge_total"] = self.edge_total
        if self.edge_offset is not None:
            out["edge_offset"] = self.edge_offset
        if self.edge_limit is not None:
            out["edge_limit"] = self.edge_limit
        if self.has_more_edges is not None:
            out["has_more_edges"] = self.has_more_edges
        return out


class GraphRAGTraverser:
    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        mongo_client: AsyncIOMotorClient,
        embedding_fn,  # async callable: (str) -> list[float]
    ):
        self.pg_pool = pg_pool
        self.mongo_client = mongo_client
        self._embed = embedding_fn

    # --- Time-travel signature verification ---

    async def _verify_time_travel_event_signatures(
        self,
        conn: asyncpg.Connection,
        event_ids: list[str],
    ) -> None:
        """
        Verify HMAC signatures on event_log rows that contributed to a time-travel result.

        Time-travel CTE queries reconstruct historical KG state from ``event_log``
        rows entirely inside Postgres, bypassing Python-level ``verify_event_signature()``.
        This method closes that gap by fetching the winning event rows and validating
        their signatures before the subgraph is returned to the caller.

        Raises ``DataIntegrityError`` if any event has an invalid or missing signature.
        """
        if not event_ids:
            return
        from trimcp.event_log import DataIntegrityError, verify_event_signature

        # Deduplicate — the same event may appear from multiple CTE branches.
        unique_ids = list(set(event_ids))

        # Fetch full event_log rows.  event_log is RANGE-partitioned so this
        # scans all partitions, but the subgraph size is bounded by MAX_NODES.
        rows = await conn.fetch(
            "SELECT * FROM event_log WHERE id = ANY($1::uuid[])",
            unique_ids,
        )
        for row in rows:
            try:
                await verify_event_signature(conn, row)
            except DataIntegrityError:
                raise  # re-raise — tampering is a critical security event
            except Exception as exc:
                log.error(
                    "Signature verification failed for event_id=%s: %s",
                    row.get("id"),
                    exc,
                )
                raise DataIntegrityError(
                    f"Event signature verification error for event_id={row.get('id')}: {exc}"
                ) from exc

    # --- Step 1: Vector anchor search ---

    async def _find_anchor(
        self,
        query: str,
        namespace_id: str | None = None,
        top_k: int = 3,
        as_of: datetime | None = None,
        *,
        _allow_global_sweep: bool = False,
    ) -> list[GraphNode]:
        """
        Vector anchor search against kg_nodes.

        Security contract:
            ``namespace_id=None`` performs a **global** sweep across ALL tenants.
            This is ONLY safe for admin/diagnostic operations.  Tenant-facing
            callers MUST pass a namespace_id OR explicitly opt in with
            ``_allow_global_sweep=True``.

        Raises:
            ValueError: if ``namespace_id`` is None and ``_allow_global_sweep``
                        is not True (accidental global-sweep guard).
        """
        if namespace_id is None and not _allow_global_sweep:
            raise ValueError(
                "_find_anchor: namespace_id is required for tenant-scoped searches. "
                "Pass _allow_global_sweep=True only for admin/diagnostic cross-tenant operations."
            )
        vector = await self._embed(query)
        async with self.pg_pool.acquire() as conn:
            if namespace_id:
                from trimcp.auth import set_namespace_context

                await set_namespace_context(conn, UUID(str(namespace_id)))

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
                            params->'entities' AS entities,
                            id AS event_id
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
                        SELECT memory_id, entities, event_id
                        FROM memory_events 
                        WHERE event_type = 'store_memory'
                    ),
                    historical_nodes AS (
                        SELECT DISTINCT ON (label)
                            jsonb_array_elements(entities)->>'label' AS label,
                            jsonb_array_elements(entities)->>'entity_type' AS entity_type,
                            memory_id,
                            event_id
                        FROM active_memories
                    )
                    SELECT n.label, n.entity_type, m.payload_ref,
                           m.embedding <=> $1::vector AS distance,
                           n.event_id
                    FROM historical_nodes n
                    JOIN memories m ON n.memory_id = m.id
                    ORDER BY distance ASC
                    LIMIT $2
                    """,
                    json.dumps(vector),
                    top_k,
                    namespace_id,
                    as_of,
                )
                # Verify signatures on event_log rows that contributed to this result.
                event_ids = [str(r["event_id"]) for r in rows if r.get("event_id")]
                await self._verify_time_travel_event_signatures(conn, event_ids)
            else:
                rows = await conn.fetch(
                    """
                    SELECT label, entity_type, payload_ref,
                           embedding <=> $1::vector AS distance
                    FROM kg_nodes
                    ORDER BY distance ASC
                    LIMIT $2
                    """,
                    json.dumps(vector),
                    top_k,
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

    # --- Step 2: BFS edge traversal (single PostgreSQL recursive CTE) ---

    async def _bfs(
        self,
        start_label: str,
        max_depth: int,
        namespace_id: str | None = None,
        as_of: datetime | None = None,
        *,
        _allow_global_sweep: bool = False,
        max_edges_per_node: int = MAX_EDGES_PER_NODE,
    ) -> tuple[set[str], list[GraphEdge]]:
        """
        BFS edge traversal over kg_edges — single PostgreSQL recursive CTE.

        Replaces the previous Python ``while queue:`` loop that issued N
        sequential SQL queries (one per BFS hop + one per visited label).
        The recursive CTE traverses the entire subgraph in one round-trip,
        then a follow-up ``SELECT`` fetches all matching edges at once.

        Security contract:
            ``namespace_id=None`` performs a **global** sweep across ALL tenants
            (queries ``kg_edges`` without namespace isolation).  This is ONLY
            safe for admin/diagnostic operations.  Tenant-facing callers MUST
            pass a namespace_id OR explicitly opt in with
            ``_allow_global_sweep=True``.

        Raises:
            ValueError: if ``namespace_id`` is None and ``_allow_global_sweep``
                        is not True (accidental global-sweep guard).
        """
        if namespace_id is None and not _allow_global_sweep:
            raise ValueError(
                "_bfs: namespace_id is required for tenant-scoped traversals. "
                "Pass _allow_global_sweep=True only for admin/diagnostic cross-tenant operations."
            )

        async with self.pg_pool.acquire() as conn:
            if namespace_id:
                from trimcp.auth import set_namespace_context

                await set_namespace_context(conn, UUID(str(namespace_id)))

            # ---- Single recursive CTE: find all reachable labels ----
            # The recursive branch discovers neighbors via ``kg_edges``
            # (or time-travel ``event_log``) up to ``max_depth``.  The
            # anchor is the caller-supplied ``start_label``.
            visited: set[str] = set()
            all_edges: list[GraphEdge] = []
            bfs_event_ids: list[str] = []

            if as_of and namespace_id:
                # Time-travel BFS: reconstruct edges from event_log
                labels = await conn.fetch(
                    """
                    WITH RECURSIVE traversal AS (
                        SELECT $1::text AS label, 0 AS depth
                        UNION
                        SELECT DISTINCT
                            CASE WHEN h.subject_label = t.label THEN h.object_label ELSE h.subject_label END,
                            t.depth + 1
                        FROM traversal t
                        JOIN LATERAL (
                            WITH ns AS (
                                SELECT id, parent_id,
                                       (metadata->'fork_config'->>'forked_from_as_of')::timestamptz AS forked_as_of
                                FROM namespaces WHERE id = $3::uuid
                            ),
                            memory_events AS (
                                SELECT DISTINCT ON ((params->>'memory_id')::uuid)
                                    (params->>'memory_id')::uuid AS memory_id,
                                    event_type, params->'triplets' AS triplets, id AS event_id
                                FROM event_log CROSS JOIN ns
                                WHERE (
                                    (namespace_id = ns.id AND occurred_at <= $4)
                                    OR (namespace_id = ns.parent_id AND occurred_at <= LEAST($4, ns.forked_as_of))
                                )
                                  AND event_type IN ('store_memory', 'forget_memory')
                                ORDER BY (params->>'memory_id')::uuid, occurred_at DESC, event_seq DESC
                            ),
                            active_memories AS (
                                SELECT memory_id, triplets, event_id
                                FROM memory_events WHERE event_type = 'store_memory'
                            ),
                            historical_edges AS (
                                SELECT
                                    jsonb_array_elements(triplets)->>'subject_label' AS subject_label,
                                    jsonb_array_elements(triplets)->>'predicate' AS predicate,
                                    jsonb_array_elements(triplets)->>'object_label' AS object_label,
                                    (jsonb_array_elements(triplets)->>'confidence')::float AS confidence,
                                    memory_id, event_id
                                FROM active_memories
                            )
                            SELECT e.subject_label, e.object_label, e.event_id
                            FROM historical_edges e
                            JOIN memories m ON e.memory_id = m.id
                            WHERE e.subject_label = t.label OR e.object_label = t.label
                            LIMIT $5
                        ) h ON true
                        WHERE t.depth < $2
                          AND (SELECT count(*) = 0 FROM traversal AS exclude
                               WHERE exclude.label IN (h.subject_label, h.object_label))
                          AND (SELECT count(DISTINCT label) FROM traversal) < $6
                    )
                    SELECT DISTINCT label FROM traversal ORDER BY depth ASC
                    """,
                    start_label,
                    max_depth,
                    namespace_id,
                    as_of,
                    max_edges_per_node,
                    MAX_NODES,
                )
                visited = {r["label"] for r in labels}

                # Batch-fetch all time-travel edges between visited labels
                if visited:
                    edge_rows = await conn.fetch(
                        """
                        WITH ns AS (
                            SELECT id, parent_id,
                                   (metadata->'fork_config'->>'forked_from_as_of')::timestamptz AS forked_as_of
                            FROM namespaces WHERE id = $2::uuid
                        ),
                        memory_events AS (
                            SELECT DISTINCT ON ((params->>'memory_id')::uuid)
                                (params->>'memory_id')::uuid AS memory_id,
                                event_type, params->'triplets' AS triplets, id AS event_id
                            FROM event_log CROSS JOIN ns
                            WHERE (
                                (namespace_id = ns.id AND occurred_at <= $3)
                                OR (namespace_id = ns.parent_id AND occurred_at <= LEAST($3, ns.forked_as_of))
                            )
                              AND event_type IN ('store_memory', 'forget_memory')
                            ORDER BY (params->>'memory_id')::uuid, occurred_at DESC, event_seq DESC
                        ),
                        active_memories AS (
                            SELECT memory_id, triplets, event_id
                            FROM memory_events WHERE event_type = 'store_memory'
                        ),
                        historical_edges AS (
                            SELECT
                                jsonb_array_elements(triplets)->>'subject_label' AS subject_label,
                                jsonb_array_elements(triplets)->>'predicate' AS predicate,
                                jsonb_array_elements(triplets)->>'object_label' AS object_label,
                                (jsonb_array_elements(triplets)->>'confidence')::float AS confidence,
                                memory_id, event_id
                            FROM active_memories
                        )
                        SELECT DISTINCT ON (e.subject_label, e.predicate, e.object_label)
                            e.subject_label, e.predicate, e.object_label, m.payload_ref,
                            e.confidence AS decayed_confidence, e.event_id
                        FROM historical_edges e
                        JOIN memories m ON e.memory_id = m.id
                        WHERE (e.subject_label = ANY($1::text[]) OR e.object_label = ANY($1::text[]))
                        ORDER BY e.subject_label, e.predicate, e.object_label, decayed_confidence DESC
                        """,
                        list(visited),
                        namespace_id,
                        as_of,
                    )
                    bfs_event_ids = [str(r["event_id"]) for r in edge_rows if r.get("event_id")]
                    all_edges = [
                        GraphEdge(
                            subject=r["subject_label"],
                            predicate=r["predicate"],
                            obj=r["object_label"],
                            confidence=r["decayed_confidence"],
                            payload_ref=r["payload_ref"],
                        )
                        for r in edge_rows
                    ]
            else:
                # Current-state BFS: single recursive CTE + batch edge fetch
                labels = await conn.fetch(
                    """
                    WITH RECURSIVE traversal AS (
                        SELECT $1::text AS label, 0 AS depth
                        UNION
                        SELECT DISTINCT
                            CASE WHEN e.subject_label = t.label THEN e.object_label ELSE e.subject_label END,
                            t.depth + 1
                        FROM traversal t
                        JOIN kg_edges e ON (e.subject_label = t.label OR e.object_label = t.label)
                        WHERE t.depth < $2
                          -- Exclude labels already visited (avoid cycles)
                          AND NOT EXISTS (
                              SELECT 1 FROM traversal AS seen
                              WHERE seen.label IN (e.subject_label, e.object_label)
                                AND seen.label != t.label
                          )
                          -- Respect MAX_NODES cap
                          AND (SELECT count(DISTINCT label) FROM traversal) < $3
                    )
                    SELECT DISTINCT label FROM traversal ORDER BY depth ASC
                    """,
                    start_label,
                    max_depth,
                    MAX_NODES,
                )
                visited = {r["label"] for r in labels}

                # Batch-fetch all edges between visited labels in one query
                if visited:
                    edge_rows = await conn.fetch(
                        """
                        SELECT DISTINCT ON (e.subject_label, e.predicate, e.object_label)
                            e.subject_label, e.predicate, e.object_label, e.payload_ref,
                            e.confidence * EXP(-0.01 * EXTRACT(EPOCH FROM (NOW() - e.updated_at)) / 86400)
                                AS decayed_confidence
                        FROM kg_edges e
                        WHERE (e.subject_label = ANY($1::text[]) OR e.object_label = ANY($1::text[]))
                        ORDER BY e.subject_label, e.predicate, e.object_label, decayed_confidence DESC
                        """,
                        list(visited),
                    )
                    all_edges = [
                        GraphEdge(
                            subject=r["subject_label"],
                            predicate=r["predicate"],
                            obj=r["object_label"],
                            confidence=r["decayed_confidence"],
                            payload_ref=r["payload_ref"],
                        )
                        for r in edge_rows
                    ]

            # Verify signatures on event_log rows if time-travel mode.
            if bfs_event_ids:
                await self._verify_time_travel_event_signatures(conn, bfs_event_ids)

        return visited, all_edges

    # --- Step 3: Hydrate source documents from MongoDB (batch) ---

    async def _hydrate_sources(
        self,
        mongo_ref_ids: set[str],
        restrict_user_id: str | None = None,
    ) -> list[dict]:
        """
        Hydrate source documents from MongoDB using batch ``$in`` queries.

        Replaces the previous N+1 pattern that called ``find_one`` sequentially
        for each ``payload_ref`` (up to 100 round-trips per graph search).
        Now uses two batch ``$in`` queries (one per collection), reducing
        round-trips to exactly 2 regardless of result size.

        When restrict_user_id is set (private graph search), only include
        documents owned by that user.
        """
        valid_refs = [ref for ref in mongo_ref_ids if ref]
        if not valid_refs:
            return []

        # Build ObjectId list — skip invalid refs with a warning.
        oids: list[ObjectId] = []
        for ref in valid_refs:
            try:
                oids.append(ObjectId(ref))
            except Exception as e:
                log.warning("Invalid payload_ref=%s: %s", ref, e)

        if not oids:
            return []

        db = self.mongo_client.memory_archive

        # Two batch queries — always exactly 2 round-trips, never N.
        ep_docs: dict[str, dict] = {}
        code_docs: dict[str, dict] = {}

        try:
            cursor = db.episodes.find({"_id": {"$in": oids}})
            async for doc in cursor:
                ep_docs[str(doc["_id"])] = doc
        except Exception as e:
            log.warning("Batch episodes hydration failed: %s", e)

        try:
            cursor = db.code_files.find({"_id": {"$in": oids}})
            async for doc in cursor:
                code_docs[str(doc["_id"])] = doc
        except Exception as e:
            log.warning("Batch code_files hydration failed: %s", e)

        sources: list[dict] = []
        for ref_id in valid_refs:
            doc = ep_docs.get(ref_id)
            if doc is not None:
                if restrict_user_id is not None and doc.get("user_id") != restrict_user_id:
                    continue
                raw = doc.get("raw_data", "")
                sources.append(
                    {
                        "payload_ref": ref_id,
                        "collection": "episodes",
                        "type": doc.get("type", "unknown"),
                        "excerpt": str(raw)[:600],
                    }
                )
                continue

            code_doc = code_docs.get(ref_id)
            if code_doc is not None:
                if restrict_user_id is not None and code_doc.get("user_id") != restrict_user_id:
                    continue
                raw = code_doc.get("raw_code", "")
                sources.append(
                    {
                        "payload_ref": ref_id,
                        "collection": "code_files",
                        "type": "code",
                        "filepath": code_doc.get("filepath"),
                        "language": code_doc.get("language"),
                        "excerpt": str(raw)[:600],
                    }
                )

        return sources

    # --- Public API ---

    async def search(
        self,
        query: str,
        namespace_id: str | None = None,
        max_depth: int = 2,
        anchor_top_k: int = 1,
        *,
        private: bool = False,
        user_id: str | None = None,
        as_of=None,
        _allow_global_sweep: bool = False,
        max_edges_per_node: int | None = None,
        edge_limit: int | None = None,
        edge_offset: int = 0,
    ) -> Subgraph:
        """
        Full GraphRAG traversal pipeline.
        Returns a Subgraph with nodes, edges, and hydrated source excerpts.

        Security contract:
            ``namespace_id=None`` performs a **global** sweep across ALL tenants
            (anchor + BFS without namespace isolation).  This is ONLY safe for
            admin/diagnostic operations.  Tenant-facing callers MUST pass a
            namespace_id OR explicitly opt in with ``_allow_global_sweep=True``.

        Args:
            private: If True, hydrate only Mongo sources belonging to user_id
                     (Phase 0; anchor/BFS use namespace-scoped RLS).
            max_edges_per_node: Upper bound on incident edges fetched per BFS step
                (SQL ``LIMIT``, ordered by confidence descending). Defaults to
                :data:`MAX_EDGES_PER_NODE`.
            edge_limit: If set, slice the deduplicated edge list to at most this many
                entries after ``edge_offset`` (response pagination).
            edge_offset: Start index into the deduplicated edge list.

        Raises:
            ValueError: if ``namespace_id`` is None and ``_allow_global_sweep``
                        is not True (accidental global-sweep guard).
        """
        if namespace_id is None and not _allow_global_sweep:
            raise ValueError(
                "search: namespace_id is required for tenant-scoped graph searches. "
                "Pass _allow_global_sweep=True only for admin/diagnostic cross-tenant operations."
            )
        per_node = max_edges_per_node if max_edges_per_node is not None else MAX_EDGES_PER_NODE
        if per_node < 1:
            raise ValueError("max_edges_per_node must be >= 1")
        if edge_offset < 0:
            raise ValueError("edge_offset must be >= 0")
        if edge_limit is not None and edge_limit < 1:
            raise ValueError("edge_limit must be >= 1 when provided")
        anchors = await self._find_anchor(
            query,
            namespace_id=namespace_id,
            top_k=anchor_top_k,
            as_of=as_of,
            _allow_global_sweep=_allow_global_sweep,
        )
        if not anchors:
            log.info("No anchor node found in knowledge graph.")
            return Subgraph(anchor="<none>")

        anchor = anchors[0]
        log.info("Anchor: '%s' (distance=%.4f)", anchor.label, anchor.distance)

        visited_labels, edges = await self._bfs(
            anchor.label,
            max_depth=max_depth,
            namespace_id=namespace_id,
            as_of=as_of,
            _allow_global_sweep=_allow_global_sweep,
            max_edges_per_node=per_node,
        )

        # Fetch full node metadata for all visited labels
        async with self.pg_pool.acquire() as conn:
            if namespace_id:
                from trimcp.auth import set_namespace_context

                await set_namespace_context(conn, UUID(str(namespace_id)))

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
                            params->'entities' AS entities,
                            id AS event_id
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
                        SELECT memory_id, entities, event_id
                        FROM memory_events 
                        WHERE event_type = 'store_memory'
                    ),
                    historical_nodes AS (
                        SELECT DISTINCT ON (label)
                            jsonb_array_elements(entities)->>'label' AS label,
                            jsonb_array_elements(entities)->>'entity_type' AS entity_type,
                            memory_id,
                            event_id
                        FROM active_memories
                    )
                    SELECT n.label, n.entity_type, m.payload_ref, n.event_id
                    FROM historical_nodes n
                    JOIN memories m ON n.memory_id = m.id
                    WHERE n.label = ANY($1::text[])
                    """,
                    list(visited_labels),
                    namespace_id,
                    as_of,
                )
                # Verify signatures on event_log rows that contributed to node metadata.
                event_ids = [str(r["event_id"]) for r in rows if r.get("event_id")]
                await self._verify_time_travel_event_signatures(conn, event_ids)
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

        # Deduplicate edges (BFS can traverse same edge from both directions)
        seen_edges: set[tuple] = set()
        unique_edges = []
        for e in edges:
            key = (e.subject, e.predicate, e.obj)
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(e)

        edge_total = len(unique_edges)
        off = edge_offset
        if edge_limit is None:
            page_edges = unique_edges[off:]
        else:
            page_edges = unique_edges[off : off + edge_limit]
        has_more = edge_total > off + len(page_edges)

        labels_for_page = {anchor.label}
        for e in page_edges:
            labels_for_page.add(e.subject)
            labels_for_page.add(e.obj)
        nodes_for_page = [n for n in nodes if n.label in labels_for_page]

        all_refs = {n.payload_ref for n in nodes_for_page if n.payload_ref}
        all_refs |= {e.payload_ref for e in page_edges if e.payload_ref}
        restrict = user_id if private else None
        sources = await self._hydrate_sources(all_refs, restrict_user_id=restrict)

        return Subgraph(
            anchor=anchor.label,
            nodes=nodes_for_page,
            edges=page_edges,
            sources=sources,
            edge_total=edge_total,
            edge_offset=off,
            edge_limit=edge_limit,
            has_more_edges=has_more,
            max_edges_per_node=per_node,
        )

    async def get_subgraph(self, *args, **kwargs) -> Subgraph:
        """Alias for :meth:`search` — subgraph retrieval with edge pagination."""
        return await self.search(*args, **kwargs)
