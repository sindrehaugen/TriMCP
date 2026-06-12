# Diff Reference for Batch 63

```diff
diff --git a/RL.md b/RL.md
index 2db7897..848e305 100644
--- a/RL.md
+++ b/RL.md
@@ -70,7 +70,7 @@
 * [DONE] Batch 60 — Multicore: HTTP workers + RQ replicas + thread pinning (VI.5a) [PASSED TAG]
 * [DONE] Batch 61 — RAM: offload spaCy + NLI to a sidecar; container mem limits (VI.5b) [PASSED TAG]
 * [DONE] Batch 62 — Disk: datastore tuning + halfvec + tmpfs temp (VI.5c) [PASSED TAG]
-* [OPEN] Batch 63 — Cross-encoder reranking (IV.1) [NO TAG]
+* [RUNNING] Batch 63 — Cross-encoder reranking (IV.1) [WAITING TAG]
 * [OPEN] Batch 64 — Multi-vector / aspect embeddings (IV.2) [NO TAG]
 * [LOCKED] Batch 65 — diag-config: `NCE_DIAG_*` configuration surface (Diag P1) [NO TAG]
 * [LOCKED] Batch 66 — ingestion-event-type: `ingestion_completed` event type + replay handler (Diag P1) [NO TAG]
diff --git a/nce/semantic_search.py b/nce/semantic_search.py
index 5740e0f..15c87d9 100644
--- a/nce/semantic_search.py
+++ b/nce/semantic_search.py
@@ -100,6 +100,67 @@ async def _fire_reinforcement(
         log.warning("Reinforcement background task failed (non-fatal)")
 
 
+async def check_nli_relevance(premise: str, hypothesis: str) -> float:
+    """Async wrapper for NLI relevance prediction.
+
+    If NCE_COGNITIVE_BASE_URL is configured, the NLI calculation is offloaded
+    out-of-process to the cognitive sidecar to prevent memory usage spikes.
+    Otherwise, it runs locally in-process using the CrossEncoder.
+    """
+    try:
+        from nce.embeddings import validated_cognitive_base_url
+
+        base_url = validated_cognitive_base_url()
+    except Exception:
+        base_url = ""
+
+    if base_url:
+        import math
+
+        import httpx
+
+        from nce.contradictions import NLIUnavailableError
+        from nce.http_resilience import request_with_retry
+
+        url = f"{base_url}/v1/nlp/nli"
+        async with httpx.AsyncClient(timeout=30.0) as client:
+            resp = await request_with_retry(
+                client,
+                "POST",
+                url,
+                json={"premise": premise, "hypothesis": hypothesis},
+                operation_name="nlp_sidecar:nli",
+            )
+            data = resp.json()
+            score = float(data["score"])
+            if math.isnan(score) or not (0.0 <= score <= 1.0):
+                raise NLIUnavailableError(f"Remote NLI score out of bounds: {score}")
+            return 1.0 - score
+
+    from nce.contradictions import NLIUnavailableError, _executor, _load_nli_model
+
+    model = _load_nli_model()
+    if model is None:
+        raise NLIUnavailableError("NLI model not loaded")
+
+    import math
+
+    import torch
+
+    loop = asyncio.get_running_loop()
+
+    def _predict() -> float:
+        scores = model.predict([(premise, hypothesis)])
+        probs = torch.nn.functional.softmax(torch.from_numpy(scores), dim=1).numpy()[0]
+        # DeBERTa NLI: 0=entail, 1=neutral, 2=contradiction
+        entail_score = float(probs[0])
+        if math.isnan(entail_score) or not (0.0 <= entail_score <= 1.0):
+            raise NLIUnavailableError(f"NLI score out of bounds: {entail_score}")
+        return entail_score
+
+    return await loop.run_in_executor(_executor, _predict)
+
+
 async def semantic_search(
     *,
     pg_pool: asyncpg.Pool,
@@ -111,6 +172,7 @@ async def semantic_search(
     limit: int = 5,
     offset: int = 0,
     as_of=None,
+    rerank: bool = False,
 ) -> list[dict]:
     """Semantic search with pgvector cosine + FTS hybrid ranking.
 
@@ -389,6 +451,29 @@ async def semantic_search(
                 else last_reinforced_at,
                 "confidence": confidence,
                 "stale": stale,
+                "reranker_score": None,
             }
         )
+
+    if rerank and results:
+        from nce.contradictions import NLIUnavailableError
+
+        reranked = True
+        for r in results:
+            raw_text = r["raw_data"] or ""
+            if not raw_text:
+                r["reranker_score"] = 0.0
+            else:
+                try:
+                    nli_score = await check_nli_relevance(raw_text, query)
+                    r["reranker_score"] = nli_score
+                except (NLIUnavailableError, Exception) as exc:
+                    log.warning("NLI reranking failed (falling back to database sorting): %s", exc)
+                    reranked = False
+                    break
+
+        if reranked:
+            results.sort(key=lambda x: (-x["reranker_score"], -x["score"], str(x["memory_id"])))
+            for r in results:
+                r["confidence"] = r["reranker_score"]
     return results
diff --git a/tests/test_semantic_search.py b/tests/test_semantic_search.py
index 51e4a17..c9bdbc8 100644
--- a/tests/test_semantic_search.py
+++ b/tests/test_semantic_search.py
@@ -499,3 +499,209 @@ class TestBatch37DecayConfidence:
         assert res["confidence"] > 0.04
         assert res["salience_score"] == 1.0
         assert res["last_reinforced_at"] == three_months_ago.isoformat()
+
+
+class TestBatch63CrossEncoderReranking:
+    @pytest.mark.asyncio
+    async def test_rerank_default_false(self) -> None:
+        oid = str(ObjectId())
+        mid = uuid.uuid4()
+        rows = [_pg_row(payload_ref=oid, memory_id=mid, score=0.9)]
+        mongo = _mongo_client(
+            episode_docs={oid: {"_id": ObjectId(oid), "raw_data": "some memory content"}}
+        )
+
+        async def embed(_query: str):
+            return [0.0] * VECTOR_DIM
+
+        mock_conn = _base_pg_conn(rows)
+        pool = MagicMock()
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
+                    query="test query",
+                    namespace_id=NS,
+                    agent_id=AGENT,
+                    rerank=False,
+                )
+
+        assert len(results) == 1
+        assert results[0]["reranker_score"] is None
+
+    @pytest.mark.asyncio
+    async def test_rerank_local_model_reorders_and_surfaces_score(self) -> None:
+        oid_a = str(ObjectId())
+        oid_b = str(ObjectId())
+        mid_a = uuid.UUID("00000000-0000-4000-8000-00000000000a")
+        mid_b = uuid.UUID("00000000-0000-4000-8000-00000000000b")
+
+        # A has lower database score (0.5) than B (0.9)
+        rows = [
+            _pg_row(payload_ref=oid_b, memory_id=mid_b, score=0.9),
+            _pg_row(payload_ref=oid_a, memory_id=mid_a, score=0.5),
+        ]
+        mongo = _mongo_client(
+            episode_docs={
+                oid_a: {"_id": ObjectId(oid_a), "raw_data": "matching content A"},
+                oid_b: {"_id": ObjectId(oid_b), "raw_data": "unrelated content B"},
+            }
+        )
+
+        async def embed(_query: str):
+            return [0.0] * VECTOR_DIM
+
+        mock_conn = _base_pg_conn(rows)
+        pool = MagicMock()
+
+        # Mock the local NLI model to return higher entailment score (probs[0]) for A than B
+        # probs structure: [entailment, neutral, contradiction]
+        import numpy as np
+
+        mock_model = MagicMock()
+        mock_model.predict = MagicMock(
+            side_effect=lambda pairs: np.array(
+                [[2.0, 0.0, -1.0] if pairs[0][0] == "matching content A" else [-2.0, 0.0, 1.0]],
+                dtype=np.float32,
+            )
+        )
+
+        with patch("nce.semantic_search.scoped_pg_session", _fake_scoped(mock_conn)):
+            with patch(
+                "nce.semantic_search.asyncio.create_task",
+                side_effect=lambda coro: (coro.close(), MagicMock())[1],
+            ):
+                with patch("nce.contradictions._load_nli_model", return_value=mock_model):
+                    results = await semantic_search(
+                        pg_pool=pool,
+                        mongo_client=mongo,
+                        embedding_fn=embed,
+                        query="matching query",
+                        namespace_id=NS,
+                        agent_id=AGENT,
+                        rerank=True,
+                    )
+
+        # After reranking, A (higher NLI entailment score) should be first, even though its database score was lower
+        assert len(results) == 2
+
+        # A should have high entailment probability (> 0.5)
+        # B should have low entailment probability (< 0.5)
+        assert results[0]["memory_id"] == mid_a
+        assert results[1]["memory_id"] == mid_b
+        assert results[0]["reranker_score"] > 0.8
+        assert results[1]["reranker_score"] < 0.2
+
+        # Surfaced as a confidence signal
+        assert results[0]["confidence"] == results[0]["reranker_score"]
+        assert results[1]["confidence"] == results[1]["reranker_score"]
+
+    @pytest.mark.asyncio
+    async def test_rerank_remote_cognitive_sidecar(self) -> None:
+        oid_a = str(ObjectId())
+        oid_b = str(ObjectId())
+        mid_a = uuid.UUID("00000000-0000-4000-8000-00000000000a")
+        mid_b = uuid.UUID("00000000-0000-4000-8000-00000000000b")
+
+        rows = [
+            _pg_row(payload_ref=oid_b, memory_id=mid_b, score=0.9),
+            _pg_row(payload_ref=oid_a, memory_id=mid_a, score=0.5),
+        ]
+        mongo = _mongo_client(
+            episode_docs={
+                oid_a: {"_id": ObjectId(oid_a), "raw_data": "matching content A"},
+                oid_b: {"_id": ObjectId(oid_b), "raw_data": "unrelated content B"},
+            }
+        )
+
+        async def embed(_query: str):
+            return [0.0] * VECTOR_DIM
+
+        mock_conn = _base_pg_conn(rows)
+        pool = MagicMock()
+
+        # Mock cognitive base URL to return a fake URL
+        with patch(
+            "nce.embeddings.validated_cognitive_base_url", return_value="http://localhost:11435"
+        ):
+            # Mock httpx POST response
+            mock_resp_a = MagicMock()
+            mock_resp_a.json = MagicMock(
+                return_value={"score": 0.1}
+            )  # low contradiction = high relevance
+
+            mock_resp_b = MagicMock()
+            mock_resp_b.json = MagicMock(
+                return_value={"score": 0.9}
+            )  # high contradiction = low relevance
+
+            async def mock_post(*args, **kwargs):
+                body = kwargs.get("json", {})
+                if body.get("premise") == "matching content A":
+                    return mock_resp_a
+                return mock_resp_b
+
+            with patch("nce.semantic_search.scoped_pg_session", _fake_scoped(mock_conn)):
+                with patch(
+                    "nce.semantic_search.asyncio.create_task",
+                    side_effect=lambda coro: (coro.close(), MagicMock())[1],
+                ):
+                    with patch("nce.http_resilience.request_with_retry", side_effect=mock_post):
+                        results = await semantic_search(
+                            pg_pool=pool,
+                            mongo_client=mongo,
+                            embedding_fn=embed,
+                            query="matching query",
+                            namespace_id=NS,
+                            agent_id=AGENT,
+                            rerank=True,
+                        )
+
+        # After reranking, A should be first (relevance = 1.0 - 0.1 = 0.9)
+        # B should be second (relevance = 1.0 - 0.9 = 0.1)
+        assert len(results) == 2
+        assert results[0]["memory_id"] == mid_a
+        assert results[1]["memory_id"] == mid_b
+        assert pytest.approx(results[0]["reranker_score"], 0.01) == 0.9
+        assert pytest.approx(results[1]["reranker_score"], 0.01) == 0.1
+        assert results[0]["confidence"] == results[0]["reranker_score"]
+
+    @pytest.mark.asyncio
+    async def test_rerank_graceful_degradation_on_nli_failure(self) -> None:
+        oid = str(ObjectId())
+        mid = uuid.uuid4()
+        rows = [_pg_row(payload_ref=oid, memory_id=mid, score=0.9)]
+        mongo = _mongo_client(episode_docs={oid: {"_id": ObjectId(oid), "raw_data": "some memory"}})
+
+        async def embed(_query: str):
+            return [0.0] * VECTOR_DIM
+
+        mock_conn = _base_pg_conn(rows)
+        pool = MagicMock()
+
+        # Mock NLI model loading to return None (model not installed/loaded)
+        with patch("nce.semantic_search.scoped_pg_session", _fake_scoped(mock_conn)):
+            with patch(
+                "nce.semantic_search.asyncio.create_task",
+                side_effect=lambda coro: (coro.close(), MagicMock())[1],
+            ):
+                with patch("nce.contradictions._load_nli_model", return_value=None):
+                    results = await semantic_search(
+                        pg_pool=pool,
+                        mongo_client=mongo,
+                        embedding_fn=embed,
+                        query="test",
+                        namespace_id=NS,
+                        agent_id=AGENT,
+                        rerank=True,
+                    )
+
+        # Should fall back to database sorting and return results cleanly
+        assert len(results) == 1
+        assert results[0]["reranker_score"] is None
```
