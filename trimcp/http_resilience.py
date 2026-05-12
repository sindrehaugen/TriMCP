"""Outbound HTTP resilience for non-LLM integrations (OAuth, webhooks, …).

Uses :mod:`tenacity` with exponential backoff and *full jitter* (same strategy as
:class:`trimcp.providers.base.RetryPolicy`) so concurrent workers do not retry in lockstep
after shared outages or rate limits — avoiding thundering herds toward third-party APIs.

LLM traffic should continue to use :meth:`trimcp.providers.base.LLMProvider.execute_with_retry`;
this module covers other ``httpx`` call sites that previously retried not at all or surfaced only
generic exceptions.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
)
from tenacity.before_sleep import before_sleep_log

log = logging.getLogger(__name__)

T = TypeVar("T")


class ExternalAPIError(Exception):
    """Base class for outbound HTTP integration failures (non-LLM)."""

    def __init__(
        self,
        message: str,
        *,
        operation: str = "http",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code


class ExternalAPITransientError(ExternalAPIError):
    """Transient failure — timeouts, transport errors, HTTP 429 / 5xx.

    ``retry_after_s`` may be set when the upstream returned ``Retry-After`` (seconds).
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str = "http",
        status_code: int | None = None,
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message, operation=operation, status_code=status_code)
        self.retry_after_s = retry_after_s


class ExternalAPIClientError(ExternalAPIError):
    """Non-retryable client or upstream rejection (typical 4xx except 429)."""


class ExternalAPIRetriesExhaustedError(ExternalAPIError):
    """All retry attempts failed for a transient error chain."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        last_error: Exception,
        attempts: int,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, operation=operation, status_code=status_code)
        self.last_error = last_error
        self.attempts = attempts
        if isinstance(last_error, ExternalAPIError) and last_error.status_code is not None:
            self.status_code = last_error.status_code


def _backoff_cap_ms(
    attempt: int,
    *,
    base_delay_ms: int,
    max_delay_ms: int,
    backoff_factor: float,
) -> int:
    return min(int(base_delay_ms * (backoff_factor ** (attempt - 1))), max_delay_ms)


def _wait_seconds_policy(
    *,
    base_delay_ms: int,
    max_delay_ms: int,
    backoff_factor: float,
):
    """Build tenacity ``wait`` callable with full jitter and optional Retry-After merge."""

    def wait_policy(retry_state):  # type: ignore[no-untyped-def]
        attempt = retry_state.attempt_number
        cap_ms = _backoff_cap_ms(
            attempt,
            base_delay_ms=base_delay_ms,
            max_delay_ms=max_delay_ms,
            backoff_factor=backoff_factor,
        )
        exc: BaseException | None = None
        if retry_state.outcome is not None and retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
        if isinstance(exc, ExternalAPITransientError) and exc.retry_after_s is not None:
            hint_ms = min(max_delay_ms, int(exc.retry_after_s * 1000))
            cap_ms = max(cap_ms, hint_ms)
        # Full jitter in [0, cap_ms] — spreads wakeup times across workers (AWS pattern).
        delay_ms = max(1, int(random.uniform(0, max(1, cap_ms))))
        return delay_ms / 1000.0

    return wait_policy


async def execute_http_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str = "http",
    max_retries: int = 3,
    base_delay_ms: int = 1_000,
    max_delay_ms: int = 30_000,
    max_total_ms: int = 60_000,
    backoff_factor: float = 2.0,
) -> T:
    """Run an async *operation* under tenacity retry + full jitter (no circuit breaker).

    Raises
    ------
    ExternalAPIRetriesExhaustedError
        After retry budget is exhausted for :class:`ExternalAPITransientError` subclasses.
    ExternalAPIClientError
        Propagated immediately without retry.
    """

    stop = stop_after_attempt(max_retries + 1) | stop_after_delay(max_total_ms / 1000.0)
    retry_predicate = retry_if_exception(lambda exc: isinstance(exc, ExternalAPITransientError))

    async def _run_once() -> T:
        return await operation()

    try:
        return await AsyncRetrying(
            stop=stop,
            wait=_wait_seconds_policy(
                base_delay_ms=base_delay_ms,
                max_delay_ms=max_delay_ms,
                backoff_factor=backoff_factor,
            ),
            retry=retry_predicate,
            before_sleep=before_sleep_log(log, logging.INFO),
            reraise=False,
        )(_run_once)
    except RetryError as re:
        last_exc = re.last_attempt.exception()
        attempts = re.last_attempt.attempt_number
        if last_exc is None:
            raise ExternalAPIRetriesExhaustedError(
                f"{operation_name}: retries exhausted after {attempts} attempt(s) (no exception)",
                operation=operation_name,
                last_error=RuntimeError("retry exhausted without captured exception"),
                attempts=attempts,
            ) from None
        if isinstance(last_exc, ExternalAPIClientError):
            raise last_exc
        if isinstance(last_exc, ExternalAPIRetriesExhaustedError):
            raise last_exc
        if not isinstance(last_exc, BaseException):
            raise last_exc
        log.warning(
            "%s: HTTP retries exhausted after %d attempt(s) — last error: %s",
            operation_name,
            attempts,
            last_exc,
        )
        raise ExternalAPIRetriesExhaustedError(
            f"{operation_name}: retries exhausted after {attempts} attempt(s): {last_exc}",
            operation=operation_name,
            last_error=last_exc if isinstance(last_exc, Exception) else RuntimeError(str(last_exc)),
            attempts=attempts,
        ) from last_exc


def classify_httpx_response(
    resp: httpx.Response,
    *,
    operation: str,
    error_detail: str = "",
) -> None:
    """Raise typed API errors for a finished ``httpx`` response (no network I/O)."""
    status = resp.status_code
    tail = (error_detail or resp.text[:500]).strip()

    if status == 429:
        retry_after_s: int | None = None
        try:
            retry_after_s = int(resp.headers.get("retry-after", ""))
        except (ValueError, TypeError):
            pass
        raise ExternalAPITransientError(
            f"{operation}: rate limited (HTTP 429)" + (f" — {tail}" if tail else ""),
            operation=operation,
            status_code=429,
            retry_after_s=retry_after_s,
        )

    if status >= 500:
        raise ExternalAPITransientError(
            f"{operation}: upstream error (HTTP {status})" + (f" — {tail}" if tail else ""),
            operation=operation,
            status_code=status,
        )

    if not resp.is_success:
        raise ExternalAPIClientError(
            f"{operation}: HTTP {status}" + (f" — {tail}" if tail else ""),
            operation=operation,
            status_code=status,
        )


async def oauth_token_post_form(
    url: str,
    data: dict[str, str],
    *,
    operation: str,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> dict:
    """POST ``application/x-www-form-urlencoded`` to an OAuth token endpoint with retries."""

    async def once() -> dict:
        hdrs = dict(headers or {})
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=hdrs, data=data)
        except httpx.TimeoutException as exc:
            raise ExternalAPITransientError(
                f"{operation}: request timed out after {timeout}s",
                operation=operation,
            ) from exc
        except httpx.RequestError as exc:
            raise ExternalAPITransientError(
                f"{operation}: transport error: {exc}",
                operation=operation,
            ) from exc
        classify_httpx_response(resp, operation=operation)
        try:
            return resp.json()
        except ValueError as exc:
            raise ExternalAPIClientError(
                f"{operation}: token endpoint returned non-JSON body",
                operation=operation,
                status_code=resp.status_code,
            ) from exc

    return await execute_http_with_retry(once, operation_name=operation)
