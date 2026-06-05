-- 010_citus_sharding.sql
-- Citus Multi-Tenant Sharding Initializer for NCE Phase 2
-- Enables Citus distributed PostgreSQL and configures tenant-scoped table sharding.
--
-- This migration:
-- 1. Enables the Citus extension
-- 2. Creates the topology_graph table (new in Phase 2)
-- 3. Converts reference tables to Citus reference tables (replicated across workers)
-- 4. Distributes core tenant-scoped tables on tenant_id hash key
-- 5. Configures Two-Phase Commit for cross-shard consistency
--
-- Backwards Compatibility: All existing data remains accessible. Sharding is transparent
-- to the application layer after this migration completes.
-- ============================================================================

-- Enable Citus extension (requires Citus PostgreSQL package installed)
CREATE EXTENSION IF NOT EXISTS citus;

-- Enable distributed transactions (2PC) for consistency across shards
ALTER SYSTEM SET citus.enable_ddl_propagation = on;
ALTER SYSTEM SET citus.multi_shard_commit_protocol = '2pc';

-- Restart PostgreSQL to apply system-level configuration
-- Note: In production, this is typically done via operator controls.
-- For dev/test, this can be done with: SELECT pg_reload_conf();

-- ============================================================================
-- PHASE 1: Create the topology_graph table (new in Phase 2)
-- ============================================================================
-- Stores the topological graph of infrastructure entities: devices, services, apps.
-- Used by Causal Inference Layer for do-calculus and spreading activation.

