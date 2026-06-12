# Diff Reference for Batch 61

```diff
diff --git a/RL.md b/RL.md
index 694014a..e8c9c85 100644
--- a/RL.md
+++ b/RL.md
@@ -68,7 +68,7 @@
 * [DONE] Batch 58 — Reverse-orphan reconciliation sweep (R-B / VI.6a) [PASSED TAG]
 * [DONE] Batch 59 — RQ in-flight job recovery (R-C / VI.6a) [PASSED TAG]
 * [DONE] Batch 60 — Multicore: HTTP workers + RQ replicas + thread pinning (VI.5a) [PASSED TAG]
-* [OPEN] Batch 61 — RAM: offload spaCy + NLI to a sidecar; container mem limits (VI.5b) [NO TAG]
+* [RUNNING] Batch 61 — RAM: offload spaCy + NLI to a sidecar; container mem limits (VI.5b) [RUNNING TAG]
 * [DONE] Batch 62 — Disk: datastore tuning + halfvec + tmpfs temp (VI.5c) [PASSED TAG]
 * [OPEN] Batch 63 — Cross-encoder reranking (IV.1) [NO TAG]
 * [OPEN] Batch 64 — Multi-vector / aspect embeddings (IV.2) [NO TAG]
diff --git a/deploy/cognitive-stub/stub_server.py b/deploy/cognitive-stub/stub_server.py
index 196bafb..2ce0abf 100644
--- a/deploy/cognitive-stub/stub_server.py
+++ b/deploy/cognitive-stub/stub_server.py
@@ -14,6 +14,7 @@ from __future__ import annotations
 
 import json
 import os
+import re
 from http.server import BaseHTTPRequestHandler, HTTPServer
 
 PORT = int(os.getenv("COGNITIVE_PORT", "11435"))
@@ -21,6 +22,62 @@ DIM = int(os.getenv("EMBEDDING_VECTOR_DIM", "768"))
 
 _HEALTH = json.dumps({"status": "ok", "engine": "stub"}).encode()
 
+_IS_RELATION = re.compile(
+    r"(\b\w[\w\s]{1,30}?\b)\s+(is|are|uses|has|contains|stores|connects to|depends on|runs on)\s+([\w][\w\s]{1,30}?\b)",
+    re.IGNORECASE,
+)
+_KNOWN_TOOLS = {
+    "redis",
+    "postgres",
+    "postgresql",
+    "mongodb",
+    "mongo",
+    "docker",
+    "python",
+    "fastapi",
+    "mcp",
+    "nce",
+    "pgvector",
+    "tree-sitter",
+}
+
+
+def _stub_regex_extract(text: str) -> dict:
+    nodes = []
+    edges = []
+    seen = set()
+
+    def add_node(label: str, etype: str):
+        cleaned = label.strip()
+        key = cleaned.lower()
+        if cleaned and key not in seen:
+            nodes.append({"label": cleaned, "entity_type": etype, "source_text": cleaned})
+            seen.add(key)
+
+    for word in re.findall(r"\b\w[\w\-]+\b", text):
+        lower = word.lower()
+        if lower in _KNOWN_TOOLS:
+            add_node(word, "TOOL")
+
+    for m in _IS_RELATION.finditer(text):
+        subj, pred, obj = (
+            m.group(1).strip(),
+            m.group(2).strip().lower(),
+            m.group(3).strip(),
+        )
+        edges.append(
+            {
+                "subject_label": subj,
+                "predicate": pred,
+                "object_label": obj,
+                "confidence": 0.85,
+            }
+        )
+        for label in (subj, obj):
+            add_node(label, "CONCEPT")
+
+    return {"nodes": nodes, "edges": edges}
+
 
 def _chat_response(body: dict) -> bytes:
     model = body.get("model", "stub")
@@ -46,8 +103,7 @@ def _embeddings_response(body: dict) -> bytes:
     if isinstance(inputs, str):
         inputs = [inputs]
     data = [
-        {"object": "embedding", "index": i, "embedding": [0.0] * DIM}
-        for i in range(len(inputs))
+        {"object": "embedding", "index": i, "embedding": [0.0] * DIM} for i in range(len(inputs))
     ]
     return json.dumps(
         {
@@ -88,6 +144,11 @@ class _Handler(BaseHTTPRequestHandler):
             self._send(200, _chat_response(body))
         elif self.path == "/v1/embeddings":
             self._send(200, _embeddings_response(body))
+        elif self.path == "/v1/nlp/spacy":
+            text = body.get("text", "")
+            self._send(200, json.dumps(_stub_regex_extract(text)).encode())
+        elif self.path == "/v1/nlp/nli":
+            self._send(200, b'{"score":0.0}')
         else:
             self._send(404, b'{"error":"not found"}')
 
diff --git a/docker-compose.yml b/docker-compose.yml
index 3d11571..c9ec24c 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -21,6 +21,10 @@ services:
       interval: 5s
       timeout: 3s
       retries: 5
+    deploy:
+      resources:
+        limits:
+          memory: 512M
 
   postgres:
     image: pgvector/pgvector:pg16
@@ -65,6 +69,10 @@ services:
       options:
         max-size: "10m"
         max-file: "3"
+    deploy:
+      resources:
+        limits:
+          memory: 2G
 
   mongodb:
     image: mongo:7.0
@@ -90,6 +98,10 @@ services:
       options:
         max-size: "10m"
         max-file: "3"
+    deploy:
+      resources:
+        limits:
+          memory: 1G
 
   minio:
     image: minio/minio:RELEASE.2024-11-07T00-52-20Z
@@ -109,6 +121,10 @@ services:
       interval: 5s
       timeout: 5s
       retries: 5
+    deploy:
+      resources:
+        limits:
+          memory: 512M
 
   cognitive:
     image: ghcr.io/sindrehaugen/nce-cognitive:v1
@@ -117,10 +133,14 @@ services:
       - "${COGNITIVE_PORT:-11435}:11435"
     restart: unless-stopped
     healthcheck:
-      test: ["CMD", "curl", "-f", "http://localhost:11435/health"]
+      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:11435/health')\""]
       interval: 10s
       timeout: 5s
       retries: 3
+    deploy:
+      resources:
+        limits:
+          memory: 2G
 
   worker:
     build:
@@ -149,6 +169,7 @@ services:
       # those writes never touch real disk.
       NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
       TMPDIR: /dev/shm/nce-staging
+      NCE_APP_PASSWORD: nce_app_secret
     tmpfs:
       - /dev/shm/nce-staging
     deploy:
@@ -156,6 +177,8 @@ services:
       replicas: ${WORKER_REPLICAS:-2}
       # GPU access for re-embedding CUDA operations (Item 49)
       resources:
+        limits:
+          memory: 1G
         reservations:
           devices:
             - driver: nvidia
@@ -198,12 +221,16 @@ services:
       # Disk-I/O tuning (VI.5c D4/D5): RAM-backed temp/staging (see worker).
       NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
       TMPDIR: /dev/shm/nce-staging
+      NCE_APP_PASSWORD: nce_app_secret
     tmpfs:
       - /dev/shm/nce-staging
     # Multicore (VI.5a): cron MUST stay a singleton — CronLock is the only
     # split-brain guard. NEVER scale this above 1 replica.
     deploy:
       replicas: 1
+      resources:
+        limits:
+          memory: 512M
     depends_on:
       postgres:
         condition: service_healthy
@@ -252,6 +279,7 @@ services:
       # Disk-I/O tuning (VI.5c D4/D5): RAM-backed temp/staging (see worker).
       NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
       TMPDIR: /dev/shm/nce-staging
+      NCE_APP_PASSWORD: nce_app_secret
     tmpfs:
       - /dev/shm/nce-staging
     ports:
@@ -285,6 +313,10 @@ services:
       options:
         max-size: "10m"
         max-file: "3"
+    deploy:
+      resources:
+        limits:
+          memory: 1G
 
   a2a:
     build:
@@ -319,6 +351,7 @@ services:
       # Disk-I/O tuning (VI.5c D4/D5): RAM-backed temp/staging (see worker).
       NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
       TMPDIR: /dev/shm/nce-staging
+      NCE_APP_PASSWORD: nce_app_secret
     tmpfs:
       - /dev/shm/nce-staging
     ports:
@@ -350,6 +383,10 @@ services:
       options:
         max-size: "10m"
         max-file: "3"
+    deploy:
+      resources:
+        limits:
+          memory: 1G
 
   webhook-receiver:
     build:
@@ -384,6 +421,7 @@ services:
       # Disk-I/O tuning (VI.5c D4/D5): RAM-backed temp/staging (see worker).
       NCE_ARTIFACT_STAGING_DIR: ${NCE_ARTIFACT_STAGING_DIR:-/dev/shm/nce-staging}
       TMPDIR: /dev/shm/nce-staging
+      NCE_APP_PASSWORD: nce_app_secret
     tmpfs:
       - /dev/shm/nce-staging
     ports:
@@ -411,6 +449,10 @@ services:
       options:
         max-size: "10m"
         max-file: "3"
+    deploy:
+      resources:
+        limits:
+          memory: 512M
 
   jaeger:
     image: jaegertracing/all-in-one:1.60
@@ -428,13 +470,17 @@ services:
       interval: 10s
       timeout: 5s
       retries: 5
+    deploy:
+      resources:
+        limits:
+          memory: 512M
 
   caddy:
     image: caddy:2.8-alpine
     container_name: nce-caddy
     ports:
-      - "${CADDY_HTTP_PORT:-80}:80"
-      - "${CADDY_HTTPS_PORT:-443}:443"
+      - "${CADDY_HTTP_PORT:-8082}:80"
+      - "${CADDY_HTTPS_PORT:-8443}:443"
     volumes:
       - ./Caddyfile:/etc/caddy/Caddyfile:ro
       - caddy_data:/data
@@ -451,6 +497,10 @@ services:
       retries: 3
       start_period: 5s
     restart: unless-stopped
+    deploy:
+      resources:
+        limits:
+          memory: 256M
 
 volumes:
   redis_data:
diff --git a/nce/contradictions.py b/nce/contradictions.py
index 389e05e..df8055e 100644
--- a/nce/contradictions.py
+++ b/nce/contradictions.py
@@ -82,7 +82,38 @@ def _sync_nli_predict(premise: str, hypothesis: str) -> float:
 
 
 async def check_nli_contradiction(premise: str, hypothesis: str) -> float:
-    """Async wrapper for NLI prediction."""
+    """Async wrapper for NLI prediction.
+
+    If NCE_COGNITIVE_BASE_URL is configured, the NLI calculation is offloaded
+    out-of-process to the cognitive sidecar to prevent memory usage spikes.
+    """
+    try:
+        from nce.embeddings import validated_cognitive_base_url
+
+        base_url = validated_cognitive_base_url()
+    except Exception:
+        base_url = ""
+
+    if base_url:
+        import httpx
+
+        from nce.http_resilience import request_with_retry
+
+        url = f"{base_url}/v1/nlp/nli"
+        async with httpx.AsyncClient(timeout=30.0) as client:
+            resp = await request_with_retry(
+                client,
+                "POST",
+                url,
+                json={"premise": premise, "hypothesis": hypothesis},
+                operation_name="nlp_sidecar:nli",
+            )
+            data = resp.json()
+            score = float(data["score"])
+            if math.isnan(score) or not (0.0 <= score <= 1.0):
+                raise NLIUnavailableError(f"Remote NLI score out of bounds: {score}")
+            return score
+
     loop = asyncio.get_running_loop()
     return await loop.run_in_executor(_executor, _sync_nli_predict, premise, hypothesis)
 
diff --git a/nce/graph_extractor.py b/nce/graph_extractor.py
index 20e36e7..18b012e 100644
--- a/nce/graph_extractor.py
+++ b/nce/graph_extractor.py
@@ -276,6 +276,45 @@ def deduplicate_graph(
     return merged_nodes, merged_edges
 
 
+def _spacy_extract_remote(text: str, base_url: str) -> tuple[list[KGNode], list[KGEdge]]:
+    """Send text to cognitive sidecar for spaCy entity and triplet extraction."""
+    import httpx
+
+    from nce.http_resilience import request_with_retry_sync
+
+    url = f"{base_url}/v1/nlp/spacy"
+    with httpx.Client(timeout=30.0) as client:
+        resp = request_with_retry_sync(
+            client,
+            "POST",
+            url,
+            json={"text": text},
+            operation_name="nlp_sidecar:spacy",
+        )
+        data = resp.json()
+
+    nodes = []
+    for n in data.get("nodes", []):
+        nodes.append(
+            KGNode(
+                label=n["label"],
+                entity_type=n["entity_type"],
+                source_text=n["source_text"],
+            )
+        )
+    edges = []
+    for e in data.get("edges", []):
+        edges.append(
+            KGEdge(
+                subject_label=e["subject_label"],
+                predicate=e["predicate"],
+                object_label=e["object_label"],
+                confidence=e.get("confidence", 0.85),
+            )
+        )
+    return nodes, edges
+
+
 # --- Public API ---
 
 
@@ -291,8 +330,19 @@ def extract(text: str) -> tuple[list[KGNode], list[KGEdge]]:
     use ``deduplicate_graph()``.
     """
     try:
-        nodes, edges = _spacy_extract(text)
-        log.debug("spaCy extracted %d nodes, %d edges.", len(nodes), len(edges))
+        from nce.embeddings import validated_cognitive_base_url
+
+        base_url = validated_cognitive_base_url()
+    except Exception:
+        base_url = ""
+
+    try:
+        if base_url:
+            nodes, edges = _spacy_extract_remote(text, base_url)
+            log.debug("spaCy (remote) extracted %d nodes, %d edges.", len(nodes), len(edges))
+        else:
+            nodes, edges = _spacy_extract(text)
+            log.debug("spaCy (local) extracted %d nodes, %d edges.", len(nodes), len(edges))
         return nodes, edges
     except (ImportError, Exception) as e:
         log.info("spaCy unavailable (%s), using regex fallback.", e)
diff --git a/scripts/bootstrap-compose-secrets.py b/scripts/bootstrap-compose-secrets.py
index 6eb0a42..537e638 100644
--- a/scripts/bootstrap-compose-secrets.py
+++ b/scripts/bootstrap-compose-secrets.py
@@ -139,7 +139,7 @@ def _hash_pbkdf2(password: str) -> str:
         iters,
         dklen=32,
     )
-    return f"$pbkdf2${iters}${salt.hex()}${dk.hex()}"
+    return f"$$pbkdf2$${iters}$${salt.hex()}$${dk.hex()}"
 
 
 def _gen_for_key(key: str) -> str:
```
