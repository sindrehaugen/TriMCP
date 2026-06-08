"""
nce/atms.py
===========
BATCH-P3-001 — Assumption-Based Truth Maintenance System (ATMS)

Implements logical justification tracking, nogood environment recording,
and recursive deprecation cascades for memory nodes and infrastructure
topology entities when underlying assumptions are violated.

Integrates with Judea Pearl's do-calculus CausalGraph from `nce/causal/correlation.py`
to propagate invalidations downstream using directional graph semantics.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nce.causal.correlation import _FORWARD_FAILURE_TYPES, _REVERSE_FAILURE_TYPES, CausalGraph

log = logging.getLogger("nce.atms")


class ATMSNodeType(str, Enum):
    """Classification of nodes within the ATMS.

    - ASSUMPTION: Baseline belief state that can be directly invalidated/asserted.
    - PREMISE: Fact that is unconditionally and eternally valid.
    - DERIVED: Fact whose validity depends on at least one justification.
    """

    ASSUMPTION = "assumption"
    PREMISE = "premise"
    DERIVED = "derived"


@dataclass(frozen=True)
class Justification:
    """A logical support link: antecedents -> consequent.

    If all antecedents are valid, the consequent receives support to be valid.
    """

    consequent: str
    antecedents: frozenset[str]
    description: str = ""


@dataclass
class ATMSNode:
    """A node tracked by the Truth Maintenance System."""

    node_id: str
    node_type: ATMSNodeType
    is_valid: bool = True
    justifications: list[Justification] = field(default_factory=list)


class ATMSEngine:
    """Assumption-Based Truth Maintenance System Engine.

    Manages logical dependencies (justifications) between nodes, tracks contradictions,
    and runs recursive deprecation cascades when base assumptions fail.
    """

    def __init__(self, namespace_id: uuid.UUID | None = None) -> None:
        self.namespace_id = namespace_id
        self.nodes: dict[str, ATMSNode] = {}
        self.contradictions: list[tuple[str, str]] = []

    def register_node(
        self,
        node_id: str,
        node_type: ATMSNodeType | str,
        is_valid: bool = True,
    ) -> ATMSNode:
        """Registers a node in the ATMS. If already registered, updates its type/validity."""
        ntype = ATMSNodeType(node_type) if isinstance(node_type, str) else node_type
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.node_type = ntype
            node.is_valid = is_valid
        else:
            node = ATMSNode(node_id=node_id, node_type=ntype, is_valid=is_valid)
            self.nodes[node_id] = node
        return node

    def add_justification(
        self,
        consequent_id: str,
        antecedents: set[str] | frozenset[str],
        description: str = "",
    ) -> Justification:
        """Adds a logical justification for a consequent node."""
        if consequent_id not in self.nodes:
            self.register_node(consequent_id, ATMSNodeType.DERIVED)

        for ant in antecedents:
            if ant not in self.nodes:
                self.register_node(ant, ATMSNodeType.ASSUMPTION)

        just = Justification(
            consequent=consequent_id,
            antecedents=frozenset(antecedents),
            description=description,
        )
        self.nodes[consequent_id].justifications.append(just)
        return just

    def is_node_provably_valid(
        self,
        node_id: str,
        active_path: set[str],
        memo: dict[str, bool] | None = None,
    ) -> bool:
        """Recursively checks if a node is logically valid based on active assumptions and premises.

        Detects self-supporting cycles (circular justifications) and marks them invalid.
        Optimized with a memoization cache for acyclic sub-graphs.
        """
        # Cache is only valid for computations with no active path dependency
        if memo is not None and not active_path and node_id in memo:
            return memo[node_id]

        node = self.nodes.get(node_id)
        if not node:
            return False

        if node.node_type == ATMSNodeType.PREMISE:
            return True

        if node.node_type == ATMSNodeType.ASSUMPTION:
            return node.is_valid

        # Cycle guard: circular justification with no base support
        if node_id in active_path:
            return False

        new_path = active_path | {node_id}
        for just in node.justifications:
            # A justification is valid if all its antecedents are recursively provably valid
            if all(self.is_node_provably_valid(ant, new_path, memo) for ant in just.antecedents):
                if memo is not None and not active_path:
                    memo[node_id] = True
                return True

        if memo is not None and not active_path:
            memo[node_id] = False
        return False

    def invalidate_assumption(self, assumption_id: str) -> set[str]:
        """Invalidates an assumption and recursively cascades deprecation downstream.

        Returns the set of all node IDs affected (invalidated) by the cascade.
        """
        node = self.nodes.get(assumption_id)
        if not node:
            log.warning("Node %s not found in ATMS", assumption_id)
            return set()

        if node.node_type == ATMSNodeType.PREMISE:
            log.warning("Cannot invalidate PREMISE node %s", assumption_id)
            return set()

        return self.propagate_deprecation(assumption_id)

    def register_contradiction(
        self,
        node_a_id: str,
        node_b_id: str,
        resolution_strategy: str = "invalidate_a",
    ) -> set[str]:
        """Registers a contradiction (nogood environment) between two nodes.

        Applies the selected resolution strategy to invalidate the target baseline
        belief and cascades invalidation downstream.
        """
        self.contradictions.append((node_a_id, node_b_id))
        self.add_justification("FALSE", {node_a_id, node_b_id}, "Contradiction")

        node_a = self.nodes.get(node_a_id)
        node_b = self.nodes.get(node_b_id)

        cascade_set: set[str] = set()
        if node_a and node_b and node_a.is_valid and node_b.is_valid:
            if resolution_strategy == "invalidate_a":
                cascade_set.update(self.invalidate_assumption(node_a_id))
            elif resolution_strategy == "invalidate_b":
                cascade_set.update(self.invalidate_assumption(node_b_id))
            elif resolution_strategy == "invalidate_both":
                cascade_set.update(self.invalidate_assumption(node_a_id))
                cascade_set.update(self.invalidate_assumption(node_b_id))

        return cascade_set

    def propagate_deprecation(self, node_id: str, visited: set[str] | None = None) -> set[str]:
        """Recursively flags all downstream dependent nodes linked to an invalidated node.

        Ensures cycle-safety via visited-set tracking and recursive proof checking.
        """
        if visited is None:
            visited = set()

        if node_id in visited:
            return set()
        visited.add(node_id)

        node = self.nodes.get(node_id)
        if not node:
            return set()

        # Invalidate current node
        old_valid = node.is_valid
        if node.node_type != ATMSNodeType.PREMISE:
            node.is_valid = False

        cascade_set = {node_id} if old_valid else set()

        # Evaluation memoization cache for this propagation step
        memo: dict[str, bool] = {}

        # Recursively search for children (derived nodes dependent on this node)
        for child_id, child_node in list(self.nodes.items()):
            if child_node.node_type == ATMSNodeType.DERIVED and child_node.is_valid:
                # If the derived node is no longer recursively provable, invalidate and recurse
                if not self.is_node_provably_valid(child_id, set(), memo):
                    child_cascade = self.propagate_deprecation(child_id, visited)
                    cascade_set.update(child_cascade)

        return cascade_set

    def evaluate_belief_states(self) -> None:
        """Evaluates belief states for all nodes using recursive proof search."""
        memo: dict[str, bool] = {}
        for node_id, node in self.nodes.items():
            if node.node_type == ATMSNodeType.DERIVED:
                node.is_valid = self.is_node_provably_valid(node_id, set(), memo)
            elif node.node_type == ATMSNodeType.PREMISE:
                node.is_valid = True


def build_atms_from_causal_graph(graph: CausalGraph) -> ATMSEngine:
    """Translates a CausalGraph into an ATMSEngine structure.

    Maps topology failure propagation directions directly to logical dependencies:
    - FORWARD propagation: target depends on source.
    - REVERSE propagation: source depends on target.
    """
    ns_id = None
    if graph._nodes:
        first_node = next(iter(graph._nodes.values()))
        ns_id = first_node.namespace_id

    atms = ATMSEngine(namespace_id=ns_id)

    # 1. Gather all incoming justifications
    dependencies: dict[str, set[str]] = {nid: set() for nid in graph.node_ids}

    for src_id, edges in graph._outgoing.items():
        for edge in edges:
            if edge.edge_type in _FORWARD_FAILURE_TYPES:
                # FORWARD: target depends on source
                dependencies[edge.target_node_id].add(edge.source_node_id)
            elif edge.edge_type in _REVERSE_FAILURE_TYPES:
                # REVERSE: source depends on target
                dependencies[edge.source_node_id].add(edge.target_node_id)

    # 2. Register nodes (ASSUMPTION for roots, DERIVED for dependent nodes)
    for nid in graph.node_ids:
        if dependencies[nid]:
            atms.register_node(nid, ATMSNodeType.DERIVED)
            atms.add_justification(nid, dependencies[nid], "Causal dependency")
        else:
            atms.register_node(nid, ATMSNodeType.ASSUMPTION)

    return atms


# ---------------------------------------------------------------------------
# Database-driven state updates & wiring
# ---------------------------------------------------------------------------

def is_valid_uuid(val: str) -> bool:
    """Returns True if val is a valid UUID string."""
    try:
        uuid.UUID(val)
        return True
    except ValueError:
        return False


async def evaluate_atms_intervention(
    conn: Any,  # asyncpg.Connection
    namespace_id: uuid.UUID,
    invalidated_node_id: str,
) -> set[str]:
    """Loads the causal graph for a namespace, builds an ATMS, and cascades invalidation."""
    graph = await CausalGraph.load_from_db(conn, namespace_id)
    atms = build_atms_from_causal_graph(graph)

    # Invalidate the target node and get all affected downstream nodes
    cascade = atms.invalidate_assumption(invalidated_node_id)
    if invalidated_node_id in atms.nodes:
        # Force invalidation if registered as DERIVED
        cascade.update(atms.propagate_deprecation(invalidated_node_id))

    return cascade


async def persist_atms_invalidation(
    conn: Any,  # asyncpg.Connection
    namespace_id: uuid.UUID,
    invalidated_node_ids: set[str],
) -> int:
    """Soft-deletes (valid_to = now()) invalidated memories and topology edges in DB."""
    if not invalidated_node_ids:
        return 0

    # 1. Update memories
    uuid_candidates = [uuid.UUID(nid) for nid in invalidated_node_ids if is_valid_uuid(nid)]
    count_mem = 0
    if uuid_candidates:
        res_mem = await conn.execute(
            """
            UPDATE memories
            SET valid_to = now()
            WHERE namespace_id = $1::uuid
              AND id = ANY($2::uuid[])
              AND valid_to IS NULL
            """,
            namespace_id,
            uuid_candidates,
        )
        count_mem = int(res_mem.split()[-1]) if res_mem else 0

    # 2. Update topology edges
    res_topo = await conn.execute(
        """
        UPDATE topology_graph
        SET valid_to = now()
        WHERE namespace_id = $1::uuid
          AND (source_node_id = ANY($2::text[]) OR target_node_id = ANY($2::text[]))
          AND valid_to IS NULL
        """,
        namespace_id,
        list(invalidated_node_ids),
    )
    count_topo = int(res_topo.split()[-1]) if res_topo else 0

    log.info(
        "Persisted ATMS invalidation cascade for namespace=%s: "
        "soft-deleted %d memories, %d topology edges",
        namespace_id,
        count_mem,
        count_topo,
    )
    return count_mem + count_topo
