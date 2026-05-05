-- ============================================================================
-- TriMCP — PostgreSQL Schema
-- Loaded by trimcp.orchestrator.TriStackEngine._init_pg_schema on connect().
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

-- --- Phase 0.1: Namespaces ---
CREATE TABLE IF NOT EXISTS namespaces (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug       TEXT UNIQUE NOT NULL,
    parent_id  UUID REFERENCES namespaces(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata   JSONB NOT NULL DEFAULT '{}'::jsonb
);

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

-- Data Migration from legacy tables
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'memory_metadata') THEN
        INSERT INTO memories (
            id, user_id, session_id, embedding, payload_ref, created_at, content_fts, 
            namespace_id, agent_id, signature, signature_key_id, memory_type
        )
        SELECT 
            id, user_id, session_id, embedding, mongo_ref_id, created_at, content_fts,
            namespace_id, agent_id, signature, signature_key_id, 'episodic'
        FROM memory_metadata
        ON CONFLICT DO NOTHING;
        
        DROP TABLE memory_metadata CASCADE;
    END IF;

    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'code_metadata') THEN
        INSERT INTO memories (
            id, filepath, language, node_type, name, start_line, end_line, file_hash, 
            embedding, payload_ref, created_at, user_id, content_fts, memory_type
        )
        SELECT 
            id, filepath, language, node_type, name, start_line, end_line, file_hash, 
            embedding, mongo_ref_id, created_at, user_id, content_fts, 'code_chunk'
        FROM code_metadata
        ON CONFLICT DO NOTHING;
        
        DROP TABLE code_metadata CASCADE;
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

-- --- Knowledge-graph nodes (partitioned by HASH) ---
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = 'kg_nodes' AND c.relkind = 'r' AND c.relispartition = false AND NOT EXISTS (SELECT 1 FROM pg_partitioned_table WHERE partrelid = c.oid)) THEN
        ALTER TABLE kg_nodes RENAME TO kg_nodes_old;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS kg_nodes (
    id           UUID DEFAULT gen_random_uuid(),
    label        TEXT NOT NULL,
    entity_type  VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN',
    embedding    VECTOR(768),
    payload_ref  CHAR(24),
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (label)
) PARTITION BY HASH (label);

CREATE TABLE IF NOT EXISTS kg_nodes_0 PARTITION OF kg_nodes FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE IF NOT EXISTS kg_nodes_1 PARTITION OF kg_nodes FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE IF NOT EXISTS kg_nodes_2 PARTITION OF kg_nodes FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE IF NOT EXISTS kg_nodes_3 PARTITION OF kg_nodes FOR VALUES WITH (MODULUS 4, REMAINDER 3);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'kg_nodes_old') THEN
        INSERT INTO kg_nodes (id, label, entity_type, embedding, payload_ref, created_at, updated_at)
        SELECT id, label, entity_type, embedding, mongo_ref_id, created_at, updated_at
        FROM kg_nodes_old
        ON CONFLICT (label) DO NOTHING;
        DROP TABLE kg_nodes_old CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_kg_nodes_embedding_hnsw ON kg_nodes USING hnsw (embedding vector_cosine_ops);

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
    payload_ref  CHAR(24),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (subject_label, predicate, object_label)
) PARTITION BY HASH (subject_label, predicate, object_label);

CREATE TABLE IF NOT EXISTS kg_edges_0 PARTITION OF kg_edges FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE IF NOT EXISTS kg_edges_1 PARTITION OF kg_edges FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE IF NOT EXISTS kg_edges_2 PARTITION OF kg_edges FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE IF NOT EXISTS kg_edges_3 PARTITION OF kg_edges FOR VALUES WITH (MODULUS 4, REMAINDER 3);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'kg_edges_old') THEN
        INSERT INTO kg_edges (id, subject_label, predicate, object_label, confidence, payload_ref, created_at, updated_at)
        SELECT id, subject_label, predicate, object_label, confidence, mongo_ref_id, created_at, updated_at
        FROM kg_edges_old
        ON CONFLICT (subject_label, predicate, object_label) DO NOTHING;
        DROP TABLE kg_edges_old CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_kg_edges_subject ON kg_edges (subject_label);
CREATE INDEX IF NOT EXISTS idx_kg_edges_object  ON kg_edges (object_label);

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
    PRIMARY KEY (id, detected_at)
) PARTITION BY RANGE (detected_at);

CREATE TABLE IF NOT EXISTS contradictions_default PARTITION OF contradictions DEFAULT;

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
    memory_id  UUID NOT NULL,
    model_id   UUID NOT NULL REFERENCES embedding_models(id),
    embedding  vector, -- Unconstrained dimension to support any model
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (memory_id, model_id)
) PARTITION BY HASH (memory_id);

CREATE TABLE IF NOT EXISTS memory_embeddings_0 PARTITION OF memory_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE IF NOT EXISTS memory_embeddings_1 PARTITION OF memory_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE IF NOT EXISTS memory_embeddings_2 PARTITION OF memory_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE IF NOT EXISTS memory_embeddings_3 PARTITION OF memory_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 3);

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

-- --- Phase 2.3: Event Log (WORM) ---
CREATE TABLE IF NOT EXISTS consolidation_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace_id     UUID NOT NULL REFERENCES namespaces(id),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'running',
    events_processed INTEGER NOT NULL DEFAULT 0,
    clusters_formed  INTEGER NOT NULL DEFAULT 0,
    abstractions_created INTEGER NOT NULL DEFAULT 0,
    error_message    TEXT
);

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
    PRIMARY KEY (id, occurred_at),
    UNIQUE (namespace_id, event_seq, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE IF NOT EXISTS event_log_default PARTITION OF event_log DEFAULT;

CREATE INDEX IF NOT EXISTS idx_event_log_ns_time ON event_log (namespace_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_event_log_ns_seq  ON event_log (namespace_id, event_seq);
CREATE INDEX IF NOT EXISTS idx_event_log_parent  ON event_log (parent_event_id) WHERE parent_event_id IS NOT NULL;

DO $$
BEGIN
    REVOKE ALL ON event_log FROM PUBLIC;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trimcp_app') THEN
        GRANT INSERT, SELECT ON event_log TO trimcp_app;
    END IF;
END $$;
