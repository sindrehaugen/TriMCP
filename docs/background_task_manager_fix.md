# Fix P1: Async Fire-and-Forget Leaks — Exception Tracking & Monitoring

**Status**: ✅ Complete  
**Phase**: 6 Audit Remediation  
**Scope**: All 6 fire-and-forget background tasks now route through robust task manager  
**Outcome**: Exceptions in background jobs are surfaced to central monitoring layer instead of failing silently

---

## Problem Statement (Phase 6 Audit Pattern 4)

Before this fix, the TriMCP codebase had 6 instances of `asyncio.create_task()` that launched background jobs without exception handling:

| Location | Task | Issue |
|----------|------|-------|
| **admin_server.py:445** | ForkedReplay._run_fork() | No exception tracking |
| **server.py:1795** | GC loop | No exception tracking |
| **replay_mcp_handlers.py:103** | Forked replay | No exception tracking |
| **replay_mcp_handlers.py:149** | Reconstructive replay | No exception tracking |
| **re_embedder.py:264** | Re-embedding worker | No exception tracking |
| **bridge_renewal.py:308** | Token refresh | No exception tracking |

**Result of silence**: 
- Client receives `202 Accepted` even if background job crashes
- Failure never surfaced to logs or monitoring
- Silent data corruption possible in long-running replay operations
- Token refresh failures invisible until next refresh attempt fails

---

## Solution: Background Task Manager

Created **`trimcp/background_task_manager.py`** — a robust task lifecycle manager that:

### 1. Tracks All Background Tasks

```python
from trimcp.background_task_manager import create_tracked_task

# Instead of:
asyncio.create_task(my_coro())

# Do this:
await create_tracked_task(my_coro(), name="operation-id")
```

### 2. Automatic Exception Logging

When a task raises an exception:
- Exception is immediately logged via `logger.exception()` → visible in log aggregation (ELK/Datadog)
- Task name and exception type recorded in Prometheus metrics
- Exception doesn't crash the event loop

### 3. Prometheus Metrics for Monitoring

**Task Lifecycle Metrics:**
```
trimcp_background_tasks_total{task_name="fork-abc123", status="created"} 1
trimcp_background_tasks_total{task_name="fork-abc123", status="completed"} 1
trimcp_background_tasks_total{task_name="fork-abc123", status="failed"} 0

trimcp_background_task_failures_total{task_name="fork-abc123", exception_type="ValueError"} 1
trimcp_background_task_duration_seconds{task_name="fork-abc123"} 12.3

trimcp_background_task_active{task_name="fork-abc123"} 0
```

**Interpretation:**
- `status="failed"` + `exception_type` → Alert on this
- `duration_seconds` → P95/P99 latency tracking
- `active` gauge → Prevents runaway task creation

---

## How Exceptions Surface Through Monitoring Layer

### Exception → Logger → Monitoring

**Step 1: Task executes and fails**
```python
async def replay_fork():
    raise ValueError("Fork cannot proceed — state divergence detected")

await create_tracked_task(replay_fork(), name="fork-xyz")
```

**Step 2: Done callback extracts exception**
```python
def _done_callback(task: asyncio.Task[Any]) -> None:
    try:
        task.result()  # Raises if exception occurred
    except Exception as exc:
        # ↓ This is the critical step ↓
        log.exception(
            "Background task failed with exception: name=%s",
            name,
            exc_info=exc,
        )
```

**Step 3: Log entry flows to central aggregation**
- Syslog / structured logging (JSON)
- ELK Stack / Splunk / Datadog
- Search query: `service:trimcp AND level:ERROR AND logger:trimcp.background_task_manager`

**Step 4: Prometheus scrapes metrics**
```
curl http://localhost:8000/metrics | grep trimcp_background_task_failures
trimcp_background_task_failures_total{task_name="fork-xyz", exception_type="ValueError"} 1
```

**Step 5: Alert fires**
```yaml
# Example Prometheus alert
groups:
  - name: TriMCP
    rules:
      - alert: BackgroundTaskFailure
        expr: increase(trimcp_background_task_failures_total[5m]) > 0
        annotations:
          summary: "{{ $labels.task_name }} failed: {{ $labels.exception_type }}"
```

---

## Implementation Details

### Exception Handling Strategy

**Graceful degradation** — `create_tracked_task()` handles all edge cases:

1. **Normal exception** → Logged + metric recorded
2. **CancelledError** → Not treated as failure (task was deliberately cancelled)
3. **Event loop closed** → Synchronous fallback for metrics recording
4. **Registry unavailable** → Metrics still recorded independently

### Task Registry

Maintains in-memory registry of all tracked tasks:
```python
# Get active tasks
active = await get_active_background_tasks(task_name="fork-*")
for task in active:
    print(f"{task.name}: {task.duration:.1f}s, active={task.is_active()}")

# Get statistics
stats = await get_background_task_stats()
# {
#   "fork-abc123": {"total": 1, "active": 0, "failed": 0, "succeeded": 1},
#   "gc_loop": {"total": 1, "active": 1, "failed": 0, "succeeded": 0},
# }
```

