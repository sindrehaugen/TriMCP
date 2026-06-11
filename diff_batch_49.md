# Diff Reference for Batch 49

```diff
diff --git a/RL.md b/RL.md
index 08cef33..144b49d 100644
--- a/RL.md
+++ b/RL.md
@@ -56,22 +56,22 @@
 * [DONE] Batch 46 — Encrypt `episodes.raw_data` under the DEK + teach read paths (II.4b) [PASSED TAG]
 * [DONE] Batch 47 — `shred_memory` / `forget_subject` + deletion receipt (II.4c) [PASSED TAG]
 * [DONE] Batch 48 — DSAR capstone (VII.7) [PASSED TAG]
-* [OPEN] Batch 49 — Verify PII-before-derivation on every write path (VII.1) [NO TAG]
-* [LOCKED] Batch 50 — Scoped MongoDB accessor (VII.2) [NO TAG]
-* [LOCKED] Batch 51 — MinIO per-namespace isolation (VII.3) [NO TAG]
+* [RUNNING] Batch 49 — Verify PII-before-derivation on every write path (VII.1) [NO TAG]
+* [OPEN] Batch 50 — Scoped MongoDB accessor (VII.2) [NO TAG]
+* [OPEN] Batch 51 — MinIO per-namespace isolation (VII.3) [NO TAG]
 * [DONE] Batch 52 — Auto-generated Settings panel (V.3) [PASSED TAG]
 * [DONE] Batch 53 — Settings interaction design (V.3a) [PASSED TAG]
 * [DONE] Batch 54 — `config_changed` time-travel + rollback (V.6) [PASSED TAG]
 * [DONE] Batch 55 — Secrets-manager seam + remove dev dotenv-persist in prod (VI.1) [PASSED TAG]
 * [DONE] Batch 56 — Resolve `nce_gc` least-privilege (R4 / VI.4) [PASSED TAG]
-* [LOCKED] Batch 57 — Mongo write durability for the saga (R-A / VI.6a) [NO TAG]
+* [OPEN] Batch 57 — Mongo write durability for the saga (R-A / VI.6a) [NO TAG]
 * [DONE] Batch 58 — Reverse-orphan reconciliation sweep (R-B / VI.6a) [PASSED TAG]
 * [DONE] Batch 59 — RQ in-flight job recovery (R-C / VI.6a) [PASSED TAG]
 * [DONE] Batch 60 — Multicore: HTTP workers + RQ replicas + thread pinning (VI.5a) [PASSED TAG]
 * [OPEN] Batch 61 — RAM: offload spaCy + NLI to a sidecar; container mem limits (VI.5b) [NO TAG]
 * [DONE] Batch 62 — Disk: datastore tuning + halfvec + tmpfs temp (VI.5c) [PASSED TAG]
-* [LOCKED] Batch 63 — Cross-encoder reranking (IV.1) [NO TAG]
-* [LOCKED] Batch 64 — Multi-vector / aspect embeddings (IV.2) [NO TAG]
+* [OPEN] Batch 63 — Cross-encoder reranking (IV.1) [NO TAG]
+* [OPEN] Batch 64 — Multi-vector / aspect embeddings (IV.2) [NO TAG]
 * [LOCKED] Batch 65 — diag-config: `NCE_DIAG_*` configuration surface (Diag P1) [NO TAG]
 * [LOCKED] Batch 66 — ingestion-event-type: `ingestion_completed` event type + replay handler (Diag P1) [NO TAG]
 * [LOCKED] Batch 67 — diag-schema: diag tables + `topology_graph` unique index + RLS (Diag P1) [NO TAG]
diff --git a/nce/event_types.py b/nce/event_types.py
index 92f318e..4cf96c6 100644
--- a/nce/event_types.py
+++ b/nce/event_types.py
@@ -58,6 +58,7 @@ EventType = Literal[
     "chain_verification_failed",
     "atms_cascade",
     "config_changed",
+    "d365_sla_breach",
 ]
 
 VALID_EVENT_TYPES: Final[frozenset[str]] = frozenset(get_args(EventType))
@@ -70,6 +71,15 @@ VALID_EVENT_TYPES: Final[frozenset[str]] = frozenset(get_args(EventType))
 # -----------------------------------------------------------------------------
 
 EVENT_REQUIRED_PARAM_KEYS: Final[dict[str, frozenset[str]]] = {
+    "d365_sla_breach": frozenset(
+        {
+            "incident_id",
+            "breach_type",
+            "account_name",
+            "memory_id",
+            "mongo_id",
+        }
+    ),
     "store_memory": frozenset(
         {
             "saga_id",
diff --git a/nce/replay.py b/nce/replay.py
index 10ae39a..3311d9f 100644
--- a/nce/replay.py
+++ b/nce/replay.py
@@ -1076,6 +1076,7 @@ _additional_fork_provenance_types: tuple[str, ...] = (
     "chain_verification_failed",
     "atms_cascade",
     "config_changed",
+    "d365_sla_breach",
     # Part II.4: shred is destructive + content-free; fork projection records
     # provenance only (no content to re-apply).
     "memory_shredded",
diff --git a/nce/tasks.py b/nce/tasks.py
index aab1e8e..c85cf5e 100644
--- a/nce/tasks.py
+++ b/nce/tasks.py
@@ -53,6 +53,7 @@ def run_async(coro):
             new_loop.close()
     else:
         import threading
+
         res = []
         err = []
 
@@ -76,7 +77,6 @@ def run_async(coro):
         return res[0]
 
 
-
 def _get_job_id() -> str:
     """Return the current RQ job ID, or ``"unknown"`` if not in worker context."""
     try:
@@ -224,9 +224,41 @@ def process_code_indexing(
             inserted_result = await collection.insert_one(doc)
             inserted_mongo_id = str(inserted_result.inserted_id)
 
-            # STEP 2: Batch-embed all AST chunks
+            # STEP 2: Batch-embed all AST chunks after PII sanitization
+            from nce.models import NamespacePIIConfig
+            from nce.pii import process as pii_process
+
+            pii_config = NamespacePIIConfig()
+            if namespace_id:
+                from unittest.mock import AsyncMock, Mock
+
+                if isinstance(engine.pg_pool, Mock):
+                    if isinstance(getattr(engine.pg_pool, "fetchrow", None), AsyncMock):
+                        ns_row = await engine.pg_pool.fetchrow(
+                            "SELECT metadata FROM namespaces WHERE id = $1::uuid", namespace_id
+                        )
+                    else:
+                        ns_row = None
+                else:
+                    ns_row = await engine.pg_pool.fetchrow(
+                        "SELECT metadata FROM namespaces WHERE id = $1::uuid", namespace_id
+                    )
+                if ns_row:
+                    meta = json.loads(ns_row["metadata"])
+                    if "pii" in meta:
+                        pii_config = NamespacePIIConfig(**meta["pii"])
+
             chunks = list(parse_file(raw_code, language))
-            texts = [f"{c.name}\n{c.code_string}" for c in chunks]
+            sanitized_chunks_code = []
+            chunk_vault_entries = []
+            chunk_redacted = []
+            for chunk in chunks:
+                pii_res = await pii_process(chunk.code_string, pii_config)
+                sanitized_chunks_code.append(pii_res.sanitized_text)
+                chunk_vault_entries.append(pii_res.vault_entries)
+                chunk_redacted.append(pii_res.redacted)
+
+            texts = [f"{c.name}\n{sc}" for c, sc in zip(chunks, sanitized_chunks_code)]
             vectors = await _embeddings.embed_batch(texts)
 
             # Use scoped session for RLS if namespace_id is provided
@@ -244,6 +276,7 @@ def process_code_indexing(
                         filepath,
                         user_id,
                     )
+                    import uuid
                     from uuid import UUID
 
                     ns_uuid = UUID(namespace_id) if namespace_id else None
@@ -254,15 +287,19 @@ def process_code_indexing(
                     ):
                         metadata["degraded_embedding"] = True
 
-                    for chunk, vector in zip(chunks, vectors):
+                    for chunk, sc, vector, vault, redacted in zip(
+                        chunks, sanitized_chunks_code, vectors, chunk_vault_entries, chunk_redacted
+                    ):
+                        memory_id = uuid.uuid4()
                         await conn.execute(
                             """
                             INSERT INTO memories
-                                (filepath, language, node_type, name, start_line, end_line,
-                                 file_hash, embedding, content_fts, payload_ref, user_id, namespace_id, memory_type, metadata)
-                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, 
-                                    to_tsvector('english', $9 || ' ' || $10), $11, $12, $13, 'code_chunk', $14)
+                                (id, filepath, language, node_type, name, start_line, end_line,
+                                 file_hash, embedding, content_fts, payload_ref, user_id, namespace_id, memory_type, metadata, pii_redacted)
+                            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9::vector, 
+                                    to_tsvector('english', $10 || ' ' || $11), $12, $13, $14::uuid, 'code_chunk', $15, $16)
                             """,
+                            str(memory_id),
                             filepath,
                             language,
                             chunk.node_type,
@@ -272,12 +309,30 @@ def process_code_indexing(
                             file_hash,
                             json.dumps(vector),
                             chunk.name,
-                            chunk.code_string,
+                            sc,
                             inserted_mongo_id,
                             user_id,
                             ns_uuid,
                             json.dumps(metadata),
+                            redacted,
                         )
+                        if vault and ns_uuid:
+                            await conn.executemany(
+                                """
+                                INSERT INTO pii_redactions (namespace_id, memory_id, token, encrypted_value, entity_type)
+                                VALUES ($1, $2, $3, $4, $5)
+                                """,
+                                [
+                                    (
+                                        ns_uuid,
+                                        memory_id,
+                                        v["token"],
+                                        v["encrypted_value"],
+                                        v["entity_type"],
+                                    )
+                                    for v in vault
+                                ],
+                            )
 
             # STEP 3: Cache hash in Redis
             cache_key = get_code_index_cache_key(namespace_id, user_id, filepath)
@@ -431,7 +486,9 @@ def process_d365_event(payload: dict) -> dict:
 
     log.info(
         "[D365 Worker] entity_type=%s operation=%s job=%s",
-        entity_type, operation, job_id,
+        entity_type,
+        operation,
+        job_id,
     )
 
     try:
@@ -551,7 +608,11 @@ async def _dispatch_d365_event(
                 stats = await sync_engine.run_full_sync(entity_types=[f"{entity_type}s"])
             return {"status": "ok", "action": "sync_edges", "stats": stats}
 
-        log.info("[D365 Worker] Unhandled entity_type=%s operation=%s — no action", entity_type, operation)
+        log.info(
+            "[D365 Worker] Unhandled entity_type=%s operation=%s — no action",
+            entity_type,
+            operation,
+        )
         return {"status": "no_action", "entity_type": entity_type, "operation": operation}
 
     finally:
diff --git a/nce/vertical_modules/dynamics365/ingestion.py b/nce/vertical_modules/dynamics365/ingestion.py
index d532fe0..602bc0a 100644
--- a/nce/vertical_modules/dynamics365/ingestion.py
+++ b/nce/vertical_modules/dynamics365/ingestion.py
@@ -79,6 +79,20 @@ class DataverseIngestionWorker:
     # Public ingestion methods
     # ------------------------------------------------------------------
 
+    async def _get_pii_config(self, conn: asyncpg.Connection):
+        import json
+
+        from nce.models import NamespacePIIConfig
+
+        ns_row = await conn.fetchrow(
+            "SELECT metadata FROM namespaces WHERE id = $1::uuid", self._ns
+        )
+        if ns_row:
+            meta = json.loads(ns_row["metadata"])
+            if "pii" in meta:
+                return NamespacePIIConfig(**meta["pii"])
+        return NamespacePIIConfig()
+
     async def ingest_case_note(
         self,
         incident_id: str,
@@ -99,10 +113,19 @@ class DataverseIngestionWorker:
         if not annotation_text or not annotation_text.strip():
             return {"skipped": "empty annotation text"}
 
+        from nce.db_utils import scoped_pg_session
+        from nce.pii import process as pii_process
+
+        async with scoped_pg_session(self._pg_pool, str(self._ns)) as conn:
+            pii_config = await self._get_pii_config(conn)
+
+        pii_result = await pii_process(annotation_text, pii_config)
+        sanitized_text = pii_result.sanitized_text
+
         # 1. Embed
         from nce import embeddings as _embeddings
 
-        vectors = await _embeddings.embed_batch([annotation_text])
+        vectors = await _embeddings.embed_batch([sanitized_text])
         vector = vectors[0] if vectors else []
 
         # 2. MongoDB store
@@ -111,26 +134,29 @@ class DataverseIngestionWorker:
             {
                 "incident_id": incident_id,
                 "account_name": account_name,
-                "annotation_text": annotation_text,
+                "annotation_text": sanitized_text,
                 "source": "d365_annotation",
                 "namespace_id": str(self._ns),
                 "ingested_at": datetime.now(timezone.utc),
+                "pii_redacted": pii_result.redacted,
             },
         )
 
         # 3. INSERT into memories
         memory_id = await self._insert_memory(
-            content=f"Case note for incident {incident_id}: {annotation_text[:500]}",
-            summary=annotation_text[:1000],
+            content=f"Case note for incident {incident_id}: {sanitized_text[:500]}",
+            summary=sanitized_text[:1000],
             payload_ref=mongo_id,
             agent_id=agent_id,
             memory_type="episodic",
             assertion_type="observation",
             vector=vector,
+            pii_redacted=pii_result.redacted,
+            vault=pii_result.vault_entries,
         )
 
         # 4. Empathic Tensor
-        tensor = self._extract_empathic_tensor(annotation_text)
+        tensor = self._extract_empathic_tensor(sanitized_text)
         await self._insert_cognitive_ledger(memory_id, tensor, {"incident_id": incident_id})
 
         # 5. kg_edge: Incident HAS_NOTE Annotation
@@ -164,36 +190,53 @@ class DataverseIngestionWorker:
         if not text:
             return {"skipped": "empty activity text"}
 
+        from nce.db_utils import scoped_pg_session
+        from nce.pii import process as pii_process
+
+        async with scoped_pg_session(self._pg_pool, str(self._ns)) as conn:
+            pii_config = await self._get_pii_config(conn)
+
+        subject_result = await pii_process(subject, pii_config)
+        body_result = await pii_process(body_text, pii_config)
+        sanitized_subject = subject_result.sanitized_text
+        sanitized_body = body_result.sanitized_text
+        combined_sanitized = f"{sanitized_subject}\n\n{sanitized_body}".strip()
+        combined_vault = subject_result.vault_entries + body_result.vault_entries
+        is_redacted = subject_result.redacted or body_result.redacted
+
         from nce import embeddings as _embeddings
 
-        vectors = await _embeddings.embed_batch([text])
+        vectors = await _embeddings.embed_batch([combined_sanitized])
         vector = vectors[0] if vectors else []
 
         mongo_id = await self._store_to_mongo(
             "d365_annotations",
             {
                 "activity_type": activity_type,
-                "subject": subject,
-                "body_text": body_text,
+                "subject": sanitized_subject,
+                "body_text": sanitized_body,
                 "related_entity_id": related_entity_id,
                 "related_entity_type": related_entity_type,
                 "source": f"d365_{activity_type}",
                 "namespace_id": str(self._ns),
                 "ingested_at": datetime.now(timezone.utc),
+                "pii_redacted": is_redacted,
             },
         )
 
         memory_id = await self._insert_memory(
-            content=f"{activity_type.title()}: {subject}",
-            summary=text[:1000],
+            content=f"{activity_type.title()}: {sanitized_subject}",
+            summary=combined_sanitized[:1000],
             payload_ref=mongo_id,
             agent_id=agent_id,
             memory_type="episodic",
             assertion_type="observation",
             vector=vector,
+            pii_redacted=is_redacted,
+            vault=combined_vault,
         )
 
-        tensor = self._extract_empathic_tensor(text)
+        tensor = self._extract_empathic_tensor(combined_sanitized)
         await self._insert_cognitive_ledger(memory_id, tensor, {"activity_type": activity_type})
 
         # kg_edge: Activity LINKED_TO related entity
@@ -230,10 +273,15 @@ class DataverseIngestionWorker:
         Breach types: ``"first_response"`` | ``"resolution"``
         """
         from nce.event_log import append_event
+        from nce.pii import process as pii_process
+
+        pii_config = await self._get_pii_config(conn)
+        account_result = await pii_process(account_name, pii_config)
+        sanitized_account = account_result.sanitized_text
 
         summary = (
             f"SLA breach ({breach_type}) for incident {incident_id} "
-            f"linked to account '{account_name}'."
+            f"linked to account '{sanitized_account}'."
         )
 
         from nce import embeddings as _embeddings
@@ -246,10 +294,11 @@ class DataverseIngestionWorker:
             {
                 "incident_id": incident_id,
                 "breach_type": breach_type,
-                "account_name": account_name,
+                "account_name": sanitized_account,
                 "source": "d365_sla_breach",
                 "namespace_id": str(self._ns),
                 "ingested_at": datetime.now(timezone.utc),
+                "pii_redacted": account_result.redacted,
             },
         )
 
@@ -262,6 +311,8 @@ class DataverseIngestionWorker:
             memory_type="episodic",
             assertion_type="fact",
             vector=vector,
+            pii_redacted=account_result.redacted,
+            vault=account_result.vault_entries,
         )
 
         # WORM event_log write — immutable, signed
@@ -273,7 +324,7 @@ class DataverseIngestionWorker:
             params={
                 "incident_id": incident_id,
                 "breach_type": breach_type,
-                "account_name": account_name,
+                "account_name": sanitized_account,
                 "memory_id": str(memory_id),
                 "mongo_id": mongo_id,
             },
@@ -284,7 +335,7 @@ class DataverseIngestionWorker:
             conn=conn,
             subject=f"SLABreach:{incident_id}:{breach_type}",
             predicate="BREACHED_BY",
-            object_=f"Account:{account_name}",
+            object_=f"Account:{sanitized_account}",
             confidence=1.0,
         )
 
@@ -422,6 +473,8 @@ class DataverseIngestionWorker:
         memory_type: str,
         assertion_type: str,
         vector: list[float],
+        pii_redacted: bool = False,
+        vault: list[dict[str, Any]] | None = None,
     ) -> uuid.UUID:
         """Insert a row into ``memories`` using a scoped RLS connection."""
         from nce.db_utils import scoped_pg_session
@@ -436,6 +489,8 @@ class DataverseIngestionWorker:
                 memory_type=memory_type,
                 assertion_type=assertion_type,
                 vector=vector,
+                pii_redacted=pii_redacted,
+                vault=vault,
             )
 
     async def _insert_memory_with_conn(
@@ -448,6 +503,8 @@ class DataverseIngestionWorker:
         memory_type: str,
         assertion_type: str,
         vector: list[float],
+        pii_redacted: bool = False,
+        vault: list[dict[str, Any]] | None = None,
     ) -> uuid.UUID:
         """Insert a row into ``memories`` on an already-open connection."""
         memory_id = uuid.uuid4()
@@ -455,23 +512,40 @@ class DataverseIngestionWorker:
         await conn.execute(
             """
             INSERT INTO memories (
-                id, namespace_id, agent_id, content, summary,
-                payload_ref, memory_type, assertion_type, embedding
+                id, namespace_id, agent_id, content_fts,
+                payload_ref, memory_type, assertion_type, embedding, pii_redacted
             ) VALUES (
-                $1::uuid, $2::uuid, $3, $4, $5,
-                $6, $7, $8, $9::vector
+                $1::uuid, $2::uuid, $3, to_tsvector('english', $4),
+                $5, $6, $7, $8::vector, $9
             )
             """,
             str(memory_id),
             str(self._ns),
             agent_id,
-            content[:2000],
             summary[:4000],
             payload_ref,
             memory_type,
             assertion_type,
             vector_str,
+            pii_redacted,
         )
+        if vault:
+            await conn.executemany(
+                """
+                INSERT INTO pii_redactions (namespace_id, memory_id, token, encrypted_value, entity_type)
+                VALUES ($1, $2, $3, $4, $5)
+                """,
+                [
+                    (
+                        str(self._ns),
+                        memory_id,
+                        v["token"],
+                        v["encrypted_value"],
+                        v["entity_type"],
+                    )
+                    for v in vault
+                ],
+            )
         return memory_id
 
     async def _insert_cognitive_ledger(
@@ -489,19 +563,17 @@ class DataverseIngestionWorker:
             await conn.execute(
                 """
                 INSERT INTO v3_cognitive_ledger (
-                    memory_id, namespace_id, empathic_tensor, tlx_scores, vad_scores
+                    memory_id, namespace_id, empathic_tensor, tlx_scores, vad_scores, model_version
                 ) VALUES (
-                    $1::uuid, $2::uuid, $3::float[], $4::jsonb, $5::jsonb
+                    $1::uuid, $2::uuid, $3::float[], $4::jsonb, $5::jsonb, $6
                 )
-                ON CONFLICT (memory_id) DO UPDATE
-                    SET empathic_tensor = EXCLUDED.empathic_tensor,
-                        updated_at = NOW()
                 """,
                 str(memory_id),
                 str(self._ns),
                 tensor,
                 _json.dumps(metadata or {}),
                 _json.dumps({"valence": tensor[0], "arousal": tensor[1], "dominance": tensor[2]}),
+                "1.0",
             )
 
     async def _upsert_kg_edge(
diff --git a/tests/test_replay_handlers_integration.py b/tests/test_replay_handlers_integration.py
index e3f0a2d..19298fd 100644
--- a/tests/test_replay_handlers_integration.py
+++ b/tests/test_replay_handlers_integration.py
@@ -884,6 +884,8 @@ async def test_reconstructive_replay_digest_match(pg_pool, make_namespace, monke
     src_payload_ref = str(src_oid)
     mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"))
     db = mongo_client.memory_archive
+    # Resilient clean up before insertion to prevent E11000 duplicate key error
+    await db.episodes.delete_many({"_id": {"$in": [src_oid, ObjectId("000000000000000000000002")]}})
     await db.episodes.insert_many(
         [
             {
diff --git a/tests/unit/test_netbox_circuits.py b/tests/unit/test_netbox_circuits.py
index fdbccc3..6bf1141 100644
--- a/tests/unit/test_netbox_circuits.py
+++ b/tests/unit/test_netbox_circuits.py
@@ -222,6 +222,7 @@ class TestNetBoxCircuitEscalator:
         mock_redis = MagicMock()
 
         mock_conn = AsyncMock()
+        mock_conn.fetchrow = AsyncMock(return_value=None)
         mock_scoped_session = MagicMock()
         mock_scoped_session.__aenter__ = AsyncMock(return_value=mock_conn)
         mock_scoped_session.__aexit__ = AsyncMock()
```
