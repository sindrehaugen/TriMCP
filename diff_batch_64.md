# Diff Reference for Batch 64

```diff
diff --git a/RL.md b/RL.md
index 2c66b07..984fa61 100644
--- a/RL.md
+++ b/RL.md
@@ -71,7 +71,7 @@
 * [DONE] Batch 61 — RAM: offload spaCy + NLI to a sidecar; container mem limits (VI.5b) [PASSED TAG]
 * [DONE] Batch 62 — Disk: datastore tuning + halfvec + tmpfs temp (VI.5c) [PASSED TAG]
 * [DONE] Batch 63 — Cross-encoder reranking (IV.1) [PASSED TAG]
-* [OPEN] Batch 64 — Multi-vector / aspect embeddings (IV.2) [NO TAG]
+* [RUNNING] Batch 64 — Multi-vector / aspect embeddings (IV.2) [NO TAG]
 * [LOCKED] Batch 65 — diag-config: `NCE_DIAG_*` configuration surface (Diag P1) [NO TAG]
 * [LOCKED] Batch 66 — ingestion-event-type: `ingestion_completed` event type + replay handler (Diag P1) [NO TAG]
 * [LOCKED] Batch 67 — diag-schema: diag tables + `topology_graph` unique index + RLS (Diag P1) [NO TAG]
diff --git a/nce/code_mcp_handlers.py b/nce/code_mcp_handlers.py
index e9549e1..430e04d 100644
--- a/nce/code_mcp_handlers.py
+++ b/nce/code_mcp_handlers.py
@@ -125,7 +125,7 @@ async def handle_search_codebase(engine: NCEEngine, arguments: dict[str, Any]) -
     """Semantic search over indexed code chunks. Returns matching functions/classes.
 
     Required: query, namespace_id.
-    Optional: language_filter (allowlisted), top_k (1–50), user_id, private.
+    Optional: language_filter (allowlisted), top_k (1–50), user_id, private, aspect.
     """
     namespace_id = _require_namespace_id(arguments)
 
@@ -140,6 +140,10 @@ async def handle_search_codebase(engine: NCEEngine, arguments: dict[str, Any]) -
 
     top_k = _clamp_top_k(arguments.get("top_k", _TOP_K_DEFAULT))
 
+    aspect = arguments.get("aspect")
+    if aspect is not None:
+        aspect = str(aspect).strip()
+
     results = await engine.search_codebase(
         query=query,
         namespace_id=namespace_id,
@@ -148,5 +152,6 @@ async def handle_search_codebase(engine: NCEEngine, arguments: dict[str, Any]) -
         user_id=arguments.get("user_id"),
         # Default to private=True: callers must opt out explicitly.
         private=_bool_arg(arguments, "private", default=True),
+        aspect=aspect,
     )
     return json.dumps(results)
diff --git a/nce/orchestrator.py b/nce/orchestrator.py
index 3c1881c..4f67623 100644
--- a/nce/orchestrator.py
+++ b/nce/orchestrator.py
@@ -651,6 +651,7 @@ class NCEEngine(OrchestratorBase):
         *,
         user_id: str | None = None,
         private: bool = False,
+        aspect: str | None = None,
     ) -> list[dict]:
         """Codebase hybrid search — delegating to GraphOrchestrator."""
         await self._ensure_graph("search_codebase")
@@ -661,6 +662,7 @@ class NCEEngine(OrchestratorBase):
             top_k,
             user_id=user_id,
             private=private,
+            aspect=aspect,
         )
 
     async def manage_quotas(self, payload: ManageQuotasRequest) -> dict:
diff --git a/nce/orchestrators/graph.py b/nce/orchestrators/graph.py
index 358be3f..8578c2a 100644
--- a/nce/orchestrators/graph.py
+++ b/nce/orchestrators/graph.py
@@ -90,6 +90,7 @@ class GraphOrchestrator(OrchestratorBase):
         *,
         user_id: str | None = None,
         private: bool = False,
+        aspect: str | None = None,
     ) -> list[dict]:
         top_k = max(1, min(top_k, _MAX_TOP_K))
         if language_filter and language_filter not in _ALLOWED_LANGUAGES:
@@ -99,6 +100,8 @@ class GraphOrchestrator(OrchestratorBase):
                 raise ValueError("private codebase search requires valid user_id")
         elif user_id is not None and not _SAFE_ID_RE.match(user_id):
             raise ValueError("Invalid user_id format")
+        if aspect and aspect not in ("code_intent", "nl_intent"):
+            raise ValueError(f"Invalid aspect '{aspect}'")
 
         query = query.strip()
         if not query:
@@ -135,6 +138,17 @@ class GraphOrchestrator(OrchestratorBase):
             lang_clause = f"AND language = ${next_i}" if language_filter else ""
             if language_filter:
                 query_params.append(language_filter)
+                next_i += 1
+
+            embedding_col = "ea.embedding" if aspect else "m.embedding"
+            aspect_join = (
+                f"JOIN embedding_aspects ea ON m.id = ea.memory_id AND ea.aspect = ${next_i}"
+                if aspect
+                else ""
+            )
+            if aspect:
+                query_params.append(aspect)
+                next_i += 1
 
             # NOTE: scope_clause and lang_clause inject ONLY hardcoded string literals
             # or parameterized placeholders ($N). No user-controlled values are
@@ -143,10 +157,11 @@ class GraphOrchestrator(OrchestratorBase):
             # Explicit namespace_id filter added as defense-in-depth (Fix 2B).
             sql = f"""
                 WITH vector_candidates AS (
-                    SELECT id, embedding <=> $1::vector AS distance
-                    FROM memories
-                    WHERE memory_type = 'code_chunk'
-                      AND namespace_id = current_setting('nce.namespace_id')::uuid
+                    SELECT m.id, {embedding_col} <=> $1::vector AS distance
+                    FROM memories m
+                    {aspect_join}
+                    WHERE m.memory_type = 'code_chunk'
+                      AND m.namespace_id = current_setting('nce.namespace_id')::uuid
                       {scope_clause} {lang_clause}
                     ORDER BY distance ASC
                     LIMIT $2
@@ -234,9 +249,14 @@ class GraphOrchestrator(OrchestratorBase):
                         meta = dict(raw)
                 name = row["name"] or meta.get("name") or row["filepath"]
                 node_type = row["node_type"] or meta.get("node_type") or "chunk"
-                start_line = row["start_line"] if row["start_line"] is not None else meta.get("start_line", 0)
-                end_line = row["end_line"] if row["end_line"] is not None else meta.get("end_line", 0)
-
+                start_line = (
+                    row["start_line"]
+                    if row["start_line"] is not None
+                    else meta.get("start_line", 0)
+                )
+                end_line = (
+                    row["end_line"] if row["end_line"] is not None else meta.get("end_line", 0)
+                )
 
                 ref_key = normalize_payload_ref(row["payload_ref"])
                 raw_code = code_docs.get(ref_key, "") if ref_key else ""
diff --git a/nce/reembedding_migration.py b/nce/reembedding_migration.py
index d2563fd..e97a035 100644
--- a/nce/reembedding_migration.py
+++ b/nce/reembedding_migration.py
@@ -13,6 +13,7 @@ from __future__ import annotations
 
 import asyncio
 import hashlib
+import json
 import logging
 import math
 import sys
@@ -23,7 +24,7 @@ if sys.version_info >= (3, 11):
     from enum import StrEnum
 else:
     from strenum import StrEnum  # type: ignore[import-untyped]
-from typing import Protocol
+from typing import Any, Protocol
 
 log = logging.getLogger("nce-reembedding-migration")
 
@@ -382,3 +383,116 @@ _EMBED_MAX_CONCURRENT: int = 8
 _EMBED_TIMEOUT_SECONDS: float = 30.0
 _MAX_CANONICAL_TEXT_BYTES: int = 32_768
 _EMBED_MAX_RETRIES: int = 3
+
+
+class PostgresAspectReembeddingStore:
+    """Postgres aspect store implementing ReembeddingStorePort for aspect backfilling."""
+
+    def __init__(
+        self,
+        pool: Any,
+        aspect: str,
+        mongo_client: Any = None,
+    ) -> None:
+        self.pool = pool
+        self.aspect = aspect
+        self.mongo_client = mongo_client
+
+    async def pop_pending_ids(self, limit: int) -> list[str]:
+        """Fetch code_chunk memories that do not have the target aspect in embedding_aspects."""
+        async with self.pool.acquire() as conn:
+            rows = await conn.fetch(
+                """
+                SELECT m.id::text
+                FROM memories m
+                LEFT JOIN embedding_aspects ea ON m.id = ea.memory_id AND ea.aspect = $1
+                WHERE m.memory_type = 'code_chunk'
+                  AND ea.memory_id IS NULL
+                LIMIT $2
+                """,
+                self.aspect,
+                limit,
+            )
+            return [str(r["id"]) for r in rows]
+
+    async def load_row(self, memory_id: str) -> MemoryEmbeddingRow | None:
+        """Load code_chunk memory and resolve canonical text based on aspect type."""
+        async with self.pool.acquire() as conn:
+            row = await conn.fetchrow(
+                """
+                SELECT id, payload_ref, name, filepath, embedding::vector as embedding_vector, namespace_id
+                FROM memories
+                WHERE id = $1::uuid
+                """,
+                memory_id,
+            )
+            if not row:
+                return None
+
+            raw_emb = row["embedding_vector"]
+            embedding_v1: list[float] = []
+            if isinstance(raw_emb, str):
+                embedding_v1 = [float(x) for x in raw_emb.strip("[]").split(",") if x.strip()]
+            elif isinstance(raw_emb, list):
+                embedding_v1 = [float(x) for x in raw_emb]
+            elif raw_emb is not None:
+                embedding_v1 = [float(x) for x in str(raw_emb).strip("[]").split(",") if x.strip()]
+
+            canonical_text = ""
+            if self.aspect == "nl_intent":
+                canonical_text = row["name"] or ""
+            elif self.aspect == "code_intent":
+                ref = row["payload_ref"]
+                ns_id = row["namespace_id"]
+                if ref and len(ref) == 24 and ns_id and self.mongo_client is not None:
+                    from bson import ObjectId
+                    from nce.db_utils import scoped_mongo_session
+                    try:
+                        async with scoped_mongo_session(self.mongo_client, ns_id) as s_db:
+                            doc = await s_db.code_files.find_one({"_id": ObjectId(ref)}, {"raw_code": 1})
+                            if doc:
+                                canonical_text = doc.get("raw_code", "")
+                    except Exception as exc:
+                        log.warning("Aspect backfill: MongoDB query failed for %s: %s", memory_id, exc)
+
+                if not canonical_text:
+                    canonical_text = row["filepath"] or ""
+
+            return MemoryEmbeddingRow(
+                memory_id=memory_id,
+                canonical_text=canonical_text,
+                embedding_v1=embedding_v1,
+            )
+
+    async def write_embedding_v2(
+        self,
+        memory_id: str,
+        *,
+        embedding: Sequence[float],
+        model_id: str,
+    ) -> None:
+        """Write the aspect embedding to embedding_aspects companion table."""
+        async with self.pool.acquire() as conn:
+            namespace_id = await conn.fetchval(
+                "SELECT namespace_id FROM memories WHERE id = $1::uuid",
+                memory_id,
+            )
+            from nce.db_utils import scoped_pg_session, unmanaged_pg_connection
+            async with (
+                scoped_pg_session(self.pool, str(namespace_id))
+                if namespace_id
+                else unmanaged_pg_connection(self.pool, site="reembedding.aspects.backfill")
+            ) as session_conn:
+                await session_conn.execute(
+                    """
+                    INSERT INTO embedding_aspects (memory_id, aspect, embedding, namespace_id)
+                    VALUES ($1::uuid, $2, $3::vector, $4::uuid)
+                    ON CONFLICT (memory_id, aspect)
+                    DO UPDATE SET embedding = $3::vector
+                    """,
+                    memory_id,
+                    self.aspect,
+                    json.dumps(list(embedding)),
+                    namespace_id,
+                )
+
diff --git a/nce/schema.sql b/nce/schema.sql
index a6a2006..e392d40 100644
--- a/nce/schema.sql
+++ b/nce/schema.sql
@@ -453,6 +453,24 @@ CREATE TABLE IF NOT EXISTS memory_embeddings_3 PARTITION OF memory_embeddings FO
 -- Index for validate_migration emb_count query and model-scoped lookups
 CREATE INDEX IF NOT EXISTS idx_memory_embeddings_model_id ON memory_embeddings(model_id);
 
+CREATE TABLE IF NOT EXISTS embedding_aspects (
+    memory_id    UUID NOT NULL,
+    aspect       VARCHAR(64) NOT NULL,
+    embedding    halfvec(768),
+    namespace_id UUID REFERENCES namespaces(id),
+    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
+    PRIMARY KEY (memory_id, aspect)
+) PARTITION BY HASH (memory_id);
+
+CREATE TABLE IF NOT EXISTS embedding_aspects_0 PARTITION OF embedding_aspects FOR VALUES WITH (MODULUS 4, REMAINDER 0);
+CREATE TABLE IF NOT EXISTS embedding_aspects_1 PARTITION OF embedding_aspects FOR VALUES WITH (MODULUS 4, REMAINDER 1);
+CREATE TABLE IF NOT EXISTS embedding_aspects_2 PARTITION OF embedding_aspects FOR VALUES WITH (MODULUS 4, REMAINDER 2);
+CREATE TABLE IF NOT EXISTS embedding_aspects_3 PARTITION OF embedding_aspects FOR VALUES WITH (MODULUS 4, REMAINDER 3);
+
+CREATE INDEX IF NOT EXISTS idx_embedding_aspects_hnsw ON embedding_aspects USING hnsw (embedding halfvec_cosine_ops);
+CREATE INDEX IF NOT EXISTS idx_embedding_aspects_namespace_id ON embedding_aspects (namespace_id);
+
+
 CREATE TABLE IF NOT EXISTS kg_node_embeddings (
     node_id    UUID NOT NULL,
     model_id   UUID NOT NULL REFERENCES embedding_models(id),
@@ -1185,6 +1203,7 @@ DECLARE
         'dead_letter_queue',
         'embedding_migrations',
         'memory_embeddings',
+        'embedding_aspects',
         'active_learning_queue',
         'd365_integrations',
         'd365_netbox_mappings'
diff --git a/nce/tasks.py b/nce/tasks.py
index c85cf5e..50d9206 100644
--- a/nce/tasks.py
+++ b/nce/tasks.py
@@ -258,8 +258,17 @@ def process_code_indexing(
                 chunk_vault_entries.append(pii_res.vault_entries)
                 chunk_redacted.append(pii_res.redacted)
 
-            texts = [f"{c.name}\n{sc}" for c, sc in zip(chunks, sanitized_chunks_code)]
-            vectors = await _embeddings.embed_batch(texts)
+            primary_texts = [f"{c.name}\n{sc}" for c, sc in zip(chunks, sanitized_chunks_code)]
+            code_texts = [sc for sc in sanitized_chunks_code]
+            nl_texts = [c.name for c in chunks]
+
+            all_texts = primary_texts + code_texts + nl_texts
+            all_vectors = await _embeddings.embed_batch(all_texts)
+
+            n_chunks = len(chunks)
+            primary_vectors = all_vectors[:n_chunks]
+            code_vectors = all_vectors[n_chunks : 2 * n_chunks]
+            nl_vectors = all_vectors[2 * n_chunks :]
 
             # Use scoped session for RLS if namespace_id is provided
             async with (
@@ -287,8 +296,14 @@ def process_code_indexing(
                     ):
                         metadata["degraded_embedding"] = True
 
-                    for chunk, sc, vector, vault, redacted in zip(
-                        chunks, sanitized_chunks_code, vectors, chunk_vault_entries, chunk_redacted
+                    for i, (chunk, sc, vector, vault, redacted) in enumerate(
+                        zip(
+                            chunks,
+                            sanitized_chunks_code,
+                            primary_vectors,
+                            chunk_vault_entries,
+                            chunk_redacted,
+                        )
                     ):
                         memory_id = uuid.uuid4()
                         await conn.execute(
@@ -316,6 +331,26 @@ def process_code_indexing(
                             json.dumps(metadata),
                             redacted,
                         )
+                        # Store code_intent aspect embedding
+                        await conn.execute(
+                            """
+                            INSERT INTO embedding_aspects (memory_id, aspect, embedding, namespace_id)
+                            VALUES ($1::uuid, 'code_intent', $2::vector, $3::uuid)
+                            """,
+                            str(memory_id),
+                            json.dumps(code_vectors[i]),
+                            ns_uuid,
+                        )
+                        # Store nl_intent aspect embedding
+                        await conn.execute(
+                            """
+                            INSERT INTO embedding_aspects (memory_id, aspect, embedding, namespace_id)
+                            VALUES ($1::uuid, 'nl_intent', $2::vector, $3::uuid)
+                            """,
+                            str(memory_id),
+                            json.dumps(nl_vectors[i]),
+                            ns_uuid,
+                        )
                         if vault and ns_uuid:
                             await conn.executemany(
                                 """
```
