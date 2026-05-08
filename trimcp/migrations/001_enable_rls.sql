-- ============================================================================
-- TriMCP Migration: Enable Row-Level Security (RLS)
-- Target: P0 Security Gap - Multi-tenant Isolation
-- ============================================================================

-- 1. Create a restricted application role if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trimcp_app') THEN
        CREATE ROLE trimcp_app;
    END IF;
END $$;

-- 2. Define the unified isolation logic
-- We use a helper function to avoid repeated current_setting logic in policies
CREATE OR REPLACE FUNCTION get_trimcp_namespace() RETURNS uuid AS $$
    SELECT current_setting('trimcp.namespace_id', true)::uuid;
$$ LANGUAGE sql STABLE;

-- 3. List of tables requiring isolation
-- memories, pii_redactions, memory_salience, contradictions, 
-- memory_embeddings, kg_node_embeddings, consolidation_runs, 
-- event_log, a2a_grants, resource_quotas.

-- NOTE: kg_nodes and kg_edges are intentionally global/shared in the current 
-- architecture (labels are deduplicated across namespaces). Access control 
-- to their source is handled via the 'memories' table link.

DO $$
DECLARE
    t text;
    tables_to_isolate text[] := ARRAY[
        'memories', 
        'pii_redactions', 
        'memory_salience', 
        'contradictions', 
        'memory_embeddings', 
        'kg_node_embeddings', 
        'consolidation_runs', 
        'event_log', 
        'a2a_grants', 
        'resource_quotas'
    ];
BEGIN
    FOREACH t IN ARRAY tables_to_isolate
    LOOP
        -- Enable RLS
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);

        -- Drop existing policy if it exists (idempotency)
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_policy ON %I', t);

        -- Create the isolation policy
        -- USING: Restricts which rows can be SELECTed, UPDATED, DELETED
        -- WITH CHECK: Restricts which rows can be INSERTed or UPDATED to
        EXECUTE format('
            CREATE POLICY tenant_isolation_policy ON %I
            FOR ALL
            TO trimcp_app
            USING (namespace_id = get_trimcp_namespace())
            WITH CHECK (namespace_id = get_trimcp_namespace())
        ', t);

        -- Ensure the app role has permissions
        EXECUTE format('GRANT ALL ON TABLE %I TO trimcp_app', t);
    END LOOP;
END $$;

-- 4. Special case for a2a_grants (handling target_namespace_id)
-- Grants are visible to BOTH the owner and the target
DROP POLICY IF EXISTS tenant_isolation_policy ON a2a_grants;
CREATE POLICY tenant_isolation_policy ON a2a_grants
FOR ALL
TO trimcp_app
USING (
    owner_namespace_id = get_trimcp_namespace() OR 
    target_namespace_id = get_trimcp_namespace()
)
WITH CHECK (owner_namespace_id = get_trimcp_namespace());

-- 5. Quality gate: row counts after RLS
-- FORCE ROW LEVEL SECURITY applies even to superuser. Without namespace context,
-- unscoped COUNT(*) on isolated tables returns 0 regardless of actual data — so any
-- verification must bypass RLS only for this transactional introspection block.
BEGIN;
SET LOCAL row_security = off;
DO $$
DECLARE
    t text;
    tables_to_check text[] := ARRAY[
        'memories',
        'pii_redactions',
        'memory_salience',
        'contradictions',
        'memory_embeddings',
        'kg_node_embeddings',
        'consolidation_runs',
        'event_log',
        'a2a_grants',
        'resource_quotas'
    ];
    row_count bigint;
BEGIN
    FOREACH t IN ARRAY tables_to_check
    LOOP
        EXECUTE format('SELECT count(*) FROM %I', t) INTO row_count;
        RAISE NOTICE '001_enable_rls quality gate: table % row_count=%', t, row_count;
    END LOOP;
END $$;
COMMIT;

-- 6. Ensure admin roles (like 'postgres') bypass RLS for system tasks (GC, etc.)
ALTER ROLE postgres SET row_security = off;
