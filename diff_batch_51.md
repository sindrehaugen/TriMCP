# Diff Reference for Batch 51

```diff
diff --git a/RL.md b/RL.md
index 53884c4..452acfc 100644
--- a/RL.md
+++ b/RL.md
@@ -58,7 +58,7 @@
 * [DONE] Batch 48 — DSAR capstone (VII.7) [PASSED TAG]
 * [DONE] Batch 49 — Verify PII-before-derivation on every write path (VII.1) [PASSED TAG]
 * [DONE] Batch 50 — Scoped MongoDB accessor (VII.2) [PASSED TAG]
-* [OPEN] Batch 51 — MinIO per-namespace isolation (VII.3) [NO TAG]
+* [RUNNING] Batch 51 — MinIO per-namespace isolation (VII.3) [NO TAG]
 * [DONE] Batch 52 — Auto-generated Settings panel (V.3) [PASSED TAG]
 * [DONE] Batch 53 — Settings interaction design (V.3a) [PASSED TAG]
 * [DONE] Batch 54 — `config_changed` time-travel + rollback (V.6) [PASSED TAG]
diff --git a/nce/orchestrators/memory.py b/nce/orchestrators/memory.py
index b4d564a..5439608 100644
--- a/nce/orchestrators/memory.py
+++ b/nce/orchestrators/memory.py
@@ -912,6 +912,13 @@ class MemoryOrchestrator(OrchestratorBase):
                     f"{payload.namespace_id}/{payload.session_id}/{uuid.uuid4().hex}{file_ext}"
                 )
 
+                # Enforce that the object name carries the namespace prefix
+                ns_prefix = f"{payload.namespace_id}/"
+                if not object_name.startswith(ns_prefix):
+                    raise PermissionError(
+                        "Access denied: Object name must start with namespace prefix."
+                    )
+
                 await asyncio.to_thread(
                     self.minio_client.fput_object,
                     bucket_name,
@@ -1409,6 +1416,12 @@ class MemoryOrchestrator(OrchestratorBase):
                 warnings.append("minio_object_present_but_client_unconfigured")
             else:
                 try:
+                    # Enforce that the object name carries the namespace prefix
+                    ns_prefix = f"{namespace_id}/"
+                    if not object_name.startswith(ns_prefix):
+                        raise PermissionError(
+                            "Access denied: Object name does not belong to this namespace."
+                        )
                     await asyncio.to_thread(self.minio_client.remove_object, bucket, object_name)
                     minio_objects_removed = 1
                 except Exception as exc:
diff --git a/nce/storage.py b/nce/storage.py
index 1f32798..3d9a7f0 100644
--- a/nce/storage.py
+++ b/nce/storage.py
@@ -22,31 +22,29 @@ def generate_secure_presigned_url(
     minio_client: Minio,
     bucket_name: str,
     object_name: str,
+    current_namespace_id: str | UUID,
     method: str = "GET",
     expiry_seconds: int = 900,
     expected_mime: str | None = None,
-    current_namespace_id: str | UUID | None = None,
 ) -> str:
     """
     Generate a secure pre-signed URL for a MinIO object.
 
     Enforces the following security boundaries:
-    1. Tenant Isolation: If current_namespace_id is specified, validates that
-       the object_name starts with the prefix "{namespace_id}/".
+    1. Tenant Isolation: Validates that the object_name starts with the prefix "{namespace_id}/".
     2. Expiry Bounding: Restricts expiry to a maximum of 15 minutes (900 seconds).
     3. MIME/Extension Validation: For PUT operations, validates that the extension
        in the object_name is supported by the NCE document dispatcher.
     """
     # 1. Tenant Isolation Check
-    if current_namespace_id:
-        ns_str = str(current_namespace_id).strip().lower()
-        if not object_name.lower().startswith(f"{ns_str}/"):
-            log.warning(
-                "Access denied: Tenant path mismatch. Namespace %s requested object %s",
-                ns_str,
-                object_name,
-            )
-            raise PermissionError("Access denied: Tenant path mismatch.")
+    ns_str = str(current_namespace_id).strip().lower()
+    if not object_name.lower().startswith(f"{ns_str}/"):
+        log.warning(
+            "Access denied: Tenant path mismatch. Namespace %s requested object %s",
+            ns_str,
+            object_name,
+        )
+        raise PermissionError("Access denied: Tenant path mismatch.")
 
     # 2. Expiry Bounding Check
     bounded_expiry = min(max(expiry_seconds, 1), MAX_EXPIRY_SECONDS)
@@ -87,7 +85,7 @@ def generate_secure_presigned_url(
     try:
         if method_upper == "GET":
             # For GET operations, enforce attachment Content-Disposition to prevent inline HTML/XSS
-            response_headers = {
+            response_headers: dict[str, str | list[str] | tuple[str]] = {
                 "response-content-type": expected_mime or "application/octet-stream",
                 "response-content-disposition": "attachment",
             }
diff --git a/tests/test_batch9_storage.py b/tests/test_batch9_storage.py
index c0cfd40..667528a 100644
--- a/tests/test_batch9_storage.py
+++ b/tests/test_batch9_storage.py
@@ -52,6 +52,7 @@ def test_presigned_url_expiry_bounding():
         minio_client=minio_mock,
         bucket_name="mcp-document",
         object_name=object_name,
+        current_namespace_id=ns_id,
         method="GET",
         expiry_seconds=3600,  # 1 hour
     )
@@ -71,6 +72,7 @@ def test_presigned_url_put_validation():
         minio_client=minio_mock,
         bucket_name="mcp-document",
         object_name=f"{ns_id}/session-1/document.pdf",
+        current_namespace_id=ns_id,
         method="PUT",
     )
 
@@ -80,6 +82,7 @@ def test_presigned_url_put_validation():
             minio_client=minio_mock,
             bucket_name="mcp-document",
             object_name=f"{ns_id}/session-1/malicious.exe",
+            current_namespace_id=ns_id,
             method="PUT",
         )
     assert "Unsupported file extension" in str(exc_info.value)
@@ -250,3 +253,106 @@ async def test_dispatch_gc_collection():
             assert res.text == "hello"
             # Verify gc.collect() was explicitly called in dispatch.py success path
             mock_gc.assert_called()
+
+
+@pytest.mark.asyncio
+async def test_store_artifact_object_name_prefix(monkeypatch):
+    from nce.models import ArtifactPayload
+    from nce.orchestrators.memory import MemoryOrchestrator
+
+    pg_pool = MagicMock()
+    mongo_client = MagicMock()
+    redis_client = MagicMock()
+    minio_client = MagicMock(spec=Minio)
+
+    orchestrator = MemoryOrchestrator(
+        pg_pool=pg_pool,
+        mongo_client=mongo_client,
+        redis_client=redis_client,
+        minio_client=minio_client,
+    )
+
+    monkeypatch.setattr("pathlib.Path.is_file", lambda self: True)
+    orchestrator.store_memory = AsyncMock(return_value={"payload_ref": "some_ref"})
+
+    ns_id = uuid4()
+    payload = ArtifactPayload(
+        namespace_id=ns_id,
+        user_id="user1",
+        session_id="session1",
+        media_type="image",
+        file_path_on_disk="test.png",
+        summary="Test artifact",
+    )
+
+    res = await orchestrator.store_artifact(payload)
+    assert res == "some_ref"
+
+    # Assert that fput_object was called with an object_name starting with f"{ns_id}/"
+    minio_client.fput_object.assert_called_once()
+    args, kwargs = minio_client.fput_object.call_args
+    # signature: fput_object(bucket_name, object_name, file_path)
+    called_object_name = args[1]
+    assert called_object_name.startswith(f"{ns_id}/")
+
+
+@pytest.mark.asyncio
+async def test_shred_memory_cross_tenant_denied():
+    from nce.orchestrators.memory import MemoryOrchestrator
+
+    pg_pool = MagicMock()
+    mongo_client = MagicMock()
+    redis_client = MagicMock()
+    minio_client = MagicMock(spec=Minio)
+
+    orchestrator = MemoryOrchestrator(
+        pg_pool=pg_pool,
+        mongo_client=mongo_client,
+        redis_client=redis_client,
+        minio_client=minio_client,
+    )
+
+    ns_id = uuid4()
+    other_ns_id = uuid4()
+    memory_id = uuid4()
+
+    mock_conn = AsyncMock()
+    mock_conn.fetchrow.return_value = {
+        "payload_ref": "507f1f77bcf86cd799439011",
+        "dek_key_id": "key-1",
+        "was_encrypted": True,
+        "user_id": "user1",
+        "session_id": "session1",
+        "agent_id": "agent1",
+        "metadata": {"bucket": "mcp-image", "object_name": f"{other_ns_id}/session1/file.png"},
+    }
+
+    mock_conn.execute.return_value = "UPDATE 1"
+    mock_conn.fetch.return_value = []
+
+    mock_tx = AsyncMock()
+    mock_conn.transaction = MagicMock(return_value=mock_tx)
+
+    class MockSession:
+        async def __aenter__(self):
+            return mock_conn
+
+        async def __aexit__(self, exc_type, exc_val, exc_tb):
+            pass
+
+    with (
+        patch("nce.orchestrators.memory.scoped_pg_session", return_value=MockSession()),
+        patch("nce.event_log.append_event", AsyncMock()),
+    ):
+        res = await orchestrator.shred_memory(
+            memory_id=str(memory_id), namespace_id=str(ns_id), agent_id="system"
+        )
+
+    warnings = res["receipt"]["warnings"]
+    assert len(warnings) > 0
+    assert any(
+        "Access denied: Object name does not belong to this namespace" in w for w in warnings
+    )
+
+    # Verify that remove_object was NEVER called
+    minio_client.remove_object.assert_not_called()
```
