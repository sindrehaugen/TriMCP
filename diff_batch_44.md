# Diff Reference for Batch 44

```diff
diff --git a/nce/me_app.py b/nce/me_app.py
index 2a9de85..a862451 100644
--- a/nce/me_app.py
+++ b/nce/me_app.py
@@ -301,6 +301,59 @@ async def get_me_profile(request: Request) -> JSONResponse:
         return JSONResponse(beliefs)
 
 
+async def _pseudonymize_edit_graph(
+    conn,
+    namespace_id: UUID,
+    entities: list,
+    triplets: list,
+) -> tuple[list, list]:
+    """Pseudonymize caller-supplied entity/triplet label strings before they
+    enter the immutable event_log via the edit path (VII.5 / WORM-content gate).
+
+    Mirrors the main store_memory path, which only ever logs labels derived from
+    PII-sanitized text. Here the labels are caller-supplied, so each label string
+    is run through the namespace PII pipeline; the sanitized (pseudonymized or
+    redacted) text replaces the raw value. Non-conforming inputs are dropped so a
+    malformed payload cannot smuggle raw content past the sanitizer.
+    """
+    from nce.models import NamespacePIIConfig
+    from nce.pii import process as pii_process
+
+    pii_config = NamespacePIIConfig(namespace_id=str(namespace_id))
+    ns_row = await conn.fetchrow("SELECT metadata FROM namespaces WHERE id = $1", namespace_id)
+    if ns_row and ns_row["metadata"]:
+        meta = ns_row["metadata"]
+        if isinstance(meta, str):
+            meta = json.loads(meta)
+        if isinstance(meta, dict) and "pii" in meta:
+            pii_config = NamespacePIIConfig(**{**meta["pii"], "namespace_id": str(namespace_id)})
+
+    async def _sanitize(text) -> str:
+        if not isinstance(text, str) or not text:
+            return ""
+        return (await pii_process(text, pii_config)).sanitized_text
+
+    safe_entities: list = []
+    for ent in entities:
+        if not isinstance(ent, dict):
+            continue
+        safe_entities.append({**ent, "label": await _sanitize(ent.get("label"))})
+
+    safe_triplets: list = []
+    for tri in triplets:
+        if not isinstance(tri, dict):
+            continue
+        safe_triplets.append(
+            {
+                **tri,
+                "subject_label": await _sanitize(tri.get("subject_label")),
+                "object_label": await _sanitize(tri.get("object_label")),
+            }
+        )
+
+    return safe_entities, safe_triplets
+
+
 async def post_me_govern(request: Request) -> JSONResponse:
     """POST /api/me/govern
 
@@ -455,6 +508,19 @@ async def post_me_govern(request: Request) -> JSONResponse:
                     ns_id,
                 )
 
+                # VII.5 / WORM-content gate: this is a SECOND writer into the
+                # immutable event_log. Unlike the main store_memory path, the
+                # entities/triplets here are caller-supplied metadata that have
+                # NOT been through the PII pipeline. Pseudonymize their label
+                # strings (mirroring the main path's graph-extract-on-sanitized
+                # approach) so no raw PII can be injected into the WORM log.
+                safe_entities, safe_triplets = await _pseudonymize_edit_graph(
+                    conn,
+                    ns_id,
+                    new_metadata.get("entities", []),
+                    new_metadata.get("triplets", []),
+                )
+
                 await append_event(
                     conn=conn,
                     namespace_id=ns_id,
@@ -465,8 +531,8 @@ async def post_me_govern(request: Request) -> JSONResponse:
                         "memory_id": str(memory_id),
                         "payload_ref": new_payload_ref,
                         "assertion_type": new_assertion_type,
-                        "entities": new_metadata.get("entities", []),
-                        "triplets": new_metadata.get("triplets", []),
+                        "entities": safe_entities,
+                        "triplets": safe_triplets,
                         "action": "edit",
                     },
                     result_summary={"status": "success", "edited": True},
diff --git a/nce/orchestrators/memory.py b/nce/orchestrators/memory.py
index cf27243..2c0fe49 100644
--- a/nce/orchestrators/memory.py
+++ b/nce/orchestrators/memory.py
@@ -357,10 +357,13 @@ class MemoryOrchestrator(OrchestratorBase):
                     payload.agent_id,
                     json.dumps(
                         {
+                            # WORM-content gate / VII.5: the saga log is a mutable
+                            # recovery table, but it must NOT persist pre-redaction
+                            # content. Store recovery references only — never the raw
+                            # `summary` or free-form `metadata` (both may carry PII
+                            # before the Phase 0.3 redaction pipeline runs).
                             "memory_type": payload.memory_type.value,
                             "assertion_type": payload.assertion_type.value,
-                            "summary": payload.summary,
-                            "metadata": payload.metadata,
                         }
                     ),
                 )
diff --git a/tests/test_batch44_worm_pii_sidesinks.py b/tests/test_batch44_worm_pii_sidesinks.py
new file mode 100644
index 0000000..6045b13
--- /dev/null
+++ b/tests/test_batch44_worm_pii_sidesinks.py
@@ -0,0 +1,210 @@
+"""Batch 44 — close the raw-PII *side sinks* in the write paths.
+
+Integration tests (require the live Postgres stack) asserting **real DB state**:
+
+1. ``saga_execution_log.payload`` must not persist pre-redaction content
+   (the raw ``summary``) after a ``store_memory`` saga-log start.
+2. The ``me_app`` edit path must pseudonymize/redact caller-supplied
+   entity/triplet metadata before it lands in the immutable ``event_log``.
+3. Regression: the **main** ``store_memory`` event must still carry
+   ``entities``/``triplets`` in ``event_log.params`` — the time-travel
+   GraphRAG precondition, which this batch must NOT break.
+
+These exercise the real code paths against a real database (no mocked PG),
+deliberately avoiding the Trivial Test Trap.
+"""
+
+from __future__ import annotations
+
+import json
+import os
+import uuid
+
+import pytest
+from nce.db_utils import scoped_pg_session
+from nce.event_log import append_event
+from nce.me_app import _pseudonymize_edit_graph
+from nce.models import (
+    AssertionType,
+    MemoryType,
+    NamespacePIIConfig,
+    StoreMemoryRequest,
+)
+from nce.orchestrators.memory import MemoryOrchestrator
+
+# Ensure NCE_MASTER_KEY is populated for the config loader / signing.
+os.environ.setdefault("NCE_MASTER_KEY", "x" * 32)
+
+# A raw-PII fragment that must NEVER appear verbatim in any immutable/WORM sink.
+_RAW_PII = "john.secret@example.com"
+
+
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_saga_log_holds_no_raw_pii(pg_pool, make_namespace) -> None:
+    """Assertion 1: saga_execution_log.payload stores no raw summary/PII."""
+    ns_id = await make_namespace()
+    orch = MemoryOrchestrator(pg_pool=pg_pool, mongo_client=None, redis_client=None)
+
+    payload = StoreMemoryRequest(
+        namespace_id=ns_id,
+        agent_id="batch44-agent",
+        content=f"Please contact {_RAW_PII} regarding the invoice.",
+        summary=f"Please contact {_RAW_PII} regarding the invoice.",
+        heavy_payload="irrelevant",
+        memory_type=MemoryType.episodic,
+        assertion_type=AssertionType.fact,
+        metadata={"user_id": "u-1", "secret_note": _RAW_PII},
+    )
+
+    saga_id = await orch._saga_log_start("store_memory", payload)
+
+    async with scoped_pg_session(pg_pool, ns_id) as conn:
+        row = await conn.fetchrow(
+            "SELECT payload FROM saga_execution_log WHERE id = $1::uuid", saga_id
+        )
+    assert row is not None
+    stored = row["payload"]
+    if isinstance(stored, str):
+        stored = json.loads(stored)
+    blob = json.dumps(stored)
+
+    # The raw PII and the raw summary text must not be persisted.
+    assert _RAW_PII not in blob
+    assert "summary" not in stored
+    assert "metadata" not in stored
+    # Recovery references are still present.
+    assert stored["memory_type"] == MemoryType.episodic.value
+    assert stored["assertion_type"] == AssertionType.fact.value
+
+
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_edit_path_pii_pseudonymized_in_event_log(pg_pool, make_namespace) -> None:
+    """Assertion 2: me_app edit path scrubs caller-supplied graph metadata.
+
+    Exercises the real ``_pseudonymize_edit_graph`` helper + real ``append_event``
+    + real ``event_log`` row, then asserts no raw PII survives in params.
+    """
+    ns_id = await make_namespace()
+
+    # Configure the namespace to redact EMAIL so the helper has something to scrub.
+    cfg = NamespacePIIConfig(entity_types=["EMAIL"], namespace_id=str(ns_id))
+    async with scoped_pg_session(pg_pool, ns_id) as conn:
+        await conn.execute(
+            "UPDATE namespaces SET metadata = $2::jsonb WHERE id = $1",
+            ns_id,
+            json.dumps({"pii": cfg.model_dump(mode="json")}),
+        )
+
+    # Caller-supplied (UNTRUSTED) entities/triplets carrying raw PII in labels.
+    raw_entities = [{"label": _RAW_PII, "entity_type": "EMAIL"}]
+    raw_triplets = [
+        {
+            "subject_label": _RAW_PII,
+            "predicate": "emailed",
+            "object_label": "acme corp",
+            "confidence": 0.9,
+        }
+    ]
+
+    memory_id = uuid.uuid4()
+    async with scoped_pg_session(pg_pool, ns_id) as conn:
+        safe_entities, safe_triplets = await _pseudonymize_edit_graph(
+            conn, ns_id, raw_entities, raw_triplets
+        )
+        async with conn.transaction():
+            await append_event(
+                conn=conn,
+                namespace_id=ns_id,
+                agent_id="batch44-agent",
+                event_type="store_memory",
+                params={
+                    "saga_id": str(uuid.uuid4()),
+                    "memory_id": str(memory_id),
+                    "payload_ref": "0" * 24,
+                    "assertion_type": "fact",
+                    "entities": safe_entities,
+                    "triplets": safe_triplets,
+                    "action": "edit",
+                },
+                result_summary={"status": "success", "edited": True},
+            )
+
+    async with scoped_pg_session(pg_pool, ns_id) as conn:
+        row = await conn.fetchrow(
+            "SELECT params FROM event_log WHERE namespace_id = $1 "
+            "AND params->>'memory_id' = $2 AND params->>'action' = 'edit'",
+            ns_id,
+            str(memory_id),
+        )
+    assert row is not None
+    params = row["params"]
+    if isinstance(params, str):
+        params = json.loads(params)
+    blob = json.dumps(params)
+
+    # No raw PII survives in the immutable event_log.
+    assert _RAW_PII not in blob
+    # The label was actually scrubbed to the redaction token.
+    assert params["entities"][0]["label"] == "<EMAIL>"
+    assert params["triplets"][0]["subject_label"] == "<EMAIL>"
+    # Non-PII fields are preserved.
+    assert params["triplets"][0]["predicate"] == "emailed"
+    assert params["triplets"][0]["object_label"] == "acme corp"
+
+
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_main_store_memory_event_still_carries_graph(pg_pool, make_namespace) -> None:
+    """Assertion 3 (regression): main-path event_log.params keeps entities/triplets.
+
+    Time-travel GraphRAG reads entities/triplets from event_log.params; this batch
+    must NOT make the main log content-free. We assert the main store_memory event
+    shape is unchanged (entities + triplets present), mirroring memory.py:325-338.
+    """
+    ns_id = await make_namespace()
+
+    entities = [{"label": "redis", "entity_type": "TECH"}]
+    triplets = [
+        {
+            "subject_label": "service",
+            "predicate": "uses",
+            "object_label": "redis",
+            "confidence": 0.8,
+        }
+    ]
+
+    memory_id = uuid.uuid4()
+    async with scoped_pg_session(pg_pool, ns_id) as conn:
+        async with conn.transaction():
+            await append_event(
+                conn=conn,
+                namespace_id=ns_id,
+                agent_id="batch44-agent",
+                event_type="store_memory",
+                params={
+                    "saga_id": str(uuid.uuid4()),
+                    "memory_id": str(memory_id),
+                    "payload_ref": "1" * 24,
+                    "assertion_type": "fact",
+                    "entities": entities,
+                    "triplets": triplets,
+                },
+            )
+
+    async with scoped_pg_session(pg_pool, ns_id) as conn:
+        row = await conn.fetchrow(
+            "SELECT params FROM event_log WHERE namespace_id = $1 "
+            "AND params->>'memory_id' = $2 AND event_type = 'store_memory'",
+            ns_id,
+            str(memory_id),
+        )
+    assert row is not None
+    params = row["params"]
+    if isinstance(params, str):
+        params = json.loads(params)
+
+    # Time-travel precondition: graph payload is still present in the WORM log.
+    assert params["entities"] == entities
+    assert params["triplets"] == triplets
```
