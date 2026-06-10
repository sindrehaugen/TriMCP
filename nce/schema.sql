-- ============================================================================
-- TriMCP — PostgreSQL Schema
-- Loaded by nce.orchestrator.TriStackEngine._init_pg_schema on connect().
--
-- All statements are idempotent (IF NOT EXISTS). Safe to run on every startup.
-- Hardening applied: pgcrypto, HNSW cosine indexes, TIMESTAMPTZ, CHECK on
-- confidence, compound index for recall, updated_at on upserted KG tables,
-- CHAR(24) mongo_ref_id (MongoDB ObjectId hex length), NOT NULL where Saga
-- semantics forbid orphans.
-- ============================================================================

-- --- Extensions ---
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- --- Application roles (required before any RLS policy references nce_app) ---
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        CREATE ROLE nce_app WITH LOGIN PASSWORD 'nce_app_secret';
    ELSE
        ALTER ROLE nce_app WITH LOGIN PASSWORD 'nce_app_secret';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_gc') THEN
        CREATE ROLE nce_gc BYPASSRLS NOLOGIN;
    ELSE
        ALTER ROLE nce_gc BYPASSRLS NOLOGIN;
    END IF;
END $$;

-- --- Phase 0.1: Namespaces ---
CREATE TABLE IF NOT EXISTS namespaces (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug       TEXT UNIQUE NOT NULL,
    parent_id  UUID REFERENCES namespaces(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata   JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_namespaces_parent_id ON namespaces(parent_id);
CREATE INDEX IF NOT EXISTS idx_namespaces_created_at ON namespaces(created_at DESC);

-- --- Phase 0.2: Cryptographic Signing Keys ---
CREATE TABLE IF NOT EXISTS signing_keys (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id        TEXT UNIQUE NOT NULL,
    encrypted_key BYTEA NOT NULL,
    status        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at    TIMESTAMPTZ
);

-- --- Unified Memories Table (Phase 0.1) ---
-- Replaces memory_metadata and code_metadata. Partitioned by RANGE(created_at).
CREATE TABLE IF NOT EXISTS memories (
    id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
    namespace_id        UUID        REFERENCES namespaces(id),
    agent_id            TEXT        NOT NULL DEFAULT 'default',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    memory_type         TEXT        NOT NULL DEFAULT 'episodic',
    assertion_type      TEXT        NOT NULL DEFAULT 'fact',
    payload_ref         TEXT        NOT NULL,
    embedding           vector(768),
    embedding_model_id  UUID,
    derived_from        JSONB,
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to            TIMESTAMPTZ,
    signature           BYTEA,
    signature_key_id    TEXT,
    pii_redacted        BOOLEAN     NOT NULL DEFAULT false,
    
    -- Legacy compatibility fields (from memory_metadata and code_metadata)
    user_id             VARCHAR(128),
    session_id          VARCHAR(128),
    content_fts         TSVECTOR,
    filepath            TEXT,
    language            VARCHAR(64),
    node_type           VARCHAR(64),
    name                VARCHAR(255),
    start_line          INT,
    end_line            INT,
    file_hash           VARCHAR(64),
    
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE IF NOT EXISTS memories_default PARTITION OF memories DEFAULT;

ALTER TABLE memories ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Migration 018 (Part II.4 Provable Forgetting): envelope-encryption DEK columns.
-- wrapped_dek holds the AES-256-GCM-wrapped Data Encryption Key (envelope-encrypted
-- under NCE_MASTER_KEY via nce.envelope.wrap_dek); dek_key_id is an opaque, key-free
-- identifier used in deletion receipts/audit events.  Zeroing wrapped_dek crypto-shreds
-- the corresponding episodes.raw_data ciphertext.  Read-path wiring lands in Batch 46.
ALTER TABLE memories ADD COLUMN IF NOT EXISTS wrapped_dek BYTEA;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS dek_key_id TEXT;

-- Data Migration from legacy tables
DO $$
DECLARE
    global_ns_id UUID;
BEGIN
    -- Ensure fallback namespace exists
    INSERT INTO namespaces (slug, metadata)
    VALUES ('_global_legacy', '{"description":"Fallback namespace for pre-RLS data"}'::jsonb)
    ON CONFLICT (slug) DO NOTHING;
    
    SELECT id INTO global_ns_id FROM namespaces WHERE slug = '_global_legacy';

    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'memory_metadata') THEN
        INSERT INTO memories (
            id, user_id, session_id, embedding, payload_ref, created_at, content_fts, 
            namespace_id, agent_id, signature, signature_key_id, memory_type
        )
        SELECT 
            id, user_id, session_id, embedding, mongo_ref_id, created_at, content_fts,
            global_ns_id, 'default', NULL, NULL, 'episodic'
        FROM memory_metadata
        ON CONFLICT DO NOTHING;
        
        DROP TABLE memory_metadata CASCADE;
    END IF;

    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'code_metadata') THEN
        INSERT INTO memories (
            id, filepath, language, node_type, name, start_line, end_line, file_hash, 
            embedding, payload_ref, created_at, user_id, content_fts, namespace_id, memory_type
        )
        SELECT 
            id, filepath, language, node_type, name, start_line, end_line, file_hash, 
            embedding, mongo_ref_id, created_at, NULL, content_fts, global_ns_id, 'code_chunk'
        FROM code_metadata
        ON CONFLICT DO NOTHING;
        
        DROP TABLE code_metadata CASCADE;
    END IF;
END $$;

-- memory_type / assertion_type — align with nce.models MemoryType / AssertionType
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'ck_memories_memory_type'
    ) THEN
        ALTER TABLE memories ADD CONSTRAINT ck_memories_memory_type
            CHECK (memory_type IN ('episodic', 'consolidated', 'decision', 'code_chunk'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'ck_memories_assertion_type'
    ) THEN
        ALTER TABLE memories ADD CONSTRAINT ck_memories_assertion_type
            CHECK (assertion_type IN ('fact', 'opinion', 'preference', 'observation'));
    END IF;
END $$;

-- Indexes for memories
CREATE INDEX IF NOT EXISTS idx_memories_fts ON memories USING GIN (content_fts);
CREATE INDEX IF NOT EXISTS idx_memories_payload_ref ON memories (payload_ref);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories (user_id);
CREATE INDEX IF NOT EXISTS idx_memories_user_session ON memories (user_id, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_filepath ON memories (filepath);
CREATE INDEX IF NOT EXISTS idx_memories_user_path ON memories (user_id, filepath);
CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw ON memories USING hnsw (embedding vector_cosine_ops);
-- Fleet admin: COUNT(*) / lookups by tenant without scanning all time partitions
CREATE INDEX IF NOT EXISTS idx_memories_namespace_id ON memories (namespace_id);

-- payload_ref CHECK constraint — enforce MongoDB ObjectId hex format (24 hex chars)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'ck_payload_ref_objectid_format'
    ) THEN
        ALTER TABLE memories ADD CONSTRAINT ck_payload_ref_objectid_format
            CHECK (payload_ref ~ '^[a-f0-9]{24}$');
    END IF;
END $$;

-- --- Knowledge-graph nodes (partitioned by HASH) ---
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = 'kg_nodes' AND c.relkind = 'r' AND c.relispartition = false AND NOT EXISTS (SELECT 1 FROM pg_partitioned_table WHERE partrelid = c.oid)) THEN
        ALTER TABLE kg_nodes RENAME TO kg_nodes_old;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS kg_nodes (
    id            UUID DEFAULT gen_random_uuid(),
    label         TEXT NOT NULL,
    entity_type   VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN',
    embedding     VECTOR(768),
    embedding_model_id UUID,
    namespace_id  UUID NOT NULL,
    payload_ref   CHAR(24),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (label, namespace_id)
) PARTITION BY HASH (label);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='kg_nodes' AND column_name='embedding_model_id') THEN
        ALTER TABLE kg_nodes ADD COLUMN embedding_model_id UUID;
    END IF;
