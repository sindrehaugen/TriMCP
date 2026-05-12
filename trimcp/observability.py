"""
TriMCP Observability Layer
==========================
Centralised Prometheus metrics and OpenTelemetry tracing for the TriMCP stack.
Handles initialization and provides decorators/context managers for instrumentation.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

log = logging.getLogger("trimcp.observability")

try:
    from opentelemetry import context as otel_context
    from opentelemetry import propagate, trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

    # Stub classes for metrics if prometheus_client is missing
    class _StubMetric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

    Counter = Histogram = Gauge = _StubMetric

    def start_http_server(*args, **kwargs):
        pass


from trimcp.config import cfg  # noqa: E402 — after optional-dep stubs

# --- Types ---
F = TypeVar("F", bound=Callable[..., Any])

# --- Prometheus Metrics ---

# Tool level metrics (server.py)
TOOL_CALLS = Counter(
    "trimcp_tool_calls_total",
    "Total count of MCP tool calls",
    ["tool_name", "status"],
)
TOOL_LATENCY = Histogram(
    "trimcp_tool_latency_seconds",
    "Latency of MCP tool calls in seconds",
    ["tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf")),
)

# Saga level metrics (orchestrator.py)
SAGA_DURATION = Histogram(
    "trimcp_saga_duration_seconds",
    "Duration of distributed saga transactions",
    ["operation", "result"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, float("inf")),
)
SAGA_FAILURES = Counter(
    "trimcp_saga_failures_total",
    "Total count of saga step failures",
    ["stage"],  # stage = pg, mongo, redis, etc.
)

# Component specific
EMBEDDING_COUNT = Counter(
    "trimcp_embedding_count",
    "Total count of individual chunks embedded",
    ["model_id"],
)
REEMBEDDING_PROGRESS = Gauge(
    "trimcp_reembedding_progress",
    "Progress of the background re-embedding worker",
    ["worker_id"],
)

# VRAM metrics for re-embedder CUDA memory pressure monitoring (Item 49)
REEMBEDDER_VRAM_ALLOCATED = Gauge(
    "trimcp_reembedder_vram_allocated_bytes",
    "Current VRAM allocated to PyTorch tensors by the re-embedder (torch.cuda.memory_allocated)",
    ["worker_id"],
)
REEMBEDDER_VRAM_RESERVED = Gauge(
    "trimcp_reembedder_vram_reserved_bytes",
    "Current VRAM reserved by the CUDA caching allocator for the re-embedder (torch.cuda.memory_reserved)",
    ["worker_id"],
)
REEMBEDDER_VRAM_PEAK = Gauge(
    "trimcp_reembedder_vram_peak_bytes",
    "Peak VRAM allocated since last measurement reset (torch.cuda.max_memory_allocated)",
    ["worker_id"],
)

# Connection pool / RLS overhead
SCOPED_SESSION_LATENCY = Histogram(
    "trimcp_scoped_session_latency_seconds",
    "Latency of scoped_session acquisition + SET LOCAL RLS",
    ["namespace_id"],
    buckets=(0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, float("inf")),
)

# Dead Letter Queue / Poison Pill metrics (Phase 3 tasks.py)
TASK_DLQ_TOTAL = Counter(
    "trimcp_task_dlq_total",
    "Total count of background tasks routed to the Dead Letter Queue after exhausting retries",
    ["task_name"],
)
TASK_DLQ_BACKLOG = Gauge(
    "trimcp_task_dlq_backlog",
    "Current number of pending (un-replayed, un-purged) entries in the Dead Letter Queue",
    ["task_name"],
)

# Partition maintenance runway (Item C)
EVENT_LOG_PARTITION_MONTHS_AHEAD = Gauge(
    "trimcp_event_log_partition_months_ahead",
    "Number of future monthly partitions ahead of current month for event_log",
)

# Merkle chain verification gauge (B2) — 1=valid, 0=corrupted
MERKLE_CHAIN_VALID = Gauge(
    "trimcp_merkle_chain_valid",
    "Merkle chain validity: 1=valid, 0=corrupted",
    ["namespace_id"],
)

# Signing key cache (Item 31)
SIGNING_KEY_CACHE_HIT_TOTAL = Counter(
    "trimcp_signing_key_cache_hit_total",
    "Total count of signing key cache hits",
)
SIGNING_KEY_CACHE_MISS_TOTAL = Counter(
    "trimcp_signing_key_cache_miss_total",
    "Total count of signing key cache misses",
)

# Extraction security (Items E, K)
EXTRACTION_MIME_MISMATCH_TOTAL = Counter(
    "trimcp_extraction_mime_mismatch_total",
    "Total count of attachments rejected due to extension/magic-byte MIME mismatch",
)
EXTRACTION_REJECTED_TOO_LARGE_TOTAL = Counter(
    "trimcp_extraction_rejected_too_large_total",
    "Total count of attachments rejected due to size limit",
)

# Circuit breaker state (Item 44)
CIRCUIT_BREAKER_STATE = Gauge(
    "trimcp_circuit_breaker_state",
    "Current circuit breaker state: 0=closed, 1=half_open, 2=open",
    ["provider"],
)
CIRCUIT_BREAKER_FAILURES = Gauge(
    "trimcp_circuit_breaker_failures",
    "Current consecutive failure count inside the circuit breaker",
    ["provider"],
)
MINIO_ORPHAN_CLEANUP_FAILURES_TOTAL = Counter(
    "trimcp_minio_orphan_cleanup_failures_total",
    "Number of MinIO object deletions that failed during orphan cleanup",
)

# --- Initialization ---

_tracer_initialized = False


def init_observability() -> None:
    """Initializes OTel tracer and starts Prometheus exporter."""
    global _tracer_initialized
    if not cfg.TRIMCP_OBSERVABILITY_ENABLED:
        return
    if not HAS_OTEL:
        return

    if not _tracer_initialized:
        # 1. Prometheus
        try:
            start_http_server(cfg.TRIMCP_PROMETHEUS_PORT)
        except Exception:
            # Port might already be in use if running in a multi-process environment
            pass

        # 2. OpenTelemetry
        resource = Resource(attributes={"service.name": cfg.TRIMCP_OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{cfg.TRIMCP_OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces"
            )
        )
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        _tracer_initialized = True


def get_tracer():
    if not HAS_OTEL:
        # Return a mock tracer that does nothing
        class _MockSpan:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def set_attribute(self, *args):
                pass

            def record_exception(self, *args):
                pass

            def set_status(self, *args):
                pass

        class _MockTracer:
            def start_as_current_span(self, *args, **kwargs):
                return _MockSpan()

        return _MockTracer()
    return trace.get_tracer("trimcp")


# --- Instrumentation Helpers ---


def instrument_tool(tool_name: str):
    """Decorator to instrument an MCP tool with metrics and a span."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not cfg.TRIMCP_OBSERVABILITY_ENABLED:
                return await func(*args, **kwargs)

            tracer = get_tracer()
            start_time = time.perf_counter()
            status = "success"

            with tracer.start_as_current_span(f"mcp_tool:{tool_name}") as span:
                span.set_attribute("trimcp.tool", tool_name)
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    status = "error"
                    span.record_exception(e)
                    if HAS_OTEL:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                    raise
                finally:
                    duration = time.perf_counter() - start_time
                    TOOL_CALLS.labels(tool_name=tool_name, status=status).inc()
                    TOOL_LATENCY.labels(tool_name=tool_name).observe(duration)

        return wrapper  # type: ignore

    return decorator


