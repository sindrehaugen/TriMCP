"""
trimcp.providers.base
~~~~~~~~~~~~~~~~~~~~~
Abstract base for all LLM provider implementations.

All LLM calls in TriMCP MUST go through this interface.  No direct SDK or
HTTP calls to model APIs are permitted outside of this package.

Design decisions
----------------
* ``complete()`` is generic: callers pass the Pydantic V2 *model class* they
  expect back.  The provider validates the raw JSON from the model and returns
  a typed, fully-validated instance.  This eliminates ``dict`` passing and
  moves validation failures close to the LLM boundary rather than deep in
  business logic.

* ``model_identifier()`` returns ``"provider/model"`` so callers can write
  this string into ``event_log.llm_provider`` without coupling to provider
  internals.

* ``LLMProviderError`` wraps every provider-specific failure so callers handle
  one exception type regardless of which backend is active.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import sys
from abc import ABC, abstractmethod

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from strenum import StrEnum  # type: ignore[import-untyped]
from typing import TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

try:
    from trimcp.observability import CIRCUIT_BREAKER_FAILURES, CIRCUIT_BREAKER_STATE
except Exception:
    CIRCUIT_BREAKER_STATE = None
    CIRCUIT_BREAKER_FAILURES = None

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSRF guard — validate base_url before issuing any HTTP calls
# ---------------------------------------------------------------------------


def validate_base_url(
    base_url: str,
    *,
    allow_http: bool = False,
    allow_loopback: bool = False,
) -> None:
    """SSRF guard: validate *base_url* does not point to private/internal networks.

    Checks
    ------
    * URL parses correctly (scheme + netloc present).
    * Scheme is ``https`` (unless ``allow_http=True``).
    * Hostname resolves to at least one IP address.
    * Resolved IPs are **not** in private ranges (``10.0.0.0/8``,
      ``172.16.0.0/12``, ``192.168.0.0/16``, ``127.0.0.0/8``,
      ``::1/128``, ``fd00::/8``) unless ``allow_loopback=True``.

    Parameters
    ----------
    base_url:
        The URL to validate.
    allow_http:
        If ``True``, permit ``http://`` URLs (for local caches / internal
        cognitive containers).  Default ``False``.
    allow_loopback:
        If ``True``, permit loopback (``127.0.0.1``, ``::1``) and private
        IP addresses.  Use **only** for providers that must talk to local
        infrastructure (e.g. ``LocalCognitiveProvider``).

    Raises
    ------
    LLMProviderError
        If any check fails.
    """
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise LLMProviderError(f"SSRF guard: invalid base_url {base_url!r}")

    if not allow_http and parsed.scheme != "https":
        raise LLMProviderError(
            f"SSRF guard: base_url must use HTTPS, got {parsed.scheme!r}"
        )

    hostname = parsed.hostname
    if not hostname:
        raise LLMProviderError(
            f"SSRF guard: could not extract hostname from {base_url!r}"
        )

    # Resolve hostname to IP addresses (synchronous, fast for typical hostnames).
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise LLMProviderError(
            f"SSRF guard: could not resolve hostname {hostname!r} from {base_url!r}"
        )

    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue  # not a recognised IP family, skip

        if allow_loopback:
            continue  # caller takes responsibility for local access

        if ip.is_private:
            raise LLMProviderError(
                f"SSRF guard: {base_url!r} resolves to private IP {ip_str} (hostname={hostname!r})"
            )
        if ip.is_loopback:
            raise LLMProviderError(
                f"SSRF guard: {base_url!r} resolves to loopback {ip_str} (hostname={hostname!r})"
            )


async def validate_base_url_async(
    base_url: str,
    *,
    allow_http: bool = False,
    allow_loopback: bool = False,
) -> None:
    """Async variant of :func:`validate_base_url`.

    Offloads the synchronous ``socket.getaddrinfo`` DNS resolution to a
    thread-pool executor via ``asyncio.get_running_loop().run_in_executor``
    so the event loop is never blocked.  All other checks (URL parsing,
    IP range validation) are CPU-bound and fast — they run inline.

    Use this variant in async startup paths (e.g. ``ASGI lifespan``).
    The synchronous :func:`validate_base_url` remains available for
    ``__init__``-time validation where ``await`` is not possible.

    .. note::

        In single-instance deployments where ``validate_base_url`` is
        called from ``LLMProvider.__init__`` at server startup, the
        blocking DNS resolution is acceptable — it completes in
        sub-millisecond for cached lookups and only runs once.
    """
    import asyncio

    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise LLMProviderError(f"SSRF guard: invalid base_url {base_url!r}")

    if not allow_http and parsed.scheme != "https":
        raise LLMProviderError(
            f"SSRF guard: base_url must use HTTPS, got {parsed.scheme!r}"
        )

    hostname = parsed.hostname
    if not hostname:
        raise LLMProviderError(
            f"SSRF guard: could not extract hostname from {base_url!r}"
        )

    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.run_in_executor(None, socket.getaddrinfo, hostname, None)
    except socket.gaierror:
        raise LLMProviderError(
            f"SSRF guard: could not resolve hostname {hostname!r} from {base_url!r}"
        )

    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if allow_loopback:
            continue

        if ip.is_private:
            raise LLMProviderError(
                f"SSRF guard: {base_url!r} resolves to private IP {ip_str} (hostname={hostname!r})"
            )
        if ip.is_loopback:
            raise LLMProviderError(
                f"SSRF guard: {base_url!r} resolves to loopback {ip_str} (hostname={hostname!r})"
            )


# ---------------------------------------------------------------------------
# API key redaction helper
# ---------------------------------------------------------------------------


def _redact_api_key(key: str) -> str:
    """Return a safe representation of an API key for logs and repr.

    Preserves the first 3 and last 4 characters; replaces the middle
    with an ellipsis.  Short keys (≤7 chars) are fully replaced.
    """
    if not key:
        return "<empty>"
    if len(key) <= 7:
        return "<redacted>"
    return f"{key[:3]}...{key[-4:]}"


# ---------------------------------------------------------------------------
# TypeVar — used to make complete() generic
# ---------------------------------------------------------------------------

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


# ---------------------------------------------------------------------------
# Message model
# ---------------------------------------------------------------------------


class MessageRole(StrEnum):
    system = "system"
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    """A single turn in a multi-turn conversation sent to an LLM."""

    model_config = ConfigDict(frozen=True)

    role: MessageRole
    content: str

    @field_validator("content")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message content must not be blank.")
        return v

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=MessageRole.system, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=MessageRole.user, content=content)

    @classmethod
    def assistant(cls, content: str) -> Message:
        return cls(role=MessageRole.assistant, content=content)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMProviderError(Exception):
    """Base exception for all LLM provider failures.

    Attributes
    ----------
    provider:
        ``"provider/model"`` string, e.g. ``"anthropic/claude-opus-4-6"``.
    status_code:
        HTTP status code if the failure was an upstream HTTP error; ``None``
        otherwise.
    upstream_message:
        Raw error message from the upstream API, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "unknown",
        status_code: int | None = None,
        upstream_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.upstream_message = upstream_message


