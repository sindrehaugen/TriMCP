# Diff Reference for Batch 50

```diff
diff --git a/RL.md b/RL.md
index a72745f..ed782fd 100644
--- a/RL.md
+++ b/RL.md
@@ -57,7 +57,7 @@
 * [DONE] Batch 47 — `shred_memory` / `forget_subject` + deletion receipt (II.4c) [PASSED TAG]
 * [DONE] Batch 48 — DSAR capstone (VII.7) [PASSED TAG]
 * [DONE] Batch 49 — Verify PII-before-derivation on every write path (VII.1) [PASSED TAG]
-* [OPEN] Batch 50 — Scoped MongoDB accessor (VII.2) [NO TAG]
+* [RUNNING] Batch 50 — Scoped MongoDB accessor (VII.2) [WAITING TAG]
 * [OPEN] Batch 51 — MinIO per-namespace isolation (VII.3) [NO TAG]
 * [DONE] Batch 52 — Auto-generated Settings panel (V.3) [PASSED TAG]
 * [DONE] Batch 53 — Settings interaction design (V.3a) [PASSED TAG]
diff --git a/nce/consolidation.py b/nce/consolidation.py
index 228bbcd..962ed97 100644
--- a/nce/consolidation.py
+++ b/nce/consolidation.py
@@ -111,7 +111,6 @@ class ConsolidationWorker:
         import numpy as np
         from sklearn.cluster import HDBSCAN
 
-
         valid_memories = []
         embeddings = []
         expected_dim = None
@@ -161,13 +160,17 @@ class ConsolidationWorker:
 
         return valid_memories, clusters
 
-    async def _build_cluster_llm_documents(self, cluster_mems: list) -> list[dict]:
+    async def _build_cluster_llm_documents(
+        self, cluster_mems: list, namespace_id: UUID
+    ) -> list[dict]:
         """Resolve Mongo episode bodies in one ``$in`` query; fallback without Mongo."""
         refs = [m["payload_ref"] for m in cluster_mems]
         by_ref: dict[str, str] = {}
         if self.mongo_client is not None and refs:
-            db = self.mongo_client.memory_archive
-            by_ref = await fetch_episodes_raw_by_ref(db, refs)
+            from nce.db_utils import scoped_mongo_session
+
+            async with scoped_mongo_session(self.mongo_client, namespace_id) as s_db:
+                by_ref = await fetch_episodes_raw_by_ref(s_db, refs)
 
         docs: list[dict] = []
         for m in cluster_mems:
@@ -190,9 +193,10 @@ class ConsolidationWorker:
         cluster_mems: list,
         mem_ids: list,
         label: int,
+        namespace_id: UUID,
     ) -> ConsolidatedAbstraction | None:
         """Call LLM, validate abstraction, return None on any failure."""
-        llm_documents = await self._build_cluster_llm_documents(cluster_mems)
+        llm_documents = await self._build_cluster_llm_documents(cluster_mems, namespace_id)
         messages = _build_consolidation_messages(json.dumps(llm_documents))
 
         try:
@@ -232,11 +236,8 @@ class ConsolidationWorker:
 
         return abstraction
 
-    async def _store_abstraction_in_mongo(self, abstraction_text: str) -> str:
-        """Persist abstraction text to Mongo and return its ObjectId string.
-
-        This gives us a valid ObjectId to use as payload_ref in the memories
-        table, satisfying the ObjectId format constraint (FIX: P0.2).
+    async def _store_abstraction_in_mongo(self, namespace_id: UUID, abstraction_text: str) -> str:
+        """Store consolidated abstraction in MongoDB and return the payload_ref.
 
         When mongo_client is None (e.g. test environments or Mongo-less deployments),
         falls back to a UUID-based ref prefixed with ``nomongo/`` so the caller can
@@ -252,12 +253,13 @@ class ConsolidationWorker:
                 fallback_ref,
             )
             return fallback_ref
-        db = self.mongo_client.memory_archive
-        result = await db.episodes.insert_one(
-            {"raw_data": abstraction_text, "source": "consolidation"}
-        )
-        return str(result.inserted_id)
+        from nce.db_utils import scoped_mongo_session
 
+        async with scoped_mongo_session(self.mongo_client, namespace_id) as s_db:
+            result = await s_db.episodes.insert_one(
+                {"raw_data": abstraction_text, "source": "consolidation"}
+            )
+            return str(result.inserted_id)
 
     async def _store_consolidated_memory(
         self,
@@ -449,7 +451,9 @@ class ConsolidationWorker:
             for label, cluster_mems in clusters.items():
                 mem_ids = [str(m["id"]) for m in cluster_mems]
 
-                abstraction = await self._call_consolidation_llm(cluster_mems, mem_ids, label)
+                abstraction = await self._call_consolidation_llm(
+                    cluster_mems, mem_ids, label, namespace_id
+                )
                 if abstraction is None:
                     continue
 
@@ -457,7 +461,9 @@ class ConsolidationWorker:
                     # Store abstraction text in Mongo FIRST to get a valid ObjectId
                     # for payload_ref. This must happen outside the PG transaction
                     # because Motor is async and the PG transaction should be short.
-                    payload_ref = await self._store_abstraction_in_mongo(abstraction.abstraction)
+                    payload_ref = await self._store_abstraction_in_mongo(
+                        namespace_id, abstraction.abstraction
+                    )
 
                     # PG transaction: memory row + WORM event log via append_event().
                     async with scoped_pg_session(self.pool, namespace_id) as conn:
diff --git a/nce/contradictions.py b/nce/contradictions.py
index b6b1afa..389e05e 100644
--- a/nce/contradictions.py
+++ b/nce/contradictions.py
@@ -476,12 +476,13 @@ async def _detect_contradictions_impl(
         ns_row = await conn.fetchrow("SELECT metadata FROM namespaces WHERE id = $1", namespace_id)
     ns_for_factory = _namespace_provider_metadata(ns_row)
 
-    db = mongo_client.memory_archive
+    from nce.db_utils import scoped_mongo_session
 
-    raw_by_ref = await fetch_episodes_raw_by_ref(
-        db,
-        [c["payload_ref"] for c in candidates],
-    )
+    async with scoped_mongo_session(mongo_client, namespace_id) as s_db:
+        raw_by_ref = await fetch_episodes_raw_by_ref(
+            s_db,
+            [c["payload_ref"] for c in candidates],
+        )
 
     detected: list[dict] = []
 
diff --git a/nce/db_utils.py b/nce/db_utils.py
index 7825658..1d1a55b 100644
--- a/nce/db_utils.py
+++ b/nce/db_utils.py
@@ -9,7 +9,7 @@ from __future__ import annotations
 
 import time
 from contextlib import asynccontextmanager
-from typing import Final
+from typing import Any, Final
 from uuid import UUID
 
 import asyncpg  # type: ignore[import-untyped]
@@ -136,3 +136,151 @@ async def scoped_pg_session(
             # No explicit _reset_rls_context() call: that would run inside the
             # transaction's finally block and can mask the original SQL error if
             # the transaction is already in an aborted state.
+
+
+class ScopedMongoCollection:
+    """Wrapper around Motor's AsyncIOMotorCollection to enforce and auto-inject namespace scoping."""
+
+    def __init__(self, collection: Any, namespace_id: str):
+        self._collection = collection
+        self._namespace_id = namespace_id
+
+    def _scope_filter(self, filter_spec: Any) -> dict[str, Any]:
+        """Ensures namespace_id matches scope, or auto-injects it."""
+        if filter_spec is None:
+            filter_spec = {}
+
+        if not isinstance(filter_spec, dict):
+            raise ValueError(f"Filter must be a dictionary, got {type(filter_spec)}")
+
+        if "namespace_id" in filter_spec:
+            ns_val = filter_spec["namespace_id"]
+            if str(ns_val) != self._namespace_id:
+                raise ValueError(
+                    f"Mismatched namespace_id: query has '{ns_val}', but session scope is '{self._namespace_id}'"
+                )
+            new_filter = dict(filter_spec)
+            new_filter["namespace_id"] = self._namespace_id
+            return new_filter
+        else:
+            new_filter = dict(filter_spec)
+            new_filter["namespace_id"] = self._namespace_id
+            return new_filter
+
+    def _scope_document(self, document: Any) -> dict[str, Any]:
+        """Ensures document has correct namespace_id for writes/inserts."""
+        if not isinstance(document, dict):
+            raise ValueError(f"Document must be a dictionary, got {type(document)}")
+
+        if "namespace_id" in document:
+            ns_val = document["namespace_id"]
+            if str(ns_val) != self._namespace_id:
+                raise ValueError(
+                    f"Mismatched namespace_id: document has '{ns_val}', but session scope is '{self._namespace_id}'"
+                )
+            new_doc = dict(document)
+            new_doc["namespace_id"] = self._namespace_id
+            return new_doc
+        else:
+            new_doc = dict(document)
+            new_doc["namespace_id"] = self._namespace_id
+            return new_doc
+
+    async def find_one(self, filter: Any = None, *args: Any, **kwargs: Any) -> Any:
+        scoped_filter = self._scope_filter(filter)
+        return await self._collection.find_one(scoped_filter, *args, **kwargs)
+
+    def find(self, filter: Any = None, *args: Any, **kwargs: Any) -> Any:
+        scoped_filter = self._scope_filter(filter)
+        return self._collection.find(scoped_filter, *args, **kwargs)
+
+    async def insert_one(self, document: Any, *args: Any, **kwargs: Any) -> Any:
+        scoped_doc = self._scope_document(document)
+        return await self._collection.insert_one(scoped_doc, *args, **kwargs)
+
+    async def insert_many(self, documents: Any, *args: Any, **kwargs: Any) -> Any:
+        if not isinstance(documents, list):
+            raise ValueError("documents must be a list")
+        scoped_docs = [self._scope_document(doc) for doc in documents]
+        return await self._collection.insert_many(scoped_docs, *args, **kwargs)
+
+    async def update_one(self, filter: Any, update: Any, *args: Any, **kwargs: Any) -> Any:
+        scoped_filter = self._scope_filter(filter)
+        if isinstance(update, dict):
+            for op, val in update.items():
+                if op == "$set" and isinstance(val, dict) and "namespace_id" in val:
+                    if str(val["namespace_id"]) != self._namespace_id:
+                        raise ValueError(
+                            f"Cannot update namespace_id to '{val['namespace_id']}'; session scope is '{self._namespace_id}'"
+                        )
+        return await self._collection.update_one(scoped_filter, update, *args, **kwargs)
+
+    async def update_many(self, filter: Any, update: Any, *args: Any, **kwargs: Any) -> Any:
+        scoped_filter = self._scope_filter(filter)
+        if isinstance(update, dict):
+            for op, val in update.items():
+                if op == "$set" and isinstance(val, dict) and "namespace_id" in val:
+                    if str(val["namespace_id"]) != self._namespace_id:
+                        raise ValueError(
+                            f"Cannot update namespace_id to '{val['namespace_id']}'; session scope is '{self._namespace_id}'"
+                        )
+        return await self._collection.update_many(scoped_filter, update, *args, **kwargs)
+
+    async def replace_one(self, filter: Any, replacement: Any, *args: Any, **kwargs: Any) -> Any:
+        scoped_filter = self._scope_filter(filter)
+        scoped_replacement = self._scope_document(replacement)
+        return await self._collection.replace_one(
+            scoped_filter, scoped_replacement, *args, **kwargs
+        )
+
+    async def delete_one(self, filter: Any, *args: Any, **kwargs: Any) -> Any:
+        scoped_filter = self._scope_filter(filter)
+        return await self._collection.delete_one(scoped_filter, *args, **kwargs)
+
+    async def delete_many(self, filter: Any, *args: Any, **kwargs: Any) -> Any:
+        scoped_filter = self._scope_filter(filter)
+        return await self._collection.delete_many(scoped_filter, *args, **kwargs)
+
+    def __getattr__(self, name: str) -> Any:
+        return getattr(self._collection, name)
+
+
+class ScopedMongoDatabase:
+    """Wrapper around Motor's AsyncIOMotorDatabase to return scoped collection accessors."""
+
+    def __init__(self, database: Any, namespace_id: str):
+        self._database = database
+        self._namespace_id = namespace_id
+
+    def __getitem__(self, name: str) -> ScopedMongoCollection:
+        coll = self._database[name]
+        return ScopedMongoCollection(coll, self._namespace_id)
+
+    def __getattr__(self, name: str) -> Any:
+        attr = getattr(self._database, name)
+        if name.startswith("_"):
+            return attr
+        from motor.core import AgnosticCollection
+
+        if isinstance(attr, AgnosticCollection) or (
+            hasattr(attr, "__class__") and "Mock" in attr.__class__.__name__
+        ):
+            return ScopedMongoCollection(attr, self._namespace_id)
+        return attr
+
+
+@asynccontextmanager
+async def scoped_mongo_session(
+    client: Any,
+    namespace_id: str | UUID,
+):
+    """Context manager for tenant-isolated MongoDB sessions.
+
+    Analogous to scoped_pg_session. Enforces that all database operations
+    automatically inject/verify the namespace_id.
+    """
+    if not namespace_id:
+        raise ValueError("namespace_id is required for scoped Mongo sessions")
+    ns_str = str(namespace_id)
+    db = ScopedMongoDatabase(client.memory_archive, ns_str)
+    yield db
diff --git a/nce/garbage_collector.py b/nce/garbage_collector.py
index ba15a45..99a46d7 100644
--- a/nce/garbage_collector.py
+++ b/nce/garbage_collector.py
@@ -447,10 +447,8 @@ async def _collect_reverse_orphans(
     Returns the number of memories soft-retired across all namespaces.
     """
     cutoff = datetime.now(timezone.utc) - timedelta(seconds=cfg.GC_ORPHAN_AGE_SECONDS)
-    # Subscript access (db["episodes"]) mirrors the forward sweep and matches the
-    # MagicMock dict used in unit tests.
-    episodes = mongo_client.memory_archive["episodes"]
     retired = 0
+    from nce.db_utils import scoped_mongo_session
 
     for ns_id in namespaces:
         try:
@@ -470,48 +468,49 @@ async def _collect_reverse_orphans(
                 f"({REVERSE_SWEEP_MAX_PER_NS}); remaining refs deferred to the next pass.",
             )
 
-        for memory_id, payload_ref in candidates:
-            try:
-                doc = await episodes.find_one({"_id": ObjectId(payload_ref)}, {"_id": 1})
-            except Exception as exc:
-                # Malformed ObjectId or a transient Mongo error: skip — never
-                # soft-retire on uncertainty.
-                log.error(
-                    "GC reverse sweep: Mongo lookup failed for memory=%s ns=%s: %s",
-                    memory_id,
-                    ns_id,
-                    type(exc).__name__,
-                )
-                continue
+        async with scoped_mongo_session(mongo_client, ns_id) as s_db:
+            for memory_id, payload_ref in candidates:
+                try:
+                    doc = await s_db.episodes.find_one({"_id": ObjectId(payload_ref)}, {"_id": 1})
+                except Exception as exc:
+                    # Malformed ObjectId or a transient Mongo error: skip — never
+                    # soft-retire on uncertainty.
+                    log.error(
+                        "GC reverse sweep: Mongo lookup failed for memory=%s ns=%s: %s",
+                        memory_id,
+                        ns_id,
+                        type(exc).__name__,
+                    )
+                    continue
 
-            if doc is not None:
-                continue  # healthy — Mongo doc present, leave untouched
+                if doc is not None:
+                    continue  # healthy — Mongo doc present, leave untouched
 
-            try:
-                did_retire = await _soft_retire_dangling(pg_pool, ns_id, memory_id)
-            except Exception as exc:
-                log.error(
-                    "GC reverse sweep: soft-retire failed for memory=%s ns=%s: %s",
-                    memory_id,
-                    ns_id,
-                    type(exc).__name__,
-                )
-                continue
-
-            if did_retire:
-                retired += 1
-                log.warning(
-                    "GC reverse sweep: soft-retired dangling memory=%s ns=%s "
-                    "(payload_ref=%s missing in Mongo episodes).",
-                    memory_id,
-                    ns_id,
-                    payload_ref,
-                )
-                await _dispatch_reverse_alert(
-                    "Dangling memory payload",
-                    f"Memory {memory_id} (namespace {ns_id}) referenced a missing "
-                    f"MongoDB episodes document and was soft-retired (valid_to set).",
-                )
+                try:
+                    did_retire = await _soft_retire_dangling(pg_pool, ns_id, memory_id)
+                except Exception as exc:
+                    log.error(
+                        "GC reverse sweep: soft-retire failed for memory=%s ns=%s: %s",
+                        memory_id,
+                        ns_id,
+                        type(exc).__name__,
+                    )
+                    continue
+
+                if did_retire:
+                    retired += 1
+                    log.warning(
+                        "GC reverse sweep: soft-retired dangling memory=%s ns=%s "
+                        "(payload_ref=%s missing in Mongo episodes).",
+                        memory_id,
+                        ns_id,
+                        payload_ref,
+                    )
+                    await _dispatch_reverse_alert(
+                        "Dangling memory payload",
+                        f"Memory {memory_id} (namespace {ns_id}) referenced a missing "
+                        f"MongoDB episodes document and was soft-retired (valid_to set).",
+                    )
 
     if retired:
         log.warning("GC reverse sweep: soft-retired %d dangling memory(ies).", retired)
diff --git a/nce/graph_query.py b/nce/graph_query.py
index 4814187..8d86474 100644
--- a/nce/graph_query.py
+++ b/nce/graph_query.py
@@ -792,6 +792,7 @@ class GraphRAGTraverser:
         self,
         mongo_ref_ids: set[str],
         restrict_user_id: str | None = None,
+        namespace_id: str | None = None,
     ) -> list[dict]:
         """
         Hydrate source documents from MongoDB using batch ``$in`` queries.
@@ -819,25 +820,43 @@ class GraphRAGTraverser:
         if not oids:
             return []
 
-        db = self.mongo_client.memory_archive
+        from nce.db_utils import scoped_mongo_session
 
         # Two batch queries — always exactly 2 round-trips, never N.
         ep_docs: dict[str, dict] = {}
         code_docs: dict[str, dict] = {}
 
-        try:
-            cursor = db.episodes.find({"_id": {"$in": oids}})
-            async for doc in cursor:
-                ep_docs[str(doc["_id"])] = doc
-        except Exception as e:
-            log.warning("Batch episodes hydration failed: %s", e)
+        if namespace_id:
+            try:
+                async with scoped_mongo_session(self.mongo_client, namespace_id) as s_db:
+                    cursor = s_db.episodes.find({"_id": {"$in": oids}})
+                    async for doc in cursor:
+                        ep_docs[str(doc["_id"])] = doc
+            except Exception as e:
+                log.warning("Batch episodes hydration failed: %s", e)
 
-        try:
-            cursor = db.code_files.find({"_id": {"$in": oids}})
-            async for doc in cursor:
-                code_docs[str(doc["_id"])] = doc
-        except Exception as e:
-            log.warning("Batch code_files hydration failed: %s", e)
+            try:
+                async with scoped_mongo_session(self.mongo_client, namespace_id) as s_db:
+                    cursor = s_db.code_files.find({"_id": {"$in": oids}})
+                    async for doc in cursor:
+                        code_docs[str(doc["_id"])] = doc
+            except Exception as e:
+                log.warning("Batch code_files hydration failed: %s", e)
+        else:
+            db = self.mongo_client.memory_archive
+            try:
+                cursor = db.episodes.find({"_id": {"$in": oids}})
+                async for doc in cursor:
+                    ep_docs[str(doc["_id"])] = doc
+            except Exception as e:
+                log.warning("Batch episodes hydration failed: %s", e)
+
+            try:
+                cursor = db.code_files.find({"_id": {"$in": oids}})
+                async for doc in cursor:
+                    code_docs[str(doc["_id"])] = doc
+            except Exception as e:
+                log.warning("Batch code_files hydration failed: %s", e)
 
         # Part II.4: fetch the wrapped DEK for each episode payload_ref so an
         # encrypted raw_data excerpt can be decrypted; legacy rows → NULL →
@@ -1075,6 +1094,7 @@ class GraphRAGTraverser:
         per_node: int,
         private: bool,
         user_id: str | None,
+        namespace_id: str | None = None,
     ) -> Subgraph:
         """Helper to deduplicate, page, and format BFS/neuromorphic traversal results into a Subgraph."""
         # Deduplicate edges (BFS can traverse same edge from both directions)
@@ -1103,7 +1123,9 @@ class GraphRAGTraverser:
         all_refs = {n.payload_ref for n in nodes_for_page if n.payload_ref}
         all_refs |= {e.payload_ref for e in page_edges if e.payload_ref}
         restrict = user_id if private else None
-        sources = await self._hydrate_sources(all_refs, restrict_user_id=restrict)
+        sources = await self._hydrate_sources(
+            all_refs, restrict_user_id=restrict, namespace_id=namespace_id
+        )
 
         return Subgraph(
             anchor=anchor.label,
@@ -1205,6 +1227,7 @@ class GraphRAGTraverser:
                 per_node=per_node,
                 private=private,
                 user_id=user_id,
+                namespace_id=namespace_id,
             )
 
     async def neuromorphic_search(
@@ -1357,6 +1380,7 @@ class GraphRAGTraverser:
                 per_node=per_node,
                 private=private,
                 user_id=user_id,
+                namespace_id=namespace_id,
             )
 
     async def get_subgraph(self, *args, **kwargs) -> Subgraph:
diff --git a/nce/me_app.py b/nce/me_app.py
index 054bf11..cd46bfe 100644
--- a/nce/me_app.py
+++ b/nce/me_app.py
@@ -805,7 +805,8 @@ async def get_me_dsar_export(request: Request) -> JSONResponse:
     if payload_refs and engine.mongo_client is not None:
         from bson import ObjectId
 
-        db = engine.mongo_client.memory_archive
+        from nce.db_utils import scoped_mongo_session
+
         oids = []
         for ref in payload_refs:
             try:
@@ -813,9 +814,10 @@ async def get_me_dsar_export(request: Request) -> JSONResponse:
             except Exception:
                 pass
 
-        cursor = db.episodes.find({"_id": {"$in": oids}})
-        async for doc in cursor:
-            mongo_payloads[str(doc["_id"])] = doc
+        async with scoped_mongo_session(engine.mongo_client, ns_id) as s_db:
+            cursor = s_db.episodes.find({"_id": {"$in": oids}})
+            async for doc in cursor:
+                mongo_payloads[str(doc["_id"])] = doc
 
     # Map contradictions to memories
     contra_map: dict[UUID, list[dict]] = {}
diff --git a/nce/orchestrators/memory.py b/nce/orchestrators/memory.py
index b07bb15..b4d564a 100644
--- a/nce/orchestrators/memory.py
+++ b/nce/orchestrators/memory.py
@@ -26,7 +26,7 @@ from motor.motor_asyncio import AsyncIOMotorClient
 from nce import embeddings as _embeddings
 from nce.auth import set_namespace_context, validate_agent_id
 from nce.config import cfg
-from nce.db_utils import scoped_pg_session
+from nce.db_utils import scoped_mongo_session, scoped_pg_session
 from nce.models import (
     _SAFE_ID_RE,
     ArtifactPayload,
@@ -598,8 +598,6 @@ class MemoryOrchestrator(OrchestratorBase):
         is off, ``raw_data`` is stored as plaintext and ``(None, None)`` is
         returned (the legacy / back-compatible shape).
         """
-        db = self.mongo_client.memory_archive
-        collection = db.episodes
         user_id = payload.metadata.get("user_id") if payload.metadata else None
         session_id = payload.metadata.get("session_id") if payload.metadata else None
 
@@ -611,19 +609,20 @@ class MemoryOrchestrator(OrchestratorBase):
 
             raw_data, wrapped_dek, dek_key_id = encrypt_raw_data(sanitized_heavy)
 
-        inserted_result = await collection.insert_one(
-            {
-                "user_id": user_id,
-                "session_id": session_id,
-                "namespace_id": str(payload.namespace_id),
-                "type": payload.memory_type.value,
-                "raw_data": raw_data,
-                "metadata": payload.metadata,
-                "pii_redacted": pii_result.redacted,
-                "pii_entities_found": pii_result.entities_found,
-                "ingested_at": datetime.now(timezone.utc),
-            }
-        )
+        async with scoped_mongo_session(self.mongo_client, payload.namespace_id) as db:
+            inserted_result = await db.episodes.insert_one(
+                {
+                    "user_id": user_id,
+                    "session_id": session_id,
+                    "namespace_id": str(payload.namespace_id),
+                    "type": payload.memory_type.value,
+                    "raw_data": raw_data,
+                    "metadata": payload.metadata,
+                    "pii_redacted": pii_result.redacted,
+                    "pii_entities_found": pii_result.entities_found,
+                    "ingested_at": datetime.now(timezone.utc),
+                }
+            )
         inserted_mongo_id = str(inserted_result.inserted_id)
         log.debug("[Mongo] Inserted episode. id=%s", inserted_mongo_id)
         return inserted_mongo_id, inserted_result, wrapped_dek, dek_key_id
@@ -1058,8 +1057,8 @@ class MemoryOrchestrator(OrchestratorBase):
                 pass  # Cache miss or Redis down — recalculate below
 
             if payload_hash is None:
-                db = self.mongo_client.memory_archive
-                doc = await db.episodes.find_one({"_id": row["payload_ref"]})
+                async with scoped_mongo_session(self.mongo_client, row["namespace_id"]) as s_db:
+                    doc = await s_db.episodes.find_one({"_id": row["payload_ref"]})
                 if doc:
                     # Part II.4: hash the *decrypted* content so the payload hash is
                     # stable across the plaintext→ciphertext rollout (legacy rows
@@ -1131,8 +1130,8 @@ class MemoryOrchestrator(OrchestratorBase):
             ]
 
         # Phase 2 — Mongo + local crypto (no DB connection held).
-        db = self.mongo_client.memory_archive
-        doc = await db.episodes.find_one({"_id": ObjectId(payload_ref)})
+        async with scoped_mongo_session(self.mongo_client, namespace_id) as s_db:
+            doc = await s_db.episodes.find_one({"_id": ObjectId(payload_ref)})
         if not doc:
             raise ValueError("MongoDB payload missing.")
 
@@ -1419,17 +1418,18 @@ class MemoryOrchestrator(OrchestratorBase):
         if payload_ref and self.mongo_client is not None:
             try:
                 oid = ObjectId(payload_ref)
-                await self._mongo_db.episodes.update_one(
-                    {"_id": oid},
-                    {
-                        "$set": {
-                            "raw_data": None,
-                            "shredded": True,
-                            "shredded_at": datetime.now(timezone.utc),
+                async with scoped_mongo_session(self.mongo_client, namespace_id) as s_db:
+                    await s_db.episodes.update_one(
+                        {"_id": oid},
+                        {
+                            "$set": {
+                                "raw_data": None,
+                                "shredded": True,
+                                "shredded_at": datetime.now(timezone.utc),
+                            },
+                            "$unset": {"metadata": ""},
                         },
-                        "$unset": {"metadata": ""},
-                    },
-                )
+                    )
             except Exception as exc:
                 warnings.append(f"mongo_tombstone_failed:{payload_ref}:{exc}")
 
diff --git a/nce/re_embedder.py b/nce/re_embedder.py
index 6ac109a..e6bde12 100644
--- a/nce/re_embedder.py
+++ b/nce/re_embedder.py
@@ -103,7 +103,7 @@ async def run_re_embedding_worker(pg_pool: asyncpg.Pool, mongo_client: Any):
                 # Process memories
                 # We use keyset pagination on memories.id
                 memories_query = """
-                    SELECT id, payload_ref 
+                    SELECT id, payload_ref, namespace_id 
                     FROM memories 
                     WHERE id > $1
                     ORDER BY id ASC
@@ -111,7 +111,7 @@ async def run_re_embedding_worker(pg_pool: asyncpg.Pool, mongo_client: Any):
                 """
                 if not last_memory_id:
                     memories_query = """
-                        SELECT id, payload_ref 
+                        SELECT id, payload_ref, namespace_id 
                         FROM memories 
                         ORDER BY id ASC
                         LIMIT 100
@@ -122,19 +122,24 @@ async def run_re_embedding_worker(pg_pool: asyncpg.Pool, mongo_client: Any):
 
                 if memories_batch:
                     # Hydrate from Mongo using optimized bulk lookup
-                    db = mongo_client.memory_archive
+                    from collections import defaultdict
+
+                    from nce.db_utils import scoped_mongo_session
+
                     texts_to_embed = []
                     valid_memories = []
 
-                    # Map valid ObjectIds to their original memories
+                    # Group oids and their row references by namespace_id
+                    ns_to_oids = defaultdict(list)
                     ref_to_row = {}
-                    oids = []
+
                     for row in memories_batch:
                         ref = row.get("payload_ref")
-                        if ref:
+                        ns_id = row.get("namespace_id")
+                        if ref and ns_id:
                             try:
                                 oid = ObjectId(ref)
-                                oids.append(oid)
+                                ns_to_oids[ns_id].append(oid)
                                 ref_to_row[oid] = row
                             except Exception:
                                 log.warning(
@@ -142,18 +147,25 @@ async def run_re_embedding_worker(pg_pool: asyncpg.Pool, mongo_client: Any):
                                     ref,
                                 )
 
-                    if oids:
-                        docs = {}
-                        cursor = db.episodes.find({"_id": {"$in": oids}}, {"raw_data": 1})
-                        async for doc in cursor:
-                            docs[doc["_id"]] = doc
+                    docs = {}
+                    for ns_id, oids in ns_to_oids.items():
+                        async with scoped_mongo_session(mongo_client, ns_id) as s_db:
+                            cursor = s_db.episodes.find({"_id": {"$in": oids}}, {"raw_data": 1})
+                            async for doc in cursor:
+                                docs[doc["_id"]] = doc
 
-                        # Process in order to align properly
-                        for oid in oids:
-                            doc = docs.get(oid)
-                            if doc and doc.get("raw_data"):
-                                texts_to_embed.append(doc["raw_data"])
-                                valid_memories.append(ref_to_row[oid]["id"])
+                    # Process in order to align properly
+                    for row in memories_batch:
+                        ref = row.get("payload_ref")
+                        if ref:
+                            try:
+                                oid = ObjectId(ref)
+                                doc = docs.get(oid)
+                                if doc and doc.get("raw_data"):
+                                    texts_to_embed.append(doc["raw_data"])
+                                    valid_memories.append(row["id"])
+                            except Exception:
+                                pass
 
                     if texts_to_embed:
                         # Embed batch
@@ -258,4 +270,6 @@ async def run_re_embedding_worker(pg_pool: asyncpg.Pool, mongo_client: Any):
 
 
 def start_re_embedder(pg_pool, mongo_client) -> asyncio.Task:
-    return create_tracked_task(run_re_embedding_worker(pg_pool, mongo_client), name="re_embedding_worker")
+    return create_tracked_task(
+        run_re_embedding_worker(pg_pool, mongo_client), name="re_embedding_worker"
+    )
diff --git a/nce/reembedding_worker.py b/nce/reembedding_worker.py
index 3fc9abd..4178bd6 100644
--- a/nce/reembedding_worker.py
+++ b/nce/reembedding_worker.py
@@ -126,7 +126,7 @@ async def _fetch_memories_batch(
     if cursor_created_at is None:
         return await conn.fetch(
             """
-            SELECT id, created_at, memory_type, payload_ref, name, filepath
+            SELECT id, created_at, memory_type, payload_ref, name, filepath, namespace_id
             FROM   memories
             WHERE  embedding IS NOT NULL
               AND  (embedding_model_id IS NULL
@@ -141,7 +141,7 @@ async def _fetch_memories_batch(
     # Composite keyset: advance past (created_at, id) of the last processed row.
     return await conn.fetch(
         """
-        SELECT id, created_at, memory_type, payload_ref, name, filepath
+        SELECT id, created_at, memory_type, payload_ref, name, filepath, namespace_id
         FROM   memories
         WHERE  embedding IS NOT NULL
           AND  (embedding_model_id IS NULL
@@ -207,40 +207,44 @@ async def _resolve_texts_from_mongo(
     Episodic memories → ``episodes.raw_data``.
     Code chunks       → ``code_files.raw_code`` (truncated to max_text_chars).
     """
+    from collections import defaultdict
+
     from bson import ObjectId  # defer so tests that mock Mongo don't need bson
 
-    episodic_refs: list[str] = []
-    code_refs: list[str] = []
+    from nce.db_utils import scoped_mongo_session
+
+    ns_episodic_refs = defaultdict(list)
+    ns_code_refs = defaultdict(list)
 
     for row in rows:
         ref = row.get("payload_ref") or ""
-        if len(ref) != 24:  # MongoDB ObjectId hex is always 24 chars
+        ns_id = row.get("namespace_id")
+        if len(ref) != 24 or not ns_id:  # MongoDB ObjectId hex is always 24 chars
             continue
         if row.get("memory_type") == "code_chunk":
-            code_refs.append(ref)
+            ns_code_refs[ns_id].append(ObjectId(ref))
         else:
-            episodic_refs.append(ref)
+            ns_episodic_refs[ns_id].append(ObjectId(ref))
 
     result: dict[str, str] = {}
-    db = mongo_client.memory_archive
 
-    if episodic_refs:
+    for ns_id, oids in ns_episodic_refs.items():
         try:
-            oids = [ObjectId(r) for r in episodic_refs]
-            async for doc in db.episodes.find({"_id": {"$in": oids}}, {"raw_data": 1}):
-                ref = str(doc["_id"])
-                result[ref] = str(doc.get("raw_data", ""))[:max_text_chars]
+            async with scoped_mongo_session(mongo_client, ns_id) as s_db:
+                async for doc in s_db.episodes.find({"_id": {"$in": oids}}, {"raw_data": 1}):
+                    ref = str(doc["_id"])
+                    result[ref] = str(doc.get("raw_data", ""))[:max_text_chars]
         except Exception as exc:
-            log.warning("Re-embed: Mongo episodic fetch error: %s", exc)
+            log.warning("Re-embed: Mongo episodic fetch error for ns %s: %s", ns_id, exc)
 
-    if code_refs:
+    for ns_id, oids in ns_code_refs.items():
         try:
-            oids = [ObjectId(r) for r in code_refs]
-            async for doc in db.code_files.find({"_id": {"$in": oids}}, {"raw_code": 1}):
-                ref = str(doc["_id"])
-                result[ref] = str(doc.get("raw_code", ""))[:max_text_chars]
+            async with scoped_mongo_session(mongo_client, ns_id) as s_db:
+                async for doc in s_db.code_files.find({"_id": {"$in": oids}}, {"raw_code": 1}):
+                    ref = str(doc["_id"])
+                    result[ref] = str(doc.get("raw_code", ""))[:max_text_chars]
         except Exception as exc:
-            log.warning("Re-embed: Mongo code fetch error: %s", exc)
+            log.warning("Re-embed: Mongo code fetch error for ns %s: %s", ns_id, exc)
 
     return result
 
diff --git a/nce/replay.py b/nce/replay.py
index 3311d9f..5a742d5 100644
--- a/nce/replay.py
+++ b/nce/replay.py
@@ -450,8 +450,11 @@ def _fork_llm_payload_uri(
 class ReplayContext:
     """Carries state for replay executions, ensuring deterministic UUID remapping."""
 
-    def __init__(self, target_namespace_id: uuid.UUID) -> None:
+    def __init__(
+        self, target_namespace_id: uuid.UUID, source_namespace_id: uuid.UUID | None = None
+    ) -> None:
         self.target_namespace_id = target_namespace_id
+        self.source_namespace_id = source_namespace_id
         self.uuid_remap: dict[uuid.UUID, uuid.UUID] = {}
         self.mongo_remap: dict[str, str] = {}
         self._mongo_client: Any = None
@@ -485,7 +488,9 @@ class ReplayContext:
             self.mongo_remap[src_ref] = str(ObjectId(derived_bytes))
         return self.mongo_remap[src_ref]
 
-    async def copy_mongo_doc(self, src_ref: str) -> str:
+    async def copy_mongo_doc(
+        self, src_ref: str, source_namespace_id: uuid.UUID | None = None
+    ) -> str:
         """Copy Mongo document from src_ref to a deterministic target_ref."""
         target_ref = self.remap_mongo_ref(src_ref)
         if src_ref in self._copied_refs:
@@ -493,7 +498,11 @@ class ReplayContext:
 
         from bson import ObjectId
 
-        db = self.mongo_client.memory_archive
+        from nce.db_utils import scoped_mongo_session
+
+        ns_to_use = source_namespace_id or self.source_namespace_id
+        if ns_to_use is None:
+            ns_to_use = self.target_namespace_id
 
         try:
             src_oid = ObjectId(src_ref)
@@ -502,16 +511,29 @@ class ReplayContext:
             return target_ref
 
         try:
-            doc = await db.episodes.find_one({"_id": src_oid})
+            async with scoped_mongo_session(self.mongo_client, ns_to_use) as src_db:
+                doc = await src_db.episodes.find_one({"_id": src_oid})
+
             if doc is not None:
                 # Prepare target document
                 target_doc = dict(doc)
                 target_doc["_id"] = ObjectId(target_ref)
+                target_doc["namespace_id"] = str(self.target_namespace_id)
+
                 # Insert or replace in target (using upsert to be idempotent)
-                await db.episodes.replace_one({"_id": target_doc["_id"]}, target_doc, upsert=True)
+                async with scoped_mongo_session(
+                    self.mongo_client, self.target_namespace_id
+                ) as tgt_db:
+                    await tgt_db.episodes.replace_one(
+                        {"_id": target_doc["_id"]}, target_doc, upsert=True
+                    )
                 self._copied_refs.add(src_ref)
             else:
-                log.warning("Source Mongo document not found for payload_ref: %s", src_ref)
+                log.warning(
+                    "Source Mongo document not found for payload_ref: %s in namespace %s",
+                    src_ref,
+                    ns_to_use,
+                )
         except Exception as e:
             # Under some test configurations, Mongo might be mocked or unavailable.
             # We log the warning but do not crash the replay, so mock tests can run cleanly.
@@ -568,17 +590,12 @@ async def _handle_store_memory(
     that the fork's semantic state is identical up to the divergence point.
     Full re-embedding is supported by kicking off a re-embedding job later.
     """
-    is_raw_uuid = isinstance(ctx, uuid.UUID)
-    if isinstance(ctx, uuid.UUID):
-        ctx = ReplayContext(ctx)
-
     try:
         memory_id_str: str = src.params.get("memory_id", "")
         if not memory_id_str:
             return {"skipped": True, "reason": "no_memory_id_in_params"}
 
         src_memory_id = uuid.UUID(memory_id_str)
-        new_memory_id = ctx.remap(src_memory_id)
 
         # Fetch the source memory row (embedding + metadata).
         # The source_namespace_id is injected into params.source_namespace_id by
@@ -588,6 +605,12 @@ async def _handle_store_memory(
         if src_ns_id is None:
             return {"skipped": True, "reason": "source_namespace_id_missing_in_params"}
 
+        is_raw_uuid = isinstance(ctx, uuid.UUID)
+        if isinstance(ctx, uuid.UUID):
+            ctx = ReplayContext(ctx, source_namespace_id=src_ns_id)
+
+        new_memory_id = ctx.remap(src_memory_id)
+
         src_row = await conn.fetchrow(
             """
             SELECT embedding, assertion_type, memory_type, metadata, valid_from, created_at,
@@ -611,7 +634,7 @@ async def _handle_store_memory(
             return {"skipped": True, "reason": "payload_ref_missing_in_params"}
 
         # Copy the MongoDB document to a deterministic targets ref and update the params in-place
-        target_payload_ref = await ctx.copy_mongo_doc(payload_ref)
+        target_payload_ref = await ctx.copy_mongo_doc(payload_ref, source_namespace_id=src_ns_id)
         src.params["payload_ref"] = target_payload_ref
 
         meta = dict(src_row["metadata"]) if src_row["metadata"] else {}
@@ -816,10 +839,6 @@ async def _handle_consolidation_run(
     The handler writes the resulting consolidated memory and returns the
     result_summary for the fork's event_log entry.
     """
-    is_raw_uuid = isinstance(ctx, uuid.UUID)
-    if isinstance(ctx, uuid.UUID):
-        ctx = ReplayContext(ctx)
-
     try:
         if llm_payload is None:
             return {"skipped": True, "reason": "llm_payload_unavailable"}
@@ -842,8 +861,15 @@ async def _handle_consolidation_run(
         if not payload_ref:
             return {"skipped": True, "reason": "payload_ref_missing_in_params"}
 
+        raw_src_ns = src.params.get("source_namespace_id")
+        src_ns_id = uuid.UUID(raw_src_ns) if raw_src_ns else None
+
+        is_raw_uuid = isinstance(ctx, uuid.UUID)
+        if isinstance(ctx, uuid.UUID):
+            ctx = ReplayContext(ctx, source_namespace_id=src_ns_id)
+
         # Copy the MongoDB document to a deterministic targets ref and update the params in-place
-        target_payload_ref = await ctx.copy_mongo_doc(payload_ref)
+        target_payload_ref = await ctx.copy_mongo_doc(payload_ref, source_namespace_id=src_ns_id)
         src.params["payload_ref"] = target_payload_ref
 
         consolidated_memory_id_str = src.params.get("consolidated_memory_id")
@@ -1387,9 +1413,9 @@ async def _dispatch_and_apply_event(
     if ctx is None:
         if target_namespace_id is None:
             raise ValueError("Either ctx or target_namespace_id must be provided")
-        ctx = ReplayContext(target_namespace_id)
+        ctx = ReplayContext(target_namespace_id, source_namespace_id=source_namespace_id)
     elif isinstance(ctx, uuid.UUID):
-        ctx = ReplayContext(ctx)
+        ctx = ReplayContext(ctx, source_namespace_id=source_namespace_id)
 
     handler = _HANDLER_REGISTRY.get(src.event_type)
     if handler is None:
@@ -1478,7 +1504,7 @@ class ForkedReplay:
 
         run_id: uuid.UUID | None = None
         events_applied = 0
-        ctx = ReplayContext(target_namespace_id)
+        ctx = ReplayContext(target_namespace_id, source_namespace_id=source_namespace_id)
 
         try:
             # ------------------------------------------------------------------
@@ -1699,7 +1725,7 @@ class ReconstructiveReplay:
         """
         run_id: uuid.UUID | None = None
         events_applied = 0
-        ctx = ReplayContext(target_namespace_id)
+        ctx = ReplayContext(target_namespace_id, source_namespace_id=source_namespace_id)
 
         # 1. Create (or reuse) run row
         try:
diff --git a/nce/semantic_search.py b/nce/semantic_search.py
index 09ea2a3..5740e0f 100644
--- a/nce/semantic_search.py
+++ b/nce/semantic_search.py
@@ -322,7 +322,8 @@ async def semantic_search(
         )
     )
 
-    db = mongo_client.memory_archive
+    from nce.db_utils import scoped_mongo_session
+
     oid_map: dict[str, ObjectId] = {}
     for res in top_results:
         ref = str(res.get("payload_ref") or "")
@@ -333,11 +334,12 @@ async def semantic_search(
 
     docs: dict[str, Any] = {}
     if oid_map:
-        async for doc in db.episodes.find(
-            {"_id": {"$in": list(oid_map.values())}},
-            {"raw_data": 1},
-        ):
-            docs[str(doc["_id"])] = doc
+        async with scoped_mongo_session(mongo_client, namespace_id) as s_db:
+            async for doc in s_db.episodes.find(
+                {"_id": {"$in": list(oid_map.values())}},
+                {"raw_data": 1},
+            ):
+                docs[str(doc["_id"])] = doc
 
     from datetime import datetime, timezone
 
diff --git a/nce/state_digest.py b/nce/state_digest.py
index ab67160..5c61b36 100644
--- a/nce/state_digest.py
+++ b/nce/state_digest.py
@@ -82,16 +82,22 @@ async def compute_namespace_state_digest(
 
     mongo_client: AsyncIOMotorClient | None = None
     try:
+        from nce.db_utils import scoped_mongo_session
+
         mongo_client = AsyncIOMotorClient(cfg.MONGO_URI, serverSelectionTimeoutMS=2000)
-        db = mongo_client.memory_archive
-        if episode_oids:
-            cursor = db.episodes.find({"_id": {"$in": episode_oids}}, projection={"raw_data": 1})
-            async for doc in cursor:
-                episode_contents[str(doc["_id"])] = doc.get("raw_data") or ""
-        if code_oids:
-            cursor = db.code_files.find({"_id": {"$in": code_oids}}, projection={"raw_code": 1})
-            async for doc in cursor:
-                code_contents[str(doc["_id"])] = doc.get("raw_code") or ""
+        async with scoped_mongo_session(mongo_client, ns) as s_db:
+            if episode_oids:
+                cursor = s_db.episodes.find(
+                    {"_id": {"$in": episode_oids}}, projection={"raw_data": 1}
+                )
+                async for doc in cursor:
+                    episode_contents[str(doc["_id"])] = doc.get("raw_data") or ""
+            if code_oids:
+                cursor = s_db.code_files.find(
+                    {"_id": {"$in": code_oids}}, projection={"raw_code": 1}
+                )
+                async for doc in cursor:
+                    code_contents[str(doc["_id"])] = doc.get("raw_code") or ""
     except Exception as exc:
         log.warning("Failed to connect to MongoDB or fetch payloads for digest: %s", exc)
     finally:
diff --git a/tests/test_explain_past_decision.py b/tests/test_explain_past_decision.py
index 9fe4cc5..6d92621 100644
--- a/tests/test_explain_past_decision.py
+++ b/tests/test_explain_past_decision.py
@@ -130,6 +130,7 @@ async def test_explain_past_decision_belief_set_and_verified_fork(
             "_id": src_oid,
             "raw_data": "Bi-temporal belief content",
             "source": "test_explain_past_decision",
+            "namespace_id": str(source_ns),
         }
     )
 
diff --git a/tests/test_garbage_collector.py b/tests/test_garbage_collector.py
index 5c096a8..935c544 100644
--- a/tests/test_garbage_collector.py
+++ b/tests/test_garbage_collector.py
@@ -774,7 +774,12 @@ async def test_reverse_sweep_soft_retires_dangling_and_leaves_healthy(
         db = mongo_client.memory_archive
         # Insert ONLY the healthy doc; the dangling ref is intentionally absent.
         await db.episodes.insert_one(
-            {"_id": healthy_oid, "raw_data": "present", "source": "test_reverse_sweep"}
+            {
+                "_id": healthy_oid,
+                "raw_data": "present",
+                "source": "test_reverse_sweep",
+                "namespace_id": str(ns_id),
+            }
         )
 
         try:
diff --git a/tests/test_replay_handlers_integration.py b/tests/test_replay_handlers_integration.py
index 19298fd..a9a083d 100644
--- a/tests/test_replay_handlers_integration.py
+++ b/tests/test_replay_handlers_integration.py
@@ -469,6 +469,7 @@ async def test_replay_payload_copy_strategy(pg_pool, make_namespace, monkeypatch
             "_id": src_oid,
             "raw_data": "True isolation target content test",
             "source": "test_replay_payload_copy_strategy",
+            "namespace_id": str(source_ns),
         }
     )
 
@@ -892,11 +893,13 @@ async def test_reconstructive_replay_digest_match(pg_pool, make_namespace, monke
                 "_id": src_oid,
                 "raw_data": "State digest verification content",
                 "source": "test_reconstructive_replay_digest_match",
+                "namespace_id": str(source_ns),
             },
             {
                 "_id": ObjectId("000000000000000000000002"),
                 "raw_data": "This is a consolidated abstraction",
                 "source": "test_reconstructive_replay_digest_match",
+                "namespace_id": str(source_ns),
             },
         ]
     )
```
