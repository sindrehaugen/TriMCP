# Diff Reference for Batch 37

```diff
diff --git a/RL.md b/RL.md
index b4437b2..d54d204 100644
--- a/RL.md
+++ b/RL.md
@@ -44,7 +44,7 @@
 * [DONE] Batch 34 — `GET /api/admin/settings` (+ `/effective`, `/{key}`) (V.1b) [PASSED TAG]
 * [DONE] Batch 35 — `PATCH /api/admin/settings` (207) + `config_changed` WORM event (V.1b/V.5) [PASSED TAG]
 * [DONE] Batch 36 — `/reset`, `/reload`, `/pending` endpoints (V.1b) [PASSED TAG]
-* [OPEN] Batch 37 — Honest Uncertainty in search results (II.1) [NO TAG]
+* [RUNNING] Batch 37 — Honest Uncertainty in search results (II.1) [NO TAG]
 * [LOCKED] Batch 38 — Epistemic Receipts (II.2) [NO TAG]
 * [LOCKED] Batch 39 — Subject-scoped `/api/me/*` surface (cross-cutting enabler) [NO TAG]
 * [LOCKED] Batch 40 — Glass Profile endpoint + retract→ATMS (II.3) [NO TAG]
diff --git a/nce/semantic_search.py b/nce/semantic_search.py
index 93ce76f..2a22d61 100644
--- a/nce/semantic_search.py
+++ b/nce/semantic_search.py
@@ -270,6 +270,8 @@ async def semantic_search(
                     f"* nce_decayed_score(COALESCE(v.raw_salience, f.raw_salience), "
                     f"COALESCE(v.last_updated, f.last_updated), {p_half_life}::double precision))"
                 ).as_("final_score"),
+                RawExpression("COALESCE(v.raw_salience, f.raw_salience)").as_("raw_salience"),
+                RawExpression("COALESCE(v.last_updated, f.last_updated)").as_("last_updated"),
             )
             .orderby(Field("final_score"), order=Order.desc)
             .orderby(RawExpression("COALESCE(v.memory_id, f.memory_id)"))
@@ -283,6 +285,8 @@ async def semantic_search(
                 "payload_ref": row["payload_ref"],
                 "memory_id": row["memory_id"],
                 "score": row["final_score"],
+                "salience_score": float(row.get("raw_salience", 1.0)),
+                "last_reinforced_at": row.get("last_updated"),
             }
             for row in rows
         ]
@@ -315,11 +319,37 @@ async def semantic_search(
         ):
             docs[str(doc["_id"])] = doc
 
+    from datetime import datetime, timezone
+
+    from nce.temporal_decay import retention
+
     results = []
     for res in top_results:
         ref = str(res.get("payload_ref") or "")
         doc = docs.get(ref)
         raw = (doc.get("raw_data") or "") if doc else ""
+
+        salience_score = res.get("salience_score", 1.0)
+        last_reinforced_at = res.get("last_reinforced_at")
+
+        confidence = min(1.0, max(0.0, salience_score))
+        stale = False
+        if last_reinforced_at is not None:
+            try:
+                if isinstance(last_reinforced_at, str):
+                    ts = datetime.fromisoformat(last_reinforced_at.replace("Z", "+00:00"))
+                else:
+                    ts = last_reinforced_at
+
+                if ts.tzinfo is None:
+                    ts = ts.replace(tzinfo=timezone.utc)
+
+                retention_result = retention(ts, "episodic")
+                stale = retention_result.prune_eligible
+                confidence = min(1.0, max(0.0, salience_score * retention_result.retention))
+            except Exception:
+                pass
+
         results.append(
             {
                 "memory_id": res["memory_id"],
@@ -328,6 +358,12 @@ async def semantic_search(
                 "raw_data": (raw[:_MAX_RAW_DATA_CHARS] if isinstance(raw, str) else raw)
                 if doc
                 else None,
+                "salience_score": salience_score,
+                "last_reinforced_at": last_reinforced_at.isoformat()
+                if last_reinforced_at and hasattr(last_reinforced_at, 'isoformat')
+                else last_reinforced_at,
+                "confidence": confidence,
+                "stale": stale,
             }
         )
     return results
diff --git a/tests/test_semantic_search.py b/tests/test_semantic_search.py
index 6ac9040..51e4a17 100644
--- a/tests/test_semantic_search.py
+++ b/tests/test_semantic_search.py
@@ -452,3 +452,50 @@ class TestBatch3BackgroundReinforcement:
                 await asyncio.wait_for(done.wait(), timeout=1.0)
 
         assert set(reinforced) == {str(mid_a), str(mid_b)}
+
+
+class TestBatch37DecayConfidence:
+    @pytest.mark.asyncio
+    async def test_three_month_unreinforced_memory_returns_low_confidence_and_stale(self) -> None:
+        from datetime import datetime, timedelta, timezone
+
+        oid = str(ObjectId())
+        mid = uuid.uuid4()
+        three_months_ago = datetime.now(timezone.utc) - timedelta(days=90)
+
+        mock_row = {
+            "payload_ref": oid,
+            "memory_id": mid,
+            "final_score": 0.8,
+            "raw_salience": 1.0,
+            "last_updated": three_months_ago,
+        }
+
+        async def embed(_query: str):
+            return [0.0] * VECTOR_DIM
+
+        mock_conn = _base_pg_conn([mock_row])
+        pool = MagicMock()
+        mongo = _mongo_client(episode_docs={oid: {"_id": ObjectId(oid), "raw_data": "some memory"}})
+
+        with patch("nce.semantic_search.scoped_pg_session", _fake_scoped(mock_conn)):
+            with patch(
+                "nce.semantic_search.asyncio.create_task",
+                side_effect=lambda coro: (coro.close(), MagicMock())[1],
+            ):
+                results = await semantic_search(
+                    pg_pool=pool,
+                    mongo_client=mongo,
+                    embedding_fn=embed,
+                    query="test",
+                    namespace_id=NS,
+                    agent_id=AGENT,
+                )
+
+        assert len(results) == 1
+        res = results[0]
+        assert res["stale"] is True
+        assert res["confidence"] < 0.15
+        assert res["confidence"] > 0.04
+        assert res["salience_score"] == 1.0
+        assert res["last_reinforced_at"] == three_months_ago.isoformat()
```