END $$;

-- Phase 1 hardening: namespace_id + RLS for kg_nodes
DO $$
DECLARE
    global_ns_id UUID;
BEGIN
    -- Ensure a fallback global namespace exists for legacy data
    INSERT INTO namespaces (slug, metadata)
    VALUES ('_global_legacy', '{"description":"Fallback namespace for pre-RLS KG data"}'::jsonb)
    ON CONFLICT (slug) DO NOTHING;
    SELECT id INTO global_ns_id FROM namespaces WHERE slug = '_global_legacy';

    -- Add namespace_id column if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='kg_nodes' AND column_name='namespace_id') THEN
        ALTER TABLE kg_nodes ADD COLUMN namespace_id UUID;
    END IF;

    -- Backfill existing NULL rows
    UPDATE kg_nodes SET namespace_id = global_ns_id WHERE namespace_id IS NULL;

    -- Make NOT NULL now that all rows have a value
    ALTER TABLE kg_nodes ALTER COLUMN namespace_id SET NOT NULL;

    -- Add FK to namespaces
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'kg_nodes_namespace_id_fkey'
    ) THEN
        ALTER TABLE kg_nodes ADD CONSTRAINT kg_nodes_namespace_id_fkey
            FOREIGN KEY (namespace_id) REFERENCES namespaces(id);
    END IF;

    -- Migrate UNIQUE constraint: (label) → (label, namespace_id)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'kg_nodes' AND constraint_name = 'kg_nodes_label_key'
    ) THEN
        ALTER TABLE kg_nodes DROP CONSTRAINT kg_nodes_label_key;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'kg_nodes' AND constraint_name = 'kg_nodes_label_namespace_id_key'
    ) THEN
        ALTER TABLE kg_nodes ADD CONSTRAINT kg_nodes_label_namespace_id_key
            UNIQUE (label, namespace_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS kg_nodes_0 PARTITION OF kg_nodes FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE IF NOT EXISTS kg_nodes_1 PARTITION OF kg_nodes FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE IF NOT EXISTS kg_nodes_2 PARTITION OF kg_nodes FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE IF NOT EXISTS kg_nodes_3 PARTITION OF kg_nodes FOR VALUES WITH (MODULUS 4, REMAINDER 3);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'kg_nodes_old') THEN
        INSERT INTO kg_nodes (id, label, entity_type, embedding, payload_ref, created_at, updated_at, namespace_id)
        SELECT id, label, entity_type, embedding, mongo_ref_id, created_at, updated_at, (SELECT id FROM namespaces WHERE slug = '_global_legacy' LIMIT 1)
        FROM kg_nodes_old
        ON CONFLICT (label, namespace_id) DO NOTHING;
        DROP TABLE kg_nodes_old CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_kg_nodes_embedding_hnsw ON kg_nodes USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_updated ON kg_nodes (updated_at);

-- --- Knowledge-graph edges (partitioned by HASH) ---
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = 'kg_edges' AND c.relkind = 'r' AND c.relispartition = false AND NOT EXISTS (SELECT 1 FROM pg_partitioned_table WHERE partrelid = c.oid)) THEN
        ALTER TABLE kg_edges RENAME TO kg_edges_old;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS kg_edges (
    id            UUID DEFAULT gen_random_uuid(),
    subject_label TEXT NOT NULL,
    predicate     TEXT NOT NULL,
    object_label  TEXT NOT NULL,
    confidence    FLOAT NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    namespace_id  UUID NOT NULL,
    payload_ref   CHAR(24),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (subject_label, predicate, object_label, namespace_id)
) PARTITION BY HASH (subject_label, predicate, object_label);

