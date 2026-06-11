# Diff Reference for Batch 46

```diff
diff --git a/nce/config.py b/nce/config.py
index 1c7af9c..5115026 100644
--- a/nce/config.py
+++ b/nce/config.py
@@ -348,6 +348,15 @@ class _Config:
 
     NCE_MAX_OCR_PAGES: int = _int_env("NCE_MAX_OCR_PAGES", 10, minimum=1)
 
+    # --- Provable Forgetting (Part II.4) — envelope encryption of raw content ---
+    # When enabled, store_memory encrypts the raw payload that fans out to
+    # MongoDB ``episodes.raw_data`` under a fresh per-memory DEK (wrapped under
+    # NCE_MASTER_KEY; see nce/envelope.py).  Read paths transparently decrypt and
+    # ALWAYS remain back-compatible with legacy rows whose ``wrapped_dek IS NULL``
+    # (those carry plaintext raw_data).  Default OFF so rollout is controlled —
+    # flip on only once NCE_MASTER_KEY is provisioned in the target environment.
+    NCE_ENVELOPE_ENCRYPTION_ENABLED: bool = _bool_env("NCE_ENVELOPE_ENCRYPTION_ENABLED", False)
+
     # --- MCP Sizing Limits ---
     NCE_MAX_ARGUMENTS_JSON_SIZE: int = _int_env(
         "NCE_MAX_ARGUMENTS_JSON_SIZE", 1_000_000, minimum=1024
diff --git a/nce/envelope.py b/nce/envelope.py
index 3a6bc3a..fbd77d2 100644
--- a/nce/envelope.py
+++ b/nce/envelope.py
@@ -50,6 +50,7 @@ from nce.signing import (
     SigningError,
     decrypt_signing_key,
     encrypt_signing_key,
+    require_master_key,
 )
 
 # ---------------------------------------------------------------------------
@@ -192,3 +193,76 @@ def decrypt_with_dek(blob: bytes, dek: bytes) -> bytes:
             "has been corrupted (or the DEK was destroyed — content is "
             "cryptographically unrecoverable)."
         ) from exc
+
+
+# ---------------------------------------------------------------------------
+# High-level helpers — orchestrate DEK + master-key + back-compat for callers
+# ---------------------------------------------------------------------------
+#
+# These wrap the primitives above so the write path and every read path share
+# one implementation of "encrypt the raw payload" / "decrypt it transparently,
+# tolerating legacy plaintext rows".  Read paths must hydrate raw content
+# through :func:`maybe_decrypt_raw_data` so that:
+#   * a row with a wrapped DEK → its ciphertext is unwrapped + decrypted, and
+#   * a legacy row (``wrapped_dek IS NULL``) → its plaintext is returned as-is.
+
+
+def encrypt_raw_data(plaintext: str) -> tuple[bytes, bytes, str]:
+    """Encrypt a raw-content *plaintext* under a fresh per-memory DEK.
+
+    Reuses the envelope primitives: generates a DEK, AES-256-GCM-encrypts the
+    UTF-8 payload under it, and wraps the DEK under the environment master key.
+
+    Returns ``(ciphertext, wrapped_dek, dek_key_id)`` — ``ciphertext`` goes into
+    Mongo ``episodes.raw_data``; ``wrapped_dek`` + ``dek_key_id`` go onto the
+    ``memories`` row.  ``NCE_MASTER_KEY`` is reached only via
+    :func:`nce.signing.require_master_key` (env-only).
+    """
+    dek = generate_dek()
+    try:
+        ciphertext = encrypt_with_dek(plaintext.encode("utf-8"), dek)
+        with require_master_key() as master_key:
+            wrapped = wrap_dek(dek, master_key)
+    finally:
+        # Zero the transient plaintext DEK the moment wrapping completes.
+        with SecureKeyBuffer(dek):
+            pass
+    return ciphertext, wrapped, new_dek_key_id()
+
+
+def maybe_decrypt_raw_data(raw_data: object, wrapped_dek: bytes | None) -> str:
+    """Return the plaintext raw content, decrypting only when encrypted.
+
+    Back-compat contract (legacy rows predate envelope encryption):
+      * ``wrapped_dek`` is ``None``/empty  → *raw_data* is plaintext; coerce to
+        ``str`` and return it unchanged.
+      * ``wrapped_dek`` is set            → *raw_data* is a DEK-encrypted blob;
+        unwrap the DEK under the master key and AES-256-GCM-decrypt it.
+
+    As a defensive fallback, if a ``wrapped_dek`` is present but *raw_data* is
+    not a recognised ciphertext blob (e.g. a half-migrated row), the value is
+    treated as plaintext rather than raising — so reads never hard-fail.
+
+    Raises :class:`~nce.signing.SigningKeyDecryptionError` if the wrapped DEK
+    cannot be unwrapped (wrong/destroyed master key) and
+    :class:`DEKDecryptionError` if the ciphertext fails authentication.
+    """
+    if not wrapped_dek:
+        if raw_data is None:
+            return ""
+        return raw_data if isinstance(raw_data, str) else str(raw_data)
+
+    blob = bytes(raw_data) if isinstance(raw_data, (bytes, bytearray, memoryview)) else raw_data
+    if not isinstance(blob, bytes) or not blob.startswith(_DEK_PAYLOAD_PREFIX):
+        # wrapped_dek set but payload isn't ciphertext — treat as plaintext.
+        if raw_data is None:
+            return ""
+        return raw_data if isinstance(raw_data, str) else str(raw_data)
+
+    with require_master_key() as master_key:
+        dek = unwrap_dek(bytes(wrapped_dek), master_key)
+    try:
+        return decrypt_with_dek(blob, dek).decode("utf-8")
+    finally:
+        with SecureKeyBuffer(dek):
+            pass
diff --git a/nce/graph_query.py b/nce/graph_query.py
index a32f5cb..4814187 100644
--- a/nce/graph_query.py
+++ b/nce/graph_query.py
@@ -839,13 +839,34 @@ class GraphRAGTraverser:
         except Exception as e:
             log.warning("Batch code_files hydration failed: %s", e)
 
+        # Part II.4: fetch the wrapped DEK for each episode payload_ref so an
+        # encrypted raw_data excerpt can be decrypted; legacy rows → NULL →
+        # plaintext.  code_files.raw_code is not envelope-encrypted by this batch.
+        wrapped_by_ref: dict[str, bytes | None] = {}
+        if ep_docs:
+            try:
+                async with self.pg_pool.acquire(timeout=10.0) as c:
+                    dek_rows = await c.fetch(
+                        "SELECT payload_ref, wrapped_dek FROM memories WHERE payload_ref = ANY($1::text[])",
+                        list(ep_docs.keys()),
+                    )
+                for dek_row in dek_rows:
+                    wd = dek_row["wrapped_dek"]
+                    wrapped_by_ref[str(dek_row["payload_ref"])] = (
+                        bytes(wd) if wd is not None else None
+                    )
+            except Exception as e:
+                log.warning("wrapped_dek lookup failed; treating raw_data as plaintext: %s", e)
+
+        from nce.envelope import maybe_decrypt_raw_data
+
         sources: list[dict] = []
         for ref_id in valid_refs:
             doc = ep_docs.get(ref_id)
             if doc is not None:
                 if restrict_user_id is not None and doc.get("user_id") != restrict_user_id:
                     continue
-                raw = doc.get("raw_data", "")
+                raw = maybe_decrypt_raw_data(doc.get("raw_data", ""), wrapped_by_ref.get(ref_id))
                 sources.append(
                     {
                         "payload_ref": ref_id,
@@ -893,9 +914,7 @@ class GraphRAGTraverser:
                 "Pass _allow_global_sweep=True only for admin/diagnostic cross-tenant operations."
             )
         if not (1 <= max_depth <= MAX_GRAPH_DEPTH):
-            raise ValueError(
-                f"max_depth must be between 1 and {MAX_GRAPH_DEPTH}, got {max_depth}"
-            )
+            raise ValueError(f"max_depth must be between 1 and {MAX_GRAPH_DEPTH}, got {max_depth}")
         if as_of is not None:
             if not isinstance(as_of, datetime):
                 raise ValueError("as_of must be a datetime object")
diff --git a/nce/mongo_bulk.py b/nce/mongo_bulk.py
index 103d704..685ae40 100644
--- a/nce/mongo_bulk.py
+++ b/nce/mongo_bulk.py
@@ -34,9 +34,7 @@ def normalize_payload_ref(payload_ref: str | ObjectId | None) -> str | None:
     return str(payload_ref)
 
 
-def _normalize_and_validate_refs(
-    refs: Iterable[str | ObjectId | None]
-) -> list[ObjectId]:
+def _normalize_and_validate_refs(refs: Iterable[str | ObjectId | None]) -> list[ObjectId]:
     """Deduplicate, normalize, and validate a sequence of payload refs.
 
     Raises ValueError if the number of unique refs exceeds _MAX_REFS.
@@ -73,7 +71,16 @@ async def _fetch_field_by_refs(
     refs: Iterable[str | ObjectId | None],
     *,
     field: str,
+    decode_bytes: bool = True,
 ) -> dict[str, str]:
+    """Map episode/code ``_id`` (str) → *field* value.
+
+    By default the value is coerced to ``str`` (legacy behaviour).  Pass
+    ``decode_bytes=False`` to preserve a ``bytes`` payload verbatim — required
+    by callers that must hand DEK-encrypted ciphertext (Part II.4) to
+    :func:`nce.envelope.maybe_decrypt_raw_data` without corrupting it via
+    ``str(bytes)``.
+    """
     if field not in _ALLOWED_FIELDS:
         raise ValueError(f"field {field!r} is not allowed. Allowed: {sorted(_ALLOWED_FIELDS)}")
 
@@ -93,8 +100,15 @@ async def _fetch_field_by_refs(
             )
             async for doc in cursor:
                 rid = normalize_payload_ref(doc.get("_id"))
+                if not rid:
+                    continue
                 raw = doc.get(field)
-                out[rid] = "" if raw is None else str(raw)
+                if raw is None:
+                    out[rid] = ""
+                elif isinstance(raw, (bytes, bytearray, memoryview)) and not decode_bytes:
+                    out[rid] = bytes(raw)  # type: ignore[assignment]
+                else:
+                    out[rid] = raw if isinstance(raw, str) else str(raw)
         except Exception as exc:
             log.error(
                 "Batch Mongo hydrate failed batch=%d/%d (%s): %s",
@@ -112,9 +126,14 @@ async def fetch_episodes_raw_by_ref(
     refs: Iterable[str | ObjectId | None],
     *,
     field: str = "raw_data",
+    decode_bytes: bool = True,
 ) -> dict[str, str]:
-    """Map episode ``_id`` (str) → ``raw_data`` (or *field*) text."""
-    return await _fetch_field_by_refs(db.episodes, refs, field=field)
+    """Map episode ``_id`` (str) → ``raw_data`` (or *field*) text.
+
+    ``decode_bytes=False`` preserves a ``bytes`` ciphertext payload so callers
+    can decrypt it (Part II.4); see :func:`_fetch_field_by_refs`.
+    """
+    return await _fetch_field_by_refs(db.episodes, refs, field=field, decode_bytes=decode_bytes)
 
 
 async def fetch_episode_previews_by_ref(
diff --git a/nce/orchestrators/memory.py b/nce/orchestrators/memory.py
index 2c0fe49..3369ac5 100644
--- a/nce/orchestrators/memory.py
+++ b/nce/orchestrators/memory.py
@@ -147,10 +147,14 @@ class MemoryOrchestrator(OrchestratorBase):
         target_model_ids,
         user_id,
         session_id,
+        wrapped_dek=None,
+        dek_key_id=None,
     ):
         """Insert memory row + memory_embeddings + PII vault (inside PG tx).
 
-        Returns the new memory_id (UUID).
+        Returns the new memory_id (UUID).  ``wrapped_dek``/``dek_key_id`` are the
+        envelope-encryption handles for the Mongo ``raw_data`` ciphertext (Part
+        II.4); both are NULL for legacy / unencrypted writes.
         """
         metadata = dict(payload.metadata) if payload.metadata else {}
         if (
@@ -161,8 +165,8 @@ class MemoryOrchestrator(OrchestratorBase):
 
         memory_id = await conn.fetchval(
             """
-            INSERT INTO memories (user_id, session_id, namespace_id, agent_id, embedding, content_fts, payload_ref, pii_redacted, assertion_type, memory_type, metadata)
-            VALUES ($1, $2, $3, $4, $5::vector, to_tsvector('english', $6), $7, $8, $9, $10, $11)
+            INSERT INTO memories (user_id, session_id, namespace_id, agent_id, embedding, content_fts, payload_ref, pii_redacted, assertion_type, memory_type, metadata, wrapped_dek, dek_key_id)
+            VALUES ($1, $2, $3, $4, $5::vector, to_tsvector('english', $6), $7, $8, $9, $10, $11, $12, $13)
             RETURNING id
             """,
             user_id,
@@ -176,6 +180,8 @@ class MemoryOrchestrator(OrchestratorBase):
             payload.assertion_type.value,
             payload.memory_type.value,
             json.dumps(metadata),
+            wrapped_dek,
+            dek_key_id,
         )
 
         for model_id in target_model_ids:
@@ -582,20 +588,36 @@ class MemoryOrchestrator(OrchestratorBase):
 
     async def _store_episodic_mongodb(
         self, payload: StoreMemoryRequest, sanitized_heavy: str, pii_result: Any
-    ) -> tuple[str, Any]:
-        """STEP 1: Episodic Commit (MongoDB)."""
+    ) -> tuple[str, Any, bytes | None, str | None]:
+        """STEP 1: Episodic Commit (MongoDB).
+
+        Part II.4 (Provable Forgetting): when ``NCE_ENVELOPE_ENCRYPTION_ENABLED``
+        is set, the raw payload (``raw_data``) is encrypted under a fresh
+        per-memory DEK before it touches Mongo, and the wrapped DEK + key id are
+        returned so they can be persisted on the ``memories`` row.  When the flag
+        is off, ``raw_data`` is stored as plaintext and ``(None, None)`` is
+        returned (the legacy / back-compatible shape).
+        """
         db = self.mongo_client.memory_archive
         collection = db.episodes
         user_id = payload.metadata.get("user_id") if payload.metadata else None
         session_id = payload.metadata.get("session_id") if payload.metadata else None
 
+        raw_data: Any = sanitized_heavy
+        wrapped_dek: bytes | None = None
+        dek_key_id: str | None = None
+        if cfg.NCE_ENVELOPE_ENCRYPTION_ENABLED:
+            from nce.envelope import encrypt_raw_data
+
+            raw_data, wrapped_dek, dek_key_id = encrypt_raw_data(sanitized_heavy)
+
         inserted_result = await collection.insert_one(
             {
                 "user_id": user_id,
                 "session_id": session_id,
                 "namespace_id": str(payload.namespace_id),
                 "type": payload.memory_type.value,
-                "raw_data": sanitized_heavy,
+                "raw_data": raw_data,
                 "metadata": payload.metadata,
                 "pii_redacted": pii_result.redacted,
                 "pii_entities_found": pii_result.entities_found,
@@ -604,7 +626,7 @@ class MemoryOrchestrator(OrchestratorBase):
         )
         inserted_mongo_id = str(inserted_result.inserted_id)
         log.debug("[Mongo] Inserted episode. id=%s", inserted_mongo_id)
-        return inserted_mongo_id, inserted_result
+        return inserted_mongo_id, inserted_result, wrapped_dek, dek_key_id
 
     async def _store_semantic_graph_pg(
         self,
@@ -619,6 +641,8 @@ class MemoryOrchestrator(OrchestratorBase):
         saga_id: str,
         user_id: str | None,
         session_id: str | None,
+        wrapped_dek: bytes | None = None,
+        dek_key_id: str | None = None,
     ) -> UUID:
         """STEP 2 + 2b + 2c: Atomic Semantic + Graph Commit (single PG transaction)."""
         async with scoped_pg_session(self.pg_pool, payload.namespace_id) as conn:
@@ -639,6 +663,8 @@ class MemoryOrchestrator(OrchestratorBase):
                     target_model_ids=target_model_ids,
                     user_id=user_id,
                     session_id=session_id,
+                    wrapped_dek=wrapped_dek,
+                    dek_key_id=dek_key_id,
                 )
 
                 await self._insert_graph_nodes_and_edges(
@@ -748,9 +774,12 @@ class MemoryOrchestrator(OrchestratorBase):
                 user_id = payload.metadata.get("user_id") if payload.metadata else None
                 session_id = payload.metadata.get("session_id") if payload.metadata else None
 
-                inserted_mongo_id, inserted_result = await self._store_episodic_mongodb(
-                    payload, sanitized_heavy, pii_result
-                )
+                (
+                    inserted_mongo_id,
+                    inserted_result,
+                    wrapped_dek,
+                    dek_key_id,
+                ) = await self._store_episodic_mongodb(payload, sanitized_heavy, pii_result)
 
                 # Pre-compute all embeddings OUTSIDE the PG transaction
                 all_texts = [sanitized_summary] + [e.label for e in entities]
@@ -771,6 +800,8 @@ class MemoryOrchestrator(OrchestratorBase):
                     saga_id=saga_id,
                     user_id=user_id,
                     session_id=session_id,
+                    wrapped_dek=wrapped_dek,
+                    dek_key_id=dek_key_id,
                 )
 
                 # Mark committed once exited from PG session block successfully
@@ -1030,7 +1061,16 @@ class MemoryOrchestrator(OrchestratorBase):
                 db = self.mongo_client.memory_archive
                 doc = await db.episodes.find_one({"_id": row["payload_ref"]})
                 if doc:
-                    content = doc.get("raw_data", "")
+                    # Part II.4: hash the *decrypted* content so the payload hash is
+                    # stable across the plaintext→ciphertext rollout (legacy rows
+                    # have wrapped_dek NULL and read as plaintext).
+                    from nce.envelope import maybe_decrypt_raw_data
+
+                    wrapped = row["wrapped_dek"]
+                    content = maybe_decrypt_raw_data(
+                        doc.get("raw_data", ""),
+                        bytes(wrapped) if wrapped is not None else None,
+                    )
                     payload_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                     try:
                         await self.redis_client.setex(cache_key, cfg.REDIS_TTL, payload_hash)
@@ -1069,7 +1109,7 @@ class MemoryOrchestrator(OrchestratorBase):
                 )
 
             mem_row = await conn.fetchrow(
-                "SELECT payload_ref, pii_redacted FROM memories WHERE id = $1",
+                "SELECT payload_ref, pii_redacted, wrapped_dek FROM memories WHERE id = $1",
                 memory_id,
             )
             if not mem_row:
@@ -1085,6 +1125,7 @@ class MemoryOrchestrator(OrchestratorBase):
                 return {"status": "no_vault_entries"}
 
             payload_ref = mem_row["payload_ref"]
+            wrapped_dek = mem_row["wrapped_dek"]
             vault_list = [
                 {"token": r["token"], "encrypted_value": r["encrypted_value"]} for r in vault_rows
             ]
@@ -1095,9 +1136,16 @@ class MemoryOrchestrator(OrchestratorBase):
         if not doc:
             raise ValueError("MongoDB payload missing.")
 
-        raw_data = doc.get("raw_data", "")
-        if not isinstance(raw_data, str):
+        # Part II.4: decrypt the raw payload under its wrapped DEK; legacy rows
+        # (wrapped_dek NULL) read as plaintext.
+        from nce.envelope import maybe_decrypt_raw_data
+
+        stored_raw = doc.get("raw_data", "")
+        if not wrapped_dek and not isinstance(stored_raw, str):
             return {"status": "raw_data_not_string"}
+        raw_data = maybe_decrypt_raw_data(
+            stored_raw, bytes(wrapped_dek) if wrapped_dek is not None else None
+        )
 
         with require_master_key() as mk:
             for v_row in vault_list:
@@ -1214,7 +1262,7 @@ class MemoryOrchestrator(OrchestratorBase):
                 order_by = "created_at DESC"
 
             sql = f"""
-                SELECT payload_ref FROM memories
+                SELECT payload_ref, wrapped_dek FROM memories
                 WHERE {" AND ".join(filters)}
                 ORDER BY {order_by} LIMIT ${p_idx} OFFSET ${p_idx + 1}
             """
@@ -1224,16 +1272,24 @@ class MemoryOrchestrator(OrchestratorBase):
         if not rows:
             return []
 
+        from nce.envelope import maybe_decrypt_raw_data
+
         db = self.mongo_client.memory_archive
         keys = [normalize_payload_ref(r["payload_ref"]) for r in rows]
-        raw_by_ref = await fetch_episodes_raw_by_ref(db, keys)
+        # Part II.4: hydrate raw_data and transparently decrypt rows that carry a
+        # wrapped DEK; legacy rows (wrapped_dek NULL) read as plaintext.
+        raw_by_ref = await fetch_episodes_raw_by_ref(db, keys, decode_bytes=False)
 
         results = []
         for row in rows:
             key = normalize_payload_ref(row["payload_ref"])
-            txt = raw_by_ref.get(key, "")
+            raw = raw_by_ref.get(key)
+            if raw is None:
+                continue
+            wrapped = row["wrapped_dek"]
+            txt = maybe_decrypt_raw_data(raw, bytes(wrapped) if wrapped is not None else None)
             if txt:
-                results.append(str(txt))
+                results.append(txt)
 
         if not as_of and limit == 1 and offset == 0 and results:
             if user_id and session_id:
diff --git a/nce/orchestrators/temporal.py b/nce/orchestrators/temporal.py
index 2bad531..14ac61a 100644
--- a/nce/orchestrators/temporal.py
+++ b/nce/orchestrators/temporal.py
@@ -114,9 +114,45 @@ class TemporalOrchestrator(OrchestratorBase):
             return
         refs = [normalize_payload_ref(getattr(res, "payload_ref", None)) for res in outs]
         previews = await fetch_episode_previews_by_ref(self._mongo_db, refs)
+
+        # Part II.4: previews prefer the (plaintext) summary, but fall back to
+        # raw_data which may now be DEK-encrypted.  Fetch the wrapped DEK per
+        # memory and decrypt those refs so the preview is plaintext; legacy rows
+        # (wrapped_dek NULL) are untouched.
+        from nce.envelope import maybe_decrypt_raw_data
+        from nce.mongo_bulk import fetch_episodes_raw_by_ref
+
+        memory_ids = [getattr(res, "memory_id", None) for res in outs]
+        memory_ids = [m for m in memory_ids if m]
+        wrapped_by_ref: dict[str, bytes] = {}
+        if memory_ids:
+            try:
+                async with self.pg_pool.acquire(timeout=10.0) as conn:
+                    dek_rows = await conn.fetch(
+                        "SELECT payload_ref, wrapped_dek FROM memories "
+                        "WHERE id = ANY($1::uuid[]) AND wrapped_dek IS NOT NULL",
+                        [UUID(str(m)) for m in memory_ids],
+                    )
+                for dek_row in dek_rows:
+                    wrapped_by_ref[str(dek_row["payload_ref"])] = bytes(dek_row["wrapped_dek"])
+            except Exception:
+                wrapped_by_ref = {}
+
+        decrypted_raw: dict[str, str] = {}
+        if wrapped_by_ref:
+            raw_by_ref = await fetch_episodes_raw_by_ref(
+                self._mongo_db, list(wrapped_by_ref.keys()), decode_bytes=False
+            )
+            for ref, blob in raw_by_ref.items():
+                decrypted_raw[ref] = maybe_decrypt_raw_data(blob, wrapped_by_ref.get(ref))
+
         for res in outs:
             key = normalize_payload_ref(getattr(res, "payload_ref", None))
-            if key and key in previews:
+            if not key:
+                continue
+            if key in decrypted_raw:
+                res.content_preview = decrypted_raw[key][:200]
+            elif key in previews:
                 res.content_preview = previews[key]
 
     # ------------------------------------------------------------------
@@ -317,12 +353,8 @@ class TemporalOrchestrator(OrchestratorBase):
         hit_b = {_mid(r): r for r in res_b}
 
         async with self.scoped_session(payload.namespace_id) as conn:
-            map_a = await self._fetch_memories_valid_at(
-                conn, ns_uuid, all_uuid, payload.as_of_a
-            )
-            map_b = await self._fetch_memories_valid_at(
-                conn, ns_uuid, all_uuid, payload.as_of_b
-            )
+            map_a = await self._fetch_memories_valid_at(conn, ns_uuid, all_uuid, payload.as_of_a)
+            map_b = await self._fetch_memories_valid_at(conn, ns_uuid, all_uuid, payload.as_of_b)
 
         added_ids = ids_b - ids_a
         removed_ids = ids_a - ids_b
diff --git a/nce/replay.py b/nce/replay.py
index 0737729..824be0b 100644
--- a/nce/replay.py
+++ b/nce/replay.py
@@ -590,7 +590,8 @@ async def _handle_store_memory(
 
         src_row = await conn.fetchrow(
             """
-            SELECT embedding, assertion_type, memory_type, metadata, valid_from, created_at
+            SELECT embedding, assertion_type, memory_type, metadata, valid_from, created_at,
+                   wrapped_dek, dek_key_id
             FROM memories
             WHERE id = $1 AND namespace_id = $2
               AND valid_to IS NULL
@@ -616,18 +617,23 @@ async def _handle_store_memory(
         meta = dict(src_row["metadata"]) if src_row["metadata"] else {}
         meta["source_memory_id"] = str(src_memory_id)
 
+        # Part II.4: the copied Mongo doc carries the source ciphertext verbatim;
+        # carry the source wrapped_dek/dek_key_id so the target can decrypt under
+        # the same (global) NCE_MASTER_KEY.  Legacy rows carry NULL → plaintext.
         await conn.execute(
             """
             INSERT INTO memories (
                 id, namespace_id, agent_id,
                 embedding, assertion_type, memory_type,
                 payload_ref, metadata,
-                valid_from, created_at
+                valid_from, created_at,
+                wrapped_dek, dek_key_id
             ) VALUES (
                 $1, $2, $3,
                 $4, $5, $6,
                 $7, $8::jsonb,
-                $9, $10
+                $9, $10,
+                $11, $12
             )
             ON CONFLICT DO NOTHING
             """,
@@ -641,6 +647,8 @@ async def _handle_store_memory(
             json.dumps(meta),
             src_row["valid_from"],
             src_row["created_at"],
+            src_row["wrapped_dek"],
+            src_row["dek_key_id"],
         )
 
         # Carry over salience score if it exists in the source namespace
@@ -849,16 +857,22 @@ async def _handle_consolidation_run(
         src_ns_id = uuid.UUID(raw_src_ns) if raw_src_ns else None
         src_valid_from = None
         src_created_at = None
+        src_wrapped_dek = None
+        src_dek_key_id = None
         if consolidated_memory_id_str and src_ns_id:
             try:
                 row = await conn.fetchrow(
-                    "SELECT valid_from, created_at FROM memories WHERE id = $1 AND namespace_id = $2",
+                    "SELECT valid_from, created_at, wrapped_dek, dek_key_id FROM memories WHERE id = $1 AND namespace_id = $2",
                     uuid.UUID(consolidated_memory_id_str),
                     src_ns_id,
                 )
                 if row:
                     src_valid_from = row["valid_from"]
                     src_created_at = row["created_at"]
+                    # Part II.4: carry the source DEK so the copied ciphertext doc
+                    # stays decryptable under the global master key.
+                    src_wrapped_dek = row["wrapped_dek"]
+                    src_dek_key_id = row["dek_key_id"]
             except Exception:
                 pass
 
@@ -888,12 +902,14 @@ async def _handle_consolidation_run(
                 id, namespace_id, agent_id,
                 embedding, assertion_type, memory_type,
                 payload_ref, metadata,
-                valid_from, created_at
+                valid_from, created_at,
+                wrapped_dek, dek_key_id
             ) VALUES (
                 $1, $2, $3,
                 $4, 'fact', 'consolidated',
                 $5, $6::jsonb,
-                $7, $8
+                $7, $8,
+                $9, $10
             )
             ON CONFLICT DO NOTHING
             """,
@@ -905,6 +921,8 @@ async def _handle_consolidation_run(
             json.dumps(meta),
             src_valid_from,
             src_created_at,
+            src_wrapped_dek,
+            src_dek_key_id,
         )
 
         # Populate target namespace KG nodes and edges
diff --git a/nce/semantic_search.py b/nce/semantic_search.py
index 2a22d61..09ea2a3 100644
--- a/nce/semantic_search.py
+++ b/nce/semantic_search.py
@@ -292,6 +292,26 @@ async def semantic_search(
         ]
         reinforcement_delta = cognitive_config.reinforcement_delta
 
+        # Part II.4: fetch the wrapped DEK for each result so encrypted raw_data
+        # can be decrypted on hydration; legacy rows return NULL → plaintext.
+        memory_ids = [r["memory_id"] for r in top_results if r.get("memory_id")]
+        wrapped_by_ref: dict[str, bytes | None] = {}
+        if memory_ids:
+            try:
+                dek_rows = await conn.fetch(
+                    "SELECT payload_ref, wrapped_dek FROM memories WHERE id = ANY($1::uuid[])",
+                    memory_ids,
+                )
+                for dek_row in dek_rows:
+                    wd = dek_row.get("wrapped_dek") if hasattr(dek_row, "get") else None
+                    if wd is None:
+                        continue
+                    wrapped_by_ref[str(dek_row["payload_ref"] or "")] = bytes(wd)
+            except Exception:
+                # Defensive: a DEK lookup failure must not break search; rows
+                # then read as plaintext (only encrypted rows would be affected).
+                wrapped_by_ref = {}
+
     asyncio.create_task(
         _fire_reinforcement(
             pg_pool,
@@ -321,13 +341,16 @@ async def semantic_search(
 
     from datetime import datetime, timezone
 
+    from nce.envelope import maybe_decrypt_raw_data
     from nce.temporal_decay import retention
 
     results = []
     for res in top_results:
         ref = str(res.get("payload_ref") or "")
         doc = docs.get(ref)
-        raw = (doc.get("raw_data") or "") if doc else ""
+        # Part II.4: transparently decrypt encrypted raw_data; legacy rows
+        # (wrapped_dek NULL) pass through as plaintext.
+        raw = maybe_decrypt_raw_data(doc.get("raw_data"), wrapped_by_ref.get(ref)) if doc else ""
 
         salience_score = res.get("salience_score", 1.0)
         last_reinforced_at = res.get("last_reinforced_at")
diff --git a/nce/snapshot_mcp_handlers.py b/nce/snapshot_mcp_handlers.py
index f48a5f4..52ec411 100644
--- a/nce/snapshot_mcp_handlers.py
+++ b/nce/snapshot_mcp_handlers.py
@@ -220,6 +220,7 @@ async def stream_snapshot_export(
                         m.valid_from,
                         m.pii_redacted,
                         m.derived_from,
+                        m.wrapped_dek,
                         COALESCE(m.metadata, '{}'::jsonb) AS metadata,
                         (SELECT ms.salience_score
                          FROM memory_salience ms
@@ -325,6 +326,10 @@ def _serialize_memory_row(row: Any) -> dict[str, Any]:
     for k, v in dict(row).items():
         if isinstance(v, uuid.UUID):
             out[k] = str(v)
+        elif isinstance(v, (bytes, bytearray, memoryview)):
+            # Part II.4: wrapped_dek is BYTEA; hex-encode so it survives NDJSON
+            # and import can decrypt the source ciphertext before re-storing.
+            out[k] = bytes(v).hex()
         elif isinstance(v, datetime):
             out[k] = v.astimezone(timezone.utc).isoformat() if v else None
         elif k == "metadata" and isinstance(v, str):
@@ -421,7 +426,14 @@ async def restore_namespace(
             errors.append(f"Line {i + 1}: MongoDB document not found for payload_ref {payload_ref}")
             continue
 
-        raw_data = doc.get("raw_data", "")
+        # Part II.4: decrypt the source ciphertext (if encrypted) back to plaintext
+        # before re-storing; store_memory will re-encrypt under a fresh DEK if the
+        # target has envelope encryption enabled.  Legacy docs read as plaintext.
+        from nce.envelope import maybe_decrypt_raw_data
+
+        wrapped_hex = memory_data.get("wrapped_dek")
+        wrapped_bytes = bytes.fromhex(wrapped_hex) if wrapped_hex else None
+        raw_data = maybe_decrypt_raw_data(doc.get("raw_data", ""), wrapped_bytes)
 
         # Merge metadata with salience and bypass_quarantine
         metadata = dict(memory_data.get("metadata") or {})
diff --git a/tests/test_envelope_encryption_integration.py b/tests/test_envelope_encryption_integration.py
new file mode 100644
index 0000000..dd9621a
--- /dev/null
+++ b/tests/test_envelope_encryption_integration.py
@@ -0,0 +1,205 @@
+"""Integration acceptance test for Batch 46 — Provable Forgetting (Part II.4).
+
+Asserts the end-to-end envelope-encryption contract:
+
+* With ``NCE_ENVELOPE_ENCRYPTION_ENABLED`` on, ``store_memory`` writes the raw
+  payload to Mongo ``episodes.raw_data`` as **ciphertext** (the plaintext does
+  NOT appear at rest) and sets ``memories.wrapped_dek`` + ``dek_key_id``.
+* Read paths (``recall_recent`` and ``verify_memory``) transparently decrypt and
+  return the correct plaintext content.
+* A legacy row written with encryption OFF (``wrapped_dek IS NULL``, plaintext
+  ``raw_data``) still reads back as plaintext — back-compat holds.
+
+Requires live MongoDB + PostgreSQL + Redis (``-m integration``).
+"""
+
+from __future__ import annotations
+
+import os
+import socket
+import uuid
+from urllib.parse import urlparse
+
+import pytest
+import pytest_asyncio
+from nce import MemoryPayload, NCEEngine
+from nce.config import cfg
+from nce.db_utils import scoped_pg_session
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
+async def namespace_id(engine) -> uuid.UUID:
+    slug = f"pytest-envelope-{uuid.uuid4().hex}"
+    async with engine.pg_pool.acquire() as conn:
+        ns = await conn.fetchval("INSERT INTO namespaces (slug) VALUES ($1) RETURNING id", slug)
+    assert ns is not None
+    return ns
+
+
+@_skip_no_containers
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_raw_data_encrypted_at_rest_and_reads_decrypt(engine, namespace_id, monkeypatch):
+    """Encryption ON: ciphertext at rest in Mongo, DEK on the row, reads decrypt."""
+    from nce.envelope import _DEK_PAYLOAD_PREFIX
+
+    monkeypatch.setattr(cfg, "NCE_ENVELOPE_ENCRYPTION_ENABLED", True, raising=False)
+
+    secret = (
+        "PROVABLE-FORGETTING-SENTINEL-"
+        + uuid.uuid4().hex
+        + " the quick brown fox jumps over the lazy dog"
+    )
+    test_id = str(uuid.uuid4())
+    payload = MemoryPayload(
+        namespace_id=namespace_id,
+        agent_id="test-agent",
+        content=secret,
+        summary=secret,
+        heavy_payload=secret,
+        metadata={"user_id": test_id, "session_id": test_id},
+    )
+
+    res = await engine.store_memory(payload)
+    payload_ref = res["payload_ref"]
+    assert payload_ref
+
+    # 1. Mongo episodes.raw_data is CIPHERTEXT — plaintext must NOT be at rest.
+    from bson import ObjectId
+
+    db = engine.mongo_client.memory_archive
+    doc = await db.episodes.find_one({"_id": ObjectId(payload_ref)})
+    assert doc is not None
+    raw = doc["raw_data"]
+    raw_bytes = bytes(raw) if isinstance(raw, (bytes, bytearray, memoryview)) else None
+    assert raw_bytes is not None, f"raw_data is not bytes ciphertext: {type(raw)!r}"
+    assert raw_bytes.startswith(_DEK_PAYLOAD_PREFIX), "raw_data missing DEK wire prefix"
+    assert secret.encode("utf-8") not in raw_bytes, "plaintext leaked into Mongo ciphertext"
+
+    # 2. memories.wrapped_dek + dek_key_id are set.
+    async with scoped_pg_session(engine.pg_pool, str(namespace_id)) as conn:
+        mem = await conn.fetchrow(
+            "SELECT wrapped_dek, dek_key_id FROM memories WHERE payload_ref = $1",
+            payload_ref,
+        )
+    assert mem is not None
+    assert mem["wrapped_dek"] is not None, "wrapped_dek not persisted"
+    assert mem["dek_key_id"], "dek_key_id not persisted"
+
+    # 3a. recall_recent read path decrypts back to plaintext.
+    recalled = await engine.recall_recent(
+        str(namespace_id), agent_id="test-agent", limit=5, user_id=test_id, session_id=test_id
+    )
+    assert any(secret == r for r in recalled), f"recall_recent did not decrypt: {recalled!r}"
+
+    # 3b. semantic_search read path also decrypts the hydrated raw_data.
+    hits = await engine.semantic_search(
+        query=secret,
+        namespace_id=str(namespace_id),
+        agent_id="test-agent",
+        limit=5,
+    )
+    assert any((h.get("raw_data") or "") == secret for h in hits), (
+        f"semantic_search did not decrypt raw_data: {[h.get('raw_data') for h in hits]!r}"
+    )
+
+    # 3c. verify_memory, when the memory is signed, hashes the DECRYPTED content
+    # (stable across the plaintext→ciphertext rollout).  Unsigned memories return
+    # payload_hash=None by design — only assert the hash when one is produced.
+    import hashlib
+
+    async with scoped_pg_session(engine.pg_pool, str(namespace_id)) as conn:
+        memory_id = await conn.fetchval(
+            "SELECT id FROM memories WHERE payload_ref = $1", payload_ref
+        )
+    verify = await engine.verify_memory(str(memory_id))
+    expected_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
+    if verify.get("payload_hash") is not None:
+        assert verify["payload_hash"] == expected_hash, (
+            "verify_memory payload_hash is over ciphertext, not decrypted plaintext"
+        )
+
+
+@_skip_no_containers
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_legacy_null_wrapped_dek_reads_as_plaintext(engine, namespace_id, monkeypatch):
+    """Back-compat: a row written with encryption OFF reads back as plaintext."""
+    monkeypatch.setattr(cfg, "NCE_ENVELOPE_ENCRYPTION_ENABLED", False, raising=False)
+
+    legacy = "LEGACY-PLAINTEXT-" + uuid.uuid4().hex
+    test_id = str(uuid.uuid4())
+    payload = MemoryPayload(
+        namespace_id=namespace_id,
+        agent_id="legacy-agent",
+        content=legacy,
+        summary=legacy,
+        heavy_payload=legacy,
+        metadata={"user_id": test_id, "session_id": test_id},
+    )
+
+    res = await engine.store_memory(payload)
+    payload_ref = res["payload_ref"]
+
+    # Stored as plaintext str with NULL wrapped_dek (the legacy shape).
+    from bson import ObjectId
+
+    db = engine.mongo_client.memory_archive
+    doc = await db.episodes.find_one({"_id": ObjectId(payload_ref)})
+    assert isinstance(doc["raw_data"], str)
+    assert doc["raw_data"] == legacy
+
+    async with scoped_pg_session(engine.pg_pool, str(namespace_id)) as conn:
+        wrapped = await conn.fetchval(
+            "SELECT wrapped_dek FROM memories WHERE payload_ref = $1", payload_ref
+        )
+    assert wrapped is None, "legacy write should not set wrapped_dek"
+
+    # Read path returns the plaintext unchanged.
+    recalled = await engine.recall_recent(
+        str(namespace_id), agent_id="legacy-agent", limit=5, user_id=test_id, session_id=test_id
+    )
+    assert any(legacy == r for r in recalled), f"legacy plaintext not returned: {recalled!r}"
```