CREATE TABLE IF NOT EXISTS topology_graph (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id        UUID        NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    source_node_id      TEXT        NOT NULL,  -- Entity identifier (hostname, service_id, etc.)
    source_node_type    TEXT        NOT NULL,  -- Type: "device", "service", "app", "circuit"
    target_node_id      TEXT        NOT NULL,  -- Target entity identifier
    target_node_type    TEXT        NOT NULL,  -- Type: "device", "service", "app", "circuit"
    edge_type           TEXT        NOT NULL,  -- Relationship type: "connected_to", "depends_on", "host_application", "powered_by"
    decay_coefficient   FLOAT8      NOT NULL DEFAULT 0.001,  -- $\mu$ in decay model
    confidence_score    FLOAT8      NOT NULL DEFAULT 0.9,    -- Initial confidence (0.0 to 1.0)
    last_verified      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata            JSONB       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_topology_graph_namespace_id
    ON topology_graph(namespace_id);

CREATE INDEX IF NOT EXISTS idx_topology_graph_source_node
    ON topology_graph(namespace_id, source_node_id);

CREATE INDEX IF NOT EXISTS idx_topology_graph_target_node
    ON topology_graph(namespace_id, target_node_id);

CREATE INDEX IF NOT EXISTS idx_topology_graph_edge_type
    ON topology_graph(namespace_id, edge_type);

-- Enable Row-Level Security (same pattern as v3_cognitive_ledger)
ALTER TABLE topology_graph ENABLE ROW LEVEL SECURITY;

CREATE POLICY topology_graph_tenant_isolation ON topology_graph
    FOR ALL
    USING (namespace_id = get_nce_namespace());

-- Grant permissions to application roles
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON topology_graph TO nce_app;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_gc') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON topology_graph TO nce_gc;
    END IF;
END $$;

-- ============================================================================
-- PHASE 2: Configure Reference Tables (replicated across all workers)
-- ============================================================================
-- Reference tables are small lookup tables needed by distributed tables.
-- Citus replicates them to all worker nodes automatically.

-- namespaces: Tenant boundaries (small, slow-changing)
SELECT create_reference_table('namespaces');

-- signing_keys: Cryptographic key references (small, replicated for verification)
SELECT create_reference_table('signing_keys');

-- ============================================================================
-- PHASE 3: Distribute Core Tenant-Scoped Tables on tenant_id
-- ============================================================================
-- These tables are sharded by tenant_id hash key across Citus worker nodes.
-- All application queries must include tenant_id for co-location benefits.

-- memories: All episodic, semantic, and code memories
-- Shard key: namespace_id (maps to tenant_id via foreign key)
SELECT create_distributed_table('memories', 'namespace_id', shard_count => 32);

-- event_log: Immutable event ledger with monthly partitions
-- Shard key: namespace_id
SELECT create_distributed_table('event_log', 'namespace_id', shard_count => 32);

-- topology_graph: Infrastructure topology and causal graphs
-- Shard key: namespace_id
SELECT create_distributed_table('topology_graph', 'namespace_id', shard_count => 32);

-- v3_cognitive_ledger: Empathic tensor storage for Phase 3
-- Shard key: namespace_id
SELECT create_distributed_table('v3_cognitive_ledger', 'namespace_id', shard_count => 32);

-- ============================================================================
-- PHASE 4: Configure Two-Phase Commit (2PC) for Cross-Shard Consistency
-- ============================================================================
-- Two-Phase Commit ensures ACID semantics across multiple shards.
-- Overhead: ~5-10% latency per distributed transaction.

-- Set 2PC protocol at database level (can also be set per session)
ALTER DATABASE postgres SET citus.multi_shard_commit_protocol = '2pc';

-- Configure 2PC timeout (default 60s, increase for slow networks)
ALTER SYSTEM SET max_prepared_transactions = 256;

-- ============================================================================
-- PHASE 5: Update Distributed Query Configuration
-- ============================================================================
-- These settings optimize routing and execution for multi-tenant queries.

-- Enable adaptive executor for smart query planning
ALTER SYSTEM SET citus.executor_type = 'adaptive';

-- Set reasonable limits on multi-shard queries (prevent runaway scans)
ALTER SYSTEM SET citus.max_adaptive_executor_pool_size = 16;

-- Enable connection caching to worker nodes (reduces connection overhead)
ALTER SYSTEM SET citus.connection_cache_expiration = 600000;  -- 10 minutes

-- Log all DDL changes across all shards (required for Phase 2+ operations)
ALTER SYSTEM SET citus.log_distributed_deadlock_entries = on;

-- ============================================================================
-- PHASE 6: Create Shard Indexes for Common Query Patterns
-- ============================================================================
-- Citus automatically propagates these indexes to all shards.

-- Fast lookup of memories by namespace and creation time (common scan pattern)
CREATE INDEX IF NOT EXISTS idx_memories_namespace_created
    ON memories(namespace_id, created_at DESC)
    WHERE pii_redacted = false;

-- Fast lookup of high-confidence memories for ranking
CREATE INDEX IF NOT EXISTS idx_memories_confidence
    ON memories(namespace_id, (metadata->>'confidence_score'))
    WHERE valid_to IS NULL;

-- Fast event_log lookups by namespace and event_type (for filtering dashboards)
CREATE INDEX IF NOT EXISTS idx_event_log_namespace_type
    ON event_log(namespace_id, event_type, occurred_at DESC);

-- Fast topology graph traversal by source node (spreading activation queries)
CREATE INDEX IF NOT EXISTS idx_topology_source_traversal
    ON topology_graph(namespace_id, source_node_id, edge_type);

-- Fast topology graph traversal by target node (incoming dependencies)
CREATE INDEX IF NOT EXISTS idx_topology_target_traversal
    ON topology_graph(namespace_id, target_node_id, edge_type);

-- Fast v3_cognitive_ledger lookups by memory reference
CREATE INDEX IF NOT EXISTS idx_v3_cognitive_memory
    ON v3_cognitive_ledger(namespace_id, memory_id)
    WHERE memory_id IS NOT NULL;

-- ============================================================================
-- PHASE 7: Verify Shard Distribution and Consistency
-- ============================================================================
-- Queries for debugging and monitoring shard distribution.
-- These should be run after migration completes to validate setup.

-- Create helper view to monitor shard distribution
CREATE OR REPLACE VIEW v_citus_shard_distribution AS
SELECT
    logicalrelid::regclass AS table_name,
    count(DISTINCT shardid) AS shard_count,
    count(DISTINCT nodeport) AS worker_node_count,
    count(*) AS total_shardlet_count
FROM pg_dist_placement
GROUP BY logicalrelid
ORDER BY logicalrelid::text;

-- Create helper view to monitor shard size distribution
CREATE OR REPLACE VIEW v_citus_shard_sizes AS
SELECT
    nodename,
    sum(shardlength) / (1024.0 * 1024.0) AS total_size_mb,
    count(*) AS shard_count,
    min(shardlength) AS min_shard_bytes,
    max(shardlength) AS max_shard_bytes
FROM pg_dist_placement
JOIN pg_dist_shard USING (shardid)
JOIN pg_dist_shard_placement USING (shardid)
GROUP BY nodename
ORDER BY nodename;

-- ============================================================================
-- PHASE 8: Document Distributed Table Metadata
-- ============================================================================

COMMENT ON TABLE memories IS
'Distributed table: memories - sharded on namespace_id (tenant_id).
All episodic, semantic, and code memories across tenants.
Row-level security: enabled (namespace_id via get_nce_namespace())
Vector index: HNSW cosine on embedding(768)';

COMMENT ON TABLE event_log IS
'Distributed table: event_log - sharded on namespace_id (tenant_id).
Immutable ledger of all cognitive events. Monthly range partitions.
Row-level security: enabled (namespace_id via get_nce_namespace())
Unique constraint: (namespace_id, event_seq, occurred_at)';

COMMENT ON TABLE topology_graph IS
'Distributed table: topology_graph - sharded on namespace_id (tenant_id).
Infrastructure topology graph for causal inference and spreading activation.
Edge types: connected_to, depends_on, host_application, powered_by
Row-level security: enabled (namespace_id via get_nce_namespace())
Used by: Pearl do-calculus, ATMS (Phase 3)';

COMMENT ON TABLE v3_cognitive_ledger IS
'Distributed table: v3_cognitive_ledger - sharded on namespace_id (tenant_id).
Empathic tensor storage: [valence, arousal, dominance, temporal_demand, mental_demand, frustration]
Vector index: HNSW cosine on empathic_tensor(6)
Row-level security: enabled (namespace_id via get_nce_namespace())
Used by: Memory decay (Phase 2), Operator stress tracking (Phase 3)';

COMMENT ON TABLE namespaces IS
'Reference table: namespaces - replicated to all worker nodes.
Tenant boundaries and multi-tenancy root. Small, replicated for fast joins.
All distributed tables have foreign keys to namespaces.id.';

COMMENT ON TABLE signing_keys IS
'Reference table: signing_keys - replicated to all worker nodes.
Cryptographic key references for WORM ledger verification.
Small, replicated for fast signature validation across shards.';

-- ============================================================================
-- Migration Complete
-- ============================================================================
-- Summary:
-- - Citus extension enabled
-- - Topology_graph table created and distributed
-- - Reference tables: namespaces, signing_keys (replicated)
-- - Distributed tables: memories, event_log, topology_graph, v3_cognitive_ledger (32 shards each)
-- - 2PC configured for cross-shard ACID consistency
-- - Shard indexes created for common query patterns
-- - Monitoring views created for shard distribution
--
-- Next steps (Phase 2 Batch 2-4):
-- - BATCH-P2-002: Implement Ebbinghaus forgetting curves in nce/temporal_decay.py
-- - BATCH-P2-003: Cascade Pruning Engine (cascade_delete_tenant stored procedure)
-- - BATCH-P2-004: Causal Inference Layer (Pearl do-calculus in nce/causal_inference.py)
