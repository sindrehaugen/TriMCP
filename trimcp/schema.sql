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
-- pgcrypto provides gen_random_uuid() on PG <13. On PG >=13 it's built-in,
-- but enabling the extension is idempotent and guarantees portability.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- --- Semantic memory index (vector) ---
-- mongo_ref_id is NOT NULL: the Saga never inserts a vector row without a
-- committed Mongo document, so a null value indicates corruption.
CREATE TABLE IF NOT EXISTS memory_metadata (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      VARCHAR(128),
    session_id   VARCHAR(128),
    embedding    VECTOR(768),
    mongo_ref_id CHAR(24) NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Migration: Add content_fts if it doesn't exist
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='memory_metadata' AND column_name='content_fts') THEN
        ALTER TABLE memory_metadata ADD COLUMN content_fts TSVECTOR;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_memory_fts ON memory_metadata USING GIN (content_fts);
CREATE INDEX IF NOT EXISTS idx_memory_mongo_ref ON memory_metadata (mongo_ref_id);
CREATE INDEX IF NOT EXISTS idx_memory_user      ON memory_metadata (user_id);

-- Compound index for recall_memory: it filters on (user_id, session_id) and
-- sorts by created_at DESC LIMIT 1, so an index matching that exact prefix +
-- order lets PG answer without a sort.
CREATE INDEX IF NOT EXISTS idx_memory_user_session
    ON memory_metadata (user_id, session_id, created_at DESC);

-- --- Code AST chunk index ---
CREATE TABLE IF NOT EXISTS code_metadata (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filepath     TEXT,
    language     VARCHAR(64),
    node_type    VARCHAR(64),
    name         VARCHAR(255),
    start_line   INT,
    end_line     INT,
    file_hash    VARCHAR(64),
    embedding    VECTOR(768),
    mongo_ref_id CHAR(24) NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Migration: Add content_fts if it doesn't exist
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='code_metadata' AND column_name='content_fts') THEN
        ALTER TABLE code_metadata ADD COLUMN content_fts TSVECTOR;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_code_fts       ON code_metadata USING GIN (content_fts);
CREATE INDEX IF NOT EXISTS idx_code_mongo_ref ON code_metadata (mongo_ref_id);
CREATE INDEX IF NOT EXISTS idx_code_filepath  ON code_metadata (filepath);

-- --- Knowledge-graph nodes (entities, upserted by label) ---
-- mongo_ref_id is nullable here: a node may outlive the document that first
-- introduced it if that doc is garbage-collected. updated_at is maintained
-- by the ON CONFLICT DO UPDATE clause in store_memory.
CREATE TABLE IF NOT EXISTS kg_nodes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label        TEXT NOT NULL,
    entity_type  VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN',
    embedding    VECTOR(768),
    mongo_ref_id CHAR(24),
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (label)
);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_label ON kg_nodes (label);

-- --- Knowledge-graph edges (typed relations between labels) ---
-- confidence bounded [0, 1]; malformed extractions rejected at the DB layer.
CREATE TABLE IF NOT EXISTS kg_edges (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_label TEXT NOT NULL,
    predicate     TEXT NOT NULL,
    object_label  TEXT NOT NULL,
    confidence    FLOAT NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    mongo_ref_id  CHAR(24),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (subject_label, predicate, object_label)
);

CREATE INDEX IF NOT EXISTS idx_kg_edges_subject ON kg_edges (subject_label);
CREATE INDEX IF NOT EXISTS idx_kg_edges_object  ON kg_edges (object_label);

-- --- HNSW vector indexes (cosine) ---
-- Without these, every semantic/graph search is a sequential scan over all
-- rows. HNSW gives approximate k-NN in O(log N) with tunable recall via
-- (m, ef_construction). Defaults (m=16, ef_construction=64) suit datasets up
-- to ~10M vectors; tune per workload if needed.
CREATE INDEX IF NOT EXISTS idx_memory_embedding_hnsw
    ON memory_metadata USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_code_embedding_hnsw
    ON code_metadata   USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_embedding_hnsw
    ON kg_nodes        USING hnsw (embedding vector_cosine_ops);
