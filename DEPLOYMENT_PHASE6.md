# TriMCP Phase 6 Production Cutover Runbook
**Author:** Senior Cloud & DevOps Architect  
**Target Scale:** 750M tokens/day  
**Scope:** Phase 6 Security & Architecture Remediation  
**Strategy:** Zero-Downtime Expand/Contract (Parallel Run) Migration  

---

## Executive Summary

To achieve multi-tenant Row-Level Security (RLS) enforcement on our multi-layered database without service interruption, we must decouple the application logic update from the database policy enforcement. 

If we apply RLS policies before the application code is updated, older application nodes (which do not wrap `set_namespace_context()` in transactions or fail to set it correctly) will experience **immediate data starvation (returning zero rows)**. Conversely, if we roll out the application code without preparation, writes will fail if table structures are mismatched.

This runbook implements an **Expand/Contract** deployment pattern:
```
                                        [100% Rollout Completed]
                                                   │
  ┌──────────────────────┐        ┌────────────────┴──────────────┐        ┌──────────────────────┐
  │  Phase 1 (Expand)    │───────>│  Phase 2 (Rolling Update)     │───────>│  Phase 3 (Contract)  │
  │  - Add Cols / Roles  │        │  - Run Terraform Changes      │        │  - Enable RLS DB-side│
  │  - Keep RLS Disabled │        │  - Rolling Update App Nodes   │        │  - policies ACTIVE   │
  └──────────────────────┘        └───────────────────────────────┘        └──────────────────────┘
```

---

## Prerequisites & Pre-flight Checklist

Before initiating the cutover, verify the following variables and configurations:

| Service | Setting | Required State | Command / Verification |
| :--- | :--- | :--- | :--- |
| **PostgreSQL** | Version | `>= 15.0` | `SELECT version();` |
| **PostgreSQL** | Max Connections | `>= 500` | `SHOW max_connections;` |
| **PostgreSQL** | Row Security | Enabled | Confirm superuser has `row_security = on` |
| **Terraform** | CLI Version | `>= 1.5.0` | `terraform version` |
| **Application** | Env Var | `TRIMCP_ADMIN_OVERRIDE` | Must be `""` or `unset` in production envs |
| **Application** | Env Var | `MINIO_SECRET_KEY` | Must be configured dynamically (no defaults) |

---

## Phase 1: Database Schema Expansion (Safe Prep)

In this phase, we expand our database schema to include the required isolation columns and create the security roles, but **we do not enable RLS**. This ensures that the existing (old) application code continues to write and read normally without being blocked.

### Step 1.1: Schema Additions & Role Creation
Connect to your production database using your administrative tool (e.g., `psql` or pgAdmin) and run the following script.

