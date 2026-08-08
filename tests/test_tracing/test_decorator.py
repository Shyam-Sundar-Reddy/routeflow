from __future__ import annotations

from routeflow.tracing import Trace, track


def test_sync_function_produces_a_span(trace: Trace) -> None:
    @track
    def add(a: int, b: int) -> int:
        return a + b

    result = add(2, 3)

    assert result == 5
    (span,) = trace.spans.values()
    assert span.name == "add"
    assert span.status == "ok"
    assert span.duration_ms is not None