CREATE TABLE IF NOT EXISTS kg_edges_0 PARTITION OF kg_edges FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE IF NOT EXISTS kg_edges_1 PARTITION OF kg_edges FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE IF NOT EXISTS kg_edges_2 PARTITION OF kg_edges FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE IF NOT EXISTS kg_edges_3 PARTITION OF kg_edges FOR VALUES WITH (MODULUS 4, REMAINDER 3);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'kg_edges_old') THEN
        INSERT INTO kg_edges (id, subject_label, predicate, object_label, confidence, payload_ref, created_at, updated_at, namespace_id)
        SELECT id, subject_label, predicate, object_label, confidence, mongo_ref_id, created_at, updated_at, (SELECT id FROM namespaces WHERE slug = '_global_legacy' LIMIT 1)
        FROM kg_edges_old
        -- FIX-038: 4-column conflict target matches the unique constraint on kg_edges.
        -- Do not revert to 3-column; namespace_id is required for multi-tenant isolation.
        ON CONFLICT (subject_label, predicate, object_label, namespace_id) DO NOTHING;
        DROP TABLE kg_edges_old CASCADE;
    END IF;
END $$;

-- Phase 1 hardening: namespace_id + RLS for kg_edges
DO $$
DECLARE
    global_ns_id UUID;
BEGIN
    SELECT id INTO global_ns_id FROM namespaces WHERE slug = '_global_legacy';

    -- Add namespace_id column if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='kg_edges' AND column_name='namespace_id') THEN
        ALTER TABLE kg_edges ADD COLUMN namespace_id UUID;
    END IF;

    -- Backfill existing NULL rows
    UPDATE kg_edges SET namespace_id = global_ns_id WHERE namespace_id IS NULL;

    -- Make NOT NULL
    ALTER TABLE kg_edges ALTER COLUMN namespace_id SET NOT NULL;

    -- Add FK
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'kg_edges_namespace_id_fkey'
    ) THEN
        ALTER TABLE kg_edges ADD CONSTRAINT kg_edges_namespace_id_fkey
            FOREIGN KEY (namespace_id) REFERENCES namespaces(id);
    END IF;

    -- Migrate UNIQUE: (s,p,o) → (s,p,o,namespace_id)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'kg_edges' AND constraint_name = 'kg_edges_subject_label_predicate_objec_key'
    ) THEN
        ALTER TABLE kg_edges DROP CONSTRAINT kg_edges_subject_label_predicate_objec_key;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'kg_edges' AND constraint_name = 'kg_edges_subject_label_predicate_object_label_namespace_id_key'
    ) THEN
        ALTER TABLE kg_edges ADD CONSTRAINT kg_edges_subject_label_predicate_object_label_namespace_id_key
            UNIQUE (subject_label, predicate, object_label, namespace_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_kg_edges_subject ON kg_edges (subject_label);
CREATE INDEX IF NOT EXISTS idx_kg_edges_object  ON kg_edges (object_label);
CREATE INDEX IF NOT EXISTS idx_kg_edges_updated ON kg_edges (updated_at);

-- --- Phase 0.3: PII Redactions Vault ---
CREATE TABLE IF NOT EXISTS pii_redactions (
    id              UUID DEFAULT gen_random_uuid(),
    namespace_id    UUID NOT NULL REFERENCES namespaces(id),
    memory_id       UUID NOT NULL,
    token           TEXT NOT NULL,
    encrypted_value BYTEA NOT NULL,
    entity_type     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE IF NOT EXISTS pii_redactions_default PARTITION OF pii_redactions DEFAULT;

CREATE INDEX IF NOT EXISTS idx_pii_redactions_memory ON pii_redactions (memory_id);
CREATE INDEX IF NOT EXISTS idx_pii_redactions_token ON pii_redactions (token);

-- FIX-054: namespace-scoped PII queries require this index to avoid full partition scans.
CREATE INDEX IF NOT EXISTS idx_pii_redactions_namespace_id
    ON pii_redactions (namespace_id);

-- --- Phase 1.1: Memory Salience ---
CREATE TABLE IF NOT EXISTS memory_salience (
    memory_id       UUID        NOT NULL,
    agent_id        TEXT        NOT NULL,
    namespace_id    UUID        NOT NULL REFERENCES namespaces(id),
    salience_score  REAL        NOT NULL DEFAULT 1.0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    access_count    INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (memory_id, agent_id)
) PARTITION BY HASH (memory_id, agent_id);

CREATE TABLE IF NOT EXISTS memory_salience_0 PARTITION OF memory_salience FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE IF NOT EXISTS memory_salience_1 PARTITION OF memory_salience FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE IF NOT EXISTS memory_salience_2 PARTITION OF memory_salience FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE IF NOT EXISTS memory_salience_3 PARTITION OF memory_salience FOR VALUES WITH (MODULUS 4, REMAINDER 3);

-- Fleet admin: salience-map + fleet rollup subqueries scoped by namespace_id
CREATE INDEX IF NOT EXISTS idx_memory_salience_namespace_id ON memory_salience (namespace_id);

-- --- Phase 1.3: Contradictions ---
CREATE TABLE IF NOT EXISTS contradictions (
    id             UUID        NOT NULL DEFAULT gen_random_uuid(),
    namespace_id   UUID        NOT NULL REFERENCES namespaces(id),
    memory_a_id    UUID        NOT NULL,
    memory_b_id    UUID        NOT NULL,
    agent_id       TEXT        NOT NULL DEFAULT 'system',
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    detection_path TEXT        NOT NULL,
    signals        JSONB       NOT NULL,
    confidence     REAL        NOT NULL,
    resolution     TEXT,
    resolved_at    TIMESTAMPTZ,
    resolved_by    TEXT,
    note           TEXT,
    PRIMARY KEY (id, detected_at)
) PARTITION BY RANGE (detected_at);

CREATE TABLE IF NOT EXISTS contradictions_default PARTITION OF contradictions DEFAULT;

-- Fleet admin: open contradiction counts per namespace
CREATE INDEX IF NOT EXISTS idx_contradictions_namespace_id ON contradictions (namespace_id);

-- --- Phase 2.1: Embedding Models & Migrations ---
CREATE TABLE IF NOT EXISTS embedding_models (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT UNIQUE NOT NULL,
    dimension  INTEGER NOT NULL,
    status     TEXT NOT NULL,   -- active | migrating | retired
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    memory_id    UUID NOT NULL,
    model_id     UUID NOT NULL REFERENCES embedding_models(id),
    embedding    vector, -- Unconstrained dimension to support any model
    namespace_id UUID REFERENCES namespaces(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (memory_id, model_id)
) PARTITION BY HASH (memory_id);

CREATE TABLE IF NOT EXISTS memory_embeddings_0 PARTITION OF memory_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE IF NOT EXISTS memory_embeddings_1 PARTITION OF memory_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE IF NOT EXISTS memory_embeddings_2 PARTITION OF memory_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE IF NOT EXISTS memory_embeddings_3 PARTITION OF memory_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 3);

-- Index for validate_migration emb_count query and model-scoped lookups
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_model_id ON memory_embeddings(model_id);

CREATE TABLE IF NOT EXISTS kg_node_embeddings (
    node_id    UUID NOT NULL,
    model_id   UUID NOT NULL REFERENCES embedding_models(id),
    embedding  vector,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (node_id, model_id)
) PARTITION BY HASH (node_id);

CREATE TABLE IF NOT EXISTS kg_node_embeddings_0 PARTITION OF kg_node_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE IF NOT EXISTS kg_node_embeddings_1 PARTITION OF kg_node_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE IF NOT EXISTS kg_node_embeddings_2 PARTITION OF kg_node_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE IF NOT EXISTS kg_node_embeddings_3 PARTITION OF kg_node_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 3);

CREATE TABLE IF NOT EXISTS embedding_migrations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id     UUID REFERENCES namespaces(id),
    target_model_id  UUID NOT NULL REFERENCES embedding_models(id),
    status           TEXT NOT NULL DEFAULT 'running', -- running | validating | committed | aborted
    last_memory_id   UUID,
    last_node_id     UUID,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ
);

