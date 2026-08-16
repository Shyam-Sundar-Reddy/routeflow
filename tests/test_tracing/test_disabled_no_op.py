from __future__ import annotations

import asyncio

import pytest

from routeflow.tracing import track
from routeflow.tracing.context import get_current_span, get_current_trace
from routeflow.tracing.lifecycle import span_scope

# Deliberately no `trace` fixture in any of these — that's the entire
# point: no active trace at all is exactly the state RouteFlow disabled
# (ROUTEFLOW_ENABLED=0 / enabled=False) leaves things in, and everything
# here must behave as a true no-op rather than raise. Regression coverage
# for a real bug report: @track used to call open_span() unconditionally,
# which raised RuntimeError with no active trace - turning every
# @track-ed endpoint into an unhandled 500 the moment tracing was
# disabled, exactly the scenario the flag exists to make safe.


def test_span_scope_is_a_true_no_op_with_no_active_trace() -> None:
    assert get_current_trace() is None  # sanity: nothing set one

    with span_scope("some_call") as span:
        assert span is None
        ran = True

    assert ran


def test_track_runs_the_function_normally_with_no_active_trace() -> None:
    @track
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_track_runs_async_function_normally_with_no_active_trace() -> None:
    @track
    async def add(a: int, b: int) -> int:
        return a + b

    assert asyncio.run(add(2, 3)) == 5


def test_track_with_get_current_span_log_inside_no_active_trace() -> None:
    """The exact pattern this project's own examples use
    (get_current_span().log(...) inside a @track-ed function) - must not
    crash with AttributeError just because there's no active trace to
    attach the log to.
    """

    @track
    def do_work(x: int) -> int:
        get_current_span().log("doing work")  # must not raise
        return x * 2

    assert do_work(5) == 10


def test_get_current_span_returns_a_safe_placeholder_with_no_trace() -> None:
    span = get_current_span()
    assert span is not None
    span.log("harmless")  # must not raise
    span.record_error(ValueError("also harmless"))  # must not raise


def test_exception_inside_a_no_op_span_still_propagates_unchanged() -> None:
    """@track's "observe only, never alter behavior" contract must hold
    in the disabled case too - an exception isn't swallowed just because
    there's no span to record it on.
    """

    @track
    def boom() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        boom()