@asynccontextmanager
async def instrument_tool_call(tool_name: str):
    """Context manager to instrument an MCP tool call."""
    if not cfg.TRIMCP_OBSERVABILITY_ENABLED:
        yield None
        return

    tracer = get_tracer()
    start_time = time.perf_counter()
    status = "success"

    with tracer.start_as_current_span(f"mcp_tool:{tool_name}") as span:
        span.set_attribute("trimcp.tool", tool_name)
        try:
            yield span
        except Exception as e:
            status = "error"
            span.record_exception(e)
            if HAS_OTEL:
                span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
        finally:
            duration = time.perf_counter() - start_time
            TOOL_CALLS.labels(tool_name=tool_name, status=status).inc()
            TOOL_LATENCY.labels(tool_name=tool_name).observe(duration)


class SagaMetrics:
    """Context manager for saga transactions.

    Optional *on_failure* callback
    --------------------------------
    Pass a callable ``on_failure(exc: BaseException, **kwargs)`` to receive
    structured information when the saga fails.  The callback MUST use
    ``.get()`` (or keyword defaults) for every key it reads from ``kwargs``
    because callers are not required to supply any particular key.

    Example::

        def _on_fail(exc, **kw):
            step = kw.get("step_name", "unknown")   # safe — never KeyError
            SagaMetrics.record_failure(stage=step)

        with SagaMetrics("store_memory", on_failure=_on_fail):
            ...
    """

    def __init__(
        self,
        operation: str,
        on_failure: Callable[..., None] | None = None,
    ) -> None:
        self.operation = operation
        self.start_time = 0.0
        self._on_failure = on_failure

    def __enter__(self) -> SagaMetrics:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not cfg.TRIMCP_OBSERVABILITY_ENABLED:
            return

        result = "success" if exc_type is None else "failure"
        duration = time.perf_counter() - self.start_time
        SAGA_DURATION.labels(operation=self.operation, result=result).observe(duration)

        if exc_type is not None and self._on_failure is not None:
            try:
                # Fire the callback — it receives the live exception.
                # kwargs are intentionally empty here; callers that need
                # richer context should bind them via functools.partial or
                # a closure so the callback signature stays (exc, **kw).
                self._on_failure(exc_val)
            except Exception as cb_exc:  # pragma: no cover
                log.warning("[SagaMetrics] on_failure callback raised: %s", cb_exc)

    @staticmethod
    def record_failure(stage: str) -> None:
        """Increment SAGA_FAILURES counter for the given pipeline stage."""
        if cfg.TRIMCP_OBSERVABILITY_ENABLED:
            SAGA_FAILURES.labels(stage=stage).inc()

    @staticmethod
    def on_saga_failure(exc: BaseException, **kwargs: Any) -> None:
        """Safe Saga failure handler for use as an *on_failure* callback.

        Reads ``kwargs`` with ``.get()`` throughout so omitting any key
        (including ``step_name``) never raises ``KeyError``.  The metric
        is always emitted — it defaults to ``"unknown"`` when ``step_name``
        is absent.

        Usage::

            import functools
            cb = functools.partial(
                SagaMetrics.on_saga_failure, step_name="pg_insert"
            )
            with SagaMetrics("store_memory", on_failure=cb):
                ...
        """
        step_name: str = kwargs.get("step_name", "unknown")  # never raises
        stage: str = kwargs.get("stage", step_name)
        if cfg.TRIMCP_OBSERVABILITY_ENABLED:
            SAGA_FAILURES.labels(stage=stage).inc()