-- --- Document bridge subscriptions ---
CREATE TABLE IF NOT EXISTS bridge_subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id    UUID REFERENCES namespaces(id),
    user_id         TEXT NOT NULL,
    provider        TEXT NOT NULL CHECK (provider IN ('sharepoint', 'gdrive', 'dropbox')),
    resource_id     TEXT NOT NULL,
    subscription_id TEXT,
    cursor          TEXT,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('REQUESTED','VALIDATING','ACTIVE','DEGRADED','EXPIRED','DISCONNECTED')),
    expires_at      TIMESTAMPTZ,
    client_state    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bridge_subs_user_provider ON bridge_subscriptions (user_id, provider);
CREATE INDEX IF NOT EXISTS idx_bridge_subs_expires_active ON bridge_subscriptions (expires_at) WHERE status = 'ACTIVE';
-- Fleet admin: per-namespace ACTIVE counts / next expiry resolution
CREATE INDEX IF NOT EXISTS idx_bridge_subscriptions_namespace_id ON bridge_subscriptions (namespace_id);

ALTER TABLE bridge_subscriptions ADD COLUMN IF NOT EXISTS oauth_access_token_enc BYTEA;
ALTER TABLE bridge_subscriptions ADD COLUMN IF NOT EXISTS namespace_id UUID REFERENCES namespaces(id);

-- --- Phase 2.2: Time Travel Snapshots ---
CREATE TABLE IF NOT EXISTS snapshots (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    agent_id     TEXT NOT NULL,
    name         TEXT NOT NULL,
    snapshot_at  TIMESTAMPTZ NOT NULL,    -- The point in time being snapshotted
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (namespace_id, name)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_ns ON snapshots (namespace_id);

DO $$
BEGIN
    REVOKE ALL ON snapshots FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON snapshots TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — snapshot GRANTs skipped (create role or run migrations)';
    END IF;
END $$;

-- --- Phase 2.3: Event Log (WORM) ---
CREATE TABLE IF NOT EXISTS consolidation_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id      UUID NOT NULL REFERENCES namespaces(id),
    agent_id          TEXT NOT NULL DEFAULT 'system',
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'running',
    clusters_found    INTEGER DEFAULT 0,
    clusters_accepted INTEGER DEFAULT 0,
    clusters_rejected INTEGER DEFAULT 0,
    memories_synth    INTEGER DEFAULT 0,
    llm_provider      TEXT,
    llm_model         TEXT,
    llm_tokens_used   INTEGER DEFAULT 0,
    error             TEXT
);

-- Columns used by nce.consolidation (idempotent add for older DBs)
ALTER TABLE consolidation_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE consolidation_runs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE consolidation_runs ADD COLUMN IF NOT EXISTS events_processed INTEGER;
ALTER TABLE consolidation_runs ADD COLUMN IF NOT EXISTS clusters_formed INTEGER;
ALTER TABLE consolidation_runs ADD COLUMN IF NOT EXISTS abstractions_created INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'ck_consolidation_runs_status'
    ) THEN
        ALTER TABLE consolidation_runs ADD CONSTRAINT ck_consolidation_runs_status
            CHECK (status IN ('running', 'completed', 'failed'));
    END IF;
END $$;

-- Fleet admin: latest consolidation_run per namespace
CREATE INDEX IF NOT EXISTS idx_consolidation_runs_namespace_id ON consolidation_runs (namespace_id);

