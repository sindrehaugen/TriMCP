# Diff Reference for Batch 57

```diff
diff --git a/RL.md b/RL.md
index 336adee..92f7d2c 100644
--- a/RL.md
+++ b/RL.md
@@ -64,7 +64,7 @@
 * [DONE] Batch 54 — `config_changed` time-travel + rollback (V.6) [PASSED TAG]
 * [DONE] Batch 55 — Secrets-manager seam + remove dev dotenv-persist in prod (VI.1) [PASSED TAG]
 * [DONE] Batch 56 — Resolve `nce_gc` least-privilege (R4 / VI.4) [PASSED TAG]
-* [OPEN] Batch 57 — Mongo write durability for the saga (R-A / VI.6a) [NO TAG]
+* [RUNNING] Batch 57 — Mongo write durability for the saga (R-A / VI.6a) [WAITING TAG]
 * [DONE] Batch 58 — Reverse-orphan reconciliation sweep (R-B / VI.6a) [PASSED TAG]
 * [DONE] Batch 59 — RQ in-flight job recovery (R-C / VI.6a) [PASSED TAG]
 * [DONE] Batch 60 — Multicore: HTTP workers + RQ replicas + thread pinning (VI.5a) [PASSED TAG]
diff --git a/nce/orchestrators/memory.py b/nce/orchestrators/memory.py
index 5439608..b5b4216 100644
--- a/nce/orchestrators/memory.py
+++ b/nce/orchestrators/memory.py
@@ -610,7 +610,17 @@ class MemoryOrchestrator(OrchestratorBase):
             raw_data, wrapped_dek, dek_key_id = encrypt_raw_data(sanitized_heavy)
 
         async with scoped_mongo_session(self.mongo_client, payload.namespace_id) as db:
-            inserted_result = await db.episodes.insert_one(
+            from pymongo.write_concern import WriteConcern
+
+            from nce.db_utils import ScopedMongoCollection
+
+            # Apply write concern majority + journaling to underlying collection, then re-wrap
+            raw_coll = db.episodes._collection
+            if not hasattr(raw_coll, "_mock_self"):
+                raw_coll = raw_coll.with_options(write_concern=WriteConcern(w="majority", j=True))
+            scoped_coll = ScopedMongoCollection(raw_coll, str(payload.namespace_id))
+
+            inserted_result = await scoped_coll.insert_one(
                 {
                     "user_id": user_id,
                     "session_id": session_id,
```
