from __future__ import annotations

import asyncio

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


def test_async_function_produces_a_span(trace: Trace) -> None:
    @track
    async def fetch(x: int) -> int:
        await asyncio.sleep(0)
        return x * 2

    result = asyncio.run(fetch(21))

    assert result == 42
    (span,) = trace.spans.values()
    assert span.name == "fetch"
    assert span.status == "ok"
    assert span.duration_ms is not None