CREATE TABLE IF NOT EXISTS event_log (
    id               UUID DEFAULT gen_random_uuid(),
    namespace_id     UUID NOT NULL REFERENCES namespaces(id),
    agent_id         TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    event_seq        BIGINT NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    params           JSONB NOT NULL,
    result_summary   JSONB,
    parent_event_id  UUID,
    llm_payload_uri  TEXT,
    llm_payload_hash BYTEA,
    signature        BYTEA NOT NULL,
    signature_key_id TEXT NOT NULL,
    signature_version SMALLINT NOT NULL DEFAULT 1,
    chain_hash       BYTEA,
    PRIMARY KEY (id, occurred_at),
    UNIQUE (namespace_id, event_seq, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE IF NOT EXISTS event_log_default PARTITION OF event_log DEFAULT;

-- Per-namespace monotonic event_seq counter (single-row UPSERT avoids MAX(event_seq)
-- merge-append scans across event_log partitions on every append).
CREATE TABLE IF NOT EXISTS event_sequences (
    namespace_id UUID PRIMARY KEY REFERENCES namespaces(id),
    seq          BIGINT NOT NULL DEFAULT 0
);

-- --- Phase 2.3: Memory Replay Engine Sessions ---
CREATE TABLE IF NOT EXISTS replay_runs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_namespace_id  UUID NOT NULL REFERENCES namespaces(id),
    target_namespace_id  UUID REFERENCES namespaces(id),
    mode                 TEXT NOT NULL,          -- observational | reconstructive | forked
    replay_mode          TEXT NOT NULL DEFAULT 'deterministic',  -- deterministic | re-execute
    start_seq            BIGINT NOT NULL,
    end_seq              BIGINT,
    divergence_seq       BIGINT,
    config_overrides     JSONB,
    status               TEXT NOT NULL,          -- running | success | failed | aborted
    events_applied       BIGINT NOT NULL DEFAULT 0,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at          TIMESTAMPTZ,
    error                TEXT,
    source_state_digest  TEXT,
    target_state_digest  TEXT,
    digest_match         BOOLEAN
);

DO $$
BEGIN
    REVOKE ALL ON replay_runs FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON replay_runs TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — replay_runs GRANTs skipped';
    END IF;
END $$;

-- Fail-fast session namespace for RLS policies (see nce/auth.set_namespace_context).
CREATE OR REPLACE FUNCTION get_nce_namespace() RETURNS uuid AS $$
DECLARE
    val text;
BEGIN
    val := nullif(trim(current_setting('nce.namespace_id', true)), '');
    IF val IS NULL THEN
        RAISE EXCEPTION 'nce.namespace_id is not set for this transaction';
    END IF;
    BEGIN
        RETURN val::uuid;
    EXCEPTION
        WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'nce.namespace_id is not a valid UUID: %', val;
    END;
END;
$$ LANGUAGE plpgsql STABLE;

ALTER TABLE replay_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE replay_runs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS namespace_isolation_policy ON replay_runs;
DROP POLICY IF EXISTS tenant_isolation_policy ON replay_runs;
CREATE POLICY tenant_isolation_policy ON replay_runs
    FOR ALL TO nce_app
    USING (
        source_namespace_id IS NOT NULL
        AND source_namespace_id = get_nce_namespace()
    )
    WITH CHECK (
        source_namespace_id IS NOT NULL
        AND source_namespace_id = get_nce_namespace()
    );


CREATE INDEX IF NOT EXISTS idx_event_log_ns_time ON event_log (namespace_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_event_log_ns_seq  ON event_log (namespace_id, event_seq);
CREATE INDEX IF NOT EXISTS idx_event_log_parent  ON event_log (parent_event_id) WHERE parent_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_event_log_memory_id ON event_log (((params->>'memory_id')::uuid));
CREATE INDEX IF NOT EXISTS idx_event_log_event_type ON event_log (event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_time_travel ON event_log (namespace_id, occurred_at)
    WHERE event_type IN ('store_memory', 'forget_memory');
CREATE INDEX IF NOT EXISTS idx_event_log_params_gin ON event_log USING GIN (params);

-- Monthly partition windows (UTC); keeps hot data off the DEFAULT catch-all partition
CREATE OR REPLACE FUNCTION nce_ensure_event_log_monthly_partitions(p_months_ahead int DEFAULT 3)
RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    m int;
    p_start timestamptz;
    p_end timestamptz;
    p_name text;
    violating_count int;
BEGIN
    IF p_months_ahead < 0 THEN
        RAISE EXCEPTION 'p_months_ahead must be >= 0';
    END IF;
    FOR m IN 0..p_months_ahead LOOP
        p_start := date_trunc('month', now() + make_interval(months => m));
        p_end := p_start + interval '1 month';
        p_name := 'event_log_' || to_char(p_start, 'YYYY_MM');
        IF to_regclass(format('public.%I', p_name)) IS NULL THEN
            -- Check if there are violating rows in event_log_default
            EXECUTE format(
                'SELECT count(*)::int FROM event_log_default WHERE occurred_at >= %L AND occurred_at < %L',
                p_start,
                p_end
            ) INTO violating_count;
            
            IF violating_count > 0 THEN
                -- Move violating rows from event_log_default to a temp table
                CREATE TEMP TABLE temp_event_log_migrate ON COMMIT DROP AS 
                    SELECT * FROM event_log_default 
                    WHERE occurred_at >= p_start AND occurred_at < p_end;
                    
                DELETE FROM event_log_default 
                WHERE occurred_at >= p_start AND occurred_at < p_end;
                
                -- Create partition
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF event_log FOR VALUES FROM (%L) TO (%L)',
                    p_name,
                    p_start,
                    p_end
                );
                
                -- Insert them back into event_log so they route to the new partition
                INSERT INTO event_log SELECT * FROM temp_event_log_migrate;
                
                -- Drop the temp table
                DROP TABLE temp_event_log_migrate;
            ELSE
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF event_log FOR VALUES FROM (%L) TO (%L)',
                    p_name,
                    p_start,
                    p_end
                );
            END IF;
        END IF;
    END LOOP;
END;
$fn$;

SELECT nce_ensure_event_log_monthly_partitions(3);

DO $$
BEGIN
    REVOKE ALL ON event_log FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT INSERT, SELECT ON event_log TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — event_log GRANTs skipped (create role or run migrations)';
    END IF;
END $$;

DO $$
BEGIN
    REVOKE ALL ON event_sequences FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT INSERT, SELECT, UPDATE ON event_sequences TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — event_sequences GRANTs skipped (create role or run migrations)';
    END IF;
END $$;

-- FIX-064 / FIX-065: parent_event_id triggers validate or UPDATE without a partition key,
-- causing partition merge-appends; SET NULL path is also incompatible with WORM.
-- Partition-safe policy is deferred (FIX-067); Merkle chain provides integrity.
DROP TRIGGER IF EXISTS trg_event_log_parent_fk ON event_log;
DROP TRIGGER IF EXISTS trg_event_log_parent_fk_insupd ON event_log;
DROP TRIGGER IF EXISTS trg_event_log_parent_fk_del ON event_log;
DROP TRIGGER IF EXISTS trg_event_log_parent_set_null ON event_log;
DROP FUNCTION IF EXISTS trg_event_log_parent_fk();
DROP FUNCTION IF EXISTS trg_event_log_parent_set_null();

-- WORM immutability: reject any UPDATE or DELETE on event_log.
CREATE OR REPLACE FUNCTION prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'event_log is immutable (WORM). % operation is forbidden.', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Salience decay UDF (Item B): pushes Ebbinghaus decay into PostgreSQL
CREATE OR REPLACE FUNCTION nce_decayed_score(
    s_last FLOAT,
    updated_at TIMESTAMPTZ,
    half_life_days FLOAT
) RETURNS FLOAT AS $$
DECLARE
    delta_t FLOAT;
    decay_constant FLOAT;
    exponent FLOAT;
    MAX_EXP CONSTANT FLOAT := 20.0;
BEGIN
    IF half_life_days <= 0 THEN
        RETURN s_last;
    END IF;
    delta_t := GREATEST(0.0, EXTRACT(EPOCH FROM (NOW() - updated_at)) / 86400.0);
    decay_constant := LN(2) / half_life_days;
    exponent := LEAST(decay_constant * delta_t, MAX_EXP);
    RETURN s_last * EXP(-exponent);
END;
$$ LANGUAGE plpgsql STABLE;

DO $$
BEGIN
    -- Install WORM immutability trigger (legacy parent-FK triggers dropped above).
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_event_log_worm') THEN
        CREATE TRIGGER trg_event_log_worm
            BEFORE UPDATE OR DELETE ON event_log
            FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
    END IF;
END $$;

-- --- Phase 3.1: A2A (Agent-to-Agent) Sharing Grants ---
CREATE TABLE IF NOT EXISTS a2a_grants (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_namespace_id   UUID        NOT NULL REFERENCES namespaces(id),
    owner_agent_id       TEXT        NOT NULL,
    target_namespace_id  UUID,                       -- NULL = any bearer is valid
    target_agent_id      TEXT,                       -- NULL = any agent
    scopes               JSONB       NOT NULL,
    token_hash           BYTEA       NOT NULL UNIQUE, -- SHA-256 of sharing token
    status               TEXT        NOT NULL DEFAULT 'active'
                                     CHECK (status IN ('active', 'revoked', 'expired')),
    expires_at           TIMESTAMPTZ NOT NULL,
    can_delegate         BOOLEAN     NOT NULL DEFAULT false,
    one_time             BOOLEAN     NOT NULL DEFAULT false,
    usage_count          INTEGER     NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Active-token lookup (most frequent hot path)
CREATE INDEX IF NOT EXISTS idx_a2a_grants_token_active
    ON a2a_grants (token_hash)
    WHERE status = 'active';

-- Owner namespace list-grants query
CREATE INDEX IF NOT EXISTS idx_a2a_grants_owner
    ON a2a_grants (owner_namespace_id, status);

-- Expiry sweep (background janitor)
CREATE INDEX IF NOT EXISTS idx_a2a_grants_expires
    ON a2a_grants (expires_at)
    WHERE status = 'active';

DO $$
BEGIN
    REVOKE ALL ON a2a_grants FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT INSERT, SELECT, UPDATE ON a2a_grants TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — a2a_grants GRANTs skipped (create role or run migrations)';
    END IF;
END $$;

-- Enforce SHA-256 hash length (32 bytes) on token_hash
-- Diagnostic: if existing rows have invalid token_hash length, warn and skip
-- the constraint to prevent a hard crash on dirty legacy data.
DO $$
DECLARE
    invalid_count BIGINT;
BEGIN
    SELECT count(*) INTO invalid_count FROM a2a_grants WHERE length(token_hash) != 32;

    IF invalid_count > 0 THEN
        RAISE WARNING 'ck_a2a_grants_token_hash_len NOT ADDED: % row(s) in a2a_grants have token_hash length != 32. Repair these rows before the constraint can be enforced.', invalid_count;
    ELSE
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.check_constraints
            WHERE constraint_name = 'ck_a2a_grants_token_hash_len'
        ) THEN
            ALTER TABLE a2a_grants ADD CONSTRAINT ck_a2a_grants_token_hash_len
                CHECK (length(token_hash) = 32);
            RAISE NOTICE 'ck_a2a_grants_token_hash_len constraint added successfully.';
        END IF;
    END IF;
END $$;

-- --- Phase 3.2: Multi-namespace resource quotas ---
-- ``used_amount`` is the last flushed value in PostgreSQL. When
-- ``TRIMCP_QUOTA_REDIS_COUNTERS`` is enabled, the hot path increments a Redis
-- mirror (see nce.quotas) and a background task periodically runs
-- ``flush_quota_counters_to_postgres`` to persist counters without serializing
-- writers on this table.
-- Namespace-wide rows use agent_id IS NULL; per-agent rows set agent_id.
-- Enforcement applies only where matching rows exist (no row => no limit for that scope).
CREATE TABLE IF NOT EXISTS resource_quotas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id    UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    agent_id        TEXT,
    resource_type   TEXT NOT NULL,
    limit_amount    BIGINT NOT NULL CHECK (limit_amount >= 0),
    used_amount     BIGINT NOT NULL DEFAULT 0 CHECK (used_amount >= 0),
    reset_at        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (agent_id IS NULL OR (length(agent_id) >= 1 AND length(agent_id) <= 128)),
    CHECK (resource_type <> ''),
    CONSTRAINT chk_quota CHECK (used_amount <= limit_amount)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_quotas_ns_res
    ON resource_quotas (namespace_id, resource_type)
    WHERE agent_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_quotas_ns_agent_res
    ON resource_quotas (namespace_id, agent_id, resource_type)
    WHERE agent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_resource_quotas_ns_type
    ON resource_quotas (namespace_id, resource_type);

DO $$
BEGIN
    REVOKE ALL ON resource_quotas FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON resource_quotas TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — resource_quotas GRANTs skipped (create role or run migrations)';
    END IF;
END $$;

-- --- Phase 3: Dead Letter Queue (Poison Pill) ---
-- Captures background-task payloads that exhaust their retry budget so they
-- are not re-enqueued indefinitely.  Admin UI / API can replay or purge.
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id   UUID REFERENCES namespaces(id),
    task_name      TEXT NOT NULL,          -- e.g. 'process_code_indexing'
    job_id         TEXT NOT NULL,          -- RQ job id
    kwargs         JSONB NOT NULL,         -- frozen kwargs of the failed invocation
    error_message  TEXT NOT NULL,          -- last exception message (truncated to 1024)
    attempt_count  INTEGER NOT NULL CHECK (attempt_count > 0),
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'replayed', 'purged')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    replayed_at    TIMESTAMPTZ,
    purged_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dlq_task_status ON dead_letter_queue (task_name, status);