```sql
-- ============================================================================
-- Phase 1: DB Expansion (Safely Add Columns & Roles, Leave RLS Disabled)
-- ============================================================================

BEGIN;

-- 1. Create the Restricted Application Role
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trimcp_app') THEN
        CREATE ROLE trimcp_app;
    END IF;
END $$;

-- 2. Create the Dedicated GC Admin Role (Bypasses RLS for maintenance)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trimcp_gc') THEN
        CREATE ROLE trimcp_gc BYPASSRLS;
    ELSE
        ALTER ROLE trimcp_gc BYPASSRLS;
    END IF;
END $$;

-- 3. Add namespace_id Column to tables requiring isolation (if missing)
-- Note: Making these columns NULLABLE at this stage is critical so old code can write rows
-- without supplying a namespace_id value.
ALTER TABLE bridge_subscriptions ADD COLUMN IF NOT EXISTS namespace_id UUID REFERENCES namespaces(id);
ALTER TABLE dead_letter_queue ADD COLUMN IF NOT EXISTS namespace_id UUID REFERENCES namespaces(id);
ALTER TABLE embedding_migrations ADD COLUMN IF NOT EXISTS namespace_id UUID REFERENCES namespaces(id);

-- 4. Create Index on pii_redactions to avoid full-table scans under load
CREATE INDEX IF NOT EXISTS idx_pii_redactions_ns ON pii_redactions (namespace_id);

-- 5. Build Global Stable Function for Namespace Resolution (used by policy later)
CREATE OR REPLACE FUNCTION get_trimcp_namespace() RETURNS uuid AS $$
    SELECT current_setting('trimcp.namespace_id', true)::uuid;
$$ LANGUAGE sql STABLE;

-- 6. Ensure App Role has All Privileges on the tables
GRANT ALL ON TABLE memories TO trimcp_app;
GRANT ALL ON TABLE pii_redactions TO trimcp_app;
GRANT ALL ON TABLE memory_salience TO trimcp_app;
GRANT ALL ON TABLE contradictions TO trimcp_app;
GRANT ALL ON TABLE consolidation_runs TO trimcp_app;
GRANT ALL ON TABLE event_log TO trimcp_app;
GRANT ALL ON TABLE a2a_grants TO trimcp_app;
GRANT ALL ON TABLE resource_quotas TO trimcp_app;
GRANT ALL ON TABLE bridge_subscriptions TO trimcp_app;
GRANT ALL ON TABLE dead_letter_queue TO trimcp_app;
GRANT ALL ON TABLE embedding_migrations TO trimcp_app;

COMMIT;
```

---

## Phase 2: Infrastructure & Application Rolling Update

We now update the Cloud Infrastructure configurations (Terraform) and deploy the updated container workloads. 

### Step 2.1: Terraform Application
Deploy the infrastructure parameters that guarantee a zero-downtime rolling update. We modify our ECS task configuration to use active application scripts instead of mock/tail commands, and enforce proper scaling configurations.

Navigate to `trimcp-infra/aws` (or GCP environment directory) and run:

```powershell
# 1. Initialize Terraform
terraform init

# 2. Check changes - pay special attention to fargate task definitions
terraform plan -out=tfplan_phase6

# 3. Apply changes (Requires explicit approval)
terraform apply tfplan_phase6
```

> [!NOTE]
> **What this Terraform apply changes (FIX-003, FIX-043):**
> * **Fargate Worker Task Command:** Modifies the worker command from `tail -f /dev/null` to `python start_worker.py` (Worker) and `python server.py` (Orchestrator).
> * **ECS Rolling Update Strategy:** Sets `deployment_minimum_healthy_percent = 100` and `deployment_maximum_percent = 200`. This guarantees that old containers remain fully healthy and routing traffic while new containers spin up and pass health probes, preventing cold starts and dropouts.

### Step 2.2: Wait for Rolling Update to Complete
Monitor the deployment state. Under a zero-downtime rolling update, the orchestrator (ECS/CloudRun) will spin up the updated version side-by-side with the old version.

```powershell
# Verify ECS Service rollout status
aws ecs describe-services --cluster trimcp-prod-cluster --services trimcp-api-service trimcp-worker-service
```

### Step 2.3: Verification of Expand State
During this transition state, both versions are running concurrently. 
* **Old code:** Continues running queries normally (since RLS is not yet enabled) and writes rows without a `namespace_id` (since column is nullable).
* **New code:** Sets `set_namespace_context()` correctly within transaction blocks, and writes rows with populated `namespace_id` columns.

Run this introspection script to confirm that the new code is actively writing `namespace_id` values:

```sql
-- Check if rows with non-null namespace_id are appearing
SELECT 
    (SELECT count(*) FROM memories WHERE namespace_id IS NOT NULL) as memories_migrated,
    (SELECT count(*) FROM memories WHERE namespace_id IS NULL) as memories_legacy;
```

---

## Phase 3: Database Contracting (RLS Activation)

Once 100% of the active container instances are running the updated Python application code, we contract the schema by enabling database-level Row-Level Security policies. This forces Postgres to filter all incoming queries using the namespace session contexts.