### Task Naming Convention

All refactored calls use structured names for traceability:

| Task | Name Pattern | Example |
|------|--------------|---------|
| Fork replay | `fork-{run_id}` | `fork-3f8e9a2c` |
| Reconstruct replay | `reconstruct-{run_id}` | `reconstruct-8c2d1f7e` |
| GC loop | `gc_loop` | `gc_loop` |
| Re-embedding | `re_embedding_worker` | `re_embedding_worker` |
| Token refresh | `token-refresh-{bridge_id}` | `token-refresh-5a9c` |

---

## Refactored Call Sites

### 1. admin_server.py:445 — ForkedReplay

**Before:**
```python
asyncio.create_task(_run_fork(), name=f"fork-{fork_run_id}")
return JSONResponse({"status": "started", ...}, status_code=202)
```

**After:**
```python
await create_tracked_task(_run_fork(), name=f"fork-{fork_run_id}")
return JSONResponse({"status": "started", ...}, status_code=202)
```

**Behavior**: If `_run_fork()` raises an exception:
- Exception logged immediately
- Metric `trimcp_background_task_failures_total{task_name="fork-...", exception_type="..."}` incremented
- Alert system can detect and notify

---

### 2. server.py:1795 — GC Loop

**Before:**
```python
gc_task = asyncio.create_task(run_gc_loop())
```

**After:**
```python
from trimcp.background_task_manager import create_tracked_task
gc_task = await create_tracked_task(run_gc_loop(), name="gc_loop")
```

**Behavior**: GC failures are now visible in metrics:
```
trimcp_background_task_failures_total{task_name="gc_loop", exception_type="asyncpg.DatabaseError"} 1
```

---

### 3. replay_mcp_handlers.py:103, 149 — Replay Operations

**Before:**
```python
asyncio.create_task(_run_fork())
asyncio.create_task(_run())
```

**After:**
```python
await create_tracked_task(_run_fork(), name=f"fork-{fork_run_id}")
await create_tracked_task(_run(), name=f"reconstruct-{run_id}")
```

**Behavior**: Each replay operation now has dedicated traceability:
- logs: `[fork-3f8e9a2c] Background task failed: ValueError: State divergence detected`
- metrics: Per-replay failure rates

---

### 4. re_embedder.py:264 — Re-embedding Worker

**Before:**
```python
def start_re_embedder(pg_pool, mongo_client):
    asyncio.create_task(run_re_embedding_worker(pg_pool, mongo_client))
```

**After:**
```python
def start_re_embedder(pg_pool, mongo_client):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(create_tracked_task(
            run_re_embedding_worker(pg_pool, mongo_client), 
            name="re_embedding_worker"
        ))
    except RuntimeError:
        asyncio.create_task(create_tracked_task(
            run_re_embedding_worker(pg_pool, mongo_client), 
            name="re_embedding_worker"
        ))
```

**Behavior**: Re-embedding crashes are now observable:
```
trimcp_background_task_failures_total{task_name="re_embedding_worker", exception_type="torch.cuda.OutOfMemoryError"} 1
trimcp_background_task_duration_seconds_bucket{task_name="re_embedding_worker", le="300.0"} 1
```

---

### 5. bridge_renewal.py:308 — Token Refresh

**Before:**
```python
asyncio.create_task(_bg_refresh_token(pool, row, provider, refresh_token))
```

**After:**
```python
await create_tracked_task(
    _bg_refresh_token(pool, row, provider, refresh_token),
    name=f"token-refresh-{bridge_id}"
)
```

**Behavior**: Token refresh failures are now traced:
```
trimcp_background_task_failures_total{task_name="token-refresh-5a9c", exception_type="aiohttp.ClientError"} 1
```

---

## Monitoring & Alerting

### Prometheus Queries

**Find all background task failures in the last hour:**
```promql
increase(trimcp_background_task_failures_total[1h]) > 0
```

**Alert on task exceeding threshold duration:**
```promql
trimcp_background_task_duration_seconds_bucket{le="+Inf"} > 300
```

**Track active tasks by name:**
```promql
trimcp_background_task_active
```

**Task failure rate (per task type):**
```promql
rate(trimcp_background_task_failures_total[5m]) / rate(trimcp_background_tasks_total{status="completed"}[5m])
```

### Grafana Dashboard Recommendations

**Panel 1: Background Task Failure Rate**
```promql
rate(trimcp_background_task_failures_total[5m])
```

**Panel 2: Active Background Tasks**
```promql
trimcp_background_task_active
```

**Panel 3: P95 Task Duration**
```promql
histogram_quantile(0.95, trimcp_background_task_duration_seconds_bucket)
```

**Panel 4: Failure Breakdown by Exception Type**
```promql
topk(10, trimcp_background_task_failures_total)
```

---

