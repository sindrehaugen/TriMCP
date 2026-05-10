import os
import time
from uuid import UUID, uuid4

import pytest

from trimcp import MemoryPayload, TriStackEngine

# Tests require live DB containers (MongoDB, Redis, PostgreSQL).
# Skip gracefully when containers are not available.


def _check_container(env_var: str, host: str, port: int, label: str) -> bool:
    """Return True if the container at host:port is reachable."""
    import socket

    url = os.getenv(env_var)
    if url:
        # Parse host:port from URI if possible
        try:
            if "://" in url:
                host = url.split("://")[1].split(":")[0].split("/")[0]
            else:
                host = url.split(":")[0]
        except Exception:
            pass
    try:
        sock = socket.create_connection((host, port), timeout=1)
        sock.close()
        return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


_MONGO_OK = _check_container("MONGO_URI", "localhost", 27017, "MongoDB")
_PG_OK = _check_container("PG_DSN", "localhost", 5432, "PostgreSQL")
_REDIS_OK = _check_container("REDIS_URL", "localhost", 6379, "Redis")
_ALL_CONTAINERS = _MONGO_OK and _PG_OK and _REDIS_OK


# ---------------------------------------------------------------------------
# Unit tests — no live containers required
# ---------------------------------------------------------------------------


class TestEnsureUuid:
    """Regression suite for TriStackEngine._ensure_uuid (Phase 2 Issue #1).

    Verifies that string UUIDs are correctly parsed to UUID objects, UUID
    objects are returned as-is, and None inputs return None.  The critical
    regression case is that a string input must NEVER silently produce the
    string "None" that would corrupt RLS context.
    """

    def setup_method(self):
        self.engine = TriStackEngine()

    def test_none_returns_none(self):
        """None input must return None, not UUID('None')."""
        result = self.engine._ensure_uuid(None)
        assert result is None

    def test_uuid_object_returned_unchanged(self):
        """UUID objects must pass through without wrapping."""
        uid = uuid4()
        result = self.engine._ensure_uuid(uid)
        assert result is uid

    def test_string_uuid_is_parsed_to_uuid_object(self):
        """String UUIDs must be converted — NOT silently passed as strings."""
        uid = uuid4()
        uid_str = str(uid)
        result = self.engine._ensure_uuid(uid_str)
        assert isinstance(result, UUID), (
            f"Expected UUID object, got {type(result).__name__!r}. "
            "This means _ensure_uuid is NOT converting strings — "
            "RLS context would receive a bare string, not a UUID."
        )
        assert result == uid

    def test_string_uuid_never_produces_string_none(self):
        """The historical bug: result was str('None') when val was a string.
        This test is the primary regression guard for Phase 2 Issue #1.
        """
        uid = uuid4()
        result = self.engine._ensure_uuid(str(uid))
        assert str(result) != "None", (
            "RLS namespace context would be set to 'None' — "
            "this is the exact P0 regression this test guards against."
        )

    def test_invalid_string_raises_value_error(self):
        """Non-UUID strings must raise ValueError immediately, not silently pass."""
        with pytest.raises(ValueError):
            self.engine._ensure_uuid("not-a-uuid")


class TestSagaMetricsOnFailure:
    """Regression suite for SagaMetrics.on_saga_failure (Phase 2 Issue #2).

    Verifies that the callback safely handles missing kwargs so the metric
    is always emitted — omitting step_name must not raise KeyError.
    """

    def test_on_saga_failure_empty_kwargs_does_not_raise(self):
        """Calling on_saga_failure with no kwargs must never raise KeyError."""
        from trimcp.observability import SagaMetrics

        exc = RuntimeError("saga exploded")
        # Must not raise — this was the bug
        SagaMetrics.on_saga_failure(exc)

    def test_on_saga_failure_missing_step_name_uses_default(self, monkeypatch):
        """When step_name is absent the metric stage defaults to 'unknown'."""
        from trimcp.observability import SAGA_FAILURES, SagaMetrics

        def _fake_inc():
            # We need to capture the labels tuple; monkeypatch the .inc() method
            pass

        # Capture what stage label gets set
        stages: list[str] = []
        original_labels = SAGA_FAILURES.labels

        def _capture_labels(**kw):
            stages.append(kw.get("stage", "<none>"))
            return original_labels(**kw)

        monkeypatch.setattr(SAGA_FAILURES, "labels", _capture_labels)

        exc = ValueError("oops")
        SagaMetrics.on_saga_failure(exc)  # no step_name kwarg

        # The stage must be the safe default "unknown", not a KeyError crash
        assert stages, "SAGA_FAILURES.labels was never called — metric not emitted"
        assert (
            stages[0] == "unknown"
        ), f"Expected stage='unknown' when step_name omitted, got {stages[0]!r}"

    def test_on_saga_failure_with_step_name(self, monkeypatch):
        """When step_name is provided it is forwarded as the metric stage."""
        from trimcp.observability import SAGA_FAILURES, SagaMetrics

        stages: list[str] = []
        original_labels = SAGA_FAILURES.labels

        def _capture_labels(**kw):
            stages.append(kw.get("stage", "<none>"))
            return original_labels(**kw)

        monkeypatch.setattr(SAGA_FAILURES, "labels", _capture_labels)

        SagaMetrics.on_saga_failure(RuntimeError("x"), step_name="pg_insert")
        assert stages == ["pg_insert"], f"Unexpected stage: {stages}"

    def test_saga_metrics_context_fires_on_failure_callback(self):
        """SagaMetrics.__exit__ invokes the on_failure callback on exception."""
        from trimcp.observability import SagaMetrics

        fired: list[BaseException] = []

        def _cb(exc):
            fired.append(exc)

        with pytest.raises(RuntimeError):
            with SagaMetrics("test_op", on_failure=_cb):
                raise RuntimeError("deliberately broken")

        assert len(fired) == 1, "on_failure callback was not called"
        assert isinstance(fired[0], RuntimeError)

    def test_saga_metrics_context_does_not_fire_on_success(self):
        """on_failure must NOT be called when the block completes normally."""
        from trimcp.observability import SagaMetrics

        fired: list[BaseException] = []

        def _cb(exc):
            fired.append(exc)

        with SagaMetrics("test_op", on_failure=_cb):
            pass  # no exception

        assert fired == [], "on_failure fired on a successful saga block"


