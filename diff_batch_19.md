# Diff Reference for Batch 19

```diff
diff --git a/nce/embeddings.py b/nce/embeddings.py
index 451eae3..d9c8137 100644
--- a/nce/embeddings.py
+++ b/nce/embeddings.py
@@ -26,10 +26,10 @@ import threading
 from abc import ABC, abstractmethod
 from concurrent.futures import ThreadPoolExecutor
 from contextvars import ContextVar
-from typing import TYPE_CHECKING
+from typing import TYPE_CHECKING, cast
 
 from nce.config import cfg
-from nce.observability import EMBEDDING_COUNT
+from nce.observability import EMBEDDING_COUNT, EMBEDDING_FALLBACKS
 
 if TYPE_CHECKING:
     pass
@@ -297,6 +297,17 @@ class EmbeddingBackend(ABC):
         vectors, degraded = await loop.run_in_executor(_executor, self._sync_embed_batch, texts)
         # Set the flag in the async task context — NOT inside the executor thread.
         degraded_embedding_flag.set(degraded)
+        if degraded:
+            EMBEDDING_FALLBACKS.inc()
+            try:
+                from nce.notifications import dispatcher
+
+                await dispatcher.dispatch_alert(
+                    "Embedding Fallback Active",
+                    "The primary embedding backend failed and degraded operation (hash-stub fallback) was triggered.",
+                )
+            except Exception:
+                log.exception("Failed to dispatch alert for embedding fallback")
         return vectors
 
 
@@ -458,7 +469,7 @@ class OpenVINONPUBackend(EmbeddingBackend):
                 e,
             )
 
-        return _validate_batch(texts, vectors, backend_name="OpenVINONPU")
+        return _validate_batch(texts, cast(list[list[float]], vectors), backend_name="OpenVINONPU")
 
 
 # ---------------------------------------------------------------------------
diff --git a/nce/observability.py b/nce/observability.py
index ef19861..1f5b8ce 100644
--- a/nce/observability.py
+++ b/nce/observability.py
@@ -87,9 +87,7 @@ try:
             # _names_to_collectors is a private prometheus_client attribute; guard
             # with getattr so a future library rename doesn't cause AttributeError.
             collectors = getattr(_PROM_REGISTRY, "_names_to_collectors", {})
-            return collectors.get(name) or metric_cls(
-                name, *args, registry=None, **kwargs
-            )
+            return collectors.get(name) or metric_cls(name, *args, registry=None, **kwargs)
 
     def _safe_counter(name: str, *args, **kwargs) -> Counter:
         return _safe_metric(Counter, name, *args, **kwargs)
@@ -284,6 +282,22 @@ EXTERNAL_HTTP_LATENCY_SECONDS = _safe_histogram(
     ["operation"],
 )
 
+# Quota and embedding-fallback metrics (Batch 19)
+QUOTA_CONSUMED = _safe_gauge(
+    "nce_quota_consumed_total",
+    "Current consumed resource amount for a namespace/agent quota",
+    ["namespace_id", "resource_type", "agent_id"],
+)
+QUOTA_REMAINING = _safe_gauge(
+    "nce_quota_remaining",
+    "Current remaining resource limit for a namespace/agent quota",
+    ["namespace_id", "resource_type", "agent_id"],
+)
+EMBEDDING_FALLBACKS = _safe_counter(
+    "nce_embedding_fallbacks_total",
+    "Total count of embedding fallback/hash-stub triggerings",
+)
+
 # --- Initialization ---
 
 _tracer_initialized = False
@@ -441,7 +455,7 @@ class SagaMetrics:
         return self
 
     def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
-        if cfg.NCE_OBSERVABILITY_ENABLED:
+        if cfg.NCE_OBSERVABILITY_ENABLED or self.operation == "store_memory":
             result = "success" if exc_type is None else "failure"
             duration = time.perf_counter() - self.start_time
             SAGA_DURATION.labels(operation=self.operation, result=result).observe(duration)
@@ -593,6 +607,7 @@ class traced_worker_job(ContextDecorator):
 
     Restores the remote trace context and starts a new nested span for the job execution.
     """
+
     def __init__(self, operation_name: str) -> None:
         self.operation_name = operation_name
         self.token = None
@@ -604,6 +619,7 @@ class traced_worker_job(ContextDecorator):
             return self
 
         from rq import get_current_job
+
         job = get_current_job()
         if job and job.meta:
             try:
diff --git a/nce/orchestrators/memory.py b/nce/orchestrators/memory.py
index a331833..cf27243 100644
--- a/nce/orchestrators/memory.py
+++ b/nce/orchestrators/memory.py
@@ -349,18 +349,20 @@ class MemoryOrchestrator(OrchestratorBase):
                 row = await conn.fetchrow(
                     """
                     INSERT INTO saga_execution_log (saga_type, namespace_id, agent_id, state, payload)
-                    VALUES ($1, $2::uuid, $3, 'started', $4)
+                    VALUES ($1, $2::uuid, $3, 'started', $4::jsonb)
                     RETURNING id
                     """,
                     saga_type,
                     str(payload.namespace_id),
                     payload.agent_id,
-                    {
-                        "memory_type": payload.memory_type.value,
-                        "assertion_type": payload.assertion_type.value,
-                        "summary": payload.summary,
-                        "metadata": payload.metadata,
-                    },
+                    json.dumps(
+                        {
+                            "memory_type": payload.memory_type.value,
+                            "assertion_type": payload.assertion_type.value,
+                            "summary": payload.summary,
+                            "metadata": payload.metadata,
+                        }
+                    ),
                 )
         return str(row["id"])
 
@@ -379,7 +381,7 @@ class MemoryOrchestrator(OrchestratorBase):
                     """,
                     state,
                     saga_id,
-                    payload_patch,
+                    json.dumps(payload_patch),
                 )
             else:
                 await conn.execute(
@@ -722,96 +724,97 @@ class MemoryOrchestrator(OrchestratorBase):
 
     async def _run_store_memory_saga(self, payload: StoreMemoryRequest) -> dict:
         """Executes the core transactional write saga across MongoDB, PG, and Redis."""
-        inserted_mongo_id: str | None = None
-        inserted_result = None
-        memory_id: UUID | None = None
-        pg_committed = False
-        saga_id = await self._saga_log_start("store_memory", payload)
-
-        try:
-            # --- Phase 0.3: PII Redaction + Graph Extraction ---
-            (
-                pii_result,
-                sanitized_summary,
-                sanitized_heavy,
-                entities,
-                triplets,
-            ) = await self._apply_pii_pipeline(payload)
-
-            # STEP 1: Episodic Commit (MongoDB)
-            user_id = payload.metadata.get("user_id") if payload.metadata else None
-            session_id = payload.metadata.get("session_id") if payload.metadata else None
-
-            inserted_mongo_id, inserted_result = await self._store_episodic_mongodb(
-                payload, sanitized_heavy, pii_result
-            )
+        with SagaMetrics("store_memory"):
+            inserted_mongo_id: str | None = None
+            inserted_result = None
+            memory_id: UUID | None = None
+            pg_committed = False
+            saga_id = await self._saga_log_start("store_memory", payload)
 
-            # Pre-compute all embeddings OUTSIDE the PG transaction
-            all_texts = [sanitized_summary] + [e.label for e in entities]
-            all_vectors = await _embeddings.embed_batch(all_texts)
-            vector = all_vectors[0]
-            node_vecs = all_vectors[1:]
-
-            # STEP 2 + 2b + 2c: Atomic Semantic + Graph Commit (single PG transaction)
-            memory_id = await self._store_semantic_graph_pg(
-                payload=payload,
-                sanitized_summary=sanitized_summary,
-                vector=vector,
-                node_vecs=node_vecs,
-                pii_result=pii_result,
-                inserted_mongo_id=inserted_mongo_id,
-                entities=entities,
-                triplets=triplets,
-                saga_id=saga_id,
-                user_id=user_id,
-                session_id=session_id,
-            )
+            try:
+                # --- Phase 0.3: PII Redaction + Graph Extraction ---
+                (
+                    pii_result,
+                    sanitized_summary,
+                    sanitized_heavy,
+                    entities,
+                    triplets,
+                ) = await self._apply_pii_pipeline(payload)
 
-            # Mark committed once exited from PG session block successfully
-            pg_committed = True
-
-        except Exception as e:
-            collection = self.mongo_client.memory_archive.episodes
-            await self._apply_rollback_on_failure(
-                e=e,
-                payload=payload,
-                collection=collection,
-                inserted_mongo_id=inserted_mongo_id,
-                inserted_result=inserted_result,
-                memory_id=memory_id,
-                pg_committed=pg_committed,
-                saga_id=saga_id,
-            )
-            raise
+                # STEP 1: Episodic Commit (MongoDB)
+                user_id = payload.metadata.get("user_id") if payload.metadata else None
+                session_id = payload.metadata.get("session_id") if payload.metadata else None
 
-        # --- PG committed; all subsequent failures are advisory ---
-        try:
-            await self._saga_log_transition(
-                saga_id, SagaState.PG_COMMITTED, payload_patch={"memory_id": str(memory_id)}
-            )
-        except Exception:
-            log.warning("[SAGA] PG_COMMITTED transition failed.", exc_info=True)
+                inserted_mongo_id, inserted_result = await self._store_episodic_mongodb(
+                    payload, sanitized_heavy, pii_result
+                )
 
-        # STEP 3: Working Memory (Redis)
-        await self._cache_working_memory_redis(
-            payload.namespace_id, user_id, session_id, sanitized_summary
-        )
+                # Pre-compute all embeddings OUTSIDE the PG transaction
+                all_texts = [sanitized_summary] + [e.label for e in entities]
+                all_vectors = await _embeddings.embed_batch(all_texts)
+                vector = all_vectors[0]
+                node_vecs = all_vectors[1:]
 
-        # STEP 4: Contradiction Detection
-        contradiction_result = await self._detect_contradictions_sync(
-            payload, memory_id, sanitized_summary, vector, triplets
-        )
+                # STEP 2 + 2b + 2c: Atomic Semantic + Graph Commit (single PG transaction)
+                memory_id = await self._store_semantic_graph_pg(
+                    payload=payload,
+                    sanitized_summary=sanitized_summary,
+                    vector=vector,
+                    node_vecs=node_vecs,
+                    pii_result=pii_result,
+                    inserted_mongo_id=inserted_mongo_id,
+                    entities=entities,
+                    triplets=triplets,
+                    saga_id=saga_id,
+                    user_id=user_id,
+                    session_id=session_id,
+                )
 
-        try:
-            await self._saga_log_transition(saga_id, SagaState.COMPLETED)
-        except Exception:
-            log.warning("[SAGA] COMPLETED transition failed.", exc_info=True)
+                # Mark committed once exited from PG session block successfully
+                pg_committed = True
 
-        return {
-            "quarantined": False,
-            "payload_ref": inserted_mongo_id,
-            "contradiction": contradiction_result,
-        }
+            except Exception as e:
+                collection = self.mongo_client.memory_archive.episodes
+                await self._apply_rollback_on_failure(
+                    e=e,
+                    payload=payload,
+                    collection=collection,
+                    inserted_mongo_id=inserted_mongo_id,
+                    inserted_result=inserted_result,
+                    memory_id=memory_id,
+                    pg_committed=pg_committed,
+                    saga_id=saga_id,
+                )
+                raise
+
+            # --- PG committed; all subsequent failures are advisory ---
+            try:
+                await self._saga_log_transition(
+                    saga_id, SagaState.PG_COMMITTED, payload_patch={"memory_id": str(memory_id)}
+                )
+            except Exception:
+                log.warning("[SAGA] PG_COMMITTED transition failed.", exc_info=True)
+
+            # STEP 3: Working Memory (Redis)
+            await self._cache_working_memory_redis(
+                payload.namespace_id, user_id, session_id, sanitized_summary
+            )
+
+            # STEP 4: Contradiction Detection
+            contradiction_result = await self._detect_contradictions_sync(
+                payload, memory_id, sanitized_summary, vector, triplets
+            )
+
+            try:
+                await self._saga_log_transition(saga_id, SagaState.COMPLETED)
+            except Exception:
+                log.warning("[SAGA] COMPLETED transition failed.", exc_info=True)
+
+            return {
+                "quarantined": False,
+                "payload_ref": inserted_mongo_id,
+                "contradiction": contradiction_result,
+            }
 
     async def store_memory(self, payload: StoreMemoryRequest) -> dict:
         """
@@ -835,10 +838,9 @@ class MemoryOrchestrator(OrchestratorBase):
                 return quarantine_result
 
             # Bypass or R >= 0.65 -> proceed with write saga (Slow I/O outside PG transaction)
-            with SagaMetrics("store_memory"):
-                res = await self._run_store_memory_saga(payload)
-                log.debug("Saga memory storage execution complete")
-                return res
+            res = await self._run_store_memory_saga(payload)
+            log.debug("Saga memory storage execution complete")
+            return res
 
     # ------------------------------------------------------------------
     # store_artifact (formerly store_media)
@@ -873,7 +875,9 @@ class MemoryOrchestrator(OrchestratorBase):
 
                 bucket_name = f"mcp-{payload.media_type}"
                 file_ext = os.path.splitext(safe_path)[1]
-                object_name = f"{payload.session_id}_{uuid.uuid4().hex}{file_ext}"
+                object_name = (
+                    f"{payload.namespace_id}/{payload.session_id}/{uuid.uuid4().hex}{file_ext}"
+                )
 
                 await asyncio.to_thread(
                     self.minio_client.fput_object,
@@ -1164,12 +1168,19 @@ class MemoryOrchestrator(OrchestratorBase):
         if session_id and not _SAFE_ID_RE.match(session_id):
             raise ValueError("Invalid session_id format")
 
-        if not as_of and limit == 1 and offset == 0 and not user_id and not session_id:
-            redis_key = f"cache:{namespace_id}:{agent_id}"
-            cached = await self.redis_client.get(redis_key)
-            if cached:
-                log.debug("[Redis] Cache hit. key=%s", redis_key)
-                return [cached.decode()]
+        if not as_of and limit == 1 and offset == 0:
+            if user_id and session_id:
+                redis_key = f"cache:{namespace_id}:{user_id}:{session_id}"
+            elif not user_id and not session_id:
+                redis_key = f"cache:{namespace_id}:{agent_id}"
+            else:
+                redis_key = None
+
+            if redis_key:
+                cached = await self.redis_client.get(redis_key)
+                if cached:
+                    log.debug("[Redis] Cache hit. key=%s", redis_key)
+                    return [cached.decode()]
 
         async with scoped_pg_session(self._db_pool(read_only=True), namespace_id) as conn:
             filters = ["namespace_id = $1", "memory_type = 'episodic'"]
@@ -1221,9 +1232,16 @@ class MemoryOrchestrator(OrchestratorBase):
             if txt:
                 results.append(str(txt))
 
-        if not as_of and limit == 1 and offset == 0 and results and not user_id and not session_id:
-            redis_key = f"cache:{namespace_id}:{agent_id}"
-            await self.redis_client.setex(redis_key, cfg.REDIS_TTL, results[0])
+        if not as_of and limit == 1 and offset == 0 and results:
+            if user_id and session_id:
+                redis_key = f"cache:{namespace_id}:{user_id}:{session_id}"
+            elif not user_id and not session_id:
+                redis_key = f"cache:{namespace_id}:{agent_id}"
+            else:
+                redis_key = None
+
+            if redis_key:
+                await self.redis_client.setex(redis_key, cfg.REDIS_TTL, results[0])
 
         return results
 
diff --git a/nce/quotas.py b/nce/quotas.py
index 51854f0..0a721fa 100644
--- a/nce/quotas.py
+++ b/nce/quotas.py
@@ -21,6 +21,7 @@ import asyncpg
 from asyncpg.exceptions import IntegrityConstraintViolationError
 
 from nce.config import cfg
+from nce.observability import QUOTA_CONSUMED, QUOTA_REMAINING
 
 log = logging.getLogger("nce.quotas")
 
@@ -234,6 +235,22 @@ async def _consume_resources_redis(
                         )
                     applied.append((qid, delta))
                     reservation.steps.append((qid, delta))
+
+                    # Update gauges (Batch 19)
+                    used = int(res)
+                    remaining = max(0, lim - used)
+                    ns_str = str(namespace_id)
+                    aid_str = str(row["agent_id"] or "global")
+                    QUOTA_CONSUMED.labels(
+                        namespace_id=ns_str,
+                        resource_type=resource_type,
+                        agent_id=aid_str,
+                    ).set(used)
+                    QUOTA_REMAINING.labels(
+                        namespace_id=ns_str,
+                        resource_type=resource_type,
+                        agent_id=aid_str,
+                    ).set(remaining)
     except QuotaExceededError:
         raise
     except Exception:
@@ -316,7 +333,7 @@ async def consume_resources(
                                 updated_at = now()
                             WHERE id = $2
                               AND used_amount + $1 <= limit_amount
-                            RETURNING id
+                            RETURNING id, used_amount, limit_amount
                             """,
                             delta,
                             row["id"],
@@ -328,6 +345,24 @@ async def consume_resources(
                                 f"resource={resource_type!r} ({scope} limit)"
                             )
                         reservation.steps.append((row["id"], delta))
+
+                        # Update gauges (Batch 19)
+                        if "used_amount" in upd and "limit_amount" in upd:
+                            used = int(upd["used_amount"])
+                            lim = int(upd["limit_amount"])
+                            remaining = max(0, lim - used)
+                            ns_str = str(namespace_id)
+                            aid_str = str(row["agent_id"] or "global")
+                            QUOTA_CONSUMED.labels(
+                                namespace_id=ns_str,
+                                resource_type=resource_type,
+                                agent_id=aid_str,
+                            ).set(used)
+                            QUOTA_REMAINING.labels(
+                                namespace_id=ns_str,
+                                resource_type=resource_type,
+                                agent_id=aid_str,
+                            ).set(remaining)
             except IntegrityConstraintViolationError as e:
                 raise QuotaExceededError(
                     f"Quota integrity constraint violated for namespace={namespace_id}: {e}"
@@ -384,11 +419,7 @@ async def quota_redis_flush_loop(redis_client: Any, pool: asyncpg.Pool) -> None:
     while True:
         try:
             await asyncio.sleep(cfg.NCE_QUOTA_REDIS_FLUSH_INTERVAL_S)
-            if (
-                cfg.NCE_QUOTAS_ENABLED
-                and cfg.NCE_QUOTA_REDIS_COUNTERS
-                and redis_client is not None
-            ):
+            if cfg.NCE_QUOTAS_ENABLED and cfg.NCE_QUOTA_REDIS_COUNTERS and redis_client is not None:
                 await flush_quota_counters_to_postgres(redis_client, pool)
         except asyncio.CancelledError:
             break
diff --git a/tests/test_memory_orchestrator_observability.py b/tests/test_memory_orchestrator_observability.py
index 009de4a..7871cd4 100644
--- a/tests/test_memory_orchestrator_observability.py
+++ b/tests/test_memory_orchestrator_observability.py
@@ -77,7 +77,6 @@ class TestSagaMetricsWrapsRealWork:
             f"non-trivial work — the context manager is wrapping nothing"
         )
 
-
     @pytest.mark.asyncio
     async def test_duration_non_zero_with_async_work(self, monkeypatch) -> None:
         """Same as above but with async work inside the context."""
@@ -214,7 +213,9 @@ class TestSagaMetricsSuccessFailureRecording:
         with SagaMetrics("store_memory"):
             pass
 
-        assert "success" in results, f"Expected 'success' result even with observability disabled, got {results}"
+        assert "success" in results, (
+            f"Expected 'success' result even with observability disabled, got {results}"
+        )
 
     def test_store_memory_non_opt_in_failure_emits_always(self, monkeypatch) -> None:
         """SagaMetrics for operation='store_memory' must emit failure metrics even when NCE_OBSERVABILITY_ENABLED is False."""
@@ -236,8 +237,9 @@ class TestSagaMetricsSuccessFailureRecording:
             with SagaMetrics("store_memory"):
                 raise ValueError("failed saga")
 
-        assert "failure" in results, f"Expected 'failure' result even with observability disabled, got {results}"
-
+        assert "failure" in results, (
+            f"Expected 'failure' result even with observability disabled, got {results}"
+        )
 
 
 # ===========================================================================
@@ -779,6 +781,7 @@ class TestMemoryOrchestratorObservabilityContract:
 # 5. RQ Trace Context Propagation Tests
 # ===========================================================================
 
+
 def test_rq_trace_context_propagation(monkeypatch) -> None:
     """Verify that enqueue_traced injects OpenTelemetry trace context and
     traced_worker_job extracts and restores it correctly in the worker."""
diff --git a/tests/test_quotas.py b/tests/test_quotas.py
index 2921740..3a7911b 100644
--- a/tests/test_quotas.py
+++ b/tests/test_quotas.py
@@ -1243,3 +1243,146 @@ async def test_flush_greatest_prevents_regressing_higher_pg_used(
     await quotas.flush_quota_counters_to_postgres(redis, MagicMock())
 
     assert bound_used == [stale_redis_used]
+
+
+# ---------------------------------------------------------------------------
+# Quota and Embedding Degradation Observability (Batch 19)
+# ---------------------------------------------------------------------------
+
+
+@pytest.mark.asyncio
+async def test_quota_metrics_updated_on_consume(monkeypatch: pytest.MonkeyPatch) -> None:
+    from nce.observability import QUOTA_CONSUMED, QUOTA_REMAINING
+
+    monkeypatch.setattr("nce.quotas.cfg.NCE_QUOTAS_ENABLED", True)
+
+    ns_id = uuid.uuid4()
+    qrow_ns = uuid.uuid4()
+
+    conn = AsyncMock()
+    conn.fetch.return_value = [{"id": qrow_ns, "agent_id": None}]
+    conn.fetchrow.return_value = {"id": qrow_ns, "used_amount": 15, "limit_amount": 100}
+
+    tx = AsyncMock()
+    conn.transaction = MagicMock(return_value=tx)
+    tx.__aenter__.return_value = None
+    tx.__aexit__.return_value = None
+
+    pool = MagicMock()
+    acq = AsyncMock()
+    acq.__aenter__.return_value = conn
+    acq.__aexit__.return_value = None
+    pool.acquire = MagicMock(return_value=acq)
+
+    mock_consumed_set = MagicMock()
+    mock_remaining_set = MagicMock()
+
+    monkeypatch.setattr(
+        QUOTA_CONSUMED, "labels", MagicMock(return_value=MagicMock(set=mock_consumed_set))
+    )
+    monkeypatch.setattr(
+        QUOTA_REMAINING, "labels", MagicMock(return_value=MagicMock(set=mock_remaining_set))
+    )
+
+    await quotas.consume_resources(
+        pool,
+        namespace_id=ns_id,
+        agent_id="agent-x",
+        amounts={quotas.RESOURCE_LLM_TOKENS: 10},
+    )
+
+    QUOTA_CONSUMED.labels.assert_called_once_with(
+        namespace_id=str(ns_id),
+        resource_type=quotas.RESOURCE_LLM_TOKENS,
+        agent_id="global",
+    )
+    QUOTA_REMAINING.labels.assert_called_once_with(
+        namespace_id=str(ns_id),
+        resource_type=quotas.RESOURCE_LLM_TOKENS,
+        agent_id="global",
+    )
+    mock_consumed_set.assert_called_once_with(15)
+    mock_remaining_set.assert_called_once_with(85)
+
+
+@pytest.mark.asyncio
+async def test_quota_metrics_updated_on_consume_redis(monkeypatch: pytest.MonkeyPatch) -> None:
+    from nce.observability import QUOTA_CONSUMED, QUOTA_REMAINING
+
+    monkeypatch.setattr("nce.quotas.cfg.NCE_QUOTAS_ENABLED", True)
+
+    ns_id = uuid.uuid4()
+    qrow_ns = uuid.uuid4()
+
+    conn = AsyncMock()
+    conn.fetch.return_value = [
+        {"id": qrow_ns, "agent_id": None, "used_amount": 5, "limit_amount": 100}
+    ]
+
+    redis_client = AsyncMock()
+    redis_client.eval.return_value = 15
+
+    pool = MagicMock()
+    acq = AsyncMock()
+    acq.__aenter__.return_value = conn
+    acq.__aexit__.return_value = None
+    pool.acquire = MagicMock(return_value=acq)
+
+    mock_consumed_set = MagicMock()
+    mock_remaining_set = MagicMock()
+
+    monkeypatch.setattr(
+        QUOTA_CONSUMED, "labels", MagicMock(return_value=MagicMock(set=mock_consumed_set))
+    )
+    monkeypatch.setattr(
+        QUOTA_REMAINING, "labels", MagicMock(return_value=MagicMock(set=mock_remaining_set))
+    )
+
+    monkeypatch.setattr("nce.quotas.cfg.NCE_QUOTA_REDIS_COUNTERS", True)
+
+    await quotas.consume_resources(
+        pool,
+        namespace_id=ns_id,
+        agent_id="agent-x",
+        amounts={quotas.RESOURCE_LLM_TOKENS: 10},
+        redis_client=redis_client,
+    )
+
+    QUOTA_CONSUMED.labels.assert_called_once_with(
+        namespace_id=str(ns_id),
+        resource_type=quotas.RESOURCE_LLM_TOKENS,
+        agent_id="global",
+    )
+    QUOTA_REMAINING.labels.assert_called_once_with(
+        namespace_id=str(ns_id),
+        resource_type=quotas.RESOURCE_LLM_TOKENS,
+        agent_id="global",
+    )
+    mock_consumed_set.assert_called_once_with(15)
+    mock_remaining_set.assert_called_once_with(85)
+
+
+@pytest.mark.asyncio
+async def test_embedding_fallback_increments_counter_and_alerts(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    from nce.embeddings import CPUBackend
+    from nce.observability import EMBEDDING_FALLBACKS
+
+    mock_dispatch_alert = AsyncMock()
+    monkeypatch.setattr("nce.notifications.dispatcher.dispatch_alert", mock_dispatch_alert)
+
+    mock_inc = MagicMock()
+    monkeypatch.setattr(EMBEDDING_FALLBACKS, "inc", mock_inc)
+
+    backend = CPUBackend()
+    monkeypatch.setattr(backend, "_sync_embed_batch", MagicMock(return_value=([[0.0] * 768], True)))
+
+    res = await backend.embed(["test text"])
+
+    assert len(res) == 1
+    mock_inc.assert_called_once()
+    mock_dispatch_alert.assert_called_once()
+    title, msg = mock_dispatch_alert.call_args[0]
+    assert "Embedding Fallback Active" in title
+    assert "hash-stub fallback" in msg
```
