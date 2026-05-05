"""Unit tests for Phase 1.1 Ebbinghaus-style salience decay (trimcp.salience)."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from trimcp import salience


def test_compute_decayed_score_half_life_halves_salience():
    half_life_days = 7.0
    s_last = 1.0
    updated_at = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    reference_now = datetime(2026, 1, 8, 0, 0, tzinfo=timezone.utc)

    out = salience.compute_decayed_score(s_last, updated_at, half_life_days, now=reference_now)
    assert math.isclose(out, 0.5, rel_tol=1e-9)


def test_compute_decayed_score_zero_half_life_returns_unchanged():
    ref = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert salience.compute_decayed_score(0.8, datetime(2020, 1, 1, tzinfo=timezone.utc), 0.0, now=ref) == 0.8
    assert salience.compute_decayed_score(0.8, datetime(2020, 1, 1, tzinfo=timezone.utc), -1.0, now=ref) == 0.8


def test_compute_decayed_score_future_updated_at_returns_unchanged():
    ref = datetime(2026, 1, 1, tzinfo=timezone.utc)
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert salience.compute_decayed_score(1.0, future, 30.0, now=ref) == 1.0


def test_compute_decayed_score_naive_updated_at_assumed_utc():
    reference_now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 9, 12, 0)
    out = salience.compute_decayed_score(1.0, naive, 30.0, now=reference_now)
    assert 0.9 < out <= 1.0


def test_ranking_score_clamps_inputs_and_matches_formula():
    cosine_sim = 0.5
    sal = 0.8
    alpha = 0.7
    expected = cosine_sim * (alpha + (1.0 - alpha) * sal)
    assert salience.ranking_score(cosine_sim, sal, alpha) == pytest.approx(expected)

    assert salience.ranking_score(-1.0, 2.0, 0.5) == pytest.approx(0.0)


def test_reinforce_executes_upsert_sql():
    conn = AsyncMock()
    memory_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    agent_id = "agent-a"
    namespace_id = "11111111-2222-3333-4444-555555555555"

    async def _run() -> None:
        await salience.reinforce(conn, memory_id, agent_id, namespace_id, delta=0.05)

    asyncio.run(_run())

    conn.execute.assert_awaited_once()
    call = conn.execute.await_args
    sql = call.args[0].lower()
    assert "memory_salience" in sql
    assert "on conflict" in sql
    assert call.args[1:] == (memory_id, agent_id, namespace_id, 0.05)
