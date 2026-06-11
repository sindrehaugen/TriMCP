# Diff Reference for Batch 62

```diff
diff --git a/docker-compose.yml b/docker-compose.yml
index 5738ca6..3d11571 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -25,6 +25,25 @@ services:
   postgres:
     image: pgvector/pgvector:pg16
     container_name: nce-postgres
+    # Disk-I/O tuning (VI.5c D1). Larger shared_buffers + maintenance_work_mem
+    # speed HNSW index builds; wal_compression + a higher max_wal_size and
+    # checkpoint_completion_target=0.9 spread WAL/checkpoint flushes for the
+    # write-heavy WORM event_log. synchronous_commit STAYS ON — the WORM log's
+    # durability (a committed row is WAL-durable on disk) must NOT be weakened.
+    command:
+      - "postgres"
+      - "-c"
+      - "shared_buffers=512MB"
+      - "-c"
+      - "maintenance_work_mem=512MB"
+      - "-c"
+      - "wal_compression=on"
+      - "-c"
+      - "checkpoint_completion_target=0.9"
+      - "-c"
+      - "max_wal_size=4GB"
+      - "-c"
+      - "synchronous_commit=on"
     environment:
       POSTGRES_USER: mcp_user
       POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-mcp_password}
@@ -41,10 +60,21 @@ services:
       timeout: 5s
       retries: 5
     restart: unless-stopped
+    logging:
+      driver: json-file
+      options:
+        max-size: "10m"
+        max-file: "3"
 
   mongodb:
     image: mongo:7.0
     container_name: nce-mongo
+    # Disk-I/O tuning (VI.5c D1): zstd block compressor (vs the snappy default)
+    # for collection data — transcripts/code/payloads compress well, so this
+    # cuts on-disk size and read I/O.
+    command:
+      - "--wiredTigerCollectionBlockCompressor"
+      - "zstd"
     ports:
       - "127.0.0.1:27017:27017"
     volumes:
@@ -55,6 +85,11 @@ services:
       interval: 5s
       timeout: 5s
       retries: 5
+    logging:
+      driver: json-file
+      options:
+        max-size: "10m"
+        max-file: "3"
 
   minio:
     image: minio/minio:RELEASE.2024-11-07T00-52-20Z
@@ -108,6 +143,14 @@ services:
       OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
       MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
       TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
+      # Disk-I/O tuning (VI.5c D4/D5): extractor temp churn (write temp ->
+      # subprocess reads -> unlink) is purely transient data. Point the artifact
+      # staging dir AND tempfile's TMPDIR at the RAM-backed tmpfs mount below so
+      # those writes never touch real disk.
+      NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
+      TMPDIR: /dev/shm/nce-staging
+    tmpfs:
+      - /dev/shm/nce-staging
     deploy:
       # N replicas process N RQ jobs concurrently (default 2).
       replicas: ${WORKER_REPLICAS:-2}
@@ -128,6 +171,11 @@ services:
       minio:
         condition: service_healthy
     restart: unless-stopped
+    logging:
+      driver: json-file
+      options:
+        max-size: "10m"
+        max-file: "3"
 
   # APScheduler: bridge subscription renewal + re-embedding sweeps (cognitive maintenance).
   cron:
@@ -147,6 +195,11 @@ services:
       OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
       MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
       TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
+      # Disk-I/O tuning (VI.5c D4/D5): RAM-backed temp/staging (see worker).
+      NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
+      TMPDIR: /dev/shm/nce-staging
+    tmpfs:
+      - /dev/shm/nce-staging
     # Multicore (VI.5a): cron MUST stay a singleton — CronLock is the only
     # split-brain guard. NEVER scale this above 1 replica.
     deploy:
@@ -161,6 +214,11 @@ services:
       minio:
         condition: service_healthy
     restart: unless-stopped
+    logging:
+      driver: json-file
+      options:
+        max-size: "10m"
+        max-file: "3"
 
   admin:
     build:
@@ -191,6 +249,11 @@ services:
       OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
       MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
       TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
+      # Disk-I/O tuning (VI.5c D4/D5): RAM-backed temp/staging (see worker).
+      NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
+      TMPDIR: /dev/shm/nce-staging
+    tmpfs:
+      - /dev/shm/nce-staging
     ports:
       - "${ADMIN_PORT:-8003}:8003"
     depends_on:
@@ -217,6 +280,11 @@ services:
       retries: 3
       start_period: 20s
     restart: unless-stopped
+    logging:
+      driver: json-file
+      options:
+        max-size: "10m"
+        max-file: "3"
 
   a2a:
     build:
@@ -248,6 +316,11 @@ services:
       OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
       MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
       TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
+      # Disk-I/O tuning (VI.5c D4/D5): RAM-backed temp/staging (see worker).
+      NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
+      TMPDIR: /dev/shm/nce-staging
+    tmpfs:
+      - /dev/shm/nce-staging
     ports:
       - "${A2A_PORT:-8004}:8004"
     depends_on:
@@ -272,6 +345,11 @@ services:
       retries: 3
       start_period: 15s
     restart: unless-stopped
+    logging:
+      driver: json-file
+      options:
+        max-size: "10m"
+        max-file: "3"
 
   webhook-receiver:
     build:
@@ -303,6 +381,11 @@ services:
       OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
       MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
       TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
+      # Disk-I/O tuning (VI.5c D4/D5): RAM-backed temp/staging (see worker).
+      NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
+      TMPDIR: /dev/shm/nce-staging
+    tmpfs:
+      - /dev/shm/nce-staging
     ports:
       - "${WEBHOOK_PORT:-8080}:8080"
     depends_on:
@@ -323,6 +406,11 @@ services:
       retries: 3
       start_period: 10s
     restart: unless-stopped
+    logging:
+      driver: json-file
+      options:
+        max-size: "10m"
+        max-file: "3"
 
   jaeger:
     image: jaegertracing/all-in-one:1.60
diff --git a/nce/migrations/019_halfvec_embeddings.sql b/nce/migrations/019_halfvec_embeddings.sql
new file mode 100644
index 0000000..108171a
--- /dev/null
+++ b/nce/migrations/019_halfvec_embeddings.sql
@@ -0,0 +1,54 @@
+-- 019_halfvec_embeddings.sql
+-- NCE_MASTER_PLAN VI.5c D2 (Disk I/O) — migrate fixed-dimension pgvector
+-- embedding columns from vector(768) (fp32, ~3 KB/row + a large, write-
+-- amplifying HNSW index) to halfvec(768) (fp16). This halves on-disk vector
+-- storage, HNSW index size, and read I/O with negligible recall loss; the
+-- existing fp32 values cast to fp16 in place (USING embedding::halfvec(768)).
+-- The existing re-embedding machinery carries recall going forward — no
+-- coordinated re-embedding is required, so this is a pure in-place column-type
+-- migration + HNSW index rebuild. Reconciled with Batch 18 (vector compliance /
+-- cryptographic erasure), which is DONE+PASSED TAG, so the storage-format change
+-- does not conflict with the erasure work.
+--
+-- Mirrors nce/schema.sql (memories.embedding, kg_nodes.embedding and their HNSW
+-- indexes idx_memories_embedding_hnsw / idx_kg_nodes_embedding_hnsw).
+--
+-- NOTE: The dynamic-dimension embedding stores (memory_embeddings.embedding,
+-- kg_node_embeddings.embedding) are unconstrained `vector` (any model dim) and
+-- are intentionally NOT touched here.
+--
+-- Idempotent: re-running is a no-op. ALTER ... TYPE is skipped when the column
+-- is already halfvec; the HNSW index drop/recreate is conditioned on the column
+-- type so a second run does not rebuild an already-halfvec index.
+-- ============================================================================
+
+DO $$
+BEGIN
+    -- memories.embedding -----------------------------------------------------
+    IF EXISTS (
+        SELECT 1 FROM information_schema.columns
+        WHERE table_schema = 'public' AND table_name = 'memories'
+          AND column_name = 'embedding' AND udt_name = 'vector'
+    ) THEN
+        DROP INDEX IF EXISTS idx_memories_embedding_hnsw;
+        ALTER TABLE memories
+            ALTER COLUMN embedding TYPE halfvec(768)
+            USING embedding::halfvec(768);
+        CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw
+            ON memories USING hnsw (embedding halfvec_cosine_ops);
+    END IF;
+
+    -- kg_nodes.embedding -----------------------------------------------------
+    IF EXISTS (
+        SELECT 1 FROM information_schema.columns
+        WHERE table_schema = 'public' AND table_name = 'kg_nodes'
+          AND column_name = 'embedding' AND udt_name = 'vector'
+    ) THEN
+        DROP INDEX IF EXISTS idx_kg_nodes_embedding_hnsw;
+        ALTER TABLE kg_nodes
+            ALTER COLUMN embedding TYPE halfvec(768)
+            USING embedding::halfvec(768);
+        CREATE INDEX IF NOT EXISTS idx_kg_nodes_embedding_hnsw
+            ON kg_nodes USING hnsw (embedding halfvec_cosine_ops);
+    END IF;
+END $$;
diff --git a/nce/schema.sql b/nce/schema.sql
index 3dbb455..9b964bc 100644
--- a/nce/schema.sql
+++ b/nce/schema.sql
@@ -60,7 +60,9 @@ CREATE TABLE IF NOT EXISTS memories (
     memory_type         TEXT        NOT NULL DEFAULT 'episodic',
     assertion_type      TEXT        NOT NULL DEFAULT 'fact',
     payload_ref         TEXT        NOT NULL,
-    embedding           vector(768),
+    -- VI.5c D2: fp16 (halfvec) halves on-disk vector + HNSW index size and read
+    -- I/O vs full fp32 storage, with negligible recall loss. fp32 casts to fp16.
+    embedding           halfvec(768),
     embedding_model_id  UUID,
     derived_from        JSONB,
     valid_from          TIMESTAMPTZ NOT NULL DEFAULT now(),
@@ -163,7 +165,7 @@ CREATE INDEX IF NOT EXISTS idx_memories_user ON memories (user_id);
 CREATE INDEX IF NOT EXISTS idx_memories_user_session ON memories (user_id, session_id, created_at DESC);
 CREATE INDEX IF NOT EXISTS idx_memories_filepath ON memories (filepath);
 CREATE INDEX IF NOT EXISTS idx_memories_user_path ON memories (user_id, filepath);
-CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw ON memories USING hnsw (embedding vector_cosine_ops);
+CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw ON memories USING hnsw (embedding halfvec_cosine_ops);
 -- Fleet admin: COUNT(*) / lookups by tenant without scanning all time partitions
 CREATE INDEX IF NOT EXISTS idx_memories_namespace_id ON memories (namespace_id);
 
@@ -191,7 +193,8 @@ CREATE TABLE IF NOT EXISTS kg_nodes (
     id            UUID DEFAULT gen_random_uuid(),
     label         TEXT NOT NULL,
     entity_type   VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN',
-    embedding     VECTOR(768),
+    -- VI.5c D2: fp16 (halfvec) — see memories.embedding above.
+    embedding     halfvec(768),
     embedding_model_id UUID,
     namespace_id  UUID NOT NULL,
     payload_ref   CHAR(24),
@@ -270,7 +273,7 @@ BEGIN
     END IF;
 END $$;
 
-CREATE INDEX IF NOT EXISTS idx_kg_nodes_embedding_hnsw ON kg_nodes USING hnsw (embedding vector_cosine_ops);
+CREATE INDEX IF NOT EXISTS idx_kg_nodes_embedding_hnsw ON kg_nodes USING hnsw (embedding halfvec_cosine_ops);
 CREATE INDEX IF NOT EXISTS idx_kg_nodes_updated ON kg_nodes (updated_at);
 
 -- --- Knowledge-graph edges (partitioned by HASH) ---
diff --git a/tests/test_disk_io_tuning.py b/tests/test_disk_io_tuning.py
new file mode 100644
index 0000000..481bcaa
--- /dev/null
+++ b/tests/test_disk_io_tuning.py
@@ -0,0 +1,148 @@
+"""Disk-I/O tuning acceptance (NCE_MASTER_PLAN VI.5c, Batch 62).
+
+Structural assertions over the parsed ``docker-compose.yml`` plus the
+``halfvec(768)`` storage-format change in ``nce/schema.sql`` and migration 019:
+
+* D1 — Postgres ``command:`` carries the WAL/compression/checkpoint tuning
+  flags, and ``synchronous_commit`` is NOT turned off (WORM ``event_log``
+  durability must stay ON);
+* D1 — Mongo runs the zstd WiredTiger collection block compressor;
+* D2 — the fixed-dimension embedding columns are ``halfvec(768)`` in both
+  ``schema.sql`` and migration 019, and the HNSW indexes use
+  ``halfvec_cosine_ops`` (mirror is consistent);
+* D4 — a RAM-backed tmpfs staging mount is wired and ``NCE_ARTIFACT_STAGING_DIR``
+  points at it on the compute-bearing services;
+* D7 — container log rotation (``max-size``/``max-file``) is set.
+"""
+
+from __future__ import annotations
+
+import re
+from pathlib import Path
+
+import yaml
+
+_REPO_ROOT = Path(__file__).resolve().parents[1]
+_COMPOSE = _REPO_ROOT / "docker-compose.yml"
+_SCHEMA = _REPO_ROOT / "nce" / "schema.sql"
+_MIGRATION = _REPO_ROOT / "nce" / "migrations" / "019_halfvec_embeddings.sql"
+
+# Services that stage/extract artifacts and so must get the tmpfs staging mount.
+_STAGING_SERVICES = ("worker", "cron", "admin", "a2a", "webhook-receiver")
+# Every service that pins a json-file log-rotation policy (D7).
+_ROTATED_SERVICES = (
+    "postgres",
+    "mongodb",
+    "worker",
+    "cron",
+    "admin",
+    "a2a",
+    "webhook-receiver",
+)
+_TMPFS_PATH = "/dev/shm/nce-staging"
+
+
+def _load() -> dict:
+    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
+
+
+def _command(service: dict) -> list[str]:
+    cmd = service.get("command", [])
+    if isinstance(cmd, str):
+        return cmd.split()
+    return list(cmd)
+
+
+# --- D1: Postgres / Mongo datastore tuning ---------------------------------
+
+
+def test_postgres_wal_and_compression_tuning() -> None:
+    pg = _load()["services"]["postgres"]
+    cmd = " ".join(_command(pg))
+    assert "shared_buffers=" in cmd, "PG shared_buffers tuning missing"
+    assert "maintenance_work_mem=" in cmd, "PG maintenance_work_mem tuning missing"
+    assert "wal_compression=on" in cmd, "PG wal_compression=on missing"
+    assert "checkpoint_completion_target=0.9" in cmd, "PG checkpoint target missing"
+    assert "max_wal_size=" in cmd, "PG max_wal_size tuning missing"
+
+
+def test_worm_synchronous_commit_not_weakened() -> None:
+    """The WORM event_log requires synchronous_commit ON — never off/local/remote_*."""
+    pg = _load()["services"]["postgres"]
+    cmd = " ".join(_command(pg))
+    # synchronous_commit, if set at all, must be exactly =on.
+    for forbidden in (
+        "synchronous_commit=off",
+        "synchronous_commit=local",
+        "synchronous_commit=remote_write",
+        "synchronous_commit=remote_apply",
+    ):
+        assert forbidden not in cmd, f"WORM durability weakened: {forbidden}"
+    assert "synchronous_commit=on" in cmd, "synchronous_commit=on must be explicit for the WORM log"
+
+
+def test_mongo_zstd_block_compressor() -> None:
+    mongo = _load()["services"]["mongodb"]
+    cmd = _command(mongo)
+    assert "--wiredTigerCollectionBlockCompressor" in cmd, "Mongo block compressor flag missing"
+    idx = cmd.index("--wiredTigerCollectionBlockCompressor")
+    assert cmd[idx + 1] == "zstd", f"Mongo compressor must be zstd, got {cmd[idx + 1]!r}"
+
+
+# --- D4: tmpfs RAM-backed staging ------------------------------------------
+
+
+def test_compute_services_have_tmpfs_staging() -> None:
+    services = _load()["services"]
+    for name in _STAGING_SERVICES:
+        svc = services[name]
+        tmpfs = svc.get("tmpfs", [])
+        assert any(_TMPFS_PATH in str(m) for m in tmpfs), f"{name} missing tmpfs {_TMPFS_PATH}"
+        env = svc.get("environment", {})
+        assert isinstance(env, dict)
+        staging = env.get("NCE_ARTIFACT_STAGING_DIR", "")
+        assert _TMPFS_PATH in str(staging), (
+            f"{name} NCE_ARTIFACT_STAGING_DIR must point at the tmpfs mount, got {staging!r}"
+        )
+        assert _TMPFS_PATH in str(env.get("TMPDIR", "")), f"{name} TMPDIR must point at tmpfs"
+
+
+# --- D7: bounded log volume ------------------------------------------------
+
+
+def test_log_rotation_configured() -> None:
+    services = _load()["services"]
+    for name in _ROTATED_SERVICES:
+        logging = services[name].get("logging", {})
+        opts = logging.get("options", {})
+        assert opts.get("max-size"), f"{name} missing logging max-size"
+        assert opts.get("max-file"), f"{name} missing logging max-file"
+
+
+# --- D2: halfvec storage format (schema + migration mirror) ----------------
+
+
+def test_schema_uses_halfvec_not_fp32_for_fixed_dim_columns() -> None:
+    schema = _SCHEMA.read_text(encoding="utf-8")
+    # The two fixed-dimension embedding columns must be halfvec(768)...
+    assert len(re.findall(r"halfvec\(768\)", schema)) >= 2, "schema.sql lost a halfvec(768) column"
+    # ...and no fixed-dim fp32 vector(768) columns remain.
+    assert not re.search(r"\bvector\(768\)", schema, re.IGNORECASE), (
+        "schema.sql still has a fp32 vector(768) column"
+    )
+    # HNSW indexes must use the halfvec opclass, not the fp32 vector opclass.
+    assert "halfvec_cosine_ops" in schema
+    assert "vector_cosine_ops" not in schema, "schema.sql HNSW index still uses vector_cosine_ops"
+
+
+def test_migration_019_mirrors_halfvec_change() -> None:
+    mig = _MIGRATION.read_text(encoding="utf-8")
+    assert "halfvec(768)" in mig
+    assert "halfvec_cosine_ops" in mig
+    # Both fixed-dim tables are migrated.
+    assert "memories" in mig and "kg_nodes" in mig
+    # The fp32 -> fp16 cast is present (carries existing values).
+    assert "::halfvec(768)" in mig
+    # The HNSW indexes are rebuilt for halfvec.
+    assert "idx_memories_embedding_hnsw" in mig
+    assert "idx_kg_nodes_embedding_hnsw" in mig
```
