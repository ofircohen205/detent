"""Unit tests for the CircuitBreaker state machine."""

import pytest

from detent.circuit_breaker import CircuitBreaker, CircuitOpenError


async def _failing_coroutine() -> None:
    raise RuntimeError("failure")


async def _succeeding_coroutine() -> str:
    return "ok"


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker("test", failure_threshold=2, recovery_window_s=60.0)
    with pytest.raises(RuntimeError):
        await cb.call(_failing_coroutine())
    with pytest.raises(RuntimeError):
        await cb.call(_failing_coroutine())
    assert cb.state == "open"
    with pytest.raises(CircuitOpenError):
        await cb.call(_failing_coroutine())


@pytest.mark.asyncio
async def test_half_open_recovery_success(monkeypatch):
    cb = CircuitBreaker("probe", failure_threshold=1, recovery_window_s=0.0)
    with pytest.raises(RuntimeError):
        await cb.call(_failing_coroutine())
    assert cb.state == "open"

    monkeypatch.setattr("detent.circuit_breaker.time.monotonic", lambda: (cb._opened_at or 0) + 1)
    result = await cb.call(_succeeding_coroutine())
    assert result == "ok"
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_half_open_recovery_failure(monkeypatch):
    cb = CircuitBreaker("retry", failure_threshold=1, recovery_window_s=0.0)
    with pytest.raises(RuntimeError):
        await cb.call(_failing_coroutine())
    assert cb.state == "open"

    monkeypatch.setattr("detent.circuit_breaker.time.monotonic", lambda: (cb._opened_at or 0) + 1)
    with pytest.raises(RuntimeError):
        await cb.call(_failing_coroutine())
    assert cb.state == "open"
