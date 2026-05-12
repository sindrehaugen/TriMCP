"""
Regression tests for async background task managers, metrics, and safety fallback mechanisms.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from unittest import mock

import pytest

from trimcp.background_task_manager import (
    TrackedTask,
    TaskRegistry,
    create_tracked_task,
    get_active_background_tasks,
    get_background_task_stats,
    _mark_complete_sync,
    _mark_complete_async,
)


@pytest.mark.asyncio
async def test_tracked_task_duration_metadata() -> None:
    """Test that TrackedTask correctly calculates duration and active status."""
    task = asyncio.create_task(asyncio.sleep(0.01))
    tracked = TrackedTask(name="metadata-test", task=task)

    assert tracked.is_active()
    assert tracked.duration >= 0.0

    # Complete the task
    await task
    tracked.completed_at = time.time()

    assert not tracked.is_active()
    assert tracked.duration >= 0.01


@pytest.mark.asyncio
async def test_task_registry_operations() -> None:
    """Test TaskRegistry registration, completions, statistics, and filtering."""
    registry = TaskRegistry()
    task = asyncio.create_task(asyncio.sleep(0.05))
    tracked = TrackedTask(name="registry-test", task=task)

    # Register task
    await registry.register(tracked)

    active = await registry.get_active_tasks()
    assert tracked in active

    active_filtered = await registry.get_active_tasks(task_name="registry-test")
    assert tracked in active_filtered

    active_filtered_miss = await registry.get_active_tasks(task_name="no-such-task")
    assert tracked not in active_filtered_miss

    # Mark as complete (success)
    await task
    await registry.mark_complete(tracked, success=True)

    stats = await registry.get_task_stats()
    assert "registry-test" in stats
    assert stats["registry-test"]["total"] == 1
    assert stats["registry-test"]["succeeded"] == 1
    assert stats["registry-test"]["failed"] == 0
    assert stats["registry-test"]["active"] == 0


@pytest.mark.asyncio
async def test_task_registry_stats_failure() -> None:
    """Test registry statistics tracking with exception metadata."""
    registry = TaskRegistry()
    task = asyncio.create_task(asyncio.sleep(0.01))
    tracked = TrackedTask(name="registry-fail-test", task=task)

    await registry.register(tracked)

    await task
    exc = ValueError("Simulated operational failure")
    await registry.mark_complete(tracked, success=False, exception=exc)

    stats = await registry.get_task_stats()
    assert stats["registry-fail-test"]["total"] == 1
    assert stats["registry-fail-test"]["succeeded"] == 0
    assert stats["registry-fail-test"]["failed"] == 1


@pytest.mark.asyncio
async def test_stub_metrics_parity() -> None:
    """Ensure _StubMetric stub objects behave cleanly like Prometheus clients."""
    from trimcp.background_task_manager import _StubMetric

    stub = _StubMetric("test_metric", "doc")
    # All fluent api calls should chain safely
    assert stub.labels(task_name="foo", status="bar") is stub
    assert stub.inc() is None
    assert stub.observe(0.5) is None
    assert stub.set(10) is None


@pytest.mark.asyncio
async def test_mark_complete_sync_fallback() -> None:
    """Test synchronous marking completion fallback path for closed event loops."""
    task = asyncio.create_task(asyncio.sleep(0.01))
    tracked = TrackedTask(name="sync-fallback-test", task=task)

    # Invoke the sync fallback directly
    _mark_complete_sync(tracked, success=True, exception=None)

    assert tracked.completed_at is not None
    assert tracked.success is True
    assert tracked.exception is None

    await task