# ---------------------------------------------------------------------------
# Integration tests — require live MongoDB + PostgreSQL + Redis containers
# ---------------------------------------------------------------------------

_skip_no_containers = pytest.mark.skipif(
    not _ALL_CONTAINERS,
    reason="Integration tests require live MongoDB, PostgreSQL, and Redis containers",
)


@pytest.fixture
async def engine():
    eng = TriStackEngine()
    await eng.connect()
    yield eng
    await eng.disconnect()


@_skip_no_containers
@pytest.mark.asyncio
async def test_store_and_recall(engine):
    """store_memory → get_recent_context (Redis hit)"""
    test_id = str(uuid4())
    payload = MemoryPayload(
        user_id=test_id,
        session_id=test_id,
        content_type="chat",
        summary="TriMCP uses Redis as working memory for sub-millisecond recall.",
        heavy_payload="Full conversation transcript placeholder for test T1.",
    )
    mongo_id = await engine.store_memory(payload)
    assert mongo_id, "No mongo_id returned"

    cached = await engine.recall_memory(test_id, test_id)
    assert cached == payload.summary, f"Cache mismatch: {cached!r}"


@_skip_no_containers
@pytest.mark.asyncio
async def test_semantic_search(engine):
    """semantic_search returns stored document"""
    test_id = str(uuid4())
    payload = MemoryPayload(
        user_id=test_id,
        session_id=test_id,
        content_type="chat",
        summary="PostgreSQL pgvector stores 768-dimensional cosine embeddings.",
        heavy_payload="Full transcript: pgvector enables cosine similarity search on 768-dim vectors.",
    )
    await engine.store_memory(payload)

    results_sr = await engine.semantic_search(
        test_id, "vector database embeddings", limit=3
    )
    assert len(results_sr) > 0, "No results returned"
    assert "pgvector" in str(
        results_sr[0].get("raw_data", "")
    ), f"Expected pgvector in top result, got: {results_sr[0].get('raw_data', '')!r}"


@_skip_no_containers
@pytest.mark.asyncio
async def test_index_and_search_code(engine):
    """index_code_file + search_codebase finds the function"""
    run_id = str(int(time.time()))
    sample_code = "def calculate_embedding_distance(vec_a, vec_b):\n    pass\nclass VectorStore:\n    pass\n"
    result = await engine.index_code_file(
        filepath=f"test_fixtures/vector_utils_{run_id}.py",
        raw_code=sample_code,
        language="python",
    )
    assert result["status"] == "indexed", f"Unexpected status: {result}"

    code_results = await engine.search_codebase(
        "cosine distance between vectors", top_k=3
    )
    assert len(code_results) > 0, "No code results returned"
    assert any(
        "calculate_embedding_distance" in r.get("name", "") for r in code_results
    )


@_skip_no_containers
@pytest.mark.asyncio
async def test_change_detection(engine):
    """Re-indexing unchanged file returns status=skipped"""
    code = "def noop(): pass\n"
    fp = "test_fixtures/noop.py"
    await engine.index_code_file(filepath=fp, raw_code=code, language="python")
    result2 = await engine.index_code_file(
        filepath=fp, raw_code=code, language="python"
    )
    assert result2["status"] == "skipped", f"Expected skipped, got: {result2}"


@_skip_no_containers
@pytest.mark.asyncio
async def test_graph_search(engine):
    """store_memory extracts KG entities; graph_search returns a subgraph"""
    test_id = str(uuid4())
    payload = MemoryPayload(
        user_id=test_id,
        session_id=test_id,
        content_type="chat",
        summary="MongoDB stores raw data. Redis connects to the cache layer.",
        heavy_payload="Heavy payload for T5.",
    )
    await engine.store_memory(payload)

    subgraph = await engine.graph_search("MongoDB storage", max_depth=2)
    assert "nodes" in subgraph, "No nodes key in subgraph"
    assert "edges" in subgraph, "No edges key in subgraph"
    assert len(subgraph["nodes"]) > 0, "Subgraph has no nodes"


@_skip_no_containers
@pytest.mark.asyncio
async def test_rollback(engine):
    """Forcing a PG failure must leave MongoDB clean"""
    from motor.motor_asyncio import AsyncIOMotorClient

    test_id = str(uuid4())

    db = AsyncIOMotorClient(
        os.getenv("MONGO_URI", "mongodb://localhost:27017")
    ).memory_archive
    before_count = await db.episodes.count_documents({})

    real_pool = engine.pg_pool
    engine.pg_pool = None
    try:
        await engine.store_memory(
            MemoryPayload(
                user_id=test_id,
                session_id=test_id,
                content_type="chat",
                summary="This write must be rolled back.",
                heavy_payload="Rollback test payload.",
            )
        )
        pytest.fail("Exception was NOT raised — rollback did not trigger")
    except Exception:
        pass
    finally:
        engine.pg_pool = real_pool

    after_count = await db.episodes.count_documents({})
    assert (
        after_count == before_count
    ), f"MongoDB grew by {after_count - before_count} — orphan NOT cleaned up"