# ---------------------------------------------------------------------------
# Distributed tracing — W3C Trace Context propagation
# ---------------------------------------------------------------------------

# Re-export for convenience so callers don't need to import opentelemetry directly
HasOTel = HAS_OTEL


def inject_trace_headers(
    headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Inject the current OpenTelemetry trace context into *headers*.

    Adds the W3C ``traceparent`` (and optionally ``tracestate``) header to an
    outbound HTTP request so the downstream service can continue the same trace.

    Usage::

        headers = inject_trace_headers({"content-type": "application/json"})
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=headers, json=body)

    Returns a new dict if *headers* is ``None``, or mutates and returns the
    same dict.  Safe to call when OTel is disabled (returns headers unchanged).
    """
    headers = {} if headers is None else headers
    if HAS_OTEL and cfg.TRIMCP_OBSERVABILITY_ENABLED:
        propagate.inject(headers)
    return headers


def extract_trace_from_headers(
    headers: dict[str, str],
) -> None:
    """Extract W3C Trace Context from incoming request *headers* and activate it.

    Call this at the top of an HTTP request handler (or middleware) to bind the
    current span to a remotely-initiated trace.  If no ``traceparent`` header is
    present this is a no-op.

    After calling this, any new spans created with ``get_tracer()`` will be
    children of the remote span.  Use ``@instrument_tool`` / ``instrument_tool_call``
    / ``get_tracer().start_as_current_span(...)`` to create child spans.

    Usage::

        extract_trace_from_headers(dict(request.headers))
        with get_tracer().start_as_current_span("my_handler") as span:
            ...
    """
    if HAS_OTEL and cfg.TRIMCP_OBSERVABILITY_ENABLED and headers:
        ctx = propagate.extract(headers)
        trace.get_current_span()  # ensure tracer provider is set
        # Activate the extracted context so child spans are correctly parented
        token = otel_context.attach(ctx)
        # Note: we deliberately do NOT keep the token — the context is active
        # for the duration of the current async task.  In an ASGI middleware
        # this matches the request lifecycle naturally.
        _ = token


# ---------------------------------------------------------------------------
# Starlette / ASGI middleware — extract trace context from incoming requests
# ---------------------------------------------------------------------------

try:
    from starlette.types import ASGIApp, Receive, Scope, Send

    HAS_STARLETTE = True
except ImportError:
    HAS_STARLETTE = False


class OpenTelemetryTraceMiddleware:
    """Starlette ASGI middleware that extracts W3C ``traceparent`` from incoming
    HTTP requests and activates the remote trace context.

    Place this **before** auth middleware so the trace is established before any
    handler runs::

        app = Starlette(
            middleware=[
                Middleware(OpenTelemetryTraceMiddleware),
                Middleware(BasicAuthMiddleware, ...),
                Middleware(HMACAuthMiddleware, ...),
            ],
            ...
        )

    When no ``traceparent`` header is present on the request, this middleware is
    a no-op — the current trace remains whatever OTel auto-instrumentation or
    the SDK has already established.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and HAS_OTEL and cfg.TRIMCP_OBSERVABILITY_ENABLED:
            # Build a plain dict from the ASGI scope headers (list of (bytes, bytes))
            headers = {
                k.decode("ascii", errors="replace").lower(): v.decode(
                    "ascii", errors="replace"
                )
                for k, v in scope.get("headers", [])
            }
            if "traceparent" in headers:
                ctx = propagate.extract(headers)
                # Set the extracted context as the active context for this request
                token = otel_context.attach(ctx)
                try:
                    await self.app(scope, receive, send)
                finally:
                    otel_context.detach(token)
                return

        await self.app(scope, receive, send)