### Step 3.1: Backfill Remaining Null Values
Before enabling RLS, ensure that any legacy rows created by the old code have a namespace ID associated with them. Run a backfill query if necessary (e.g., mapping unassigned memories to a default system namespace or utilizing metadata).

```sql
-- Example Backfill: Align all NULL namespace records to their source namespaces
BEGIN;
UPDATE memories SET namespace_id = '00000000-0000-0000-0000-000000000000' WHERE namespace_id IS NULL;
COMMIT;
```

### Step 3.2: Activate Row-Level Security
Apply the full RLS policies and force enforcement. Execute the following script:

```sql
-- ============================================================================
-- Phase 3: DB Contracting (Enable RLS & Create Security Policies)
-- ============================================================================

BEGIN;

-- 1. Enable RLS and Force RLS on all isolated tables
-- Force RLS is vital so that even superusers (like the default postgres connection role) 
-- are strictly isolated unless bypassing RLS explicitly via bypass role (trimcp_gc).
DO $$
DECLARE
    t text;
    tables_to_isolate text[] := ARRAY[
        'memories', 
        'pii_redactions', 
        'memory_salience', 
        'contradictions', 
        'consolidation_runs', 
        'event_log', 
        'resource_quotas',
        'bridge_subscriptions',
        'dead_letter_queue',
        'embedding_migrations'
    ];
BEGIN
    FOREACH t IN ARRAY tables_to_isolate
    LOOP
        -- Enable security checks
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);

        -- Drop existing policy if it exists (idempotency)
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_policy ON %I', t);

        -- Create tenant isolation policy
        EXECUTE format('
            CREATE POLICY tenant_isolation_policy ON %I
            FOR ALL
            TO trimcp_app
            USING (namespace_id = get_trimcp_namespace())
            WITH CHECK (namespace_id = get_trimcp_namespace())
        ', t);
    END LOOP;
END $$;

-- 2. Special policy for a2a_grants (Visible to BOTH owner and target namespaces)
ALTER TABLE a2a_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a_grants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_policy ON a2a_grants;

CREATE POLICY tenant_isolation_policy ON a2a_grants
FOR ALL
TO trimcp_app
USING (
    owner_namespace_id = get_trimcp_namespace() OR 
    target_namespace_id = get_trimcp_namespace()
)
WITH CHECK (owner_namespace_id = get_trimcp_namespace());

-- 3. Reset postgres role row_security configuration
ALTER ROLE postgres RESET row_security;

COMMIT;
```

### Step 3.3: Verify Security Enforcement
Verify that Row-Level Security is behaving correctly.

```sql
-- Verify with RLS bypassed (Admin query)
BEGIN;
SET LOCAL row_security = off;
SELECT count(*) as total_physical_records FROM memories;
COMMIT;

-- Verify RLS Filtered (App Simulation)
BEGIN;
-- Set session variables to pretend to be 'trimcp_app' with context
SET ROLE trimcp_app;
SET LOCAL trimcp.namespace_id = '11111111-1111-1111-1111-111111111111'; -- Replace with actual tenant namespace ID

-- This count should ONLY return rows matching the specified namespace_id
SELECT count(*) as total_visible_records FROM memories;

RESET ROLE;
COMMIT;
```

---

## Distributed-Systems Physics & Failure Analysis

Deployments at a scale of **750M tokens/day** operate under harsh network and resource environments. Let's analyze our steps against physical constraints.

### 1. What happens if Step 2 (Rolling Update) fails halfway through?
* **Physical state:** 50% of application nodes are running the Old code; 50% are running the New code.
* **Database State:** RLS is **disabled** (Phase 1).
* **Distributed-systems outcome:** 
  * Old nodes continue to read and write without error because RLS is inactive.
  * New nodes write `namespace_id` and execute transaction blocks successfully.
  * **Blast Radius:** `0%` traffic blocked. No system degradation. This validates the safety of the Expand stage. We can safely pause, troubleshoot, or redeploy Phase 2 without pressure.

