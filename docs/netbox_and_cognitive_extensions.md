# NetBox Integration & Phase 3 Cognitive Spec

This document details the architecture, design specifications, and signal flows for the Phase 3 enhancements: **Assumption-Based Truth Maintenance System (ATMS)**, **Counterfactual Chrono-Branching**, **Spiking spreading activation**, **Longitudinal Operator Stress Tracking**, **Active Learning operator loops**, **NetBox vertical modules**, and the **NetBox Cognitive Dashboard Plugin**.

---

## 1. Assumption-Based Truth Maintenance System (ATMS)
The ATMS module ([nce/atms.py](file:///c:/Users/SindreLøvlieHaugen/Documents/systemer/TriMCP/TriMCP-1/nce/atms.py)) maintains logical consistency across beliefs and causal statements derived from incoming telemetry.

### Data Structures
* **ATMSNode**: A logical unit representing a state.
  * `node_type`: `ASSUMPTION` (can be dynamically retracted), `PREMISE` (always true), or `DERIVED` (requires a justification).
  * `state`: `VALID` (believed to be true) or `DEPRECATED` (invalidated).
* **Justification**: A logical relation mapping a set of cause nodes to a target node:
  $$\text{antecedents} \implies \text{consequent}$$

### Cyclic-Safe Recursive Belief Validation
Evaluating whether a derived node is valid involves traversing the justification graph:
1. **Premise**: Immediately valid.
2. **Assumption**: Valid if `state == VALID`.
3. **Derived Node**: Valid if there exists at least one justification where *all* antecedents are provably valid.
4. **Cycle-Prevention**: An in-memory traversal set tracks visited nodes to prevent infinite recursion on self-referencing loops.

### Invalidation & Deprecation Propagation
When an `ASSUMPTION` node is deprecated, NCE triggers a recursive update:
1. Mark the assumption node as `DEPRECATED`.
2. Recursively locate all `DERIVED` nodes where the deprecated node is an antecedent.
3. Re-evaluate their justifications. If no alternate valid justifications exist, mark them as `DEPRECATED`.
4. Trigger database hooks to perform soft-deletes (`valid_to = NOW()`) on matching rows inside the active `memories` and `topology_graph` namespaces.

---

## 2. Counterfactual Chrono-Branching
NCE enables timeline "What-If" counterfactual simulations using chrono-branching ([nce/causal/chrono.py](file:///c:/Users/SindreLøvlieHaugen/Documents/systemer/TriMCP/TriMCP-1/nce/causal/chrono.py)).

### Thread & Task Safety
* Uses python `contextvars.ContextVar` (`chrono_branch_var`) to bind active branch states to the current async task execution context.
* Prevents concurrent timeline operations in other tasks or web requests from interfering with or leaking data into parallel transactions.

### Memory Overlay & Isolation
When a timeline branch context is opened (`with branch_timeline(namespace_id, schema_id, target_time):`):
1. Database reads from `topology_graph` and `event_log` filter data up to `occurred_at <= target_time`.
2. All subsequent in-memory operations overlay dynamic counterfactual mutations (e.g. node deletion, link additions, parameter overrides) on the active `CausalGraph` cache.
3. No raw table writes occur; production data remains isolated, allowing zero-risk downstream propagation modeling.

---

## 3. Spiking Spreading Activation Engine
The neuromorphic engine ([nce/graph_query.py](file:///c:/Users/SindreLøvlieHaugen/Documents/systemer/TriMCP/TriMCP-1/nce/graph_query.py)) simulates charge propagation across the Knowledge Graph.

### Spiking Neural Network Mechanics
At each time step $t$:
1. **Firing Detection**: Any node $i$ with membrane potential $V_i(t) \ge \theta$ is added to the firing set. Its potential is reset to $0.0$.
2. **Charge Transfer**: Fired nodes distribute charge to their direct neighbors $j$:
   $$V_j(t+1) = V_j(t) \cdot \lambda + \alpha \cdot V_i(t) \cdot w_{ij}$$
   Where:
   * $\lambda$ = decay coefficient.
   * $\alpha$ = transfer efficiency.
   * $w_{ij}$ = weight of the edge between $i$ and $j$.
3. **Membrane Clamping**: To ensure numerical stability, all potentials are clamped at a hard limit `max_charge = 10.0`.
4. **Peak Tracking**: The engine records the historical maximum potential (`max_potentials`) reached by nodes during the simulation to retain decayed intermediate nodes in search results.

### Symmetrical Weight Adaptation (LTP/LTD)
Synaptic weights are adapted based on the outcomes of downstream decisions:
* **Success (LTP)**: Potentiates edge weight $w$:
  $$w_{\text{new}} = w + \eta \cdot (1.0 - w)$$
* **Failure (LTD)**: Depresses edge weight $w$:
  $$w_{\text{new}} = w - \eta \cdot w$$
* **Bidirectional/Symmetrical updates**: Queries and updates matching edges in *both* directions (`(src, tgt)` and `(tgt, src)`) inside `kg_edges` and `topology_graph` tables.
* **Savepoint Isolation**: Each edge update executes in a nested database savepoint context manager, isolating lock contention (`LockNotAvailableError`) and preventing transaction poisoning.

---

## 4. Longitudinal Operator Stress Tracking
The stress analytics module ([nce/analytics/stress.py](file:///c:/Users/SindreLøvlieHaugen/Documents/systemer/TriMCP/TriMCP-1/nce/analytics/stress.py)) monitors operator cognitive load while preserving data privacy.

### Analytics Pipeline
1. **Biometric Extraction**: Extracts the operator's emotional state vector (specifically index 5 representing frustration) from `empathic_tensor` records.
2. **Burnout Standby Triggers**: If frustration remains $> 7.0$ for more than 5 consecutive shifts, NCE generates a burnout alert.
3. **On-Call Weight Redistribution**: NetBox integration hooks immediately update on-call routing weights. The burned-out operator's standby weight is set to `0.0`, and their active tickets are redistributed proportionally to healthy operators.
4. **Biometric Field Encryption**: All raw `empathic_tensor` arrays and fatigue profiles are encrypted at rest using AES-256-GCM via the NCE Master Key.

---

## 5. Active Learning Queue & Gamification
Active learning ([nce/active_learning.py](file:///c:/Users/SindreLøvlieHaugen/Documents/systemer/TriMCP/TriMCP-1/nce/active_learning.py)) intercepts and quarantines low-confidence memories for operator validation.

```
                  store_memory()
                        │
             R = Confidence Score
                        │
                  ┌─────┴─────┐
              R >= 0.65    R < 0.65
                  │           │
              (Bypass)   (Quarantine)
                  │           │
           TriStack Write     └──► active_learning_queue
                                          │
                                   Operator Dashboard
                                   (Confirm / Reject)
```

### Gamification & Streak Rewards
Operators are incentivized via a gamified micro-confirmation interface:
* **Confirming** a memory promotes it to the main stack and rewards **10 XP**.
* **Rejecting** a memory flags it as discarded and rewards **5 XP**.
* **Confirmation Streaks**: Consecutive validations multiply XP rewards, maintaining engagement.

---

## 6. NetBox Vertical Integration Modules
NCE integrates natively with NetBox infrastructure managers ([nce/vertical_modules/netbox/](file:///c:/Users/SindreLøvlieHaugen/Documents/systemer/TriMCP/TriMCP-1/nce/vertical_modules/netbox/)):

* **GraphQL Topology Activation**: Pulls complete site, rack, device, and connection mappings in a single polymorphic query. Parses polymorphic cable terminations to construct an undirected adjacency matrix.
* **Unregistered Asset Discovery**: Compares live discovered telemetry against the cached NetBox graph. Identifies missing components and stages them on draft branches using the NetBox Branching API.
* **Circuit Provider Escalator**: Utilizes Pearl's do-calculus causal engine to determine if specific circuit thresholds caused observed device failures, auto-generating upstream provider escalations.

---

## 7. NetBox Cognitive Dashboard Plugin
Exposes NCE cognitive data directly within NetBox detail layouts using a PyPI-compatible package layout under `src/nce-netbox-plugin/`.

### Django Views & PostgreSQL RLS Context
The stats controller ([views.py](file:///c:/Users/SindreLøvlieHaugen/Documents/systemer/TriMCP/TriMCP-1/src/nce-netbox-plugin/nce_netbox_plugin/api/views.py)) resolves tenant mappings:
1. Resolves the NetBox object's tenant slug to map it to an NCE namespace.
2. Opens a Django `transaction.atomic()` transaction.
3. Sets the PostgreSQL session variable:
   `SELECT set_config('nce.namespace_id', <ns_uuid>, true);`
4. Queries RLS-enforced database tables (`event_log`, `v3_cognitive_ledger`, `active_learning_queue`, `replay_runs`) within that transaction scope.
5. Employs a zero-dependency fallback telemetry generator if NCE database tables do not exist in the active schema.
