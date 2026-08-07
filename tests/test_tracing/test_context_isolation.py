from __future__ import annotations

import asyncio

from routeflow.tracing import Trace
from routeflow.tracing.context import (
    get_current_trace,
    reset_current_trace,
    set_current_trace,
)

# No pytest-asyncio dependency needed: asyncio.run() inside an ordinary
# `def` test is enough to exercise concurrent coroutines.


def test_concurrent_requests_never_see_each_others_trace() -> None:
    """The waiter-with-many-tables scenario: N requests interleaved on one
    event loop must each only ever see their own trace, never another's.
    """

    async def handle_request(label: str) -> str:
        trace = Trace(method="GET", path=f"/{label}")
        token = set_current_trace(trace)
        try:
            await asyncio.sleep(0.001)  # yield, let other requests interleave
            assert get_current_trace() is trace, f"{label} saw the wrong trace"
            await asyncio.sleep(0.001)
            assert get_current_trace() is trace, f"{label} saw the wrong trace"
            return label
        finally:
            reset_current_trace(token)

    async def scenario() -> list[str]:
        return await asyncio.gather(
            handle_request("orders"),
            handle_request("payments"),
            handle_request("health"),
        )

    results = asyncio.run(scenario())
    assert results == ["orders", "payments", "health"]


def test_asyncio_task_gets_a_context_snapshot_not_a_live_view() -> None:
    """asyncio.create_task() copies the current context at creation time —
    a task doesn't see later changes the parent makes, and the parent
    doesn't see changes the task makes. This is the propagation gap
    background tasks fall into if it isn't handled explicitly.
    """

    async def scenario() -> Trace:
        trace_a = Trace(method="GET", path="/a")
        token_a = set_current_trace(trace_a)
        seen_in_child: list[Trace | None] = []

        async def child() -> None:
            await asyncio.sleep(0)  # give the parent a chance to change context first
            seen_in_child.append(get_current_trace())

        task = asyncio.create_task(child())

        # Change the parent's context *after* the task was created.
        trace_b = Trace(method="GET", path="/b")
        token_b = set_current_trace(trace_b)

        await task
        reset_current_trace(token_b)
        reset_current_trace(token_a)

        assert seen_in_child == [trace_a], (
            "child task should see the trace that was current when it was "
            "created, not a later change made by its parent"
        )
        return trace_a

    asyncio.run(scenario())
