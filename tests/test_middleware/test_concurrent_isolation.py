from __future__ import annotations

import asyncio

import httpx
from starlette.applications import Starlette

from routeflow.tracing import Trace


def test_concurrent_requests_get_correctly_isolated_traces(
    app_and_traces: tuple[Starlette, list[Trace]],
) -> None:
    """The waiter-with-many-tables scenario end to end, through the real
    middleware this time (Phase 1's version tested the ContextVar
    directly). N requests interleaved on one event loop must each open
    their own trace, see only their own tracked spans, and never observe
    another request's trace — even though the handler `await`s partway
    through, giving the event loop a chance to interleave them.
    """
    app, traces = app_and_traces

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await asyncio.gather(
                *(client.get(f"/orders/{order_id}") for order_id in range(10))
            )

    asyncio.run(scenario())

    assert len(traces) == 10
    seen_paths = {trace.path for trace in traces}
    assert seen_paths == {f"/orders/{i}" for i in range(10)}

    for trace in traces:
        # Each trace's own tracked span must belong to that same trace,
        # not one interleaved from a neighboring request.
        (span,) = trace.spans.values()
        assert span.trace_id == trace.trace_id
        assert span.name == "validate_order"
        expected_id = trace.path.removeprefix("/orders/")
        assert span.args["order_id"] == repr(expected_id)
