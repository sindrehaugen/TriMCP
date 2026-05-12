"""Tests for trimcp.http_resilience — tenacity-backed outbound HTTP retries."""

from __future__ import annotations

import pytest

import trimcp.http_resilience as hr


@pytest.mark.asyncio
async def test_execute_http_with_retry_recovers_after_transient():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise hr.ExternalAPITransientError("temporary", operation="t")
        return "ok"

    out = await hr.execute_http_with_retry(
        op,
        operation_name="t",
        max_retries=3,
        base_delay_ms=1,
        max_delay_ms=50,
        max_total_ms=5000,
    )
    assert out == "ok"
    assert calls == 2


@pytest.mark.asyncio
async def test_execute_http_with_retry_client_error_not_retried():
    calls = 0

    async def op():
        nonlocal calls
        calls += 1
        raise hr.ExternalAPIClientError("bad request", operation="t", status_code=400)

    with pytest.raises(hr.ExternalAPIClientError):
        await hr.execute_http_with_retry(
            op,
            operation_name="t",
            max_retries=3,
            base_delay_ms=1,
        )
    assert calls == 1


@pytest.mark.asyncio
async def test_execute_http_with_retry_exhaustion_raises_distinct_exception():
    async def op():
        raise hr.ExternalAPITransientError("always", operation="t")

    with pytest.raises(hr.ExternalAPIRetriesExhaustedError) as ei:
        await hr.execute_http_with_retry(
            op,
            operation_name="t",
            max_retries=2,
            base_delay_ms=1,
            max_delay_ms=20,
            max_total_ms=5000,
        )
    assert ei.value.operation == "t"
    assert ei.value.attempts >= 1
    assert isinstance(ei.value.last_error, hr.ExternalAPITransientError)
