import json
import re
import uuid

import pytest
from nce.db_utils import scoped_pg_session
from nce.event_log import append_event
from nce.replay import ReconstructiveReplay


class MockAcquireContext:
    def __init__(self, ctx):
        self.ctx = ctx
        self.conn = None

    async def __aenter__(self):
        self.conn = await self.ctx.__aenter__()
        try:
            await self.conn.set_type_codec(
                "jsonb",
                encoder=json.dumps,
                decoder=json.loads,
                schema="pg_catalog",
            )
        except Exception:
            pass
        try:
            await self.conn.set_type_codec(
                "json",
                encoder=json.dumps,
                decoder=json.loads,
                schema="pg_catalog",
            )
        except Exception:
            pass
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.ctx.__aexit__(exc_type, exc_val, exc_tb)


class PoolProxy:
    def __init__(self, pool):
        self._pool = pool

    def __getattr__(self, name):
        return getattr(self._pool, name)

    def acquire(self, *args, **kwargs):
        return MockAcquireContext(self._pool.acquire(*args, **kwargs))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_replay_handlers_integration_end_to_end(pg_pool, make_namespace, monkeypatch) -> None:
    pool_proxy = PoolProxy(pg_pool)

    # 1. Create source and target namespaces
    source_ns = await make_namespace()
    target_ns = await make_namespace()

    agent_id = "test-agent"
    src_memory_id = uuid.uuid4()
    payload_ref = "000000000000000000000001"
    embedding = [0.1] * 768
    assertion_type = "fact"
    memory_type = "episodic"
    metadata = {"source_text": "Episodic memory details"}

    # 2. Seed the source namespace
    # We need to insert the memory directly into memories and memory_salience of source_ns
    async with scoped_pg_session(pool_proxy, source_ns) as conn:
        await conn.execute(
            """
            INSERT INTO memories (id, namespace_id, agent_id, embedding, assertion_type, memory_type, payload_ref, metadata, valid_from)
            VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8::jsonb, now())
            """,
            src_memory_id,
            source_ns,
            agent_id,
            json.dumps(embedding),
            assertion_type,
            memory_type,
            payload_ref,
            metadata,
        )
        await conn.execute(
            """
            INSERT INTO memory_salience (memory_id, agent_id, namespace_id, salience_score)
            VALUES ($1, $2, $3, $4)
            """,
            src_memory_id,
            agent_id,
            source_ns,
            0.5,
        )

        # Seed events: store_memory (with source_namespace_id injected to bypass handler lookup bug)
        await append_event(
            conn=conn,
            namespace_id=source_ns,
            agent_id=agent_id,
            event_type="store_memory",
            params={
                "saga_id": str(uuid.uuid4()),
                "memory_id": str(src_memory_id),
                "payload_ref": payload_ref,
                "assertion_type": assertion_type,
                "entities": [],
                "triplets": [],
                "source_namespace_id": str(source_ns),
            },
        )

        # Seed events: consolidation_run
        consolidated_memory_id = uuid.uuid4()
        consolidation_payload_ref = "000000000000000000000002"
        await append_event(
            conn=conn,
            namespace_id=source_ns,
            agent_id=agent_id,
            event_type="consolidation_run",
            params={
                "abstraction": "This is a consolidated abstraction",
                "key_entities": [],
                "key_relations": [],
                "supporting_memory_ids": [str(src_memory_id)],
                "contradicting_memory_ids": [],
                "confidence": 0.8,
                "source_memories": [str(src_memory_id)],
                "consolidated_memory_id": str(consolidated_memory_id),
                "payload_ref": consolidation_payload_ref,
            },
        )

        # Seed events: boost_memory
        await append_event(
            conn=conn,
            namespace_id=source_ns,
            agent_id=agent_id,
            event_type="boost_memory",
            params={
                "memory_id": str(src_memory_id),
                "factor": 0.2,
            },
        )

    # 3. Monkeypatch _dispatch_and_apply_event to handle consolidation_run llm_payload and ConnectionProxy
    import nce.replay as replay_mod

    class ConnectionProxy:
        def __init__(self, c):
            self._conn = c

        def __getattr__(self, name):
            return getattr(self._conn, name)

        async def execute(self, query, *args, **kwargs):
            new_args = list(args)
            new_query = query
            if "INSERT INTO memories" in query:
                # 1. Cast embedding ($4) to vector if it is a list
                if len(new_args) >= 4 and isinstance(new_args[3], list):
                    new_args[3] = json.dumps(new_args[3])
                new_query = new_query.replace("$4,", "$4::vector,")

                # 2. Deserialize any manually serialized JSON string parameters back to dict (except index 3)
                for i, val in enumerate(new_args):
                    if i == 3:
                        continue
                    if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                        try:
                            new_args[i] = json.loads(val)
                        except Exception:
                            pass
            return await self._conn.execute(new_query, *new_args, **kwargs)

    original_dispatch = replay_mod._dispatch_and_apply_event

    async def mock_dispatch(
        write_conn,
        src,
        target_namespace_id,
        llm_payload,
        config_overrides,
        run_id,
        source_namespace_id,
        **kwargs,
    ):
        if src.event_type == "consolidation_run" and llm_payload is None:
            llm_payload = {
                "prompt": "fake prompt",
                "response": {
                    "abstraction": src.params.get("abstraction", "Consolidated memory abstraction"),
                    "confidence": src.params.get("confidence", 0.8),
                    "supporting_memory_ids": src.params.get("supporting_memory_ids", []),
                    "key_entities": src.params.get("key_entities", []),
                    "key_relations": src.params.get("key_relations", []),
                },
            }
        proxy = ConnectionProxy(write_conn)
        return await original_dispatch(
            proxy,
            src=src,
            target_namespace_id=target_namespace_id,
            llm_payload=llm_payload,
            config_overrides=config_overrides,
            run_id=run_id,
            source_namespace_id=source_namespace_id,
            **kwargs,
        )

    monkeypatch.setattr(replay_mod, "_dispatch_and_apply_event", mock_dispatch)

    # Monkeypatch _build_event_query to select namespace_id (workaround for production query missing namespace_id)
    original_build_query = replay_mod._build_event_query

    def mock_build_query(**kwargs):
        sql, args = original_build_query(**kwargs)
        # Insert namespace_id into the SELECT fields
        sql = sql.replace("SELECT\n            id,", "SELECT\n            id, namespace_id,")
        return sql, args

    monkeypatch.setattr(replay_mod, "_build_event_query", mock_build_query)

    # Monkeypatch _record_to_event_row to parse JSON params/result_summary if returned as strings
    original_to_event_row = replay_mod._record_to_event_row

    def mock_to_event_row(record):
        rec_dict = dict(record)
        params = rec_dict.get("params")
        if isinstance(params, str):
            rec_dict["params"] = json.loads(params)
        result_summary = rec_dict.get("result_summary")
        if isinstance(result_summary, str):
            rec_dict["result_summary"] = json.loads(result_summary)
        return original_to_event_row(rec_dict)

    monkeypatch.setattr(replay_mod, "_record_to_event_row", mock_to_event_row)

    # 4. Run ReconstructiveReplay
    replay = ReconstructiveReplay(pool_proxy)
    events_applied = []
    async for item in replay.execute(
        source_namespace_id=source_ns,
        target_namespace_id=target_ns,
        end_seq=3,
        start_seq=1,
    ):
        events_applied.append(item)

    # Verify replay status messages
    assert any(item.get("type") == "complete" for item in events_applied)

    # 5. Query the target namespace database tables to verify assertions
    async with scoped_pg_session(pool_proxy, target_ns) as conn:
        memories = await conn.fetch(
            "SELECT id, agent_id, memory_type, payload_ref, metadata FROM memories WHERE namespace_id = $1",
            target_ns,
        )

        # We expect two memories: episodic and consolidated
        assert len(memories) == 2, f"Expected 2 memories in target, got {len(memories)}"

        payload_ref_pattern = re.compile(r"^[a-f0-9]{24}$")

        for memory in memories:
            ref = memory["payload_ref"]
            assert payload_ref_pattern.match(ref), f"Invalid payload_ref format: {ref}"

        # Verify salience score for episodic memory reflects the boost
        salience_records = await conn.fetch(
            """
            SELECT s.salience_score, m.metadata
            FROM memory_salience s
            JOIN memories m ON m.id = s.memory_id
            WHERE s.namespace_id = $1 AND m.memory_type = 'episodic'
            """,
            target_ns,
        )

        assert len(salience_records) == 1
        salience_score = salience_records[0]["salience_score"]
        # Source salience was 0.5, boost factor was 0.2. So final salience should be 0.7
        assert abs(salience_score - 0.7) < 1e-5, (
            f"Expected salience score 0.7, got {salience_score}"
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_replay_reconstructive_repeatable_uuids(pg_pool, make_namespace, monkeypatch) -> None:
    pool_proxy = PoolProxy(pg_pool)

    # 1. Create source namespace and target namespace
    source_ns = await make_namespace()
    target_ns = await make_namespace()

    agent_id = "test-agent"
    src_memory_id = uuid.uuid4()
    payload_ref = "000000000000000000000001"
    embedding = [0.1] * 768
    assertion_type = "fact"
    memory_type = "episodic"
    metadata = {"source_text": "Episodic memory details"}

    # Seed the source namespace
    async with scoped_pg_session(pool_proxy, source_ns) as conn:
        await conn.execute(
            """
            INSERT INTO memories (id, namespace_id, agent_id, embedding, assertion_type, memory_type, payload_ref, metadata, valid_from)
            VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8::jsonb, now())
            """,
            src_memory_id,
            source_ns,
            agent_id,
            json.dumps(embedding),
            assertion_type,
            memory_type,
            payload_ref,
            metadata,
        )
        await conn.execute(
            """
            INSERT INTO memory_salience (memory_id, agent_id, namespace_id, salience_score)
            VALUES ($1, $2, $3, $4)
            """,
            src_memory_id,
            agent_id,
            source_ns,
            0.5,
        )

        # Seed events: store_memory
        await append_event(
            conn=conn,
            namespace_id=source_ns,
            agent_id=agent_id,
            event_type="store_memory",
            params={
                "saga_id": str(uuid.uuid4()),
                "memory_id": str(src_memory_id),
                "payload_ref": payload_ref,
                "assertion_type": assertion_type,
                "entities": [],
                "triplets": [],
                "source_namespace_id": str(source_ns),
            },
        )

    # Replay monkeypatching to support type conversions and JSON parsing if needed
    import nce.replay as replay_mod

    # Monkeypatch _build_event_query to select namespace_id (workaround for production query missing namespace_id)
    original_build_query = replay_mod._build_event_query

    def mock_build_query(**kwargs):
        sql, args = original_build_query(**kwargs)
        # Insert namespace_id into the SELECT fields
        sql = sql.replace("SELECT\n            id,", "SELECT\n            id, namespace_id,")
        return sql, args

    monkeypatch.setattr(replay_mod, "_build_event_query", mock_build_query)

    original_to_event_row = replay_mod._record_to_event_row

    def mock_to_event_row(record):
        rec_dict = dict(record)
        params = rec_dict.get("params")
        if isinstance(params, str):
            rec_dict["params"] = json.loads(params)
        result_summary = rec_dict.get("result_summary")
        if isinstance(result_summary, str):
            rec_dict["result_summary"] = json.loads(result_summary)
        return original_to_event_row(rec_dict)

    monkeypatch.setattr(replay_mod, "_record_to_event_row", mock_to_event_row)

    # Run ReconstructiveReplay the first time
    replay = ReconstructiveReplay(pool_proxy)
    events_run1 = []
    async for item in replay.execute(
        source_namespace_id=source_ns,
        target_namespace_id=target_ns,
        end_seq=1,
        start_seq=1,
    ):
        events_run1.append(item)

    # Collect memory IDs and event IDs from run 1
    async with scoped_pg_session(pool_proxy, target_ns) as conn:
        memories1 = await conn.fetch("SELECT id FROM memories WHERE namespace_id = $1", target_ns)
        events1 = await conn.fetch("SELECT id FROM event_log WHERE namespace_id = $1", target_ns)

    assert len(memories1) == 1
    assert len(events1) == 1
    mem_id1 = memories1[0]["id"]
    event_id1 = events1[0]["id"]

    # Clear target namespace tables
    from nce.config import cfg

    monkeypatch.setenv("NCE_BYPASS_WORM", "true")
    monkeypatch.setattr(cfg, "NCE_BYPASS_WORM", True)

    async with scoped_pg_session(pool_proxy, target_ns) as conn:
        await conn.execute("DELETE FROM memory_salience WHERE namespace_id = $1", target_ns)
        await conn.execute("DELETE FROM memories WHERE namespace_id = $1", target_ns)
        await conn.execute("ALTER TABLE event_log DISABLE TRIGGER trg_event_log_worm")
        try:
            await conn.execute("DELETE FROM event_log WHERE namespace_id = $1", target_ns)
        finally:
            await conn.execute("ALTER TABLE event_log ENABLE TRIGGER trg_event_log_worm")
        # Reset sequence in event_sequences
        await conn.execute("UPDATE event_sequences SET seq = 0 WHERE namespace_id = $1", target_ns)

    # Run ReconstructiveReplay the second time
    events_run2 = []
    async for item in replay.execute(
        source_namespace_id=source_ns,
        target_namespace_id=target_ns,
        end_seq=1,
        start_seq=1,
    ):
        events_run2.append(item)

    # Collect memory IDs and event IDs from run 2
    async with scoped_pg_session(pool_proxy, target_ns) as conn:
        memories2 = await conn.fetch("SELECT id FROM memories WHERE namespace_id = $1", target_ns)
        events2 = await conn.fetch("SELECT id FROM event_log WHERE namespace_id = $1", target_ns)

    assert len(memories2) == 1
    assert len(events2) == 1
    mem_id2 = memories2[0]["id"]
    event_id2 = events2[0]["id"]

    # Assert that the remapped UUIDs are identical across reconstruction runs
    assert mem_id1 == mem_id2
    assert event_id1 == event_id2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_replay_payload_copy_strategy(pg_pool, make_namespace, monkeypatch) -> None:
    import os

    from bson import ObjectId
    from motor.motor_asyncio import AsyncIOMotorClient

    pool_proxy = PoolProxy(pg_pool)

    # 1. Create source and target namespaces
    source_ns = await make_namespace()
    target_ns = await make_namespace()

    agent_id = "test-agent"
    src_memory_id = uuid.uuid4()

    # Generate source payload_ref as a valid ObjectId
    src_oid = ObjectId()
    src_payload_ref = str(src_oid)

    # 2. Insert source document in MongoDB
    mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"))
    db = mongo_client.memory_archive

    await db.episodes.insert_one(
        {
            "_id": src_oid,
            "raw_data": "True isolation target content test",
            "source": "test_replay_payload_copy_strategy",
        }
    )

    embedding = [0.1] * 768
    assertion_type = "fact"
    memory_type = "episodic"
    metadata = {"source_text": "True isolation test"}

    # 3. Seed the source namespace in Postgres
    async with scoped_pg_session(pool_proxy, source_ns) as conn:
        await conn.execute(
            """
            INSERT INTO memories (id, namespace_id, agent_id, embedding, assertion_type, memory_type, payload_ref, metadata, valid_from)
            VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8::jsonb, now())
            """,
            src_memory_id,
            source_ns,
            agent_id,
            json.dumps(embedding),
            assertion_type,
            memory_type,
            src_payload_ref,
            metadata,
        )
        await conn.execute(
            """
            INSERT INTO memory_salience (memory_id, agent_id, namespace_id, salience_score)
            VALUES ($1, $2, $3, $4)
            """,
            src_memory_id,
            agent_id,
            source_ns,
            0.5,
        )

        # Seed event: store_memory
        await append_event(
            conn=conn,
            namespace_id=source_ns,
            agent_id=agent_id,
            event_type="store_memory",
            params={
                "saga_id": str(uuid.uuid4()),
                "memory_id": str(src_memory_id),
                "payload_ref": src_payload_ref,
                "assertion_type": assertion_type,
                "entities": [],
                "triplets": [],
                "source_namespace_id": str(source_ns),
            },
        )

    # 4. Monkeypatch to handle postgres vector inserts and JSON parsing
    import nce.replay as replay_mod

    class ConnectionProxy:
        def __init__(self, c):
            self._conn = c

        def __getattr__(self, name):
            return getattr(self._conn, name)

        async def execute(self, query, *args, **kwargs):
            new_args = list(args)
            new_query = query
            if "INSERT INTO memories" in query:
                if len(new_args) >= 4 and isinstance(new_args[3], list):
                    new_args[3] = json.dumps(new_args[3])
                new_query = new_query.replace("$4,", "$4::vector,")
                for i, val in enumerate(new_args):
                    if i == 3:
                        continue
                    if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                        try:
                            new_args[i] = json.loads(val)
                        except Exception:
                            pass
            return await self._conn.execute(new_query, *new_args, **kwargs)

    original_dispatch = replay_mod._dispatch_and_apply_event

    async def mock_dispatch(
        write_conn,
        src,
        target_namespace_id,
        llm_payload,
        config_overrides,
        run_id,
        source_namespace_id,
        **kwargs,
    ):
        proxy = ConnectionProxy(write_conn)
        return await original_dispatch(
            proxy,
            src=src,
            target_namespace_id=target_namespace_id,
            llm_payload=llm_payload,
            config_overrides=config_overrides,
            run_id=run_id,
            source_namespace_id=source_namespace_id,
            **kwargs,
        )

    monkeypatch.setattr(replay_mod, "_dispatch_and_apply_event", mock_dispatch)

    original_build_query = replay_mod._build_event_query

    def mock_build_query(**kwargs):
        sql, args = original_build_query(**kwargs)
        sql = sql.replace("SELECT\n            id,", "SELECT\n            id, namespace_id,")
        return sql, args

    monkeypatch.setattr(replay_mod, "_build_event_query", mock_build_query)

    original_to_event_row = replay_mod._record_to_event_row

    def mock_to_event_row(record):
        rec_dict = dict(record)
        params = rec_dict.get("params")
        if isinstance(params, str):
            rec_dict["params"] = json.loads(params)
        result_summary = rec_dict.get("result_summary")
        if isinstance(result_summary, str):
            rec_dict["result_summary"] = json.loads(result_summary)
        return original_to_event_row(rec_dict)

    monkeypatch.setattr(replay_mod, "_record_to_event_row", mock_to_event_row)

    # 5. Run ReconstructiveReplay
    replay = ReconstructiveReplay(pool_proxy)
    events_applied = []
    async for item in replay.execute(
        source_namespace_id=source_ns,
        target_namespace_id=target_ns,
        end_seq=1,
        start_seq=1,
    ):
        events_applied.append(item)

    assert any(item.get("type") == "complete" for item in events_applied)

    # 6. Verify distinct payload_refs pointing to equal content
    async with scoped_pg_session(pool_proxy, target_ns) as conn:
        memories = await conn.fetch(
            "SELECT id, payload_ref FROM memories WHERE namespace_id = $1",
            target_ns,
        )
        assert len(memories) == 1
        target_payload_ref = memories[0]["payload_ref"]

        # Assert distinct payload_refs
        assert target_payload_ref != src_payload_ref, (
            "Source and target payload_ref must be distinct"
        )

        # Verify both point to equal content in MongoDB
        src_doc = await db.episodes.find_one({"_id": ObjectId(src_payload_ref)})
        target_doc = await db.episodes.find_one({"_id": ObjectId(target_payload_ref)})

        assert src_doc is not None, "Source MongoDB document should exist"
        assert target_doc is not None, "Target MongoDB document should exist and have been copied"
        assert target_doc["raw_data"] == src_doc["raw_data"], (
            "Target Mongo doc content must match source"
        )
        assert target_doc["source"] == src_doc["source"], "Metadata details should also match"

    mongo_client.close()