CREATE INDEX IF NOT EXISTS idx_dlq_created ON dead_letter_queue (created_at DESC);

DO $$
BEGIN
    REVOKE ALL ON dead_letter_queue FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT SELECT, INSERT, UPDATE ON dead_letter_queue TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — dead_letter_queue GRANTs skipped';
    END IF;
END $$;

-- --- Phase 4: Transactional Outbox ---
-- Ordered, at-most-once delivery of domain events.
-- The relay process polls unpublished rows, delivers to downstream
-- consumers, and marks published_at.
CREATE TABLE IF NOT EXISTS outbox_events (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id   UUID NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id   TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    payload        JSONB NOT NULL,
    headers        JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox_events (created_at)
    WHERE published_at IS NULL;

ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS namespace_isolation_policy ON outbox_events;
DROP POLICY IF EXISTS tenant_isolation_policy ON outbox_events;
CREATE POLICY tenant_isolation_policy ON outbox_events
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    REVOKE ALL ON outbox_events FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON outbox_events TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — outbox_events GRANTs skipped';
    END IF;
END $$;

-- --- Phase 3: Active Learning Queue ---
CREATE TABLE IF NOT EXISTS active_learning_queue (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id     UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    agent_id         TEXT NOT NULL DEFAULT 'default',
    payload          JSONB NOT NULL,
    confidence_score REAL NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'confirmed', 'rejected')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at      TIMESTAMPTZ,
    resolved_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_active_learning_queue_ns_status
    ON active_learning_queue (namespace_id, status);

-- --- Phase 4: Saga Execution Log ---
-- Durable saga state for crash-recovery.  If a worker dies between PG commit
-- and rollback completion, the recovery cron re-drives compensation from the
-- persisted payload.
CREATE TABLE IF NOT EXISTS saga_execution_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    saga_type    TEXT NOT NULL,           -- 'store_memory', 'forget_memory', etc.
    namespace_id UUID NOT NULL,
    agent_id     TEXT NOT NULL,
    state        TEXT NOT NULL
                 CHECK (state IN ('started', 'pg_committed', 'completed', 'rolled_back', 'recovery_needed')),
    payload      JSONB NOT NULL,          -- enough to re-drive rollback
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saga_state_created
    ON saga_execution_log (state, created_at)
    WHERE state IN ('started', 'pg_committed', 'recovery_needed');

ALTER TABLE saga_execution_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE saga_execution_log FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS namespace_isolation_policy ON saga_execution_log;
DROP POLICY IF EXISTS tenant_isolation_policy ON saga_execution_log;
CREATE POLICY tenant_isolation_policy ON saga_execution_log
    FOR ALL TO nce_app
    USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())
    WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace());

