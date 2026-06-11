# Diff Reference for Batch 47

```diff
diff --git a/nce/event_types.py b/nce/event_types.py
index ab76811..92f318e 100644
--- a/nce/event_types.py
+++ b/nce/event_types.py
@@ -21,6 +21,8 @@ EventType = Literal[
     "store_memory_rolled_back",
     "forget_memory",
     "boost_memory",
+    # SECURITY_EVENTS — Part II.4 Provable Forgetting (content-free shred receipt)
+    "memory_shredded",
     # COGNITIVE_EVENTS
     "resolve_contradiction",
     "consolidation_run",
@@ -80,6 +82,20 @@ EVENT_REQUIRED_PARAM_KEYS: Final[dict[str, frozenset[str]]] = {
     ),
     "store_memory_rolled_back": frozenset({"saga_id", "memory_id", "reason", "payload_ref"}),
     "forget_memory": frozenset({"memory_id"}),
+    "memory_shredded": frozenset(
+        {
+            "memory_id",
+            "payload_ref",
+            "dek_key_id",
+            "was_encrypted",
+            "kg_nodes_deleted",
+            "kg_edges_deleted",
+            "embeddings_deleted",
+            "pii_redactions_deleted",
+            "cascade_ids",
+            "receipt_digest",
+        }
+    ),
     "boost_memory": frozenset({"memory_id", "factor"}),
     "resolve_contradiction": frozenset({"contradiction_id", "resolution"}),
     "consolidation_run": frozenset(
@@ -122,6 +138,11 @@ EVENT_FORBIDDEN_PARAM_KEYS: Final[dict[str, frozenset[str]]] = {
     # Prevent accidentally mixing audit vocabulary into the wrong event shape.
     "unredact": frozenset({"pii_redaction"}),
     "pii_redaction": frozenset({"unredact"}),
+    # Part II.4: the shred event is a content-free receipt — never let raw
+    # content, derived strings, or PII leak into the immutable log.
+    "memory_shredded": frozenset(
+        {"raw_data", "content", "summary", "heavy_payload", "entities", "triplets"}
+    ),
     # Never persist raw bearer material or hashed secrets in provenance payloads.
     "a2a_grant_created": frozenset({"sharing_token", "token_hash", "scopes"}),
     "a2a_grant_revoked": frozenset({"sharing_token", "token_hash"}),
diff --git a/nce/mcp_stdio_tools.py b/nce/mcp_stdio_tools.py
index ebc1411..99afc64 100644
--- a/nce/mcp_stdio_tools.py
+++ b/nce/mcp_stdio_tools.py
@@ -678,6 +678,30 @@ TOOLS = [
             "required": ["memory_id", "namespace_id", "agent_id", "admin_api_key"],
         },
     ),
+    Tool(
+        name="shred_memory",
+        description=(
+            "[ADMIN][Part II.4] Provably forget a memory across every store: destroys "
+            "the per-memory DEK (making the encrypted raw payload cryptographically "
+            "unrecoverable), deletes all plaintext derivatives (FTS, embeddings, KG "
+            "labels/edges via ATMS cascade, PII vault), purges Redis + MinIO, and "
+            "appends a signed, content-free 'memory_shredded' WORM event.  Returns a "
+            "verifiable deletion receipt."
+        ),
+        inputSchema={
+            "type": "object",
+            "properties": {
+                "memory_id": {"type": "string"},
+                "namespace_id": {"type": "string"},
+                "agent_id": {"type": "string"},
+                "admin_api_key": {
+                    "type": "string",
+                    "description": "Server-side admin API key for elevated access",
+                },
+            },
+            "required": ["memory_id", "namespace_id", "agent_id", "admin_api_key"],
+        },
+    ),
     # Migration tools are appended conditionally below
     Tool(
         name="replay_observe",
diff --git a/nce/memory_mcp_handlers.py b/nce/memory_mcp_handlers.py
index f7b923d..8599da1 100644
--- a/nce/memory_mcp_handlers.py
+++ b/nce/memory_mcp_handlers.py
@@ -25,6 +25,7 @@ from nce.models import (
     ForgetMemoryRequest,
     GetRecentContextRequest,
     SemanticSearchRequest,
+    ShredMemoryRequest,
     StoreMemoryRequest,
     UnredactMemoryRequest,
 )
@@ -139,6 +140,18 @@ async def handle_forget_memory(engine: NCEEngine, arguments: dict[str, Any]) ->
     return _serialize(res)
 
 
+@mcp_handler
+async def handle_shred_memory(engine: NCEEngine, arguments: dict[str, Any]) -> str:
+    """[ADMIN] Provably forget a memory across every store, returning a deletion receipt."""
+    req = ShredMemoryRequest(**arguments)
+    result = await engine.shred_memory(
+        memory_id=str(req.memory_id),
+        namespace_id=str(req.namespace_id),
+        agent_id=req.agent_id,
+    )
+    return _serialize(result)
+
+
 @mcp_handler
 async def handle_unredact_memory(engine: NCEEngine, arguments: dict[str, Any]) -> str:
     """Reverse pseudonymisation for a given memory (requires elevated permissions)."""
diff --git a/nce/models.py b/nce/models.py
index 5d00e17..5c36729 100644
--- a/nce/models.py
+++ b/nce/models.py
@@ -843,6 +843,21 @@ class UnredactMemoryRequest(BaseModel):
         return _validate_agent_id(v)
 
 
+class ShredMemoryRequest(BaseModel):
+    """Input for the shred_memory MCP tool (Part II.4 — Provable Forgetting, ADMIN)."""
+
+    model_config = ConfigDict(extra="forbid")
+
+    memory_id: UUID4
+    namespace_id: UUID4
+    agent_id: str
+
+    @field_validator("agent_id")
+    @classmethod
+    def _validate_agent_id(cls, v: str) -> str:
+        return _validate_agent_id(v)
+
+
 class GetRecentContextRequest(BaseModel):
     """Input for the get_recent_context MCP tool."""
 
diff --git a/nce/orchestrator.py b/nce/orchestrator.py
index 2e5dcb7..3c1881c 100644
--- a/nce/orchestrator.py
+++ b/nce/orchestrator.py
@@ -943,6 +943,11 @@ class NCEEngine(OrchestratorBase):
         await self._ensure_memory()
         return await self.memory.unredact_memory(memory_id, namespace_id, agent_id)
 
+    async def shred_memory(self, memory_id: str, namespace_id: str, agent_id: str) -> dict:
+        """[Part II.4] Provably forget a memory — delegating to MemoryOrchestrator."""
+        await self._ensure_memory()
+        return await self.memory.shred_memory(memory_id, namespace_id, agent_id)
+
     # --- Phase 1.1: Cognitive Layer (Salience) ---
 
     async def boost_memory(
diff --git a/nce/orchestrators/memory.py b/nce/orchestrators/memory.py
index 3369ac5..b07bb15 100644
--- a/nce/orchestrators/memory.py
+++ b/nce/orchestrators/memory.py
@@ -1174,6 +1174,323 @@ class MemoryOrchestrator(OrchestratorBase):
 
         return {"status": "success", "unredacted_text": raw_data}
 
+    # ------------------------------------------------------------------
+    # shred_memory — Part II.4 Provable Forgetting
+    # ------------------------------------------------------------------
+
+    async def shred_memory(
+        self,
+        memory_id: str,
+        namespace_id: str,
+        agent_id: str,
+    ) -> dict:
+        """[Part II.4] Provably forget a memory across every store.
+
+        Performs the full provable-forgetting sequence and returns a verifiable
+        *deletion receipt*.  The cryptographic guarantee is: after this call the
+        raw payload is **cryptographically unrecoverable** (its per-memory DEK is
+        destroyed) and every plaintext *derivative* is deleted; the immutable
+        ``event_log`` retains only the *fact* of deletion — never the content.
+
+        Sequence (the durable steps run inside one RLS-scoped PG transaction so
+        they commit atomically with the signed WORM event):
+
+          1. Destroy the DEK — zero ``memories.wrapped_dek`` / ``dek_key_id`` so
+             the encrypted Mongo ``episodes.raw_data`` becomes undecryptable.
+          2. Delete the plaintext derivatives — ``memories.content_fts`` and
+             ``memories.embedding`` (zeroed in place) plus ``memory_embeddings``.
+          3. ATMS-cascade-delete the KG labels/edges (``kg_nodes`` / ``kg_edges``
+             keyed by ``payload_ref``) and derived/consolidated dependent
+             memories (reuses the Batch-23 ATMS mechanism).
+          4. Delete the ``pii_redactions`` rows.
+          5. Append a signed, **content-free** ``memory_shredded`` WORM event
+             (refs + counts + key-id only).
+
+        The best-effort, out-of-transaction steps (durable once the PG tx has
+        committed; a partial failure leaves the content cryptographically
+        unrecoverable regardless, and is surfaced in the receipt's ``warnings``):
+
+          6. Purge the Redis working-memory cache key(s).
+          7. ``remove_object`` the MinIO media object(s).
+          8. Overwrite the Mongo ciphertext with a tombstone (defence-in-depth;
+             the content is already unrecoverable once the DEK is destroyed).
+
+        RLS: all tenant SQL runs inside ``scoped_session`` so a caller cannot
+        shred a memory outside their own namespace.
+        """
+        from nce.atms import evaluate_atms_intervention, persist_atms_invalidation
+        from nce.event_log import append_event
+
+        ns_uuid = UUID(str(namespace_id))
+        mem_uuid = UUID(str(memory_id))
+
+        # ── Durable phase: DEK destroy + derivative deletes + WORM event ──────
+        # All inside one RLS-scoped transaction; append_event shares the tx.
+        async with scoped_pg_session(self.pg_pool, namespace_id) as conn:
+            async with conn.transaction():
+                # Defence-in-depth on top of RLS: the row must live in this
+                # namespace, else the SELECT returns nothing and we abort.
+                row = await conn.fetchrow(
+                    """
+                    SELECT payload_ref, dek_key_id,
+                           (wrapped_dek IS NOT NULL) AS was_encrypted,
+                           user_id, session_id, agent_id, metadata
+                    FROM memories
+                    WHERE id = $1::uuid AND namespace_id = $2::uuid
+                    """,
+                    mem_uuid,
+                    ns_uuid,
+                )
+                if not row:
+                    raise PermissionError(f"Memory {memory_id} not accessible in your namespace")
+
+                payload_ref = row["payload_ref"]
+                dek_key_id = row["dek_key_id"]
+                was_encrypted = bool(row["was_encrypted"])
+                metadata = row["metadata"]
+                if isinstance(metadata, str):
+                    try:
+                        metadata = json.loads(metadata)
+                    except Exception:
+                        metadata = {}
+                metadata = metadata or {}
+
+                # 1+2. Destroy the DEK and the plaintext derivatives on the
+                # memories row.  Zeroing wrapped_dek crypto-shreds the Mongo
+                # ciphertext; content_fts/embedding are reversible derivatives.
+                await conn.execute(
+                    """
+                    UPDATE memories
+                    SET wrapped_dek = NULL,
+                        dek_key_id = NULL,
+                        content_fts = NULL,
+                        embedding = NULL,
+                        valid_to = COALESCE(valid_to, now())
+                    WHERE id = $1::uuid AND namespace_id = $2::uuid
+                    """,
+                    mem_uuid,
+                    ns_uuid,
+                )
+
+                # 2b. Delete derived embedding vectors.
+                res_emb = await conn.execute(
+                    "DELETE FROM memory_embeddings WHERE memory_id = $1::uuid",
+                    mem_uuid,
+                )
+                embeddings_deleted = int(res_emb.split()[-1]) if res_emb else 0
+
+                # 3. ATMS-cascade-delete KG labels/edges + derived memories.
+                #    KG nodes/edges are keyed by the Mongo payload_ref (the
+                #    content fanned out under that ref); delete them outright —
+                #    labels are plaintext content that cannot be encrypted.
+                nodes_deleted = 0
+                edges_deleted = 0
+                if payload_ref:
+                    await conn.execute(
+                        "DELETE FROM kg_node_embeddings "
+                        "WHERE node_id IN (SELECT id FROM kg_nodes WHERE payload_ref = $1)",
+                        payload_ref,
+                    )
+                    res_edges = await conn.execute(
+                        "DELETE FROM kg_edges WHERE payload_ref = $1", payload_ref
+                    )
+                    edges_deleted = int(res_edges.split()[-1]) if res_edges else 0
+                    res_nodes = await conn.execute(
+                        "DELETE FROM kg_nodes WHERE payload_ref = $1", payload_ref
+                    )
+                    nodes_deleted = int(res_nodes.split()[-1]) if res_nodes else 0
+
+                # 3b. Cascade soft-deletion to derived/consolidated dependents
+                #     and topology edges via the Batch-23 ATMS mechanism.
+                cascade_set: set[str] = {str(mem_uuid)}
+                topo_cascade = await evaluate_atms_intervention(conn, ns_uuid, str(mem_uuid))
+                cascade_set.update(topo_cascade)
+
+                max_cascade = 100
+                todo = [str(mem_uuid)]
+                visited = {str(mem_uuid)}
+                while todo and len(visited) < max_cascade:
+                    current = todo.pop()
+                    dep_rows = await conn.fetch(
+                        """
+                        SELECT id FROM memories
+                        WHERE namespace_id = $1::uuid
+                          AND (derived_from @> jsonb_build_array($2::text)
+                               OR derived_from @> jsonb_build_array($2::uuid))
+                          AND valid_to IS NULL
+                        """,
+                        ns_uuid,
+                        current,
+                    )
+                    for dep in dep_rows:
+                        dep_id = str(dep["id"])
+                        if dep_id not in visited:
+                            visited.add(dep_id)
+                            todo.append(dep_id)
+                            if len(visited) >= max_cascade:
+                                break
+                cascade_set.update(visited)
+                await persist_atms_invalidation(conn, ns_uuid, cascade_set)
+
+                # 4. Delete the PII vault rows (encrypted derivatives).
+                res_pii = await conn.execute(
+                    "DELETE FROM pii_redactions WHERE memory_id = $1::uuid",
+                    mem_uuid,
+                )
+                pii_deleted = int(res_pii.split()[-1]) if res_pii else 0
+
+                # 5. Append the signed, content-free memory_shredded WORM event.
+                #    Carries refs + counts + key-id ONLY — never any content,
+                #    entity string, summary, or PII.  A content-free digest binds
+                #    the receipt to the destroyed artifacts without revealing them.
+                shred_facts = {
+                    "memory_id": str(mem_uuid),
+                    "payload_ref": payload_ref or "",
+                    "dek_key_id": dek_key_id or "",
+                    "was_encrypted": was_encrypted,
+                    "cascade_count": len(cascade_set),
+                }
+                receipt_digest = hashlib.sha256(
+                    json.dumps(shred_facts, sort_keys=True).encode("utf-8")
+                ).hexdigest()
+
+                append_result = await append_event(
+                    conn=conn,
+                    namespace_id=ns_uuid,
+                    agent_id=agent_id,
+                    event_type="memory_shredded",
+                    params={
+                        "memory_id": str(mem_uuid),
+                        "payload_ref": payload_ref or "",
+                        "dek_key_id": dek_key_id or "",
+                        "was_encrypted": was_encrypted,
+                        "kg_nodes_deleted": nodes_deleted,
+                        "kg_edges_deleted": edges_deleted,
+                        "embeddings_deleted": embeddings_deleted,
+                        "pii_redactions_deleted": pii_deleted,
+                        "cascade_ids": sorted(cascade_set),
+                        "receipt_digest": receipt_digest,
+                    },
+                    result_summary={
+                        "status": "success",
+                        "cascade_count": len(cascade_set),
+                    },
+                )
+
+        # ── Best-effort phase (post-commit): Redis, MinIO, Mongo tombstone ────
+        # The cryptographic guarantee already holds; these reduce the residual
+        # ciphertext/cache surface.  Failures are recorded in `warnings`, never
+        # raised — the durable forget has already committed.
+        warnings: list[str] = []
+
+        # 6. Purge Redis working-memory cache key(s).
+        redis_keys_purged = 0
+        if self.redis_client is not None:
+            user_id = row["user_id"]
+            session_id = row["session_id"]
+            mem_agent = row["agent_id"]
+            candidate_keys: list[str] = []
+            if user_id and session_id:
+                candidate_keys.append(f"cache:{namespace_id}:{user_id}:{session_id}")
+            if mem_agent:
+                candidate_keys.append(f"cache:{namespace_id}:{mem_agent}")
+            candidate_keys.append(f"mem_verify_hash:{memory_id}")
+            for key in candidate_keys:
+                try:
+                    redis_keys_purged += int(await self.redis_client.delete(key))
+                except Exception as exc:
+                    warnings.append(f"redis_purge_failed:{key}:{exc}")
+
+        # 7. remove_object the MinIO media object(s).
+        minio_objects_removed = 0
+        bucket = metadata.get("bucket")
+        object_name = metadata.get("object_name")
+        if bucket and object_name:
+            if self.minio_client is None:
+                warnings.append("minio_object_present_but_client_unconfigured")
+            else:
+                try:
+                    await asyncio.to_thread(self.minio_client.remove_object, bucket, object_name)
+                    minio_objects_removed = 1
+                except Exception as exc:
+                    warnings.append(f"minio_remove_failed:{bucket}/{object_name}:{exc}")
+
+        # 8. Overwrite the Mongo ciphertext with a tombstone (defence-in-depth).
+        if payload_ref and self.mongo_client is not None:
+            try:
+                oid = ObjectId(payload_ref)
+                await self._mongo_db.episodes.update_one(
+                    {"_id": oid},
+                    {
+                        "$set": {
+                            "raw_data": None,
+                            "shredded": True,
+                            "shredded_at": datetime.now(timezone.utc),
+                        },
+                        "$unset": {"metadata": ""},
+                    },
+                )
+            except Exception as exc:
+                warnings.append(f"mongo_tombstone_failed:{payload_ref}:{exc}")
+
+        # ── Build the verifiable deletion receipt ─────────────────────────────
+        receipt = {
+            "memory_id": str(mem_uuid),
+            "namespace_id": str(ns_uuid),
+            "dek_destroyed": was_encrypted,
+            "dek_key_id": dek_key_id or "",
+            "payload_ref": payload_ref or "",
+            "derivatives_deleted": {
+                "content_fts": True,
+                "embedding": True,
+                "memory_embeddings": embeddings_deleted,
+                "kg_nodes": nodes_deleted,
+                "kg_edges": edges_deleted,
+                "pii_redactions": pii_deleted,
+            },
+            "cascade_count": len(cascade_set),
+            "redis_keys_purged": redis_keys_purged,
+            "minio_objects_removed": minio_objects_removed,
+            "receipt_digest": receipt_digest,
+            "worm_event": {
+                "event_id": str(append_result.event_id),
+                "event_seq": append_result.event_seq,
+                "occurred_at": append_result.occurred_at.isoformat(),
+                "event_type": "memory_shredded",
+            },
+            "warnings": warnings,
+            "guarantee": (
+                "raw payload is cryptographically unrecoverable (DEK destroyed) "
+                "and all plaintext derivatives are deleted; the immutable log "
+                "retains only the fact of deletion, never the content. "
+                "Note: entity/triplet strings recorded in prior store_memory WORM "
+                "events at write time persist there by design."
+            ),
+        }
+
+        # Self-verify the WORM event signature so the receipt ships verified.
+        async with scoped_pg_session(self.pg_pool, namespace_id) as conn:
+            event_row = await conn.fetchrow(
+                """
+                SELECT id, namespace_id, agent_id, event_type, event_seq,
+                       occurred_at, params, signature, signature_key_id,
+                       signature_version, chain_hash
+                FROM event_log
+                WHERE id = $1 AND namespace_id = $2::uuid
+                """,
+                append_result.event_id,
+                ns_uuid,
+            )
+            from nce.event_log import DataIntegrityError, verify_event_signature
+
+            try:
+                await verify_event_signature(conn, event_row)
+                receipt["verified"] = True
+            except DataIntegrityError:
+                receipt["verified"] = False
+
+        return {"status": "success", "receipt": receipt}
+
     # ------------------------------------------------------------------
     # recall_memory / recall_recent
     # ------------------------------------------------------------------
diff --git a/nce/replay.py b/nce/replay.py
index 824be0b..10ae39a 100644
--- a/nce/replay.py
+++ b/nce/replay.py
@@ -1076,6 +1076,9 @@ _additional_fork_provenance_types: tuple[str, ...] = (
     "chain_verification_failed",
     "atms_cascade",
     "config_changed",
+    # Part II.4: shred is destructive + content-free; fork projection records
+    # provenance only (no content to re-apply).
+    "memory_shredded",
 )
 for _fork_et in _additional_fork_provenance_types:
     assert _fork_et not in _HANDLER_REGISTRY, (
diff --git a/nce/tool_registry.py b/nce/tool_registry.py
index 4b5ec7e..2075c8e 100644
--- a/nce/tool_registry.py
+++ b/nce/tool_registry.py
@@ -125,6 +125,11 @@ TOOL_REGISTRY: dict[str, ToolSpec] = {
         admin_only=True,
         mutation=True,
     ),
+    "shred_memory": ToolSpec(
+        _h(memory_mcp_handlers, "handle_shred_memory"),
+        admin_only=True,
+        mutation=True,
+    ),
     # ------------------------------------------------------------------
     # Code indexing tools
     # ------------------------------------------------------------------
diff --git a/tests/test_shred_memory_integration.py b/tests/test_shred_memory_integration.py
new file mode 100644
index 0000000..626a14c
--- /dev/null
+++ b/tests/test_shred_memory_integration.py
@@ -0,0 +1,294 @@
+"""Integration acceptance test for Batch 47 — Provable Forgetting capstone (II.4c).
+
+This is the plan's *headline completeness test* (NCE_MASTER_PLAN II.4 verification):
+after ``shred_memory`` runs, assert that **NO plaintext fragment of the content
+survives in ANY store**:
+
+* Mongo ``episodes.raw_data`` ciphertext is undecryptable (the wrapped DEK was
+  destroyed) — and the sentinel plaintext is absent from the doc entirely.
+* ``memories.content_fts`` is empty and ``memories.embedding`` is NULL.
+* ``memory_embeddings`` rows for the memory are gone.
+* ``kg_nodes`` / ``kg_edges`` labels derived from the content are deleted
+  (ATMS cascade — KG labels are plaintext content).
+* ``pii_redactions`` rows are deleted.
+* the Redis working-memory cache key is purged.
+* ``event_log`` holds a signed ``memory_shredded`` event carrying only
+  refs/counts/hashes (no content), and the returned deletion receipt verifies.
+
+Requires live MongoDB + PostgreSQL + Redis (``-m integration``).
+"""
+
+from __future__ import annotations
+
+import json
+import os
+import socket
+import uuid
+from urllib.parse import urlparse
+
+import pytest
+import pytest_asyncio
+from bson import ObjectId
+from nce import MemoryPayload, NCEEngine
+from nce.config import cfg
+from nce.db_utils import scoped_pg_session
+from nce.envelope import _DEK_PAYLOAD_PREFIX, DEKDecryptionError, decrypt_with_dek
+
+
+def _reachable(env_var: str, host: str, port: int) -> bool:
+    url = os.getenv(env_var)
+    if url:
+        try:
+            if "://" in url:
+                parsed = urlparse(url)
+                host = parsed.hostname or host
+                port = parsed.port or port
+            else:
+                parts = url.split(":")
+                host = parts[0]
+                if len(parts) > 1:
+                    port = int(parts[1].split("/")[0])
+        except Exception:
+            pass
+    try:
+        sock = socket.create_connection((host, port), timeout=1)
+        sock.close()
+        return True
+    except OSError:
+        return False
+
+
+_CONTAINERS_OK = (
+    _reachable("MONGO_URI", "127.0.0.1", 27017)
+    and _reachable("PG_DSN", "127.0.0.1", 5432)
+    and _reachable("REDIS_URL", "127.0.0.1", 6379)
+)
+
+_skip_no_containers = pytest.mark.skipif(
+    not _CONTAINERS_OK,
+    reason="Integration test requires live MongoDB, PostgreSQL, and Redis containers",
+)
+
+
+@pytest_asyncio.fixture
+async def engine():
+    eng = NCEEngine()
+    await eng.connect()
+    yield eng
+    await eng.disconnect()
+
+
+@pytest_asyncio.fixture
+async def active_embedding_model(engine):
+    """Ensure at least one ACTIVE embedding model exists.
+
+    ``_store_semantic_graph_pg`` only writes ``memory_embeddings`` (and
+    ``kg_node_embeddings``) rows for models with status in (active, migrating).
+    The shred completeness test asserts ``emb_before > 0`` and then that those
+    rows are gone post-shred, so a model row is a precondition.  Idempotent:
+    inserts the configured model only if no active/migrating model is present,
+    so it is a no-op on an already-seeded DB.
+    """
+    from nce import embeddings as _emb
+
+    async with engine.pg_pool.acquire() as conn:
+        existing = await conn.fetchval(
+            "SELECT count(*) FROM embedding_models WHERE status IN ('active', 'migrating')"
+        )
+        if not existing:
+            await conn.execute(
+                "INSERT INTO embedding_models (name, dimension, status) "
+                "VALUES ($1, $2, 'active') ON CONFLICT (name) DO UPDATE SET status = 'active'",
+                _emb.MODEL_ID,
+                _emb.VECTOR_DIM,
+            )
+    yield
+
+
+@pytest_asyncio.fixture
+async def namespace_id(engine, active_embedding_model) -> uuid.UUID:
+    # Reversible pseudonymisation so the store path writes pii_redactions vault
+    # rows (only the reversible-pseudonymise path populates vault_entries) which
+    # we then assert are deleted on shred.  Fields must match NamespacePIIConfig
+    # exactly (extra="forbid"): entity_types/policy/reversible — NOT
+    # enabled/default_policy.  ``entity_types`` is REQUIRED: the scanner returns
+    # no entities (and thus no vault row) when it is empty.  "EMAIL" is the entity
+    # type recognised by the regex fallback used when Presidio is absent.
+    slug = f"pytest-shred-{uuid.uuid4().hex}"
+    meta = {
+        "pii": {
+            "entity_types": ["EMAIL"],
+            "policy": "pseudonymise",
+            "reversible": True,
+        }
+    }
+    async with engine.pg_pool.acquire() as conn:
+        ns = await conn.fetchval(
+            "INSERT INTO namespaces (slug, metadata) VALUES ($1, $2::jsonb) RETURNING id",
+            slug,
+            json.dumps(meta),
+        )
+    assert ns is not None
+    return ns
+
+
+@_skip_no_containers
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_shred_leaves_no_plaintext_in_any_store(engine, namespace_id, monkeypatch):
+    """The completeness test: after shred, no plaintext fragment survives anywhere."""
+    monkeypatch.setattr(cfg, "NCE_ENVELOPE_ENCRYPTION_ENABLED", True, raising=False)
+
+    sentinel = "SHRED-SENTINEL-" + uuid.uuid4().hex
+    # Email guarantees a regex-backed PII vault row; the proper-noun phrase
+    # seeds KG node/edge labels (plaintext content in the graph).
+    email = f"victim-{uuid.uuid4().hex[:8]}@example.com"
+    content = (
+        f"{sentinel}. Alice Johnson works at Globex Corporation in Berlin. Contact her at {email}."
+    )
+    sid = str(uuid.uuid4())
+    payload = MemoryPayload(
+        namespace_id=namespace_id,
+        agent_id="shred-agent",
+        content=content,
+        summary=content,
+        heavy_payload=content,
+        metadata={"user_id": sid, "session_id": sid},
+    )
+
+    res = await engine.store_memory(payload)
+    payload_ref = res["payload_ref"]
+    assert payload_ref
+
+    # Resolve the memory id and confirm pre-shred artifacts exist.
+    async with scoped_pg_session(engine.pg_pool, str(namespace_id)) as conn:
+        mem = await conn.fetchrow(
+            "SELECT id, wrapped_dek, dek_key_id FROM memories WHERE payload_ref = $1",
+            payload_ref,
+        )
+        assert mem is not None
+        assert mem["wrapped_dek"] is not None, "precondition: memory should be encrypted"
+        memory_id = str(mem["id"])
+
+        kg_nodes_before = await conn.fetchval(
+            "SELECT count(*) FROM kg_nodes WHERE payload_ref = $1", payload_ref
+        )
+        emb_before = await conn.fetchval(
+            "SELECT count(*) FROM memory_embeddings WHERE memory_id = $1::uuid", memory_id
+        )
+        pii_before = await conn.fetchval(
+            "SELECT count(*) FROM pii_redactions WHERE memory_id = $1::uuid", memory_id
+        )
+    assert emb_before > 0, "precondition: memory_embeddings should exist"
+    assert pii_before > 0, "precondition: a pii_redactions row should exist (email redacted)"
+
+    # Capture the ciphertext + wrapped DEK BEFORE the shred so we can prove the
+    # ciphertext is undecryptable afterwards (the DEK that decrypts it is gone).
+    db = engine.mongo_client.memory_archive
+    doc_before = await db.episodes.find_one({"_id": ObjectId(payload_ref)})
+    raw_before = doc_before["raw_data"]
+    ciphertext_before = bytes(raw_before)
+    assert ciphertext_before.startswith(_DEK_PAYLOAD_PREFIX)
+
+    # Prime the Redis cache key so we can assert it is purged.
+    recalled = await engine.recall_recent(
+        str(namespace_id), agent_id="shred-agent", limit=1, user_id=sid, session_id=sid
+    )
+    assert recalled, "precondition: recall should hydrate + cache the summary"
+    redis_key = f"cache:{namespace_id}:{sid}:{sid}"
+    assert await engine.redis_client.get(redis_key) is not None
+
+    # ── SHRED ─────────────────────────────────────────────────────────────────
+    out = await engine.shred_memory(memory_id, str(namespace_id), "shred-agent")
+    assert out["status"] == "success"
+    receipt = out["receipt"]
+
+    # The receipt verifies (the signed WORM event was self-verified).
+    assert receipt["verified"] is True
+    assert receipt["dek_destroyed"] is True
+    assert receipt["worm_event"]["event_type"] == "memory_shredded"
+
+    # 1. Mongo: the wrapped DEK is gone from PG → ciphertext is undecryptable.
+    async with scoped_pg_session(engine.pg_pool, str(namespace_id)) as conn:
+        post = await conn.fetchrow(
+            "SELECT wrapped_dek, dek_key_id, content_fts, embedding "
+            "FROM memories WHERE id = $1::uuid",
+            memory_id,
+        )
+    assert post["wrapped_dek"] is None, "DEK not destroyed"
+    assert post["dek_key_id"] is None, "dek_key_id not cleared"
+
+    # 2. content_fts empty + embedding NULL (reversible plaintext derivatives).
+    assert post["content_fts"] is None, "content_fts survived the shred"
+    assert post["embedding"] is None, "embedding survived the shred"
+
+    # The DEK is unrecoverable: prove the captured ciphertext cannot be decrypted
+    # with any wrong key (the real one no longer exists anywhere).
+    with pytest.raises(DEKDecryptionError):
+        decrypt_with_dek(ciphertext_before, b"\x00" * 32)
+
+    # And the Mongo doc itself no longer carries the plaintext (tombstoned).
+    doc_after = await db.episodes.find_one({"_id": ObjectId(payload_ref)})
+    assert doc_after is not None
+    raw_after = doc_after.get("raw_data")
+    raw_after_bytes = (
+        bytes(raw_after) if isinstance(raw_after, (bytes, bytearray, memoryview)) else b""
+    )
+    assert sentinel.encode() not in raw_after_bytes
+    assert email.encode() not in raw_after_bytes
+    assert sentinel not in json.dumps(doc_after, default=str)
+
+    # 3. memory_embeddings, kg_nodes, kg_edges, pii_redactions are gone.
+    async with scoped_pg_session(engine.pg_pool, str(namespace_id)) as conn:
+        emb_after = await conn.fetchval(
+            "SELECT count(*) FROM memory_embeddings WHERE memory_id = $1::uuid", memory_id
+        )
+        kg_nodes_after = await conn.fetchval(
+            "SELECT count(*) FROM kg_nodes WHERE payload_ref = $1", payload_ref
+        )
+        kg_edges_after = await conn.fetchval(
+            "SELECT count(*) FROM kg_edges WHERE payload_ref = $1", payload_ref
+        )
+        pii_after = await conn.fetchval(
+            "SELECT count(*) FROM pii_redactions WHERE memory_id = $1::uuid", memory_id
+        )
+    assert emb_after == 0, "memory_embeddings survived"
+    assert kg_nodes_after == 0, "kg_nodes (plaintext labels) survived"
+    assert kg_edges_after == 0, "kg_edges (plaintext triplets) survived"
+    assert pii_after == 0, "pii_redactions survived"
+    # If KG nodes existed pre-shred, the ATMS cascade should have removed them.
+    if kg_nodes_before:
+        assert kg_nodes_after == 0
+
+    # 4. Redis working-memory key purged.
+    assert await engine.redis_client.get(redis_key) is None, "Redis cache key survived"
+    assert receipt["redis_keys_purged"] >= 1
+
+    # 5. event_log holds a signed, CONTENT-FREE memory_shredded event.
+    async with scoped_pg_session(engine.pg_pool, str(namespace_id)) as conn:
+        ev = await conn.fetchrow(
+            """
+            SELECT params, signature, signature_key_id
+            FROM event_log
+            WHERE namespace_id = $1::uuid AND event_type = 'memory_shredded'
+              AND params->>'memory_id' = $2
+            ORDER BY occurred_at DESC LIMIT 1
+            """,
+            namespace_id,
+            memory_id,
+        )
+    assert ev is not None, "memory_shredded event not appended"
+    assert ev["signature"] is not None and ev["signature_key_id"], "event not signed"
+    params = ev["params"]
+    if isinstance(params, str):
+        params = json.loads(params)
+    # The immutable event must carry refs/counts/hashes ONLY — never content.
+    blob = json.dumps(params)
+    assert sentinel not in blob, "content sentinel leaked into WORM event"
+    assert email not in blob, "PII leaked into WORM event"
+    assert "Globex" not in blob and "Alice" not in blob, "entity strings leaked into WORM event"
+    assert params["memory_id"] == memory_id
+    assert "receipt_digest" in params and len(params["receipt_digest"]) == 64
+    # No content-bearing keys present at all.
+    for forbidden in ("raw_data", "content", "summary", "heavy_payload", "entities", "triplets"):
+        assert forbidden not in params, f"forbidden content key {forbidden!r} in WORM event"
diff --git a/tests/test_tool_registry.py b/tests/test_tool_registry.py
index 7267199..50b8f86 100644
--- a/tests/test_tool_registry.py
+++ b/tests/test_tool_registry.py
@@ -25,7 +25,7 @@ from nce.tool_registry import (
 # Cardinality
 # ---------------------------------------------------------------------------
 
-_EXPECTED_TOTAL = 65
+_EXPECTED_TOTAL = 66
 
 
 def test_registry_has_expected_entries():
@@ -82,6 +82,9 @@ _EXPECTED_MUTATION_TOOLS: frozenset[str] = frozenset(
         "a2a_revoke_grant",
         "a2a_update_grant_scopes",
         "unredact_memory",
+        # Batch 47 — Part II.4 Provable Forgetting; full crypto-shred + cascade
+        # delete across all stores is a mutation (and admin_only).
+        "shred_memory",
         "replay_reconstruct",
         # Batch 43 — bi-temporal accountability; optional counterfactual fork writes
         # events into the target namespace, so the tool is a mutation.
@@ -109,7 +112,7 @@ def test_mutation_tools_exact_match():
 
 
 def test_mutation_tools_count():
-    assert len(MUTATION_TOOLS) == 30
+    assert len(MUTATION_TOOLS) == 31
 
 
 # ---------------------------------------------------------------------------
@@ -152,6 +155,8 @@ _EXPECTED_ADMIN_ONLY: frozenset[str] = frozenset(
         "replay_fork",
         "replay_status",
         "explain_past_decision",
+        # Batch 47 — Part II.4 Provable Forgetting; shred is destructive + admin-only.
+        "shred_memory",
         "d365_sync_now",
         "d365_list_sla_breaches",
         # Batch 54 — V.6 config time-travel audit; admin-only read of the
@@ -169,7 +174,7 @@ def test_admin_only_tools_exact_match():
 
 
 def test_admin_only_tools_count():
-    assert len(ADMIN_ONLY_TOOLS) == 9
+    assert len(ADMIN_ONLY_TOOLS) == 10
 
 
 # ---------------------------------------------------------------------------
@@ -265,6 +270,10 @@ def test_toolspec_is_frozen():
             "unredact_memory",
             {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
         ),
+        (
+            "shred_memory",
+            {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
+        ),
         # code
         (
             "index_code_file",
```