class LLMValidationError(LLMProviderError):
    """Raised when the model returns valid JSON that fails Pydantic validation."""


class LLMTimeoutError(LLMProviderError):
    """Raised when the upstream API call times out."""


class LLMAuthenticationError(LLMProviderError):
    """Raised on 401/403 — invalid or expired API credentials."""


class LLMRateLimitError(LLMProviderError):
    """Raised on 429 — rate limit exceeded.  Carries ``retry_after`` seconds."""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "unknown",
        retry_after: int | None = None,
        **kwargs,
    ) -> None:
        super().__init__(message, provider=provider, status_code=429, **kwargs)
        self.retry_after = retry_after


class LLMUpstreamError(LLMProviderError):
    """Raised on 5xx — temporary upstream failure (safe to retry)."""


class LLMBadRequestError(LLMProviderError):
    """Raised on 400 — malformed request (do NOT retry)."""


# ---------------------------------------------------------------------------
# Retry policy  —  exponential backoff with full-jitter
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402 — placed here to avoid circular import via LLMProvider
import random  # noqa: E402
import time  # noqa: E402


class RetryPolicy:
    """Exponential backoff for transient LLM failures.

    Retries on: timeouts, 429 (rate-limit), 5xx (upstream errors).
    Never retries on: 400 (bad request), 401/403 (auth errors), validation errors.

    The ``max_total_ms`` parameter enforces an upper bound so the MCP
    server never exceeds its protocol timeout window (typically 10-20 s).

    **Jitter** uses the *full-jitter* strategy (``random.uniform(0, delay)``)
    to prevent thundering-herd wakeups when multiple workers retry
    simultaneously after a 429 or 5xx burst.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_ms: int = 1_000,
        max_delay_ms: int = 30_000,
        max_total_ms: int = 60_000,
        backoff_factor: float = 2.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.max_total_ms = max_total_ms
        self.backoff_factor = backoff_factor

    def is_retryable(self, exc: Exception) -> bool:
        """Return True if this exception type warrants a retry."""
        if isinstance(exc, (LLMTimeoutError, LLMRateLimitError, LLMUpstreamError)):
            return True
        # Connection errors from httpx are transient
        if isinstance(exc, asyncio.TimeoutError):
            return True
        return False

    def delay_for_attempt(self, attempt: int) -> int:
        """Compute exponential backoff delay *with full jitter* in milliseconds.

        Returns ``random.uniform(0, capped_exponential)`` so concurrent
        callers spread out rather than hammering the upstream in lockstep.
        """
        cap = min(
            int(self.base_delay_ms * (self.backoff_factor ** (attempt - 1))),
            self.max_delay_ms,
        )
        return random.randint(1, max(1, cap))


# Default retry policy — 3 retries, 60 s max total
DEFAULT_RETRY_POLICY = RetryPolicy()


# ---------------------------------------------------------------------------
# Circuit breaker  —  protects upstream LLM endpoints from cascading load
# ---------------------------------------------------------------------------


class CircuitBreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """State-machine circuit breaker for LLM provider calls.

    Protects upstream API endpoints from cascading load when they are
    already degraded (429 / 5xx bursts).  After ``failure_threshold``
    consecutive failures the circuit *opens*; subsequent callers fail fast
    without touching the network.  After ``recovery_timeout`` seconds the
    circuit transitions to *half-open* and permits a limited number of
    probe requests.  If a probe succeeds the circuit *closes*; if it fails
    the circuit snaps back to *open* for another recovery cycle.

    Thread-safety via ``asyncio.Lock`` — safe to share across multiple
    concurrent ``execute_with_retry`` calls.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 1,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        self._state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._half_open_used: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    async def check(self) -> bool:
        """Return ``True`` if a request is allowed through the circuit."""
        async with self._lock:
            if self._state is CircuitBreakerState.CLOSED:
                return True

            if self._state is CircuitBreakerState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._half_open_used = 1  # this probe counts toward the limit
                    return True
                return False

            # HALF_OPEN
            if self._half_open_used < self.half_open_max_requests:
                self._half_open_used += 1
                return True
            return False

    def _emit_metrics(self, provider_label: str = "default") -> None:
        if CIRCUIT_BREAKER_STATE is None:
            return
        state_map = {
            CircuitBreakerState.CLOSED: 0,
            CircuitBreakerState.HALF_OPEN: 1,
            CircuitBreakerState.OPEN: 2,
        }
        CIRCUIT_BREAKER_STATE.labels(provider=provider_label).set(
            state_map.get(self._state, 0)
        )
        CIRCUIT_BREAKER_FAILURES.labels(provider=provider_label).set(self._failure_count)

    async def record_success(self) -> None:
        """Record a successful call — resets failure count (and closes if half-open)."""
        async with self._lock:
            self._failure_count = 0
            if self._state is CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.CLOSED
                log.debug("Circuit breaker CLOSED — upstream recovered.")
            self._emit_metrics()

    async def record_failure(self) -> None:
        """Record a failed call — may open the circuit at threshold."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                old_state = self._state
                self._state = CircuitBreakerState.OPEN
                if old_state is not CircuitBreakerState.OPEN:
                    log.warning(
                        "Circuit breaker OPEN after %d consecutive failures (recovery in %.1fs).",
                        self._failure_count,
                        self.recovery_timeout,
                    )
            self._emit_metrics()

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self._state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )


# Default circuit breaker — 5 failures, 30 s recovery
DEFAULT_CIRCUIT_BREAKER = CircuitBreaker()


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract interface every LLM provider must implement.

    Usage
    -----
    ::

        provider = get_provider(namespace_metadata)
        result: ConsolidatedAbstraction = await provider.complete(
            messages=[
                Message.system("You are a memory consolidation engine."),
                Message.user(prompt),
            ],
            response_model=ConsolidatedAbstraction,
        )

    Implementors
    ------------
    * ``LocalCognitiveProvider``  — bundled model on port 11435 [D2/D7]
    * ``OpenAICompatProvider``    — OpenAI, Azure OpenAI, DeepSeek, Moonshot
    * ``AnthropicProvider``       — Anthropic Claude (tool_use structured output)
    * ``GoogleGeminiProvider``    — Gemini (schema-in-prompt + JSON parsing)

    Retry & circuit breaker
    -----------------------
    Every provider automatically gets an ``execute_with_retry()`` wrapper
    that applies exponential-backoff (with full jitter) and a state-machine
    circuit breaker.  Subclasses should call ``await self.execute_with_retry(...)``
    in their ``complete()`` implementation rather than issuing the HTTP call
    directly.  Override ``_retry_policy`` or ``_circuit_breaker`` on the
    instance to tune per-endpoint behaviour.
    """

    # ------------------------------------------------------------------
    # Lazy-initialised retry policy & circuit breaker
    # (no super().__init__() required in subclasses)
    # ------------------------------------------------------------------

    @property
    def _retry_policy(self) -> RetryPolicy:
        try:
            return self.__retry_policy  # type: ignore[has-type]
        except AttributeError:
            self.__retry_policy = DEFAULT_RETRY_POLICY  # type: ignore[has-type]
            return self.__retry_policy  # type: ignore[has-type]

    @_retry_policy.setter
    def _retry_policy(self, value: RetryPolicy) -> None:
        self.__retry_policy = value

    @property
    def _circuit_breaker(self) -> CircuitBreaker:
        try:
            return self.__circuit_breaker  # type: ignore[has-type]
        except AttributeError:
            self.__circuit_breaker = DEFAULT_CIRCUIT_BREAKER  # type: ignore[has-type]
            return self.__circuit_breaker  # type: ignore[has-type]

    @_circuit_breaker.setter
    def _circuit_breaker(self, value: CircuitBreaker) -> None:
        self.__circuit_breaker = value

    # ------------------------------------------------------------------
    # Retry loop with circuit-breaker integration
    # ------------------------------------------------------------------

    async def execute_with_retry(
        self,
        operation,
        *,
        retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> object:
        """Execute an async *operation* under retry + circuit-breaker guard.

        Parameters
        ----------
        operation:
            A zero-argument async callable that performs the actual LLM
            request (e.g. ``lambda: self._post(body)``).
        retry_policy:
            Override the instance-level retry policy for this call.
        circuit_breaker:
            Override the instance-level circuit breaker for this call.

        Returns
        -------
        The return value of *operation*.

        Raises
        ------
        LLMProviderError
            If the circuit breaker is open and refuses the request.
        LLMTimeoutError, LLMRateLimitError, LLMUpstreamError
            Propagated from *operation* after all retries exhausted.
        """
        rp = retry_policy or self._retry_policy
        cb = circuit_breaker or self._circuit_breaker

        for attempt in range(1, rp.max_retries + 2):  # +1 for the initial call
            # --- circuit-breaker guard ---
            allowed = await cb.check()
            if not allowed:
                msg = (
                    f"Circuit breaker OPEN for {self.model_identifier()} — "
                    f"failing fast. Retry after recovery_timeout={cb.recovery_timeout:.0f}s."
                )
                log.warning("%s", msg)
                raise LLMProviderError(
                    msg,
                    provider=self.model_identifier(),
                    status_code=503,  # service unavailable
                )

            # --- execute ---
            try:
                result = await operation()
                await cb.record_success()
                return result
            except (LLMTimeoutError, LLMRateLimitError, LLMUpstreamError) as exc:
                await cb.record_failure()

                if not rp.is_retryable(exc):
                    raise

                if attempt > rp.max_retries:
                    log.warning(
                        "%s: retries exhausted after %d attempts — last error: %s",
                        self.model_identifier(),
                        rp.max_retries,
                        exc,
                    )
                    raise

                delay_ms = rp.delay_for_attempt(attempt)
                log.info(
                    "%s: attempt %d/%d failed (%s), retrying in %dms (jittered)",
                    self.model_identifier(),
                    attempt,
                    rp.max_retries,
                    exc,
                    delay_ms,
                )
                await asyncio.sleep(delay_ms / 1000.0)

            except (LLMAuthenticationError, LLMBadRequestError, LLMValidationError):
                # Non-retryable — record the failure but do NOT retry
                await cb.record_failure()
                raise

        # Guard: should never reach here
        raise LLMProviderError(
            f"{self.model_identifier()}: unexpected exit from retry loop",
            provider=self.model_identifier(),
        )

    @abstractmethod
    async def complete(
        self,
        messages: list,
        response_model: type[ResponseModelT],
    ) -> ResponseModelT:
        """Send *messages* to the model and return a validated *response_model* instance.

        Parameters
        ----------
        messages:
            Ordered list of :class:`Message` objects.
        response_model:
            A Pydantic V2 ``BaseModel`` *class* (not an instance) that describes
            the expected response shape.  The provider must JSON-serialise the
            model's schema into the request and validate the raw response against
            this class before returning.

        Returns
        -------
        ResponseModelT
            A fully-validated, frozen-safe instance of *response_model*.

        Raises
        ------
        LLMValidationError
            The model returned valid JSON that does not match *response_model*.
        LLMProviderError
            Any upstream API error, connection failure, or unexpected response.
        LLMTimeoutError
            The upstream call exceeded the configured timeout.
        """
        ...

    @abstractmethod
    def model_identifier(self) -> str:
        """Return the ``"provider/model"`` identifier for ``event_log`` rows.

        Examples: ``"anthropic/claude-opus-4-6"``, ``"local/cognitive-model"``.
        """
        ...
