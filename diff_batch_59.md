# Diff Reference for Batch 59

```diff
diff --git a/start_worker.py b/start_worker.py
index f5f03eb..c3a0b7f 100644
--- a/start_worker.py
+++ b/start_worker.py
@@ -6,27 +6,144 @@ Priority lanes (§5.4): the worker dequeues ``high_priority`` before
 ``batch_processing`` so that user-facing API extractions never wait behind
 large batch uploads.  The ``default`` queue is retained for backward
 compatibility with any older enqueue sites that haven't been migrated.
+
+In-flight job recovery (R-C, NCE_MASTER_PLAN §VI.6a)
+----------------------------------------------------
+A bare ``Worker(...).work()`` silently loses any job that was *running* when
+the worker died (power loss, OOM, ``SIGKILL``): the job sits forever in the
+queue's ``StartedJobRegistry`` and is never re-executed, because the app-level
+dead-letter queue only catches Python *exceptions*, not process death.
+
+This launcher closes that gap two ways:
+
+* ``with_scheduler=True`` — the worker runs RQ's scheduler in-process so
+  scheduled / retried jobs fire even with a single worker.
+* a periodic ``StartedJobRegistry`` sweep (``maintain_started_registries``)
+  runs on every worker maintenance tick.  Abandoned started jobs (whose
+  monitoring TTL has expired — i.e. no live worker is renewing them) are
+  **requeued onto their origin lane** rather than being dropped or only
+  moved to the failed registry.
+
+Safe-to-lose vs must-requeue
+----------------------------
+All NCE job classes are idempotent / re-derivable, so requeue (rather than
+fail) is the correct default:
+
+* **must-requeue (re-runnable, this sweep requeues them):**
+  ``process_code_indexing`` (re-triggerable from source), bridge cursor /
+  d365 sync polls (re-pollable from the stored cursor), webhook re-indexes.
+  Re-running them at-most reproduces the same content — WORM/idempotency
+  upstream dedupes, so a duplicate run is safe.
+* **safe-to-lose (NOT requeued by this sweep):** none today.  If a future
+  job class is *not* idempotent it must be enqueued with an explicit retry
+  policy and excluded here; document it before adding.
+
+``RESULT_TTL`` / ``FAILURE_TTL`` bound how long finished/failed job metadata
+lingers in Redis so the registries don't grow unbounded between sweeps.
 """
 
+from __future__ import annotations
+
 import logging
+from typing import TYPE_CHECKING
 
 from nce.config import cfg
 from nce.extractors.dispatch import BATCH_QUEUE, HIGH_PRIORITY_QUEUE
-from redis import from_url
+from redis import Redis, from_url
 from rq import Queue, Worker
+from rq.registry import StartedJobRegistry
+
+if TYPE_CHECKING:
+    from rq.job import Job
 
 logging.basicConfig(level=logging.INFO, format="%(asctime)s [Worker] %(levelname)s %(message)s")
+log = logging.getLogger(__name__)
+
+# Lane ordering is load-bearing (§5.4): high-priority first, legacy last.
+QUEUE_NAMES: tuple[str, ...] = (HIGH_PRIORITY_QUEUE, BATCH_QUEUE, "default")
+
+# Retention for finished/failed job metadata (seconds). Bounds Redis growth so
+# the registries stay small enough to sweep cheaply.
+RESULT_TTL = 24 * 60 * 60  # keep successful results 24h for debugging/idempotency
+FAILURE_TTL = 7 * 24 * 60 * 60  # keep failures 7d for post-mortem
+
+
+def requeue_abandoned_jobs(queue: Queue, connection: Redis) -> list[str]:
+    """Requeue every abandoned in-flight job for *queue*'s started registry.
+
+    An "abandoned" job is one whose entry in the ``StartedJobRegistry`` has an
+    expiry score earlier than now: a live worker renews that score while it
+    holds the job, so an expired score means the worker that owned it died
+    mid-execution. We re-enqueue each such job onto its origin lane via the
+    real RQ ``Job.requeue`` contract, so it is picked up again instead of
+    vanishing.
+
+    Returns the list of job ids that were requeued.
+    """
+    registry = StartedJobRegistry(name=queue.name, connection=connection)
+    expired_ids = registry.get_expired_job_ids()
+    requeued: list[str] = []
+    for job_id in expired_ids:
+        try:
+            job: Job = registry.job_class.fetch(job_id, connection=connection)
+        except Exception:  # NoSuchJobError or a half-written job — drop from registry
+            connection.zrem(registry.key, job_id)
+            continue
+        # Drop the stale started-registry entry (StartedJobRegistry.remove is a
+        # no-op in RQ, so we zrem the sorted-set member directly), then re-enqueue
+        # onto the job's *origin* lane. This mirrors RQ's own
+        # ``FailedJobRegistry.requeue`` contract — reset the run timestamps and
+        # push the same Job object back via ``Queue.enqueue_job`` — so the job is
+        # picked up again from the lane it came from instead of vanishing.
+        connection.zrem(registry.key, job_id)
+        origin = Queue(job.origin, connection=connection)
+        job.started_at = None
+        job.ended_at = None
+        job._exc_info = ""
+        origin.enqueue_job(job)
+        requeued.append(job_id)
+        log.warning(
+            "Requeued abandoned in-flight job %s onto lane %r (worker death recovery)",
+            job_id,
+            job.origin,
+        )
+    return requeued
+
+
+def maintain_started_registries(queues: list[Queue], connection: Redis) -> list[str]:
+    """Sweep the started registry of every lane, requeuing abandoned jobs.
+
+    Returns the flat list of requeued job ids across all lanes.
+    """
+    requeued: list[str] = []
+    for queue in queues:
+        requeued.extend(requeue_abandoned_jobs(queue, connection))
+    return requeued
+
+
+class RecoveringWorker(Worker):
+    """RQ worker that requeues abandoned in-flight jobs on each maintenance tick.
+
+    ``Worker.run_maintenance_tasks`` is invoked periodically by ``work()`` (and
+    once at startup); hooking it means crashed-worker recovery happens without a
+    separate process while keeping standard ``work()`` semantics.
+    """
+
+    def run_maintenance_tasks(self) -> None:
+        super().run_maintenance_tasks()
+        try:
+            maintain_started_registries(list(self.queues), self.connection)
+        except Exception:  # never let recovery crash the worker loop
+            log.exception("started-registry maintenance sweep failed")
 
 
-def start_worker():
+def start_worker() -> None:
     redis_conn = from_url(cfg.REDIS_URL)
-    queues = [
-        Queue(HIGH_PRIORITY_QUEUE, connection=redis_conn),
-        Queue(BATCH_QUEUE, connection=redis_conn),
-        Queue("default", connection=redis_conn),  # backward compat
-    ]
-    worker = Worker(queues, connection=redis_conn)
-    worker.work()
+    queues = [Queue(name, connection=redis_conn) for name in QUEUE_NAMES]
+    worker = RecoveringWorker(queues, connection=redis_conn)
+    # Recover anything abandoned by a previous worker crash before we start.
+    maintain_started_registries(queues, redis_conn)
+    worker.work(with_scheduler=True)
 
 
 if __name__ == "__main__":
diff --git a/tests/test_worker_inflight_recovery.py b/tests/test_worker_inflight_recovery.py
new file mode 100644
index 0000000..4c626f9
--- /dev/null
+++ b/tests/test_worker_inflight_recovery.py
@@ -0,0 +1,117 @@
+"""R-C (NCE_MASTER_PLAN §VI.6a): in-flight RQ jobs must survive worker death.
+
+These tests prove that a job which was *running* when its worker died (i.e. an
+abandoned entry in the lane's ``StartedJobRegistry``) is requeued onto its
+origin lane by ``start_worker.requeue_abandoned_jobs`` — not silently lost and
+not merely moved to the failed registry.
+
+They run against the live Redis from the local Docker stack and are marked
+``integration`` so unit-only runs skip them. The assertions check the *real*
+RQ requeue contract (the job is back, queued, on its origin lane), not that a
+mock was called.
+"""
+
+from __future__ import annotations
+
+import uuid
+
+import pytest
+import start_worker
+from redis import from_url
+from rq import Queue
+from rq.job import Job, JobStatus
+from rq.registry import StartedJobRegistry
+
+REDIS_URL = "redis://localhost:6379/0"
+
+
+def _noop_job() -> str:
+    """A re-runnable, idempotent job body (stands in for code-indexing)."""
+    return "ok"
+
+
+@pytest.fixture
+def redis_conn():
+    conn = from_url(REDIS_URL)
+    try:
+        conn.ping()
+    except Exception:  # pragma: no cover - skip when stack is down
+        pytest.skip("local Redis not reachable")
+    yield conn
+
+
+@pytest.fixture
+def lane(redis_conn):
+    """A throwaway queue lane, cleaned up after the test."""
+    name = f"test_recovery_{uuid.uuid4().hex}"
+    queue = Queue(name, connection=redis_conn)
+    yield queue
+    # Tear down: drop the queue and its started registry.
+    redis_conn.delete(queue.key)
+    redis_conn.delete(StartedJobRegistry(name=name, connection=redis_conn).key)
+
+
+def _make_abandoned_started_job(queue: Queue, redis_conn) -> Job:
+    """Create a job, mark it STARTED, and place it in the started registry with
+    an already-expired score — exactly the state left behind by a worker that
+    was killed mid-execution."""
+    job = queue.enqueue(_noop_job)
+    # It is enqueued; simulate the worker having dequeued and started it, then
+    # dying without finishing: remove from the ready queue, mark STARTED, and
+    # register it as in-flight with an expiry in the past.
+    redis_conn.lrem(queue.key, 0, job.id)
+    job.set_status(JobStatus.STARTED)
+    registry = StartedJobRegistry(name=queue.name, connection=redis_conn)
+    # score = 1 → unix epoch 1970, i.e. expired relative to now ⇒ "abandoned".
+    redis_conn.zadd(registry.key, {job.id: 1})
+    return job
+
+
+@pytest.mark.integration
+def test_abandoned_inflight_job_is_requeued_onto_origin_lane(lane, redis_conn):
+    queue = lane
+    job = _make_abandoned_started_job(queue, redis_conn)
+    registry = StartedJobRegistry(name=queue.name, connection=redis_conn)
+
+    # Precondition: job is abandoned (in started registry, expired) and is NOT
+    # on the ready queue.
+    assert job.id in registry.get_expired_job_ids()
+    assert job.id not in queue.get_job_ids()
+
+    requeued = start_worker.requeue_abandoned_jobs(queue, redis_conn)
+
+    # Real requeue contract, not a mock assertion:
+    # 1. our job id is reported as requeued
+    assert requeued == [job.id]
+    # 2. it is back on its origin lane's ready queue
+    assert job.id in queue.get_job_ids()
+    # 3. it is no longer parked in the started registry
+    assert job.id not in StartedJobRegistry(name=queue.name, connection=redis_conn).get_job_ids()
+    # 4. its status is QUEUED again (re-runnable), proving it was not just
+    #    dropped into the failed registry
+    refreshed = Job.fetch(job.id, connection=redis_conn)
+    assert refreshed.get_status() == JobStatus.QUEUED
+    # 5. it kept its origin lane (did not migrate to "default")
+    assert refreshed.origin == queue.name
+
+
+@pytest.mark.integration
+def test_sweep_across_lanes_requeues_only_abandoned(lane, redis_conn):
+    """A live (non-expired) started job is left alone; only abandoned ones move."""
+    queue = lane
+    abandoned = _make_abandoned_started_job(queue, redis_conn)
+
+    # A second job that is "started" but still being actively renewed by a live
+    # worker: score far in the future ⇒ NOT abandoned.
+    live = queue.enqueue(_noop_job)
+    redis_conn.lrem(queue.key, 0, live.id)
+    live.set_status(JobStatus.STARTED)
+    registry = StartedJobRegistry(name=queue.name, connection=redis_conn)
+    redis_conn.zadd(registry.key, {live.id: 9_999_999_999})  # year 2286
+
+    requeued = start_worker.maintain_started_registries([queue], redis_conn)
+
+    assert requeued == [abandoned.id]
+    # the live job stays in-flight, untouched
+    assert live.id in StartedJobRegistry(name=queue.name, connection=redis_conn).get_job_ids()
+    assert live.id not in queue.get_job_ids()
```