## Exception Surfacing Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    participant App as Application Layer
    participant TM as create_tracked_task
    participant Reg as TaskRegistry
    participant Loop as asyncio Event Loop
    participant Metrics as Prometheus / Observability
    participant Alert as Prometheus Alertmanager

    App->>TM: create_tracked_task(coro(), name="fork-abc")
    TM->>Reg: register(tracked_task)
    Reg->>Metrics: BACKGROUND_TASK_ACTIVE.inc()
    TM->>Loop: asyncio.create_task(coro)
    TM->>Loop: task.add_done_callback(_done_callback)
    
    Note over Loop: Task runs asynchronously...
    
    alt Task Raises Exception (e.g. ValueError)
        Loop-->>TM: Trigger _done_callback(task)
        TM->>TM: Extract exception via task.result()
        TM->>TM: Log exception using logger.exception()
        TM->>Reg: mark_complete(tracked_task, success=False, exception)
        Reg->>Metrics: BACKGROUND_TASK_ACTIVE.dec()
        Reg->>Metrics: BACKGROUND_TASK_FAILURES_TOTAL.inc()
        Reg->>Metrics: BACKGROUND_TASK_DURATION.observe()
        
        Note over Metrics: Scraped by Prometheus / Datadog Agent
        Metrics->>Alert: Check Alert Rules (failures > 0)
        Alert->>App: Fire alert to Slack/PagerDuty
    else Task Completes Successfully
        Loop-->>TM: Trigger _done_callback(task)
        TM->>Reg: mark_complete(tracked_task, success=True)
        Reg->>Metrics: BACKGROUND_TASK_ACTIVE.dec()
        Reg->>Metrics: BACKGROUND_TASKS_TOTAL.inc(status="completed")
        Reg->>Metrics: BACKGROUND_TASK_DURATION.observe()
    end
```

---

## Validation

### Tests Added

**Test file**: `tests/test_background_task_manager.py`

Tests validate:
1. ✅ Tasks complete successfully and are tracked
2. ✅ Exceptions are logged to logger.exception()
3. ✅ Prometheus metrics are recorded
4. ✅ Active task counts tracked accurately
5. ✅ Task duration measured correctly
6. ✅ Cancelled tasks handled gracefully
7. ✅ Multiple tasks with same name tracked separately
8. ✅ Custom task names (fork-xyz) preserved
9. ✅ Registry stats computed correctly

**Run tests:**
```bash
pytest tests/test_background_task_manager.py -v
pytest tests/test_background_task_manager.py::test_create_tracked_task_exception_logged -v
```

---

## Before / After Comparison

### Before Fix (Silent Failure)

```python
async def api_replay_fork():
    # Create background task
    asyncio.create_task(_run_fork())
    
    # Return 202 Accepted immediately
    return JSONResponse({"status": "started"}, status_code=202)

# If _run_fork() raises:
# ❌ No log entry
# ❌ No metric recorded
# ❌ Caller thinks operation succeeded
# ❌ Silent data corruption possible
```

### After Fix (Observable Failure)

```python
async def api_replay_fork():
    # Create tracked task with exception handling
    await create_tracked_task(_run_fork(), name=f"fork-{fork_run_id}")
    
    # Return 202 Accepted
    return JSONResponse({"status": "started"}, status_code=202)

# If _run_fork() raises:
# ✅ Log: "Background task failed: name=fork-3f8e9a2c"
# ✅ Metric: trimcp_background_task_failures_total{task_name="fork-3f8e9a2c", exception_type="ValueError"} 1
# ✅ Operator sees exception in logs/dashboard
# ✅ Alert fires on Prometheus rule
# ✅ Root cause visible immediately
```

---

## Migration Path

**Done** — All 6 instances refactored:
- ✅ admin_server.py:445
- ✅ server.py:1795
- ✅ replay_mcp_handlers.py:103, 149
- ✅ re_embedder.py:264
- ✅ bridge_renewal.py:308

**No breaking changes** — Existing APIs unchanged, pure addition of observability.

---

## Configuration

### Environment Variables

No new env vars required. Uses existing:
- `TRIMCP_PROMETHEUS_PORT` — Already configured
- `TRIMCP_OBSERVABILITY_ENABLED` — Already configured

### Backward Compatibility

✅ Full backward compatibility:
- No changes to task execution semantics
- Only adds exception logging + metrics
- Existing alert/dashboard configs continue working
- Can gradually adopt without coordination

---

## Kaizen / Future Improvements

1. **Distributed tracing**: Add OpenTelemetry span context propagation into background tasks
2. **Task lifecycle hooks**: Allow custom callbacks on task creation/completion/failure
3. **Resource quotas**: Prevent unbounded task creation with per-task-type concurrency limits
4. **Task dependencies**: Chain background tasks with explicit dependencies
5. **Dead letter queue**: Route permanently failing tasks to DLQ for replay

---

## Summary

**Problem**: 6 fire-and-forget background tasks silently swallowed exceptions  
**Solution**: `trimcp/background_task_manager.py` + 5-file refactor  
**Outcome**: All background task exceptions now visible in:
- ✅ Central logger (ELK/Datadog searchable)
- ✅ Prometheus metrics (alertable)
- ✅ Task registry (introspectable)
- ✅ Grafana dashboards (visualizable)

**Impact**: Production observability for long-running operations dramatically improved. No more silent failures.

