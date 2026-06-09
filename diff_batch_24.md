# Diff Reference for Batch 24

```diff
diff --git a/nce/embeddings.py b/nce/embeddings.py
index 451eae3..a2cd3b4 100644
--- a/nce/embeddings.py
+++ b/nce/embeddings.py
@@ -26,10 +26,10 @@ import threading
 from abc import ABC, abstractmethod
 from concurrent.futures import ThreadPoolExecutor
 from contextvars import ContextVar
-from typing import TYPE_CHECKING
+from typing import TYPE_CHECKING, cast
 
 from nce.config import cfg
-from nce.observability import EMBEDDING_COUNT
+from nce.observability import EMBEDDING_COUNT, EMBEDDING_FALLBACKS
 
 if TYPE_CHECKING:
     pass
@@ -297,6 +297,17 @@ class EmbeddingBackend(ABC):
         vectors, degraded = await loop.run_in_executor(_executor, self._sync_embed_batch, texts)
         # Set the flag in the async task context — NOT inside the executor thread.
         degraded_embedding_flag.set(degraded)
+        if degraded:
+            EMBEDDING_FALLBACKS.inc()
+            try:
+                from nce.notifications import dispatcher
+
+                await dispatcher.dispatch_alert(
+                    "Embedding Fallback Active",
+                    "The primary embedding backend failed and degraded operation (hash-stub fallback) was triggered.",
+                )
+            except Exception:
+                log.exception("Failed to dispatch alert for embedding fallback")
         return vectors
 
 
@@ -458,7 +469,7 @@ class OpenVINONPUBackend(EmbeddingBackend):
                 e,
             )
 
-        return _validate_batch(texts, vectors, backend_name="OpenVINONPU")
+        return _validate_batch(texts, cast(list[list[float]], vectors), backend_name="OpenVINONPU")
 
 
 # ---------------------------------------------------------------------------
@@ -524,10 +535,18 @@ class CognitiveRemoteBackend(EmbeddingBackend):
         if self._model:
             payload["model"] = self._model
 
+        from nce.http_resilience import request_with_retry_sync
+
         try:
             with httpx.Client(timeout=120.0) as client:
-                r = client.post(url, json=payload, headers=headers)
-                r.raise_for_status()
+                r = request_with_retry_sync(
+                    client,
+                    "POST",
+                    url,
+                    json=payload,
+                    headers=headers,
+                    operation_name="embedding_sidecar:primary",
+                )
                 data = r.json()
         except Exception as e:
             # Classify the error so we can decide whether to try the fallback model.
@@ -557,8 +576,14 @@ class CognitiveRemoteBackend(EmbeddingBackend):
 
                 try:
                     with httpx.Client(timeout=60.0) as client:
-                        r = client.post(url, json=payload_fallback, headers=headers)
-                        r.raise_for_status()
+                        r = request_with_retry_sync(
+                            client,
+                            "POST",
+                            url,
+                            json=payload_fallback,
+                            headers=headers,
+                            operation_name="embedding_sidecar:fallback",
+                        )
                         data = r.json()
                 except Exception as fe:
                     return _fallback_with_error(
diff --git a/nce/extractors/libreoffice.py b/nce/extractors/libreoffice.py
index 071dcd9..f59e502 100644
--- a/nce/extractors/libreoffice.py
+++ b/nce/extractors/libreoffice.py
@@ -10,6 +10,8 @@ import subprocess
 import tempfile
 from pathlib import Path
 
+from nce.net_safety import _verify_binary_safety
+
 log = logging.getLogger(__name__)
 
 _SAFE_EXT = re.compile(r"^\.[a-zA-Z0-9]{1,8}$")
@@ -55,13 +57,21 @@ def libreoffice_convert(
         return None
     target = target_ext.lstrip(".")
     soffice = _resolve_soffice()
+    expected_hash = os.environ.get("NCE_SOFFICE_HASH", "").strip()
+    if not expected_hash:
+        log.warning("libreoffice_convert: NCE_SOFFICE_HASH environment variable is not set")
+        return None
+    verified_soffice = _verify_binary_safety(soffice, expected_hash)
+    if not verified_soffice:
+        log.warning("libreoffice_convert: binary safety check failed for %s", soffice)
+        return None
     try:
         with tempfile.TemporaryDirectory(prefix="nce_lo_") as d:
             td = Path(d)
             src = td / f"source{ext}"
             src.write_bytes(blob)
             cmd = [
-                soffice,
+                verified_soffice,
                 "--headless",
                 "--norestore",
                 "--nolockcheck",
diff --git a/nce/extractors/project_ext.py b/nce/extractors/project_ext.py
index cdbba84..bc52cd0 100644
--- a/nce/extractors/project_ext.py
+++ b/nce/extractors/project_ext.py
@@ -15,6 +15,7 @@ from nce.extractors import pdf_ext
 from nce.extractors.core import ExtractionResult, Section, empty_skipped
 from nce.extractors.libreoffice import libreoffice_convert
 from nce.extractors.office_word import extract_docx
+from nce.net_safety import _verify_binary_safety
 
 log = logging.getLogger(__name__)
 
@@ -27,7 +28,7 @@ def _mpxj_allowed_binaries() -> frozenset[str]:
     if not raw:
         return _DEFAULT_MPXJ_BINARIES
     names = {part.strip().lower() for part in raw.split(",") if part.strip()}
-    return names or _DEFAULT_MPXJ_BINARIES
+    return frozenset(names) if names else _DEFAULT_MPXJ_BINARIES
 
 
 def _normalize_executable_name(path: str) -> str:
@@ -74,8 +75,26 @@ def _extract_mpp_sync(blob: bytes) -> ExtractionResult:
             return empty_skipped(
                 "mpp",
                 "mpp_bad_command",
-                warnings=["NCE_MPXJ_EXTRACTOR is not on the allowlist or contains shell metacharacters"],
+                warnings=[
+                    "NCE_MPXJ_EXTRACTOR is not on the allowlist or contains shell metacharacters"
+                ],
             )
+        expected_hash = os.environ.get("NCE_MPXJ_HASH", "").strip()
+        if not expected_hash:
+            return empty_skipped(
+                "mpp",
+                "mpp_binary_hash_not_configured",
+                warnings=["NCE_MPXJ_HASH environment variable is not set"],
+            )
+        verified_bin = _verify_binary_safety(argv[0], expected_hash)
+        if not verified_bin:
+            return empty_skipped(
+                "mpp",
+                "mpp_binary_safety_failed",
+                warnings=[f"MPXJ binary safety check failed for {argv[0]!r}"],
+            )
+        argv[0] = verified_bin
+
         from nce.subprocess_registry import tracked_process
 
         proc = subprocess.Popen(
@@ -91,7 +110,9 @@ def _extract_mpp_sync(blob: bytes) -> ExtractionResult:
             except subprocess.TimeoutExpired:
                 proc.kill()
                 proc.communicate()
-                return empty_skipped("mpp", "mpp_sidecar_timeout", warnings=["MPXJ extractor timed out"])
+                return empty_skipped(
+                    "mpp", "mpp_sidecar_timeout", warnings=["MPXJ extractor timed out"]
+                )
             except Exception as e:
                 proc.kill()
                 proc.communicate()
diff --git a/nce/graph_mcp_handlers.py b/nce/graph_mcp_handlers.py
index 644c86f..e9bc209 100644
--- a/nce/graph_mcp_handlers.py
+++ b/nce/graph_mcp_handlers.py
@@ -31,3 +31,57 @@ async def handle_graph_search(engine: NCEEngine, arguments: dict[str, Any]) -> s
     req = GraphSearchRequest(**arguments)
     result = await engine.graph_search(req)
     return json.dumps(result, default=str)
+
+
+@mcp_handler
+async def handle_neuromorphic_search(engine: NCEEngine, arguments: dict[str, Any]) -> str:
+    """GraphRAG spreading activation traversal over the Knowledge Graph."""
+    if engine._graph_traverser is None:
+        raise RuntimeError("Engine not connected — call connect() first")
+
+    # Validate baseline parameters against GraphSearchRequest
+    search_keys = {
+        "namespace_id",
+        "agent_id",
+        "query",
+        "max_depth",
+        "anchor_top_k",
+        "as_of",
+        "max_edges_per_node",
+        "edge_limit",
+        "edge_offset",
+    }
+    search_args = {k: v for k, v in arguments.items() if k in search_keys}
+    req = GraphSearchRequest(**search_args)
+
+    # Extract additional neuromorphic parameters
+    telemetry_severity = arguments.get("telemetry_severity")
+    if telemetry_severity is not None:
+        telemetry_severity = float(telemetry_severity)
+
+    theta = float(arguments.get("theta", 0.5))
+    decay = float(arguments.get("decay", 0.85))
+    alpha = float(arguments.get("alpha", 1.0))
+
+    ticks = arguments.get("ticks")
+    if ticks is not None:
+        ticks = int(ticks)
+
+    subgraph = await engine._graph_traverser.neuromorphic_search(
+        query=req.query,
+        namespace_id=str(req.namespace_id),
+        max_depth=req.max_depth,
+        anchor_top_k=req.anchor_top_k,
+        user_id=req.agent_id,
+        private=bool(req.agent_id),
+        as_of=req.as_of,
+        max_edges_per_node=req.max_edges_per_node,
+        edge_limit=req.edge_limit,
+        edge_offset=req.edge_offset,
+        telemetry_severity=telemetry_severity,
+        theta=theta,
+        decay=decay,
+        alpha=alpha,
+        ticks=ticks,
+    )
+    return json.dumps(subgraph.to_dict(), default=str)
diff --git a/nce/http_resilience.py b/nce/http_resilience.py
index 8ba4604..12a54bb 100644
--- a/nce/http_resilience.py
+++ b/nce/http_resilience.py
@@ -23,6 +23,7 @@ import httpx
 from tenacity import (
     AsyncRetrying,
     RetryError,
+    Retrying,
     retry_if_exception,
     stop_after_attempt,
     stop_after_delay,
@@ -316,6 +317,153 @@ def classify_httpx_response(
         )
 
 
+async def request_with_retry(
+    client: httpx.AsyncClient,
+    method: str,
+    url: str,
+    *,
+    operation_name: str,
+    max_retries: int = 3,
+    base_delay_ms: int = 1_000,
+    max_delay_ms: int = 30_000,
+    max_total_ms: int = 60_000,
+    backoff_factor: float = 2.0,
+    **kwargs: Any,
+) -> httpx.Response:
+    """Send an HTTP request using AsyncClient with retries on transient errors."""
+
+    async def once() -> httpx.Response:
+        try:
+            resp = await client.request(method, url, **kwargs)
+        except httpx.TimeoutException as exc:
+            raise ExternalAPITransientError(
+                f"{operation_name}: request timed out",
+                operation=operation_name,
+            ) from exc
+        except httpx.RequestError as exc:
+            raise ExternalAPITransientError(
+                f"{operation_name}: transport error: {redact_secrets_in_text(str(exc))}",
+                operation=operation_name,
+            ) from exc
+        classify_httpx_response(resp, operation=operation_name)
+        return resp
+
+    return await execute_http_with_retry(
+        once,
+        operation_name=operation_name,
+        max_retries=max_retries,
+        base_delay_ms=base_delay_ms,
+        max_delay_ms=max_delay_ms,
+        max_total_ms=max_total_ms,
+        backoff_factor=backoff_factor,
+    )
+
+
+def request_with_retry_sync(
+    client: httpx.Client,
+    method: str,
+    url: str,
+    *,
+    operation_name: str,
+    max_retries: int = 3,
+    base_delay_ms: int = 1_000,
+    max_delay_ms: int = 30_000,
+    max_total_ms: int = 60_000,
+    backoff_factor: float = 2.0,
+    **kwargs: Any,
+) -> httpx.Response:
+    """Send an HTTP request using httpx.Client with retries on transient errors (sync)."""
+    if max_retries < 0:
+        raise ValueError("max_retries must be >= 0")
+    if base_delay_ms < 1:
+        raise ValueError("base_delay_ms must be >= 1")
+    if max_delay_ms < base_delay_ms:
+        raise ValueError("max_delay_ms must be >= base_delay_ms")
+    if max_total_ms < 1:
+        raise ValueError("max_total_ms must be >= 1")
+    if backoff_factor < 1.0:
+        raise ValueError("backoff_factor must be >= 1.0")
+    if len(operation_name) > 128:
+        raise ValueError("operation_name must be <= 128 characters")
+
+    stop = stop_after_attempt(max_retries + 1) | stop_after_delay(max_total_ms / 1000.0)
+    retry_predicate = retry_if_exception(lambda exc: isinstance(exc, ExternalAPITransientError))
+
+    def once() -> httpx.Response:
+        EXTERNAL_HTTP_ATTEMPTS_TOTAL.labels(operation=operation_name).inc()
+        try:
+            resp = client.request(method, url, **kwargs)
+        except httpx.TimeoutException as exc:
+            raise ExternalAPITransientError(
+                f"{operation_name}: request timed out",
+                operation=operation_name,
+            ) from exc
+        except httpx.RequestError as exc:
+            raise ExternalAPITransientError(
+                f"{operation_name}: transport error: {redact_secrets_in_text(str(exc))}",
+                operation=operation_name,
+            ) from exc
+        classify_httpx_response(resp, operation=operation_name)
+        return resp
+
+    _t0 = time.perf_counter()
+    try:
+        result = Retrying(
+            stop=stop,
+            wait=_wait_seconds_policy(
+                base_delay_ms=base_delay_ms,
+                max_delay_ms=max_delay_ms,
+                backoff_factor=backoff_factor,
+            ),
+            retry=retry_predicate,
+            before_sleep=_make_before_sleep_safe(operation_name),
+            reraise=False,
+        )(once)
+        EXTERNAL_HTTP_LATENCY_SECONDS.labels(operation=operation_name).observe(
+            time.perf_counter() - _t0
+        )
+        return result
+    except RetryError as re:
+        EXTERNAL_HTTP_LATENCY_SECONDS.labels(operation=operation_name).observe(
+            time.perf_counter() - _t0
+        )
+        last_exc = re.last_attempt.exception()
+        attempts = re.last_attempt.attempt_number
+        if last_exc is None:
+            EXTERNAL_HTTP_FAILURES_TOTAL.labels(
+                operation=operation_name, error_type="no_exception"
+            ).inc()
+            raise ExternalAPIRetriesExhaustedError(
+                f"{operation_name}: retries exhausted after {attempts} attempt(s) (no exception)",
+                operation=operation_name,
+                last_error=RuntimeError("retry exhausted without captured exception"),
+                attempts=attempts,
+            ) from None
+        if isinstance(last_exc, ExternalAPIClientError):
+            EXTERNAL_HTTP_FAILURES_TOTAL.labels(
+                operation=operation_name, error_type="client_error"
+            ).inc()
+            raise last_exc
+        if isinstance(last_exc, ExternalAPIRetriesExhaustedError):
+            raise last_exc
+        safe_error = redact_secrets_in_text(str(last_exc))
+        EXTERNAL_HTTP_FAILURES_TOTAL.labels(
+            operation=operation_name, error_type=type(last_exc).__name__
+        ).inc()
+        log.warning(
+            "%s: HTTP retries exhausted after %d attempt(s) — last error: %s",
+            operation_name,
+            attempts,
+            safe_error,
+        )
+        raise ExternalAPIRetriesExhaustedError(
+            f"{operation_name}: retries exhausted after {attempts} attempt(s): {safe_error}",
+            operation=operation_name,
+            last_error=last_exc if isinstance(last_exc, Exception) else RuntimeError(str(last_exc)),
+            attempts=attempts,
+        ) from last_exc
+
+
 async def oauth_token_post_form(
     url: str,
     data: dict[str, str],
@@ -403,4 +551,3 @@ async def post_json_with_retry(
                 ) from exc
 
         return await execute_http_with_retry(once, operation_name=operation)
-
diff --git a/nce/mcp_stdio_tools.py b/nce/mcp_stdio_tools.py
index f0d22c4..e33933b 100644
--- a/nce/mcp_stdio_tools.py
+++ b/nce/mcp_stdio_tools.py
@@ -357,6 +357,93 @@ TOOLS = [
             "required": ["query"],
         },
     ),
+    Tool(
+        name="neuromorphic_search",
+        description=(
+            "GraphRAG spreading activation traversal over the Knowledge Graph. "
+            "Uses a spiking neural model to search and traverse the knowledge graph "
+            "instead of legacy BFS, returning a structured subgraph with nodes, relations, "
+            "and source document excerpts."
+        ),
+        inputSchema={
+            "type": "object",
+            "properties": {
+                "query": {
+                    "type": "string",
+                    "description": "Natural language query to anchor the graph search",
+                },
+                "namespace_id": {
+                    "type": "string",
+                    "description": "Namespace ID to search within.",
+                },
+                "max_depth": {
+                    "type": "integer",
+                    "default": 2,
+                    "description": "Maximum BFS hop depth for traversal",
+                },
+                "user_id": {
+                    "type": "string",
+                    "description": "Optional. When supplied, restricts hydrated sources to this user.",
+                },
+                "private": {
+                    "type": "boolean",
+                    "default": False,
+                    "description": "When true, only hydrate sources owned by user_id.",
+                },
+                "as_of": {
+                    "type": "string",
+                    "format": "date-time",
+                    "description": (
+                        "Optional ISO 8601 UTC timestamp (e.g. '2026-01-15T10:00:00Z'). "
+                        "Traverses the knowledge graph as it existed at or before this instant."
+                    ),
+                },
+                "max_edges_per_node": {
+                    "type": "integer",
+                    "default": 512,
+                    "minimum": 1,
+                    "maximum": 2048,
+                    "description": "Max incident edges loaded per hop.",
+                },
+                "edge_limit": {
+                    "type": "integer",
+                    "minimum": 1,
+                    "maximum": 5000,
+                    "description": "Optional page size on the deduplicated edge list.",
+                },
+                "edge_offset": {
+                    "type": "integer",
+                    "default": 0,
+                    "minimum": 0,
+                    "description": "Offset into deduplicated edges when using edge_limit.",
+                },
+                "telemetry_severity": {
+                    "type": "number",
+                    "description": "Optional system telemetry severity score to dynamically tune spreading thresholds.",
+                },
+                "theta": {
+                    "type": "number",
+                    "default": 0.5,
+                    "description": "Spiking threshold potential.",
+                },
+                "decay": {
+                    "type": "number",
+                    "default": 0.85,
+                    "description": "Spiking potential decay factor.",
+                },
+                "alpha": {
+                    "type": "number",
+                    "default": 1.0,
+                    "description": "Transfer weight coefficient for signal propagation.",
+                },
+                "ticks": {
+                    "type": "integer",
+                    "description": "Number of propagation steps (defaults to max_depth).",
+                },
+            },
+            "required": ["query"],
+        },
+    ),
     Tool(
         name="get_recent_context",
         description=(
diff --git a/nce/net_safety.py b/nce/net_safety.py
index 2fbfd86..90324af 100644
--- a/nce/net_safety.py
+++ b/nce/net_safety.py
@@ -1,11 +1,93 @@
 import asyncio
+import hashlib
 import ipaddress
 import logging
+import os
+import shutil
 import socket
+from typing import Any
 from urllib.parse import urlparse
 
 log = logging.getLogger("nce.net_safety")
 
+# Global registry for DNS-rebinding prevention pinning
+_PINNED_HOSTS: dict[str, str] = {}
+
+
+def _apply_transport_patch() -> None:
+    """
+    Hook httpcore AsyncNetworkBackend / SyncBackend connect_tcp to reuse resolved IPs,
+    effectively mitigating DNS rebinding (SSRF TOCTOU) by resolving hostnames once.
+    """
+
+    classes_to_patch: list[Any] = []
+    try:
+        from httpcore._backends.auto import AutoBackend
+
+        classes_to_patch.append(AutoBackend)
+    except ImportError:
+        pass
+
+    try:
+        from httpcore._backends.anyio import AnyIOBackend
+
+        classes_to_patch.append(AnyIOBackend)
+    except ImportError:
+        pass
+
+    try:
+        from httpcore._backends.trio import TrioBackend
+
+        classes_to_patch.append(TrioBackend)
+    except ImportError:
+        pass
+
+    try:
+        from httpcore._backends.sync import SyncBackend
+
+        classes_to_patch.append(SyncBackend)
+    except ImportError:
+        pass
+
+    def make_patched_connect_tcp(original_method: Any) -> Any:
+        async def patched_connect_tcp(
+            self: Any, host: str, port: int, *args: Any, **kwargs: Any
+        ) -> Any:
+            pinned_ip = _PINNED_HOSTS.get(host.lower().strip())
+            if pinned_ip:
+                return await original_method(self, pinned_ip, port, *args, **kwargs)
+            return await original_method(self, host, port, *args, **kwargs)
+
+        return patched_connect_tcp
+
+    def make_patched_connect_tcp_sync(original_method: Any) -> Any:
+        def patched_connect_tcp_sync(
+            self: Any, host: str, port: int, *args: Any, **kwargs: Any
+        ) -> Any:
+            pinned_ip = _PINNED_HOSTS.get(host.lower().strip())
+            if pinned_ip:
+                return original_method(self, pinned_ip, port, *args, **kwargs)
+            return original_method(self, host, port, *args, **kwargs)
+
+        return patched_connect_tcp_sync
+
+    for cls in classes_to_patch:
+        if hasattr(cls, "connect_tcp"):
+            orig = cls.connect_tcp
+            if not getattr(orig, "_is_patched", False):
+                import inspect
+
+                if inspect.iscoroutinefunction(orig):
+                    patched = make_patched_connect_tcp(orig)
+                else:
+                    patched = make_patched_connect_tcp_sync(orig)
+                patched._is_patched = True  # type: ignore[attr-defined]
+                cls.connect_tcp = patched
+
+
+_apply_transport_patch()
+
+
 _MAX_URL_LEN: int = 4_096
 
 # Explicit IPv6 CIDR denylist for SSRF (defense in depth next to ipaddress is_* flags).
@@ -144,10 +226,13 @@ async def validate_bridge_webhook_base_url(raw: str) -> str:
             "BRIDGE_WEBHOOK_BASE_URL must use https for non-loopback hosts"
         )
 
+    _PINNED_HOSTS[host.lower().strip()] = str(ips[0])
     return base
 
 
-async def assert_url_allowed_prefix(url: str, allowed_prefixes: tuple[str, ...], *, what: str) -> None:
+async def assert_url_allowed_prefix(
+    url: str, allowed_prefixes: tuple[str, ...], *, what: str
+) -> None:
     """
     Ensure ``url`` is under one of ``allowed_prefixes`` (parsed scheme/host/port/path match).
     Used for delta / pagination links stored in Redis.
@@ -172,6 +257,7 @@ async def assert_url_allowed_prefix(url: str, allowed_prefixes: tuple[str, ...],
                 raise BridgeURLValidationError(
                     f"{what}: host {host!r} resolves to a non-public address"
                 )
+            _PINNED_HOSTS[host.lower().strip()] = str(ips[0])
         except BridgeURLValidationError:
             raise
         except Exception as e:
@@ -249,6 +335,7 @@ async def validate_extractor_url(url: str, *, what: str = "extractor") -> str:
             f"(private/link-local/reserved/multicast/loopback)"
         )
 
+    _PINNED_HOSTS[host.lower().strip()] = str(ips[0])
     return raw
 
 
@@ -336,6 +423,7 @@ async def validate_webhook_payload_url(
                 f"webhook {field_name}: host {host!r} resolves to a non-public "
                 f"address (private/link-local/reserved/multicast/loopback)"
             )
+        _PINNED_HOSTS[host.lower().strip()] = str(ips[0])
     except BridgeURLValidationError:
         raise
     except Exception as e:
@@ -351,4 +439,62 @@ async def validate_webhook_payload_url(
         raise BridgeURLValidationError(
             f"webhook {field_name}: URL not within allowed prefixes (got {raw[:120]!r}...)"
         )
+    _PINNED_HOSTS[host.lower().strip()] = str(ips[0])
     return raw
+
+
+def _verify_binary_safety(executable: str, expected_hash: str | None) -> str | None:
+    """
+    Verify that the executable is an absolute path (or resolves to one),
+    exists as a file, and matches the expected SHA-256 hash if configured.
+    Returns the absolute path on success, or None on failure/mismatch.
+    """
+    if not executable:
+        log.warning("binary_safety: empty executable")
+        return None
+
+    # Reject relative paths that contain directory separators
+    if ("/" in executable or "\\" in executable) and not os.path.isabs(executable):
+        log.warning(
+            "binary_safety: relative path containing separators is not allowed: %s", executable
+        )
+        return None
+
+    if os.path.isfile(executable):
+        resolved: str | None = executable
+    else:
+        resolved = shutil.which(executable)
+
+    if not resolved:
+        log.warning("binary_safety: executable not found: %s", executable)
+        return None
+
+    abs_path = os.path.abspath(resolved)
+    if not os.path.isabs(abs_path):
+        log.warning("binary_safety: path is not absolute: %s", abs_path)
+        return None
+
+    if not os.path.isfile(abs_path):
+        log.warning("binary_safety: path is not a file: %s", abs_path)
+        return None
+
+    if expected_hash:
+        expected_hash = expected_hash.strip().lower()
+        h = hashlib.sha256()
+        try:
+            with open(abs_path, "rb") as f:
+                while chunk := f.read(8192):
+                    h.update(chunk)
+            file_hash = h.hexdigest().lower()
+            if file_hash != expected_hash:
+                log.warning(
+                    "binary_safety: hash mismatch for %s: expected %s, got %s",
+                    abs_path,
+                    expected_hash,
+                    file_hash,
+                )
+                return None
+        except Exception as e:
+            log.warning("binary_safety: failed to hash %s: %s", abs_path, e)
+            return None
+    return abs_path
diff --git a/nce/observability.py b/nce/observability.py
index ef19861..1f5b8ce 100644
--- a/nce/observability.py
+++ b/nce/observability.py
@@ -87,9 +87,7 @@ try:
             # _names_to_collectors is a private prometheus_client attribute; guard
             # with getattr so a future library rename doesn't cause AttributeError.
             collectors = getattr(_PROM_REGISTRY, "_names_to_collectors", {})
-            return collectors.get(name) or metric_cls(
-                name, *args, registry=None, **kwargs
-            )
+            return collectors.get(name) or metric_cls(name, *args, registry=None, **kwargs)
 
     def _safe_counter(name: str, *args, **kwargs) -> Counter:
         return _safe_metric(Counter, name, *args, **kwargs)
@@ -284,6 +282,22 @@ EXTERNAL_HTTP_LATENCY_SECONDS = _safe_histogram(
     ["operation"],
 )
 
+# Quota and embedding-fallback metrics (Batch 19)
+QUOTA_CONSUMED = _safe_gauge(
+    "nce_quota_consumed_total",
+    "Current consumed resource amount for a namespace/agent quota",
+    ["namespace_id", "resource_type", "agent_id"],
+)
+QUOTA_REMAINING = _safe_gauge(
+    "nce_quota_remaining",
+    "Current remaining resource limit for a namespace/agent quota",
+    ["namespace_id", "resource_type", "agent_id"],
+)
+EMBEDDING_FALLBACKS = _safe_counter(
+    "nce_embedding_fallbacks_total",
+    "Total count of embedding fallback/hash-stub triggerings",
+)
+
 # --- Initialization ---
 
 _tracer_initialized = False
@@ -441,7 +455,7 @@ class SagaMetrics:
         return self
 
     def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
-        if cfg.NCE_OBSERVABILITY_ENABLED:
+        if cfg.NCE_OBSERVABILITY_ENABLED or self.operation == "store_memory":
             result = "success" if exc_type is None else "failure"
             duration = time.perf_counter() - self.start_time
             SAGA_DURATION.labels(operation=self.operation, result=result).observe(duration)
@@ -593,6 +607,7 @@ class traced_worker_job(ContextDecorator):
 
     Restores the remote trace context and starts a new nested span for the job execution.
     """
+
     def __init__(self, operation_name: str) -> None:
         self.operation_name = operation_name
         self.token = None
@@ -604,6 +619,7 @@ class traced_worker_job(ContextDecorator):
             return self
 
         from rq import get_current_job
+
         job = get_current_job()
         if job and job.meta:
             try:
diff --git a/nce/orchestrators/memory.py b/nce/orchestrators/memory.py
index a331833..cf27243 100644
--- a/nce/orchestrators/memory.py
+++ b/nce/orchestrators/memory.py
@@ -349,18 +349,20 @@ class MemoryOrchestrator(OrchestratorBase):
                 row = await conn.fetchrow(
                     """
                     INSERT INTO saga_execution_log (saga_type, namespace_id, agent_id, state, payload)
-                    VALUES ($1, $2::uuid, $3, 'started', $4)
+                    VALUES ($1, $2::uuid, $3, 'started', $4::jsonb)
                     RETURNING id
                     """,
                     saga_type,
                     str(payload.namespace_id),
                     payload.agent_id,
-                    {
-                        "memory_type": payload.memory_type.value,
-                        "assertion_type": payload.assertion_type.value,
-                        "summary": payload.summary,
-                        "metadata": payload.metadata,
-                    },
+                    json.dumps(
+                        {
+                            "memory_type": payload.memory_type.value,
+                            "assertion_type": payload.assertion_type.value,
+                            "summary": payload.summary,
+                            "metadata": payload.metadata,
+                        }
+                    ),
                 )
         return str(row["id"])
 
@@ -379,7 +381,7 @@ class MemoryOrchestrator(OrchestratorBase):
                     """,
                     state,
                     saga_id,
-                    payload_patch,
+                    json.dumps(payload_patch),
                 )
             else:
                 await conn.execute(
@@ -722,96 +724,97 @@ class MemoryOrchestrator(OrchestratorBase):
 
     async def _run_store_memory_saga(self, payload: StoreMemoryRequest) -> dict:
         """Executes the core transactional write saga across MongoDB, PG, and Redis."""
-        inserted_mongo_id: str | None = None
-        inserted_result = None
-        memory_id: UUID | None = None
-        pg_committed = False
-        saga_id = await self._saga_log_start("store_memory", payload)
-
-        try:
-            # --- Phase 0.3: PII Redaction + Graph Extraction ---
-            (
-                pii_result,
-                sanitized_summary,
-                sanitized_heavy,
-                entities,
-                triplets,
-            ) = await self._apply_pii_pipeline(payload)
-
-            # STEP 1: Episodic Commit (MongoDB)
-            user_id = payload.metadata.get("user_id") if payload.metadata else None
-            session_id = payload.metadata.get("session_id") if payload.metadata else None
-
-            inserted_mongo_id, inserted_result = await self._store_episodic_mongodb(
-                payload, sanitized_heavy, pii_result
-            )
+        with SagaMetrics("store_memory"):
+            inserted_mongo_id: str | None = None
+            inserted_result = None
+            memory_id: UUID | None = None
+            pg_committed = False
+            saga_id = await self._saga_log_start("store_memory", payload)
 
-            # Pre-compute all embeddings OUTSIDE the PG transaction
-            all_texts = [sanitized_summary] + [e.label for e in entities]
-            all_vectors = await _embeddings.embed_batch(all_texts)
-            vector = all_vectors[0]
-            node_vecs = all_vectors[1:]
-
-            # STEP 2 + 2b + 2c: Atomic Semantic + Graph Commit (single PG transaction)
-            memory_id = await self._store_semantic_graph_pg(
-                payload=payload,
-                sanitized_summary=sanitized_summary,
-                vector=vector,
-                node_vecs=node_vecs,
-                pii_result=pii_result,
-                inserted_mongo_id=inserted_mongo_id,
-                entities=entities,
-                triplets=triplets,
-                saga_id=saga_id,
-                user_id=user_id,
-                session_id=session_id,
-            )
+            try:
+                # --- Phase 0.3: PII Redaction + Graph Extraction ---
+                (
+                    pii_result,
+                    sanitized_summary,
+                    sanitized_heavy,
+                    entities,
+                    triplets,
+                ) = await self._apply_pii_pipeline(payload)
 
-            # Mark committed once exited from PG session block successfully
-            pg_committed = True
-
-        except Exception as e:
-            collection = self.mongo_client.memory_archive.episodes
-            await self._apply_rollback_on_failure(
-                e=e,
-                payload=payload,
-                collection=collection,
-                inserted_mongo_id=inserted_mongo_id,
-                inserted_result=inserted_result,
-                memory_id=memory_id,
-                pg_committed=pg_committed,
-                saga_id=saga_id,
-            )
-            raise
+                # STEP 1: Episodic Commit (MongoDB)
+                user_id = payload.metadata.get("user_id") if payload.metadata else None
+                session_id = payload.metadata.get("session_id") if payload.metadata else None
 
-        # --- PG committed; all subsequent failures are advisory ---
-        try:
-            await self._saga_log_transition(
-                saga_id, SagaState.PG_COMMITTED, payload_patch={"memory_id": str(memory_id)}
-            )
-        except Exception:
-            log.warning("[SAGA] PG_COMMITTED transition failed.", exc_info=True)
+                inserted_mongo_id, inserted_result = await self._store_episodic_mongodb(
+                    payload, sanitized_heavy, pii_result
+                )
 
-        # STEP 3: Working Memory (Redis)
-        await self._cache_working_memory_redis(
-            payload.namespace_id, user_id, session_id, sanitized_summary
-        )
+                # Pre-compute all embeddings OUTSIDE the PG transaction
+                all_texts = [sanitized_summary] + [e.label for e in entities]
+                all_vectors = await _embeddings.embed_batch(all_texts)
+                vector = all_vectors[0]
+                node_vecs = all_vectors[1:]
 
-        # STEP 4: Contradiction Detection
-        contradiction_result = await self._detect_contradictions_sync(
-            payload, memory_id, sanitized_summary, vector, triplets
-        )
+                # STEP 2 + 2b + 2c: Atomic Semantic + Graph Commit (single PG transaction)
+                memory_id = await self._store_semantic_graph_pg(
+                    payload=payload,
+                    sanitized_summary=sanitized_summary,
+                    vector=vector,
+                    node_vecs=node_vecs,
+                    pii_result=pii_result,
+                    inserted_mongo_id=inserted_mongo_id,
+                    entities=entities,
+                    triplets=triplets,
+                    saga_id=saga_id,
+                    user_id=user_id,
+                    session_id=session_id,
+                )
 
-        try:
-            await self._saga_log_transition(saga_id, SagaState.COMPLETED)
-        except Exception:
-            log.warning("[SAGA] COMPLETED transition failed.", exc_info=True)
+                # Mark committed once exited from PG session block successfully
+                pg_committed = True
 
-        return {
-            "quarantined": False,
-            "payload_ref": inserted_mongo_id,
-            "contradiction": contradiction_result,
-        }
+            except Exception as e:
+                collection = self.mongo_client.memory_archive.episodes
+                await self._apply_rollback_on_failure(
+                    e=e,
+                    payload=payload,
+                    collection=collection,
+                    inserted_mongo_id=inserted_mongo_id,
+                    inserted_result=inserted_result,
+                    memory_id=memory_id,
+                    pg_committed=pg_committed,
+                    saga_id=saga_id,
+                )
+                raise
+
+            # --- PG committed; all subsequent failures are advisory ---
+            try:
+                await self._saga_log_transition(
+                    saga_id, SagaState.PG_COMMITTED, payload_patch={"memory_id": str(memory_id)}
+                )
+            except Exception:
+                log.warning("[SAGA] PG_COMMITTED transition failed.", exc_info=True)
+
+            # STEP 3: Working Memory (Redis)
+            await self._cache_working_memory_redis(
+                payload.namespace_id, user_id, session_id, sanitized_summary
+            )
+
+            # STEP 4: Contradiction Detection
+            contradiction_result = await self._detect_contradictions_sync(
+                payload, memory_id, sanitized_summary, vector, triplets
+            )
+
+            try:
+                await self._saga_log_transition(saga_id, SagaState.COMPLETED)
+            except Exception:
+                log.warning("[SAGA] COMPLETED transition failed.", exc_info=True)
+
+            return {
+                "quarantined": False,
+                "payload_ref": inserted_mongo_id,
+                "contradiction": contradiction_result,
+            }
 
     async def store_memory(self, payload: StoreMemoryRequest) -> dict:
         """
@@ -835,10 +838,9 @@ class MemoryOrchestrator(OrchestratorBase):
                 return quarantine_result
 
             # Bypass or R >= 0.65 -> proceed with write saga (Slow I/O outside PG transaction)
-            with SagaMetrics("store_memory"):
-                res = await self._run_store_memory_saga(payload)
-                log.debug("Saga memory storage execution complete")
-                return res
+            res = await self._run_store_memory_saga(payload)
+            log.debug("Saga memory storage execution complete")
+            return res
 
     # ------------------------------------------------------------------
     # store_artifact (formerly store_media)
@@ -873,7 +875,9 @@ class MemoryOrchestrator(OrchestratorBase):
 
                 bucket_name = f"mcp-{payload.media_type}"
                 file_ext = os.path.splitext(safe_path)[1]
-                object_name = f"{payload.session_id}_{uuid.uuid4().hex}{file_ext}"
+                object_name = (
+                    f"{payload.namespace_id}/{payload.session_id}/{uuid.uuid4().hex}{file_ext}"
+                )
 
                 await asyncio.to_thread(
                     self.minio_client.fput_object,
@@ -1164,12 +1168,19 @@ class MemoryOrchestrator(OrchestratorBase):
         if session_id and not _SAFE_ID_RE.match(session_id):
             raise ValueError("Invalid session_id format")
 
-        if not as_of and limit == 1 and offset == 0 and not user_id and not session_id:
-            redis_key = f"cache:{namespace_id}:{agent_id}"
-            cached = await self.redis_client.get(redis_key)
-            if cached:
-                log.debug("[Redis] Cache hit. key=%s", redis_key)
-                return [cached.decode()]
+        if not as_of and limit == 1 and offset == 0:
+            if user_id and session_id:
+                redis_key = f"cache:{namespace_id}:{user_id}:{session_id}"
+            elif not user_id and not session_id:
+                redis_key = f"cache:{namespace_id}:{agent_id}"
+            else:
+                redis_key = None
+
+            if redis_key:
+                cached = await self.redis_client.get(redis_key)
+                if cached:
+                    log.debug("[Redis] Cache hit. key=%s", redis_key)
+                    return [cached.decode()]
 
         async with scoped_pg_session(self._db_pool(read_only=True), namespace_id) as conn:
             filters = ["namespace_id = $1", "memory_type = 'episodic'"]
@@ -1221,9 +1232,16 @@ class MemoryOrchestrator(OrchestratorBase):
             if txt:
                 results.append(str(txt))
 
-        if not as_of and limit == 1 and offset == 0 and results and not user_id and not session_id:
-            redis_key = f"cache:{namespace_id}:{agent_id}"
-            await self.redis_client.setex(redis_key, cfg.REDIS_TTL, results[0])
+        if not as_of and limit == 1 and offset == 0 and results:
+            if user_id and session_id:
+                redis_key = f"cache:{namespace_id}:{user_id}:{session_id}"
+            elif not user_id and not session_id:
+                redis_key = f"cache:{namespace_id}:{agent_id}"
+            else:
+                redis_key = None
+
+            if redis_key:
+                await self.redis_client.setex(redis_key, cfg.REDIS_TTL, results[0])
 
         return results
 
diff --git a/nce/quotas.py b/nce/quotas.py
index 51854f0..0a721fa 100644
--- a/nce/quotas.py
+++ b/nce/quotas.py
@@ -21,6 +21,7 @@ import asyncpg
 from asyncpg.exceptions import IntegrityConstraintViolationError
 
 from nce.config import cfg
+from nce.observability import QUOTA_CONSUMED, QUOTA_REMAINING
 
 log = logging.getLogger("nce.quotas")
 
@@ -234,6 +235,22 @@ async def _consume_resources_redis(
                         )
                     applied.append((qid, delta))
                     reservation.steps.append((qid, delta))
+
+                    # Update gauges (Batch 19)
+                    used = int(res)
+                    remaining = max(0, lim - used)
+                    ns_str = str(namespace_id)
+                    aid_str = str(row["agent_id"] or "global")
+                    QUOTA_CONSUMED.labels(
+                        namespace_id=ns_str,
+                        resource_type=resource_type,
+                        agent_id=aid_str,
+                    ).set(used)
+                    QUOTA_REMAINING.labels(
+                        namespace_id=ns_str,
+                        resource_type=resource_type,
+                        agent_id=aid_str,
+                    ).set(remaining)
     except QuotaExceededError:
         raise
     except Exception:
@@ -316,7 +333,7 @@ async def consume_resources(
                                 updated_at = now()
                             WHERE id = $2
                               AND used_amount + $1 <= limit_amount
-                            RETURNING id
+                            RETURNING id, used_amount, limit_amount
                             """,
                             delta,
                             row["id"],
@@ -328,6 +345,24 @@ async def consume_resources(
                                 f"resource={resource_type!r} ({scope} limit)"
                             )
                         reservation.steps.append((row["id"], delta))
+
+                        # Update gauges (Batch 19)
+                        if "used_amount" in upd and "limit_amount" in upd:
+                            used = int(upd["used_amount"])
+                            lim = int(upd["limit_amount"])
+                            remaining = max(0, lim - used)
+                            ns_str = str(namespace_id)
+                            aid_str = str(row["agent_id"] or "global")
+                            QUOTA_CONSUMED.labels(
+                                namespace_id=ns_str,
+                                resource_type=resource_type,
+                                agent_id=aid_str,
+                            ).set(used)
+                            QUOTA_REMAINING.labels(
+                                namespace_id=ns_str,
+                                resource_type=resource_type,
+                                agent_id=aid_str,
+                            ).set(remaining)
             except IntegrityConstraintViolationError as e:
                 raise QuotaExceededError(
                     f"Quota integrity constraint violated for namespace={namespace_id}: {e}"
@@ -384,11 +419,7 @@ async def quota_redis_flush_loop(redis_client: Any, pool: asyncpg.Pool) -> None:
     while True:
         try:
             await asyncio.sleep(cfg.NCE_QUOTA_REDIS_FLUSH_INTERVAL_S)
-            if (
-                cfg.NCE_QUOTAS_ENABLED
-                and cfg.NCE_QUOTA_REDIS_COUNTERS
-                and redis_client is not None
-            ):
+            if cfg.NCE_QUOTAS_ENABLED and cfg.NCE_QUOTA_REDIS_COUNTERS and redis_client is not None:
                 await flush_quota_counters_to_postgres(redis_client, pool)
         except asyncio.CancelledError:
             break
diff --git a/nce/tool_registry.py b/nce/tool_registry.py
index a64adbf..b2b1385 100644
--- a/nce/tool_registry.py
+++ b/nce/tool_registry.py
@@ -144,6 +144,10 @@ TOOL_REGISTRY: dict[str, ToolSpec] = {
         _h(graph_mcp_handlers, "handle_graph_search"),
         cacheable=True,
     ),
+    "neuromorphic_search": ToolSpec(
+        _h(graph_mcp_handlers, "handle_neuromorphic_search"),
+        cacheable=True,
+    ),
     # ------------------------------------------------------------------
     # Bridge / integration tools
     # ------------------------------------------------------------------
diff --git a/nce/vertical_modules/dynamics365/client.py b/nce/vertical_modules/dynamics365/client.py
index ba9e66c..8e50de0 100644
--- a/nce/vertical_modules/dynamics365/client.py
+++ b/nce/vertical_modules/dynamics365/client.py
@@ -170,14 +170,24 @@ class DataverseClient:
         params: dict[str, str] | None,
         json_body: dict[str, Any] | None,
     ) -> dict[str, Any]:
-        resp = await client.request(
-            method,
-            url,
-            headers=headers,
-            params=params,
-            json=json_body,
-            follow_redirects=True,
-        )
+        from nce.http_resilience import ExternalAPIClientError, request_with_retry
+
+        try:
+            resp = await request_with_retry(
+                client,
+                method,
+                url,
+                headers=headers,
+                params=params,
+                json=json_body,
+                follow_redirects=True,
+                operation_name="dynamics365:odata",
+            )
+        except ExternalAPIClientError as exc:
+            if exc.status_code == 404:
+                return {}
+            raise
+
         if resp.status_code == 404:
             return {}
         resp.raise_for_status()
diff --git a/nce/vertical_modules/dynamics365/netbox_bridge.py b/nce/vertical_modules/dynamics365/netbox_bridge.py
index ff1f70f..6d5c8e2 100644
--- a/nce/vertical_modules/dynamics365/netbox_bridge.py
+++ b/nce/vertical_modules/dynamics365/netbox_bridge.py
@@ -96,9 +96,17 @@ class NetBoxBridgeClient:
         next_url: str | None = f"{url}?limit={self._page_size}&offset=0"
         headers = {**self._HEADERS, **self._auth}
 
+        from nce.http_resilience import request_with_retry
+
         async with httpx.AsyncClient(timeout=30.0) as client:
             while next_url:
-                resp = await client.get(next_url, headers=headers)
+                resp = await request_with_retry(
+                    client,
+                    "GET",
+                    next_url,
+                    headers=headers,
+                    operation_name="netbox:paginate",
+                )
                 resp.raise_for_status()
                 body = resp.json()
                 results.extend(body.get("results") or [])
@@ -321,8 +329,8 @@ class D365NetBoxBridge:
 
         site_by_norm: dict[str, dict] = {_normalize(s["name"]): s for s in nb_sites}
         site_by_slug: dict[str, dict] = {s.get("slug", ""): s for s in nb_sites}
-        loc_by_norm: dict[str, dict] = {_normalize(l["name"]): l for l in nb_locs}
-        loc_by_slug: dict[str, dict] = {l.get("slug", ""): l for l in nb_locs}
+        loc_by_norm: dict[str, dict] = {_normalize(loc["name"]): loc for loc in nb_locs}
+        loc_by_slug: dict[str, dict] = {loc.get("slug", ""): loc for loc in nb_locs}
 
         stats: dict[str, int] = {"exact": 0, "slug": 0, "fuzzy": 0, "unmatched": 0}
         edges: list[tuple[str, str, str, float]] = []
diff --git a/nce/vertical_modules/netbox/circuits.py b/nce/vertical_modules/netbox/circuits.py
index e617a65..67a649d 100644
--- a/nce/vertical_modules/netbox/circuits.py
+++ b/nce/vertical_modules/netbox/circuits.py
@@ -41,7 +41,7 @@ class NetBoxCircuitsClient:
         if self._client is not None:
             return await self._send_get(self._client, url)
 
-        async with httpx.AsyncClient() as client:
+        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
             return await self._send_get(client, url)
 
     async def _send_get(self, client: httpx.AsyncClient, url: str) -> list[dict[str, Any]]:
@@ -144,7 +144,7 @@ class NetBoxCircuitEscalator:
                 provider = circuit.get("provider") or {}
                 provider_id = provider.get("id") or circuit.get("provider_id")
                 provider_name = provider.get("name") or "Unknown Provider"
-                
+
                 custom_fields = circuit.get("custom_fields") or {}
                 account_string = (
                     custom_fields.get("account_string")
@@ -152,12 +152,8 @@ class NetBoxCircuitEscalator:
                     or circuit.get("account")
                     or f"ACCT-{provider_name.upper()}"
                 )
-                
-                commit_rate = (
-                    circuit.get("commit_rate")
-                    or custom_fields.get("commit_rate")
-                    or 0
-                )
+
+                commit_rate = circuit.get("commit_rate") or custom_fields.get("commit_rate") or 0
 
                 # Auto-generate structured upstream escalation ticket targeting external provider
                 ticket = {
@@ -169,7 +165,9 @@ class NetBoxCircuitEscalator:
                     "account_string": account_string,
                     "commit_rate_kbps": int(commit_rate) if commit_rate else None,
                     "causally_linked_degradations": causally_linked,
-                    "severity": "CRITICAL" if any(v["degradation_severity"] >= 0.8 for v in causally_linked.values()) else "WARNING",
+                    "severity": "CRITICAL"
+                    if any(v["degradation_severity"] >= 0.8 for v in causally_linked.values())
+                    else "WARNING",
                     "description": (
                         f"Automated NetBox Circuit Escalation for Account {account_string}. "
                         f"Circuit {circuit_id} provided by {provider_name} has been causally linked to telemetry degradation "
diff --git a/nce/vertical_modules/netbox/contacts.py b/nce/vertical_modules/netbox/contacts.py
index e768fa3..6915365 100644
--- a/nce/vertical_modules/netbox/contacts.py
+++ b/nce/vertical_modules/netbox/contacts.py
@@ -40,7 +40,7 @@ class NetBoxClient:
         if self._client is not None:
             return await self._send_get(self._client, url)
 
-        async with httpx.AsyncClient() as client:
+        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
             return await self._send_get(client, url)
 
     async def fetch_contact_assignments(self) -> list[dict[str, Any]]:
@@ -49,7 +49,7 @@ class NetBoxClient:
         if self._client is not None:
             return await self._send_get(self._client, url)
 
-        async with httpx.AsyncClient() as client:
+        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
             return await self._send_get(client, url)
 
     async def _send_get(self, client: httpx.AsyncClient, url: str) -> list[dict[str, Any]]:
@@ -148,10 +148,14 @@ class NetBoxContactSync:
                 tensor.append(0.0)
             tensor = tensor[:6]
 
-            records.append({
-                "empathic_tensor": tensor,
-                "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
-            })
+            records.append(
+                {
+                    "empathic_tensor": tensor,
+                    "created_at": r["created_at"].isoformat()
+                    if hasattr(r["created_at"], "isoformat")
+                    else str(r["created_at"]),
+                }
+            )
         return records
 
     async def evaluate_contact_stress_report(
@@ -166,7 +170,9 @@ class NetBoxContactSync:
         Build, encrypt, and decrypt a contact's stress report to verify the data
         payload alignment and field parsing against NCE cryptoprimitives.
         """
-        records = await self.fetch_stress_records_for_operator(conn, namespace_id, operator_id, email)
+        records = await self.fetch_stress_records_for_operator(
+            conn, namespace_id, operator_id, email
+        )
         if not records:
             return {
                 "burnout_alert": False,
@@ -229,7 +235,9 @@ class NetBoxContactSync:
         async with conn.transaction():
             # 1. Evaluate individual stress and update database
             for contact in contacts:
-                username = contact.get("username") or contact.get("name", "").lower().replace(" ", "_")
+                username = contact.get("username") or contact.get("name", "").lower().replace(
+                    " ", "_"
+                )
                 email = contact.get("email") or f"{username}@example.com"
 
                 # Parse frustration metric from encrypted tensor pipeline
@@ -265,14 +273,16 @@ class NetBoxContactSync:
                     status,
                 )
 
-                contact_details.append({
-                    "username": username,
-                    "email": email,
-                    "is_active": is_active,
-                    "status": status,
-                    "frustration": last_frustration,
-                    "weight": weight,
-                })
+                contact_details.append(
+                    {
+                        "username": username,
+                        "email": email,
+                        "is_active": is_active,
+                        "status": status,
+                        "frustration": last_frustration,
+                        "weight": weight,
+                    }
+                )
 
             # 2. Redistribute load weights among active contacts
             active_contacts = [c for c in contact_details if c["is_active"]]
diff --git a/nce/vertical_modules/netbox/discovery.py b/nce/vertical_modules/netbox/discovery.py
index 5f3aeab..6d10d86 100644
--- a/nce/vertical_modules/netbox/discovery.py
+++ b/nce/vertical_modules/netbox/discovery.py
@@ -29,9 +29,9 @@ DEVICE_WRITE_SCHEMA = {
         "role": {"type": ["integer", "string"]},
         "site": {"type": ["integer", "string"]},
         "serial": {"type": ["string", "null"]},
-        "custom_fields": {"type": "object"}
+        "custom_fields": {"type": "object"},
     },
-    "required": ["name", "device_type", "role", "site"]
+    "required": ["name", "device_type", "role", "site"],
 }
 
 INTERFACE_WRITE_SCHEMA = {
@@ -39,9 +39,9 @@ INTERFACE_WRITE_SCHEMA = {
     "properties": {
         "device": {"type": ["integer", "string"]},
         "name": {"type": "string", "minLength": 1},
-        "type": {"type": "string", "minLength": 1}
+        "type": {"type": "string", "minLength": 1},
     },
-    "required": ["device", "name", "type"]
+    "required": ["device", "name", "type"],
 }
 
 CABLE_WRITE_SCHEMA = {
@@ -53,11 +53,11 @@ CABLE_WRITE_SCHEMA = {
                 "type": "object",
                 "properties": {
                     "object_type": {"type": "string"},
-                    "object_id": {"type": ["integer", "string"]}
+                    "object_id": {"type": ["integer", "string"]},
                 },
-                "required": ["object_type", "object_id"]
+                "required": ["object_type", "object_id"],
             },
-            "minItems": 1
+            "minItems": 1,
         },
         "b_terminations": {
             "type": "array",
@@ -65,15 +65,15 @@ CABLE_WRITE_SCHEMA = {
                 "type": "object",
                 "properties": {
                     "object_type": {"type": "string"},
-                    "object_id": {"type": ["integer", "string"]}
+                    "object_id": {"type": ["integer", "string"]},
                 },
-                "required": ["object_type", "object_id"]
+                "required": ["object_type", "object_id"],
             },
-            "minItems": 1
+            "minItems": 1,
         },
-        "status": {"type": "string"}
+        "status": {"type": "string"},
     },
-    "required": ["a_terminations", "b_terminations"]
+    "required": ["a_terminations", "b_terminations"],
 }
 
 
@@ -83,19 +83,29 @@ class NetBoxDiscoveryReconciler:
     Saves new detections as staging change proposals using the NetBox Branching API.
     """
 
-    def __init__(self, netbox_client: NetBoxGraphQLClient, rest_client: httpx.AsyncClient | None = None):
+    def __init__(
+        self, netbox_client: NetBoxGraphQLClient, rest_client: httpx.AsyncClient | None = None
+    ):
         self.netbox_client = netbox_client
         self.base_url = netbox_client.base_url
         self.headers = netbox_client.headers.copy()
         self._rest_client = rest_client
 
-    async def _send_get(self, client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
+    async def _send_get(
+        self, client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None
+    ) -> dict[str, Any]:
         h = headers if headers is not None else self.headers
         resp = await client.get(url, headers=h, timeout=10.0)
         resp.raise_for_status()
         return resp.json()
 
-    async def _send_post(self, client: httpx.AsyncClient, url: str, json_data: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
+    async def _send_post(
+        self,
+        client: httpx.AsyncClient,
+        url: str,
+        json_data: dict[str, Any],
+        headers: dict[str, str] | None = None,
+    ) -> dict[str, Any]:
         h = headers if headers is not None else self.headers
         resp = await client.post(url, json=json_data, headers=h, timeout=10.0)
         resp.raise_for_status()
@@ -124,7 +134,7 @@ class NetBoxDiscoveryReconciler:
         if self._rest_client is not None:
             return await execute_ops(self._rest_client)
         else:
-            async with httpx.AsyncClient() as client:
+            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                 return await execute_ops(client)
 
     async def reconcile(self, live_topology: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
@@ -133,6 +143,7 @@ class NetBoxDiscoveryReconciler:
         Pinpoints unregistered devices, interfaces, and connections.
         """
         from nce.vertical_modules.netbox.graphql_activation import UNIFIED_TOPOLOGY_QUERY
+
         response = await self.netbox_client.execute_query(UNIFIED_TOPOLOGY_QUERY)
 
         cached_devices: dict[str, Any] = {}
@@ -199,24 +210,28 @@ class NetBoxDiscoveryReconciler:
 
             if dev_name not in cached_devices:
                 cached_devices[dev_name] = None
-                unregistered_devices.append({
-                    "name": dev_name,
-                    "serial": dev.get("serial") or "UNKNOWN",
-                    "device_type": dev.get("device_type") or 1,
-                    "role": dev.get("role") or 1,
-                    "site": dev.get("site") or 1,
-                    "custom_fields": dev.get("custom_fields") or {}
-                })
+                unregistered_devices.append(
+                    {
+                        "name": dev_name,
+                        "serial": dev.get("serial") or "UNKNOWN",
+                        "device_type": dev.get("device_type") or 1,
+                        "role": dev.get("role") or 1,
+                        "site": dev.get("site") or 1,
+                        "custom_fields": dev.get("custom_fields") or {},
+                    }
+                )
 
             interfaces = dev.get("interfaces") or []
             for int_name in interfaces:
                 if (dev_name, int_name) not in cached_interfaces:
                     cached_interfaces.add((dev_name, int_name))
-                    unregistered_interfaces.append({
-                        "device": dev_name,
-                        "name": int_name,
-                        "type": cfg.NCE_NETBOX_DEFAULT_INTERFACE_TYPE
-                    })
+                    unregistered_interfaces.append(
+                        {
+                            "device": dev_name,
+                            "name": int_name,
+                            "type": cfg.NCE_NETBOX_DEFAULT_INTERFACE_TYPE,
+                        }
+                    )
 
         # 2. Reconcile cables/connections
         live_cables = live_topology.get("cables") or []
@@ -231,20 +246,22 @@ class NetBoxDiscoveryReconciler:
             conn_key = tuple(sorted([(a_dev, a_int), (b_dev, b_int)]))
             if conn_key not in cached_connections:  # type: ignore
                 cached_connections.add(conn_key)  # type: ignore
-                unregistered_cables.append({
-                    "a_terminations": [
-                        {"object_type": "dcim.interface", "object_id": f"{a_dev}:{a_int}"}
-                    ],
-                    "b_terminations": [
-                        {"object_type": "dcim.interface", "object_id": f"{b_dev}:{b_int}"}
-                    ],
-                    "status": "connected"
-                })
+                unregistered_cables.append(
+                    {
+                        "a_terminations": [
+                            {"object_type": "dcim.interface", "object_id": f"{a_dev}:{a_int}"}
+                        ],
+                        "b_terminations": [
+                            {"object_type": "dcim.interface", "object_id": f"{b_dev}:{b_int}"}
+                        ],
+                        "status": "connected",
+                    }
+                )
 
         return {
             "devices": unregistered_devices,
             "interfaces": unregistered_interfaces,
-            "cables": unregistered_cables
+            "cables": unregistered_cables,
         }
 
     async def stage_discovery(
@@ -268,12 +285,14 @@ class NetBoxDiscoveryReconciler:
                 validate(instance=dev, schema=DEVICE_WRITE_SCHEMA)
                 url = f"{self.base_url}/api/dcim/devices/"
                 res = await self._send_post(client, url, dev, headers=branch_headers)
-                proposals.append({
-                    "object_type": "device",
-                    "name": dev["name"],
-                    "netbox_id": res.get("id"),
-                    "status": "staged"
-                })
+                proposals.append(
+                    {
+                        "object_type": "device",
+                        "name": dev["name"],
+                        "netbox_id": res.get("id"),
+                        "status": "staged",
+                    }
+                )
 
             # 2. Stage Interfaces
             interfaces = unregistered_assets.get("interfaces") or []
@@ -281,12 +300,14 @@ class NetBoxDiscoveryReconciler:
                 validate(instance=interface, schema=INTERFACE_WRITE_SCHEMA)
                 url = f"{self.base_url}/api/dcim/interfaces/"
                 res = await self._send_post(client, url, interface, headers=branch_headers)
-                proposals.append({
-                    "object_type": "interface",
-                    "name": f"{interface['device']}:{interface['name']}",
-                    "netbox_id": res.get("id"),
-                    "status": "staged"
-                })
+                proposals.append(
+                    {
+                        "object_type": "interface",
+                        "name": f"{interface['device']}:{interface['name']}",
+                        "netbox_id": res.get("id"),
+                        "status": "staged",
+                    }
+                )
 
             # 3. Stage Cables
             cables = unregistered_assets.get("cables") or []
@@ -294,16 +315,14 @@ class NetBoxDiscoveryReconciler:
                 validate(instance=cable, schema=CABLE_WRITE_SCHEMA)
                 url = f"{self.base_url}/api/dcim/cables/"
                 res = await self._send_post(client, url, cable, headers=branch_headers)
-                proposals.append({
-                    "object_type": "cable",
-                    "netbox_id": res.get("id"),
-                    "status": "staged"
-                })
+                proposals.append(
+                    {"object_type": "cable", "netbox_id": res.get("id"), "status": "staged"}
+                )
 
             return proposals
 
         if self._rest_client is not None:
             return await run_staging(self._rest_client)
         else:
-            async with httpx.AsyncClient() as client:
+            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                 return await run_staging(client)
diff --git a/nce/vertical_modules/netbox/graphql_activation.py b/nce/vertical_modules/netbox/graphql_activation.py
index 37349f9..26a8a5c 100644
--- a/nce/vertical_modules/netbox/graphql_activation.py
+++ b/nce/vertical_modules/netbox/graphql_activation.py
@@ -121,7 +121,9 @@ class NetBoxGraphQLClient:
         }
         self._client = client
 
-    async def execute_query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
+    async def execute_query(
+        self, query: str, variables: dict[str, Any] | None = None
+    ) -> dict[str, Any]:
         """
         Executes a GraphQL query payload. Logs and raises on GraphQL-level errors.
         """
@@ -132,10 +134,12 @@ class NetBoxGraphQLClient:
         if self._client is not None:
             return await self._send_request(self._client, payload)
 
-        async with httpx.AsyncClient() as client:
+        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
             return await self._send_request(client, payload)
 
-    async def _send_request(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> dict[str, Any]:
+    async def _send_request(
+        self, client: httpx.AsyncClient, payload: dict[str, Any]
+    ) -> dict[str, Any]:
         resp = await client.post(self.url, json=payload, headers=self.headers, timeout=10.0)
         resp.raise_for_status()
         data = resp.json()
@@ -152,7 +156,12 @@ def parse_cable(cable: dict[str, Any], add_edge_fn: Callable[[str, str, float],
     status = cable.get("status") or ""
     # Set weight based on status
     weight = 1.0
-    if isinstance(status, str) and status.upper() in ("PLANNED", "DEPRECATED", "FAILED", "DISCONNECTED"):
+    if isinstance(status, str) and status.upper() in (
+        "PLANNED",
+        "DEPRECATED",
+        "FAILED",
+        "DISCONNECTED",
+    ):
         weight = 0.0
 
     a_terms = cable.get("a_terminations") or []
@@ -319,6 +328,7 @@ class GraphQLSpikingActivator:
             if conn is not None:
                 # Set local namespace context
                 from nce.auth import set_namespace_context
+
                 await set_namespace_context(conn, ns_uuid)
 
                 # Fetch check if anchor_label is authorized (exists in kg_nodes or topology_graph)
diff --git a/tests/test_http_resilience.py b/tests/test_http_resilience.py
index c957575..09c9c77 100644
--- a/tests/test_http_resilience.py
+++ b/tests/test_http_resilience.py
@@ -384,3 +384,101 @@ class TestPostJsonWithRetry:
         hdrs = mock_client.post.call_args.kwargs["headers"]
         assert hdrs["Content-Type"] == "application/json"
 
+
+class TestRequestWithRetry:
+    @pytest.mark.asyncio
+    async def test_transient_503_retries_and_succeeds(self):
+        calls = 0
+
+        async def mock_request(method, url, **kwargs):
+            nonlocal calls
+            calls += 1
+            if calls < 3:
+                return _response(503)
+            return _response(200, content=b"success")
+
+        client = AsyncMock()
+        client.request = mock_request
+
+        resp = await hr.request_with_retry(
+            client,
+            "GET",
+            "https://example.com/api",
+            operation_name="test_transient",
+            base_delay_ms=1,
+            max_delay_ms=5,
+            max_total_ms=1000,
+        )
+        assert resp.status_code == 200
+        assert resp.content == b"success"
+        assert calls == 3
+
+    @pytest.mark.asyncio
+    async def test_sustained_outage_fails(self):
+        async def mock_request(method, url, **kwargs):
+            return _response(503)
+
+        client = AsyncMock()
+        client.request = mock_request
+
+        with pytest.raises(hr.ExternalAPIRetriesExhaustedError):
+            await hr.request_with_retry(
+                client,
+                "GET",
+                "https://example.com/api",
+                operation_name="test_sustained",
+                max_retries=2,
+                base_delay_ms=1,
+                max_delay_ms=5,
+                max_total_ms=1000,
+            )
+
+
+class TestRequestWithRetrySync:
+    def test_transient_503_retries_and_succeeds_sync(self):
+        calls = 0
+        from unittest.mock import MagicMock
+
+        def mock_request(method, url, **kwargs):
+            nonlocal calls
+            calls += 1
+            if calls < 3:
+                return _response(503)
+            return _response(200, content=b"success")
+
+        client = MagicMock()
+        client.request = mock_request
+
+        resp = hr.request_with_retry_sync(
+            client,
+            "GET",
+            "https://example.com/api",
+            operation_name="test_transient_sync",
+            base_delay_ms=1,
+            max_delay_ms=5,
+            max_total_ms=1000,
+        )
+        assert resp.status_code == 200
+        assert resp.content == b"success"
+        assert calls == 3
+
+    def test_sustained_outage_fails_sync(self):
+        from unittest.mock import MagicMock
+
+        def mock_request(method, url, **kwargs):
+            return _response(503)
+
+        client = MagicMock()
+        client.request = mock_request
+
+        with pytest.raises(hr.ExternalAPIRetriesExhaustedError):
+            hr.request_with_retry_sync(
+                client,
+                "GET",
+                "https://example.com/api",
+                operation_name="test_sustained_sync",
+                max_retries=2,
+                base_delay_ms=1,
+                max_delay_ms=5,
+                max_total_ms=1000,
+            )
diff --git a/tests/test_memory_orchestrator_observability.py b/tests/test_memory_orchestrator_observability.py
index 009de4a..7871cd4 100644
--- a/tests/test_memory_orchestrator_observability.py
+++ b/tests/test_memory_orchestrator_observability.py
@@ -77,7 +77,6 @@ class TestSagaMetricsWrapsRealWork:
             f"non-trivial work — the context manager is wrapping nothing"
         )
 
-
     @pytest.mark.asyncio
     async def test_duration_non_zero_with_async_work(self, monkeypatch) -> None:
         """Same as above but with async work inside the context."""
@@ -214,7 +213,9 @@ class TestSagaMetricsSuccessFailureRecording:
         with SagaMetrics("store_memory"):
             pass
 
-        assert "success" in results, f"Expected 'success' result even with observability disabled, got {results}"
+        assert "success" in results, (
+            f"Expected 'success' result even with observability disabled, got {results}"
+        )
 
     def test_store_memory_non_opt_in_failure_emits_always(self, monkeypatch) -> None:
         """SagaMetrics for operation='store_memory' must emit failure metrics even when NCE_OBSERVABILITY_ENABLED is False."""
@@ -236,8 +237,9 @@ class TestSagaMetricsSuccessFailureRecording:
             with SagaMetrics("store_memory"):
                 raise ValueError("failed saga")
 
-        assert "failure" in results, f"Expected 'failure' result even with observability disabled, got {results}"
-
+        assert "failure" in results, (
+            f"Expected 'failure' result even with observability disabled, got {results}"
+        )
 
 
 # ===========================================================================
@@ -779,6 +781,7 @@ class TestMemoryOrchestratorObservabilityContract:
 # 5. RQ Trace Context Propagation Tests
 # ===========================================================================
 
+
 def test_rq_trace_context_propagation(monkeypatch) -> None:
     """Verify that enqueue_traced injects OpenTelemetry trace context and
     traced_worker_job extracts and restores it correctly in the worker."""
diff --git a/tests/test_quotas.py b/tests/test_quotas.py
index 2921740..3a7911b 100644
--- a/tests/test_quotas.py
+++ b/tests/test_quotas.py
@@ -1243,3 +1243,146 @@ async def test_flush_greatest_prevents_regressing_higher_pg_used(
     await quotas.flush_quota_counters_to_postgres(redis, MagicMock())
 
     assert bound_used == [stale_redis_used]
+
+
+# ---------------------------------------------------------------------------
+# Quota and Embedding Degradation Observability (Batch 19)
+# ---------------------------------------------------------------------------
+
+
+@pytest.mark.asyncio
+async def test_quota_metrics_updated_on_consume(monkeypatch: pytest.MonkeyPatch) -> None:
+    from nce.observability import QUOTA_CONSUMED, QUOTA_REMAINING
+
+    monkeypatch.setattr("nce.quotas.cfg.NCE_QUOTAS_ENABLED", True)
+
+    ns_id = uuid.uuid4()
+    qrow_ns = uuid.uuid4()
+
+    conn = AsyncMock()
+    conn.fetch.return_value = [{"id": qrow_ns, "agent_id": None}]
+    conn.fetchrow.return_value = {"id": qrow_ns, "used_amount": 15, "limit_amount": 100}
+
+    tx = AsyncMock()
+    conn.transaction = MagicMock(return_value=tx)
+    tx.__aenter__.return_value = None
+    tx.__aexit__.return_value = None
+
+    pool = MagicMock()
+    acq = AsyncMock()
+    acq.__aenter__.return_value = conn
+    acq.__aexit__.return_value = None
+    pool.acquire = MagicMock(return_value=acq)
+
+    mock_consumed_set = MagicMock()
+    mock_remaining_set = MagicMock()
+
+    monkeypatch.setattr(
+        QUOTA_CONSUMED, "labels", MagicMock(return_value=MagicMock(set=mock_consumed_set))
+    )
+    monkeypatch.setattr(
+        QUOTA_REMAINING, "labels", MagicMock(return_value=MagicMock(set=mock_remaining_set))
+    )
+
+    await quotas.consume_resources(
+        pool,
+        namespace_id=ns_id,
+        agent_id="agent-x",
+        amounts={quotas.RESOURCE_LLM_TOKENS: 10},
+    )
+
+    QUOTA_CONSUMED.labels.assert_called_once_with(
+        namespace_id=str(ns_id),
+        resource_type=quotas.RESOURCE_LLM_TOKENS,
+        agent_id="global",
+    )
+    QUOTA_REMAINING.labels.assert_called_once_with(
+        namespace_id=str(ns_id),
+        resource_type=quotas.RESOURCE_LLM_TOKENS,
+        agent_id="global",
+    )
+    mock_consumed_set.assert_called_once_with(15)
+    mock_remaining_set.assert_called_once_with(85)
+
+
+@pytest.mark.asyncio
+async def test_quota_metrics_updated_on_consume_redis(monkeypatch: pytest.MonkeyPatch) -> None:
+    from nce.observability import QUOTA_CONSUMED, QUOTA_REMAINING
+
+    monkeypatch.setattr("nce.quotas.cfg.NCE_QUOTAS_ENABLED", True)
+
+    ns_id = uuid.uuid4()
+    qrow_ns = uuid.uuid4()
+
+    conn = AsyncMock()
+    conn.fetch.return_value = [
+        {"id": qrow_ns, "agent_id": None, "used_amount": 5, "limit_amount": 100}
+    ]
+
+    redis_client = AsyncMock()
+    redis_client.eval.return_value = 15
+
+    pool = MagicMock()
+    acq = AsyncMock()
+    acq.__aenter__.return_value = conn
+    acq.__aexit__.return_value = None
+    pool.acquire = MagicMock(return_value=acq)
+
+    mock_consumed_set = MagicMock()
+    mock_remaining_set = MagicMock()
+
+    monkeypatch.setattr(
+        QUOTA_CONSUMED, "labels", MagicMock(return_value=MagicMock(set=mock_consumed_set))
+    )
+    monkeypatch.setattr(
+        QUOTA_REMAINING, "labels", MagicMock(return_value=MagicMock(set=mock_remaining_set))
+    )
+
+    monkeypatch.setattr("nce.quotas.cfg.NCE_QUOTA_REDIS_COUNTERS", True)
+
+    await quotas.consume_resources(
+        pool,
+        namespace_id=ns_id,
+        agent_id="agent-x",
+        amounts={quotas.RESOURCE_LLM_TOKENS: 10},
+        redis_client=redis_client,
+    )
+
+    QUOTA_CONSUMED.labels.assert_called_once_with(
+        namespace_id=str(ns_id),
+        resource_type=quotas.RESOURCE_LLM_TOKENS,
+        agent_id="global",
+    )
+    QUOTA_REMAINING.labels.assert_called_once_with(
+        namespace_id=str(ns_id),
+        resource_type=quotas.RESOURCE_LLM_TOKENS,
+        agent_id="global",
+    )
+    mock_consumed_set.assert_called_once_with(15)
+    mock_remaining_set.assert_called_once_with(85)
+
+
+@pytest.mark.asyncio
+async def test_embedding_fallback_increments_counter_and_alerts(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    from nce.embeddings import CPUBackend
+    from nce.observability import EMBEDDING_FALLBACKS
+
+    mock_dispatch_alert = AsyncMock()
+    monkeypatch.setattr("nce.notifications.dispatcher.dispatch_alert", mock_dispatch_alert)
+
+    mock_inc = MagicMock()
+    monkeypatch.setattr(EMBEDDING_FALLBACKS, "inc", mock_inc)
+
+    backend = CPUBackend()
+    monkeypatch.setattr(backend, "_sync_embed_batch", MagicMock(return_value=([[0.0] * 768], True)))
+
+    res = await backend.embed(["test text"])
+
+    assert len(res) == 1
+    mock_inc.assert_called_once()
+    mock_dispatch_alert.assert_called_once()
+    title, msg = mock_dispatch_alert.call_args[0]
+    assert "Embedding Fallback Active" in title
+    assert "hash-stub fallback" in msg
diff --git a/tests/test_tool_registry.py b/tests/test_tool_registry.py
index d989eb5..6aecee6 100644
--- a/tests/test_tool_registry.py
+++ b/tests/test_tool_registry.py
@@ -25,10 +25,10 @@ from nce.tool_registry import (
 # Cardinality
 # ---------------------------------------------------------------------------
 
-_EXPECTED_TOTAL = 59
+_EXPECTED_TOTAL = 60
 
 
-def test_registry_has_59_entries():
+def test_registry_has_60_entries():
     assert len(TOOL_REGISTRY) == _EXPECTED_TOTAL, (
         f"Expected {_EXPECTED_TOTAL} tools, got {len(TOOL_REGISTRY)}. "
         f"Tools: {sorted(TOOL_REGISTRY)}"
@@ -117,6 +117,7 @@ _EXPECTED_CACHEABLE: frozenset[str] = frozenset(
         "semantic_search",
         "search_codebase",
         "graph_search",
+        "neuromorphic_search",
         "d365_query_case",
         "d365_case_stress_report",
         "d365_netbox_mappings",
@@ -132,7 +133,7 @@ def test_cacheable_tools_exact_match():
 
 
 def test_cacheable_tools_count():
-    assert len(CACHEABLE_TOOLS) == 6
+    assert len(CACHEABLE_TOOLS) == 7
 
 
 # ---------------------------------------------------------------------------
@@ -213,9 +214,7 @@ def test_migration_tools_subset_of_registry():
 def test_migration_mutations_are_in_mutation_tools():
     """All migration tools marked mutation=True must appear in MUTATION_TOOLS."""
     migration_mutations = {
-        name
-        for name, spec in TOOL_REGISTRY.items()
-        if spec.migration and spec.mutation
+        name for name, spec in TOOL_REGISTRY.items() if spec.migration and spec.mutation
     }
     assert migration_mutations <= MUTATION_TOOLS
 
@@ -246,47 +245,178 @@ def test_toolspec_is_frozen():
     "tool_name,expected_flags",
     [
         # memory
-        ("store_memory", {"mutation": True, "cacheable": False, "admin_only": False, "migration": False}),
-        ("semantic_search", {"mutation": False, "cacheable": True, "admin_only": False, "migration": False}),
-        ("unredact_memory", {"mutation": True, "cacheable": False, "admin_only": True, "migration": False}),
+        (
+            "store_memory",
+            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
+        ),
+        (
+            "semantic_search",
+            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
+        ),
+        (
+            "unredact_memory",
+            {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
+        ),
         # code
-        ("index_code_file", {"mutation": True, "cacheable": False, "admin_only": False, "migration": False}),
-        ("search_codebase", {"mutation": False, "cacheable": True, "admin_only": False, "migration": False}),
+        (
+            "index_code_file",
+            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
+        ),
+        (
+            "search_codebase",
+            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
+        ),
         # graph
-        ("graph_search", {"mutation": False, "cacheable": True, "admin_only": False, "migration": False}),
+        (
+            "graph_search",
+            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
+        ),
+        (
+            "neuromorphic_search",
+            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
+        ),
         # bridges
-        ("connect_bridge", {"mutation": True, "cacheable": False, "admin_only": False, "migration": False}),
-        ("list_bridges", {"mutation": False, "cacheable": False, "admin_only": False, "migration": False}),
+        (
+            "connect_bridge",
+            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
+        ),
+        (
+            "list_bridges",
+            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
+        ),
         # migration
-        ("start_migration", {"mutation": True, "cacheable": False, "admin_only": False, "migration": True}),
-        ("migration_status", {"mutation": False, "cacheable": False, "admin_only": False, "migration": True}),
-        ("commit_migration", {"mutation": True, "cacheable": False, "admin_only": False, "migration": True}),
+        (
+            "start_migration",
+            {"mutation": True, "cacheable": False, "admin_only": False, "migration": True},
+        ),
+        (
+            "migration_status",
+            {"mutation": False, "cacheable": False, "admin_only": False, "migration": True},
+        ),
+        (
+            "commit_migration",
+            {"mutation": True, "cacheable": False, "admin_only": False, "migration": True},
+        ),
         # replay
-        ("replay_observe", {"mutation": False, "cacheable": False, "admin_only": True, "migration": False}),
-        ("replay_reconstruct", {"mutation": True, "cacheable": False, "admin_only": True, "migration": False}),
-        ("get_event_provenance", {"mutation": False, "cacheable": False, "admin_only": False, "migration": False}),
+        (
+            "replay_observe",
+            {"mutation": False, "cacheable": False, "admin_only": True, "migration": False},
+        ),
+        (
+            "replay_reconstruct",
+            {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
+        ),
+        (
+            "get_event_provenance",
+            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
+        ),
         # a2a
-        ("a2a_create_grant", {"mutation": True, "cacheable": False, "admin_only": False, "migration": False}),
-        ("a2a_list_grants", {"mutation": False, "cacheable": False, "admin_only": False, "migration": False}),
+        (
+            "a2a_create_grant",
+            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
+        ),
+        (
+            "a2a_list_grants",
+            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
+        ),
         # admin
-        ("manage_namespace", {"mutation": True, "cacheable": False, "admin_only": False, "migration": False}),
-        ("get_health", {"mutation": False, "cacheable": False, "admin_only": False, "migration": False}),
+        (
+            "manage_namespace",
+            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
+        ),
+        (
+            "get_health",
+            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
+        ),
         # snapshots
-        ("create_snapshot", {"mutation": True, "cacheable": False, "admin_only": False, "migration": False}),
-        ("compare_states", {"mutation": False, "cacheable": False, "admin_only": False, "migration": False}),
+        (
+            "create_snapshot",
+            {"mutation": True, "cacheable": False, "admin_only": False, "migration": False},
+        ),
+        (
+            "compare_states",
+            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
+        ),
         # catalog
-        ("suggest_queries", {"mutation": False, "cacheable": False, "admin_only": False, "migration": False}),
+        (
+            "suggest_queries",
+            {"mutation": False, "cacheable": False, "admin_only": False, "migration": False},
+        ),
         # d365
-        ("d365_query_case", {"mutation": False, "cacheable": True, "admin_only": False, "migration": False}),
-        ("d365_sync_now", {"mutation": True, "cacheable": False, "admin_only": True, "migration": False}),
-        ("d365_case_stress_report", {"mutation": False, "cacheable": True, "admin_only": False, "migration": False}),
-        ("d365_list_sla_breaches", {"mutation": False, "cacheable": False, "admin_only": True, "migration": False}),
+        (
+            "d365_query_case",
+            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
+        ),
+        (
+            "d365_sync_now",
+            {"mutation": True, "cacheable": False, "admin_only": True, "migration": False},
+        ),
+        (
+            "d365_case_stress_report",
+            {"mutation": False, "cacheable": True, "admin_only": False, "migration": False},
+        ),
+        (
+            "d365_list_sla_breaches",
+            {"mutation": False, "cacheable": False, "admin_only": True, "migration": False},
+        ),
     ],
 )
 def test_tool_flags(tool_name: str, expected_flags: dict):
     spec = TOOL_REGISTRY[tool_name]
     for flag, expected in expected_flags.items():
         actual = getattr(spec, flag)
-        assert actual == expected, (
-            f"{tool_name}.{flag}: expected {expected!r}, got {actual!r}"
-        )
+        assert actual == expected, f"{tool_name}.{flag}: expected {expected!r}, got {actual!r}"
+
+
+@pytest.mark.asyncio
+async def test_handle_neuromorphic_search_success():
+    import json
+    from unittest.mock import AsyncMock, MagicMock
+
+    from nce.graph_mcp_handlers import handle_neuromorphic_search
+    from nce.graph_query import Subgraph
+
+    # Mock engine and traverser
+    mock_engine = MagicMock()
+    mock_traverser = AsyncMock()
+    mock_engine._graph_traverser = mock_traverser
+
+    # Mock subgraph result
+    dummy_subgraph = Subgraph(anchor="mock_anchor")
+    mock_traverser.neuromorphic_search.return_value = dummy_subgraph
+
+    # Valid arguments
+    args = {
+        "namespace_id": "00000000-0000-4000-8000-000000000001",
+        "query": "test query",
+        "telemetry_severity": 0.8,
+        "theta": 0.6,
+        "decay": 0.9,
+        "alpha": 1.1,
+        "ticks": 3,
+        "max_depth": 3,
+        "anchor_top_k": 2,
+    }
+
+    # Call handler
+    resp = await handle_neuromorphic_search(mock_engine, args)
+    resp_dict = json.loads(resp)
+
+    assert resp_dict["anchor"] == "mock_anchor"
+    mock_traverser.neuromorphic_search.assert_called_once_with(
+        query="test query",
+        namespace_id="00000000-0000-4000-8000-000000000001",
+        max_depth=3,
+        anchor_top_k=2,
+        user_id=None,
+        private=False,
+        as_of=None,
+        max_edges_per_node=512,
+        edge_limit=None,
+        edge_offset=0,
+        telemetry_severity=0.8,
+        theta=0.6,
+        decay=0.9,
+        alpha=1.1,
+        ticks=3,
+    )
diff --git a/tests/unit/test_netbox_contacts.py b/tests/unit/test_netbox_contacts.py
index 06dc37e..f3dcc5c 100644
--- a/tests/unit/test_netbox_contacts.py
+++ b/tests/unit/test_netbox_contacts.py
@@ -35,10 +35,10 @@ class MockTransaction:
 
 class MockConnection:
     def __init__(self) -> None:
-        self.fetch_results = []
-        self.fetchval_results = []
-        self.execute_calls = []
-        self.fetch_calls = []
+        self.fetch_results: list[dict[str, Any]] = []
+        self.fetchval_results: list[Any] = []
+        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []
+        self.fetch_calls: list[tuple[str, tuple[Any, ...]]] = []
 
     async def fetch(self, query: str, *args: Any) -> list[dict]:
         self.fetch_calls.append((query, args))
@@ -57,12 +57,19 @@ class MockConnection:
 
 @pytest.mark.anyio
 class TestNetBoxClient:
-
     async def test_fetch_contacts(self, monkeypatch):
         client = NetBoxClient("http://netbox.local", "token123")
 
-        mock_results = {"results": [{"name": "John Doe", "email": "jdoe@example.com", "username": "jdoe"}]}
-        mock_get = AsyncMock(return_value=Response(200, json=mock_results, request=Request("GET", "http://netbox.local/api/tenancy/contacts/")))
+        mock_results = {
+            "results": [{"name": "John Doe", "email": "jdoe@example.com", "username": "jdoe"}]
+        }
+        mock_get = AsyncMock(
+            return_value=Response(
+                200,
+                json=mock_results,
+                request=Request("GET", "http://netbox.local/api/tenancy/contacts/"),
+            )
+        )
         monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
 
         contacts = await client.fetch_contacts()
@@ -74,10 +81,29 @@ class TestNetBoxClient:
             timeout=10.0,
         )
 
+    async def test_fetch_contacts_timeout_and_config(self, monkeypatch):
+        import httpx
+
+        client = NetBoxClient("http://netbox.local", "token123")
+
+        timeout_value = None
+
+        async def mock_send(self, request, *args, **kwargs):
+            nonlocal timeout_value
+            timeout_value = self.timeout
+            raise httpx.ReadTimeout("Request timed out", request=request)
+
+        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)
+
+        with pytest.raises(httpx.TimeoutException):
+            await client.fetch_contacts()
+
+        assert timeout_value is not None
+        assert timeout_value.read == 30.0
+
 
 @pytest.mark.anyio
 class TestNetBoxContactSync:
-
     async def test_ensure_on_call_schema(self):
         conn = MockConnection()
         conn.fetchval_results = [False]  # Policy does not exist
@@ -86,7 +112,10 @@ class TestNetBoxContactSync:
         await sync.ensure_on_call_schema(conn)
 
         assert any("CREATE TABLE IF NOT EXISTS on_call_routing" in c[0] for c in conn.execute_calls)
-        assert any("ALTER TABLE on_call_routing ENABLE ROW LEVEL SECURITY" in c[0] for c in conn.execute_calls)
+        assert any(
+            "ALTER TABLE on_call_routing ENABLE ROW LEVEL SECURITY" in c[0]
+            for c in conn.execute_calls
+        )
         assert any("CREATE POLICY on_call_tenant_isolation" in c[0] for c in conn.execute_calls)
 
     async def test_evaluate_contact_stress_report(self):
@@ -94,8 +123,7 @@ class TestNetBoxContactSync:
         now = datetime.now(timezone.utc)
         # 5 consecutive shifts with frustration (index 5) = 8.0 (burnout)
         conn.fetch_results = [
-            {"empathic_tensor": [1.0, 2.0, 3.0, 4.0, 5.0, 8.0], "created_at": now}
-            for _ in range(5)
+            {"empathic_tensor": [1.0, 2.0, 3.0, 4.0, 5.0, 8.0], "created_at": now} for _ in range(5)
         ]
 
         sync = NetBoxContactSync(None, None)
@@ -112,10 +140,12 @@ class TestNetBoxContactSync:
     async def test_sync_contacts_and_update_oncall_burnout_trigger(self, monkeypatch):
         # 1. Mock NetBox API to return two operators: Jane and Bob
         client_mock = MagicMock()
-        client_mock.fetch_contacts = AsyncMock(return_value=[
-            {"name": "Jane", "email": "jane@example.com", "username": "jane"},
-            {"name": "Bob", "email": "bob@example.com", "username": "bob"},
-        ])
+        client_mock.fetch_contacts = AsyncMock(
+            return_value=[
+                {"name": "Jane", "email": "jane@example.com", "username": "jane"},
+                {"name": "Bob", "email": "bob@example.com", "username": "bob"},
+            ]
+        )
 
         conn = MockConnection()
         conn.fetchval_results = [True]  # Policy already exists
```
