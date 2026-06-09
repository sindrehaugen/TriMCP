# Diff Reference for Batch 29

```diff
diff --git a/RL.md b/RL.md
index f6c269f..a340657 100644
--- a/RL.md
+++ b/RL.md
@@ -35,8 +35,8 @@
 * [DONE] Batch 25 — Wire do-calculus circuit escalation (Phase 4.2) [PASSED TAG]
 * [DONE] Batch 26 — Snapshot import / restore (III.2) [PASSED TAG]
 * [DONE] Batch 27 — Deterministic identity remap (uuid5) in replay (Phase 2.1) [PASSED TAG]
-* [RUNNING] Batch 28 — Payload copy strategy (Phase 2.1b) [WAITING TAG]
-* [LOCKED] Batch 29 — Faithful timestamps with mandatory re-sign (Phase 2.2) [NO TAG]
+* [DONE] Batch 28 — Payload copy strategy (Phase 2.1b) [PASSED TAG]
+* [RUNNING] Batch 29 — Faithful timestamps with mandatory re-sign (Phase 2.2) [NO TAG]
 * [LOCKED] Batch 30 — Namespace state-digest + equality gate (Phase 2.3) [NO TAG]
 * [LOCKED] Batch 31 — `settings` table migration (V.1a) [NO TAG]
 * [LOCKED] Batch 32 — `SettingsStore` accessor with precedence + cache (V.1b) [NO TAG]
diff --git a/nce/event_log.py b/nce/event_log.py
index 2a1206d..6d87e06 100644
--- a/nce/event_log.py
+++ b/nce/event_log.py
@@ -953,6 +953,7 @@ async def append_event(
     llm_payload_hash: bytes | None = None,
     correlation_id: uuid.UUID | None = None,
     event_id: uuid.UUID | None = None,
+    replay_occurred_at: datetime | None = None,
 ) -> AppendResult:
     """
     Append one entry to the tamper-resistant ``event_log`` table.
@@ -1012,6 +1013,21 @@ async def append_event(
 
     # 4. Fetch DB clock (used in signature so it matches stored occurred_at)
     occurred_at: datetime = await _fetch_db_clock(conn)
+    if replay_occurred_at is not None:
+        replay_run_id = params.get("replay_run_id")
+        if replay_run_id:
+            try:
+                run_id_uuid = (
+                    uuid.UUID(replay_run_id) if isinstance(replay_run_id, str) else replay_run_id
+                )
+                run_mode = await conn.fetchval(
+                    "SELECT replay_mode FROM replay_runs WHERE id = $1",
+                    run_id_uuid,
+                )
+                if run_mode == "deterministic":
+                    occurred_at = replay_occurred_at.astimezone(timezone.utc)
+            except Exception as exc:
+                log.warning("Failed to verify replay mode for run %s: %s", replay_run_id, exc)
     occurred_at_iso: str = occurred_at.isoformat()
 
     # 5. Allocate event_seq (atomic event_sequences upsert)
diff --git a/nce/replay.py b/nce/replay.py
index 54d8438..190c60f 100644
--- a/nce/replay.py
+++ b/nce/replay.py
@@ -586,7 +586,7 @@ async def _handle_store_memory(
 
         src_row = await conn.fetchrow(
             """
-            SELECT embedding, assertion_type, memory_type, metadata
+            SELECT embedding, assertion_type, memory_type, metadata, valid_from
             FROM memories
             WHERE id = $1 AND namespace_id = $2
               AND valid_to IS NULL
@@ -623,7 +623,7 @@ async def _handle_store_memory(
                 $1, $2, $3,
                 $4, $5, $6,
                 $7, $8::jsonb,
-                now()
+                $9
             )
             ON CONFLICT DO NOTHING
             """,
@@ -635,6 +635,7 @@ async def _handle_store_memory(
             src_row["memory_type"],
             target_payload_ref,
             json.dumps(meta),
+            src_row["valid_from"],
         )
 
         # Carry over salience score if it exists in the source namespace
@@ -837,6 +838,23 @@ async def _handle_consolidation_run(
         else:
             new_memory_id = uuid.uuid4()
 
+        # Fetch valid_from from source memories table if it exists
+        raw_src_ns = src.params.get("source_namespace_id")
+        src_ns_id = uuid.UUID(raw_src_ns) if raw_src_ns else None
+        src_valid_from = None
+        if consolidated_memory_id_str and src_ns_id:
+            try:
+                src_valid_from = await conn.fetchval(
+                    "SELECT valid_from FROM memories WHERE id = $1 AND namespace_id = $2",
+                    uuid.UUID(consolidated_memory_id_str),
+                    src_ns_id,
+                )
+            except Exception:
+                pass
+
+        if src_valid_from is None:
+            src_valid_from = src.occurred_at
+
         # Embed the abstraction (reuse the existing embedding infrastructure
         # via a direct import; avoids circular deps since we don't import engine).
         from nce import embeddings as _emb  # local import to avoid module-level circular
@@ -854,7 +872,7 @@ async def _handle_consolidation_run(
                 $1, $2, $3,
                 $4, 'fact', 'consolidated',
                 $5, $6::jsonb,
-                now()
+                $7
             )
             ON CONFLICT DO NOTHING
             """,
@@ -871,6 +889,7 @@ async def _handle_consolidation_run(
                     "replay_fork": True,
                 }
             ),
+            src_valid_from,
         )
 
         # Route salience into memory_salience.salience_score
@@ -1337,6 +1356,7 @@ async def _dispatch_and_apply_event(
         llm_payload_uri=fork_uri,
         llm_payload_hash=fork_hash,
         event_id=det_event_id,
+        replay_occurred_at=src.occurred_at,
     )
 
     return result_summary, fork_event
diff --git a/tests/test_replay_engine.py b/tests/test_replay_engine.py
index 9cfb484..e02ded8 100644
--- a/tests/test_replay_engine.py
+++ b/tests/test_replay_engine.py
@@ -150,6 +150,7 @@ async def test_replay_checksum_success_on_correct_hash(monkeypatch: pytest.Monke
 async def test_handle_store_memory_handler() -> None:
     from unittest.mock import AsyncMock
 
+    from bson import ObjectId
     from nce.replay import _handle_store_memory
 
     mock_conn = AsyncMock()
@@ -218,6 +219,10 @@ async def test_handle_store_memory_handler() -> None:
     sql_query_memories = memories_insert_call[0][0]
     args_memories = memories_insert_call[0][1:]
 
+    # Under the payload copy strategy, target_payload_ref is derived deterministically using uuid5
+    derived_uuid = uuid.uuid5(target_ns, f"payload_ref:{payload_ref}")
+    expected_target_ref = str(ObjectId(derived_uuid.bytes[:12]))
+
     assert "INSERT INTO memories" in sql_query_memories
     assert "summary" not in sql_query_memories
     assert "salience" not in sql_query_memories
@@ -228,7 +233,7 @@ async def test_handle_store_memory_handler() -> None:
     assert args_memories[3] == [0.1] * 768
     assert args_memories[4] == "fact"
     assert args_memories[5] == "episodic"
-    assert args_memories[6] == payload_ref
+    assert args_memories[6] == expected_target_ref
 
     # Verify the arguments to INSERT INTO memory_salience
     salience_insert_call = mock_conn.execute.call_args_list[1]
diff --git a/tests/test_replay_handlers_integration.py b/tests/test_replay_handlers_integration.py
index 7c6f024..2edd99f 100644
--- a/tests/test_replay_handlers_integration.py
+++ b/tests/test_replay_handlers_integration.py
@@ -636,3 +636,225 @@ async def test_replay_payload_copy_strategy(pg_pool, make_namespace, monkeypatch
         assert target_doc["source"] == src_doc["source"], "Metadata details should also match"
 
     mongo_client.close()
+
+
+@pytest.mark.integration
+@pytest.mark.asyncio
+async def test_replay_deterministic_timestamp_preservation(
+    pg_pool, make_namespace, monkeypatch
+) -> None:
+    from datetime import datetime, timedelta, timezone
+
+    from nce.event_log import verify_event_signature
+
+    pool_proxy = PoolProxy(pg_pool)
+
+    # 1. Create source and target namespaces
+    source_ns = await make_namespace()
+    target_ns = await make_namespace()
+
+    agent_id = "test-agent"
+    src_memory_id = uuid.uuid4()
+    payload_ref = "000000000000000000000001"
+    embedding = [0.1] * 768
+    assertion_type = "fact"
+    memory_type = "episodic"
+    metadata = {"source_text": "Timestamp preservation integration test"}
+
+    # Define past timestamps to assert deterministic preservation
+    # Backdate both occurred_at and valid_from by 1 day
+    past_time = datetime.now(timezone.utc) - timedelta(days=1)
+    past_time = past_time.replace(microsecond=0)
+
+    # 2. Seed source memory and event log with the specific past timestamps
+    async with scoped_pg_session(pool_proxy, source_ns) as conn:
+        await conn.execute(
+            """
+            INSERT INTO memories (id, namespace_id, agent_id, embedding, assertion_type, memory_type, payload_ref, metadata, valid_from)
+            VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8::jsonb, $9)
+            """,
+            src_memory_id,
+            source_ns,
+            agent_id,
+            json.dumps(embedding),
+            assertion_type,
+            memory_type,
+            payload_ref,
+            metadata,
+            past_time,
+        )
+
+        await conn.execute("ALTER TABLE event_log DISABLE TRIGGER trg_event_log_worm")
+        try:
+            # Append normally
+            res = await append_event(
+                conn=conn,
+                namespace_id=source_ns,
+                agent_id=agent_id,
+                event_type="store_memory",
+                params={
+                    "saga_id": str(uuid.uuid4()),
+                    "memory_id": str(src_memory_id),
+                    "payload_ref": payload_ref,
+                    "assertion_type": assertion_type,
+                    "entities": [],
+                    "triplets": [],
+                    "source_namespace_id": str(source_ns),
+                },
+            )
+            # Recompute signature and update event_log to match past_time
+            from nce.signing import get_active_key, sign_fields
+
+            key_id, raw_key = await get_active_key(conn)
+
+            row = await conn.fetchrow("SELECT * FROM event_log WHERE id = $1", res.event_id)
+            params = (
+                json.loads(row["params"]) if isinstance(row["params"], str) else dict(row["params"])
+            )
+
+            from nce.event_log import (
+                _GENESIS_SENTINEL,
+                _build_signing_fields,
+                _compute_chain_hash,
+                _compute_content_hash,
+            )
+
+            signing_fields = _build_signing_fields(
+                event_id=row["id"],
+                namespace_id=row["namespace_id"],
+                agent_id=row["agent_id"],
+                event_type=row["event_type"],
+                event_seq=row["event_seq"],
+                occurred_at_iso=past_time.isoformat(),
+                params=params,
+                parent_event_id=row["parent_event_id"],
+                prev_chain_hash_hex=_GENESIS_SENTINEL.hex(),
+            )
+            sig = sign_fields(signing_fields, raw_key)
+            c_hash = _compute_content_hash(signing_fields=signing_fields)
+            ch_hash = _compute_chain_hash(
+                content_hash=c_hash, previous_chain_hash=_GENESIS_SENTINEL
+            )
+
+            await conn.execute(
+                """
+                UPDATE event_log
+                SET occurred_at = $1, signature = $2, chain_hash = $3
+                WHERE id = $4
+                """,
+                past_time,
+                sig,
+                ch_hash,
+                row["id"],
+            )
+        finally:
+            await conn.execute("ALTER TABLE event_log ENABLE TRIGGER trg_event_log_worm")
+
+    # 3. Setup replay monkeypatching
+    import nce.replay as replay_mod
+
+    class ConnectionProxy:
+        def __init__(self, c):
+            self._conn = c
+
+        def __getattr__(self, name):
+            return getattr(self._conn, name)
+
+        async def execute(self, query, *args, **kwargs):
+            new_args = list(args)
+            new_query = query
+            if "INSERT INTO memories" in query:
+                if len(new_args) >= 4 and isinstance(new_args[3], list):
+                    new_args[3] = json.dumps(new_args[3])
+                new_query = new_query.replace("$4,", "$4::vector,")
+                for i, val in enumerate(new_args):
+                    if i == 3:
+                        continue
+                    if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
+                        try:
+                            new_args[i] = json.loads(val)
+                        except Exception:
+                            pass
+            return await self._conn.execute(new_query, *new_args, **kwargs)
+
+    original_dispatch = replay_mod._dispatch_and_apply_event
+
+    async def mock_dispatch(
+        write_conn,
+        src,
+        target_namespace_id,
+        llm_payload,
+        config_overrides,
+        run_id,
+        source_namespace_id,
+        **kwargs,
+    ):
+        proxy = ConnectionProxy(write_conn)
+        return await original_dispatch(
+            proxy,
+            src=src,
+            target_namespace_id=target_namespace_id,
+            llm_payload=llm_payload,
+            config_overrides=config_overrides,
+            run_id=run_id,
+            source_namespace_id=source_namespace_id,
+            **kwargs,
+        )
+
+    monkeypatch.setattr(replay_mod, "_dispatch_and_apply_event", mock_dispatch)
+
+    original_build_query = replay_mod._build_event_query
+
+    def mock_build_query(**kwargs):
+        sql, args = original_build_query(**kwargs)
+        sql = sql.replace("SELECT\n            id,", "SELECT\n            id, namespace_id,")
+        return sql, args
+
+    monkeypatch.setattr(replay_mod, "_build_event_query", mock_build_query)
+
+    original_to_event_row = replay_mod._record_to_event_row
+
+    def mock_to_event_row(record):
+        rec_dict = dict(record)
+        params = rec_dict.get("params")
+        if isinstance(params, str):
+            rec_dict["params"] = json.loads(params)
+        result_summary = rec_dict.get("result_summary")
+        if isinstance(result_summary, str):
+            rec_dict["result_summary"] = json.loads(result_summary)
+        return original_to_event_row(rec_dict)
+
+    monkeypatch.setattr(replay_mod, "_record_to_event_row", mock_to_event_row)
+
+    # 4. Run ReconstructiveReplay
+    replay = ReconstructiveReplay(pool_proxy)
+    events_applied = []
+    async for item in replay.execute(
+        source_namespace_id=source_ns,
+        target_namespace_id=target_ns,
+        end_seq=1,
+        start_seq=1,
+    ):
+        events_applied.append(item)
+
+    assert any(item.get("type") == "complete" for item in events_applied)
+
+    # 5. Verify Target occurred_at, valid_from, and event signature validity
+    async with scoped_pg_session(pool_proxy, target_ns) as conn:
+        events = await conn.fetch("SELECT * FROM event_log WHERE namespace_id = $1", target_ns)
+        assert len(events) == 1
+        replayed_event = events[0]
+
+        ev_occurred_at = replayed_event["occurred_at"].astimezone(timezone.utc)
+        assert ev_occurred_at == past_time
+
+        await verify_event_signature(conn, replayed_event)
+
+        memories = await conn.fetch(
+            "SELECT id, valid_from FROM memories WHERE namespace_id = $1", target_ns
+        )
+        assert len(memories) == 1
+        replayed_memory = memories[0]
+
+        mem_valid_from = replayed_memory["valid_from"].astimezone(timezone.utc)
+        assert mem_valid_from == past_time
```
