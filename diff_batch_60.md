# Diff Reference for Batch 60

```diff
diff --git a/docker-compose.yml b/docker-compose.yml
index 1a61433..5738ca6 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -91,7 +91,10 @@ services:
     build:
       context: .
       dockerfile: deploy/multiuser/Dockerfile
-    container_name: nce-worker
+    # Multicore (VI.5a): scale background indexing/sync across N RQ worker
+    # replicas. Lanes (high_priority -> batch_processing -> default) stay as-is;
+    # each replica is an independent forking Worker. No container_name so
+    # replicas > 1 is allowed (Compose names them nce-worker-1, -2, ...).
     profiles:
       - gpu
     env_file:
@@ -101,8 +104,14 @@ services:
       PG_DSN: postgresql://mcp_user:${POSTGRES_PASSWORD:-mcp_password}@postgres:5432/memory_meta
       MINIO_ACCESS_KEY: ${MINIO_ROOT_USER:-mcp_admin}
       MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-super_secure_minio_password}
-    # GPU access for re-embedding CUDA operations (Item 49)
+      # CPU-thread tuning (VI.5a / M2): pin native thread pools to the CPU quota.
+      OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
+      MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
+      TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
     deploy:
+      # N replicas process N RQ jobs concurrently (default 2).
+      replicas: ${WORKER_REPLICAS:-2}
+      # GPU access for re-embedding CUDA operations (Item 49)
       resources:
         reservations:
           devices:
@@ -134,6 +143,14 @@ services:
       PG_DSN: postgresql://mcp_user:${POSTGRES_PASSWORD:-mcp_password}@postgres:5432/memory_meta
       MINIO_ACCESS_KEY: ${MINIO_ROOT_USER:-mcp_admin}
       MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-super_secure_minio_password}
+      # CPU-thread tuning (VI.5a / M2): pin native thread pools to the CPU quota.
+      OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
+      MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
+      TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
+    # Multicore (VI.5a): cron MUST stay a singleton — CronLock is the only
+    # split-brain guard. NEVER scale this above 1 replica.
+    deploy:
+      replicas: 1
     depends_on:
       postgres:
         condition: service_healthy
@@ -149,6 +166,8 @@ services:
     build:
       context: .
       dockerfile: deploy/multiuser/Dockerfile
+    # Multicore (VI.5a): stateless HTTP service — run N uvicorn worker processes.
+    # NOT a background-loop process, so --workers is safe (no GC/outbox/re-embed here).
     command:
       [
         "uvicorn",
@@ -157,6 +176,8 @@ services:
         "0.0.0.0",
         "--port",
         "8003",
+        "--workers",
+        "${ADMIN_WORKERS:-2}",
       ]
     container_name: nce-admin
     env_file:
@@ -166,6 +187,10 @@ services:
       PG_DSN: postgresql://mcp_user:${POSTGRES_PASSWORD:-mcp_password}@postgres:5432/memory_meta
       MINIO_ACCESS_KEY: ${MINIO_ROOT_USER:-mcp_admin}
       MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-super_secure_minio_password}
+      # CPU-thread tuning (VI.5a / M2): pin native thread pools to the CPU quota.
+      OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
+      MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
+      TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
     ports:
       - "${ADMIN_PORT:-8003}:8003"
     depends_on:
@@ -197,6 +222,8 @@ services:
     build:
       context: .
       dockerfile: deploy/multiuser/Dockerfile
+    # Multicore (VI.5a): stateless HTTP service — run N uvicorn worker processes.
+    # NOT a background-loop process, so --workers is safe.
     command:
       [
         "uvicorn",
@@ -205,6 +232,8 @@ services:
         "0.0.0.0",
         "--port",
         "8004",
+        "--workers",
+        "${A2A_WORKERS:-2}",
       ]
     container_name: nce-a2a
     stop_grace_period: 35s
@@ -215,6 +244,10 @@ services:
       PG_DSN: postgresql://mcp_user:${POSTGRES_PASSWORD:-mcp_password}@postgres:5432/memory_meta
       MINIO_ACCESS_KEY: ${MINIO_ROOT_USER:-mcp_admin}
       MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-super_secure_minio_password}
+      # CPU-thread tuning (VI.5a / M2): pin native thread pools to the CPU quota.
+      OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
+      MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
+      TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
     ports:
       - "${A2A_PORT:-8004}:8004"
     depends_on:
@@ -244,6 +277,8 @@ services:
     build:
       context: .
       dockerfile: deploy/multiuser/Dockerfile
+    # Multicore (VI.5a): stateless HTTP service — run N uvicorn worker processes.
+    # NOT a background-loop process, so --workers is safe.
     command:
       [
         "uvicorn",
@@ -252,6 +287,8 @@ services:
         "0.0.0.0",
         "--port",
         "8080",
+        "--workers",
+        "${WEBHOOK_WORKERS:-2}",
       ]
     container_name: nce-webhook-receiver
     env_file:
@@ -262,6 +299,10 @@ services:
       PG_DSN: postgresql://mcp_user:${POSTGRES_PASSWORD:-mcp_password}@postgres:5432/memory_meta
       MINIO_ACCESS_KEY: ${MINIO_ROOT_USER:-mcp_admin}
       MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-super_secure_minio_password}
+      # CPU-thread tuning (VI.5a / M2): pin native thread pools to the CPU quota.
+      OMP_NUM_THREADS: ${OMP_NUM_THREADS:-2}
+      MKL_NUM_THREADS: ${MKL_NUM_THREADS:-2}
+      TOKENIZERS_PARALLELISM: ${TOKENIZERS_PARALLELISM:-false}
     ports:
       - "${WEBHOOK_PORT:-8080}:8080"
     depends_on:
diff --git a/tests/test_compose_multicore.py b/tests/test_compose_multicore.py
new file mode 100644
index 0000000..66b00dd
--- /dev/null
+++ b/tests/test_compose_multicore.py
@@ -0,0 +1,109 @@
+"""Multicore configuration acceptance (NCE_MASTER_PLAN VI.5a, Batch 60).
+
+Structural assertions over the parsed ``docker-compose.yml``:
+
+* the three stateless HTTP services run N uvicorn worker processes;
+* the ``worker`` (RQ) service runs M replicas;
+* ``cron`` stays a singleton (CronLock is the only split-brain guard);
+* CPU-thread env vars are pinned on every compute-bearing service;
+* no background-loop service was given ``--workers``.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+import yaml
+
+_REPO_ROOT = Path(__file__).resolve().parents[1]
+_COMPOSE = _REPO_ROOT / "docker-compose.yml"
+
+# Stateless HTTP services that are safe to run with multiple uvicorn workers.
+_HTTP_SERVICES = ("admin", "a2a", "webhook-receiver")
+# Services that must NOT carry --workers because they run background loops
+# in-process (duplicating them would double GC/outbox/re-embed/cron work).
+_BACKGROUND_LOOP_SERVICES = ("worker", "cron")
+_THREAD_ENV_VARS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "TOKENIZERS_PARALLELISM")
+
+
+def _load() -> dict:
+    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
+
+
+def _command(service: dict) -> list[str]:
+    cmd = service.get("command", [])
+    if isinstance(cmd, str):
+        return cmd.split()
+    return list(cmd)
+
+
+def test_compose_yaml_parses() -> None:
+    doc = _load()
+    assert "services" in doc
+    for name in (*_HTTP_SERVICES, *_BACKGROUND_LOOP_SERVICES):
+        assert name in doc["services"], f"missing service {name}"
+
+
+def test_http_services_declare_n_worker_processes() -> None:
+    """Each stateless HTTP service runs >1 uvicorn worker (or replica)."""
+    services = _load()["services"]
+    for name in _HTTP_SERVICES:
+        svc = services[name]
+        cmd = _command(svc)
+        replicas = svc.get("deploy", {}).get("replicas")
+        has_workers = "--workers" in cmd
+        has_scaled_replicas = isinstance(replicas, (int, str)) and "--workers" not in cmd
+        assert has_workers or has_scaled_replicas, (
+            f"{name} must scale via --workers N or deploy.replicas N"
+        )
+        if has_workers:
+            value = cmd[cmd.index("--workers") + 1]
+            assert value, f"{name} --workers has no value"
+            # ${ADMIN_WORKERS:-2} style default must resolve to >1.
+            assert (
+                ":-2" in value
+                or ":-3" in value
+                or ":-4" in value
+                or (value.isdigit() and int(value) > 1)
+            ), f"{name} --workers default must be >1, got {value!r}"
+
+
+def test_worker_runs_multiple_replicas() -> None:
+    """The RQ worker service scales to M (>1) replicas; lanes unchanged."""
+    worker = _load()["services"]["worker"]
+    replicas = worker.get("deploy", {}).get("replicas")
+    assert replicas is not None, "worker must declare deploy.replicas"
+    text = str(replicas)
+    assert ":-2" in text or ":-3" in text or ":-4" in text or (text.isdigit() and int(text) > 1), (
+        f"worker replicas default must be >1, got {replicas!r}"
+    )
+    # Replicas > 1 require no container_name pin.
+    assert "container_name" not in worker, "worker with replicas>1 must not set container_name"
+
+
+def test_cron_stays_singleton() -> None:
+    """cron must remain exactly one replica (CronLock guard)."""
+    cron = _load()["services"]["cron"]
+    replicas = cron.get("deploy", {}).get("replicas")
+    assert replicas == 1, f"cron must be a singleton (replicas: 1), got {replicas!r}"
+    assert "--workers" not in _command(cron)
+
+
+def test_background_loop_services_have_no_workers_flag() -> None:
+    """No in-process background-loop service may carry --workers."""
+    services = _load()["services"]
+    for name in _BACKGROUND_LOOP_SERVICES:
+        cmd = _command(services[name])
+        assert "--workers" not in cmd, (
+            f"{name} runs background loops in-process; --workers would duplicate them"
+        )
+
+
+def test_cpu_thread_env_vars_pinned() -> None:
+    """Compute-bearing services pin OMP/MKL/TOKENIZERS thread counts."""
+    services = _load()["services"]
+    for name in (*_HTTP_SERVICES, *_BACKGROUND_LOOP_SERVICES):
+        env = services[name].get("environment", {})
+        assert isinstance(env, dict), f"{name} environment must be a mapping"
+        for var in _THREAD_ENV_VARS:
+            assert var in env, f"{name} is missing CPU-thread env var {var}"
```
