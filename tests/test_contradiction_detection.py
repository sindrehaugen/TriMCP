"""Tests for Phase 1.3 contradiction detection (trimcp.contradictions)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from trimcp.contradictions import ContradictionResult, detect_contradictions
from trimcp.models import KGEdge

_VALID_OID = "507f1f77bcf86cd799439011"


class StubContradictionLLM:
    def __init__(self, result: ContradictionResult) -> None:
        self._result = result

    async def complete(self, messages: list, response_model: type):  # noqa: ANN401
        assert response_model is ContradictionResult
        return self._result

    def model_identifier(self) -> str:
        return "stub/contradiction-llm"


def test_detect_skips_non_fact_assertions():
    conn = AsyncMock()
    mongo = MagicMock()

    async def _run():
        return await detect_contradictions(
            conn,
            mongo,
            str(uuid4()),
            str(uuid4()),
            "I prefer dark mode",
            "preference",
            [0.1] * 8,
            "agent-1",
            [],
        )

    out = asyncio.run(_run())
    assert out is None
    conn.fetch.assert_not_called()


def test_detect_returns_none_when_no_similar_candidates():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    mongo = MagicMock()

    async def _run():
        return await detect_contradictions(
            conn,
            mongo,
            str(uuid4()),
            str(uuid4()),
            "New factual memory",
            "fact",
            [0.02] * 768,
            "agent-1",
            [],
        )

    out = asyncio.run(_run())
    assert out is None
    conn.fetch.assert_awaited_once()


def test_detect_records_contradiction_when_llm_confident(monkeypatch: pytest.MonkeyPatch):
    cand_id = uuid4()
    ns = str(uuid4())
    new_mid = str(uuid4())

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[
            {"id": cand_id, "payload_ref": _VALID_OID, "similarity": 0.92},
        ]
    )
    conn.fetchrow = AsyncMock(
        side_effect=[
            None,
            {"metadata": {}},
        ]
    )
    conn.execute = AsyncMock(return_value="INSERT 1")

    mongo = MagicMock()
    mongo.memory_archive.episodes.find_one = AsyncMock(
        return_value={"raw_data": "The API timeout is configured to 30 seconds."}
    )

    llm = StubContradictionLLM(
        ContradictionResult(
            is_contradiction=True,
            confidence=0.88,
            explanation="Mutually exclusive timeout values.",
        )
    )
    monkeypatch.setattr("trimcp.contradictions.get_provider", lambda _name: llm)

    trip = KGEdge(
        subject_label="API",
        predicate="timeout_seconds",
        object_label="30",
        metadata={"source_text": "ctx"},
    )

    async def _run():
        return await detect_contradictions(
            conn,
            mongo,
            ns,
            new_mid,
            "The API timeout is configured to 60 seconds.",
            "fact",
            [0.03] * 768,
            "agent-1",
            [trip],
        )

    out = asyncio.run(_run())

    assert out is not None
    assert out["memory_a_id"] == str(cand_id)
    assert out["memory_b_id"] == new_mid
    assert out["confidence"] == pytest.approx(0.88)
    assert any(s["source"] == "llm" for s in out["signals"])
    conn.execute.assert_awaited()


def test_detect_no_insert_when_llm_rejects_contradiction(monkeypatch: pytest.MonkeyPatch):
    cand_id = uuid4()
    ns = str(uuid4())
    new_mid = str(uuid4())

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[{"id": cand_id, "payload_ref": _VALID_OID, "similarity": 0.86}]
    )
    conn.fetchrow = AsyncMock(side_effect=[None, {"metadata": {}}])
    conn.execute = AsyncMock(return_value="INSERT 1")

    mongo = MagicMock()
    mongo.memory_archive.episodes.find_one = AsyncMock(
        return_value={"raw_data": "Servers run in region eu-west-1."}
    )

    llm = StubContradictionLLM(
        ContradictionResult(is_contradiction=False, confidence=0.2, explanation="Compatible.")
    )
    monkeypatch.setattr("trimcp.contradictions.get_provider", lambda _name: llm)

    async def _run():
        return await detect_contradictions(
            conn,
            mongo,
            ns,
            new_mid,
            "Staging mirrors production topology.",
            "fact",
            [0.04] * 768,
            "agent-1",
            [],
        )

    out = asyncio.run(_run())

    assert out is None
    conn.execute.assert_not_called()


def test_detect_inserts_on_kg_when_llm_raises(monkeypatch: pytest.MonkeyPatch):
    cand_id = uuid4()
    conflict_payload = "aaaaaaaaaaaaaaaaaaaaaaaa"
    ns = str(uuid4())
    new_mid = str(uuid4())

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[{"id": cand_id, "payload_ref": _VALID_OID, "similarity": 0.9}]
    )

    async def _fetchrow(sql: str, *args: object):
        lowered = sql.lower()
        if "kg_edges" in lowered and "join memories" in lowered:
            return {"payload_ref": conflict_payload}
        if "metadata from namespaces" in lowered:
            return {"metadata": {}}
        return None

    conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    conn.execute = AsyncMock(return_value="INSERT 1")

    mongo = MagicMock()
    mongo.memory_archive.episodes.find_one = AsyncMock(
        return_value={"raw_data": "legacy doc"}
    )

    class BoomLLM:
        async def complete(self, messages: list, response_model: type):  # noqa: ANN401
            raise RuntimeError("simulated upstream failure")

        def model_identifier(self) -> str:
            return "stub/boom"

    monkeypatch.setattr("trimcp.contradictions.get_provider", lambda _name: BoomLLM())

    trip = KGEdge(subject_label="S", predicate="p", object_label="O1")

    async def _run():
        return await detect_contradictions(
            conn,
            mongo,
            ns,
            new_mid,
            "incoming",
            "fact",
            [0.05] * 768,
            "agent-1",
            [trip],
        )

    out = asyncio.run(_run())

    assert out is not None
    assert out["confidence"] == pytest.approx(0.95)
    assert any(s["source"] == "kg" for s in out["signals"])
    conn.execute.assert_awaited()