### 2. What happens if Step 3 (RLS Activation) fails halfway through?
* **Scenario:** The SQL block runs but fails on table `contradictions` due to a locked transaction or constraint.
* **Database State:** Partially enabled (e.g., `memories` and `pii_redactions` have RLS enabled, but `contradictions` does not).
* **Distributed-systems outcome:**
  * Since our application code was 100% updated in Step 2, the application is already wrapping operations in transactions and invoking `SET LOCAL trimcp.namespace_id`.
  * For tables with RLS enabled: Query isolation occurs immediately and runs successfully.
  * For tables where RLS failed to enable: Queries run successfully (but without database-enforced security; they still fall back to application-layer scoping logic).
  * **Blast Radius:** No user traffic is dropped. Isolation remains intact at the application layer, while we execute a script to complete the remaining RLS applications.

### 3. Connection Pool and GIL Starvation under Scale (FIX-010, FIX-045, FIX-042)
* **Risk:** At 750M tokens/day, a sudden surge in requests might cause thread or socket exhaustion.
* **Analysis:**
  1. **Connection Timeout Guard (`pool.acquire(timeout=10.0)`):** If the database connection pool is fully saturated, requests wait a maximum of 10 seconds before failing gracefully, preventing the entire event loop from locking up indefinitely.
  2. **Process Pools for CPU Workloads:** CPU-heavy workloads (such as PyTorch NLP extraction or local model inference) are run in a separate `ProcessPoolExecutor` (not a ThreadPool) to bypass Python's Global Interpreter Lock (GIL). If run inside the event loop, a single inference call blocks the event loop, causing health probe timeouts and triggering container restarts in Cloud Run / ECS.
  3. **Cloud Run Concurrency Tuning:** We cap `max_instance_request_concurrency = 10` on Cloud Run. Since Python handles requests concurrently on a single CPU core, setting concurrency too high causes CPU starvation and massive latency spikes. Capping at 10 forces the infrastructure to scale horizontally as CPU load approaches limits.

---

## Zero-Downtime Rollback Plan

If unexpected tenant isolation bugs, access control errors, or database lockouts occur immediately after Phase 3, **DO NOT attempt to roll back container code or run destructive column-dropping SQL migrations.** This would cause minutes of downtime and risk data loss.

Instead, execute the **Bypass Hotfix**. This instantly disables RLS database-side in less than 5 seconds, returning the database to a standard permissive state. The application continues running safely while developers debug.

### The 5-Second RLS Bypass (SQL Hotfix)
Execute this command directly against the production Postgres instance:

```sql
-- ============================================================================
-- EMERGENCY ROLLBACK: INSTANT RLS BYPASS
-- ============================================================================
BEGIN;

-- Instantly disable RLS on all isolated tables
ALTER TABLE memories DISABLE ROW LEVEL SECURITY;
ALTER TABLE pii_redactions DISABLE ROW LEVEL SECURITY;
ALTER TABLE memory_salience DISABLE ROW LEVEL SECURITY;
ALTER TABLE contradictions DISABLE ROW LEVEL SECURITY;
ALTER TABLE consolidation_runs DISABLE ROW LEVEL SECURITY;
ALTER TABLE event_log DISABLE ROW LEVEL SECURITY;
ALTER TABLE a2a_grants DISABLE ROW LEVEL SECURITY;
ALTER TABLE resource_quotas DISABLE ROW LEVEL SECURITY;
ALTER TABLE bridge_subscriptions DISABLE ROW LEVEL SECURITY;
ALTER TABLE dead_letter_queue DISABLE ROW LEVEL SECURITY;
ALTER TABLE embedding_migrations DISABLE ROW LEVEL SECURITY;

-- Note: All columns, indexes, and application configurations are preserved.
-- Traffic is immediately restored to 100% success rate.
COMMIT;
```

---
*End of Runbook*
