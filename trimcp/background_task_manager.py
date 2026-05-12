"""
Background Task Manager
=======================
Robust management of fire-and-forget async tasks with exception tracking,
logging, and Prometheus metrics. Ensures exceptions in background tasks are
surfaced to the monitoring layer instead of being silently swallowed.

Pattern: All `asyncio.create_task()` calls are routed through `create_tracked_task()`
which automatically attaches done callbacks to extract and log exceptions.

Usage:
    from trimcp.background_task_manager import create_tracked_task
    
    # Instead of: asyncio.create_task(my_coroutine())
    # Do this:
    create_tracked_task(my_coroutine(), name="my-task")

Exception Handling:
    Any exception raised inside a tracked task is:
    1. Logged to logger.exception() → visible in logs
    2. Recorded as metric trimcp_background_task_failures_total
    3. Exposed via Prometheus for alerting
    
This ensures failures in background jobs are never silent — they surface
through the central monitoring layer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from trimcp.observability import HAS_PROMETHEUS

if HAS_PROMETHEUS:
    from prometheus_client import Counter, Gauge, Histogram
else:
    # Stub metrics
    class _StubMetric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def dec(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

    Counter = Histogram = Gauge = _StubMetric


log = logging.getLogger("trimcp.background_task_manager")

# --- Prometheus Metrics ---

BACKGROUND_TASKS_TOTAL = Counter(
    "trimcp_background_tasks_total",
    "Total count of background tasks created",
    ["task_name", "status"],  # status: created, completed, failed
)

BACKGROUND_TASK_DURATION = Histogram(
    "trimcp_background_task_duration_seconds",
    "Duration of background tasks in seconds",
    ["task_name"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0, float("inf")),
)

BACKGROUND_TASK_FAILURES_TOTAL = Counter(
    "trimcp_background_task_failures_total",
    "Total count of background task failures (exceptions)",
    ["task_name", "exception_type"],
)

BACKGROUND_TASK_ACTIVE = Gauge(
    "trimcp_background_task_active",
    "Current number of active background tasks",
    ["task_name"],
)


# --- Task Registry ---

@dataclass
class TrackedTask:
    """Metadata for a tracked background task."""

    name: str
    task: asyncio.Task[Any]
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    exception: Optional[BaseException] = None
    success: bool = False

    @property
    def duration(self) -> float:
        end_time = self.completed_at or time.time()
        return end_time - self.created_at

    def is_active(self) -> bool:
        return not self.task.done()


class TaskRegistry:
    """Global registry of tracked background tasks for lifecycle tracking."""

    def __init__(self):
        self._tasks: dict[str, list[TrackedTask]] = {}
        self._lock = asyncio.Lock()

    async def register(self, tracked_task: TrackedTask) -> None:
        """Register a new tracked task."""
        async with self._lock:
            if tracked_task.name not in self._tasks:
                self._tasks[tracked_task.name] = []
            self._tasks[tracked_task.name].append(tracked_task)
            BACKGROUND_TASK_ACTIVE.labels(task_name=tracked_task.name).inc()

    async def mark_complete(
        self,
        tracked_task: TrackedTask,
        success: bool,
        exception: Optional[BaseException] = None,
    ) -> None:
        """Mark a task as complete and record final state."""
        async with self._lock:
            tracked_task.completed_at = time.time()
            tracked_task.success = success
            tracked_task.exception = exception

            # Record metrics
            BACKGROUND_TASK_DURATION.labels(task_name=tracked_task.name).observe(
                tracked_task.duration
            )
            BACKGROUND_TASKS_TOTAL.labels(
                task_name=tracked_task.name, status="completed" if success else "failed"
            ).inc()
            if exception:
                BACKGROUND_TASK_FAILURES_TOTAL.labels(
                    task_name=tracked_task.name,
                    exception_type=type(exception).__name__,
                ).inc()

            BACKGROUND_TASK_ACTIVE.labels(task_name=tracked_task.name).dec()

    async def get_active_tasks(self, task_name: Optional[str] = None) -> list[TrackedTask]:
        """Get list of active tasks (optionally filtered by name)."""
        async with self._lock:
            if task_name:
                return [
                    t for t in self._tasks.get(task_name, []) if t.is_active()
                ]
            all_tasks = []
            for tasks in self._tasks.values():
                all_tasks.extend([t for t in tasks if t.is_active()])
            return all_tasks

    async def get_task_stats(self) -> dict[str, Any]:
        """Get statistics about tracked tasks."""
        async with self._lock:
            stats = {}
            for task_name, tasks in self._tasks.items():
                active = [t for t in tasks if t.is_active()]
                failed = [t for t in tasks if t.exception is not None]
                stats[task_name] = {
                    "total": len(tasks),
                    "active": len(active),
                    "failed": len(failed),
                    "succeeded": len([t for t in tasks if t.success]),
                }
            return stats


# Global registry instance
_registry = TaskRegistry()


async def create_tracked_task(
    coro: Any,
    name: str,
) -> asyncio.Task[Any]:
    """
    Create a tracked background task with automatic exception logging.

    Args:
        coro: The coroutine to run in the background.
        name: Unique name for the task (used in metrics and logs).
              Recommend: "{operation}-{id}" format, e.g., "fork-abc123".

    Returns:
        The created asyncio.Task. (You typically don't need to store this.)

    Behavior:
        - Task is wrapped with a done callback
        - Any exception raised in the coroutine is logged via logger.exception()
        - Task completion/failure is recorded in metrics and task registry
        - Central monitoring layer receives exception events

    Example:
        >>> async def my_long_job():
        ...     await asyncio.sleep(10)
        ...     if some_error:
        ...         raise ValueError("Something went wrong")
        ...
        >>> # Instead of: asyncio.create_task(my_long_job())
        >>> await create_tracked_task(my_long_job(), name="long-job-123")
    """
    # Create the task
    task = asyncio.create_task(coro, name=name)

    # Create tracking metadata
    tracked_task = TrackedTask(name=name, task=task)

    # Register in global registry
    await _registry.register(tracked_task)

    # Increment metrics
    BACKGROUND_TASKS_TOTAL.labels(task_name=name, status="created").inc()

    def _done_callback(t: asyncio.Task[Any]) -> None:
        """Called when task completes (success or exception)."""
        exception = None
        success = False

        try:
            # Attempt to extract the result
            t.result()
            success = True
        except asyncio.CancelledError:
            # Task was cancelled; don't log as error
            exception = None
            log.info("Background task cancelled: name=%s", name)
        except Exception as exc:
            # Extract and log the exception
            exception = exc
            log.exception(
                "Background task failed with exception: name=%s",
                name,
                exc_info=exc,
            )

        # Mark complete in registry (non-blocking)
        try:
            asyncio.create_task(_mark_complete_async(tracked_task, success, exception))
        except RuntimeError:
            # Event loop may be closed; attempt synchronous fallback
            _mark_complete_sync(tracked_task, success, exception)

    # Attach the callback
    task.add_done_callback(_done_callback)

    return task


async def _mark_complete_async(
    tracked_task: TrackedTask,
    success: bool,
    exception: Optional[BaseException],
) -> None:
    """Async path for marking task complete (prefers this for registry updates)."""
    await _registry.mark_complete(tracked_task, success, exception)


def _mark_complete_sync(
    tracked_task: TrackedTask,
    success: bool,
    exception: Optional[BaseException],
) -> None:
    """Synchronous fallback for marking task complete."""
    tracked_task.completed_at = time.time()
    tracked_task.success = success
    tracked_task.exception = exception

    # Record metrics directly (don't await)
    BACKGROUND_TASK_DURATION.labels(task_name=tracked_task.name).observe(
        tracked_task.duration
    )
    BACKGROUND_TASKS_TOTAL.labels(
        task_name=tracked_task.name,
        status="completed" if success else "failed",
    ).inc()
    if exception:
        BACKGROUND_TASK_FAILURES_TOTAL.labels(
            task_name=tracked_task.name,
            exception_type=type(exception).__name__,
        ).inc()
    BACKGROUND_TASK_ACTIVE.labels(task_name=tracked_task.name).dec()


async def get_active_background_tasks(
    task_name: Optional[str] = None,
) -> list[TrackedTask]:
    """
    Get list of currently active background tasks.

    Args:
        task_name: Optional filter by specific task name.

    Returns:
        List of TrackedTask instances that are still running.

    Usage:
        >>> active = await get_active_background_tasks()
        >>> for task in active:
        ...     print(f"{task.name}: {task.duration:.1f}s")
    """
    return await _registry.get_active_tasks(task_name)


async def get_background_task_stats() -> dict[str, Any]:
    """
    Get statistics about all tracked background tasks.

    Returns:
        Dictionary with per-task-name stats:
        {
            "fork-abc123": {"total": 1, "active": 0, "failed": 1, "succeeded": 0},
            "gc_loop": {"total": 1, "active": 1, "failed": 0, "succeeded": 0},
        }

    Usage:
        >>> stats = await get_background_task_stats()
        >>> print(f"Total failures: {sum(s['failed'] for s in stats.values())}")
    """
    return await _registry.get_task_stats()