DO $$
BEGIN
    REVOKE ALL ON saga_execution_log FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT SELECT, INSERT, UPDATE ON saga_execution_log TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — saga_execution_log GRANTs skipped';
    END IF;
END $$;



-- --- Dynamics 365 / Dataverse vertical module ---
CREATE TABLE IF NOT EXISTS d365_integrations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id        UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    org_url             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK (status IN ('ACTIVE', 'DEGRADED', 'DISABLED')),
    token_enc           BYTEA,           -- AES-256-GCM encrypted access token JSON
    token_expires_at    TIMESTAMPTZ,
    webhook_secret_enc  BYTEA,           -- AES-256-GCM encrypted webhook secret
    last_sync_at        TIMESTAMPTZ,
    last_sync_stats     JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, org_url)
);

CREATE INDEX IF NOT EXISTS idx_d365_integrations_namespace
    ON d365_integrations (namespace_id);
CREATE INDEX IF NOT EXISTS idx_d365_integrations_status
    ON d365_integrations (status)
    WHERE status = 'ACTIVE';

-- D365 ↔ NetBox cross-reference mapping table.
-- Stores confirmed and inferred mappings between Dataverse entities
-- (Accounts, Functional Locations) and NetBox entities (Tenants, Sites, Locations).
-- Rows are upserted by the bridge cron tick and surfaced as kg_edges.
CREATE TABLE IF NOT EXISTS d365_netbox_mappings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id        UUID NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    d365_entity_type    TEXT NOT NULL
                        CHECK (d365_entity_type IN ('account', 'functional_location')),
    d365_entity_id      TEXT NOT NULL,          -- Dataverse GUID string
    d365_entity_name    TEXT NOT NULL,
    nb_entity_type      TEXT NOT NULL
                        CHECK (nb_entity_type IN ('tenant', 'site', 'location')),
    nb_entity_id        INTEGER NOT NULL,       -- NetBox integer PK
    nb_entity_name      TEXT NOT NULL,
    nb_entity_slug      TEXT,
    -- How was this match made?
    match_method        TEXT NOT NULL
                        CHECK (match_method IN ('custom_field', 'exact', 'slug', 'fuzzy', 'manual')),
    match_confidence    FLOAT NOT NULL DEFAULT 1.0
                        CHECK (match_confidence BETWEEN 0.0 AND 1.0),
    -- Operator confirmation (false = inferred, true = human-confirmed)
    confirmed           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (namespace_id, d365_entity_type, d365_entity_id, nb_entity_type, nb_entity_id)
);

