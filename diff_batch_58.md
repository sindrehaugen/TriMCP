# Diff Reference for Batch 58

```diff
diff --git a/nce/garbage_collector.py b/nce/garbage_collector.py
index 9ca034e..ba15a45 100644
--- a/nce/garbage_collector.py
+++ b/nce/garbage_collector.py
@@ -24,7 +24,7 @@ from motor.motor_asyncio import AsyncIOMotorClient
 
 from nce.auth import set_namespace_context
 from nce.config import cfg, redact_secrets_in_text
-from nce.db_utils import resolve_worker_dsn
+from nce.db_utils import resolve_worker_dsn, scoped_pg_session
 from nce.redis_lock import acquire_lock as _acquire_redis_lock
 from nce.redis_lock import release_lock as _release_redis_lock
 
@@ -66,6 +66,12 @@ MAX_CONNECT_ATTEMPTS = cfg.GC_MAX_CONNECT_ATTEMPTS
 CONNECT_BASE_DELAY = cfg.GC_CONNECT_BASE_DELAY  # seconds; doubles each retry
 CHUNK_DELETE_SIZE = 1000  # rows deleted per chunk to prevent table locks
 
+# R-B reverse sweep: hard ceiling on dangling refs repaired per namespace per
+# pass, so a corrupt namespace can never turn one GC tick into an unbounded
+# scan/repair storm. Excess refs are surfaced via an alert and picked up next
+# pass.
+REVERSE_SWEEP_MAX_PER_NS = 5000
+
 
 # --- Connection helpers with retry ---
 
@@ -335,6 +341,183 @@ async def _clean_orphaned_cascade(
     return totals
 
 
+# --- Reverse integrity sweep (R-B): PG ref → missing Mongo doc ---
+
+
+async def _dispatch_reverse_alert(title: str, message: str) -> None:
+    """Fail-safe operator alert. A notification failure must never break the sweep."""
+    try:
+        from nce.notifications import dispatcher
+
+        await dispatcher.dispatch_alert(title, message)
+    except Exception as exc:  # pragma: no cover - defensive, alerting is best-effort
+        log.error("GC reverse sweep: alert dispatch failed: %s", type(exc).__name__)
+
+
+async def _fetch_reverse_candidates(
+    pg_pool: asyncpg.Pool,
+    namespace_id: UUID,
+    cutoff: datetime,
+) -> list[tuple[UUID, str]]:
+    """Collect live ``memories`` (id, payload_ref) for one namespace, RLS-scoped.
+
+    Bounded by ``REVERSE_SWEEP_MAX_PER_NS`` and keyset-paginated.  Only rows
+    older than ``cutoff`` and not already soft-retired (``valid_to IS NULL``)
+    are considered, mirroring the forward GC's orphan-age guard so a payload
+    written mid-saga is never mistaken for a dangling reference.
+
+    Mongo existence is NOT checked here — that slow I/O is deliberately kept
+    outside the scoped transaction (see ``scoped_pg_session`` warning).
+    """
+    candidates: list[tuple[UUID, str]] = []
+    last_seen_id = UUID(int=0)
+
+    async with scoped_pg_session(pg_pool, namespace_id) as conn:
+        while len(candidates) < REVERSE_SWEEP_MAX_PER_NS:
+            rows = await conn.fetch(
+                """
+                SELECT id, payload_ref
+                FROM   memories
+                WHERE  namespace_id = $1::uuid
+                  AND  payload_ref IS NOT NULL
+                  AND  valid_to IS NULL
+                  AND  created_at < $2
+                  AND  id > $3
+                ORDER BY id
+                LIMIT  $4
+                """,
+                namespace_id,
+                cutoff,
+                last_seen_id,
+                PAGE_SIZE,
+            )
+            if not rows:
+                break
+            for row in rows:
+                candidates.append((row["id"], row["payload_ref"]))
+            last_seen_id = rows[-1]["id"]
+            if len(rows) < PAGE_SIZE:
+                break  # last page
+
+    return candidates
+
+
+async def _soft_retire_dangling(
+    pg_pool: asyncpg.Pool,
+    namespace_id: UUID,
+    memory_id: UUID,
+) -> bool:
+    """Soft-retire one dangling memory (``valid_to = now()``), RLS-scoped.
+
+    Returns True when a live row was retired.  Uses ``UPDATE … SET valid_to``
+    (never DELETE) so the WORM ``event_log`` and the row itself are preserved
+    for forensic audit / replay-based rebuild.  An explicit ``namespace_id``
+    filter backs up RLS as defence-in-depth.
+    """
+    async with scoped_pg_session(pg_pool, namespace_id) as conn:
+        result = await conn.execute(
+            """
+            UPDATE memories
+            SET    valid_to = now()
+            WHERE  id = $1::uuid
+              AND  namespace_id = $2::uuid
+              AND  valid_to IS NULL
+            """,
+            memory_id,
+            namespace_id,
+        )
+    # asyncpg returns e.g. "UPDATE 1"; treat any non-zero count as retired.
+    return result.rsplit(" ", 1)[-1] != "0"
+
+
+async def _collect_reverse_orphans(
+    mongo_client: AsyncIOMotorClient,
+    pg_pool: asyncpg.Pool,
+    namespaces: list[UUID],
+) -> int:
+    """Mirror of the forward GC: detect+repair PG memories with a missing Mongo doc.
+
+    For each namespace (RLS-scoped) scan live ``memories.payload_ref`` values,
+    look up the matching ``episodes`` document in MongoDB, and for every
+    dangling reference soft-retire the memory (``valid_to = now()``), dispatch
+    a fail-safe operator alert, and log it auditably.  Today the read path only
+    raises ``ValueError("MongoDB payload missing.")`` reactively; this proactively
+    converges the R-A dangling-ref state.
+
+    Returns the number of memories soft-retired across all namespaces.
+    """
+    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cfg.GC_ORPHAN_AGE_SECONDS)
+    # Subscript access (db["episodes"]) mirrors the forward sweep and matches the
+    # MagicMock dict used in unit tests.
+    episodes = mongo_client.memory_archive["episodes"]
+    retired = 0
+
+    for ns_id in namespaces:
+        try:
+            candidates = await _fetch_reverse_candidates(pg_pool, ns_id, cutoff)
+        except Exception as exc:
+            log.error(
+                "GC reverse sweep: failed to fetch candidates for ns=%s: %s",
+                ns_id,
+                type(exc).__name__,
+            )
+            continue
+
+        if len(candidates) >= REVERSE_SWEEP_MAX_PER_NS:
+            await _dispatch_reverse_alert(
+                "GC reverse sweep bounded",
+                f"Namespace {ns_id} hit the reverse-sweep cap "
+                f"({REVERSE_SWEEP_MAX_PER_NS}); remaining refs deferred to the next pass.",
+            )
+
+        for memory_id, payload_ref in candidates:
+            try:
+                doc = await episodes.find_one({"_id": ObjectId(payload_ref)}, {"_id": 1})
+            except Exception as exc:
+                # Malformed ObjectId or a transient Mongo error: skip — never
+                # soft-retire on uncertainty.
+                log.error(
+                    "GC reverse sweep: Mongo lookup failed for memory=%s ns=%s: %s",
+                    memory_id,
+                    ns_id,
+                    type(exc).__name__,
+                )
+                continue
+
+            if doc is not None:
+                continue  # healthy — Mongo doc present, leave untouched
+
+            try:
+                did_retire = await _soft_retire_dangling(pg_pool, ns_id, memory_id)
+            except Exception as exc:
+                log.error(
+                    "GC reverse sweep: soft-retire failed for memory=%s ns=%s: %s",
+                    memory_id,
+                    ns_id,
+                    type(exc).__name__,
+                )
+                continue
+
+            if did_retire:
+                retired += 1
+                log.warning(
+                    "GC reverse sweep: soft-retired dangling memory=%s ns=%s "
+                    "(payload_ref=%s missing in Mongo episodes).",
+                    memory_id,
+                    ns_id,
+                    payload_ref,
+                )
+                await _dispatch_reverse_alert(
+                    "Dangling memory payload",
+                    f"Memory {memory_id} (namespace {ns_id}) referenced a missing "
+                    f"MongoDB episodes document and was soft-retired (valid_to set).",
+                )
+
+    if retired:
+        log.warning("GC reverse sweep: soft-retired %d dangling memory(ies).", retired)
+    return retired
+
+
 # --- Core GC pass ---
 
 
@@ -564,15 +747,24 @@ async def _collect_orphans(
             total_contradictions,
         )
 
+    # --- Reverse integrity sweep (R-B) ---
+    # Mirror of the forward sweep above: scan PG memories for payload_refs whose
+    # MongoDB episodes document is missing, soft-retire them, and alert.  Runs on
+    # the same GC cadence and over the same namespace set.
+    reverse_retired = await _collect_reverse_orphans(mongo_client, pg_pool, namespaces)
+
     log.info(
-        "GC: pass complete — %d Mongo orphan(s), %d MinIO orphan(s) removed.",
+        "GC: pass complete — %d Mongo orphan(s), %d MinIO orphan(s) removed, "
+        "%d dangling memory(ies) soft-retired.",
         deleted,
         deleted_minio,
+        reverse_retired,
     )
     ret = {
         "deleted_docs": deleted,
         "deleted_salience": total_salience,
         "deleted_contradictions": total_contradictions,
+        "reverse_retired": reverse_retired,
     }
     if minio_client is not None:
         ret["deleted_minio"] = deleted_minio
diff --git a/tests/test_garbage_collector.py b/tests/test_garbage_collector.py
index d8ff936..5c096a8 100644
--- a/tests/test_garbage_collector.py
+++ b/tests/test_garbage_collector.py
@@ -720,3 +720,125 @@ async def test_collect_minio_orphans_sweeps_incomplete_uploads():
         "mcp-test-bucket", "stale-upload", "stale-id"
     )
     assert count == 1
+
+
+# ---------------------------------------------------------------------------
+# Batch 58 — R-B reverse integrity sweep (PG ref → missing Mongo doc)
+# ---------------------------------------------------------------------------
+
+
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_reverse_sweep_soft_retires_dangling_and_leaves_healthy(
+    pg_pool, make_namespace
+) -> None:
+    """R-B: a memory whose Mongo episodes doc is missing is soft-retired + alerted;
+    a memory whose Mongo doc is present is left untouched.
+
+    Exercises real Postgres (RLS-scoped UPDATE valid_to) and real MongoDB, then
+    asserts persisted DB state — not just that a function was called.
+    """
+    import os
+    from datetime import datetime, timedelta
+
+    from bson import ObjectId
+    from motor.motor_asyncio import AsyncIOMotorClient
+    from nce.db_utils import scoped_pg_session
+    from nce.garbage_collector import _collect_reverse_orphans
+
+    ns_id = await make_namespace()
+    agent_id = "test-reverse-sweep-agent"
+
+    # created_at must be older than the orphan-age cutoff so the sweep considers
+    # the rows (mirrors the forward GC's freshly-written-payload guard).
+    old_created = datetime.now(timezone.utc) - timedelta(days=365)
+
+    # Healthy memory: Mongo episodes doc exists.
+    healthy_oid = ObjectId()
+    healthy_ref = str(healthy_oid)
+    healthy_memory_id = uuid4()
+
+    # Dangling memory: payload_ref points at an ObjectId never written to Mongo.
+    dangling_oid = ObjectId()
+    dangling_ref = str(dangling_oid)
+    dangling_memory_id = uuid4()
+
+    mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
+    mongo_client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5_000)
+    try:
+        try:
+            await mongo_client.admin.command("ping")
+        except Exception as exc:  # noqa: BLE001 - skip if Mongo unreachable
+            pytest.skip(f"MongoDB not reachable for integration test: {exc}")
+
+        db = mongo_client.memory_archive
+        # Insert ONLY the healthy doc; the dangling ref is intentionally absent.
+        await db.episodes.insert_one(
+            {"_id": healthy_oid, "raw_data": "present", "source": "test_reverse_sweep"}
+        )
+
+        try:
+            async with scoped_pg_session(pg_pool, ns_id) as conn:
+                await conn.execute(
+                    """
+                    INSERT INTO memories (id, namespace_id, agent_id,
+                                          assertion_type, memory_type, payload_ref,
+                                          metadata, created_at)
+                    VALUES
+                        ($1, $3, $4, 'fact', 'episodic', $5, '{}'::jsonb, $7),
+                        ($2, $3, $4, 'fact', 'episodic', $6, '{}'::jsonb, $7)
+                    """,
+                    healthy_memory_id,
+                    dangling_memory_id,
+                    ns_id,
+                    agent_id,
+                    healthy_ref,
+                    dangling_ref,
+                    old_created,
+                )
+
+            # Patch the operator alert so we can assert it fired without I/O.
+            alert_mock = AsyncMock()
+            with patch("nce.notifications.dispatcher.dispatch_alert", alert_mock):
+                retired = await _collect_reverse_orphans(mongo_client, pg_pool, [ns_id])
+
+            # Exactly the dangling memory was soft-retired.
+            assert retired == 1
+
+            async with scoped_pg_session(pg_pool, ns_id) as conn:
+                dangling_valid_to = await conn.fetchval(
+                    "SELECT valid_to FROM memories WHERE id = $1 AND namespace_id = $2",
+                    dangling_memory_id,
+                    ns_id,
+                )
+                healthy_valid_to = await conn.fetchval(
+                    "SELECT valid_to FROM memories WHERE id = $1 AND namespace_id = $2",
+                    healthy_memory_id,
+                    ns_id,
+                )
+
+            # Dangling row soft-retired (valid_to set); healthy row untouched.
+            assert dangling_valid_to is not None, "dangling memory must be soft-retired"
+            assert healthy_valid_to is None, "healthy memory must be left untouched"
+
+            # An operator alert was dispatched naming the dangling memory.
+            assert alert_mock.await_count >= 1
+            dispatched_text = " ".join(
+                str(arg) for call in alert_mock.await_args_list for arg in call.args
+            )
+            assert str(dangling_memory_id) in dispatched_text
+            assert str(healthy_memory_id) not in dispatched_text
+        finally:
+            # Clean up PG rows (best-effort) and the healthy Mongo doc.
+            try:
+                async with scoped_pg_session(pg_pool, ns_id) as conn:
+                    await conn.execute(
+                        "DELETE FROM memories WHERE namespace_id = $1 AND id = ANY($2::uuid[])",
+                        ns_id,
+                        [healthy_memory_id, dangling_memory_id],
+                    )
+            except Exception:
+                pass
+            await db.episodes.delete_one({"_id": healthy_oid})
+    finally:
+        mongo_client.close()
```
