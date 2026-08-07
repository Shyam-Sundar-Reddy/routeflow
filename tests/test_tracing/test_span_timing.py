from __future__ import annotations

import time

from routeflow.tracing import Trace, span_scope
from routeflow.tracing.lifecycle import close_span, open_span


def test_duration_is_none_until_closed(trace: Trace) -> None:
    span = open_span("handle_order")
    assert span.duration is None
    assert span.duration_ms is None


def test_close_span_sets_ok_status(trace: Trace) -> None:
    span = open_span("handle_order")
    close_span(span)
    assert span.status == "ok"
    assert span.end_time is not None


def test_close_span_records_a_real_duration(trace: Trace) -> None:
    span = open_span("handle_order")
    time.sleep(0.01)
    close_span(span)

    # Guards against the perf_counter regression this project already hit
    # once: time.monotonic() on Windows is backed by GetTickCount64 at
    # ~15ms resolution, so a 10ms sleep could read back as 0ms duration.
    assert span.duration_ms is not None
    assert span.duration_ms >= 5


def test_span_scope_closes_on_normal_exit(trace: Trace) -> None:
    with span_scope("handle_order") as span:
        assert span.end_time is None  # still open inside the block

    assert span.end_time is not None
    assert span.status == "ok"


def test_span_scope_registers_span_on_trace(trace: Trace) -> None:
    with span_scope("handle_order") as span:
        pass

    assert trace.spans[span.span_id] is span