CREATE INDEX IF NOT EXISTS idx_d365_netbox_mappings_namespace
    ON d365_netbox_mappings (namespace_id);
CREATE INDEX IF NOT EXISTS idx_d365_netbox_mappings_d365_type
    ON d365_netbox_mappings (namespace_id, d365_entity_type);
CREATE INDEX IF NOT EXISTS idx_d365_netbox_mappings_confirmed
    ON d365_netbox_mappings (namespace_id, confirmed)
    WHERE confirmed = TRUE;

-- --- Phase 5: DB-backed runtime settings (V.1a) ---
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       JSONB,
    secret_enc  BYTEA,
    is_secret   BOOLEAN NOT NULL DEFAULT false,
    section     TEXT,
    updated_by  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    REVOKE ALL ON settings FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nce_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON settings TO nce_app;
    ELSE
        RAISE NOTICE 'nce_app role not found — settings GRANTs skipped';
    END IF;
END $$;

-- --- Row Level Security (Phase 0.1 Hardening) ---
-- Applied after all tenant tables exist. Policies use get_nce_namespace() (fail-fast).
-- kg_node_embeddings remain global (no namespace_id). kg_nodes/kg_edges are tenant-scoped.

-- Backfill nullable namespace_id on tables that gained the column after first deploy.
DO $$
DECLARE
    legacy_ns UUID;
BEGIN
    SELECT id INTO legacy_ns FROM namespaces WHERE slug = '_global_legacy' LIMIT 1;
    IF legacy_ns IS NOT NULL THEN
        UPDATE bridge_subscriptions SET namespace_id = legacy_ns WHERE namespace_id IS NULL;
        UPDATE dead_letter_queue SET namespace_id = legacy_ns WHERE namespace_id IS NULL;
        UPDATE embedding_migrations SET namespace_id = legacy_ns WHERE namespace_id IS NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_dead_letter_queue_namespace_id
    ON dead_letter_queue (namespace_id);
CREATE INDEX IF NOT EXISTS idx_embedding_migrations_namespace_id
    ON embedding_migrations (namespace_id);

-- FIX-055: kg_node_embeddings are global (not namespace-scoped).
ALTER TABLE kg_node_embeddings DISABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    t text;
    tenant_tables text[] := ARRAY[
        'memories',
        'kg_nodes',
        'kg_edges',
        'pii_redactions',
        'memory_salience',
        'contradictions',
        'snapshots',
        'event_log',
        'resource_quotas',
        'consolidation_runs',
        'bridge_subscriptions',
        'dead_letter_queue',
        'embedding_migrations',
        'memory_embeddings',
        'active_learning_queue',
        'd365_integrations',
        'd365_netbox_mappings'
    ];
BEGIN
    FOREACH t IN ARRAY tenant_tables
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS namespace_isolation_policy ON public.%I', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_policy ON public.%I', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation_policy ON public.%I '
            'FOR ALL TO nce_app '
            'USING (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace()) '
            'WITH CHECK (namespace_id IS NOT NULL AND namespace_id = get_nce_namespace())',
            t
        );
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM nce_app', t);
        IF t IN ('event_log', 'pii_redactions') THEN
            EXECUTE format(
                'GRANT SELECT, INSERT ON TABLE public.%I TO nce_app',
                t
            );
        ELSE
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO nce_app',
                t
            );
        END IF;
    END LOOP;
END $$;

ALTER TABLE a2a_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a_grants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS namespace_isolation_policy ON a2a_grants;
DROP POLICY IF EXISTS tenant_isolation_policy ON a2a_grants;
CREATE POLICY tenant_isolation_policy ON a2a_grants
    FOR ALL TO nce_app
    USING (
        owner_namespace_id = get_nce_namespace()
        OR target_namespace_id = get_nce_namespace()
    )
    WITH CHECK (owner_namespace_id = get_nce_namespace());
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE a2a_grants TO nce_app;
